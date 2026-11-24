#!/usr/bin/env python3
"""Compare IVLegacy D3D9 frame-profiler and cache-counter logs.

The profiler measures CPU-side Present intervals and D3D9 draw-call wall time.
It does not measure GPU execution time. Comparisons are descriptive, not proof
that a cache caused a change; identical route/settings and repeated runs matter.
"""
from __future__ import annotations

import argparse
import json
import re
import statistics
from pathlib import Path
from typing import Any

KV_RE = re.compile(r"([A-Za-z][A-Za-z0-9_]*)=([^ ]+)")
FRAME_PREFIX = "FRAME_PROFILE_WINDOW"
CACHE_PREFIXES = {
    "state": "D3D9_STATE_CACHE_WINDOW",
    "binding": "D3D9_BINDING_CACHE_WINDOW",
    "shader_constant": "D3D9_SHADER_CONSTANT_CACHE_WINDOW",
}
CACHE_ENABLE_MARKERS = {
    "state": "REDUNDANT_STATE_CACHE_ENABLED",
    "binding": "BINDING_CACHE_ENABLED",
    "shader_constant": "SHADER_CONSTANT_CACHE_ENABLED",
}
CACHE_DISABLE_MARKERS = {
    "state": "STATE_CACHE_DISABLED",
    "binding": "BINDING_CACHE_DISABLED",
    "shader_constant": "SHADER_CONSTANT_CACHE_DISABLED",
}
AVERAGE_FIELDS = (
    "avg_frame_ms",
    "avg_present_ms",
    "avg_draw_api_ms",
    "avg_unattributed_ms",
    "avg_draw_calls",
)
PERCENTILE_FIELDS = (
    "p50_frame_ms",
    "p95_frame_ms",
    "p99_frame_ms",
    "p95_present_ms",
    "p95_draw_api_ms",
    "p95_unattributed_ms",
)


def parse_fields(line: str) -> dict[str, str]:
    return dict(KV_RE.findall(line))


def as_float(fields: dict[str, str], name: str) -> float | None:
    try:
        value = float(fields[name])
    except (KeyError, TypeError, ValueError):
        return None
    return value if value >= 0 else None


