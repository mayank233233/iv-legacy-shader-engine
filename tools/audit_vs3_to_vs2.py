#!/usr/bin/env python3
"""Conservative D3D9 vs_3_0 compatibility audit against the vs_2_0 baseline.

This tool does not rewrite or emit shader bytecode. It inventories a narrow,
straight-line subset that appears structurally compatible with vs_2_0 and
explains why other programs are rejected. Even a candidate needs interface,
driver and rendered-output validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

VS3_VERSION = 0xFFFE0300
OP_COMMENT = 0xFFFE
OP_END = 0xFFFF
OP_PHASE = 0xFFFD
OP_DCL = 31
OP_DEFB = 47
OP_DEFI = 48
OP_DEF = 81

# Direct3D 9 vs_2_0 instruction-slot costs from the Microsoft instruction table.
# Setup instructions have zero slot cost; matrix and transcendental instructions
# can consume multiple slots.
VS2_SLOT_COSTS = {
    0: 1,   # nop
    1: 1,   # mov
    2: 1,   # add
    3: 1,   # sub
    4: 1,   # mad
    5: 1,   # mul
    6: 1,   # rcp
    7: 1,   # rsq
    8: 1,   # dp3
    9: 1,   # dp4
    10: 1,  # min
    11: 1,  # max
    12: 1,  # slt
    13: 1,  # sge
    14: 1,  # exp
    15: 1,  # log
    16: 3,  # lit
    17: 1,  # dst
    18: 2,  # lrp
    19: 1,  # frc
    20: 4,  # m4x4
    21: 3,  # m4x3
    22: 4,  # m3x4
    23: 3,  # m3x3
    24: 2,  # m3x2
    25: 2,  # call
    26: 3,  # callnz bool
    27: 3,  # loop
    28: 1,  # ret
    29: 2,  # endloop
    30: 0,  # label
    31: 0,  # dcl
    32: 3,  # pow
    33: 2,  # crs
    34: 3,  # sgn
    35: 1,  # abs
    36: 3,  # nrm
    37: 8,  # sincos (vs_2_0 form)
    38: 3,  # rep
    39: 2,  # endrep
    40: 3,  # if bool
    42: 1,  # else
    43: 1,  # endif
    46: 1,  # mova
    47: 0,  # defb
    48: 0,  # defi
    78: 1,  # expp
    79: 1,  # logp
    81: 0,  # def
}
VS2_OPCODE_NAMES = {
    0: "nop", 1: "mov", 2: "add", 3: "sub", 4: "mad", 5: "mul",
    6: "rcp", 7: "rsq", 8: "dp3", 9: "dp4", 10: "min", 11: "max",
    12: "slt", 13: "sge", 14: "exp", 15: "log", 16: "lit", 17: "dst",
    18: "lrp", 19: "frc", 20: "m4x4", 21: "m4x3", 22: "m3x4",
    23: "m3x3", 24: "m3x2", 25: "call", 26: "callnz", 27: "loop",
    28: "ret", 29: "endloop", 30: "label", 31: "dcl", 32: "pow",
    33: "crs", 34: "sgn", 35: "abs", 36: "nrm", 37: "sincos",
    38: "rep", 39: "endrep", 40: "if", 41: "ifc", 42: "else",
    43: "endif", 44: "break", 45: "breakc", 46: "mova", 47: "defb",
    48: "defi", 78: "expp", 79: "logp", 81: "def",
}
# Exact parameter-token counts for the opcodes this audit knows how to inspect.
VS2_PARAMETER_COUNTS = {
    0: 0,
    1: 2, 2: 3, 3: 3, 4: 4, 5: 3, 6: 2, 7: 2, 8: 3, 9: 3,
    10: 3, 11: 3, 12: 3, 13: 3, 14: 2, 15: 2, 16: 2, 17: 3,
    18: 4, 19: 2, 20: 3, 21: 3, 22: 3, 23: 3, 24: 3,
    25: 1, 26: 2, 27: 2, 28: 0, 29: 0, 30: 1, 31: 2,
    32: 3, 33: 3, 34: 4, 35: 2, 36: 2, 37: 2,
    38: 1, 39: 0, 40: 1, 42: 0, 43: 0, 46: 2,
    47: 2, 48: 5, 78: 2, 79: 2, 81: 5,
}
# Static flow instructions exist in vs_2_0, but this first audit does not
# validate control-flow structure, subroutine graphs or expansion costs.
UNVALIDATED_STATIC_FLOW = {25, 26, 27, 28, 29, 30, 38, 39, 40, 42, 43}
# vs_3_0 sincos has a different two-operand form from the four-operand vs_2_0 form.
VERSION_SENSITIVE_OPS = {37}

# D3DSHADER_PARAM_REGISTER_TYPE values used by D3D9 vertex shaders.
REG_TEMP = 0
REG_INPUT = 1
REG_CONST = 2
REG_ADDR = 3
REG_RASTOUT = 4
REG_ATTROUT = 5
REG_OUTPUT = 6
REG_CONSTINT = 7
REG_SAMPLER = 10
REG_CONSTBOOL = 14
REG_LOOP = 15
REG_LABEL = 18
REG_PREDICATE = 19

# D3DDECLUSAGE values used by the output declarations this tool can map to
# the fixed vs_2_0 output register file.
USAGE_POSITION = 0
USAGE_PSIZE = 4
USAGE_TEXCOORD = 5
USAGE_COLOR = 10
USAGE_FOG = 11
D3DDECLUSAGE_NAMES = {
    0: "POSITION", 1: "BLENDWEIGHT", 2: "BLENDINDICES", 3: "NORMAL",
    4: "PSIZE", 5: "TEXCOORD", 6: "TANGENT", 7: "BINORMAL",
    8: "TESSFACTOR", 9: "POSITIONT", 10: "COLOR", 11: "FOG",
    12: "DEPTH", 13: "SAMPLE",
}
MATRIX_ROWS = {20: 4, 21: 3, 22: 4, 23: 3, 24: 2}
MATRIX_DEST_MASKS = {
    20: (0x7, 0xF),  # m4x4 permits .xyz or .xyzw
    21: (0x7,),      # m4x3 requires .xyz
    22: (0x7, 0xF),  # m3x4 permits .xyz or .xyzw
    23: (0x7,),      # m3x3 requires .xyz
    24: (0x3,),      # m3x2 requires .xy
}
IDENTITY_SWIZZLE = 0xE4

@dataclass(frozen=True)
class Instruction:
    offset: int
    token: int
    opcode: int
    operands: tuple[int, ...]


class AuditError(ValueError):
    """Raised when a bytecode stream is structurally malformed."""


def decode_register(token: int) -> tuple[int, int] | None:
    if (token & 0x80000000) == 0:
        return None
    register_type = ((token & 0x70000000) >> 28) | ((token & 0x00001800) >> 8)
    return register_type, token & 0x7FF


def make_parameter_token(register_type: int, register: int) -> int:
    """Build the common D3D9 register-type/index fields for self-tests."""
    return (
        0x80000000
        | (register & 0x7FF)
        | ((register_type & 0x7) << 28)
        | ((register_type & 0x18) << 8)
    )


def make_dest_token(register_type: int, register: int, mask: int = 0xF) -> int:
    return make_parameter_token(register_type, register) | ((mask & 0xF) << 16)


def make_source_token(register_type: int, register: int, swizzle: int = 0xE4) -> int:
    return make_parameter_token(register_type, register) | ((swizzle & 0xFF) << 16)


def destination_mask(token: int) -> int:
    return (token >> 16) & 0xF


def source_swizzle(token: int) -> int:
    return (token >> 16) & 0xFF


def source_modifier(token: int) -> int:
    return (token >> 24) & 0xF


def make_instruction(opcode: int, *operands: int) -> list[int]:
    token = (opcode & 0xFFFF) | ((len(operands) & 0xF) << 24)
    return [token, *operands]


def parse_vs3(data: bytes) -> tuple[list[int], list[Instruction]]:
    if len(data) < 8 or len(data) % 4:
        raise AuditError("bytecode must be DWORD-aligned and contain a version plus END")
    words = list(struct.unpack("<" + "I" * (len(data) // 4), data))
    if words[0] != VS3_VERSION:
        raise AuditError(
            f"expected vs_3_0 token 0x{VS3_VERSION:08X}, got 0x{words[0]:08X}"
        )

    instructions: list[Instruction] = []
    cursor = 1
    found_end = False
    while cursor < len(words):
        start = cursor
        token = words[cursor]
        cursor += 1
        opcode = token & 0xFFFF

        if opcode == OP_END:
            found_end = True
            break
        if opcode == OP_COMMENT:
            comment_length = (token >> 16) & 0x7FFF
            if comment_length > len(words) - cursor:
                raise AuditError(
                    f"COMMENT at DWORD {start} exceeds the remaining bytecode"
                )
            cursor += comment_length
            continue
        if opcode == OP_PHASE:
            raise AuditError("PHASE token is not valid in a vs_3_0 vertex shader")

        parameter_count = (token >> 24) & 0xF
        if parameter_count > len(words) - cursor:
            raise AuditError(
                f"instruction at DWORD {start} claims {parameter_count} operands, "
                f"but the bytecode ends early"
            )
        operands = tuple(words[cursor:cursor + parameter_count])
        cursor += parameter_count
        instructions.append(Instruction(start, token, opcode, operands))

    if not found_end:
        raise AuditError("missing D3DSIO_END token")
    if any(words[cursor:]):
        raise AuditError("non-zero DWORDs follow D3DSIO_END")
    return words, instructions


def output_mapping(usage: int, usage_index: int) -> tuple[int, int] | None:
    """Map semantics with a direct legacy VS2 output equivalent.

    Other valid semantics are assigned later to an unused oD#/oT# register,
    with an explicit pixel-shader interface-remap requirement.
    """
    if usage == USAGE_POSITION and usage_index == 0:
        return (REG_RASTOUT, 0)       # oPos
    if usage == USAGE_PSIZE and usage_index == 0:
        return (REG_RASTOUT, 2)       # oPts
    if usage == USAGE_COLOR and usage_index in (0, 1):
        return (REG_ATTROUT, usage_index)  # oD0/oD1
    return None


def output_target_semantic(register_type: int | None, register_index: int | None) -> str | None:
    if register_type is None or register_index is None:
        return None
    if (register_type, register_index) == (REG_RASTOUT, 0):
        return "POSITION0"
    if (register_type, register_index) == (REG_RASTOUT, 2):
        return "PSIZE0"
    if register_type == REG_ATTROUT:
        return f"COLOR{register_index}"
    if register_type == REG_OUTPUT:
        return f"TEXCOORD{register_index}"
    return None


def _register_operands(ins: Instruction) -> tuple[int, ...]:
    if ins.opcode == OP_DCL:
        return ins.operands[1:2]
    if ins.opcode in (OP_DEF, OP_DEFB, OP_DEFI):
        return ins.operands[:1]
    if ins.opcode in UNVALIDATED_STATIC_FLOW or ins.opcode in (41, 44, 45, 94, 95, 96):
        return ()
    if ins.opcode == 0:
        return ()
    return ins.operands


def audit_vs3_bytes(
    data: bytes,
    *,
    max_instruction_slots: int = 256,
    max_temps: int = 12,
    max_float_constants: int = 256,
) -> dict[str, Any]:
    if max_instruction_slots < 1 or max_temps < 1 or max_float_constants < 1:
        raise ValueError("configured vs_2_0 limits must be positive")

    try:
        _, instructions = parse_vs3(data)
    except AuditError as exc:
        return {
            "status": "parse_error",
            "structural_candidate_for_manual_lowering": False,
            "reasons": [str(exc)],
        }

    reasons: list[str] = []
    opcode_counts: Counter[str] = Counter()
    instruction_slots = 0
    input_declarations: dict[int, dict[str, int]] = {}
    output_declarations: dict[int, list[dict[str, Any]]] = {}
    output_semantics: set[tuple[int, int]] = set()
    written_outputs: dict[tuple[int, int], int] = {}
    input_semantics: dict[tuple[int, int], int] = {}
    registers: dict[str, set[int]] = {
        "temp": set(), "input": set(), "float_constant": set(),
        "integer_constant": set(), "boolean_constant": set(),
        "sampler": set(), "output": set(),
    }

    # DCL/setup instructions must precede executable instructions. The parser
    # has already discarded COMMENT payloads, so this is a direct code-order check.
    seen_executable = False
    for ins in instructions:
        if ins.opcode == OP_DCL:
            if seen_executable:
                reasons.append(
                    f"DCL at DWORD {ins.offset} appears after the first executable instruction"
                )
        elif ins.opcode not in (OP_DEF, OP_DEFB, OP_DEFI):
            seen_executable = True

    # Pass one: gather and validate declarations before validating use sites.
    for ins in instructions:
        if ins.opcode != OP_DCL:
            continue
        if len(ins.operands) != 2:
            reasons.append(f"DCL at DWORD {ins.offset} has an invalid operand count")
            continue

        declaration, destination = ins.operands
        decoded = decode_register(destination)
        if decoded is None:
            reasons.append(f"DCL at DWORD {ins.offset} has an invalid destination token")
            continue
        register_type, register_number = decoded
        usage = declaration & 0xF
        usage_index = (declaration >> 16) & 0xF
        declared_mask = destination_mask(destination)

        if destination & 0xC000:
            reasons.append(f"DCL at DWORD {ins.offset} sets reserved destination-token bits")
        if destination & (1 << 13):
            reasons.append(f"DCL at DWORD {ins.offset} uses relative addressing on a destination")
        if destination & (0xF << 20):
            reasons.append(f"DCL at DWORD {ins.offset} sets a destination modifier")
        if destination & (0xF << 24):
            reasons.append(f"DCL at DWORD {ins.offset} sets destination scaling")
        if register_type == REG_SAMPLER:
            sampler_type = (declaration & 0x78000000) >> 27
            if declaration & ~0xF8000000:
                reasons.append(
                    f"sampler DCL at DWORD {ins.offset} sets unsupported declaration bits"
                )
            if sampler_type not in (2, 3, 4):
                reasons.append(
                    f"vertex sampler s{register_number} has unsupported texture type {sampler_type}"
                )
            if register_number >= 4:
                reasons.append(
                    f"vertex sampler s{register_number} exceeds the vs_3_0 s0-s3 range"
                )
            reasons.append(
                f"vertex sampler s{register_number} is not supported by the vs_2_0 path"
            )
            registers["sampler"].add(register_number)
            continue

        if declared_mask == 0:
            reasons.append(f"DCL at DWORD {ins.offset} declares an empty component mask")
        if declaration & ~0x800F000F:
            reasons.append(
                f"DCL at DWORD {ins.offset} sets unsupported usage-token bits"
            )
        if not (declaration & 0x80000000):
            reasons.append(
                f"DCL at DWORD {ins.offset} is missing the declaration-token marker bit"
            )
        if usage not in D3DDECLUSAGE_NAMES:
            reasons.append(
                f"DCL at DWORD {ins.offset} has unknown semantic usage {usage}"
            )

        if register_type == REG_INPUT:
            if register_number >= 16:
                reasons.append(
                    f"input v{register_number} exceeds the vs_2_0 v0-v15 limit"
                )
            if register_number in input_declarations:
                reasons.append(f"input v{register_number} is declared more than once")
            semantic_key = (usage, usage_index)
            if semantic_key in input_semantics:
                reasons.append(
                    f"input semantic {D3DDECLUSAGE_NAMES.get(usage, usage)}{usage_index} "
                    f"is declared by both v{input_semantics[semantic_key]} and v{register_number}"
                )
            input_semantics[semantic_key] = register_number
            input_declarations[register_number] = {
                "usage": usage,
                "usage_name": D3DDECLUSAGE_NAMES.get(usage, f"UNKNOWN_{usage}"),
                "usage_index": usage_index,
                "component_mask": declared_mask,
            }
        elif register_type == REG_OUTPUT:
            if register_number >= 12:
                reasons.append(
                    f"output o{register_number} exceeds the vs_3_0 o0-o11 declaration range"
                )
            semantic_key = (usage, usage_index)
            if semantic_key in output_semantics:
                reasons.append(
                    f"output semantic {D3DDECLUSAGE_NAMES.get(usage, usage)}{usage_index} "
                    "is declared more than once"
                )
            output_semantics.add(semantic_key)

            if usage == USAGE_POSITION and usage_index == 0 and declared_mask != 0xF:
                reasons.append(
                    f"POSITION0 output o{register_number} must declare all four components"
                )
            if usage == USAGE_PSIZE and usage_index == 0 and declared_mask != 0xF:
                reasons.append(
                    f"PSIZE0 output o{register_number} must use the full xyzw declaration mask"
                )
            if usage == 9:  # D3DDECLUSAGE_POSITIONT
                reasons.append(
                    f"POSITIONT{usage_index} output requires the pre-transformed vertex path"
                )
            if usage == USAGE_PSIZE and usage_index != 0:
                reasons.append(
                    f"PSIZE{usage_index} is not a supported point-size output semantic"
                )

            semantic = {
                "usage": usage,
                "usage_name": D3DDECLUSAGE_NAMES.get(usage, f"UNKNOWN_{usage}"),
                "usage_index": usage_index,
                "component_mask": declared_mask,
            }
            entries = output_declarations.setdefault(register_number, [])
            existing_mask = 0
            for existing in entries:
                existing_mask |= existing["component_mask"]
            if existing_mask & declared_mask:
                reasons.append(
                    f"output o{register_number} has overlapping DCL component masks"
                )
            entries.append(semantic)
        else:
            reasons.append(
                f"DCL at DWORD {ins.offset} targets register type {register_type}, "
                "which this initial vs_2_0 audit does not map"
            )

    # Reserve special outputs and direct COLOR0/1 bindings first.
    # TEXCOORD semantics are assigned to consecutive VS2 oT# registers below;
    # this preserves their indices when already dense and compacts sparse sets
    # when the pixel shader can be updated to the reported link semantic.
    allocated_targets: set[tuple[int, int]] = set()
    for source_register, entries in sorted(output_declarations.items()):
        for entry in entries:
            target = output_mapping(entry["usage"], entry["usage_index"])
            if target is None:
                continue
            if target in allocated_targets:
                reasons.append(
                    f"multiple output semantics map to the same VS2 register "
                    f"type={target[0]} index={target[1]}"
                )
                continue
            allocated_targets.add(target)
            entry["target_register_type"] = target[0]
            entry["target_register_index"] = target[1]
            entry["requires_pixel_shader_interface_remap"] = False

    # Compact TEXCOORD0..N into oT0..N. If an original semantic index changes,
    # the paired pixel-shader DCL must be rewritten to the effective semantic.
    texcoord_entries = sorted(
        (
            (entry["usage_index"], source_register, entry)
            for source_register, entries in output_declarations.items()
            for entry in entries
            if entry["usage"] == USAGE_TEXCOORD
        ),
        key=lambda item: (item[0], item[1]),
    )
    next_texcoord_output = 0
    legal_texcoord_masks = {0x1, 0x3, 0x7, 0xF}
    for semantic_index, source_register, entry in texcoord_entries:
        component_mask = entry["component_mask"]
        if component_mask not in legal_texcoord_masks:
            # A VS2 texture output cannot preserve a sparse component mask.
            # Use a color output instead and ask the paired PS to relink it.
            target = next(
                (
                    candidate for candidate in ((REG_ATTROUT, 0), (REG_ATTROUT, 1))
                    if candidate not in allocated_targets
                ),
                None,
            )
            if target is None:
                reasons.append(
                    f"TEXCOORD{semantic_index} has a non-contiguous component mask "
                    "and no free VS2 color output for a safe remap"
                )
                continue
        elif next_texcoord_output < 8:
            target = (REG_OUTPUT, next_texcoord_output)
            next_texcoord_output += 1
        else:
            target = next(
                (
                    candidate for candidate in ((REG_ATTROUT, 0), (REG_ATTROUT, 1))
                    if candidate not in allocated_targets
                ),
                None,
            )
        if target is None:
            reasons.append(
                f"TEXCOORD{semantic_index} has no free VS2 interpolation output register"
            )
            continue
        if target in allocated_targets:
            reasons.append(
                f"TEXCOORD{semantic_index} collides with an already allocated VS2 output"
            )
            continue
        allocated_targets.add(target)
        entry["target_register_type"] = target[0]
        entry["target_register_index"] = target[1]
        entry["requires_pixel_shader_interface_remap"] = (
            target != (REG_OUTPUT, semantic_index)
        )

    # Assign remaining generic semantics to free VS2 color outputs first, then
    # consecutive texture outputs. Every remap is surfaced for paired PS work.
    generic_targets = (
        [(REG_ATTROUT, 0), (REG_ATTROUT, 1)]
        + [(REG_OUTPUT, index) for index in range(8)]
    )
    for source_register, entries in sorted(output_declarations.items()):
        for entry in entries:
            if "target_register_type" in entry:
                continue
            component_mask = entry["component_mask"]
            if component_mask not in legal_texcoord_masks:
                target = next(
                    (
                        candidate for candidate in ((REG_ATTROUT, 0), (REG_ATTROUT, 1))
                        if candidate not in allocated_targets
                    ),
                    None,
                )
            else:
                target = next(
                    (candidate for candidate in generic_targets if candidate not in allocated_targets),
                    None,
                )
            if target is None:
                if component_mask not in legal_texcoord_masks:
                    reasons.append(
                        f"{entry['usage_name']}{entry['usage_index']} has a non-contiguous "
                        "component mask and no free VS2 color output for a safe remap"
                    )
                else:
                    reasons.append(
                        "more than ten generic vertex output semantics require VS2 interpolation registers"
                    )
                continue
            allocated_targets.add(target)
            entry["target_register_type"] = target[0]
            entry["target_register_index"] = target[1]
            entry["requires_pixel_shader_interface_remap"] = True

    declared_outputs = output_declarations

    # Pass two: prove the straight-line instruction subset, register file and
    # output interface fit the baseline vs_2_0 model.
    for ins in instructions:
        opcode = ins.opcode
        name = VS2_OPCODE_NAMES.get(opcode, f"opcode_{opcode}")
        opcode_counts[name] += 1

        if opcode not in VS2_SLOT_COSTS:
            reasons.append(
                f"{name} at DWORD {ins.offset} is not in the vs_2_0 instruction set"
            )
            continue

        instruction_slots += VS2_SLOT_COSTS[opcode]
        expected = VS2_PARAMETER_COUNTS.get(opcode)
        if expected is None or len(ins.operands) != expected:
            reasons.append(
                f"{name} at DWORD {ins.offset} has {len(ins.operands)} operands; "
                f"expected {expected}"
            )
            continue

        if ins.token & 0xE0000000:
            reasons.append(
                f"{name} at DWORD {ins.offset} sets reserved instruction-token bits"
            )
        if ins.token & (1 << 28):
            reasons.append(
                f"{name} at DWORD {ins.offset} uses instruction predication, "
                "which is not part of baseline vs_2_0"
            )
        controls = (ins.token >> 16) & 0xFF
        if controls:
            reasons.append(
                f"{name} at DWORD {ins.offset} uses unvalidated control bits 0x{controls:02X}"
            )

        # DCL was fully handled in the declaration pass above. In particular,
        # declaring oPos must not be mistaken for writing oPos.
        if opcode == OP_DCL:
            continue

        if opcode in UNVALIDATED_STATIC_FLOW:
            reasons.append(
                f"{name} at DWORD {ins.offset} uses static flow control; "
                "subroutine/flow structure is outside this first audit subset"
            )
            continue
        if opcode in VERSION_SENSITIVE_OPS:
            reasons.append(
                "sincos at DWORD "
                f"{ins.offset} uses the vs_3_0 two-operand form; vs_2_0 requires "
                "a different four-operand form"
            )
            continue

        # Matrix instructions have a specific constant-file matrix operand and
        # fixed destination masks. The matrix source cannot be modified/swizzled.
        if opcode == 46:
            # VS2.0 exposes a scalar address register; arbitrary component
            # write masks are documented only for vs_2_x and later.
            if destination_mask(ins.operands[0]) != 0x1:
                reasons.append(
                    f"MOVA at DWORD {ins.offset} must use the baseline vs_2_0 a0.x mask"
                )

        if opcode in MATRIX_ROWS:
            expected_masks = MATRIX_DEST_MASKS[opcode]
            actual_mask = destination_mask(ins.operands[0])
            if actual_mask not in expected_masks:
                expected_text = " or ".join(f"0x{mask:X}" for mask in expected_masks)
                reasons.append(
                    f"{name} at DWORD {ins.offset} requires destination mask "
                    f"{expected_text}, got 0x{actual_mask:X}"
                )
            matrix_token = ins.operands[2]
            matrix_register = decode_register(matrix_token)
            if matrix_register is None or matrix_register[0] != REG_CONST:
                reasons.append(
                    f"{name} at DWORD {ins.offset} requires a float-constant matrix source"
                )
            else:
                first_constant = matrix_register[1]
                if first_constant + MATRIX_ROWS[opcode] > max_float_constants:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} reads past configured "
                        "vs_2_0 float-constant range"
                    )
            if source_swizzle(matrix_token) != IDENTITY_SWIZZLE or source_modifier(matrix_token) != 0:
                reasons.append(
                    f"{name} at DWORD {ins.offset} requires an unmodified, identity-swizzled matrix source"
                )

        # EXP/LOG/POW forms require explicit scalar replication on their inputs.
        scalar_source_indices = {
            6: (1,), 7: (1,), 14: (1,), 15: (1,),
            32: (1, 2), 78: (1,), 79: (1,)
        }.get(opcode, ())
        for source_index in scalar_source_indices:
            if source_swizzle(ins.operands[source_index]) not in (
                0x00, 0x55, 0xAA, 0xFF
            ):
                reasons.append(
                    f"{name} at DWORD {ins.offset} requires a scalar-replicate source swizzle"
                )

        if opcode in (6, 7, 14, 15, 32, 78, 79):
            mask = destination_mask(ins.operands[0])
            if mask == 0 or (mask & (mask - 1)) != 0:
                reasons.append(
                    f"{name} at DWORD {ins.offset} requires a single-component destination mask"
                )

        if opcode == 33:
            destination = decode_register(ins.operands[0])
            source0 = decode_register(ins.operands[1])
            source1 = decode_register(ins.operands[2])
            if destination is None or destination[0] != REG_TEMP:
                reasons.append(
                    f"CRS at DWORD {ins.offset} requires a temporary destination register"
                )
            if destination is not None and source0 == destination:
                reasons.append(
                    f"CRS at DWORD {ins.offset} destination aliases src0"
                )
            if destination is not None and source1 == destination:
                reasons.append(
                    f"CRS at DWORD {ins.offset} destination aliases src1"
                )
            if source_swizzle(ins.operands[1]) != IDENTITY_SWIZZLE:
                reasons.append(
                    f"CRS at DWORD {ins.offset} requires the default src0 swizzle"
                )
            if source_swizzle(ins.operands[2]) != IDENTITY_SWIZZLE:
                reasons.append(
                    f"CRS at DWORD {ins.offset} requires the default src1 swizzle"
                )
            crs_masks = {0x1, 0x2, 0x4, 0x3, 0x5, 0x6, 0x7}
            if destination_mask(ins.operands[0]) not in crs_masks:
                reasons.append(
                    f"CRS at DWORD {ins.offset} has an unsupported destination mask"
                )

        if opcode == 36:
            destination = decode_register(ins.operands[0])
            source = decode_register(ins.operands[1])
            if destination is None or destination[0] != REG_TEMP:
                reasons.append(
                    f"NRM at DWORD {ins.offset} requires a temporary destination register"
                )
            if destination is not None and source == destination:
                reasons.append(
                    f"NRM at DWORD {ins.offset} destination and source must not be the same register"
                )

        if opcode == 34:
            scratch_registers = []
            for temp_operand in ins.operands[2:4]:
                decoded_temp = decode_register(temp_operand)
                if decoded_temp is None or decoded_temp[0] != REG_TEMP:
                    reasons.append(
                        f"SGN at DWORD {ins.offset} requires its final two operands to be temporary registers"
                    )
                else:
                    scratch_registers.append(decoded_temp)
            if len(scratch_registers) == 2 and scratch_registers[0] == scratch_registers[1]:
                reasons.append(
                    f"SGN at DWORD {ins.offset} requires two different temporary scratch registers"
                )

        # DEF-family payload DWORDs are literal values, not register tokens.
        for operand_index, operand in enumerate(_register_operands(ins)):
            decoded = decode_register(operand)
            if decoded is None:
                reasons.append(
                    f"{name} at DWORD {ins.offset} has an invalid parameter token "
                    f"at operand {operand_index}"
                )
                continue
            register_type, register_number = decoded

            if operand & (1 << 13):
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses relative register addressing; "
                    "this initial audit does not lower relative operands"
                )

            # Operand zero is the destination for ordinary arithmetic instructions.
            is_destination = (
                operand_index == 0
                and opcode not in (25, 26, 27, 28, 29, 30, 38, 39, 40, 42, 43)
            )

            if operand & 0xC000:
                reasons.append(
                    f"{name} at DWORD {ins.offset} sets reserved parameter-token bits"
                )
            if is_destination and opcode not in (OP_DEF, OP_DEFB, OP_DEFI):
                if destination_mask(operand) == 0:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} has an empty destination write mask"
                    )
                destination_modifier = (operand >> 20) & 0xF
                destination_shift = (operand >> 24) & 0xF
                if destination_modifier:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} uses destination modifier "
                        f"{destination_modifier}; _sat is not supported by baseline vs_2_0"
                    )
                if destination_shift:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} uses destination scaling, "
                        "which this baseline vs_2_0 audit does not support"
                    )
            elif not is_destination:
                modifier = source_modifier(operand)
                if modifier not in (0, 1):
                    reasons.append(
                        f"{name} at DWORD {ins.offset} uses unvalidated source modifier {modifier}; "
                        "only no modifier and negate are allowed in this audit"
                    )

            if is_destination:
                if opcode == OP_DEF and register_type != REG_CONST:
                    reasons.append(f"DEF at DWORD {ins.offset} must target a float constant register")
                elif opcode == OP_DEFB and register_type != REG_CONSTBOOL:
                    reasons.append(f"DEFB at DWORD {ins.offset} must target a boolean constant register")
                elif opcode == OP_DEFI and register_type != REG_CONSTINT:
                    reasons.append(f"DEFI at DWORD {ins.offset} must target an integer constant register")
                elif opcode == 46 and register_type != REG_ADDR:
                    reasons.append(f"MOVA at DWORD {ins.offset} must target address register a0")
                elif opcode != 46 and register_type == REG_ADDR:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} may not write address register a0; "
                        "baseline vs_2_0 requires MOVA"
                    )
                elif opcode not in (OP_DEF, OP_DEFB, OP_DEFI) and register_type in (
                    REG_INPUT, REG_CONST, REG_CONSTINT, REG_CONSTBOOL,
                    REG_LOOP, REG_SAMPLER, REG_LABEL, REG_PREDICATE,
                ):
                    reasons.append(
                        f"{name} at DWORD {ins.offset} writes read-only or unsupported "
                        f"register type {register_type}"
                    )

            if register_type == REG_TEMP:
                registers["temp"].add(register_number)
                if register_number >= max_temps:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} uses r{register_number}; "
                        f"configured vs_2_0 limit is r0-r{max_temps - 1}"
                    )
            elif register_type == REG_INPUT:
                registers["input"].add(register_number)
                if register_number >= 16:
                    reasons.append(f"{name} at DWORD {ins.offset} uses v{register_number}; vs_2_0 has v0-v15")
                if register_number not in input_declarations:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} uses undeclared input v{register_number}"
                    )
            elif register_type == REG_CONST:
                registers["float_constant"].add(register_number)
                if register_number >= max_float_constants:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} reads c{register_number}; "
                        f"configured vs_2_0 float-constant limit is c0-c{max_float_constants - 1}"
                    )
            elif register_type == REG_ADDR:
                if register_number != 0:
                    reasons.append(f"{name} at DWORD {ins.offset} uses unsupported address register a{register_number}")
                if not is_destination:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} reads a0 directly; the address register "
                        "is only used for relative constant addressing"
                    )
                # Destination legality is checked above: baseline vs_2_0
                # requires MOVA for writes to a0.
            elif register_type in (REG_RASTOUT, REG_ATTROUT):
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses a legacy fixed-output register type "
                    "that is not part of the vs_3_0 output register file"
                )
            elif register_type == REG_OUTPUT:
                registers["output"].add(register_number)
                entries = declared_outputs.get(register_number)
                if not entries:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} uses output o{register_number} "
                        "without a semantic declaration"
                    )
                elif not is_destination:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} reads a write-only vertex output"
                    )
                else:
                    write_mask = destination_mask(operand)
                    declared_mask = 0
                    for entry in entries:
                        declared_mask |= entry["component_mask"]
                    if write_mask & ~declared_mask:
                        reasons.append(
                            f"{name} at DWORD {ins.offset} writes components outside "
                            f"the declared masks for output o{register_number}"
                        )
                    for entry in entries:
                        part_mask = write_mask & entry["component_mask"]
                        if not part_mask or "target_register_type" not in entry:
                            continue
                        mapped_target = (
                            entry["target_register_type"],
                            entry["target_register_index"],
                        )
                        written_outputs[mapped_target] = (
                            written_outputs.get(mapped_target, 0) | part_mask
                        )
            elif register_type == REG_CONSTINT:
                registers["integer_constant"].add(register_number)
                if register_number > 15:
                    reasons.append(f"{name} at DWORD {ins.offset} reads i{register_number}; vs_2_0 has i0-i15")
                if not is_destination:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} reads i{register_number}; "
                        "integer constants are outside this no-flow-control subset"
                    )
            elif register_type == REG_CONSTBOOL:
                registers["boolean_constant"].add(register_number)
                if register_number > 15:
                    reasons.append(f"{name} at DWORD {ins.offset} reads b{register_number}; vs_2_0 has b0-b15")
                if not is_destination:
                    reasons.append(
                        f"{name} at DWORD {ins.offset} reads b{register_number}; "
                        "boolean constants are outside this no-flow-control subset"
                    )
            elif register_type == REG_LOOP:
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses aL; loop counter semantics "
                    "require the unimplemented flow-control audit"
                )
            elif register_type == REG_SAMPLER:
                registers["sampler"].add(register_number)
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses sampler s{register_number}; "
                    "vertex texture sampling is a vs_3_0 feature"
                )
            elif register_type == REG_LABEL:
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses a subroutine label; "
                    "call-graph lowering is not implemented"
                )
            elif register_type == REG_PREDICATE:
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses predicate register p{register_number}; "
                    "predication is not part of baseline vs_2_0"
                )
            else:
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses unsupported register type "
                    f"{register_type} (register {register_number})"
                )

    if instruction_slots > max_instruction_slots:
        reasons.append(
            f"instruction-slot count {instruction_slots} exceeds configured "
            f"vs_2_0 limit {max_instruction_slots}"
        )

    position_output = (REG_RASTOUT, 0)
    position_mask = written_outputs.get(position_output, 0)
    if position_mask != 0xF:
        reasons.append(
            "shader must write all four position components xyzw; "
            f"the mapped oPos write mask is 0x{position_mask:X}"
        )

    for source_register, declarations in output_declarations.items():
        for declaration in declarations:
            target = (
                declaration.get("target_register_type"),
                declaration.get("target_register_index"),
            )
            if target[0] is None:
                continue
            written_mask = written_outputs.get(target, 0)
            missing_mask = declaration["component_mask"] & ~written_mask
            if missing_mask:
                reasons.append(
                    f"declared output semantic {declaration['usage_name']}"
                    f"{declaration['usage_index']} on o{source_register} "
                    f"has unwritten components (mask 0x{missing_mask:X})"
                )

    # VS2 point size is a scalar register but its assembler write mask must
    # remain implicit/full (.xyzw); only x is consumed by the rasterizer.
    point_size_output = (REG_RASTOUT, 2)
    if point_size_output in written_outputs and written_outputs[point_size_output] != 0xF:
        reasons.append(
            "mapped point-size output must use the full xyzw write mask"
        )

    # The combined write mask for each oT# must be .x, .xy, .xyz or .xyzw;
    # if a higher texture-coordinate register is written, all lower ones must be.
    written_texcoord_indices = sorted(
        index for (register_type, index), mask in written_outputs.items()
        if register_type == REG_OUTPUT and mask
    )
    for index in written_texcoord_indices:
        mask = written_outputs[(REG_OUTPUT, index)]
        if mask not in (0x1, 0x3, 0x7, 0xF):
            reasons.append(
                f"mapped oT{index} has unsupported combined write mask 0x{mask:X}"
            )
        for lower_index in range(index):
            if (REG_OUTPUT, lower_index) not in written_outputs:
                reasons.append(
                    f"mapped oT{index} is written without the required lower output oT{lower_index}"
                )

    reasons = list(dict.fromkeys(reasons))
    candidate = not reasons
    output_map_report = {
        f"o{source}": [
            {
                "semantic": {
                    "usage": declaration["usage"],
                    "usage_name": declaration["usage_name"],
                    "usage_index": declaration["usage_index"],
                },
                "declared_component_mask": declaration["component_mask"],
                "vs_2_0_register_type": declaration.get("target_register_type"),
                "vs_2_0_register_index": declaration.get("target_register_index"),
                "vs_2_0_link_semantic": output_target_semantic(
                    declaration.get("target_register_type"),
                    declaration.get("target_register_index"),
                ),
                "requires_pixel_shader_interface_remap": declaration.get(
                    "requires_pixel_shader_interface_remap", False
                ),
            }
            for declaration in declarations
        ]
        for source, declarations in sorted(output_declarations.items())
    }
    return {
        "status": (
            "structural_candidate_for_manual_lowering"
            if candidate else "rejected"
        ),
        "structural_candidate_for_manual_lowering": candidate,
        "profile": "vs_3_0",
        "target_profile": "vs_2_0",
        "instruction_count": len(instructions),
        "instruction_slots": instruction_slots,
        "instruction_slot_limit": max_instruction_slots,
        "highest_temporary_register": max(registers["temp"], default=None),
        "highest_input_register": max(registers["input"], default=None),
        "highest_float_constant_register": max(registers["float_constant"], default=None),
        "registers": {
            key: sorted(values) for key, values in registers.items() if values
        },
        "opcode_counts": dict(sorted(opcode_counts.items())),
        "input_declarations": {
            str(number): declaration
            for number, declaration in sorted(input_declarations.items())
        },
        "output_mapping_plan": output_map_report,
        "output_component_split_required": any(
            len(declarations) > 1 for declarations in output_declarations.values()
        ),
        "requires_pixel_shader_interface_remap": any(
            declaration.get("requires_pixel_shader_interface_remap", False)
            for declarations in output_declarations.values()
            for declaration in declarations
        ),
        "written_outputs": [
            {
                "register_type": register_type,
                "register_index": register_index,
                "component_mask": mask,
            }
            for (register_type, register_index), mask in sorted(written_outputs.items())
        ],
        "reasons": reasons,
        "output_bytecode": None,
        "scope_note": (
            "This is a conservative structural audit only. It emits no vs_2_0 bytecode, "
            "does not validate vertex-declaration linkage, constants, downstream pixel "
            "shader interfaces, GMA driver acceptance, or rendered equivalence. Static "
            "flow control and version-sensitive sincos are deliberately rejected."
        ),
    }


def inspect_file(path: Path, **limits: int) -> dict[str, Any]:
    data = path.read_bytes()
    base = {
        "file": str(path),
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }
    if len(data) < 4:
        return {
            **base,
            "status": "parse_error",
            "structural_candidate_for_manual_lowering": False,
            "reasons": ["file is shorter than a version DWORD"],
        }
    version = struct.unpack_from("<I", data)[0]
    if version != VS3_VERSION:
        return {
            **base,
            "status": "skipped_non_vs3",
            "profile_token": f"0x{version:08X}",
            "structural_candidate_for_manual_lowering": False,
            "reasons": ["input is not a vs_3_0 vertex shader"],
        }
    return {**base, **audit_vs3_bytes(data, **limits)}


def _self_test() -> None:
    def shader(*instruction_words: int) -> bytes:
        words = [VS3_VERSION, *instruction_words, OP_END]
        return struct.pack("<" + "I" * len(words), *words)

    def dcl(usage: int, register_type: int, register: int, usage_index: int = 0) -> list[int]:
        declaration = 0x80000000 | (usage & 0xF) | ((usage_index & 0xF) << 16)
        return make_instruction(OP_DCL, declaration, make_dest_token(register_type, register))

    basic_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    basic = audit_vs3_bytes(shader(*basic_words))
    assert basic["structural_candidate_for_manual_lowering"] is True
    assert basic["instruction_slots"] == 1
    assert basic["output_mapping_plan"]["o0"][0]["vs_2_0_register_type"] == REG_RASTOUT
    assert basic["output_mapping_plan"]["o0"][0]["vs_2_0_register_index"] == 0

    temp12_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_TEMP, 12)),
    ]
    temp12 = audit_vs3_bytes(shader(*temp12_words))
    assert temp12["structural_candidate_for_manual_lowering"] is False
    assert any("r12" in reason for reason in temp12["reasons"])

    sampler_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            OP_DCL,
            0x80000000 | (2 << 27),  # D3DSTT_2D
            make_dest_token(REG_SAMPLER, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    sampler = audit_vs3_bytes(shader(*sampler_words))
    assert any("vertex sampler s0 is not supported" in reason for reason in sampler["reasons"])
    assert not any("unknown texture type" in reason for reason in sampler["reasons"])

    declaration_only = audit_vs3_bytes(shader(
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
    ))
    assert declaration_only["structural_candidate_for_manual_lowering"] is False
    assert any("write all four position components" in reason for reason in declaration_only["reasons"])

    late_dcl_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *dcl(USAGE_TEXCOORD, REG_INPUT, 1, usage_index=0),
    ]
    late_dcl = audit_vs3_bytes(shader(*late_dcl_words))
    assert any("DCL at DWORD" in reason and "after the first executable" in reason for reason in late_dcl["reasons"])

    output12 = audit_vs3_bytes(shader(
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 12),
        *make_instruction(1, make_parameter_token(REG_OUTPUT, 12), make_parameter_token(REG_INPUT, 0)),
    ))
    assert any("o12 exceeds" in reason for reason in output12["reasons"])

    sincos_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(37, make_dest_token(REG_TEMP, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    sincos = audit_vs3_bytes(shader(*sincos_words))
    assert any("different four-operand form" in reason for reason in sincos["reasons"])

    dynamic_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(95, make_dest_token(REG_TEMP, 0), make_source_token(REG_INPUT, 0), make_source_token(REG_SAMPLER, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    dynamic = audit_vs3_bytes(shader(*dynamic_words))
    assert any("not in the vs_2_0 instruction set" in reason for reason in dynamic["reasons"])

    output_semantic_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(3, REG_OUTPUT, 0),  # NORMAL is not a fixed vs_2_0 output register.
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    output_semantic = audit_vs3_bytes(shader(*output_semantic_words))
    assert output_semantic["requires_pixel_shader_interface_remap"] is True
    assert output_semantic["structural_candidate_for_manual_lowering"] is False
    assert output_semantic["output_mapping_plan"]["o0"][0]["vs_2_0_link_semantic"] == "COLOR0"
    assert output_semantic["output_mapping_plan"]["o0"][0]["requires_pixel_shader_interface_remap"] is True
    assert any("position components" in reason for reason in output_semantic["reasons"])

    read_only_write_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_INPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    read_only_write = audit_vs3_bytes(shader(*read_only_write_words))
    assert any("writes read-only or unsupported register type" in reason for reason in read_only_write["reasons"])

    static_flow_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(40, make_source_token(REG_CONSTBOOL, 0)),
        *make_instruction(43),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    static_flow = audit_vs3_bytes(shader(*static_flow_words))
    assert any("static flow control" in reason for reason in static_flow["reasons"])

    # LOOP has two parameter tokens (aL and i#) in D3D9 bytecode; it is
    # parsed correctly and then rejected by this limited no-flow-control audit.
    loop_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            27,
            make_dest_token(REG_LOOP, 0),
            make_source_token(REG_CONSTINT, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    loop = audit_vs3_bytes(shader(*loop_words))
    assert any("static flow control" in reason for reason in loop["reasons"])
    assert not any("expected 2" in reason for reason in loop["reasons"])

    # a0 is write-only; baseline vs_2_0 uses MOVA (not MOV) to update it.
    address_read_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_TEMP, 0), make_source_token(REG_ADDR, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    address_read = audit_vs3_bytes(shader(*address_read_words))
    assert any("reads a0 directly" in reason for reason in address_read["reasons"])

    address_write_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(46, make_dest_token(REG_ADDR, 0, 0x1), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    address_write = audit_vs3_bytes(shader(*address_write_words))
    assert address_write["structural_candidate_for_manual_lowering"] is True

    mova_vector_mask_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(46, make_dest_token(REG_ADDR, 0, 0x3), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    mova_vector_mask = audit_vs3_bytes(shader(*mova_vector_mask_words))
    assert any("baseline vs_2_0 a0.x mask" in reason for reason in mova_vector_mask["reasons"])

    mov_to_address_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_ADDR, 0, 0x1), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    mov_to_address = audit_vs3_bytes(shader(*mov_to_address_words))
    assert any("requires MOVA" in reason for reason in mov_to_address["reasons"])

    mova_wrong_destination_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(46, make_dest_token(REG_TEMP, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    mova_wrong_destination = audit_vs3_bytes(shader(*mova_wrong_destination_words))
    assert any("MOVA" in reason and "must target address register" in reason for reason in mova_wrong_destination["reasons"])

    special_outputs_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *dcl(USAGE_PSIZE, REG_OUTPUT, 1),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 1), make_source_token(REG_INPUT, 0)),
    ]
    special_outputs = audit_vs3_bytes(shader(*special_outputs_words))
    assert special_outputs["structural_candidate_for_manual_lowering"] is True
    assert special_outputs["output_mapping_plan"]["o1"][0]["vs_2_0_link_semantic"] == "PSIZE0"

    partial_position_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0, 0x7), make_source_token(REG_INPUT, 0)),
    ]
    partial_position = audit_vs3_bytes(shader(*partial_position_words))
    assert any("write all four position components" in reason for reason in partial_position["reasons"])

    crs_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            33,
            make_dest_token(REG_TEMP, 0, 0x7),
            make_source_token(REG_INPUT, 0),
            make_source_token(REG_CONST, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    crs = audit_vs3_bytes(shader(*crs_words))
    assert crs["structural_candidate_for_manual_lowering"] is True

    crs_bad_mask_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            33,
            make_dest_token(REG_TEMP, 0, 0xF),
            make_source_token(REG_INPUT, 0),
            make_source_token(REG_CONST, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    crs_bad_mask = audit_vs3_bytes(shader(*crs_bad_mask_words))
    assert any("unsupported destination mask" in reason for reason in crs_bad_mask["reasons"])

    crs_bad_swizzle_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            33,
            make_dest_token(REG_TEMP, 0, 0x7),
            make_source_token(REG_INPUT, 0, 0x1B),
            make_source_token(REG_CONST, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    crs_bad_swizzle = audit_vs3_bytes(shader(*crs_bad_swizzle_words))
    assert any("default src0 swizzle" in reason for reason in crs_bad_swizzle["reasons"])

    crs_alias_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            33,
            make_dest_token(REG_TEMP, 0, 0x7),
            make_source_token(REG_TEMP, 0),
            make_source_token(REG_CONST, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    crs_alias = audit_vs3_bytes(shader(*crs_alias_words))
    assert any("destination aliases src0" in reason for reason in crs_alias["reasons"])

    nrm_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            36,
            make_dest_token(REG_TEMP, 0),
            make_source_token(REG_INPUT, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_TEMP, 0)),
    ]
    nrm = audit_vs3_bytes(shader(*nrm_words))
    assert nrm["structural_candidate_for_manual_lowering"] is True

    nrm_alias_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            36,
            make_dest_token(REG_TEMP, 0),
            make_source_token(REG_TEMP, 0),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    nrm_alias = audit_vs3_bytes(shader(*nrm_alias_words))
    assert any("destination and source must not be the same" in reason for reason in nrm_alias["reasons"])

    sgn_valid_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            34,
            make_dest_token(REG_TEMP, 0),
            make_source_token(REG_INPUT, 0),
            make_source_token(REG_TEMP, 1),
            make_source_token(REG_TEMP, 2),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    sgn_valid = audit_vs3_bytes(shader(*sgn_valid_words))
    assert sgn_valid["structural_candidate_for_manual_lowering"] is True

    sgn_duplicate_scratch_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            34,
            make_dest_token(REG_TEMP, 0),
            make_source_token(REG_INPUT, 0),
            make_source_token(REG_TEMP, 1),
            make_source_token(REG_TEMP, 1),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    sgn_duplicate_scratch = audit_vs3_bytes(shader(*sgn_duplicate_scratch_words))
    assert any("two different temporary scratch registers" in reason for reason in sgn_duplicate_scratch["reasons"])

    matrix_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(20, make_dest_token(REG_TEMP, 0), make_source_token(REG_INPUT, 0), make_source_token(REG_CONST, 4)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_TEMP, 0)),
    ]
    matrix = audit_vs3_bytes(shader(*matrix_words))
    assert matrix["structural_candidate_for_manual_lowering"] is True

    matrix_bad_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(20, make_dest_token(REG_TEMP, 0), make_source_token(REG_INPUT, 0), make_source_token(REG_TEMP, 4)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_TEMP, 0)),
    ]
    matrix_bad = audit_vs3_bytes(shader(*matrix_bad_words))
    assert any("requires a float-constant matrix source" in reason for reason in matrix_bad["reasons"])

    # Baseline vs_2_0 does not provide the vs_3_0 _sat instruction modifier.
    sat_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            1,
            make_dest_token(REG_OUTPUT, 0) | (1 << 20),
            make_source_token(REG_INPUT, 0),
        ),
    ]
    sat = audit_vs3_bytes(shader(*sat_words))
    assert any("_sat is not supported by baseline vs_2_0" in reason for reason in sat["reasons"])

    scalar_mask_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            6,
            make_dest_token(REG_TEMP, 0, 0x3),
            make_source_token(REG_INPUT, 0, 0x00),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_TEMP, 0)),
    ]
    scalar_mask = audit_vs3_bytes(shader(*scalar_mask_words))
    assert any("single-component destination mask" in reason for reason in scalar_mask["reasons"])

    texcoord_gap_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *dcl(USAGE_TEXCOORD, REG_OUTPUT, 1, usage_index=1),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 1), make_source_token(REG_INPUT, 0)),
    ]
    texcoord_gap = audit_vs3_bytes(shader(*texcoord_gap_words))
    assert texcoord_gap["structural_candidate_for_manual_lowering"] is True
    assert texcoord_gap["output_mapping_plan"]["o1"][0]["vs_2_0_register_index"] == 0
    assert texcoord_gap["output_mapping_plan"]["o1"][0]["vs_2_0_link_semantic"] == "TEXCOORD0"
    assert texcoord_gap["output_mapping_plan"]["o1"][0]["requires_pixel_shader_interface_remap"] is True

    texcoord_mask_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *dcl(USAGE_TEXCOORD, REG_OUTPUT, 1, usage_index=1),
        *dcl(USAGE_COLOR, REG_OUTPUT, 2, usage_index=0),
        *dcl(USAGE_COLOR, REG_OUTPUT, 3, usage_index=1),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 1, 0x5), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 2), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 3), make_source_token(REG_INPUT, 0)),
    ]
    texcoord_mask = audit_vs3_bytes(shader(*texcoord_mask_words))
    assert any("non-contiguous component mask" in reason and "no free VS2 color output" in reason for reason in texcoord_mask["reasons"])

    # A TEXCOORD with a sparse component mask can be carried by a color output
    # when one is free; the report marks the pixel-shader link rewrite.
    sparse_texcoord_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *dcl(USAGE_TEXCOORD, REG_OUTPUT, 1, usage_index=1),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 1, 0x5), make_source_token(REG_INPUT, 0)),
    ]
    sparse_texcoord = audit_vs3_bytes(shader(*sparse_texcoord_words))
    assert sparse_texcoord["structural_candidate_for_manual_lowering"] is True
    assert sparse_texcoord["output_mapping_plan"]["o1"][0]["vs_2_0_link_semantic"] == "COLOR0"
    assert sparse_texcoord["output_mapping_plan"]["o1"][0]["requires_pixel_shader_interface_remap"] is True

    # VS3 may pack different semantics into disjoint components of one output
    # register. The lowering plan must split that source write into two outputs.
    duplicate_semantic_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(OP_DCL,
            0x80000000 | (USAGE_COLOR & 0xF),
            make_dest_token(REG_OUTPUT, 3, 0x3)),
        *make_instruction(OP_DCL,
            0x80000000 | (USAGE_COLOR & 0xF),
            make_dest_token(REG_OUTPUT, 4, 0x3)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    duplicate_semantic = audit_vs3_bytes(shader(*duplicate_semantic_words))
    assert any("is declared more than once" in reason for reason in duplicate_semantic["reasons"])

    packed_distinct_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(OP_DCL,
            0x80000000 | (USAGE_COLOR & 0xF),
            make_dest_token(REG_OUTPUT, 3, 0x3)),
        *make_instruction(OP_DCL,
            0x80000000 | (3 & 0xF) | (1 << 16),
            make_dest_token(REG_OUTPUT, 3, 0xC)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 3), make_source_token(REG_INPUT, 0)),
    ]
    packed_distinct = audit_vs3_bytes(shader(*packed_distinct_words))
    assert packed_distinct["structural_candidate_for_manual_lowering"] is True
    assert packed_distinct["output_component_split_required"] is True
    assert packed_distinct["requires_pixel_shader_interface_remap"] is True
    assert len(packed_distinct["output_mapping_plan"]["o3"]) == 2

    overlapping_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(OP_DCL,
            0x80000000 | (USAGE_COLOR & 0xF),
            make_dest_token(REG_OUTPUT, 3, 0x3)),
        *make_instruction(OP_DCL,
            0x80000000 | (3 & 0xF) | (1 << 16),
            make_dest_token(REG_OUTPUT, 3, 0x2)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 3), make_source_token(REG_INPUT, 0)),
    ]
    overlapping = audit_vs3_bytes(shader(*overlapping_words))
    assert any("overlapping DCL component masks" in reason for reason in overlapping["reasons"])

    point_size_bad_mask_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *make_instruction(
            OP_DCL,
            0x80000000 | (USAGE_PSIZE & 0xF),
            make_dest_token(REG_OUTPUT, 2, 0x1),
        ),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 2, 0x1), make_source_token(REG_INPUT, 0)),
    ]
    point_size_bad_mask = audit_vs3_bytes(shader(*point_size_bad_mask_words))
    assert any("PSIZE0 output" in reason for reason in point_size_bad_mask["reasons"])
    assert any("point-size output must use the full" in reason for reason in point_size_bad_mask["reasons"])

    packed_unwritten_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
        *dcl(USAGE_COLOR, REG_OUTPUT, 3, usage_index=0),
        *make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0)),
    ]
    packed_unwritten = audit_vs3_bytes(shader(*packed_unwritten_words))
    assert any("declared output semantic" in reason and "has unwritten components" in reason for reason in packed_unwritten["reasons"])

    over_budget_words = [
        *dcl(USAGE_POSITION, REG_INPUT, 0),
        *dcl(USAGE_POSITION, REG_OUTPUT, 0),
    ]
    for _ in range(257):
        over_budget_words.extend(make_instruction(0))
    over_budget_words.extend(
        make_instruction(1, make_dest_token(REG_OUTPUT, 0), make_source_token(REG_INPUT, 0))
    )
    over_budget = audit_vs3_bytes(shader(*over_budget_words))
    assert over_budget["instruction_slots"] == 258
    assert any("exceeds configured vs_2_0 limit" in reason for reason in over_budget["reasons"])

    truncated = struct.pack("<II", VS3_VERSION, (4 << 24) | 1)
    parse_failure = audit_vs3_bytes(truncated)
    assert parse_failure["status"] == "parse_error"

    print("PASS: conservative vs_3_0 to vs_2_0 vertex-shader audit self-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path)
    parser.add_argument("--report", type=Path, help="Write the JSON audit report")
    parser.add_argument("--max-instruction-slots", type=int, default=256)
    parser.add_argument("--max-temps", type=int, default=12)
    parser.add_argument("--max-float-constants", type=int, default=256)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if args.input is None:
        parser.error("input is required unless --self-test is used")
    if not args.input.exists():
        print(f"ERROR: input path does not exist: {args.input}", file=sys.stderr)
        return 2

    limits = {
        "max_instruction_slots": args.max_instruction_slots,
        "max_temps": args.max_temps,
        "max_float_constants": args.max_float_constants,
    }
    if args.input.is_file():
        paths = [args.input]
    else:
        paths = sorted(
            path for pattern in ("*.bin", "*.vso", "*.vs")
            for path in args.input.glob(pattern) if path.is_file()
        )
    if not paths:
        print(f"ERROR: no .bin, .vso or .vs shader files found at {args.input}", file=sys.stderr)
        return 2

    results: list[dict[str, Any]] = []
    for path in paths:
        try:
            results.append(inspect_file(path, **limits))
        except (OSError, struct.error) as exc:
            results.append({
                "file": str(path),
                "status": "parse_error",
                "structural_candidate_for_manual_lowering": False,
                "reasons": [str(exc)],
            })

    report = {
        "schema_version": 1,
        "input": str(args.input),
        "audited_file_count": len(results),
        "vs_3_0_file_count": sum(1 for item in results if item.get("profile") == "vs_3_0"),
        "candidate_count": sum(
            1 for item in results
            if item.get("structural_candidate_for_manual_lowering")
        ),
        "rejected_count": sum(1 for item in results if item.get("status") == "rejected"),
        "skipped_non_vs3_count": sum(1 for item in results if item.get("status") == "skipped_non_vs3"),
        "parse_error_count": sum(1 for item in results if item.get("status") == "parse_error"),
        "limits": limits,
        "scope_note": (
            "No replacement bytecode is generated. Candidate means only that this "
            "straight-line subset passes the static register, instruction and output "
            "checks; runtime driver acceptance and visual equivalence remain unproven."
        ),
        "results": results,
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for item in results:
        print(f"{item.get('status', 'unknown')}: {item.get('file', args.input)}")
        for reason in item.get("reasons", []):
            print(f"  - {reason}")
    print(
        "Audit complete: "
        f"{report['candidate_count']} candidate(s), "
        f"{report['rejected_count']} rejected, "
        f"{report['skipped_non_vs3_count']} non-vs_3_0 skipped, "
        f"{report['parse_error_count']} parse error(s)."
    )
    return 1 if report["parse_error_count"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
