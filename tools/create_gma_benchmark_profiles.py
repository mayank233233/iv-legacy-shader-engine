#!/usr/bin/env python3
"""Generate clean, one-cache-at-a-time IVLegacy benchmark INI profiles.

The input INI is copied, not modified. Other sections and unrelated settings
are preserved. Diagnostic capture and shader fallback features are forced off.
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*(?:[;#].*)?$")
ASSIGNMENT_RE = re.compile(r"^(\s*)([^=;#]+?)\s*=(.*)$")

COMMON_OVERRIDES = {
    "StrictGTAIV100": "1",
    "StateCacheReportFrames": "120",
    "CaptureDrawTelemetry": "0",
    "CaptureShaderBytecode": "0",
    "CaptureShaderConstants": "0",
    "EnableShaderFallbacks": "0",
    "EnableFrameProfiler": "1",
    "FrameProfilerWindowFrames": "120",
}

CACHE_KEYS = (
    "EnableRedundantStateCache",
    "EnableBindingCache",
    "EnableShaderConstantCache",
)
CACHE_PROFILES = {
    "baseline": ("0", "0", "0"),
    "state-cache": ("1", "0", "0"),
    "binding-cache": ("0", "1", "0"),
    "shader-constant-cache": ("0", "0", "1"),
    "all-caches": ("1", "1", "1"),
}


def _split_lines(text: str) -> tuple[list[str], str, bool]:
    newline = "\r\n" if "\r\n" in text else "\n"
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    had_final_newline = normalized.endswith("\n")
    lines = normalized.split("\n")
    if had_final_newline:
        lines.pop()
    return lines, newline, had_final_newline


def _render_lines(lines: list[str], newline: str, final_newline: bool) -> str:
    rendered = newline.join(lines)
    return rendered + (newline if final_newline else "")


def read_general_values(text: str) -> dict[str, str]:
    lines, _, _ = _split_lines(text)
    sections = [
        (index, match.group(1).strip().casefold())
        for index, line in enumerate(lines)
        if (match := SECTION_RE.match(line))
    ]
    general = [item for item in sections if item[1] == "general"]
    if len(general) != 1:
        raise ValueError("Expected exactly one [General] section")
    start = general[0][0]
    end = next((index for index, _ in sections if index > start), len(lines))
    values: dict[str, str] = {}
    for line in lines[start + 1:end]:
        match = ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key = match.group(2).strip().casefold()
        if key in values:
            raise ValueError("Duplicate [General] setting: " + key)
        values[key] = match.group(3).strip()
    return values


def rewrite_general_section(text: str, overrides: dict[str, str]) -> str:
    """Apply case-insensitive [General] overrides without changing other sections."""
    lines, newline, final_newline = _split_lines(text)
    sections = [
        (index, match.group(1).strip().casefold())
        for index, line in enumerate(lines)
        if (match := SECTION_RE.match(line))
    ]
    general = [item for item in sections if item[1] == "general"]
    if len(general) > 1:
        raise ValueError("Input INI contains multiple [General] sections")

    if general:
        start = general[0][0]
    else:
        if lines and lines[-1].strip():
            lines.append("")
        start = len(lines)
        lines.append("[General]")
        final_newline = True

    canonical = {key.casefold(): (key, value) for key, value in overrides.items()}
    found: set[str] = set()
    result: list[str] = []
    in_general = False

    for index, line in enumerate(lines):
        if index == start:
            in_general = True
            result.append(line)
            continue
        section_match = SECTION_RE.match(line)
        if section_match:
            in_general = section_match.group(1).strip().casefold() == "general"
            result.append(line)
            continue
        if not in_general:
            result.append(line)
            continue
        match = ASSIGNMENT_RE.match(line)
        if not match:
            result.append(line)
            continue
        folded = match.group(2).strip().casefold()
        if folded not in canonical:
            result.append(line)
            continue
        if folded in found:
            # Remove duplicate copies of a setting controlled by this tool.
            continue
        key, value = canonical[folded]
        result.append(match.group(1) + key + "=" + value)
        found.add(folded)

    missing = [
        key + "=" + value
        for key, value in overrides.items()
        if key.casefold() not in found
    ]
    section_result_end = next(
        (
            index for index in range(start + 1, len(result))
            if SECTION_RE.match(result[index])
        ),
        len(result),
    )
    result[section_result_end:section_result_end] = missing

    rendered = _render_lines(result, newline, final_newline)
    values = read_general_values(rendered)
    for key, value in overrides.items():
        if values.get(key.casefold()) != value:
            raise ValueError("Failed to apply [General] override " + key)
    return rendered


def build_profiles(base_text: str) -> dict[str, str]:
    profiles: dict[str, str] = {}
    for name, bits in CACHE_PROFILES.items():
        overrides = dict(COMMON_OVERRIDES)
        overrides.update(dict(zip(CACHE_KEYS, bits)))
        profiles[name] = rewrite_general_section(base_text, overrides)
    return profiles


def self_test() -> None:
    base = (
        "[Display]\r\nWidth=800\r\nHeight=600\r\n"
        "[General]\r\nCustomSetting=keep\r\n"
        "EnableRedundantStateCache=1\r\n"
        "EnableRedundantStateCache=0\r\n"
        "CaptureDrawTelemetry=1\r\n"
        "[GMAEdition]\r\nEnableFrameProfiler=77\r\nLowResEnabled=1\r\n"
    )
    profiles = build_profiles(base)
    assert set(profiles) == set(CACHE_PROFILES)
    for name, profile in profiles.items():
        values = read_general_values(profile)
        assert tuple(values[key.casefold()] for key in CACHE_KEYS) == CACHE_PROFILES[name]
        for key, value in COMMON_OVERRIDES.items():
            assert values[key.casefold()] == value
        assert values["customsetting"] == "keep"
        assert "Width=800" in profile and "Height=600" in profile
        assert "[GMAEdition]\r\nEnableFrameProfiler=77\r\nLowResEnabled=1" in profile
        assert profile.count("EnableRedundantStateCache=") == 1
        assert "\r\n" in profile and "\n" not in profile.replace("\r\n", "")
    no_general = build_profiles("[Other]\nKeep=1\n")
    assert all("[General]" in value and "Keep=1" in value for value in no_general.values())
    print("GMA benchmark profile generator self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_ini", nargs="?", type=Path, help="existing IVLegacy.ini")
    parser.add_argument("--out-dir", type=Path, help="directory for generated profiles")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.input_ini is None or args.out_dir is None:
        parser.error("input_ini and --out-dir are required unless --self-test is used")
    if not args.input_ini.is_file():
        parser.error("input INI does not exist: " + str(args.input_ini))

    try:
        raw = args.input_ini.read_bytes()
        utf8_bom = raw.startswith(b"\xef\xbb\xbf")
        base_text = raw.decode("utf-8-sig")
        profiles = build_profiles(base_text)
        args.out_dir.mkdir(parents=True, exist_ok=True)
        encoding = "utf-8-sig" if utf8_bom else "utf-8"
        for name, content in profiles.items():
            output = args.out_dir / ("gma-" + name + ".ini")
            if output.resolve() == args.input_ini.resolve():
                raise ValueError("Output path would overwrite the input INI")
            with output.open("w", encoding=encoding, newline="") as handle:
                handle.write(content)
            print("Created: " + str(output))
    except (OSError, UnicodeError, ValueError) as exc:
        print("ERROR: " + str(exc), file=sys.stderr)
        return 2

    print("Profile order: baseline, each cache independently, then all-caches last.")
    print("Back up IVLegacy.ini and copy one profile into place before each fresh game run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