def parse_log(path: Path) -> dict[str, Any]:
    frame_windows: list[dict[str, float | int | str]] = []
    cache_totals: dict[str, dict[str, int]] = {
        name: {"frames": 0, "windows": 0, "forwarded": 0, "skipped": 0}
        for name in CACHE_PREFIXES
    }
    malformed_frames = 0
    bootstrap_complete = False
    enabled_markers = {name: False for name in CACHE_PREFIXES}
    disable_reasons: dict[str, list[str]] = {name: [] for name in CACHE_PREFIXES}

    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "BOOTSTRAP_COMPLETE" in line:
            bootstrap_complete = True
        for name, marker in CACHE_ENABLE_MARKERS.items():
            if marker in line:
                enabled_markers[name] = True
        for name, marker in CACHE_DISABLE_MARKERS.items():
            if marker in line:
                reason = parse_fields(line).get("reason", "unspecified")
                if reason not in disable_reasons[name]:
                    disable_reasons[name].append(reason)

        if FRAME_PREFIX in line:
            fields = parse_fields(line)
            samples = as_float(fields, "samples")
            frame = {name: as_float(fields, name) for name in AVERAGE_FIELDS + PERCENTILE_FIELDS}
            if samples is None or samples <= 0 or any(
                frame[name] is None for name in ("avg_frame_ms", "p50_frame_ms", "p95_frame_ms")
            ):
                malformed_frames += 1
                continue
            frame["samples"] = int(samples)
            frame["draw_failures"] = int(as_float(fields, "draw_failures") or 0)
            frame["gpu_time"] = fields.get("gpu_time", "unspecified")
            frame_windows.append(frame)

        for name, prefix in CACHE_PREFIXES.items():
            if prefix not in line:
                continue
            fields = parse_fields(line)
            totals = cache_totals[name]
            try:
                frames = int(fields.get("frames", "0"))
            except ValueError:
                frames = 0
            totals["frames"] += max(0, frames)
            totals["windows"] += 1
            for key, value in fields.items():
                if key.endswith("_forwarded") or key.endswith("_skipped"):
                    try:
                        count = max(0, int(value))
                    except ValueError:
                        continue
                    totals["forwarded" if key.endswith("_forwarded") else "skipped"] += count

    profiler_frames = sum(int(window["samples"]) for window in frame_windows)
    profiler: dict[str, Any] = {
        "windows": len(frame_windows),
        "frames": profiler_frames,
        "malformed_windows": malformed_frames,
        "gpu_time": "not_measured",
    }
    if frame_windows:
        total_samples = profiler_frames
        for field in AVERAGE_FIELDS:
            values = [(float(w[field]), int(w["samples"])) for w in frame_windows if w[field] is not None]
            denominator = sum(count for _, count in values)
            profiler[field] = (
                sum(value * count for value, count in values) / denominator
                if denominator else None
            )
        # Percentiles are not mergeable from window summaries. Report the
        # median and range of each window's percentile rather than inventing
        # a global percentile.
        for field in PERCENTILE_FIELDS:
            values = [float(w[field]) for w in frame_windows if w[field] is not None]
            if values:
                profiler[f"median_window_{field}"] = statistics.median(values)
                profiler[f"min_window_{field}"] = min(values)
                profiler[f"max_window_{field}"] = max(values)
        average_frame_ms = profiler.get("avg_frame_ms")
        profiler["effective_fps_from_average_frame_ms"] = (
            1000.0 / average_frame_ms if average_frame_ms and average_frame_ms > 0 else None
        )
        median_p95 = profiler.get("median_window_p95_frame_ms")
        profiler["fps_equivalent_at_median_window_p95"] = (
            1000.0 / median_p95 if median_p95 and median_p95 > 0 else None
        )
        profiler["draw_failures"] = sum(int(w["draw_failures"]) for w in frame_windows)
        profiler["interpretation"] = (
            "Frame intervals are measured between successful Present returns. "
            "Draw API time is CPU wall time and may include driver waits. "
            "GPU execution time is not measured."
        )
    else:
        profiler["interpretation"] = (
            "No valid FRAME_PROFILE_WINDOW records found. EnableFrameProfiler=1 "
            "and collect enough successful Present frames."
        )

    cache_report: dict[str, Any] = {}
    for name, totals in cache_totals.items():
        observed = totals["forwarded"] + totals["skipped"]
        cache_report[name] = {
            **totals,
            "observed_calls": observed,
            "skip_rate_percent": round(100.0 * totals["skipped"] / observed, 2) if observed else None,
        }

    cache_states: dict[str, Any] = {}
    for name, totals in cache_totals.items():
        configured_enabled = enabled_markers[name] if bootstrap_complete else (
            True if enabled_markers[name] else None
        )
        runtime_enabled = (
            bool(configured_enabled and not disable_reasons[name])
            if bootstrap_complete else None
        )
        cache_states[name] = {
            "configured_enabled": configured_enabled,
            "runtime_enabled_through_log": runtime_enabled,
            "disabled_reasons": disable_reasons[name],
            "counter_windows": totals["windows"],
            "counter_frames": totals["frames"],
        }
    cache_configuration = {
        "known": bootstrap_complete,
        "bootstrap_complete": bootstrap_complete,
        "caches": cache_states,
        "configured_enabled_caches": (
            [name for name, state in cache_states.items() if state["configured_enabled"] is True]
            if bootstrap_complete else None
        ),
        "runtime_enabled_caches": (
            [name for name, state in cache_states.items()
             if state["runtime_enabled_through_log"] is True]
            if bootstrap_complete else None
        ),
    }

    warnings = [
        "Skipped D3D9 calls are not evidence of faster frame times.",
        "The profiler does not measure GPU time or prove visual correctness.",
        "Compare identical game version, save, route, camera, weather, time and graphics settings; repeat each run.",
        "Window percentiles are summarized as medians/ranges across windows, not merged into global percentiles.",
    ]
    if not bootstrap_complete:
        warnings.append("Cache configuration is unknown because BOOTSTRAP_COMPLETE was not recorded.")
    if not frame_windows:
        warnings.append("No valid frame-profiler windows were found.")
    return {
        "input_log": str(path),
        "profiler": profiler,
        "cache_counters": cache_report,
        "cache_configuration": cache_configuration,
        "warnings": warnings,
    }


def percent_change(baseline: float | None, candidate: float | None) -> float | None:
    if baseline is None or candidate is None or baseline == 0:
        return None
    return round(100.0 * (candidate - baseline) / baseline, 3)


