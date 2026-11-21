#!/usr/bin/env python3
"""Conservative parser for Direct3D 9 Shader Model 2/3 tokenized bytecode.

This tool inventories captured shader programs; it does not decompile, translate,
or prove that a shader can be lowered to Shader Model 2.0.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

OPCODES = {
    0: "NOP", 1: "MOV", 2: "ADD", 3: "SUB", 4: "MAD", 5: "MUL",
    6: "RCP", 7: "RSQ", 8: "DP3", 9: "DP4", 10: "MIN", 11: "MAX",
    12: "SLT", 13: "SGE", 14: "EXP", 15: "LOG", 16: "LIT", 17: "DST",
    18: "LRP", 19: "FRC", 20: "M4X4", 21: "M4X3", 22: "M3X4",
    23: "M3X3", 24: "M3X2", 25: "CALL", 26: "CALLNZ", 27: "LOOP",
    28: "RET", 29: "ENDLOOP", 30: "LABEL", 31: "DCL", 32: "POW",
    33: "CRS", 34: "SGN", 35: "ABS", 36: "NRM", 37: "SINCOS",
    38: "REP", 39: "ENDREP", 40: "IF", 41: "IFC", 42: "ELSE",
    43: "ENDIF", 44: "BREAK", 45: "BREAKC", 46: "MOVA",
    47: "DEFB", 48: "DEFI", 64: "TEXCOORD", 65: "TEXKILL",
    66: "TEX", 67: "TEXBEM", 68: "TEXBEML", 69: "TEXREG2AR",
    70: "TEXREG2GB", 71: "TEXM3X2PAD", 72: "TEXM3X2TEX",
    73: "TEXM3X3PAD", 74: "TEXM3X3TEX", 75: "RESERVED0",
    76: "TEXM3X3SPEC", 77: "TEXM3X3VSPEC", 78: "EXPP",
    79: "LOGP", 80: "CND", 81: "DEF", 82: "TEXREG2RGB",
    83: "TEXDP3TEX", 84: "TEXM3X2DEPTH", 85: "TEXDP3",
    86: "TEXM3X3", 87: "TEXDEPTH", 88: "CMP", 89: "BEM",
    90: "DP2ADD", 91: "DSX", 92: "DSY", 93: "TEXLDD",
    94: "SETP", 95: "TEXLDL", 96: "BREAKP",
}
SPECIAL = {0xFFFD: "PHASE", 0xFFFE: "COMMENT", 0xFFFF: "END"}

REGISTER_TYPES = {
    0: "TEMP", 1: "INPUT", 2: "CONST", 3: "ADDR_OR_TEXTURE",
    4: "RASTOUT", 5: "ATTROUT", 6: "TEXCRDOUT_OR_OUTPUT",
    7: "CONSTINT", 8: "COLOROUT", 9: "DEPTHOUT", 10: "SAMPLER",
    11: "CONST2", 12: "CONST3", 13: "CONST4", 14: "CONSTBOOL",
    15: "LOOP", 16: "TEMPFLOAT16", 17: "MISCTYPE",
    18: "LABEL", 19: "PREDICATE",
}
TEXTURE_SAMPLE_OPS = {66, 93, 95}
TEXTURE_RELATED_OPS = set(range(66, 78)) | {93, 95}
FLOW_CONTROL_OPS = {25, 26, 27, 28, 29, 38, 39, 40, 41, 42, 43, 44, 45, 96}
DYNAMIC_FLOW_OPS = {26, 27, 38, 40, 41, 45, 96}
SEMANTICS = {
    0: "POSITION", 1: "BLENDWEIGHT", 2: "BLENDINDICES", 3: "NORMAL",
    4: "PSIZE", 5: "TEXCOORD", 6: "TANGENT", 7: "BINORMAL",
    8: "TESSFACTOR", 9: "POSITIONT", 10: "COLOR", 11: "FOG",
    12: "DEPTH", 13: "SAMPLE",
}


class ShaderParseError(ValueError):
    """Raised when a token stream is truncated or structurally invalid."""


def decode_register(token: int) -> tuple[int, int] | None:
    """Decode a D3D9 parameter token's register type and register index."""
    # D3DSP_REGTYPE is split across bits 28..30 and 11..12.
    if (token & 0x80000000) == 0:
        return None
    reg_type = ((token & 0x70000000) >> 28) | ((token & 0x00001800) >> 8)
    if reg_type not in REGISTER_TYPES:
        return None
    return reg_type, token & 0x7FF


def make_parameter_token(reg_type: int, register: int) -> int:
    """Build a parameter token for parser self-tests."""
    return (
        0x80000000
        | (register & 0x7FF)
        | ((reg_type & 0x7) << 28)
        | ((reg_type & 0x18) << 8)
    )


