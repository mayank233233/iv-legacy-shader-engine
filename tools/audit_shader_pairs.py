#!/usr/bin/env python3
"""Draw-level pairing audit for captured Direct3D 9 vs_3_0 / ps_3_0 shaders.

This is a read-only triage tool. It joins the shader objects used by each draw
to captured bytecode, checks VS output / PS input semantics and component masks,
checks VS inputs against the active vertex declaration or a supported FVF, and
checks captured sampler bindings and render-target limits. It emits no shader
bytecode and never changes the game or D3D9 state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import struct
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any

from analyze_asi_log import analyze_log
import audit_sm3_to_sm2
import audit_vs3_to_vs2

# D3DDECLUSAGE numeric values.
USAGE_NAMES = {
    0: "POSITION", 1: "BLENDWEIGHT", 2: "BLENDINDICES", 3: "NORMAL",
    4: "PSIZE", 5: "TEXCOORD", 6: "TANGENT", 7: "BINORMAL",
    8: "TESSFACTOR", 9: "POSITIONT", 10: "COLOR", 11: "FOG",
    12: "DEPTH", 13: "SAMPLE",
}

# D3DDECLTYPE: (byte size, explicitly stored component count).
DECL_TYPES = {
    0: (4, 1, "FLOAT1"),
    1: (8, 2, "FLOAT2"),
    2: (12, 3, "FLOAT3"),
    3: (16, 4, "FLOAT4"),
    4: (4, 4, "D3DCOLOR"),
    5: (4, 4, "UBYTE4"),
    6: (4, 2, "SHORT2"),
    7: (8, 4, "SHORT4"),
    8: (4, 4, "UBYTE4N"),
    9: (4, 2, "SHORT2N"),
    10: (8, 4, "SHORT4N"),
    11: (4, 2, "USHORT2N"),
    12: (8, 4, "USHORT4N"),
    13: (4, 3, "UDEC3"),
    14: (4, 3, "DEC3N"),
    15: (4, 2, "FLOAT16_2"),
    16: (8, 4, "FLOAT16_4"),
}

# D3D9 VS2 output register classes -> the register classes used by the
# existing PS2 downlevel tool for the corresponding rasterizer interpolators.
VS2_TO_PS2_LINK_TYPES = {
    audit_vs3_to_vs2.REG_ATTROUT: audit_sm3_to_sm2.REG_INPUT,
    audit_vs3_to_vs2.REG_OUTPUT: audit_sm3_to_sm2.REG_TEXTURE,
}

def fnv1a64(data: bytes) -> str:
    value = 14695981039346656037
    for byte in data:
        value ^= byte
        value = (value * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{value:016X}"

def profile_from_bytes(data: bytes) -> tuple[str, int, int] | None:
    if len(data) < 4 or len(data) % 4:
        return None
    token = struct.unpack_from("<I", data)[0]
    marker = token & 0xFFFF0000
    stage = "VS" if marker == 0xFFFE0000 else "PS" if marker == 0xFFFF0000 else None
    if stage is None:
        return None
    return stage, (token >> 8) & 0xFF, token & 0xFF

def index_captures(directory: Path) -> dict[str, list[tuple[Path, bytes, str, int, int]]]:
    if not directory.is_dir():
        raise FileNotFoundError(f"shader capture directory not found: {directory}")
    index: dict[str, list[tuple[Path, bytes, str, int, int]]] = {}
    candidates = sorted(
        path for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in {".bin", ".vso", ".pso", ".vs", ".ps"}
    )
    for path in candidates:
        try:
            data = path.read_bytes()
        except OSError:
            continue
        profile = profile_from_bytes(data)
        if profile is None:
            continue
        stage, major, minor = profile
        index.setdefault(fnv1a64(data), []).append((path, data, stage, major, minor))
    return index

def select_capture(
    shader: dict[str, Any] | None,
    expected_stage: str,
    captures: dict[str, list[tuple[Path, bytes, str, int, int]]],
) -> tuple[Path, bytes] | None:
    if not shader:
        return None
    key = str(shader.get("hash", "")).upper()
    for path, data, stage, major, minor in captures.get(key, []):
        if stage != expected_stage:
            continue
        declared_profile = str(shader.get("profile", "")).lower()
        actual_profile = f"{stage.lower()}_{major}_{minor}"
        if declared_profile and declared_profile != actual_profile:
            continue
        return path, data
    return None

def parse_ps_inputs(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """Read PS3 dcl_semantics inputs, retaining register packing and masks."""
    inputs: list[dict[str, Any]] = []
    reasons: list[str] = []
    try:
        _, instructions = audit_sm3_to_sm2.parse_ps3(data)
    except (audit_sm3_to_sm2.AuditError, struct.error) as exc:
        return [], [f"pixel shader declaration parse failed: {exc}"]

    for ins in instructions:
        if ins.opcode != audit_sm3_to_sm2.OP_DCL or len(ins.operands) != 2:
            continue
        declaration, destination = ins.operands
        if audit_sm3_to_sm2.reg_type(destination) != audit_sm3_to_sm2.REG_INPUT:
            continue
        usage = declaration & 0xF
        usage_index = (declaration >> 16) & 0xF
        mask = (destination >> 16) & 0xF
        modifier = (destination >> 20) & 0xF
        inputs.append({
            "register": audit_sm3_to_sm2.reg_number(destination),
            "usage": usage,
            "semantic": f"{USAGE_NAMES.get(usage, f'UNKNOWN_{usage}')}{usage_index}",
            "usage_index": usage_index,
            "component_mask": mask,
            "destination_modifier": modifier,
            "declaration_token": f"0x{declaration:08X}",
            "destination_token": f"0x{destination:08X}",
            "instruction_modifier_bits": (ins.token >> 16) & 0xFF,
        })

    semantic_counts = Counter((item["usage"], item["usage_index"]) for item in inputs)
    for semantic, count in semantic_counts.items():
        if count > 1:
            name = f"{USAGE_NAMES.get(semantic[0], f'UNKNOWN_{semantic[0]}')}{semantic[1]}"
            reasons.append(f"pixel input semantic {name} is declared more than once")

    by_register: dict[int, list[dict[str, Any]]] = {}
    for item in inputs:
        by_register.setdefault(item["register"], []).append(item)
    for register, entries in by_register.items():
        if len(entries) > 1:
            combined = 0
            for entry in entries:
                if combined & entry["component_mask"]:
                    reasons.append(
                        f"pixel input v{register} has overlapping component declarations"
                    )
                combined |= entry["component_mask"]
            reasons.append(
                f"pixel input v{register} packs multiple semantics; current PS2 lowerer "
                "cannot split one source register across multiple target registers"
            )
    return inputs, reasons

def semantic_key(item: dict[str, Any]) -> tuple[int, int]:
    return int(item["usage"]), int(item["usage_index"])

def max_ps_temp_register(data: bytes) -> int:
    """Return the highest referenced PS temporary register, or -1."""
    try:
        _, instructions = audit_sm3_to_sm2.parse_ps3(data)
    except (audit_sm3_to_sm2.AuditError, struct.error):
        return -1
    highest = -1
    for ins in instructions:
        if ins.opcode in (audit_sm3_to_sm2.OP_DCL, audit_sm3_to_sm2.OP_DEF):
            continue
        for operand in ins.operands:
            if audit_sm3_to_sm2.reg_type(operand) == audit_sm3_to_sm2.REG_TEMP:
                highest = max(highest, audit_sm3_to_sm2.reg_number(operand))
    return highest

def format_mask(mask: int) -> str:
    return "".join(letter for bit, letter in enumerate("xyzw") if mask & (1 << bit)) or "-"

def map_ps2_input(usage: int, usage_index: int) -> tuple[int, int] | None:
    if usage == audit_sm3_to_sm2.USAGE_COLOR and usage_index in (0, 1):
        return audit_sm3_to_sm2.REG_INPUT, usage_index
    if usage == audit_sm3_to_sm2.USAGE_TEXCOORD and usage_index <= 7:
        return audit_sm3_to_sm2.REG_TEXTURE, usage_index
    return None

def audit_shader_interface(
    vertex_result: dict[str, Any],
    pixel_result: dict[str, Any],
    pixel_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    outputs: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for output_register, declarations in vertex_result.get("output_mapping_plan", {}).items():
        source_register_match = re.fullmatch(r"o(\d+)", str(output_register))
        source_register = int(source_register_match.group(1)) if source_register_match else None
        for entry in declarations:
            semantic = entry["semantic"]
            key = (int(semantic["usage"]), int(semantic["usage_index"]))
            outputs.setdefault(key, []).append({
                **entry,
                "source_output_register": source_register,
            })

    matches: list[dict[str, Any]] = []
    missing: list[str] = []
    component_errors: list[str] = []
    register_remaps: list[dict[str, Any]] = []
    ambiguous: list[str] = []

    for pixel_input in pixel_inputs:
        if pixel_input.get("instruction_modifier_bits", 0):
            ambiguous.append(
                f"{pixel_input['semantic']} uses DCL interpolation modifier bits "
                f"0x{pixel_input['instruction_modifier_bits']:02X}; interpolation mode "
                "requires explicit VS2/PS2 compatibility review"
            )
        key = semantic_key(pixel_input)
        semantic = pixel_input["semantic"]
        candidates = outputs.get(key, [])
        if not candidates:
            missing.append(f"pixel input {semantic} has no matching vertex output")
            continue
        if len(candidates) != 1:
            ambiguous.append(f"vertex output semantic {semantic} has {len(candidates)} declarations")
            continue

        output = candidates[0]
        available_mask = int(output.get("vs_2_0_component_mask") or 0)
        required_mask = int(pixel_input["component_mask"])
        source_mask = int(output.get("declared_component_mask") or 0)
        if required_mask & ~source_mask:
            component_errors.append(
                f"{semantic} requires .{format_mask(required_mask)} but vertex output "
                f"declares only .{format_mask(source_mask)}"
            )
        if required_mask & ~available_mask:
            component_errors.append(
                f"{semantic} requires .{format_mask(required_mask)} but its VS2 mapping "
                f"provides only .{format_mask(available_mask)}"
            )

        vs_type = output.get("vs_2_0_register_type")
        vs_index = output.get("vs_2_0_register_index")
        ps_target = map_ps2_input(key[0], key[1])
        vs_link_type = VS2_TO_PS2_LINK_TYPES.get(vs_type)
        mapping_matches = (
            vs_link_type is not None
            and ps_target is not None
            and (vs_link_type, vs_index) == ps_target
        )
        if not mapping_matches:
            register_remaps.append({
                "semantic": semantic,
                "vertex_vs2_register": {"type": vs_type, "index": vs_index},
                "pixel_ps2_register": (
                    {"type": ps_target[0], "index": ps_target[1]}
                    if ps_target else None
                ),
                "reason": "the current independent VS2/PS2 allocation plans do not link",
            })
        matches.append({
            "semantic": semantic,
            "pixel_input_register": pixel_input["register"],
            "pixel_component_mask": required_mask,
            "vertex_source_output_register": output.get("source_output_register"),
            "vertex_output_semantic": output.get("semantic"),
            "vertex_declared_component_mask": source_mask,
            "vertex_vs2_register_type": vs_type,
            "vertex_vs2_register_index": vs_index,
            "vertex_vs2_component_mask": available_mask,
            "pixel_ps2_register_type": ps_target[0] if ps_target else None,
            "pixel_ps2_register_index": ps_target[1] if ps_target else None,
            "vs2_ps2_link_registers_match": mapping_matches,
            "requires_vertex_pixel_relink": not mapping_matches,
            "pixel_interpolation_modifier": pixel_input["destination_modifier"],
            "pixel_instruction_modifier_bits": pixel_input["instruction_modifier_bits"],
        })

    # A pixel-shader semantic must be unique. Any VS output that is duplicated
    # or has a declaration rejected by the VS auditor is not treated as linked.
    return {
        "matched_semantics": matches,
        "missing_vertex_outputs": missing,
        "component_mask_errors": component_errors,
        "ambiguous_vertex_outputs": ambiguous,
        "register_relinks_required": register_remaps,
        "pixel_input_declaration_issues": [],
        "interface_matches": not (missing or component_errors or ambiguous),
        "independent_vs2_ps2_allocations_match": (
            not register_remaps and not missing and not component_errors and not ambiguous
        ),
    }

def validate_vertex_layout(
    vertex_result: dict[str, Any],
    draw: dict[str, Any],
) -> dict[str, Any]:
    inputs = vertex_result.get("input_declarations", {})
    declaration = draw.get("vertex_declaration")
    fvf = int(draw.get("fvf") or 0)
    streams = {int(item["stream"]): item for item in draw.get("stream_bindings", [])}
    reasons: list[str] = []
    warnings: list[str] = []
    elements: list[dict[str, Any]] = []
    source = "vertex_declaration"

    if declaration is not None:
        if declaration.get("unreadable"):
            reasons.append("active vertex declaration was marked unreadable in the capture")
        elements = list(declaration.get("elements") or [])
    elif fvf:
        source = "fvf"
        elements, fvf_errors = decode_fvf(fvf)
        reasons.extend(fvf_errors)
    else:
        return {
            "status": "unverified",
            "source": "missing",
            "matched_inputs": [],
            "reasons": ["draw has neither a captured vertex declaration nor a non-zero FVF"],
            "warnings": [],
        }

    by_semantic: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for element in elements:
        key = (int(element.get("usage", -1)), int(element.get("usage_index", 0)))
        by_semantic.setdefault(key, []).append(element)

    matched: list[dict[str, Any]] = []
    for register_text, expected in sorted(inputs.items(), key=lambda item: int(item[0])):
        register = int(register_text)
        usage = int(expected["usage"])
        usage_index = int(expected["usage_index"])
        key = (usage, usage_index)
        semantic = f"{expected.get('usage_name', USAGE_NAMES.get(usage, 'UNKNOWN'))}{usage_index}"
        matches = by_semantic.get(key, [])
        if not matches:
            reasons.append(f"VS input v{register} semantic {semantic} is absent from the vertex layout")
            continue
        if len(matches) > 1:
            reasons.append(f"vertex layout contains {len(matches)} elements for semantic {semantic}")
            continue

        element = matches[0]
        type_code = int(element.get("type", -1))
        type_info = DECL_TYPES.get(type_code)
        if type_info is None:
            reasons.append(f"vertex semantic {semantic} uses unsupported D3DDECLTYPE {type_code}")
            continue
        byte_size, stored_components, type_name = type_info
        # D3D9 vertex-declaration conversion defines missing components
        # (e.g. FLOAT3's w) with default values; do not mistake the memory
        # component count for the post-conversion shader input mask.
        stream_index = int(element.get("stream", 0))
        stream = streams.get(stream_index)
        if stream is None:
            reasons.append(f"vertex semantic {semantic} uses stream {stream_index}, which is not bound")
            continue
        stride = int(stream.get("stride", 0))
        element_offset = int(element.get("offset", 0))
        stream_offset = int(stream.get("offset", 0))
        if int(element.get("method", 0)) != 0:
            reasons.append(
                f"vertex semantic {semantic} uses D3DDECLMETHOD {element.get('method')}; "
                "non-default declaration methods need separate handling"
            )
        if stride <= 0 or element_offset + byte_size > stride:
            reasons.append(
                f"vertex semantic {semantic} occupies bytes {element_offset}.."
                f"{element_offset + byte_size - 1}, outside stream stride {stride}"
            )
        buffer = stream.get("buffer_descriptor")
        buffer_check = "not_recorded"
        if buffer:
            length = int(buffer.get("length_bytes", 0))
            if stream_offset + element_offset + byte_size > length:
                reasons.append(
                    f"vertex semantic {semantic} element exceeds the recorded vertex-buffer allocation"
                )
            else:
                buffer_check = "first_element_span_fits"
                warnings.append(
                    f"vertex semantic {semantic}: allocation check covers the first element only; "
                    "the full draw index/vertex range is not validated"
                )
        else:
            warnings.append(
                f"vertex buffer size for stream {stream_index} was not captured"
            )

        matched.append({
            "vs_input_register": register,
            "semantic": semantic,
            "stream": stream_index,
            "offset": element_offset,
            "stream_offset": stream_offset,
            "stride": stride,
            "d3d_decl_type": type_name,
            "stored_components": stored_components,
            "byte_size": byte_size,
            "buffer_span_check": buffer_check,
        })

    status = "verified_layout" if not reasons and not warnings else (
        "layout_with_warnings" if not reasons else "layout_mismatch_or_incomplete"
    )
    return {
        "status": status,
        "source": source,
        "matched_inputs": matched,
        "reasons": reasons,
        "warnings": warnings,
    }

def decode_fvf(fvf: int) -> tuple[list[dict[str, Any]], list[str]]:
    """Decode common D3D9 FVF layouts; unsupported beta/position variants fail closed."""
    errors: list[str] = []
    elements: list[dict[str, Any]] = []
    offset = 0
    position_code = fvf & 0x400E
    position_formats = {
        0x0002: (2, 12, "POSITION"),
        0x0004: (3, 16, "POSITIONT"),
        0x4002: (3, 16, "POSITION"),
        0x0006: (2, 12, "POSITION"),
        0x0008: (2, 12, "POSITION"),
        0x000A: (2, 12, "POSITION"),
        0x000C: (2, 12, "POSITION"),
        0x000E: (2, 12, "POSITION"),
    }
    if position_code not in position_formats:
        return [], [f"FVF 0x{fvf:08X} has an unsupported position format"]
    pos_type, pos_size, pos_name = position_formats[position_code]
    elements.append({
        "stream": 0, "offset": offset, "type": pos_type,
        "usage": 9 if pos_name == "POSITIONT" else 0, "usage_index": 0, "method": 0,
    })
    offset += pos_size

    if position_code in (0x0006, 0x0008, 0x000A, 0x000C, 0x000E):
        beta_count = (position_code - 0x0004) // 2
        last_beta = fvf & 0x9000
        if last_beta not in (0, 0x1000, 0x8000):
            errors.append(f"FVF 0x{fvf:08X} has an invalid LASTBETA encoding")
        weight_count = beta_count - (1 if last_beta else 0)
        if weight_count:
            if weight_count > 4:
                errors.append("FVF blend-weight count exceeds the supported FLOAT1..FLOAT4 layout")
            else:
                elements.append({
                    "stream": 0, "offset": offset, "type": weight_count - 1,
                    "usage": 1, "usage_index": 0, "method": 0,
                })
                offset += weight_count * 4
        if last_beta:
            elements.append({
                "stream": 0, "offset": offset, "type": 5,
                "usage": 2, "usage_index": 0, "method": 0,
            })
            offset += 4

    if fvf & 0x10:
        elements.append({
            "stream": 0, "offset": offset, "type": 2,
            "usage": 3, "usage_index": 0, "method": 0,
        })
        offset += 12
    if fvf & 0x20:
        elements.append({
            "stream": 0, "offset": offset, "type": 0,
            "usage": 4, "usage_index": 0, "method": 0,
        })
        offset += 4
    if fvf & 0x40:
        elements.append({
            "stream": 0, "offset": offset, "type": 4,
            "usage": 10, "usage_index": 0, "method": 0,
        })
        offset += 4
    if fvf & 0x80:
        elements.append({
            "stream": 0, "offset": offset, "type": 4,
            "usage": 10, "usage_index": 1, "method": 0,
        })
        offset += 4

    texture_count = (fvf >> 8) & 0xF
    if texture_count > 8:
        errors.append(f"FVF texture-coordinate count {texture_count} exceeds eight")
    for index in range(min(texture_count, 8)):
        size_code = (fvf >> (16 + 2 * index)) & 0x3
        components = {0: 2, 1: 3, 2: 4, 3: 1}[size_code]
        type_code = components - 1
        byte_size = (1, 2, 3, 4)[components - 1] * 4
        elements.append({
            "stream": 0, "offset": offset, "type": type_code,
            "usage": 5, "usage_index": index, "method": 0,
        })
        offset += byte_size

    known_mask = 0x400E | 0x10 | 0x20 | 0x40 | 0x80 | 0x0F00 | 0x9000 | 0xFFFF0000
    if fvf & ~known_mask:
        errors.append(f"FVF 0x{fvf:08X} contains flags outside the supported subset")
    if (fvf & 0x9000) and position_code not in (0x0006, 0x0008, 0x000A, 0x000C, 0x000E):
        errors.append("FVF LASTBETA flag is present without an XYZB position format")
    return elements, errors

def audit_draw(
    draw: dict[str, Any],
    captures: dict[str, list[tuple[Path, bytes, str, int, int]]],
    caps: dict[str, Any] | None,
    stage_cache: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    vs = draw.get("vertex_shader")
    ps = draw.get("pixel_shader")
    result: dict[str, Any] = {
        "sequence": draw.get("seq"),
        "frame": draw.get("frame"),
        "draw_kind": draw.get("kind"),
        "vertex_shader_hash": vs.get("hash") if vs else None,
        "pixel_shader_hash": ps.get("hash") if ps else None,
        "status": "capture_incomplete",
        "reasons": [],
        "warnings": [],
    }
    if not vs or not ps:
        result["reasons"].append("draw does not have both a resolved programmable VS and PS object")
        return result

    vs_hash, ps_hash = str(vs.get("hash", "")).upper(), str(ps.get("hash", "")).upper()
    vs_capture = select_capture(vs, "VS", captures)
    ps_capture = select_capture(ps, "PS", captures)
    if not vs_capture or not ps_capture:
        missing = []
        if not vs_capture:
            missing.append(f"vertex bytecode capture missing for hash {vs_hash or 'unknown'}")
        if not ps_capture:
            missing.append(f"pixel bytecode capture missing for hash {ps_hash or 'unknown'}")
        result["reasons"].extend(missing)
        return result

    vs_path, vs_bytes = vs_capture
    ps_path, ps_bytes = ps_capture
    vs_profile = profile_from_bytes(vs_bytes)
    ps_profile = profile_from_bytes(ps_bytes)
    result["vertex_capture"] = {"file": vs_path.name, "profile": f"vs_{vs_profile[1]}_{vs_profile[2]}"}
    result["pixel_capture"] = {"file": ps_path.name, "profile": f"ps_{ps_profile[1]}_{ps_profile[2]}"}

    if vs_profile[1:] != (3, 0) or ps_profile[1:] != (3, 0):
        result["status"] = "not_a_vs3_ps3_pair"
        result["reasons"].append("this paired audit currently targets vs_3_0 + ps_3_0 draw pairs")
        return result

    cache_key = (vs_hash, ps_hash)
    cached = stage_cache.get(cache_key)
    if cached is None:
        vs_result = audit_vs3_to_vs2.audit_vs3_bytes(vs_bytes)
        ps_result = audit_sm3_to_sm2.audit_and_lower_ps3(ps_bytes)
        ps_inputs, ps_parse_reasons = parse_ps_inputs(ps_bytes)
        cached = {
            "vertex": vs_result,
            "pixel": ps_result,
            "pixel_inputs": ps_inputs,
            "pixel_parse_reasons": ps_parse_reasons,
        }
        stage_cache[cache_key] = cached
    vs_result = cached["vertex"]
    ps_result = cached["pixel"]
    result["vertex_stage"] = {
        "structural_candidate": bool(vs_result.get("structural_candidate_for_manual_lowering")),
        "instruction_slots": vs_result.get("instruction_slots"),
        "instruction_slot_limit": vs_result.get("instruction_slot_limit"),
        "reasons": vs_result.get("reasons", []),
    }
    result["pixel_stage"] = {
        "structural_candidate": bool(ps_result.get("eligible")),
        "arithmetic_slots": ps_result.get("arithmetic_slots"),
        "texture_slots": ps_result.get("texture_slots"),
        "declared_samplers": ps_result.get("declared_samplers", []),
        "used_samplers": ps_result.get("used_samplers", []),
        "reasons": ps_result.get("reasons", []),
    }
    if cached["pixel_parse_reasons"]:
        result["reasons"].extend(cached["pixel_parse_reasons"])

    interface = audit_shader_interface(vs_result, ps_result, cached["pixel_inputs"])
    result["interface"] = interface
    layout = validate_vertex_layout(vs_result, draw)
    result["vertex_input_layout"] = layout
    if layout["reasons"]:
        result["reasons"].extend(layout["reasons"])
    result["warnings"].extend(layout["warnings"])

    declared_samplers = set(ps_result.get("declared_samplers", []))
    used_samplers = set(ps_result.get("used_samplers", []))
    required_samplers = sorted(declared_samplers | used_samplers)
    bound_textures = {
        int(binding["stage"]): binding
        for binding in draw.get("texture_bindings", [])
        if binding.get("object") is not None
    }
    missing_samplers = [
        sampler for sampler in required_samplers if sampler not in bound_textures
    ]
    result["sampler_bindings"] = {
        "required_sampler_stages": required_samplers,
        "bound_texture_stages": sorted(bound_textures),
        "missing_sampler_stages": missing_samplers,
    }
    if missing_samplers:
        result["reasons"].append(
            "pixel shader sampler(s) lack a captured non-null texture binding: "
            + ", ".join(f"s{item}" for item in missing_samplers)
        )

    targets = draw.get("render_targets", [])
    active_targets = [item for item in targets if item.get("object") is not None]
    result["render_targets"] = [
        {
            "slot": item.get("index"),
            "width": item.get("width"),
            "height": item.get("height"),
            "format": item.get("format"),
        }
        for item in active_targets
    ]
    max_rts = (
        int(caps.get("max_simultaneous_render_targets", -1))
        if caps else -1
    )
    result["device_limits"] = {
        "max_simultaneous_render_targets": max_rts,
        "active_render_targets": len(active_targets),
    }
    if max_rts >= 0 and len(active_targets) > max_rts:
        result["reasons"].append(
            f"draw binds {len(active_targets)} render targets but the captured device cap is {max_rts}"
        )
    if not active_targets:
        result["warnings"].append("no active render-target snapshot was recorded for this draw")

    result["state_capture"] = {
        "sampler_state_fingerprint_present": bool(draw.get("sampler_state_hash")),
        "render_state_fingerprint_present": bool(draw.get("render_state_hash")),
        "texture_stage_fingerprint_present": bool(draw.get("texture_stage_state_hash")),
        "full_individual_state_values_available": False,
        "note": (
            "The current log stores state fingerprints/counts, not each blend, depth, "
            "alpha-test or sampler-state value. Those state semantics are not certified."
        ),
    }
    if draw.get("sampler_state_count", 0) == 0:
        result["warnings"].append("no sampler-state fingerprint was captured")
    if draw.get("render_state_count", 0) == 0:
        result["warnings"].append("no render-state fingerprint was captured")
    result["warnings"].append(
        "individual blend, depth, alpha-test and sampler-state values are not captured; "
        "render-state compatibility still requires manual review"
    )

    if not vs_result.get("structural_candidate_for_manual_lowering"):
        result["reasons"].append("vertex shader is outside the currently audited VS2 subset")
    if not ps_result.get("eligible"):
        result["reasons"].append("pixel shader is outside the currently audited PS2 subset")
    if not interface["interface_matches"]:
        result["reasons"].append("original VS3 output / PS3 input semantic interface does not match")
    if not interface["independent_vs2_ps2_allocations_match"]:
        result["warnings"].append(
            "the current independent SM2 register allocation requires a paired relink/rewrite"
        )
    if layout["status"] != "verified_layout":
        result["warnings"].append("vertex input layout is not fully verified")
    if not caps:
        result["warnings"].append("no device capability snapshot is available")
    else:
        vertex_cap = caps.get("vertex_shader")
        pixel_cap = caps.get("pixel_shader")
        if not vertex_cap or not pixel_cap:
            result["warnings"].append("captured shader-model capability fields are incomplete")
        else:
            result["device_limits"]["vertex_shader_profile"] = vertex_cap.get("profile")
            result["device_limits"]["pixel_shader_profile"] = pixel_cap.get("profile")
            for stage, capability in (("vertex", vertex_cap), ("pixel", pixel_cap)):
                major = int(capability.get("major", 0))
                minor = int(capability.get("minor", 0))
                if (major, minor) < (2, 0):
                    result["reasons"].append(
                        f"captured device reports {stage}-shader model {major}.{minor}; "
                        "the fallback path requires at least shader model 2.0"
                    )

        vs_temp_limit = int(caps.get("vs20_temps", -1))
        vs_temps = vs_result.get("registers", {}).get("temp", [])
        if vs_temp_limit >= 0 and vs_temps and max(vs_temps) >= vs_temp_limit:
            result["reasons"].append(
                f"vertex shader uses r{max(vs_temps)} but the captured VS2 temporary-register "
                f"limit is {vs_temp_limit}"
            )
        ps_temp_limit = int(caps.get("ps20_temps", -1))
        ps_highest_temp = max_ps_temp_register(ps_bytes)
        if ps_temp_limit >= 0 and ps_highest_temp >= ps_temp_limit:
            result["reasons"].append(
                f"pixel shader uses r{ps_highest_temp} but the captured PS2 temporary-register "
                f"limit is {ps_temp_limit}"
            )
        ps_slot_limit = int(caps.get("ps20_instruction_slots", -1))
        ps_total_slots = int(ps_result.get("arithmetic_slots", 0)) + int(ps_result.get("texture_slots", 0))
        result["device_limits"]["ps20_temporary_registers"] = ps_temp_limit
        result["device_limits"]["ps20_instruction_slots"] = ps_slot_limit
        result["device_limits"]["pixel_shader_instruction_slots_used"] = ps_total_slots
        if ps_slot_limit >= 0 and ps_total_slots > ps_slot_limit:
            result["reasons"].append(
                f"pixel shader uses {ps_total_slots} instruction slots but the captured "
                f"PS2 limit is {ps_slot_limit}"
            )

    # Classification is deliberately conservative. "Candidate" is not a claim
    # of bytecode generation, driver acceptance or visual equivalence.
    if result["reasons"]:
        result["status"] = "requires_rewrite_or_render_path_change"
    elif not interface["independent_vs2_ps2_allocations_match"]:
        result["status"] = "requires_paired_interface_relink"
    elif layout["status"] != "verified_layout" or not caps:
        result["status"] = "capture_incomplete"
    elif result["warnings"]:
        result["status"] = "manual_render_state_review"
    else:
        result["status"] = "pair_candidate_for_manual_lowering"
    return result

def audit_log(
    log_path: Path,
    capture_directory: Path,
) -> dict[str, Any]:
    draw_report = analyze_log(log_path)
    captures = index_captures(capture_directory)
    caps_list = draw_report.get("device_capability_snapshots", [])
    caps = caps_list[-1] if caps_list else None
    stage_cache: dict[tuple[str, str], dict[str, Any]] = {}
    draws = [
        audit_draw(draw, captures, caps, stage_cache)
        for draw in draw_report.get("draw_calls", [])
    ]
    counts = Counter(item["status"] for item in draws)
    return {
        "schema_version": 1,
        "input_log": str(log_path),
        "capture_directory": str(capture_directory),
        "draw_calls_audited": len(draws),
        "unique_shader_pairs_audited": len(stage_cache),
        "capture_files_indexed": sum(len(items) for items in captures.values()),
        "status_counts": dict(sorted(counts.items())),
        "draw_calls": draws,
        "scope_note": (
            "Read-only static pairing audit. A pair candidate is only a manual-lowering "
            "candidate; no VS2/PS2 bytecode is emitted and no driver acceptance, visual "
            "equivalence, gameplay correctness or FPS is established. Per-draw render, "
            "depth, texture and buffer telemetry is observational. The current capture "
            "does not include individual blend/depth/alpha/sampler state values."
        ),
    }

def _self_test() -> None:
    def vs_dcl(usage: int, register_type: int, register: int, index: int = 0,
               mask: int = 0xF) -> list[int]:
        declaration = 0x80000000 | (usage & 0xF) | ((index & 0xF) << 16)
        return audit_vs3_to_vs2.make_instruction(
            audit_vs3_to_vs2.OP_DCL,
            declaration,
            audit_vs3_to_vs2.make_dest_token(register_type, register, mask),
        )

    def ps_dcl(usage: int, register: int, index: int = 0,
               mask: int = 0xF) -> None:
        audit_sm3_to_sm2.emit_instruction(
            ps_words,
            audit_sm3_to_sm2.OP_DCL,
            (usage & 0xF) | ((index & 0xF) << 16),
            audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_INPUT, register, mask),
        )

    vs_words = [audit_vs3_to_vs2.VS3_VERSION]
    vs_words.extend(vs_dcl(0, audit_vs3_to_vs2.REG_INPUT, 0))
    vs_words.extend(vs_dcl(0, audit_vs3_to_vs2.REG_OUTPUT, 0))
    vs_words.extend(vs_dcl(5, audit_vs3_to_vs2.REG_OUTPUT, 1, index=0))
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
    vs_bytes = struct.pack("<" + "I" * len(vs_words), *vs_words)

    ps_words = [audit_sm3_to_sm2.PS3_VERSION]
    ps_dcl(5, 0, index=0)
    audit_sm3_to_sm2.emit_instruction(
        ps_words, audit_sm3_to_sm2.OP_MOV,
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_TEMP, 0),
        audit_sm3_to_sm2.make_source(audit_sm3_to_sm2.REG_INPUT, 0),
    )
    audit_sm3_to_sm2.emit_instruction(
        ps_words, audit_sm3_to_sm2.OP_MOV,
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_COLOROUT, 0),
        audit_sm3_to_sm2.make_source(audit_sm3_to_sm2.REG_TEMP, 0),
    )
    ps_words.append(audit_sm3_to_sm2.OP_END)
    ps_bytes = struct.pack("<" + "I" * len(ps_words), *ps_words)

    vs_result = audit_vs3_to_vs2.audit_vs3_bytes(vs_bytes)
    ps_result = audit_sm3_to_sm2.audit_and_lower_ps3(ps_bytes)
    ps_inputs, parse_reasons = parse_ps_inputs(ps_bytes)
    assert vs_result["structural_candidate_for_manual_lowering"], vs_result["reasons"]
    assert ps_result["eligible"], ps_result["reasons"]
    assert not parse_reasons
    interface = audit_shader_interface(vs_result, ps_result, ps_inputs)
    assert interface["interface_matches"]
    assert interface["independent_vs2_ps2_allocations_match"]

    draw = {
        "vertex_declaration": {
            "elements": [
                {"stream": 0, "offset": 0, "type": 2, "method": 0, "usage": 0, "usage_index": 0},
                {"stream": 0, "offset": 12, "type": 1, "method": 0, "usage": 5, "usage_index": 0},
            ]
        },
        "fvf": 0,
        "stream_bindings": [{
            "stream": 0, "offset": 0, "stride": 20,
            "buffer_descriptor": {"length_bytes": 4096},
        }],
    }
    layout = validate_vertex_layout(vs_result, draw)
    assert layout["status"] == "verified_layout", layout

    # Sparse TEXCOORD1 is compacted to VS2 oT0, while the current PS2 lowerer
    # maps TEXCOORD1 to t1. Original SM3 semantics match, but the pair needs a
    # shared allocation/relink pass.
    sparse_vs_words = [audit_vs3_to_vs2.VS3_VERSION]
    sparse_vs_words.extend(vs_dcl(0, audit_vs3_to_vs2.REG_INPUT, 0))
    sparse_vs_words.extend(vs_dcl(0, audit_vs3_to_vs2.REG_OUTPUT, 0))
    sparse_vs_words.extend(vs_dcl(5, audit_vs3_to_vs2.REG_OUTPUT, 1, index=1))
    sparse_vs_words.extend(audit_vs3_to_vs2.make_instruction(
        1, audit_vs3_to_vs2.make_dest_token(audit_vs3_to_vs2.REG_OUTPUT, 0),
        audit_vs3_to_vs2.make_source_token(audit_vs3_to_vs2.REG_INPUT, 0)))
    sparse_vs_words.extend(audit_vs3_to_vs2.make_instruction(
        1, audit_vs3_to_vs2.make_dest_token(audit_vs3_to_vs2.REG_OUTPUT, 1),
        audit_vs3_to_vs2.make_source_token(audit_vs3_to_vs2.REG_INPUT, 0)))
    sparse_vs_words.append(audit_vs3_to_vs2.OP_END)
    sparse_vs = audit_vs3_to_vs2.audit_vs3_bytes(
        struct.pack("<" + "I" * len(sparse_vs_words), *sparse_vs_words)
    )
    sparse_ps_words = [audit_sm3_to_sm2.PS3_VERSION]
    sparse_ps_words.extend([
        (2 << 24) | audit_sm3_to_sm2.OP_DCL,
        (5 | (1 << 16)),
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_INPUT, 0),
    ])
    audit_sm3_to_sm2.emit_instruction(
        sparse_ps_words, audit_sm3_to_sm2.OP_MOV,
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_TEMP, 0),
        audit_sm3_to_sm2.make_source(audit_sm3_to_sm2.REG_INPUT, 0))
    audit_sm3_to_sm2.emit_instruction(
        sparse_ps_words, audit_sm3_to_sm2.OP_MOV,
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_COLOROUT, 0),
        audit_sm3_to_sm2.make_source(audit_sm3_to_sm2.REG_TEMP, 0))
    sparse_ps_words.append(audit_sm3_to_sm2.OP_END)
    sparse_ps = struct.pack("<" + "I" * len(sparse_ps_words), *sparse_ps_words)
    sparse_ps_audit = audit_sm3_to_sm2.audit_and_lower_ps3(sparse_ps)
    sparse_inputs, _ = parse_ps_inputs(sparse_ps)
    sparse_interface = audit_shader_interface(sparse_vs, sparse_ps_audit, sparse_inputs)
    assert sparse_interface["interface_matches"]
    assert not sparse_interface["independent_vs2_ps2_allocations_match"]
    assert sparse_interface["register_relinks_required"]

    packed_words = [audit_sm3_to_sm2.PS3_VERSION]
    audit_sm3_to_sm2.emit_instruction(
        packed_words, audit_sm3_to_sm2.OP_DCL,
        5 | (0 << 16),
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_INPUT, 0, 0x1),
    )
    audit_sm3_to_sm2.emit_instruction(
        packed_words, audit_sm3_to_sm2.OP_DCL,
        5 | (1 << 16),
        audit_sm3_to_sm2.make_register(audit_sm3_to_sm2.REG_INPUT, 0, 0x2),
    )
    packed_words.append(audit_sm3_to_sm2.OP_END)
    packed_inputs, packed_reasons = parse_ps_inputs(
        struct.pack("<" + "I" * len(packed_words), *packed_words)
    )
    assert len(packed_inputs) == 2
    assert any("packs multiple semantics" in reason for reason in packed_reasons)

    fvf_elements, fvf_errors = decode_fvf(0x002 | 0x200)
    assert not fvf_errors
    assert [(x["usage"], x["usage_index"]) for x in fvf_elements] == [
        (0, 0), (5, 0), (5, 1)
    ]

    # Exercise end-to-end draw correlation using a synthetic log-shaped draw
    # record and matching captured bytecode files (not GTA IV captures).
    with tempfile.TemporaryDirectory() as temporary:
        capture_root = Path(temporary)
        vs_hash = fnv1a64(vs_bytes)
        ps_hash = fnv1a64(ps_bytes)
        (capture_root / f"VS_3_0_{vs_hash}.bin").write_bytes(vs_bytes)
        (capture_root / f"PS_3_0_{ps_hash}.bin").write_bytes(ps_bytes)
        captures = index_captures(capture_root)
        draw_record = {
            "seq": 1,
            "frame": 1,
            "kind": "DrawIndexedPrimitive",
            "vertex_shader": {"hash": vs_hash, "profile": "vs_3_0"},
            "pixel_shader": {"hash": ps_hash, "profile": "ps_3_0"},
            "vertex_declaration": draw["vertex_declaration"],
            "fvf": 0,
            "stream_bindings": draw["stream_bindings"],
            "texture_bindings": [],
            "render_targets": [{
                "index": 0, "object": "1000", "width": 640,
                "height": 480, "format": 21,
            }],
            "sampler_state_hash": "abcd",
            "sampler_state_count": 1,
            "render_state_hash": "1234",
            "render_state_count": 1,
            "texture_stage_state_hash": "5678",
            "texture_stage_state_count": 1,
        }
        capability_snapshot = {
            "vertex_shader": {"profile": "vs_2_0", "major": 2, "minor": 0},
            "pixel_shader": {"profile": "ps_2_0", "major": 2, "minor": 0},
            "max_simultaneous_render_targets": 1,
            "vs20_temps": 12,
            "ps20_temps": 12,
            "ps20_instruction_slots": 96,
        }
        integrated = audit_draw(
            draw_record, captures, capability_snapshot, {}
        )
        assert integrated["interface"]["interface_matches"], integrated
        assert integrated["interface"]["independent_vs2_ps2_allocations_match"], integrated
        assert integrated["vertex_input_layout"]["source"] == "vertex_declaration"
        assert integrated["sampler_bindings"]["missing_sampler_stages"] == []
        assert integrated["device_limits"]["active_render_targets"] == 1
        assert integrated["pixel_stage"]["structural_candidate"]
        assert integrated["vertex_stage"]["structural_candidate"]
        assert integrated["status"] == "capture_incomplete", integrated

    print("PASS: paired VS3/PS3 interface, vertex-layout and draw-level audit self-tests")

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log_file", nargs="?", type=Path)
    parser.add_argument("capture_directory", nargs="?", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if args.log_file is None or args.capture_directory is None:
        parser.error("log_file and capture_directory are required unless --self-test is used")
    if not args.log_file.is_file():
        print(f"ERROR: log file not found: {args.log_file}", file=sys.stderr)
        return 2
    try:
        report = audit_log(args.log_file, args.capture_directory)
    except (OSError, ValueError, KeyError, struct.error) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"Paired audit: {report['draw_calls_audited']} draw(s), "
        f"{report['unique_shader_pairs_audited']} unique shader pair(s), "
        f"{report['capture_files_indexed']} capture(s)"
    )
    for status, count in report["status_counts"].items():
        print(f"  {status}: {count}")
    print("NOTE: static triage only; this tool does not emit shaders or measure FPS.")
    if args.report:
        print(f"JSON report: {args.report}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
