#!/usr/bin/env python3
"""Validate and summarize IV Legacy D3D9 float shader-constant sidecars.

Binary format v2 adds the currently bound shader-object address after the frame index.
Version-1 records without that field remain supported.

Common header:
  4s magic 'IVCF'
  H  version (1 or 2)
  H  stage (0=VS, 1=PS)
  I  Present-frame index
  [v2 only] I bound shader-object address (0 means no shader bound)
  I  capture sequence
  I  first float-constant register
  I  vector-register count
  I  data byte count
  followed by vector_count * 4 little-endian IEEE-754 float32 values.
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import sys
from pathlib import Path
from typing import Any

HEADER_V1 = struct.Struct("<4sHHIIIII")
HEADER_V2 = struct.Struct("<4sHHIIIIII")
MAGIC = b"IVCF"
VERSION = 2
STAGES = {0: "VS", 1: "PS"}
MAX_VECTOR_COUNT = 256
MAX_FILES = 8192


class ConstantCaptureError(ValueError):
    """Raised for malformed or unsupported constant sidecar records."""


def _json_float(value: float) -> float | str:
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "Infinity" if value > 0 else "-Infinity"
    return value


def parse_capture(path: Path) -> dict[str, Any]:
    data = path.read_bytes()
    if len(data) < 8:
        raise ConstantCaptureError("truncated header")

    magic, version, stage_code = struct.unpack_from("<4sHH", data, 0)
    if magic != MAGIC:
        raise ConstantCaptureError(f"bad magic {magic!r}")

    if version == 1:
        if len(data) < HEADER_V1.size:
            raise ConstantCaptureError("truncated version-1 header")
        (_magic, _version, _stage, frame, sequence, start, count, data_bytes) = (
            HEADER_V1.unpack_from(data, 0)
        )
        shader_object = None
        header_size = HEADER_V1.size
    elif version == 2:
        if len(data) < HEADER_V2.size:
            raise ConstantCaptureError("truncated version-2 header")
        (_magic, _version, _stage, frame, shader_object, sequence,
         start, count, data_bytes) = HEADER_V2.unpack_from(data, 0)
        header_size = HEADER_V2.size
        if shader_object == 0:
            shader_object = None
    else:
        raise ConstantCaptureError(f"unsupported version {version}")

    if stage_code not in STAGES:
        raise ConstantCaptureError(f"invalid shader stage {stage_code}")
    if count < 1 or count > MAX_VECTOR_COUNT:
        raise ConstantCaptureError(f"vector count outside 1..{MAX_VECTOR_COUNT}")
    if start > 255 or start + count > 256:
        raise ConstantCaptureError("constant register range exceeds c255")
    expected_data_bytes = count * 4 * 4
    if data_bytes != expected_data_bytes:
        raise ConstantCaptureError(
            f"data byte count {data_bytes} does not match expected {expected_data_bytes}"
        )
    expected_file_bytes = header_size + expected_data_bytes
    if len(data) != expected_file_bytes:
        raise ConstantCaptureError(
            f"file length {len(data)} does not match expected {expected_file_bytes}"
        )

    float_count = count * 4
    values = struct.unpack_from(f"<{float_count}f", data, header_size)
    vectors = [
        [_json_float(values[index + offset]) for offset in range(4)]
        for index in range(0, len(values), 4)
    ]
    return {
        "file": path.name,
        "version": version,
        "stage": STAGES[stage_code],
        "frame_index": frame,
        "shader_object": f"{shader_object:08X}" if shader_object is not None else None,
        "sequence": sequence,
        "start_register": start,
        "vector_count": count,
        "data_byte_count": data_bytes,
        "registers": [
            {"register": start + index, "xyzw": vector}
            for index, vector in enumerate(vectors)
        ],
    }

def analyze_directory(directory: Path) -> dict[str, Any]:
    files = sorted(directory.glob("*.bin"))
    if len(files) > MAX_FILES:
        raise ConstantCaptureError(
            f"directory contains {len(files)} files; maximum is {MAX_FILES}"
        )

    records: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in files:
        try:
            records.append(parse_capture(path))
        except (OSError, ConstantCaptureError, struct.error) as exc:
            errors.append({"file": path.name, "error": str(exc)})

    stage_counts = {
        stage: sum(1 for record in records if record["stage"] == stage)
        for stage in ("VS", "PS")
    }
    return {
        "schema_version": 1,
        "input_directory": str(directory),
        "record_count": len(records),
        "invalid_record_count": len(errors),
        "stage_counts": stage_counts,
        "frame_indices": sorted({record["frame_index"] for record in records}),
        "records": records,
        "errors": errors,
        "scope_note": (
            "These are values submitted through SetVertexShaderConstantF and "
            "SetPixelShaderConstantF after successful D3D9 calls. They are not "
            "named semantic uniforms until matched to shader disassembly and "
            "the game's material/state code."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_directory", type=Path)
    parser.add_argument("--json", type=Path, help="Optional JSON report output")
    args = parser.parse_args()

    if not args.input_directory.is_dir():
        print(
            f"ERROR: directory not found: {args.input_directory}",
            file=sys.stderr,
        )
        return 2

    try:
        report = analyze_directory(args.input_directory)
    except (OSError, ConstantCaptureError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(
            json.dumps(report, indent=2, sort_keys=True, allow_nan=False) + "\n",
            encoding="utf-8",
        )

    print(
        f"Constant records: {report['record_count']} "
        f"(invalid={report['invalid_record_count']})"
    )
    print(
        f"Stages: VS={report['stage_counts']['VS']} "
        f"PS={report['stage_counts']['PS']}"
    )
    for record in report["records"]:
        print(
            f"  {record['stage']} frame={record['frame_index']} "
            f"c{record['start_register']}..c{record['start_register'] + record['vector_count'] - 1} "
            f"({record['vector_count']} vectors)"
        )
    if args.json:
        print(f"JSON report: {args.json}")
    if report["invalid_record_count"]:
        for error in report["errors"]:
            print(f"INVALID {error['file']}: {error['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
