#!/usr/bin/env python3
"""Conservative ps_3_0 -> ps_2_0 bytecode downleveler.

This tool emits bytecode only for a deliberately narrow, mechanically checked
subset. It does not translate arbitrary SM3 shaders, vertex shaders, dynamic
flow control, or SM3-only material behavior. A successful audit is a structural
candidate, not proof that a particular driver accepts or renders it correctly.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

PS3_VERSION = 0xFFFF0300
PS2_VERSION = 0xFFFF0200
OP_END = 0xFFFF
OP_COMMENT = 0xFFFE
OP_DCL = 31
OP_DEF = 81
OP_TEXKILL = 65
OP_TEX = 66
OP_MOV = 1
OP_SINCOS = 37

# Shader Model 2.0 pixel-shader instruction set and arithmetic slot costs.
# Texture instructions are tracked separately from arithmetic instructions.
PS2_ARITHMETIC_SLOTS = {
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
    18: 2,  # lrp
    19: 1,  # frc
    20: 4,  # m4x4
    21: 3,  # m4x3
    22: 4,  # m3x4
    23: 3,  # m3x3
    24: 2,  # m3x2
    32: 3,  # pow
    33: 2,  # crs
    35: 1,  # abs
    36: 3,  # nrm
    37: 8,  # sincos (listed for complete PS 2.0 slot accounting; this lowerer rejects the SM3 form)
    88: 1,  # cmp
    90: 2,  # dp2add
}
PS2_TEXTURE_OPS = {OP_TEXKILL, OP_TEX}
PS2_ZERO_SLOT_OPS = {OP_DCL, OP_DEF}
PS2_ALLOWED_OPS = set(PS2_ARITHMETIC_SLOTS) | PS2_TEXTURE_OPS | PS2_ZERO_SLOT_OPS

# Instruction parameter-token counts for the subset supported here.
PARAMETER_COUNTS = {
    0: 0,
    1: 2, 2: 3, 3: 3, 4: 4, 5: 3, 6: 2, 7: 2, 8: 3, 9: 3,
    10: 3, 11: 3, 12: 3, 13: 3, 14: 2, 15: 2,
    18: 4, 19: 2, 20: 3, 21: 3, 22: 3, 23: 3, 24: 3,
    32: 3, 33: 3, 35: 2, 36: 2, 37: 4,
    65: 1, 66: 3,
    31: 2,
    81: 5,
    88: 4, 90: 4,
}

OPCODE_NAMES = {
    0: "nop", 1: "mov", 2: "add", 3: "sub", 4: "mad", 5: "mul",
    6: "rcp", 7: "rsq", 8: "dp3", 9: "dp4", 10: "min", 11: "max",
    12: "slt", 13: "sge", 14: "exp", 15: "log", 18: "lrp", 19: "frc",
    20: "m4x4", 21: "m4x3", 22: "m3x4", 23: "m3x3", 24: "m3x2",
    31: "dcl", 32: "pow", 33: "crs", 35: "abs", 36: "nrm",
    37: "sincos", 65: "texkill", 66: "texld/texldb/texldp",
    81: "def", 88: "cmp", 90: "dp2add",
}

# D3DSHADER_PARAM_REGISTER_TYPE
REG_TEMP = 0
REG_INPUT = 1
REG_CONST = 2
REG_TEXTURE = 3
REG_COLOROUT = 8
REG_DEPTHOUT = 9
REG_SAMPLER = 10

# PS 2.0 permits identity, scalar-replicate and three additional swizzles.
PS2_ALLOWED_SWIZZLES = {
    0xE4,  # xyzw
    0x00,  # xxxx
    0x55,  # yyyy
    0xAA,  # zzzz
    0xFF,  # wwww
    0xC9,  # yzxw
    0xD2,  # zxyw
    0x1B,  # wzyx
}
DEFAULT_SWIZZLE = 0xE4
SOURCE_MOD_NONE = 0
SOURCE_MOD_NEGATE = 1
DEST_MOD_NONE = 0
DEST_MOD_SATURATE = 1
DEST_MOD_PARTIAL_PRECISION = 2
DEST_MOD_CENTROID = 4
TEXLD_PROJECT = 1
TEXLD_BIAS = 2

# D3DDECLUSAGE values used by Direct3D pixel-shader input declarations.
USAGE_TEXCOORD = 5
USAGE_COLOR = 10


class AuditError(ValueError):
    """A structural problem in the shader token stream."""


@dataclass
class Instruction:
    offset: int
    token: int
    opcode: int
    operands: list[int]


def reg_type(token: int) -> int:
    return ((token & 0x70000000) >> 28) | ((token & 0x00001800) >> 8)


def reg_number(token: int) -> int:
    return token & 0x7FF


def replace_register(token: int, new_type: int, new_number: int) -> int:
    token &= ~(0x70000000 | 0x00001800 | 0x000007FF)
    token |= ((new_type & 0x7) << 28) | ((new_type & 0x18) << 8)
    token |= new_number & 0x7FF
    return token


def make_register(reg: int, number: int, mask: int = 0xF) -> int:
    return (
        0x80000000
        | (number & 0x7FF)
        | ((mask & 0xF) << 16)
        | ((reg & 0x7) << 28)
        | ((reg & 0x18) << 8)
    )


def make_source(reg: int, number: int, swizzle: int = DEFAULT_SWIZZLE,
                modifier: int = SOURCE_MOD_NONE) -> int:
    return (
        0x80000000
        | (number & 0x7FF)
        | ((swizzle & 0xFF) << 16)
        | ((modifier & 0xF) << 24)
        | ((reg & 0x7) << 28)
        | ((reg & 0x18) << 8)
    )


def make_instruction(opcode: int, *operands: int, controls: int = 0,
                     predicated: bool = False) -> int:
    token = (
        (opcode & 0xFFFF)
        | ((controls & 0xFF) << 16)
        | ((len(operands) & 0xF) << 24)
    )
    if predicated:
        token |= 1 << 28
    return token


def parse_ps3(data: bytes) -> tuple[list[int], list[Instruction]]:
    if len(data) < 8 or len(data) % 4:
        raise AuditError("bytecode must be DWORD-aligned and contain a version plus END")
    words = list(struct.unpack("<" + "I" * (len(data) // 4), data))
    if words[0] != PS3_VERSION:
        raise AuditError(f"expected ps_3_0 token 0x{PS3_VERSION:08X}, got 0x{words[0]:08X}")

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
                raise AuditError("COMMENT payload runs past end of bytecode")
            cursor += comment_length
            continue
        if opcode == 0xFFFD:
            raise AuditError("PHASE token is not legal in the supported ps_3_0 subset")

        parameter_count = (token >> 24) & 0xF
        if parameter_count > len(words) - cursor:
            raise AuditError(
                f"instruction at DWORD {start} claims {parameter_count} operands, "
                "but the bytecode ends early"
            )
        operands = words[cursor:cursor + parameter_count]
        cursor += parameter_count
        instructions.append(Instruction(start, token, opcode, operands))

    if not found_end:
        raise AuditError("missing D3DSIO_END token")
    if any(words[cursor:]):
        raise AuditError("non-zero DWORDs follow D3DSIO_END")
    return words, instructions


def _fail(reason: str) -> dict[str, Any]:
    return {"eligible": False, "reasons": [reason], "output_bytecode": None}


def audit_and_lower_ps3(
    data: bytes,
    *,
    max_samplers: int = 16,
    dependent_read_limit: int = 3,
    max_arithmetic_slots: int = 64,
    max_texture_slots: int = 32,
) -> dict[str, Any]:
    if not 1 <= max_samplers <= 16:
        raise ValueError("max_samplers must be between 1 and 16")
    if dependent_read_limit < 0:
        raise ValueError("dependent_read_limit cannot be negative")

    try:
        original_words, instructions = parse_ps3(data)
    except AuditError as exc:
        return _fail(str(exc))

    reasons: list[str] = []
    input_remap: dict[int, tuple[int, int]] = {}
    occupied_ps2_inputs: set[tuple[int, int]] = set()
    declared_samplers: set[int] = set()
    used_samplers: set[int] = set()
    arithmetic_slots = 0
    texture_slots = 0
    output_writes = 0
    temp_written: set[int] = set()
    temp_dependency_depth: dict[int, int] = {}
    max_seen_dependency = 0

    # First pass: gather input/sampler declarations so references can be
    # remapped regardless of declaration order in the token stream.
    for ins in instructions:
        if ins.opcode != OP_DCL:
            continue
        if len(ins.operands) != 2:
            reasons.append(f"DCL at DWORD {ins.offset} has an invalid operand count")
            continue

        declaration, destination = ins.operands
        destination_type = reg_type(destination)
        destination_number = reg_number(destination)

        if destination_type == REG_SAMPLER:
            sampler_type = (declaration & 0x78000000) >> 27
            if sampler_type not in (2, 3, 4):
                reasons.append(
                    f"sampler s{destination_number} has an unknown or unsupported declaration type"
                )
            if destination_number >= max_samplers:
                reasons.append(
                    f"sampler s{destination_number} exceeds configured limit {max_samplers}"
                )
            if destination_number in declared_samplers:
                reasons.append(f"sampler s{destination_number} is declared more than once")
            declared_samplers.add(destination_number)
            continue

        if destination_type != REG_INPUT:
            reasons.append(
                f"DCL at DWORD {ins.offset} targets register type {destination_type}, "
                "which this lowerer does not handle"
            )
            continue

        source_register = destination_number
        if source_register > 9:
            reasons.append(f"ps_3_0 input v{source_register} exceeds the ten-input-register limit")
            continue
        usage = declaration & 0xF
        usage_index = (declaration >> 16) & 0xF

        if usage == USAGE_COLOR and usage_index in (0, 1):
            mapped = (REG_INPUT, usage_index)   # PS 2.0 v0/v1
        elif usage == USAGE_TEXCOORD and usage_index <= 7:
            mapped = (REG_TEXTURE, usage_index)  # PS 2.0 t0-t7
        else:
            reasons.append(
                f"input v{source_register} semantic usage={usage}, index={usage_index} "
                "has no supported ps_2_0 COLOR0/1 or TEXCOORD0-7 mapping"
            )
            continue

        if source_register in input_remap:
            reasons.append(f"ps_3_0 input v{source_register} has multiple declarations")
            continue
        if mapped in occupied_ps2_inputs:
            reasons.append(
                f"multiple ps_3_0 inputs map to ps_2_0 register type={mapped[0]} "
                f"index={mapped[1]}"
            )
            continue
        input_remap[source_register] = mapped
        occupied_ps2_inputs.add(mapped)

    # Second pass: prove every instruction/register/limit fits the PS 2.0 subset.
    for ins in instructions:
        opcode = ins.opcode
        name = OPCODE_NAMES.get(opcode, f"opcode_{opcode}")
        expected = PARAMETER_COUNTS.get(opcode)

        if opcode not in PS2_ALLOWED_OPS:
            reasons.append(
                f"{name} at DWORD {ins.offset} is not in the ps_2_0 instruction set"
            )
            continue
        if opcode == OP_SINCOS:
            reasons.append("sincos uses a version-sensitive operand form; bespoke rewrite required")
            continue
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
                f"{name} at DWORD {ins.offset} uses SM3 instruction predication"
            )
        controls = (ins.token >> 16) & 0xFF
        if opcode == OP_TEX:
            if controls not in (0, TEXLD_PROJECT, TEXLD_BIAS):
                reasons.append(
                    f"tex instruction at DWORD {ins.offset} uses unknown control bits 0x{controls:02X}"
                )
        elif controls != 0:
            reasons.append(
                f"{name} at DWORD {ins.offset} uses unsupported instruction control bits 0x{controls:02X}"
            )

        if opcode in PS2_ARITHMETIC_SLOTS:
            arithmetic_slots += PS2_ARITHMETIC_SLOTS[opcode]
        elif opcode in PS2_TEXTURE_OPS:
            texture_slots += 1

        if opcode == OP_DCL:
            continue
        if opcode == 0:  # nop has no operands
            continue
        if opcode == OP_DEF:
            destination = ins.operands[0]
            if reg_type(destination) != REG_CONST or reg_number(destination) > 31:
                reasons.append(
                    f"DEF at DWORD {ins.offset} defines a constant outside c0-c31"
                )
            continue

        if opcode == OP_TEXKILL:
            source = ins.operands[0]
            source_type = reg_type(source)
            source_number = reg_number(source)
            if source_type not in (REG_TEMP, REG_TEXTURE):
                reasons.append(
                    f"texkill at DWORD {ins.offset} requires a temp or texcoord register"
                )
            if source_type == REG_TEMP and source_number > 11:
                reasons.append(f"texkill at DWORD {ins.offset} reads r{source_number}; ps_2_0 has r0-r11")
            if source_type == REG_TEXTURE and source_number > 7:
                reasons.append(f"texkill at DWORD {ins.offset} reads t{source_number}; ps_2_0 has t0-t7")
            if _dest_mask(source) != 0xF or _dest_modifier(source) != DEST_MOD_NONE or _dest_shift(source) != 0:
                reasons.append(f"texkill at DWORD {ins.offset} requires a full, unmodified coordinate operand")
            continue

        if opcode == OP_TEX:
            destination, coordinates, sampler = ins.operands
            if reg_type(destination) != REG_TEMP:
                reasons.append(f"texture result at DWORD {ins.offset} must target a temp register")
            if reg_number(destination) > 11:
                reasons.append(
                    f"texture result at DWORD {ins.offset} uses r{reg_number(destination)}; ps_2_0 has r0-r11"
                )
            if _dest_mask(destination) != 0xF or _dest_modifier(destination) != DEST_MOD_NONE:
                reasons.append(f"texture result at DWORD {ins.offset} needs a full, unmodified destination")
            _check_source(coordinates, ins, reasons, input_remap, texture_coordinate=True)
            _check_source(sampler, ins, reasons, input_remap, sampler=True)
            sampler_number = reg_number(sampler)
            used_samplers.add(sampler_number)
            if sampler_number not in declared_samplers:
                reasons.append(f"texture instruction uses undeclared sampler s{sampler_number}")

            coordinate_type = reg_type(coordinates)
            destination_number = reg_number(destination)
            previous_destination_write = destination_number in temp_written
            coordinate_depth = (
                temp_dependency_depth.get(reg_number(coordinates), 0)
                if coordinate_type == REG_TEMP else 0
            )
            depth = 0
            if coordinate_type == REG_TEMP:
                depth = coordinate_depth + 1
            if previous_destination_write:
                depth = max(depth, 1)
            if dependent_read_limit > 0 and depth > dependent_read_limit:
                reasons.append(
                    f"texture instruction at DWORD {ins.offset} reaches dependent-read order {depth}; "
                    f"configured ps_2_0 limit is {dependent_read_limit}"
                )
            temp_dependency_depth[destination_number] = depth
            temp_written.add(destination_number)
            max_seen_dependency = max(max_seen_dependency, depth)
            continue

        destination = ins.operands[0]
        destination_type = reg_type(destination)
        destination_number = reg_number(destination)

        if destination_type == REG_COLOROUT:
            output_writes += 1
            if opcode != OP_MOV:
                reasons.append(
                    f"oC{destination_number} is written by {name}; ps_2_0 requires a mov"
                )
            if destination_number != 0:
                reasons.append(
                    f"oC{destination_number} requires multiple render targets; this lowerer only supports oC0"
                )
            if _dest_mask(destination) != 0xF or _dest_modifier(destination) != DEST_MOD_NONE or _dest_shift(destination) != 0:
                reasons.append("oC0 write must use the full mask and no destination modifier or shift")
            if len(ins.operands) >= 2:
                source = ins.operands[1]
                if _source_swizzle(source) != DEFAULT_SWIZZLE or _source_modifier(source) != SOURCE_MOD_NONE:
                    reasons.append("oC0 source must use default swizzle and no source modifier in this lowerer")
        elif destination_type == REG_TEMP:
            if destination_number > 11:
                reasons.append(
                    f"{name} at DWORD {ins.offset} writes r{destination_number}; ps_2_0 has r0-r11"
                )
            modifier = _dest_modifier(destination)
            if modifier not in (DEST_MOD_NONE, DEST_MOD_SATURATE, DEST_MOD_PARTIAL_PRECISION):
                reasons.append(
                    f"{name} at DWORD {ins.offset} uses unsupported destination modifier {modifier}"
                )
            if _dest_shift(destination) != 0:
                reasons.append(f"{name} at DWORD {ins.offset} uses destination scaling")
            source_depths = []
            for source in ins.operands[1:]:
                _check_source(source, ins, reasons, input_remap)
                if reg_type(source) == REG_TEMP:
                    source_depths.append(temp_dependency_depth.get(reg_number(source), 0))
            temp_dependency_depth[destination_number] = max(source_depths, default=0)
            temp_written.add(destination_number)
        else:
            reasons.append(
                f"{name} at DWORD {ins.offset} writes unsupported destination register type={destination_type}"
            )

        for source in ins.operands[1:]:
            _check_source(source, ins, reasons, input_remap)

    if output_writes == 0:
        reasons.append("shader never writes oC0, which is required by the supported ps_2_0 path")
    if output_writes > 1:
        reasons.append(
            f"shader writes pixel outputs {output_writes} times; ps_2_0 permits at most one oC# write"
        )
    if arithmetic_slots > max_arithmetic_slots:
        reasons.append(
            f"arithmetic slot count {arithmetic_slots} exceeds ps_2_0 limit {max_arithmetic_slots}"
        )
    if texture_slots > max_texture_slots:
        reasons.append(
            f"texture slot count {texture_slots} exceeds ps_2_0 limit {max_texture_slots}"
        )

    # Deduplicate repeated diagnostics while retaining their discovery order.
    reasons = list(dict.fromkeys(reasons))
    if reasons:
        return {
            "eligible": False,
            "reasons": reasons,
            "profile": "ps_3_0",
            "arithmetic_slots": arithmetic_slots,
            "texture_slots": texture_slots,
            "declared_samplers": sorted(declared_samplers),
            "used_samplers": sorted(used_samplers),
            "input_remap": {
                str(source): {"register_type": target[0], "register_index": target[1]}
                for source, target in sorted(input_remap.items())
            },
            "maximum_dependent_read_order": max_seen_dependency,
            "output_bytecode": None,
        }

    lowered = _emit_ps2_bytecode(original_words, instructions, input_remap)
    return {
        "eligible": True,
        "reasons": [],
        "profile": "ps_2_0",
        "arithmetic_slots": arithmetic_slots,
        "texture_slots": texture_slots,
        "declared_samplers": sorted(declared_samplers),
        "used_samplers": sorted(used_samplers),
        "input_remap": {
            str(source): {"register_type": target[0], "register_index": target[1]}
            for source, target in sorted(input_remap.items())
        },
        "maximum_dependent_read_order": max_seen_dependency,
        "output_bytecode": lowered,
    }


def _dest_mask(token: int) -> int:
    return (token >> 16) & 0xF


def _dest_modifier(token: int) -> int:
    return (token >> 20) & 0xF


def _dest_shift(token: int) -> int:
    return (token >> 24) & 0xF


def _source_swizzle(token: int) -> int:
    return (token >> 16) & 0xFF


def _source_modifier(token: int) -> int:
    return (token >> 24) & 0xF


def _check_source(
    token: int,
    ins: Instruction,
    reasons: list[str],
    input_remap: dict[int, tuple[int, int]],
    *,
    sampler: bool = False,
    texture_coordinate: bool = False,
) -> None:
    kind = reg_type(token)
    number = reg_number(token)
    modifier = _source_modifier(token)
    swizzle = _source_swizzle(token)

    if kind == REG_INPUT:
        if number > 9:
            reasons.append(
                f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
                f"references v{number}; ps_3_0 has v0-v9"
            )
        if number not in input_remap:
            reasons.append(
                f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
                f"reads undeclared ps_3_0 input v{number}"
            )
        mapped = input_remap.get(number)
        if mapped is not None and mapped[0] == REG_TEXTURE and mapped[1] > 7:
            reasons.append(f"mapped texture input t{mapped[1]} is outside ps_2_0 range")
        if texture_coordinate and mapped is not None and mapped[0] not in (REG_TEMP, REG_TEXTURE):
            reasons.append(
                f"texture coordinate input v{number} maps to a ps_2_0 COLOR register, "
                "but texture sampling requires t# or r#"
            )
    elif kind == REG_TEMP:
        if number > 11:
            reasons.append(
                f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
                f"reads r{number}; ps_2_0 has r0-r11"
            )
    elif kind == REG_CONST:
        if number > 31:
            reasons.append(
                f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
                f"reads c{number}; ps_2_0 has c0-c31"
            )
    elif kind == REG_TEXTURE:
        if number > 7:
            reasons.append(
                f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
                f"reads t{number}; ps_2_0 has t0-t7"
            )
    elif kind == REG_SAMPLER:
        if not sampler:
            reasons.append(
                f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
                "uses a sampler in a non-sampler operand"
            )
    else:
        reasons.append(
            f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
            f"uses unsupported source register type={kind}"
        )

    if sampler or texture_coordinate:
        if modifier != SOURCE_MOD_NONE or swizzle != DEFAULT_SWIZZLE:
            reasons.append(
                f"texture instruction at DWORD {ins.offset} requires unmodified, unswizzled "
                "coordinate and sampler operands"
            )
        return

    if modifier not in (SOURCE_MOD_NONE, SOURCE_MOD_NEGATE):
        reasons.append(
            f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
            f"uses source modifier {modifier}, outside the supported ps_2_0 subset"
        )
    if swizzle not in PS2_ALLOWED_SWIZZLES:
        reasons.append(
            f"{OPCODE_NAMES.get(ins.opcode, 'instruction')} at DWORD {ins.offset} "
            f"uses non-ps_2_0 swizzle 0x{swizzle:02X}"
        )


def _emit_ps2_bytecode(
    original_words: list[int],
    instructions: list[Instruction],
    input_remap: dict[int, tuple[int, int]],
) -> bytes:
    words = list(original_words)
    words[0] = PS2_VERSION

    for ins in instructions:
        if ins.opcode == OP_DCL:
            destination_index = ins.offset + 2
            declaration_destination = words[destination_index]
            if reg_type(declaration_destination) == REG_INPUT:
                old_number = reg_number(declaration_destination)
                new_type, new_number = input_remap[old_number]
                words[destination_index] = replace_register(
                    declaration_destination, new_type, new_number
                )
            continue

        if ins.opcode in (OP_DEF,):
            continue

        # All ordinary instruction operands after the destination are sources.
        # TEXKILL has one source operand and is handled by the same remapping.
        source_start = ins.offset + 1
        if ins.opcode == OP_TEXKILL:
            source_indices = [source_start]
        else:
            source_indices = range(source_start + 1, source_start + len(ins.operands))

        for word_index in source_indices:
            token = words[word_index]
            if reg_type(token) == REG_INPUT:
                old_number = reg_number(token)
                new_type, new_number = input_remap[old_number]
                words[word_index] = replace_register(token, new_type, new_number)

    return struct.pack("<" + "I" * len(words), *words)


def audit_file(
    path: Path,
    *,
    emit_dir: Path | None,
    max_samplers: int,
    dependent_read_limit: int,
) -> dict[str, Any]:
    data = path.read_bytes()
    base: dict[str, Any] = {
        "file": path.name,
        "sha256": hashlib.sha256(data).hexdigest(),
        "bytes": len(data),
    }

    if len(data) >= 4:
        version = struct.unpack_from("<I", data)[0]
        if version == PS2_VERSION:
            base.update({
                "status": "already_ps_2_0",
                "eligible": False,
                "reasons": ["shader is already ps_2_0"],
            })
            return base
        if version != PS3_VERSION:
            base.update({
                "status": "unsupported_profile",
                "eligible": False,
                "reasons": [f"unsupported shader version token 0x{version:08X}"],
            })
            return base

    result = audit_and_lower_ps3(
        data,
        max_samplers=max_samplers,
        dependent_read_limit=dependent_read_limit,
    )
    base.update({key: value for key, value in result.items() if key != "output_bytecode"})
    if result["eligible"]:
        base["status"] = "ps2_candidate_emitted" if emit_dir else "ps2_candidate"
        if emit_dir:
            emit_dir.mkdir(parents=True, exist_ok=True)
            stem = path.stem
            output_path = emit_dir / f"{stem}.ps20.pso"
            output_path.write_bytes(result["output_bytecode"])
            base["output_file"] = str(output_path)
            base["output_sha256"] = hashlib.sha256(result["output_bytecode"]).hexdigest()
    else:
        base["status"] = "requires_rewrite_or_manual_fallback"
    return base


def _self_test() -> None:
    # A small valid SM3 shader using only ps_2_0 operations. Inputs:
    # v0 = TEXCOORD0 -> t0, v1 = COLOR0 -> v0.
    words = [PS3_VERSION]
    words += [
        make_instruction(OP_DCL,
            (USAGE_TEXCOORD | (0 << 16)),
            make_register(REG_INPUT, 0)),
        make_instruction(OP_DCL,
            (USAGE_COLOR | (0 << 16)),
            make_register(REG_INPUT, 1)),
        make_instruction(OP_DCL,
            (2 << 27),
            make_register(REG_SAMPLER, 0)),
        make_instruction(OP_MOV,
            make_register(REG_TEMP, 0),
            make_source(REG_INPUT, 0)),
        make_instruction(OP_TEX,
            make_register(REG_TEMP, 1),
            make_source(REG_TEMP, 0),
            make_source(REG_SAMPLER, 0)),
        make_instruction(2,
            make_register(REG_TEMP, 2),
            make_source(REG_TEMP, 1),
            make_source(REG_INPUT, 1)),
        make_instruction(OP_MOV,
            make_register(REG_COLOROUT, 0),
            make_source(REG_TEMP, 2)),
        OP_END,
    ]
    source = struct.pack("<" + "I" * len(words), *words)
    audit = audit_and_lower_ps3(source)
    assert audit["eligible"], audit["reasons"]
    lowered = audit["output_bytecode"]
    lowered_words = list(struct.unpack("<" + "I" * (len(lowered) // 4), lowered))
    assert lowered_words[0] == PS2_VERSION
    # The first DCL input destination is now a t0 register (type 3).
    first_dcl_dest = lowered_words[3]
    assert reg_type(first_dcl_dest) == REG_TEXTURE and reg_number(first_dcl_dest) == 0
    # The second DCL input destination is now v0 (type 1).
    second_dcl_dest = lowered_words[6]
    assert reg_type(second_dcl_dest) == REG_INPUT and reg_number(second_dcl_dest) == 0
    # The source reference to original v0 is remapped to t0.
    mov_source = lowered_words[12]
    assert reg_type(mov_source) == REG_TEXTURE and reg_number(mov_source) == 0
    # The later source reference to original v1 is remapped to v0.
    add_source = lowered_words[20]
    assert reg_type(add_source) == REG_INPUT and reg_number(add_source) == 0

    def build(*items: int) -> bytes:
        return struct.pack("<" + "I" * len(items), *items)

    # Reject SM3-only dynamic flow and gradient instructions.
    flow_shader = build(
        PS3_VERSION,
        make_instruction(41, make_source(REG_TEMP, 0), make_source(REG_TEMP, 1)),
        OP_END,
    )
    flow_result = audit_and_lower_ps3(flow_shader)
    assert not flow_result["eligible"] and any("not in the ps_2_0 instruction set" in x for x in flow_result["reasons"])

    dsx_shader = build(PS3_VERSION, make_instruction(91, make_register(REG_TEMP, 0), make_source(REG_TEMP, 1)), OP_END)
    dsx_result = audit_and_lower_ps3(dsx_shader)
    assert not dsx_result["eligible"] and any("not in the ps_2_0 instruction set" in x for x in dsx_result["reasons"])

    # Reject r12, arbitrary swizzles and a repeated/masked oC0 write.
    high_temp = build(
        PS3_VERSION,
        make_instruction(OP_MOV, make_register(REG_TEMP, 12), make_source(REG_CONST, 0)),
        make_instruction(OP_MOV, make_register(REG_COLOROUT, 0), make_source(REG_TEMP, 12)),
        OP_END,
    )
    assert not audit_and_lower_ps3(high_temp)["eligible"]

    arbitrary_swizzle = build(
        PS3_VERSION,
        make_instruction(OP_MOV, make_register(REG_TEMP, 0), make_source(REG_CONST, 0, swizzle=0xE1)),
        make_instruction(OP_MOV, make_register(REG_COLOROUT, 0), make_source(REG_TEMP, 0)),
        OP_END,
    )
    assert not audit_and_lower_ps3(arbitrary_swizzle)["eligible"]

    masked_output = build(
        PS3_VERSION,
        make_instruction(OP_MOV, make_register(REG_COLOROUT, 0, mask=0x7), make_source(REG_CONST, 0)),
        OP_END,
    )
    assert not audit_and_lower_ps3(masked_output)["eligible"]

    print("PASS: conservative ps_3_0 to ps_2_0 downlevel audit self-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", nargs="?", type=Path, help="A shader .bin/.pso file or capture directory")
    parser.add_argument("--emit-dir", type=Path, help="Write structurally eligible ps_2_0 candidates here")
    parser.add_argument("--report", type=Path, help="Write JSON audit report")
    parser.add_argument("--max-samplers", type=int, default=16)
    parser.add_argument("--dependent-read-limit", type=int, default=3,
                        help="Use 3 for the PS 2.0 dependent-read bound; use 0 only when device caps prove no limit")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if args.input is None:
        parser.error("input is required unless --self-test is used")

    files = [args.input] if args.input.is_file() else sorted(
        p for p in args.input.glob("*.bin") if p.is_file()
    ) if args.input.is_dir() else []
    if not files:
        print(f"ERROR: no shader files found at {args.input}", file=sys.stderr)
        return 2

    records = []
    for path in files:
        try:
            records.append(audit_file(
                path,
                emit_dir=args.emit_dir,
                max_samplers=args.max_samplers,
                dependent_read_limit=args.dependent_read_limit,
            ))
        except (OSError, struct.error) as exc:
            records.append({
                "file": path.name,
                "status": "parse_error",
                "eligible": False,
                "reasons": [str(exc)],
            })

    report = {
        "schema_version": 1,
        "input": str(args.input),
        "audited_file_count": len(records),
        "eligible_count": sum(1 for r in records if r.get("eligible")),
        "rejected_count": sum(1 for r in records if not r.get("eligible")),
        "dependent_read_limit": args.dependent_read_limit,
        "max_samplers": args.max_samplers,
        "results": records,
        "scope_note": (
            "Only a constrained ps_3_0 pixel-shader subset is lowered. Vertex shaders, "
            "SM3-only instructions/features and unproven register/interface patterns "
            "are rejected. Emitted bytecode is structurally screened but must still be "
            "validated by D3D9 runtime/driver and rendered against the original material."
        ),
    }
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    for record in records:
        print(f"{record['file']}: {record.get('status', 'error')}")
        for reason in record.get("reasons", []):
            print(f"  - {reason}")

    print(
        f"Audit complete: {report['eligible_count']} candidate(s), "
        f"{report['rejected_count']} rejected/unchanged."
    )
    return 0 if all(r.get("status") not in ("parse_error",) for r in records) else 1


if __name__ == "__main__":
    raise SystemExit(main())
