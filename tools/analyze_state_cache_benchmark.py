#!/usr/bin/env python3
"""Quantify redundant D3D9 state calls skipped by IVLegacy's opt-in cache.

This reports API-call suppression, not FPS or GPU-time improvement. Use logs
captured from the same save, route, settings and duration with cache OFF/ON.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

WINDOW_RE = re.compile(
    r"D3D9_STATE_CACHE_WINDOW\s+frames=(\d+)\s+"
    r"render_forwarded=(\d+)\s+render_skipped=(\d+)\s+"
    r"texture_stage_forwarded=(\d+)\s+texture_stage_skipped=(\d+)\s+"
    r"sampler_forwarded=(\d+)\s+sampler_skipped=(\d+)"
)


def summarize(path: Path) -> dict:
    totals = {
        "render": {"forwarded": 0, "skipped": 0},
        "texture_stage": {"forwarded": 0, "skipped": 0},
        "sampler": {"forwarded": 0, "skipped": 0},
    }
    frames = 0
    windows = 0
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = WINDOW_RE.search(line)
        if not match:
            continue
        values = [int(value) for value in match.groups()]
        frame_count, *counts = values
        frames += frame_count
        windows += 1
        for index, group in enumerate(("render", "texture_stage", "sampler")):
            totals[group]["forwarded"] += counts[index * 2]
            totals[group]["skipped"] += counts[index * 2 + 1]

    groups = {}
    total_forwarded = total_skipped = 0
    for name, values in totals.items():
        forwarded, skipped = values["forwarded"], values["skipped"]
        total = forwarded + skipped
        groups[name] = {
            **values,
            "observed_calls": total,
            "skip_rate_percent": round(100.0 * skipped / total, 2) if total else None,
        }
        total_forwarded += forwarded
        total_skipped += skipped

    observed = total_forwarded + total_skipped
    return {
        "input_log": str(path),
        "cache_windows": windows,
        "frames_covered_by_windows": frames,
        "groups": groups,
        "total": {
            "forwarded": total_forwarded,
            "skipped": total_skipped,
            "observed_calls": observed,
            "skip_rate_percent": round(100.0 * total_skipped / observed, 2) if observed else None,
        },
        "interpretation": (
            "The cache suppressed repeated API submissions in the observed windows. "
            "This does not establish lower frame time; lock and bookkeeping overhead "
            "may exceed the saved driver-call cost."
            if observed else
            "No state-cache windows found. Confirm EnableRedundantStateCache=1, "
            "that the cache remained enabled, and that the capture includes a report window."
        ),
    }


def compare(baseline: dict, optimized: dict) -> dict:
    """Compare logged API suppression and frame coverage; never infer FPS."""
    return {
        "baseline": baseline["total"],
        "optimized": optimized["total"],
        "frame_coverage": {
            "baseline": baseline["frames_covered_by_windows"],
            "optimized": optimized["frames_covered_by_windows"],
        },
        "warning": (
            "Different workloads or frame coverage make this comparison invalid. "
            "Even matched API suppression is not a frame-time measurement."
        ),
    }


def self_test() -> None:
    import tempfile
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "IVLegacy.log"
        path.write_text(
            "D3D9_STATE_CACHE_WINDOW frames=120 "
            "render_forwarded=100 render_skipped=50 "
            "texture_stage_forwarded=20 texture_stage_skipped=30 "
            "sampler_forwarded=10 sampler_skipped=10\n",
            encoding="utf-8",
        )
        report = summarize(path)
    assert report["cache_windows"] == 1
    assert report["frames_covered_by_windows"] == 120
    assert report["total"]["forwarded"] == 130
    assert report["total"]["skipped"] == 90
    assert report["total"]["skip_rate_percent"] == 40.91
    print("GMA state-cache benchmark analyzer self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path)
    parser.add_argument("--compare", type=Path, help="optional cache-ON log to compare with baseline log")
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
