#!/usr/bin/env python3
"""Summarize skipped D3D9 shader-constant register uploads.

This counts exact repeated register ranges skipped by the opt-in IVLegacy
cache. It does not measure frame time, FPS, GPU time or visual correctness.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

KINDS = (
    "vs_float",
    "ps_float",
    "vs_int",
    "ps_int",
    "vs_bool",
    "ps_bool",
)
WINDOW_RE = re.compile(
    r"D3D9_SHADER_CONSTANT_CACHE_WINDOW\s+frames=(\d+)\s+"
    + r"\s+".join(
        rf"{kind}_forwarded=(\d+)\s+{kind}_skipped=(\d+)"
        for kind in KINDS
    )
)


def summarize(path: Path) -> dict:
    totals = {kind: {"forwarded": 0, "skipped": 0} for kind in KINDS}
    frames = 0
    windows = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WINDOW_RE.search(line)
        if not match:
            continue
        frame_count, *counts = (int(value) for value in match.groups())
        frames += frame_count
        windows += 1
        for index, kind in enumerate(KINDS):
            totals[kind]["forwarded"] += counts[index * 2]
            totals[kind]["skipped"] += counts[index * 2 + 1]

    groups = {}
    forwarded_total = skipped_total = 0
    for kind, values in totals.items():
        forwarded = values["forwarded"]
        skipped = values["skipped"]
        observed = forwarded + skipped
        groups[kind] = {
            **values,
            "observed_calls": observed,
            "skip_rate_percent": round(100.0 * skipped / observed, 2) if observed else None,
        }
        forwarded_total += forwarded
        skipped_total += skipped

    observed_total = forwarded_total + skipped_total
    return {
        "input_log": str(path),
        "cache_windows": windows,
        "frames_covered_by_windows": frames,
        "groups": groups,
        "total": {
            "forwarded": forwarded_total,
            "skipped": skipped_total,
            "observed_calls": observed_total,
            "skip_rate_percent": (
                round(100.0 * skipped_total / observed_total, 2)
                if observed_total else None
            ),
        },
        "interpretation": (
            "Repeated shader-constant register ranges were suppressed in the "
            "observed windows. This does not prove better frame time; comparison, "
            "thread checks and cache maintenance may cost more than the avoided calls."
            if observed_total else
            "No shader-constant cache windows found. Confirm "
            "EnableShaderConstantCache=1, that the cache remained enabled, and that "
            "the log includes at least one reporting window."
        ),
    }


def compare(baseline: dict, optimized: dict) -> dict:
    return {
        "baseline": baseline["total"],
        "optimized": optimized["total"],
        "frame_coverage": {
            "baseline": baseline["frames_covered_by_windows"],
            "optimized": optimized["frames_covered_by_windows"],
        },
        "warning": (
            "Only compare matched routes, settings and frame coverage. Skipped "
            "register-call counts are not FPS or frame-time measurements."
        ),
    }


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "IVLegacy.log"
        fields = []
        for kind in KINDS:
            fields.extend((f"{kind}_forwarded=3", f"{kind}_skipped=3"))
        path.write_text(
            "D3D9_SHADER_CONSTANT_CACHE_WINDOW frames=120 "
            + " ".join(fields) + "\n",
            encoding="utf-8",
        )
        report = summarize(path)
    assert report["cache_windows"] == 1
    assert report["frames_covered_by_windows"] == 120
    assert report["total"]["forwarded"] == 18
    assert report["total"]["skipped"] == 18
    assert report["total"]["skip_rate_percent"] == 50.0
    assert all(
        report["groups"][kind]["skip_rate_percent"] == 50.0
        for kind in KINDS
    )
    print("GMA shader-constant cache benchmark analyzer self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--compare", type=Path, help="optional second log to compare")
    parser.add_argument("--json", type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return 0
    if args.log is None or not args.log.is_file():
        parser.error("provide an existing IVLegacy.log or use --self-test")
    report = summarize(args.log)
    if args.compare:
        if not args.compare.is_file():
            parser.error("--compare must name an existing log")
        report["comparison"] = compare(report, summarize(args.compare))
    rendered = json.dumps(report, indent=2)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
