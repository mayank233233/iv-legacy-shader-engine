#!/usr/bin/env python3
"""Summarize IV Legacy D3D9 logs and correlate draw calls with shader hashes.

The report is observational: it counts submissions and associations recorded by
the ASI. It does not infer GPU time, shader execution cost, triangles actually
rasterized, or frame rate.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

TOKEN_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^\s]+)")
PRIMITIVE_NAMES = {
    1: "POINTLIST",
    2: "LINELIST",
    3: "LINESTRIP",
    4: "TRIANGLELIST",
    5: "TRIANGLESTRIP",
    6: "TRIANGLEFAN",
}


def parse_fields(line: str) -> dict[str, str]:
    """Parse key=value tokens from one IVLegacy.log line."""
    return {key: value.rstrip(",;") for key, value in TOKEN_RE.findall(line)}


def normalize_pointer(value: str | None) -> str | None:
    if value is None:
        return None
    text = value.strip().lower()
    if text in {"0", "00000000", "0x0", "0x00000000", "(nil)", "null"}:
        return None
    if text.startswith("0x"):
        text = text[2:]
    return text.lstrip("0") or "0"


def int_field(fields: dict[str, str], name: str, default: int = 0) -> int:
    raw = fields.get(name)
    if raw is None:
        return default
    try:
        return int(raw, 0)
    except ValueError:
        return default


def shader_key(shader: dict[str, Any] | None, pointer: str | None) -> str:
    if shader is None:
        return "unmapped" if pointer is not None else "fixed-function/null"
    return f"{shader['stage']}:{shader['hash']}"


def analyze_log(path: Path) -> dict[str, Any]:
    shaders_by_address: dict[tuple[str, str], dict[str, Any]] = {}
    fallback_by_address: dict[tuple[str, str], dict[str, Any]] = {}
    draws: list[dict[str, Any]] = []
    present_failures = 0
    reset_failures = 0
    malformed_shader_records = 0
    malformed_draw_records = 0

    for line_number, raw_line in enumerate(
        path.read_text(encoding="utf-8", errors="replace").splitlines(), 1
    ):
        if "SHADER_OBJECT_CREATED " in raw_line:
            fields = parse_fields(raw_line)
            stage = fields.get("stage", "").upper()
            address = normalize_pointer(fields.get("object"))
            bytecode_hash = fields.get("hash", "").lower()
            profile = fields.get("profile", "unknown")
            if stage not in {"VS", "PS"} or address is None or not bytecode_hash:
                malformed_shader_records += 1
                continue
            try:
                byte_count = int(fields.get("bytes", "0"), 0)
            except ValueError:
                byte_count = 0
            shader = {
                "stage": stage,
                "object": address,
                "profile": profile.lower(),
                "bytes": byte_count,
                "hash": bytecode_hash,
                "hr": fields.get("hr", "unknown").lower(),
                "log_line": line_number,
            }
            # A later object creation at a reused address supersedes the
            # previous lifetime in this chronological log.
            shaders_by_address[(stage, address)] = shader
            continue

        if "SHADER_FALLBACK_OBJECT_MAP " in raw_line:
            fields = parse_fields(raw_line)
            address = normalize_pointer(fields.get("object"))
            source_hash = fields.get("source_hash", "").lower()
            target_hash = fields.get("target_hash", "").lower()
            if address is None or not source_hash or not target_hash:
                continue
            fallback_by_address[("PS", address)] = {
                "source_hash": source_hash,
                "target_hash": target_hash,
                "target_profile": fields.get("target_profile", "unknown").lower(),
                "log_line": line_number,
            }
            continue

        if "DRAW_CALL " in raw_line:
            fields = parse_fields(raw_line)
            try:
                sequence = int(fields["seq"], 0)
                frame = int(fields.get("frame", "0"), 0)
                primitive_type = int(fields["primitive"], 0)
                primitive_count = int(fields["primitives"], 0)
                result_hr = int(fields["hr"], 0)
            except (KeyError, ValueError):
                malformed_draw_records += 1
                continue

            vs_pointer = normalize_pointer(fields.get("bound_vs"))
            ps_pointer = normalize_pointer(fields.get("bound_ps"))
            vs = shaders_by_address.get(("VS", vs_pointer)) if vs_pointer else None
            ps = shaders_by_address.get(("PS", ps_pointer)) if ps_pointer else None
            ps_fallback = fallback_by_address.get(("PS", ps_pointer)) if ps_pointer else None
            draws.append({
                "seq": sequence,
                "frame": frame,
                "kind": fields.get("kind", "unknown"),
                "device": fields.get("device", "unknown").lower(),
                "primitive_type": primitive_type,
                "primitive_name": PRIMITIVE_NAMES.get(
                    primitive_type, f"UNKNOWN_{primitive_type}"
                ),
                "primitive_count": primitive_count,
                "start_vertex": int_field(fields, "start_vertex"),
                "base_vertex": int_field(fields, "base_vertex"),
                "min_vertex": int_field(fields, "min_vertex"),
                "num_vertices": int_field(fields, "num_vertices"),
                "start_index": int_field(fields, "start_index"),
                "bound_vs_object": vs_pointer,
                "bound_ps_object": ps_pointer,
                "vertex_shader": vs,
                "pixel_shader": ps,
                "pixel_shader_fallback": ps_fallback,
                "pixel_shader_source_hash": ps_fallback["source_hash"] if ps_fallback else None,
                "vertex_shader_key": shader_key(vs, vs_pointer),
                "pixel_shader_key": shader_key(ps, ps_pointer),
                "hr": f"0x{result_hr & 0xFFFFFFFF:08X}",
                "succeeded": (result_hr & 0x80000000) == 0,
                "log_line": line_number,
            })
            continue

        if "DEVICE_PRESENT_FAILED " in raw_line:
            present_failures += 1
        elif "DEVICE_RESET_RESULT " in raw_line:
            fields = parse_fields(raw_line)
            try:
                reset_hr = int(fields.get("hr", "0"), 0)
            except ValueError:
                reset_hr = 0
            if reset_hr & 0x80000000:
                reset_failures += 1

    shader_usage: dict[str, dict[str, Any]] = {}
    pair_usage: dict[str, dict[str, Any]] = {}
    frame_counts: Counter[int] = Counter()
    kind_counts: Counter[str] = Counter()
    primitive_counts: Counter[str] = Counter()
    failed_draws = 0
    unresolved_shader_references = 0
    fallback_usage: dict[tuple[str, str], dict[str, Any]] = {}

    for draw in draws:
        frame_counts[draw["frame"]] += 1
        kind_counts[draw["kind"]] += 1
        primitive_counts[draw["primitive_name"]] += draw["primitive_count"]
        if not draw["succeeded"]:
            failed_draws += 1

        for stage, pointer_field, shader_field, key_field in (
            ("VS", "bound_vs_object", "vertex_shader", "vertex_shader_key"),
            ("PS", "bound_ps_object", "pixel_shader", "pixel_shader_key"),
        ):
            pointer = draw[pointer_field]
            shader = draw[shader_field]
            key = draw[key_field]
            if pointer is not None and shader is None:
                unresolved_shader_references += 1
            usage = shader_usage.setdefault(key, {
                "stage": stage if key not in {
                    "unmapped", "fixed-function/null"
                } else key,
                "draw_calls": 0,
                "primitive_submissions": 0,
                "object_addresses": set(),
                "profiles": set(),
            })
            usage["draw_calls"] += 1
            usage["primitive_submissions"] += draw["primitive_count"]
            if pointer is not None:
                usage["object_addresses"].add(pointer)
            if shader is not None:
                usage["profiles"].add(shader["profile"])

        pair_key = f"VS[{draw['vertex_shader_key']}] + PS[{draw['pixel_shader_key']}]"
        pair = pair_usage.setdefault(pair_key, {
            "draw_calls": 0,
            "primitive_submissions": 0,
            "kinds": Counter(),
            "primitive_types": Counter(),
            "frames": set(),
            "vertex_shader_hash": (
                draw["vertex_shader"]["hash"] if draw["vertex_shader"] else None
            ),
            "pixel_shader_hash": (
                draw["pixel_shader"]["hash"] if draw["pixel_shader"] else None
            ),
        })
        pair["draw_calls"] += 1
        pair["primitive_submissions"] += draw["primitive_count"]
        pair["kinds"][draw["kind"]] += 1
        pair["primitive_types"][draw["primitive_name"]] += draw["primitive_count"]
        pair["frames"].add(draw["frame"])

        fallback = draw["pixel_shader_fallback"]
        if fallback:
            fallback_key = (
                fallback["source_hash"], fallback["target_hash"]
            )
            item = fallback_usage.setdefault(fallback_key, {
                "source_shader_hash": fallback["source_hash"],
                "replacement_shader_hash": fallback["target_hash"],
                "replacement_profile": fallback["target_profile"],
                "draw_calls": 0,
                "primitive_submissions": 0,
                "frames": set(),
            })
            item["draw_calls"] += 1
            item["primitive_submissions"] += draw["primitive_count"]
            item["frames"].add(draw["frame"])

    normalized_shader_usage = []
    for key, item in shader_usage.items():
        normalized_shader_usage.append({
            "shader_key": key,
            "stage": item["stage"],
            "draw_calls": item["draw_calls"],
            "primitive_submissions": item["primitive_submissions"],
            "object_addresses": sorted(item["object_addresses"]),
            "profiles": sorted(item["profiles"]),
        })
    normalized_shader_usage.sort(
        key=lambda x: (-x["draw_calls"], x["shader_key"])
    )

    normalized_pair_usage = []
    for key, item in pair_usage.items():
        normalized_pair_usage.append({
            "shader_pair": key,
            "vertex_shader_hash": item["vertex_shader_hash"],
            "pixel_shader_hash": item["pixel_shader_hash"],
            "draw_calls": item["draw_calls"],
            "primitive_submissions": item["primitive_submissions"],
            "draw_kinds": dict(sorted(item["kinds"].items())),
            "primitive_types": dict(sorted(item["primitive_types"].items())),
            "frames": sorted(item["frames"]),
        })
    normalized_pair_usage.sort(
        key=lambda x: (-x["draw_calls"], x["shader_pair"])
    )

    normalized_fallback_usage = [
        {
            **item,
            "frames": sorted(item["frames"]),
        }
        for item in fallback_usage.values()
    ]
    normalized_fallback_usage.sort(
        key=lambda x: (-x["draw_calls"], x["source_shader_hash"])
    )

    return {
        "schema_version": 1,
        "input_file": str(path),
        "shader_objects_observed": len(shaders_by_address),
        "draw_calls_observed": len(draws),
        "successful_draw_calls": len(draws) - failed_draws,
        "failed_draw_calls": failed_draws,
        "present_failures": present_failures,
        "reset_failures": reset_failures,
        "unresolved_shader_references": unresolved_shader_references,
        "malformed_shader_records": malformed_shader_records,
        "malformed_draw_records": malformed_draw_records,
        "frames_observed": len(frame_counts),
        "draw_calls_by_frame": {
            str(frame): count for frame, count in sorted(frame_counts.items())
        },
        "draw_calls_by_kind": dict(sorted(kind_counts.items())),
        "primitive_submissions_by_type": dict(sorted(primitive_counts.items())),
        "shader_usage": normalized_shader_usage,
        "shader_pair_usage": normalized_pair_usage,
        "shader_fallback_usage": normalized_fallback_usage,
        "draw_calls": draws,
        "scope_note": (
            "Counts are log-observed D3D9 submissions, not GPU time, "
            "rasterized triangles, frame pacing, or FPS. Shader-object "
            "correlation is scoped to this process log and object addresses."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", type=Path, help="IVLegacy.log from one game process")
    parser.add_argument("--json", type=Path, help="Optional path for JSON report")
    args = parser.parse_args()

    if not args.log_file.is_file():
        print(f"ERROR: log file not found: {args.log_file}", file=sys.stderr)
        return 2

    report = analyze_log(args.log_file)
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    print(
        f"Draw calls: {report['draw_calls_observed']} "
        f"(successful={report['successful_draw_calls']}, failed={report['failed_draw_calls']})"
    )
    print(
        f"Shader objects: {report['shader_objects_observed']}; "
        f"unresolved shader references: {report['unresolved_shader_references']}"
    )
    print("Top shader pairs:")
    for item in report["shader_pair_usage"][:10]:
        print(
            f"  {item['draw_calls']:6d} draws / {item['primitive_submissions']:8d} "
            f"primitive submissions — {item['shader_pair']}"
        )
    print(
        "NOTE: submissions are not GPU time, rasterized triangles or FPS."
    )
    if args.json:
        print(f"JSON report: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