def compare_runs(baseline: dict[str, Any], candidate: dict[str, Any]) -> dict[str, Any]:
    base = baseline["profiler"]
    test = candidate["profiler"]
    base_frames = int(base["frames"])
    test_frames = int(test["frames"])
    coverage_delta = abs(test_frames - base_frames) / max(base_frames, test_frames, 1) * 100.0

    base_draws = base.get("avg_draw_calls")
    test_draws = test.get("avg_draw_calls")
    draw_delta = percent_change(base_draws, test_draws)
    avg_delta = percent_change(base.get("avg_frame_ms"), test.get("avg_frame_ms"))
    p95_delta = percent_change(
        base.get("median_window_p95_frame_ms"),
        test.get("median_window_p95_frame_ms"),
    )
    warnings = []
    base_config = baseline.get("cache_configuration", {})
    test_config = candidate.get("cache_configuration", {})
    if not base_config.get("known") or not test_config.get("known"):
        warnings.append("Cache configuration is unverified in at least one run; BOOTSTRAP_COMPLETE is required.")
    else:
        base_requested = base_config.get("configured_enabled_caches") or []
        test_requested = test_config.get("configured_enabled_caches") or []
        if base_requested:
            warnings.append(
                "Baseline is not a clean cache-off run; configured caches: "
                + ", ".join(base_requested) + "."
            )
        if len(test_requested) == 0:
            warnings.append("Candidate has no cache configured ON; it is not a cache-on test.")
        elif len(test_requested) > 1:
            warnings.append(
                "Candidate enables multiple caches (" + ", ".join(test_requested)
                + "); this cannot isolate one cache's effect."
            )
        else:
            selected_cache = test_requested[0]
            selected_state = (test_config.get("caches") or {}).get(selected_cache, {})
            if selected_state.get("runtime_enabled_through_log") is not True:
                reasons = selected_state.get("disabled_reasons") or []
                detail = ", ".join(reasons) if reasons else "runtime state not confirmed"
                warnings.append(
                    f"Candidate cache '{selected_cache}' did not remain enabled through the log: {detail}."
                )
            if int(selected_state.get("counter_windows") or 0) == 0:
                warnings.append(
                    f"Candidate cache '{selected_cache}' emitted no cache-counter windows during measurement."
                )
    if not base_frames or not test_frames:
        warnings.append("At least one run has no valid frame-profiler samples.")
    if coverage_delta > 10.0:
        warnings.append("Profiler frame coverage differs by more than 10%.")
    if draw_delta is not None and abs(draw_delta) > 5.0:
        warnings.append("Average draw-call count per frame differs by more than 5%; workloads may not match.")
    if min(base_frames, test_frames) < 240:
        warnings.append("Fewer than 240 measured frames in at least one run; repeat with longer captures.")
    if avg_delta is not None and p95_delta is not None and not warnings:
        if avg_delta <= -3.0 and p95_delta <= -3.0:
            interpretation = "candidate_faster_in_this_comparison; causation_not_established"
        elif avg_delta >= 3.0 and p95_delta >= 3.0:
            interpretation = "candidate_slower_in_this_comparison; causation_not_established"
        else:
            interpretation = "no_clear_frame_time_improvement"
    else:
        interpretation = "inconclusive_comparison"

    return {
        "baseline": baseline["input_log"],
        "candidate": candidate["input_log"],
        "frame_coverage_delta_percent": round(coverage_delta, 2),
        "average_draw_calls_change_percent": draw_delta,
        "average_frame_ms_change_percent": avg_delta,
        "median_window_p95_frame_ms_change_percent": p95_delta,
        "effective_fps_from_average_frame_ms": {
            "baseline": base.get("effective_fps_from_average_frame_ms"),
            "candidate": test.get("effective_fps_from_average_frame_ms"),
        },
        "interpretation": interpretation,
        "warnings": warnings or [
            "The measured difference is descriptive only. Repeat A/B/A runs before attributing it to a cache.",
            "Run one cache at a time; keep telemetry identical and avoid shader/draw capture during timing runs.",
        ],
    }


