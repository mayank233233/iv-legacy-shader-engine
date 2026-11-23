#!/usr/bin/env python3
"""Summarize D3D9 texture/vertex/index binding submissions skipped by IVLegacy.

Counts avoided setter calls only. They are not FPS, frame-time or GPU-time data.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

WINDOW_RE = re.compile(
    r"D3D9_BINDING_CACHE_WINDOW\s+frames=(\d+)\s+"
    r"texture_forwarded=(\d+)\s+texture_skipped=(\d+)\s+"
    r"stream_forwarded=(\d+)\s+stream_skipped=(\d+)\s+"
    r"index_forwarded=(\d+)\s+index_skipped=(\d+)\s+"
    r"vs_forwarded=(\d+)\s+vs_skipped=(\d+)\s+"
    r"ps_forwarded=(\d+)\s+ps_skipped=(\d+)\s+"
    r"vertex_format_forwarded=(\d+)\s+vertex_format_skipped=(\d+)\s+"
    r"stream_freq_forwarded=(\d+)\s+stream_freq_skipped=(\d+)"
)


def summarize(path: Path) -> dict:
    names = ("texture", "stream", "index", "vertex_shader", "pixel_shader", "vertex_format", "stream_frequency")
    totals = {name: {"forwarded": 0, "skipped": 0} for name in names}
    frames = 0
    windows = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WINDOW_RE.search(line)
        if not match:
            continue
        frame_count, *counts = (int(value) for value in match.groups())
        frames += frame_count
        windows += 1
        for index, name in enumerate(names):
            totals[name]["forwarded"] += counts[index * 2]
            totals[name]["skipped"] += counts[index * 2 + 1]

    groups = {}
    forwarded_total = skipped_total = 0
    for name, values in totals.items():
        forwarded = values["forwarded"]
        skipped = values["skipped"]
        observed = forwarded + skipped
        groups[name] = {
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
            "Repeated binding submissions were suppressed in the observed windows. "
            "This does not prove improved frame time; cache bookkeeping and thread "
            "checks may cost more than the avoided D3D9 calls."
            if observed_total else
            "No binding-cache windows found. Confirm EnableBindingCache=1, that the "
            "cache remained enabled, and that the log contains a report window."
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
            "Only compare matched routes/settings and equivalent frame coverage. "
            "API suppression counts are not frame-time or FPS measurements."
        ),
    }


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "IVLegacy.log"
        path.write_text(
            "D3D9_BINDING_CACHE_WINDOW frames=120 "
            "texture_forwarded=3 texture_skipped=3 "
            "stream_forwarded=3 stream_skipped=3 "
            "index_forwarded=3 index_skipped=3 "
            "vs_forwarded=3 vs_skipped=3 "
            "ps_forwarded=3 ps_skipped=3 "
            "vertex_format_forwarded=2 vertex_format_skipped=4 "
            "stream_freq_forwarded=3 stream_freq_skipped=3\n",
            encoding="utf-8",
        )
        report = summarize(path)
    assert report["cache_windows"] == 1
    assert report["frames_covered_by_windows"] == 120
    assert report["total"]["forwarded"] == 20
    assert report["total"]["skipped"] == 22
    assert report["total"]["skip_rate_percent"] == 52.38
    print("GMA binding-cache benchmark analyzer self-test passed")


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
