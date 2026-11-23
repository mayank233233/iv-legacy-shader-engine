#!/usr/bin/env python3
"""Read-only audit of GTA IV D3D9 render-path captures for GMA experiments.

This tool does not alter the renderer. It identifies low-resolution RT/depth
mismatches and ranks draw records for a future fixed-function compatibility
probe. A candidate is not proof that replaying the draw is safe.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from analyze_asi_log import analyze_log


def audit(path: Path, width: int = 320, height: int = 240,
          draw_limit: int = 10) -> dict:
    data = analyze_log(path)
    draws = data.get("draw_calls", [])
    target_pairs = []
    mismatches = []
    ff_candidates = []
    viewport_size_counts: dict[str, int] = {}
    viewport_unknown_draws = []
    viewport_rt0_extent_differences = []
    rt0_missing_draws = []
    depth_missing_draws = []
    viewport_known_count = 0

    for draw in draws:
        targets = draw.get("render_targets", [])
        depth = draw.get("depth_stencil_target")
        viewport = draw.get("viewport")
        if viewport:
            viewport_known_count += 1
            size_key = f"{viewport.get('width')}x{viewport.get('height')}"
            viewport_size_counts[size_key] = viewport_size_counts.get(size_key, 0) + 1
        else:
            viewport_unknown_draws.append(draw.get("seq"))

        rt0 = next((target for target in targets if target.get("index") == 0), None)
        if rt0 is None:
            rt0_missing_draws.append(draw.get("seq"))
        else:
            if viewport and (
                viewport.get("width") != rt0.get("width") or
                viewport.get("height") != rt0.get("height") or
                viewport.get("x") != 0 or viewport.get("y") != 0
            ):
                viewport_rt0_extent_differences.append({
                    "draw_seq": draw.get("seq"),
                    "viewport": viewport,
                    "rt0_width": rt0.get("width"),
                    "rt0_height": rt0.get("height"),
                })

            if depth is None:
                depth_missing_draws.append(draw.get("seq"))
            else:
                depth_covers_rt0 = (
                    depth.get("width", -1) >= rt0.get("width", 0) and
                    depth.get("height", -1) >= rt0.get("height", 0)
                )
                multisample_type_matches = (
                    depth.get("multisample_type") == rt0.get("multisample_type")
                )
                multisample_quality_matches = (
                    depth.get("multisample_quality") == rt0.get("multisample_quality")
                )
                mismatch_reasons = []
                if not depth_covers_rt0:
                    mismatch_reasons.append("depth_surface_smaller_than_render_target")
                if not multisample_type_matches:
                    mismatch_reasons.append("multisample_type_mismatch")
                if not multisample_quality_matches:
                    mismatch_reasons.append("multisample_quality_mismatch")

                if (
                    depth.get("width") == rt0.get("width") and
                    depth.get("height") == rt0.get("height")
                ):
                    depth_extent_relation = "equal"
                elif depth_covers_rt0:
                    depth_extent_relation = "depth_surface_larger"
                else:
                    depth_extent_relation = "depth_surface_does_not_cover_rt0"

                pair = {
                    "draw_seq": draw.get("seq"),
                    "rt_object": rt0.get("object"),
                    "depth_object": depth.get("object"),
                    "rt_width": rt0.get("width"),
                    "rt_height": rt0.get("height"),
                    "depth_width": depth.get("width"),
                    "depth_height": depth.get("height"),
                    "rt_format": rt0.get("format"),
                    "depth_format": depth.get("format"),
                    "rt_multisample_type": rt0.get("multisample_type"),
                    "depth_multisample_type": depth.get("multisample_type"),
                    "rt_multisample_quality": rt0.get("multisample_quality"),
                    "depth_multisample_quality": depth.get("multisample_quality"),
                    "depth_extent_relation": depth_extent_relation,
                    "depth_covers_rt0": depth_covers_rt0,
                    "multisample_type_matches": multisample_type_matches,
                    "multisample_quality_matches": multisample_quality_matches,
                    "mismatch_reasons": mismatch_reasons,
                    "viewport": viewport,
                }
                target_pairs.append(pair)
                if mismatch_reasons:
                    mismatches.append(pair)

        # Fixed-function requires both programmable stages disabled and a
        # non-zero FVF. Declaration-based draws are not considered eligible.
        if (not draw.get("bound_vs_object") and
                not draw.get("bound_ps_object") and
                draw.get("fvf", 0) != 0 and
                not draw.get("vertex_declaration_object")):
            ff_candidates.append({
                "seq": draw.get("seq"),
                "frame": draw.get("frame"),
                "fvf": draw.get("fvf"),
                "primitive_name": draw.get("primitive_name"),
                "primitive_count": draw.get("primitive_count"),
                "num_vertices": draw.get("num_vertices"),
                "render_targets": targets,
                "depth_stencil_target": depth,
                "viewport": viewport,
                "eligibility": "candidate_only_not_replay_approved",
            })

    if not draws:
        pair_status = "not_observed"
    elif mismatches:
        pair_status = "extent_or_multisample_mismatch_observed"
    elif rt0_missing_draws or depth_missing_draws or not target_pairs:
        pair_status = "incomplete_rt_depth_evidence"
    else:
        pair_status = "extent_and_multisample_compatible_pairs_observed"

    return {
        "input_log": str(path),
        "draw_calls_observed": len(draws),
        "viewport_capture_status": (
            "complete" if draws and viewport_known_count == len(draws)
            else "partial" if viewport_known_count
            else "not_observed"
        ),
        "viewport_draws_observed": viewport_known_count,
        "viewport_unknown_draw_sequences": viewport_unknown_draws,
        "viewport_dimensions": viewport_size_counts,
        "viewport_rt0_extent_differences": viewport_rt0_extent_differences,
        "rt0_missing_draw_sequences": rt0_missing_draws,
        "depth_stencil_missing_draw_sequences": depth_missing_draws,
        "render_target_depth_pair_count": len(target_pairs),
        "requested_internal_size": {"width": width, "height": height},
        "lowres_capture_status": pair_status,
        "render_target_depth_pairs": target_pairs,
        "render_target_depth_mismatches": mismatches,
        "fixed_function_candidates": ff_candidates[:max(0, draw_limit)],
        "fixed_function_candidate_count": len(ff_candidates),
        "limitations": [
            "Pair classification checks only that the depth surface covers RT0 and that multisample type and quality match.",
            "D3D9 depth-format compatibility via CheckDepthStencilMatch is not verified by this pair classifier; numeric formats are reported for review.",
            "A depth surface larger than RT0 is valid under D3D9 and is not treated as a mismatch.",
            "Viewport dimensions are recorded per draw; a viewport/RT0 size difference may be intentional cropping and is not automatically an error.",
            "This audit does not prove a selected RT is the main scene target or identify surface lifetime and pass ordering.",
            "A Present-time upscale may include UI and post-processing.",
            "FVF presence does not prove vertex data or material semantics are suitable.",
            "No candidate is replayed or modified by this tool.",
            "Log timings are CPU/API observations, not GPU execution time.",
        ],
    }


def self_test() -> None:
    import tempfile

    template = (
        "DRAW_CALL seq={seq} frame=1 kind=DrawIndexedPrimitive device=0x1 "
        "primitive=4 primitives=2 start_vertex=0 base_vertex=0 min_vertex=0 "
        "num_vertices=4 start_index=0 bound_vs=0x0 bound_ps=0x0 "
        "vertex_decl=0x0 fvf=0x112 "
        "render_targets={render_targets} depth_target={depth_target} "
        "viewport={viewport} sampler_hash=0 sampler_count=0 "
        "render_state_hash=0 render_state_count=0 "
        "texture_stage_hash=0 texture_stage_count=0 hr=0x00000000\n"
    )
    rt0 = "0:0x10:320:240:21:3:1:0:0:0"
    depth_equal = "0x20:320:240:75:2:0:0:0:0"
    viewport_full = "0:0:320:240:00000000:3F800000"

    with tempfile.TemporaryDirectory() as temp:
        root = Path(temp)

        def run_case(name: str, rt: str, depth: str,
                     viewport: str = viewport_full) -> dict:
            path = root / f"{name}.log"
            path.write_text(
                template.format(
                    seq=1, render_targets=rt, depth_target=depth,
                    viewport=viewport,
                ),
                encoding="utf-8",
            )
            return audit(path)

        matching = run_case("matching", rt0, depth_equal)
        assert matching["draw_calls_observed"] == 1
        assert matching["fixed_function_candidate_count"] == 1
        assert matching["lowres_capture_status"] == (
            "extent_and_multisample_compatible_pairs_observed"
        )
        assert matching["render_target_depth_pair_count"] == 1
        assert matching["render_target_depth_pairs"][0]["rt_object"] == "0x10"
        assert matching["render_target_depth_pairs"][0]["depth_object"] == "0x20"
        assert matching["fixed_function_candidates"][0]["eligibility"] == (
            "candidate_only_not_replay_approved"
        )

        # D3D9 permits a depth surface larger than its paired render target.
        larger_depth = run_case(
            "larger-depth", rt0, "0x20:320:256:75:2:0:0:0:0"
        )
        assert larger_depth["lowres_capture_status"] == (
            "extent_and_multisample_compatible_pairs_observed"
        )
        assert larger_depth["render_target_depth_pairs"][0][
            "depth_extent_relation"
        ] == "depth_surface_larger"

        smaller_depth = run_case(
            "smaller-depth", rt0, "0x20:320:239:75:2:0:0:0:0"
        )
        assert smaller_depth["lowres_capture_status"] == (
            "extent_or_multisample_mismatch_observed"
        )
        assert "depth_surface_smaller_than_render_target" in (
            smaller_depth["render_target_depth_mismatches"][0]["mismatch_reasons"]
        )

        msaa_type_mismatch = run_case(
            "msaa-type", "0:0x10:320:240:21:3:1:0:4:1",
            "0x20:320:240:75:2:0:0:0:2:1",
        )
        assert "multisample_type_mismatch" in (
            msaa_type_mismatch["render_target_depth_mismatches"][0]["mismatch_reasons"]
        )

        msaa_quality_mismatch = run_case(
            "msaa-quality", "0:0x10:320:240:21:3:1:0:2:1",
            "0x20:320:240:75:2:0:0:0:2:0",
        )
        assert "multisample_quality_mismatch" in (
            msaa_quality_mismatch["render_target_depth_mismatches"][0]["mismatch_reasons"]
        )

        missing_depth = run_case("missing-depth", rt0, "unknown")
        assert missing_depth["lowres_capture_status"] == "incomplete_rt_depth_evidence"
        assert missing_depth["depth_stencil_missing_draw_sequences"] == [1]
        assert missing_depth["render_target_depth_pair_count"] == 0

        missing_rt0 = run_case("missing-rt0", "", depth_equal)
        assert missing_rt0["lowres_capture_status"] == "incomplete_rt_depth_evidence"
        assert missing_rt0["rt0_missing_draw_sequences"] == [1]

        cropped_viewport = run_case(
            "cropped-viewport", rt0, depth_equal,
            "10:10:300:220:00000000:3F800000",
        )
        assert cropped_viewport["lowres_capture_status"] == (
            "extent_and_multisample_compatible_pairs_observed"
        )
        assert len(cropped_viewport["viewport_rt0_extent_differences"]) == 1

        empty_path = root / "empty.log"
        empty_path.write_text("", encoding="utf-8")
        empty = audit(empty_path)
        assert empty["lowres_capture_status"] == "not_observed"

    print("GMA edition render-path audit self-test passed")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--width", type=int, default=320)
    parser.add_argument("--height", type=int, default=240)
    parser.add_argument("--draw-limit", type=int, default=10)
    parser.add_argument("--json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.log is None or not args.log.is_file():
        parser.error("provide an existing IVLegacy.log or use --self-test")
    report = audit(args.log, args.width, args.height, args.draw_limit)
    rendered = json.dumps(report, indent=2)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