def self_test() -> None:
    import tempfile

    def row(avg: float, p50: float, p95: float, frames: int = 120) -> str:
        return (
            f"FRAME_PROFILE_WINDOW samples={frames} target_30fps_ms=33.333 "
            f"avg_frame_ms={avg:.3f} p50_frame_ms={p50:.3f} p95_frame_ms={p95:.3f} "
            f"p99_frame_ms={p95 + 3:.3f} max_frame_ms={p95 + 5:.3f} "
            "avg_present_ms=2.000 p95_present_ms=3.000 "
            "avg_draw_api_ms=1.000 p95_draw_api_ms=2.000 "
            "avg_unattributed_ms=20.000 p95_unattributed_ms=22.000 "
            "avg_draw_calls=80.00 draw_failures=0 gpu_time=not_measured\n"
        )

    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        baseline_path = root / "baseline.log"
        candidate_path = root / "candidate.log"
        state_path = root / "state-cache.log"
        unknown_path = root / "unknown-config.log"
        disabled_path = root / "disabled-cache.log"
        mixed_path = root / "mixed-cache.log"

        baseline_path.write_text(
            row(40, 39, 48) * 2
            + "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=1\n",
            encoding="utf-8",
        )
        candidate_path.write_text(
            "BINDING_CACHE_ENABLED groups=texture,vertex_stream default=off\n"
            + "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=1\n"
            + row(30, 29, 36) * 2
            + "D3D9_BINDING_CACHE_WINDOW frames=120 texture_forwarded=10 texture_skipped=10 "
            "stream_forwarded=10 stream_skipped=10\n",
            encoding="utf-8",
        )
        state_path.write_text(
            "REDUNDANT_STATE_CACHE_ENABLED groups=render_state,texture_stage,sampler default=off\n"
            "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=1\n"
            "D3D9_STATE_CACHE_WINDOW frames=120 render_forwarded=40 render_skipped=60 "
            "texture_stage_forwarded=10 texture_stage_skipped=10 sampler_forwarded=5 sampler_skipped=5\n",
            encoding="utf-8",
        )
        unknown_path.write_text(
            "BINDING_CACHE_ENABLED groups=texture,vertex_stream default=off\n" + row(30, 29, 36),
            encoding="utf-8",
        )
        disabled_path.write_text(
            "REDUNDANT_STATE_CACHE_ENABLED groups=render_state,texture_stage,sampler default=off\n"
            "STATE_CACHE_DISABLED reason=multiple_device_threads\n"
            "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=1\n",
            encoding="utf-8",
        )
        mixed_path.write_text(
            "BINDING_CACHE_ENABLED groups=texture,vertex_stream default=off\n"
            "SHADER_CONSTANT_CACHE_ENABLED groups=vs_float,ps_float default=off\n"
            "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=1\n"
            + row(30, 29, 36) * 2
            + "D3D9_BINDING_CACHE_WINDOW frames=120 texture_forwarded=10 texture_skipped=10\n",
            encoding="utf-8",
        )

        baseline = parse_log(baseline_path)
        candidate = parse_log(candidate_path)
        state = parse_log(state_path)
        unknown = parse_log(unknown_path)
        disabled = parse_log(disabled_path)
        mixed = parse_log(mixed_path)
        result = compare_runs(baseline, candidate)
        unknown_result = compare_runs(unknown, candidate)
        mixed_result = compare_runs(baseline, mixed)

    assert baseline["profiler"]["frames"] == 240
    assert baseline["profiler"]["effective_fps_from_average_frame_ms"] == 25.0
    assert baseline["cache_configuration"]["known"] is True
    assert baseline["cache_configuration"]["configured_enabled_caches"] == []
    assert candidate["cache_configuration"]["runtime_enabled_caches"] == ["binding"]
    assert candidate["cache_configuration"]["caches"]["binding"]["counter_windows"] == 1
    assert state["cache_counters"]["state"]["skipped"] == 75
    assert candidate["cache_counters"]["binding"]["skipped"] == 20
    assert result["average_frame_ms_change_percent"] == -25.0
    assert result["interpretation"] == "candidate_faster_in_this_comparison; causation_not_established"
    assert unknown["cache_configuration"]["known"] is False
    assert "Cache configuration is unknown" in " ".join(unknown["warnings"])
    assert disabled["cache_configuration"]["caches"]["state"]["runtime_enabled_through_log"] is False
    assert disabled["cache_configuration"]["caches"]["state"]["disabled_reasons"] == ["multiple_device_threads"]
    assert mixed_result["interpretation"] == "inconclusive_comparison"
    assert any("multiple caches" in warning for warning in mixed_result["warnings"])
    assert unknown_result["interpretation"] == "inconclusive_comparison"
    print("GMA performance analyzer self-test passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", nargs="?", type=Path, help="candidate IVLegacy.log")
    parser.add_argument("--baseline", type=Path, help="baseline IVLegacy.log for A/B comparison")
    parser.add_argument("--json", type=Path, help="optional JSON report path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        self_test()
        return 0
    if args.candidate is None or not args.candidate.is_file():
        parser.error("provide an existing candidate IVLegacy.log or use --self-test")
    candidate = parse_log(args.candidate)
    report: dict[str, Any] = {"candidate": candidate}
    if args.baseline:
        if not args.baseline.is_file():
            parser.error("--baseline must name an existing IVLegacy.log")
        report["comparison"] = compare_runs(parse_log(args.baseline), candidate)
    rendered = json.dumps(report, indent=2)
    if args.json:
        args.json.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
