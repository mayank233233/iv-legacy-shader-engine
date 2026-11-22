#!/usr/bin/env python3
"""Generate conservative paired VS2/PS2 candidates from a D3D9 capture.

This tool reuses the draw-level pairing audit and both stage downlevelers.
It emits bytecode only when every captured draw using a VS3/PS3 pair passes
the stage, interpolator, vertex-layout, sampler-binding and device-cap checks.
Runtime mappings require explicit approval of the *pair* (VS hash:PS hash).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tempfile
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import audit_shader_pairs
import audit_sm3_to_sm2
import audit_vs3_to_vs2

PAIR_RE = re.compile(r"^([0-9A-Fa-f]{16}):([0-9A-Fa-f]{16})$")


def normalize_pair(value: str) -> tuple[str, str]:
    match = PAIR_RE.fullmatch(value.strip())
    if not match:
        raise ValueError(
            "approved pair must be two 16-digit FNV-1a hashes separated by a colon"
        )
    return match.group(1).upper(), match.group(2).upper()


def draw_pair_candidate_reasons(draw: dict[str, Any]) -> list[str]:
    """Return blockers for paired bytecode generation; warnings remain reviewable."""
    reasons: list[str] = []

    if not draw.get("vertex_shader_hash") or not draw.get("pixel_shader_hash"):
        reasons.append("draw is missing one or both shader hashes")
        return reasons

    vertex_capture = draw.get("vertex_capture") or {}
    pixel_capture = draw.get("pixel_capture") or {}
    if vertex_capture.get("profile") != "vs_3_0":
        reasons.append("captured vertex shader is not a resolved vs_3_0 program")
    if pixel_capture.get("profile") != "ps_3_0":
        reasons.append("captured pixel shader is not a resolved ps_3_0 program")

    if draw.get("reasons"):
        reasons.extend(str(item) for item in draw["reasons"])

    vertex_stage = draw.get("vertex_stage") or {}
    pixel_stage = draw.get("pixel_stage") or {}
    if not vertex_stage.get("structural_candidate"):
        reasons.append("vertex stage did not pass the VS2 structural audit")
    if not pixel_stage.get("structural_candidate"):
        reasons.append("pixel stage did not pass the PS2 structural audit")

    interface = draw.get("interface") or {}
    if not interface.get("interface_matches"):
        reasons.append("original VS3/PS3 semantic or component interface does not match")
    if not interface.get("independent_vs2_ps2_allocations_match"):
        reasons.append("VS2 and PS2 register allocations require a paired relink")
    if interface.get("interpolation_review"):
        reasons.append("pixel input interpolation modifiers require manual lowering")

    layout = draw.get("vertex_input_layout") or {}
    if layout.get("status") != "verified_layout":
        reasons.append("the captured vertex declaration/FVF and stream layout are not fully verified")

    sampler_bindings = draw.get("sampler_bindings") or {}
    if sampler_bindings.get("missing_sampler_stages"):
        reasons.append("one or more sampled PS2 texture stages lack a captured non-null texture")

    limits = draw.get("device_limits") or {}
    if limits.get("vertex_shader_profile") != "vs_2_0":
        reasons.append("captured adapter does not confirm a VS2.0 capability")
    if limits.get("pixel_shader_profile") != "ps_2_0":
        reasons.append("captured adapter does not confirm a PS2.0 capability")

    integer_limits = (
        ("max_simultaneous_render_targets", "D3D9 render-target limit"),
        ("max_vertex_shader_constants", "MaxVertexShaderConst"),
        ("vs20_temporary_registers", "VS2 temporary-register limit"),
        ("ps20_temporary_registers", "PS2 temporary-register limit"),
        ("ps20_instruction_slots", "PS2 instruction-slot limit"),
    )
    for key, label in integer_limits:
        try:
            value = int(limits.get(key, -1))
        except (TypeError, ValueError):
            value = -1
        if value <= 0:
            reasons.append(f"captured {label} is unavailable")

    try:
        active_render_targets = int(limits.get("active_render_targets", 0))
        max_render_targets = int(limits.get("max_simultaneous_render_targets", -1))
    except (TypeError, ValueError):
        active_render_targets, max_render_targets = 0, -1
    if active_render_targets <= 0:
        reasons.append("no active render-target binding was captured for the draw")
    elif max_render_targets > 0 and active_render_targets > max_render_targets:
        reasons.append("captured active render-target count exceeds the adapter limit")

    return list(dict.fromkeys(reasons))


def group_draws_by_shader_pair(
    draws: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str], list[dict[str, Any]]], set[str], set[str]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    unpaired_vertex_hashes: set[str] = set()
    unpaired_pixel_hashes: set[str] = set()

    for draw in draws:
        vertex_hash = str(draw.get("vertex_shader_hash") or "").upper()
        pixel_hash = str(draw.get("pixel_shader_hash") or "").upper()
        valid_vertex = re.fullmatch(r"[0-9A-F]{16}", vertex_hash) is not None
        valid_pixel = re.fullmatch(r"[0-9A-F]{16}", pixel_hash) is not None

        if valid_vertex and valid_pixel:
            grouped[(vertex_hash, pixel_hash)].append(draw)
        else:
            if valid_vertex:
                unpaired_vertex_hashes.add(vertex_hash)
            if valid_pixel:
                unpaired_pixel_hashes.add(pixel_hash)

    return dict(grouped), unpaired_vertex_hashes, unpaired_pixel_hashes


def validate_approved_pairs(
    pair_records: list[dict[str, Any]],
    approved_pairs: set[tuple[str, str]],
    unpaired_vertex_hashes: set[str] | None = None,
    unpaired_pixel_hashes: set[str] | None = None,
) -> tuple[set[str], set[str]]:
    """Ensure every observed partner of a mapped shader is also approved and eligible."""
    if not approved_pairs:
        return set(), set()

    by_key = {
        (item["vertex_shader_hash"], item["pixel_shader_hash"]): item
        for item in pair_records
    }
    missing = approved_pairs - set(by_key)
    if missing:
        formatted = ", ".join(f"{vs}:{ps}" for vs, ps in sorted(missing))
        raise ValueError(f"approved pair(s) were not present in the capture: {formatted}")

    approved_vertex_hashes = {vs for vs, _ in approved_pairs}
    approved_pixel_hashes = {ps for _, ps in approved_pairs}
    unpaired_vertex_hashes = unpaired_vertex_hashes or set()
    unpaired_pixel_hashes = unpaired_pixel_hashes or set()

    blocked_vertex = approved_vertex_hashes & unpaired_vertex_hashes
    blocked_pixel = approved_pixel_hashes & unpaired_pixel_hashes
    if blocked_vertex or blocked_pixel:
        blocked = sorted(blocked_vertex | blocked_pixel)
        raise ValueError(
            "cannot map shader hash(es) that also appeared in unresolved draws: "
            + ", ".join(blocked)
        )

    for vertex_hash in approved_vertex_hashes:
        observed_partners = {
            key for key in by_key if key[0] == vertex_hash
        }
        if not observed_partners <= approved_pairs:
            raise ValueError(
                f"VS {vertex_hash} is also used with unapproved PS pair(s); "
                "a stage hash cannot select different VS2 interfaces per draw"
            )

    for pixel_hash in approved_pixel_hashes:
        observed_partners = {
            key for key in by_key if key[1] == pixel_hash
        }
        if not observed_partners <= approved_pairs:
            raise ValueError(
                f"PS {pixel_hash} is also used with unapproved VS pair(s); "
                "a stage hash cannot select different PS2 interfaces per draw"
            )

    for key in approved_pairs:
        record = by_key[key]
        if not record.get("emitted"):
            raise ValueError(
                f"approved pair {key[0]}:{key[1]} did not produce both stage bytecodes"
            )

    return approved_vertex_hashes, approved_pixel_hashes


def find_sm3_capture(
    capture_index: dict[str, list[tuple[Path, bytes, str, int, int]]],
    shader_hash: str,
    expected_stage: str,
) -> tuple[Path, bytes] | None:
    for path, data, stage, major, minor in capture_index.get(shader_hash, []):
        if stage == expected_stage and (major, minor) == (3, 0):
            return path, data
    return None


def emit_pair_candidates(
    pair_records: list[dict[str, Any]],
    capture_directory: Path,
    emit_directory: Path,
    fallback_prefix: str,
) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]], dict[str, dict[str, Any]]]:
    capture_index = audit_shader_pairs.index_captures(capture_directory)
    emit_directory.mkdir(parents=True, exist_ok=True)

    vertex_records: dict[str, dict[str, Any]] = {}
    pixel_records: dict[str, dict[str, Any]] = {}

    for pair in pair_records:
        if not pair.get("structural_pair_candidate"):
            continue

        vertex_hash = pair["vertex_shader_hash"]
        pixel_hash = pair["pixel_shader_hash"]
        vertex_capture = find_sm3_capture(capture_index, vertex_hash, "VS")
        pixel_capture = find_sm3_capture(capture_index, pixel_hash, "PS")
        pair_reasons: list[str] = []

        if vertex_capture is None:
            pair_reasons.append("matching captured vs_3_0 bytecode was not found")
        if pixel_capture is None:
            pair_reasons.append("matching captured ps_3_0 bytecode was not found")
        if pair_reasons:
            pair["emission_reasons"] = pair_reasons
            pair["emitted"] = False
            continue

        vertex_path, vertex_bytes = vertex_capture
        pixel_path, pixel_bytes = pixel_capture
        del vertex_path, pixel_path

        limits = pair.get("device_limits") or {}
        try:
            max_temps = int(limits["vs20_temporary_registers"])
            max_constants = int(limits["max_vertex_shader_constants"])
        except (KeyError, TypeError, ValueError):
            pair["emission_reasons"] = [
                "captured VS2 temporary-register or constant-register limit is unavailable"
            ]
            pair["emitted"] = False
            continue

        vertex_result = audit_vs3_to_vs2.lower_vs3_to_vs2(
            vertex_bytes,
            max_temps=max_temps,
            max_float_constants=max_constants,
        )
        pixel_result = audit_sm3_to_sm2.audit_and_lower_ps3(
            pixel_bytes,
            max_samplers=16,
            dependent_read_limit=3,
        )

        if not vertex_result.get("bytecode_emitted"):
            pair_reasons.extend(vertex_result.get("emission_reasons", []))
        if not pixel_result.get("eligible") or pixel_result.get("output_bytecode") is None:
            pair_reasons.extend(pixel_result.get("reasons", []))

        if pair_reasons:
            pair["emission_reasons"] = list(dict.fromkeys(pair_reasons))
            pair["emitted"] = False
            continue

        vertex_output = emit_directory / f"{vertex_hash}.vs20.vso"
        pixel_output = emit_directory / f"{pixel_hash}.ps20.pso"
        vertex_output.write_bytes(vertex_result["output_bytecode"])
        pixel_output.write_bytes(pixel_result["output_bytecode"])

        vertex_output_sha256 = hashlib.sha256(
            vertex_result["output_bytecode"]
        ).hexdigest()
        pixel_output_sha256 = hashlib.sha256(
            pixel_result["output_bytecode"]
        ).hexdigest()
        vertex_record = {
            **vertex_result,
            "status": "vs2_candidate_emitted",
            "source_fnv1a64": vertex_hash,
            "output_file": str(vertex_output),
            "output_sha256": vertex_output_sha256,
            "fallback_relative_path": (
                audit_vs3_to_vs2.validate_fallback_prefix(fallback_prefix)
                + "\\"
                + vertex_output.name
            ),
        }
        pixel_record = {
            **pixel_result,
            "source_fnv1a64": pixel_hash,
            "output_file": str(pixel_output),
            "output_sha256": pixel_output_sha256,
            "fallback_relative_path": (
                audit_sm3_to_sm2.validate_fallback_prefix(fallback_prefix)
                + "\\"
                + pixel_output.name
            ),
        }

        existing_vertex = vertex_records.get(vertex_hash)
        existing_pixel = pixel_records.get(pixel_hash)
        if existing_vertex and existing_vertex["output_sha256"] != vertex_output_sha256:
            pair["emission_reasons"] = [
                "the same VS source hash produced conflicting VS2 output candidates"
            ]
            pair["emitted"] = False
            continue
        if existing_pixel and existing_pixel["output_sha256"] != pixel_output_sha256:
            pair["emission_reasons"] = [
                "the same PS source hash produced conflicting PS2 output candidates"
            ]
            pair["emitted"] = False
            continue

        vertex_records[vertex_hash] = vertex_record
        pixel_records[pixel_hash] = pixel_record
        pair["vertex_output"] = {
            "file": str(vertex_output),
            "sha256": vertex_output_sha256,
        }
        pair["pixel_output"] = {
            "file": str(pixel_output),
            "sha256": pixel_output_sha256,
        }
        pair["emission_reasons"] = []
        pair["emitted"] = True

    return pair_records, vertex_records, pixel_records


def build_pair_records(
    draws: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], set[str], set[str]]:
    grouped, unpaired_vs, unpaired_ps = group_draws_by_shader_pair(draws)
    records: list[dict[str, Any]] = []

    for (vertex_hash, pixel_hash), pair_draws in sorted(grouped.items()):
        reasons_by_draw = [
            draw_pair_candidate_reasons(draw) for draw in pair_draws
        ]
        reasons = list(dict.fromkeys(
            reason for draw_reasons in reasons_by_draw for reason in draw_reasons
        ))
        first = pair_draws[0]
        limits = first.get("device_limits") or {}
        records.append({
            "vertex_shader_hash": vertex_hash,
            "pixel_shader_hash": pixel_hash,
            "draw_count": len(pair_draws),
            "draw_sequences": [draw.get("sequence") for draw in pair_draws],
            "structural_pair_candidate": not reasons,
            "reasons": reasons,
            "warnings": list(dict.fromkeys(
                warning for draw in pair_draws for warning in draw.get("warnings", [])
            )),
            "device_limits": limits,
            "status_counts": dict(sorted(
                Counter(str(draw.get("status", "unknown")) for draw in pair_draws).items()
            )),
            "emitted": False,
        })

    return records, unpaired_vs, unpaired_ps


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", type=Path, help="IVLegacy.log from one capture session")
    parser.add_argument("captures", type=Path, help="Matching IVLegacyCaptures directory")
    parser.add_argument("--emit-dir", type=Path, help="Write paired VS2/PS2 candidates here")
    parser.add_argument("--fallback-ini", type=Path, help="Merge explicitly approved pairs into both runtime map sections")
    parser.add_argument("--fallback-prefix", default="IVLegacyFallbacks")
    parser.add_argument(
        "--approved-pair", action="append", default=[],
        help="Approve one observed VS-hash:PS-hash pair after manual visual/state review",
    )
    parser.add_argument("--report", type=Path, help="Write the pair-generation JSON report")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if args.fallback_ini and not args.emit_dir:
        parser.error("--fallback-ini requires --emit-dir")
    if args.approved_pair and not args.fallback_ini:
        parser.error("--approved-pair requires --fallback-ini")
    if not args.log.is_file():
        parser.error(f"log file does not exist: {args.log}")
    if not args.captures.is_dir():
        parser.error(f"capture directory does not exist: {args.captures}")

    try:
        approved_pairs = {normalize_pair(item) for item in args.approved_pair}
        fallback_prefix = audit_vs3_to_vs2.validate_fallback_prefix(
            args.fallback_prefix
        )
    except ValueError as exc:
        parser.error(str(exc))

    audit_report = audit_shader_pairs.audit_log(args.log, args.captures)
    pair_records, unpaired_vs, unpaired_ps = build_pair_records(
        audit_report.get("draw_calls", [])
    )

    vertex_records: dict[str, dict[str, Any]] = {}
    pixel_records: dict[str, dict[str, Any]] = {}
    if args.emit_dir:
        pair_records, vertex_records, pixel_records = emit_pair_candidates(
            pair_records, args.captures, args.emit_dir, fallback_prefix
        )

    vertex_fallback_count = 0
    pixel_fallback_count = 0
    if args.fallback_ini:
        try:
            approved_vs, approved_ps = validate_approved_pairs(
                pair_records, approved_pairs, unpaired_vs, unpaired_ps
            )
            vertex_fallback_count = audit_vs3_to_vs2.write_vertex_fallback_ini(
                args.fallback_ini,
                list(vertex_records.values()),
                approved_vs,
            )
            pixel_fallback_count = audit_sm3_to_sm2.write_fallback_ini(
                args.fallback_ini,
                list(pixel_records.values()),
                approved_ps,
            )
        except (OSError, ValueError) as exc:
            print(f"ERROR: runtime pair map was not updated: {exc}", file=sys.stderr)
            return 1

    report = {
        "schema_version": 1,
        "input_log": str(args.log),
        "capture_directory": str(args.captures),
        "draw_calls_audited": audit_report.get("draw_calls_audited", 0),
        "unique_shader_pairs_audited": len(pair_records),
        "structural_pair_candidate_count": sum(
            1 for item in pair_records if item.get("structural_pair_candidate")
        ),
        "emitted_pair_count": sum(
            1 for item in pair_records if item.get("emitted")
        ),
        "approved_pair_count": len(approved_pairs),
        "vertex_fallback_mapping_count": vertex_fallback_count,
        "pixel_fallback_mapping_count": pixel_fallback_count,
        "unpaired_vertex_shader_hashes": sorted(unpaired_vs),
        "unpaired_pixel_shader_hashes": sorted(unpaired_ps),
        "pairs": pair_records,
        "scope_note": (
            "This tool emits only paired candidates that pass the captured stage, "
            "semantic, component, vertex-layout, sampler-binding and adapter-cap checks. "
            "Runtime mappings require explicit approval of each VS:PS pair, and every "
            "observed partner for a mapped stage hash must also be approved. Warnings "
            "about individual blend/depth/alpha/sampler values still require manual "
            "render-state and visual review. Synthetic or static checks do not prove "
            "GMA 3100 driver acceptance, GTA IV gameplay correctness or FPS."
        ),
    }

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for pair in pair_records:
        status = "emitted" if pair.get("emitted") else (
            "pair_candidate" if pair.get("structural_pair_candidate") else "rejected"
        )
        print(
            f"{status}: {pair['vertex_shader_hash']}:{pair['pixel_shader_hash']} "
            f"draws={pair['draw_count']}"
        )
        for reason in pair.get("reasons", []) + pair.get("emission_reasons", []):
            print(f"  - {reason}")

    print(
        f"Pair lowering complete: {report['structural_pair_candidate_count']} "
        f"structural candidate(s), {report['emitted_pair_count']} emitted, "
        f"{report['approved_pair_count']} approved pair(s), "
        f"{vertex_fallback_count} VS and {pixel_fallback_count} PS mapping(s)."
    )
    return 0


def _self_test() -> None:
    vertex_hash = "0123456789ABCDEF"
    pixel_hash = "FEDCBA9876543210"
    approved = normalize_pair(f"{vertex_hash.lower()}:{pixel_hash.lower()}")
    assert approved == (vertex_hash, pixel_hash)

    valid_draw = {
        "vertex_shader_hash": vertex_hash,
        "pixel_shader_hash": pixel_hash,
        "vertex_capture": {"profile": "vs_3_0"},
        "pixel_capture": {"profile": "ps_3_0"},
        "reasons": [],
        "warnings": ["blend/depth state values require manual review"],
        "vertex_stage": {"structural_candidate": True},
        "pixel_stage": {"structural_candidate": True},
        "interface": {
            "interface_matches": True,
            "independent_vs2_ps2_allocations_match": True,
            "interpolation_review": [],
        },
        "vertex_input_layout": {"status": "verified_layout"},
        "sampler_bindings": {"missing_sampler_stages": []},
        "device_limits": {
            "vertex_shader_profile": "vs_2_0",
            "pixel_shader_profile": "ps_2_0",
            "max_simultaneous_render_targets": 1,
            "active_render_targets": 1,
            "max_vertex_shader_constants": 96,
            "vs20_temporary_registers": 12,
            "ps20_temporary_registers": 12,
            "ps20_instruction_slots": 96,
        },
    }
    assert not draw_pair_candidate_reasons(valid_draw)
    bad_draw = dict(valid_draw)
    bad_draw["interface"] = dict(valid_draw["interface"])
    bad_draw["interface"]["independent_vs2_ps2_allocations_match"] = False
    assert any("paired relink" in reason for reason in draw_pair_candidate_reasons(bad_draw))

    records = [
        {
            "vertex_shader_hash": vertex_hash,
            "pixel_shader_hash": pixel_hash,
            "emitted": True,
        },
        {
            "vertex_shader_hash": vertex_hash,
            "pixel_shader_hash": "1111111111111111",
            "emitted": True,
        },
    ]
    try:
        validate_approved_pairs(
            records, {(vertex_hash, pixel_hash)}
        )
    except ValueError as exc:
        assert "unapproved PS pair" in str(exc)
    else:
        raise AssertionError("shared VS must not be mapped with an unapproved PS partner")

    approved_vs, approved_ps = validate_approved_pairs(
        records,
        {
            (vertex_hash, pixel_hash),
            (vertex_hash, "1111111111111111"),
        },
    )
    assert approved_vs == {vertex_hash}
    assert approved_ps == {pixel_hash, "1111111111111111"}

    try:
        validate_approved_pairs(
            [records[0]],
            {(vertex_hash, pixel_hash)},
            unpaired_vertex_hashes={vertex_hash},
        )
    except ValueError as exc:
        assert "unresolved draws" in str(exc)
    else:
        raise AssertionError("unpaired shader usage must prevent runtime map approval")

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        capture_dir = root / "captures"
        emit_dir = root / "emitted"
        capture_dir.mkdir()

        vs_words = [audit_vs3_to_vs2.VS3_VERSION]

        def vs_dcl(usage: int, register_type: int, register: int) -> list[int]:
            declaration = 0x80000000 | (usage & 0xF)
            return audit_vs3_to_vs2.make_instruction(
                audit_vs3_to_vs2.OP_DCL,
                declaration,
                audit_vs3_to_vs2.make_dest_token(register_type, register),
            )

        vs_words.extend(vs_dcl(
            audit_vs3_to_vs2.USAGE_POSITION,
            audit_vs3_to_vs2.REG_INPUT,
            0,
        ))
        vs_words.extend(vs_dcl(
            audit_vs3_to_vs2.USAGE_POSITION,
            audit_vs3_to_vs2.REG_OUTPUT,
            0,
        ))
        vs_words.extend(vs_dcl(
            audit_vs3_to_vs2.USAGE_COLOR,
            audit_vs3_to_vs2.REG_OUTPUT,
            1,
        ))
        vs_words.extend(audit_vs3_to_vs2.make_instruction(
            1,
            audit_vs3_to_vs2.make_dest_token(audit_vs3_to_vs2.REG_OUTPUT, 0),
            audit_vs3_to_vs2.make_source_token(audit_vs3_to_vs2.REG_INPUT, 0),
        ))
        vs_words.extend(audit_vs3_to_vs2.make_instruction(
            1,
            audit_vs3_to_vs2.make_dest_token(audit_vs3_to_vs2.REG_OUTPUT, 1),
            audit_vs3_to_vs2.make_source_token(audit_vs3_to_vs2.REG_INPUT, 0),
        ))
        vs_words.append(audit_vs3_to_vs2.OP_END)
        vs_bytes = audit_vs3_to_vs2.struct.pack(
            "<" + "I" * len(vs_words), *vs_words
        )

        ps_words = [audit_sm3_to_sm2.PS3_VERSION]
        audit_sm3_to_sm2.emit_instruction(
            ps_words,
            audit_sm3_to_sm2.OP_DCL,
            audit_sm3_to_sm2.USAGE_COLOR,
            audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_INPUT, 0),
        )
        audit_sm3_to_sm2.emit_instruction(
            ps_words,
            audit_sm3_to_sm2.OP_MOV,
            audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_TEMP, 0),
            audit_sm3_to_sm2.make_source(audit_sm3_to_sm2.REG_INPUT, 0),
        )
        audit_sm3_to_sm2.emit_instruction(
            ps_words,
            audit_sm3_to_sm2.OP_MOV,
            audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_COLOROUT, 0),
            audit_sm3_to_sm2.make_source(audit_sm3_to_sm2.REG_TEMP, 0),
        )
        ps_words.append(audit_sm3_to_sm2.OP_END)
        ps_bytes = audit_sm3_to_sm2.struct.pack(
            "<" + "I" * len(ps_words), *ps_words
        )

        vs_capture_hash = audit_shader_pairs.fnv1a64(vs_bytes)
        ps_capture_hash = audit_shader_pairs.fnv1a64(ps_bytes)
        fixture_pair = (vs_capture_hash, ps_capture_hash)
        (capture_dir / f"VS_3_0_{vs_capture_hash}.bin").write_bytes(vs_bytes)
        (capture_dir / f"PS_3_0_{ps_capture_hash}.bin").write_bytes(ps_bytes)

        pair_record = {
            "vertex_shader_hash": vs_capture_hash,
            "pixel_shader_hash": ps_capture_hash,
            "structural_pair_candidate": True,
            "device_limits": {
                "vs20_temporary_registers": 12,
                "max_vertex_shader_constants": 96,
            },
            "emitted": False,
        }
        emitted_pairs, vertex_outputs, pixel_outputs = emit_pair_candidates(
            [pair_record], capture_dir, emit_dir, "IVLegacyFallbacks"
        )
        assert emitted_pairs[0]["emitted"], emitted_pairs[0].get("emission_reasons")
        assert vs_capture_hash in vertex_outputs and ps_capture_hash in pixel_outputs
        vertex_output_bytes = Path(vertex_outputs[vs_capture_hash]["output_file"]).read_bytes()
        pixel_output_bytes = Path(pixel_outputs[ps_capture_hash]["output_file"]).read_bytes()
        assert audit_vs3_to_vs2.struct.unpack_from("<I", vertex_output_bytes)[0] == audit_vs3_to_vs2.VS2_VERSION
        assert audit_sm3_to_sm2.struct.unpack_from("<I", pixel_output_bytes)[0] == audit_sm3_to_sm2.PS2_VERSION

        pair_map_path = root / "IVLegacyShaderFallbacks.ini"
        approved_vs, approved_ps = validate_approved_pairs(
            emitted_pairs, {fixture_pair}
        )
        assert audit_vs3_to_vs2.write_vertex_fallback_ini(
            pair_map_path, list(vertex_outputs.values()), approved_vs
        ) == 1
        assert audit_sm3_to_sm2.write_fallback_ini(
            pair_map_path, list(pixel_outputs.values()), approved_ps
        ) == 1
        pair_map_text = pair_map_path.read_text(encoding="utf-8")
        assert "[VertexShaderFallbacks]" in pair_map_text
        assert "[ShaderFallbacks]" in pair_map_text

    print("PASS: conservative paired VS2/PS2 lowering and explicit pair approval tests")


if __name__ == "__main__":
    raise SystemExit(main())
