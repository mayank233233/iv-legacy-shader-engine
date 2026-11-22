#!/usr/bin/env python3
"""Read-only capability/shader gate analysis for IVLegacy.log.

This tool does not infer that GTA IV's gate was bypassed. It correlates the
caps returned by D3D9 with shader profiles and device-creation events, and
labels the startup ordering as evidence or as inconclusive.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

CAPS_RE = re.compile(
    r"D3D9_GET_DEVICE_CAPS .*?\bVS=0x([0-9A-Fa-f]+)\s+PS=0x([0-9A-Fa-f]+)"
    r".*?MaxSimTextures=(\d+).*?MaxRTs=(\d+).*?MaxVSConst=(\d+)"
    r".*?PS20Temps=(\d+).*?PS20Slots=(\d+)"
)
SHADER_RE = re.compile(
    r"CREATE_(VERTEX|PIXEL)_SHADER profile=(VS|PS)_(\d+)_(\d+).*?hr=0x([0-9A-Fa-f]+)"
)
DEVICE_REQUEST_RE = re.compile(r"D3D9_CREATE_DEVICE_REQUEST")
DEVICE_RESULT_RE = re.compile(r"D3D9_CREATE_DEVICE_RESULT hr=0x([0-9A-Fa-f]+)")
FORMAT_RE = re.compile(r"D3D9_CHECK_DEVICE_FORMAT .*?hr=0x([0-9A-Fa-f]+)")
DEPTH_RE = re.compile(r"D3D9_CHECK_DEPTH_MATCH .*?hr=0x([0-9A-Fa-f]+)")


def shader_version(value: int) -> tuple[int, int] | None:
    """Decode D3DVS_VERSION/D3DPS_VERSION tokens (marker: 0xFFFE/0xFFFF)."""
    marker = (value >> 16) & 0xFFFF
    if marker not in (0xFFFE, 0xFFFF):
        return None
    return ((value >> 8) & 0xFF, value & 0xFF)


def decode_hr(value: str) -> bool:
    return (int(value, 16) & 0x80000000) == 0


def analyze(log_text: str) -> dict:
    lines = log_text.splitlines()
    caps = []
    shaders = []
    device_requests = []
    device_results = []
    format_results = []
    depth_results = []

    for number, line in enumerate(lines, 1):
        m = CAPS_RE.search(line)
        if m:
            vs_raw, ps_raw, textures, rts, vsconst, pstemps, psslots = m.groups()
            caps.append({
                "line": number,
                "vertex_shader_version_raw": "0x" + vs_raw.upper(),
                "pixel_shader_version_raw": "0x" + ps_raw.upper(),
                "vertex_shader_version": shader_version(int(vs_raw, 16)),
                "pixel_shader_version": shader_version(int(ps_raw, 16)),
                "max_simultaneous_textures": int(textures),
                "max_render_targets": int(rts),
                "max_vertex_shader_constants": int(vsconst),
                "ps20_temps": int(pstemps),
                "ps20_instruction_slots": int(psslots),
            })
        m = SHADER_RE.search(line)
        if m:
            api_stage, token_stage, major, minor, hr = m.groups()
            shaders.append({
                "line": number,
                "stage": api_stage.lower(),
                "token_stage": token_stage,
                "profile": f"{token_stage.lower()}_{major}_{minor}",
                "succeeded": decode_hr(hr),
                "hr": "0x" + hr.upper(),
            })
        if DEVICE_REQUEST_RE.search(line):
            device_requests.append(number)
        m = DEVICE_RESULT_RE.search(line)
        if m:
            device_results.append({"line": number, "succeeded": decode_hr(m.group(1)),
                                   "hr": "0x" + m.group(1).upper()})
        m = FORMAT_RE.search(line)
        if m:
            format_results.append({"line": number, "succeeded": decode_hr(m.group(1)),
                                   "hr": "0x" + m.group(1).upper()})
        m = DEPTH_RE.search(line)
        if m:
            depth_results.append({"line": number, "succeeded": decode_hr(m.group(1)),
                                  "hr": "0x" + m.group(1).upper()})

    latest_caps = caps[-1] if caps else None
    unsupported = []
    if latest_caps:
        for shader in shaders:
            version = tuple(int(x) for x in shader["profile"].split("_")[1:])
            cap_version = (latest_caps["vertex_shader_version"] if shader["stage"] == "vertex"
                           else latest_caps["pixel_shader_version"])
            if cap_version and version > tuple(cap_version):
                unsupported.append({**shader, "reported_cap": list(cap_version)})

    if not caps:
        startup_assessment = "inconclusive_no_d3d9_caps_record"
    elif not device_requests:
        startup_assessment = "caps_seen_but_no_device_creation_request"
    elif device_requests[0] < caps[0]["line"]:
        startup_assessment = "device_creation_requested_before_first_caps_record"
    else:
        startup_assessment = "device_creation_request_observed_after_caps"

    return {
        "schema": "ivlegacy-capability-gap-report-v1",
        "log_lines": len(lines),
        "caps_records": caps,
        "shader_creation_records": shaders,
        "shader_profiles_above_reported_caps": unsupported,
        "device_creation_requests": device_requests,
        "device_creation_results": device_results,
        "format_check_failures": [x for x in format_results if not x["succeeded"]],
        "depth_match_failures": [x for x in depth_results if not x["succeeded"]],
        "startup_assessment": startup_assessment,
        "interpretation": (
            "A profile above the reported cap cannot be passed through unchanged. "
            "A successful SM2 fallback must be observed separately; this report does "
            "not prove a game gate was bypassed or that rendering is correct."
        ),
    }


def self_test() -> None:
    sample = """D3D9_GET_DEVICE_CAPS adapter=0 type=1 VS=0xFFFE0200 PS=0xFFFF0200 MaxSimTextures=8 MaxTextureStages=8 MaxRTs=1 MaxVSConst=256 VS20Temps=12 VS20DynamicFlow=0 VS20StaticFlow=1 PS20Caps=0x00000000 PS20Temps=12 PS20Slots=96 PS20DynamicFlow=0 PS20StaticFlow=0
D3D9_CREATE_DEVICE_REQUEST adapter=0
D3D9_CREATE_DEVICE_RESULT hr=0x00000000
CREATE_VERTEX_SHADER profile=VS_3_0 token=0xFFFE0300 hr=0x8876086A
CREATE_PIXEL_SHADER profile=PS_2_0 token=0xFFFF0200 hr=0x00000000
"""
    report = analyze(sample)
    assert report["startup_assessment"] == "device_creation_request_observed_after_caps"
    assert len(report["shader_profiles_above_reported_caps"]) == 1
    assert report["shader_profiles_above_reported_caps"][0]["profile"] == "vs_3_0"
    assert len(report["device_creation_results"]) == 1
    assert report["device_creation_results"][0]["succeeded"]
    print("capability-gap-audit self-test: PASS")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path, help="IVLegacy.log to analyze")
    parser.add_argument("--json", type=Path, help="write JSON report to this path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if not args.log:
        parser.error("provide a log path or --self-test")
    report = analyze(args.log.read_text(encoding="utf-8", errors="replace"))
    rendered = json.dumps(report, indent=2)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