def analyze_shader_bytes(data: bytes, source_name: str = "<memory>") -> dict[str, Any]:
    if len(data) < 8:
        raise ShaderParseError(f"{source_name}: bytecode is shorter than two DWORDs")
    if len(data) % 4:
        raise ShaderParseError(f"{source_name}: bytecode size is not DWORD-aligned")

    words = list(struct.unpack("<" + "I" * (len(data) // 4), data))
    version = words[0]
    marker = version & 0xFFFF0000
    if marker == 0xFFFE0000:
        stage = "VS"
    elif marker == 0xFFFF0000:
        stage = "PS"
    else:
        raise ShaderParseError(
            f"{source_name}: invalid shader version token 0x{version:08X}"
        )

    major = (version >> 8) & 0xFF
    minor = version & 0xFF
    if major not in (2, 3):
        raise ShaderParseError(
            f"{source_name}: SM{major}.{minor} is outside this analyzer's SM2/SM3 scope"
        )

    opcode_counts: Counter[str] = Counter()
    registers: dict[str, set[int]] = defaultdict(set)
    sampler_declarations: dict[int, str] = {}
    semantic_declarations: list[dict[str, Any]] = []
    texture_samples = 0
    texture_related = 0
    flow_control = 0
    dynamic_flow = 0
    comment_blocks = 0
    comment_dwords = 0
    instruction_parameter_dwords = 0
    instruction_count = 0
    phase_count = 0
    unknown_opcodes: Counter[str] = Counter()

    index = 1
    found_end = False
    end_offset_dword = -1

    while index < len(words):
        token = words[index]
        opcode = token & 0xFFFF
        instruction_offset = index
        index += 1

        if opcode == 0xFFFF:  # D3DSIO_END
            found_end = True
            end_offset_dword = instruction_offset
            break

        if opcode == 0xFFFE:  # D3DSIO_COMMENT
            comment_blocks += 1
            size = (token >> 16) & 0x7FFF
            if size > len(words) - index:
                raise ShaderParseError(
                    f"{source_name}: COMMENT at DWORD {instruction_offset} "
                    f"claims {size} DWORDs, only {len(words) - index} remain"
                )
            comment_dwords += size
            index += size
            continue

        if opcode == 0xFFFD:  # D3DSIO_PHASE
            phase_count += 1
            continue

        name = OPCODES.get(opcode)
        if name is None:
            name = f"UNKNOWN_0x{opcode:04X}"
            unknown_opcodes[name] += 1

        # For SM2/SM3 the high instruction-token length nibble is the count
        # of following DWORDs (excluding the instruction token itself).
        parameter_count = (token >> 24) & 0xF
        if parameter_count > len(words) - index:
            raise ShaderParseError(
                f"{source_name}: {name} at DWORD {instruction_offset} "
                f"claims {parameter_count} parameter DWORDs, "
                f"only {len(words) - index} remain"
            )
        operands = words[index:index + parameter_count]
        index += parameter_count
        instruction_count += 1
        instruction_parameter_dwords += parameter_count
        opcode_counts[name] += 1

        if opcode in TEXTURE_SAMPLE_OPS:
            texture_samples += 1
        if opcode in TEXTURE_RELATED_OPS:
            texture_related += 1
        if opcode in FLOW_CONTROL_OPS:
            flow_control += 1
        if opcode in DYNAMIC_FLOW_OPS:
            dynamic_flow += 1

        # DCL has a declaration-info token followed by one register token.
        # DEF/DEFB/DEFI have a destination register followed by literal data.
        if opcode == 31:
            register_operands = operands[1:2]
            if len(operands) >= 2:
                info = operands[0]
                decoded = decode_register(operands[1])
                if decoded:
                    reg_type, reg_num = decoded
                    if reg_type == 10:
                        sampler_kind = (info & 0x78000000) >> 27
                        sampler_names = {2: "2D", 3: "CUBE", 4: "VOLUME"}
                        sampler_declarations[reg_num] = sampler_names.get(
                            sampler_kind, f"UNKNOWN_{sampler_kind}"
                        )
                    else:
                        usage = info & 0xF
                        usage_index = (info >> 16) & 0xF
                        semantic_declarations.append({
                            "register_type": REGISTER_TYPES[reg_type],
                            "register": reg_num,
                            "usage": SEMANTICS.get(usage, f"UNKNOWN_{usage}"),
                            "usage_index": usage_index,
                        })
        elif opcode in (47, 48, 81):
            register_operands = operands[:1]
        else:
            register_operands = operands

        for operand in register_operands:
            decoded = decode_register(operand)
            if decoded is None:
                continue
            reg_type, reg_num = decoded
            registers[REGISTER_TYPES[reg_type]].add(reg_num)

    if not found_end:
        raise ShaderParseError(f"{source_name}: missing D3DSIO_END token")

    trailing_dwords = len(words) - index
    normalized_registers = {
        name: sorted(values)
        for name, values in sorted(registers.items())
        if values
    }
    temp_registers = registers.get("TEMP", set())
    sampler_registers = registers.get("SAMPLER", set())
    declared_sampler_indices = sorted(sampler_declarations)
    used_sampler_indices = sorted(sampler_registers)

    return {
        "source": source_name,
        "stage": stage,
        "profile": f"{stage.lower()}_{major}_{minor}",
        "bytecode_bytes": len(data),
        "bytecode_sha256": hashlib.sha256(data).hexdigest(),
        "instruction_count": instruction_count,
        "instruction_parameter_dwords": instruction_parameter_dwords,
        "opcode_counts": dict(sorted(opcode_counts.items())),
        "texture_sample_instruction_count": texture_samples,
        "texture_related_instruction_count": texture_related,
        "flow_control_instruction_count": flow_control,
        "dynamic_flow_instruction_count": dynamic_flow,
        "phase_count": phase_count,
        "comment_block_count": comment_blocks,
        "comment_payload_dwords": comment_dwords,
        "registers": normalized_registers,
        "temporary_register_count": len(temp_registers),
        "highest_temporary_register": max(temp_registers) if temp_registers else None,
        "sampler_register_count": len(sampler_registers),
        "highest_sampler_register": max(sampler_registers) if sampler_registers else None,
        "declared_samplers": [
            {"register": reg, "type": sampler_declarations[reg]}
            for reg in declared_sampler_indices
        ],
        "used_sampler_registers": used_sampler_indices,
        "semantic_declarations": semantic_declarations,
        "unknown_opcodes": dict(sorted(unknown_opcodes.items())),
        "end_token_dword_offset": end_offset_dword,
        "trailing_dwords_after_end": trailing_dwords,
    }


def analyze_directory(input_dir: Path, output_path: Path | None) -> dict[str, Any]:
    candidates = sorted(
        path for path in input_dir.iterdir()
        if path.is_file() and path.suffix.lower() in {".vso", ".pso", ".bin"}
    )
    if not candidates:
        raise FileNotFoundError(f"No .vso, .pso or .bin files found in {input_dir}")

    shaders: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for path in candidates:
        try:
            shaders.append(analyze_shader_bytes(path.read_bytes(), path.name))
        except (OSError, ShaderParseError) as exc:
            errors.append({"source": path.name, "error": str(exc)})

    profiles = Counter(shader["profile"] for shader in shaders)
    report = {
        "schema_version": 1,
        "input_directory": str(input_dir),
        "shader_file_count": len(candidates),
        "parsed_shader_count": len(shaders),
        "failed_shader_count": len(errors),
        "profile_counts": dict(sorted(profiles.items())),
        "shaders": shaders,
        "errors": errors,
        "scope_note": (
            "Token inventory only. Counts are parsed instruction/register facts, "
            "not hardware cycle estimates, proof of shader semantics, or a "
            "shader-model conversion result."
        ),
    }

    if output_path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    return report


def _self_test() -> None:
    # Pixel shader 2.0: declare two samplers, sample from s0 and s1, and
    # reference three temporary registers plus one conditional-flow opcode.
    words = [
        0xFFFF0200,
        (2 << 24) | 31,  # dcl_2d s0
        (2 << 27), make_parameter_token(10, 0),
        (2 << 24) | 31,  # dcl_cube s1
        (3 << 27), make_parameter_token(10, 1),
        (3 << 24) | 66,  # texld r0, r1, s0
        make_parameter_token(0, 0), make_parameter_token(0, 1),
        make_parameter_token(10, 0),
        (3 << 24) | 66,  # texld r2, r1, s1
        make_parameter_token(0, 2), make_parameter_token(0, 1),
        make_parameter_token(10, 1),
        (1 << 24) | 40,  # if b0
        make_parameter_token(14, 0),
        0x0000FFFF,
    ]
    data = struct.pack("<" + "I" * len(words), *words)
    result = analyze_shader_bytes(data, "self-test.ps")
    assert result["stage"] == "PS"
    assert result["profile"] == "ps_2_0"
    assert result["instruction_count"] == 5
    assert result["texture_sample_instruction_count"] == 2
    assert result["temporary_register_count"] == 3
    assert result["highest_temporary_register"] == 2
    assert result["sampler_register_count"] == 2
    assert result["declared_samplers"] == [
        {"register": 0, "type": "2D"},
        {"register": 1, "type": "CUBE"},
    ]
    assert result["dynamic_flow_instruction_count"] == 1

    bad = struct.pack("<II", 0xFFFF0200, (3 << 24) | 66)
    try:
        analyze_shader_bytes(bad, "truncated.ps")
    except ShaderParseError:
        pass
    else:
        raise AssertionError("truncated instruction must be rejected")

    print("PASS: D3D9 SM2 token parser self-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_dir", nargs="?", type=Path, default=Path("build/out"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0

    try:
        report = analyze_directory(args.input_dir, args.output)
    except (OSError, FileNotFoundError, ShaderParseError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        "Parsed {parsed}/{total} shader files; profiles: {profiles}".format(
            parsed=report["parsed_shader_count"],
            total=report["shader_file_count"],
            profiles=", ".join(
                f"{profile}={count}"
                for profile, count in report["profile_counts"].items()
            ) or "none",
        )
    )
    if args.output:
        print(f"Inventory written to: {args.output}")
    if report["failed_shader_count"]:
        for error in report["errors"]:
            print(f"ERROR: {error['source']}: {error['error']}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
