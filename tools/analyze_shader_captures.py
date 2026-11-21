#!/usr/bin/env python3
"""Inspect captured Direct3D 9 shader bytecode without external dependencies.

The report intentionally separates instruction-token counts from hardware
instruction-slot estimates. Exact scheduling/slot cost depends on the shader
profile and driver/compiler rules; this tool does not guess those costs.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import struct
import sys
from collections import Counter
from pathlib import Path
from typing import Any

MAX_DWORDS = 65_536
STAGE_MARKERS = {0xFFFE: "vs", 0xFFFF: "ps"}

# Direct3D shader-model 2/3 opcode values from the D3D9 token format.
OPCODE_NAMES = {
    0: "nop", 1: "mov", 2: "add", 3: "sub", 4: "mad", 5: "mul",
    6: "rcp", 7: "rsq", 8: "dp3", 9: "dp4", 10: "min", 11: "max",
    12: "slt", 13: "sge", 14: "exp", 15: "log", 16: "lit", 17: "dst",
    18: "lrp", 19: "frc", 20: "m4x4", 21: "m4x3", 22: "m3x4",
    23: "m3x3", 24: "m3x2", 25: "call", 26: "callnz", 27: "loop",
    28: "ret", 29: "endloop", 30: "label", 31: "dcl", 32: "pow",
    33: "crs", 34: "sgn", 35: "abs", 36: "nrm", 37: "sincos",
    38: "rep", 39: "endrep", 40: "if", 41: "ifc", 42: "else",
    43: "endif", 44: "break", 45: "breakc", 46: "mova",
    47: "defb", 48: "defi", 64: "texcoord", 65: "texkill",
    66: "tex", 67: "texbem", 68: "texbeml", 69: "texreg2ar",
    70: "texreg2gb", 71: "texm3x2pad", 72: "texm3x2tex",
    73: "texm3x3pad", 74: "texm3x3tex", 75: "texm3x3spec",
    76: "texm3x3vspec", 77: "expp", 78: "logp", 79: "cnd",
    81: "def", 82: "texreg2rgb", 83: "texdp3tex", 84: "texm3x2depth",
    85: "texdp3", 86: "texm3x3", 87: "texdepth", 88: "cmp",
    89: "bem", 90: "dp2add", 91: "dsx", 92: "dsy", 93: "texldd",
    94: "setp", 95: "texldl", 96: "breakp",
}

DECLARATION_OPCODES = {31}
DEFINITION_OPCODES = {47, 48, 81}
TEXTURE_OPCODES = {
    66, 67, 68, 69, 70, 71, 72, 73, 74, 75, 76,
    82, 83, 84, 85, 86, 87, 93, 95,
}
FLOW_CONTROL_OPCODES = {
    25, 26, 27, 28, 29, 30, 38, 39, 40, 41, 42, 43, 44, 45, 96,
}

REGISTER_TYPES = {
    0: "temp",
    1: "input",
    2: "const",
    3: "addr_or_texture",
    4: "rastout",
    5: "attout",
    6: "texcrdout_or_output",
    7: "constint",
    8: "colorout",
    9: "depthout",
    10: "sampler",
    11: "const2",
    12: "const3",
    13: "const4",
    14: "constbool",
    15: "loop",
    16: "tempfloat16",
    17: "misc",
    18: "label",
    19: "predicate",
}


class ShaderFormatError(ValueError):
    pass


def register_type(token: int) -> int:
    # D3DSP_REGTYPE_MASK plus D3DSP_REGTYPE_MASK2 (bits 11-12).
    return ((token >> 28) & 0x7) | ((token >> 8) & 0x18)


def parse_shader(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if len(raw) < 8 or len(raw) % 4:
        raise ShaderFormatError("size must be a multiple of 4 bytes and at least 8")
    dword_count = len(raw) // 4
    if dword_count > MAX_DWORDS:
        raise ShaderFormatError(f"shader exceeds {MAX_DWORDS} DWORD safety limit")

    words = struct.unpack(f"<{dword_count}I", raw)
    version = words[0]
    marker = version >> 16
    stage = STAGE_MARKERS.get(marker)
    major = (version >> 8) & 0xFF
    minor = version & 0xFF
    if stage is None:
        raise ShaderFormatError(f"invalid shader version token 0x{version:08X}")
    if major not in (2, 3):
        raise ShaderFormatError(f"unsupported shader model {major}.{minor}")
    if minor > 255:
        raise ShaderFormatError("invalid minor version")

    opcode_counts: Counter[str] = Counter()
    temp_registers: set[int] = set()
    sampler_registers: set[int] = set()
    input_registers: set[int] = set()
    output_registers: set[str] = set()
    instruction_tokens = 0
    texture_instruction_tokens = 0
    flow_control_tokens = 0
    declaration_tokens = 0
    definition_tokens = 0
    comment_tokens = 0
    cursor = 1
    found_end = False

    while cursor < dword_count:
        instruction = words[cursor]
        cursor += 1
        opcode = instruction & 0xFFFF

        if opcode == 0xFFFF:  # D3DSIO_END
            found_end = True
            break

        if opcode == 0xFFFE:  # D3DSIO_COMMENT
            comment_length = (instruction >> 16) & 0x7FFF
            if comment_length > dword_count - cursor:
                raise ShaderFormatError("comment token length exceeds file")
            comment_tokens += comment_length
            cursor += comment_length
            continue

        parameter_count = (instruction >> 24) & 0x0F
        if parameter_count > dword_count - cursor:
            raise ShaderFormatError(
                f"instruction 0x{opcode:04X} parameter length exceeds file"
            )

        name = OPCODE_NAMES.get(opcode, f"opcode_0x{opcode:04X}")
        opcode_counts[name] += 1
        if opcode in DECLARATION_OPCODES:
            declaration_tokens += 1
        elif opcode in DEFINITION_OPCODES:
            definition_tokens += 1
        else:
            instruction_tokens += 1

        if opcode in TEXTURE_OPCODES:
            texture_instruction_tokens += 1
        if opcode in FLOW_CONTROL_OPCODES:
            flow_control_tokens += 1

        for operand in words[cursor:cursor + parameter_count]:
            # Register/parameter tokens have bit 31 set. Literal DEF values
            # and usage tokens are intentionally not interpreted as registers.
            if not (operand & 0x80000000):
                continue
            rtype = register_type(operand)
            number = operand & 0x7FF
            if rtype == 0:
                temp_registers.add(number)
            elif rtype == 10:
                sampler_registers.add(number)
            elif rtype == 1:
                input_registers.add(number)
            elif rtype in (4, 5, 6, 8, 9):
                output_registers.add(f"{REGISTER_TYPES.get(rtype, str(rtype))}{number}")

        cursor += parameter_count

    if not found_end:
        raise ShaderFormatError("missing D3DSIO_END token")
    if cursor != dword_count:
        # Permit trailing zero padding only; nonzero trailing tokens indicate
        # a boundary/parser mismatch and must not silently enter an inventory.
        if any(words[cursor:]):
            raise ShaderFormatError("nonzero DWORDs found after D3DSIO_END")

    sha256 = hashlib.sha256(raw).hexdigest()
    return {
        "file": path.name,
        "sha256": sha256,
        "stage": stage,
        "profile": f"{stage}_{major}_{minor}",
        "version_token": f"0x{version:08X}",
        "byte_count": len(raw),
        "dword_count": dword_count,
        "instruction_tokens": instruction_tokens,
        "texture_instruction_tokens": texture_instruction_tokens,
        "flow_control_tokens": flow_control_tokens,
        "declaration_tokens": declaration_tokens,
        "definition_tokens": definition_tokens,
        "comment_dwords": comment_tokens,
        "temp_registers": sorted(temp_registers),
        "max_temp_register": max(temp_registers) if temp_registers else None,
        "sampler_registers": sorted(sampler_registers),
        "input_registers": sorted(input_registers),
        "output_registers": sorted(output_registers),
        "opcode_counts": dict(sorted(opcode_counts.items())),
    }


def write_json(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    columns = [
        "file", "sha256", "profile", "byte_count", "dword_count",
        "instruction_tokens", "texture_instruction_tokens",
        "flow_control_tokens", "declaration_tokens", "definition_tokens",
        "max_temp_register", "temp_registers", "sampler_registers",
        "input_registers", "output_registers",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for record in records:
            row = dict(record)
            for key in ("temp_registers", "sampler_registers",
                        "input_registers", "output_registers"):
                row[key] = ";".join(map(str, row[key]))
            writer.writerow({key: row.get(key) for key in columns})


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path, help="Directory containing captured .bin shaders")
    parser.add_argument("--output-json", type=Path, help="Write detailed JSON report")
    parser.add_argument("--output-csv", type=Path, help="Write compact CSV report")
    parser.add_argument("--expect-min-shaders", type=int, default=0)
    args = parser.parse_args()

    if args.expect_min_shaders < 0:
        parser.error("--expect-min-shaders cannot be negative")
    if not args.capture_dir.is_dir():
        print(f"ERROR: capture directory does not exist: {args.capture_dir}", file=sys.stderr)
        return 2

    files = sorted(args.capture_dir.glob("*.bin"))
    records: list[dict[str, Any]] = []
    failures: list[str] = []

    for path in files:
        try:
            records.append(parse_shader(path))
        except (OSError, ShaderFormatError, struct.error) as exc:
            failures.append(f"{path.name}: {exc}")

    if len(records) < args.expect_min_shaders:
        failures.append(
            f"expected at least {args.expect_min_shaders} valid shaders, found {len(records)}"
        )

    if failures:
        for failure in failures:
            print(f"ERROR: {failure}", file=sys.stderr)
        return 1

    if args.output_json:
        write_json(args.output_json, records)
    if args.output_csv:
        write_csv(args.output_csv, records)

    print(f"Analysed {len(records)} shader bytecode file(s).")
    print("file,profile,bytes,instruction_tokens,texture_tokens,flow_tokens,max_temp,samplers")
    for record in records:
        print(
            f"{record['file']},{record['profile']},{record['byte_count']},"
            f"{record['instruction_tokens']},{record['texture_instruction_tokens']},"
            f"{record['flow_control_tokens']},{record['max_temp_register']},"
            f"{len(record['sampler_registers'])}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
