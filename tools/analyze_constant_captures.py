#!/usr/bin/env python3
"""Validate and inventory IVLegacy bounded shader-constant sidecar files.

File format (little-endian):
    char[4] magic = "IVCF"
    uint16 version = 1
    uint16 stage = 0 (VS) / 1 (PS)
    uint32 frame index
    uint32 sequence
    uint32 start constant register
    uint32 vector4 count
    uint32 data byte count
    float32 values[vector4_count][4]

This tool validates capture integrity and emits register/value summaries. It
does not infer constant meanings; the game's shader metadata is still needed.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

HEADER = struct.Struct("<4sHHIIIII")
STAGES = {0: "VS", 1: "PS"}
MAX_VECTOR_COUNT = 256
MAX_FILE_BYTES = HEADER.size + MAX_VECTOR_COUNT * 16


class ConstantCaptureError(ValueError):
    pass


def parse_capture(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < HEADER.size:
        raise ConstantCaptureError("file shorter than IVCF header")
    if len(data) > MAX_FILE_BYTES:
        raise ConstantCaptureError(f"file exceeds {MAX_FILE_BYTES}-byte capture bound")

    magic, version, stage_id, frame, sequence, start, count, byte_count = HEADER.unpack_from(data)
    if magic != b"IVCF":
        raise ConstantCaptureError(f"bad magic {magic!r}")
    if version != 1:
        raise ConstantCaptureError(f"unsupported capture version {version}")
    if stage_id not in STAGES:
        raise ConstantCaptureError(f"unknown stage ID {stage_id}")
    if count < 1 or count > MAX_VECTOR_COUNT:
        raise ConstantCaptureError(f"vector count outside 1..{MAX_VECTOR_COUNT}: {count}")
    if start > 255 or start + count > 256:
        raise ConstantCaptureError("constant register range exceeds c0..c255")
    expected_bytes = count * 4 * 4
    if byte_count != expected_bytes:
        raise ConstantCaptureError(
            f"declared data length {byte_count} does not match {expected_bytes}"
        )
    if len(data) != HEADER.size + byte_count:
        raise ConstantCaptureError(
            f"file size {len(data)} does not match header+payload {HEADER.size + byte_count}"
        )

    values = struct.unpack_from("<" + "f" * (count * 4), data, HEADER.size)
    if not all(math.isfinite(value) for value in values):
        raise ConstantCaptureError("constant payload contains NaN or infinity")

    vectors = [list(values[i * 4:(i + 1) * 4]) for i in range(count)]
    return {
        "file": path.name,
        "stage": STAGES[stage_id],
        "frame": frame,
        "sequence": sequence,
        "start_register": start,
        "vector_count": count,
        "byte_count": byte_count,
        "registers": [
            {"register": start + offset, "value": vector}
            for offset, vector in enumerate(vectors)
        ],
    }


def analyze_directory(directory: Path) -> dict[str, Any]:
    if not directory.is_dir():
        raise FileNotFoundError(f"capture directory not found: {directory}")
    files = sorted(directory.glob("*.bin"))
    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            records.append(parse_capture(path))
        except (OSError, ConstantCaptureError, struct.error) as exc:
            errors.append({"file": path.name, "error": str(exc)})

    records.sort(key=lambda item: (item["frame"], item["sequence"], item["stage"]))
    return {
        "schema_version": 1,
        "input_directory": str(directory),
        "file_count": len(files),
        "valid_capture_count": len(records),
        "invalid_capture_count": len(errors),
        "stage_counts": {
            stage: sum(record["stage"] == stage for record in records)
            for stage in ("VS", "PS")
        },
        "frame_counts": {
            str(frame): sum(record["frame"] == frame for record in records)
            for frame in sorted({record["frame"] for record in records})
        },
        "captures": records,
        "errors": errors,
        "scope_note": (
            "Raw D3D9 float4 constant values and register ranges only. "
            "Register names and semantic meaning require matching game shader metadata."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path)
    parser.add_argument("--json", type=Path, help="Optional JSON report path")
    args = parser.parse_args()

    try:
        report = analyze_directory(args.capture_dir)
    except OSError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if report["invalid_capture_count"]:
        for error in report["errors"]:
            print(f"ERROR: {error['file']}: {error['error']}", file=sys.stderr)
        return 1

    print(
        f"Validated {report['valid_capture_count']} constant captures; "
        f"VS={report['stage_counts']['VS']} PS={report['stage_counts']['PS']}"
    )
    for record in report["captures"]:
        first = record["registers"][0]["register"]
        last = first + record["vector_count"] - 1
        print(
            f"{record['file']}: {record['stage']} c{first}..c{last} "
            f"({record['vector_count']} float4), frame={record['frame']}"
        )

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"JSON report: {args.json}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
