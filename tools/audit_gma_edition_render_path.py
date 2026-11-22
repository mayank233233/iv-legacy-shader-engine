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
    ff_candidates = []
    mismatches = []
    for draw in draws:
        targets = draw.get("render_targets", [])
        depth = draw.get("depth_stencil_target")
        for target in targets:
            if target.get("index") != 0:
                continue
            pair = {
                "draw_seq": draw.get("seq"),
                "rt_width": target.get("width"),
                "rt_height": target.get("height"),
                "depth_width": depth.get("width") if depth else None,
                "depth_height": depth.get("height") if depth else None,
            }
            target_pairs.append(pair)
            if depth and (depth.get("width") != target.get("width") or
                          depth.get("height") != target.get("height")):
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
                "eligibility": "candidate_only_not_replay_approved",
            })

    return {
        "input_log": str(path),
        "draw_calls_observed": len(draws),
        "requested_internal_size": {"width": width, "height": height},
        "lowres_capture_status": (
            "matching_rt_depth_pairs_observed" if target_pairs and not mismatches
            else "missing_or_mismatched_rt_depth_evidence"
        ),
        "render_target_depth_pairs": target_pairs,
        "render_target_depth_mismatches": mismatches,
        "fixed_function_candidates": ff_candidates[:max(0, draw_limit)],
        "fixed_function_candidate_count": len(ff_candidates),
        "limitations": [
            "The current ASI does not capture SetViewport; viewport compatibility is unknown.",
            "This audit does not prove a selected RT is the main scene target.",
            "A Present-time upscale may include UI and post-processing.",
            "FVF presence does not prove vertex data or material semantics are suitable.",
            "No candidate is replayed or modified by this tool.",
            "Log timings are CPU/API observations, not GPU execution time.",
        ],
    }


def self_test() -> None:
    # Test the conservative candidate predicate using a tiny synthetic object
    # by validating the report schema through a temporary synthetic log.
    import tempfile
    from pathlib import Path
    synthetic = """DRAW_CALL seq=1 frame=1 kind=DrawIndexedPrimitive device=0x1 primitive=4 primitive_count=2 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=4 start_index=0 vs=0x0 ps=0x0 vertex_declaration=0x0 fvf=0x112 render_targets=0:0x10:320:240:21:3:1:0:0:0 depth_target=0x20:320:240:75:2:0:0:0:0 sampler_hash=0 sampler_count=0 render_state_hash=0 render_state_count=0 texture_stage_hash=0 texture_stage_count=0 hr=0x00000000
"""
    with tempfile.TemporaryDirectory() as temp:
        path = Path(temp) / "synthetic.log"
        path.write_text(synthetic, encoding="utf-8")
        result = audit(path)
    assert result["draw_calls_observed"] == 1
    assert result["fixed_function_candidate_count"] == 1
    assert result["lowres_capture_status"] == "matching_rt_depth_pairs_observed"
    assert result["fixed_function_candidates"][0]["eligibility"] == "candidate_only_not_replay_approved"
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
