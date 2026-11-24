#!/usr/bin/env python3
"""Validate whether an IVLegacy capture is real and complete enough for pair review.

This read-only preflight rejects synthetic CI logs, verifies the expected GTA IV
executable and GMA 3100 identity, checks D3D9 setup, and correlates successful
draws with captured vertex/pixel bytecode. It never emits or approves mappings.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import analyze_asi_log
import analyze_asi_constants
import analyze_d3d9_shaders
import audit_shader_pairs

EXPECTED_VENDOR_ID = 0x8086
EXPECTED_DEVICE_ID = 0x29C2
EXPECTED_GTAIV_VERSION = "1.0.0.0"


def _has_marker(text: str, marker: str) -> bool:
    return any(marker in line for line in text.splitlines())


def _executable_version(text: str) -> str | None:
    for line in text.splitlines():
        if "EXECUTABLE " in line:
            return analyze_asi_log.parse_fields(line).get("file_version")
    return None


def _has_sm20_caps(caps: list[dict[str, Any]]) -> bool:
    for snapshot in caps:
        vs = snapshot.get("vertex_shader") or {}
        ps = snapshot.get("pixel_shader") or {}
        vs_level = (int(vs.get("major", 0)), int(vs.get("minor", 0)))
        ps_level = (int(ps.get("major", 0)), int(ps.get("minor", 0)))
        if vs_level >= (2, 0) and ps_level >= (2, 0):
            return True
    return False


def validate_capture(
    log_path: Path,
    capture_dir: Path,
    constants_dir: Path | None = None,
) -> dict[str, Any]:
    if not log_path.is_file():
        raise FileNotFoundError(f"IVLegacy log not found: {log_path}")
    if not capture_dir.is_dir():
        raise FileNotFoundError(f"shader capture directory not found: {capture_dir}")

    raw_log = log_path.read_text(encoding="utf-8", errors="replace")
    draw_report = analyze_asi_log.analyze_log(log_path)
    capture_index = audit_shader_pairs.index_captures(capture_dir)
    inventory = analyze_d3d9_shaders.analyze_directory(capture_dir, None)
    pair_report = audit_shader_pairs.audit_log(log_path, capture_dir)

    adapters = draw_report.get("adapter_identifiers", [])
    adapter = next(
        (
            item for item in adapters
            if item.get("vendor_id") == EXPECTED_VENDOR_ID
            and item.get("device_id") == EXPECTED_DEVICE_ID
        ),
        adapters[0] if adapters else None,
    )
    adapter_text = " ".join(
        str((adapter or {}).get(key) or "") for key in ("description", "driver")
    )
    synthetic = "synthetic" in adapter_text.lower()
    expected_adapter = bool(
        adapter
        and adapter.get("vendor_id") == EXPECTED_VENDOR_ID
        and adapter.get("device_id") == EXPECTED_DEVICE_ID
        and not synthetic
    )

    hook_markers = {
        "bootstrap": _has_marker(raw_log, "BOOTSTRAP_COMPLETE"),
        "d3d9_iat": _has_marker(raw_log, "D3D9_IAT_HOOK_INSTALLED"),
        "d3d9_interface": _has_marker(raw_log, "D3D9_INTERFACE_HOOK_INSTALLED"),
        "d3d9_device": _has_marker(raw_log, "D3D9_DEVICE_HOOK_INSTALLED"),
    }
    executable_version = _executable_version(raw_log)
    device_create_success = any(
        item.get("event") == "result" and item.get("succeeded") is True
        for item in draw_report.get("device_create_events", [])
    )
    successful_draws = [
        item for item in draw_report.get("draw_calls", [])
        if item.get("succeeded") is True
    ]

    captured_pairs: dict[tuple[str, str], int] = {}
    captured_pair_draws = 0
    unresolved_pair_draws = 0
    for draw in successful_draws:
        vs = draw.get("vertex_shader") or {}
        ps = draw.get("pixel_shader") or {}
        vs_hash = str(vs.get("hash") or "").upper()
        ps_hash = str(ps.get("hash") or "").upper()
        # Resolve each hash against the expected shader stage and profile.
        # Hash membership alone is insufficient: it does not prove a VS draw
        # reference points to vertex bytecode or a PS reference to pixel bytecode.
        vs_capture = audit_shader_pairs.select_capture(vs, "VS", capture_index)
        ps_capture = audit_shader_pairs.select_capture(ps, "PS", capture_index)
        if not vs_hash or not ps_hash or vs_capture is None or ps_capture is None:
            unresolved_pair_draws += 1
            continue
        captured_pair_draws += 1
        captured_pairs[(vs_hash, ps_hash)] = captured_pairs.get((vs_hash, ps_hash), 0) + 1

    profiles = inventory.get("profile_counts", {})
    vs_profiles = {key: value for key, value in profiles.items() if key.startswith("vs_")}
    ps_profiles = {key: value for key, value in profiles.items() if key.startswith("ps_")}
    vs3_files = int(vs_profiles.get("vs_3_0", 0))
    ps3_files = int(ps_profiles.get("ps_3_0", 0))

    if constants_dir is not None and constants_dir.is_dir():
        constants = analyze_asi_constants.analyze_directory(constants_dir, log_path)
    else:
        constants = {
            "record_count": 0,
            "invalid_record_count": 0,
            "shader_objects_resolved": 0,
            "stage_counts": {"VS": 0, "PS": 0},
        }

    blockers: list[str] = []
    warnings: list[str] = []
    if executable_version != EXPECTED_GTAIV_VERSION:
        blockers.append(
            f"Expected GTAIV.exe file version {EXPECTED_GTAIV_VERSION}; "
            f"observed {executable_version or 'unknown'}"
        )
    for key, label in (
        ("bootstrap", "ASI bootstrap completion"),
        ("d3d9_iat", "Direct3DCreate9 import hook"),
        ("d3d9_interface", "IDirect3D9 interface hook"),
        ("d3d9_device", "IDirect3DDevice9 hook"),
    ):
        if not hook_markers[key]:
            blockers.append(f"{label} was not recorded")
    if not expected_adapter:
        if synthetic:
            blockers.append("Adapter/driver identifies itself as synthetic test data")
        elif adapter is None:
            blockers.append("No D3D9 adapter identity was recorded")
        else:
            blockers.append(
                "Adapter PCI identity does not match Intel GMA 3100 (8086:29C2); "
                f"observed {adapter.get('vendor_id')}:{adapter.get('device_id')}"
            )
    caps = draw_report.get("device_capability_snapshots", [])
    if not _has_sm20_caps(caps):
        blockers.append("No usable VS2.0 + PS2.0 capability snapshot was recorded")
    if not device_create_success:
        blockers.append("No successful D3D9 CreateDevice result was recorded")
    if not _has_marker(raw_log, "SHADER_CAPTURE_ENABLED"):
        blockers.append("Shader bytecode capture was not enabled/recorded")
    if not _has_marker(raw_log, "DRAW_TELEMETRY_ENABLED"):
        blockers.append("Per-draw telemetry was not enabled/recorded")
    if not draw_report.get("draw_calls_observed", 0):
        blockers.append("No D3D9 draw calls were captured")
    if not successful_draws:
        blockers.append("No successful D3D9 draw submissions were captured")
    if inventory.get("failed_shader_count", 0):
        blockers.append(
            f"{inventory['failed_shader_count']} captured shader file(s) failed token parsing"
        )
    if not vs_profiles:
        blockers.append("No vertex shader bytecode was captured")
    if not ps_profiles:
        blockers.append("No pixel shader bytecode was captured")
    if captured_pair_draws == 0:
        blockers.append("No successful draw resolved to both captured VS and PS bytecode")

    if draw_report.get("failed_draw_calls", 0):
        warnings.append(
            f"{draw_report['failed_draw_calls']} draw submission(s) failed; inspect them before choosing pairs"
        )
    if draw_report.get("unresolved_shader_references", 0):
        warnings.append(
            f"{draw_report['unresolved_shader_references']} draw shader reference(s) were unresolved"
        )
    if not vs3_files or not ps3_files:
        warnings.append(
            "Both VS3.0 and PS3.0 captures were not found; full SM3 pair lowering may not be possible"
        )
    if captured_pair_draws < len(successful_draws):
        warnings.append(
            f"Only {captured_pair_draws}/{len(successful_draws)} successful draws resolved to captured VS+PS bytecode"
        )
    if constants_dir is None or not constants_dir.is_dir():
        warnings.append("Shader constant sidecar directory was not supplied; constants were not validated")
    elif constants.get("invalid_record_count", 0):
        warnings.append(
            f"{constants['invalid_record_count']} shader-constant sidecar(s) are invalid"
        )
    elif constants.get("record_count", 0) == 0:
        warnings.append("No shader-constant sidecars were recorded; this can be normal")

    pair_status_counts = pair_report.get("status_counts", {})
    ready = not blockers
    status = "ready_for_pair_review" if ready else (
        "synthetic_or_wrong_target" if synthetic or (adapter and not expected_adapter)
        else "incomplete_capture"
    )
    return {
        "schema_version": 1,
        "status": status,
        "ready_for_pair_review": ready,
        "runtime_map_approval": "not_performed",
        "input_log": str(log_path),
        "capture_directory": str(capture_dir),
        "executable_file_version": executable_version,
        "adapter": adapter,
        "expected_adapter_identity": {
            "vendor_id": EXPECTED_VENDOR_ID,
            "device_id": EXPECTED_DEVICE_ID,
        },
        "hook_markers": hook_markers,
        "device_create_success": device_create_success,
        "capability_snapshots": caps,
        "draws": {
            "observed": draw_report.get("draw_calls_observed", 0),
            "successful": len(successful_draws),
            "failed": draw_report.get("failed_draw_calls", 0),
            "successful_draws_with_resolved_vs_ps_captures": captured_pair_draws,
            "successful_draws_missing_one_or_both_captures": unresolved_pair_draws,
        },
        "shader_captures": {
            "files": inventory.get("shader_file_count", 0),
            "parsed": inventory.get("parsed_shader_count", 0),
            "failed": inventory.get("failed_shader_count", 0),
            "profile_counts": profiles,
            "vs3_files": vs3_files,
            "ps3_files": ps3_files,
            "unique_captured_shader_pairs": len(captured_pairs),
        },
        "paired_shader_audit": {
            "draws_audited": pair_report.get("draw_calls_audited", 0),
            "unique_pairs_audited": pair_report.get("unique_shader_pairs_audited", 0),
            "status_counts": pair_status_counts,
            "manual_pair_candidates": int(
                pair_status_counts.get("pair_candidate_for_manual_lowering", 0)
            ),
        },
        "shader_constants": {
            "records": constants.get("record_count", 0),
            "invalid_records": constants.get("invalid_record_count", 0),
            "resolved_to_shader_objects": constants.get("shader_objects_resolved", 0),
            "stage_counts": constants.get("stage_counts", {"VS": 0, "PS": 0}),
        },
        "blockers": blockers,
        "warnings": warnings,
        "interpretation": (
            "Ready means a non-synthetic target capture from GTA IV 1.0.0.0 on the expected "
            "adapter, with successful D3D9 setup and draws correlated to captured VS and PS "
            "bytecode. It does not mean a pair is convertible, driver-accepted, visually "
            "equivalent, or safe to add to a runtime fallback map."
        ),
    }


def _self_test() -> None:
    import tempfile

    def make_session(
        root: Path, *, synthetic: bool, swap_shader_stages: bool = False
    ) -> tuple[Path, Path]:
        capture_dir = root / "IVLegacyCaptures"
        capture_dir.mkdir(parents=True)
        vs_data = (0xFFFE0300).to_bytes(4, "little") + (0x0000FFFF).to_bytes(4, "little")
        ps_data = (0xFFFF0300).to_bytes(4, "little") + (0x0000FFFF).to_bytes(4, "little")
        vs_hash = audit_shader_pairs.fnv1a64(vs_data)
        ps_hash = audit_shader_pairs.fnv1a64(ps_data)
        (capture_dir / f"VS_3_0_{vs_hash}.bin").write_bytes(vs_data)
        (capture_dir / f"PS_3_0_{ps_hash}.bin").write_bytes(ps_data)
        description = "Synthetic GMA 3100 test adapter" if synthetic else "Intel GMA 3100"
        driver = "IVLegacy synthetic test driver" if synthetic else "Intel legacy display driver"
        if swap_shader_stages:
            vs_record = (
                f"SHADER_OBJECT_CREATED stage=VS object=0x100 profile=PS_3_0 "
                f"bytes=8 hash={ps_hash} hr=0x00000000"
            )
            ps_record = (
                f"SHADER_OBJECT_CREATED stage=PS object=0x200 profile=VS_3_0 "
                f"bytes=8 hash={vs_hash} hr=0x00000000"
            )
        else:
            vs_record = (
                f"SHADER_OBJECT_CREATED stage=VS object=0x100 profile=VS_3_0 "
                f"bytes=8 hash={vs_hash} hr=0x00000000"
            )
            ps_record = (
                f"SHADER_OBJECT_CREATED stage=PS object=0x200 profile=PS_3_0 "
                f"bytes=8 hash={ps_hash} hr=0x00000000"
            )
        log_path = root / "IVLegacy.log"
        lines = [
            "IV LEGACY SHADER ENGINE instrumentation build starting",
            r"EXECUTABLE path=C:\Games\GTAIV\GTAIV.exe PE=I386 file_version=1.0.0.0",
            "TARGET_VERSION_GATE passed=1.0.0.0",
            "D3D9_IAT_HOOK_INSTALLED original=00100000 replacement=00200000",
            "BOOTSTRAP_COMPLETE target=GTAIV_1.0.0.0 telemetry=1",
            "DIRECT3DCREATE9 sdk=32 result=00300000",
            "D3D9_INTERFACE_HOOK_INSTALLED interface=00300000",
            f"D3D9_ADAPTER adapter=0 vendor=0x8086 device=0x29C2 subsys=0x00000000 revision=0x00000001 driver_version=00000001:00000001 description={description} driver={driver}",
            "D3D9_GET_DEVICE_CAPS adapter=0 type=1 VS=0xFFFE0200 PS=0xFFFF0200 MaxSimTextures=2 MaxTextureStages=2 MaxRTs=1 MaxVSConst=96 VS20Temps=12 VS20DynamicFlow=0 VS20StaticFlow=1 PS20Caps=0x00000000 PS20Temps=12 PS20Slots=96 PS20DynamicFlow=0 PS20StaticFlow=0",
            "D3D9_CREATE_DEVICE_REQUEST adapter=0 type=1 flags=0x00000020 width=640 height=480 backbuffer_format=22 windowed=1 request_hardware_vp=0 request_mixed_vp=0 request_software_vp=1",
            "D3D9_CREATE_DEVICE_RESULT hr=0x00000000",
            "D3D9_DEVICE_HOOK_INSTALLED device=00310000 vtable=00320000 restore_protection=1",
            "SHADER_CAPTURE_ENABLED directory=IVLegacyCaptures max_files=4096",
            "DRAW_TELEMETRY_ENABLED max_calls=16384",
            vs_record,
            ps_record,
            "DRAW_CALL seq=1 frame=1 kind=DrawIndexedPrimitive device=00310000 primitive=4 primitives=2 start_vertex=0 base_vertex=0 min_vertex=0 num_vertices=3 start_index=0 bound_vs=0x100 bound_ps=0x200 vertex_decl=00000000 fvf=0x00000102 index_buffer=00000000 streams= textures=0:00000000 render_targets=0:0x333333:640:480:21:3:1:0:0:0 depth_target=0x444444:640:480:75:2:0:0:0:0 viewport=0:0:640:480:00000000:3F800000 sampler_hash=0000000000000000 sampler_count=0 render_state_hash=0000000000000000 render_state_count=0 texture_stage_hash=0000000000000000 texture_stage_count=0 hr=0x00000000",
        ]
        log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return log_path, capture_dir

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        log_path, capture_dir = make_session(root, synthetic=True)
        report = validate_capture(log_path, capture_dir)
        assert report["status"] == "synthetic_or_wrong_target"
        assert not report["ready_for_pair_review"]
        assert any("synthetic" in blocker.lower() for blocker in report["blockers"])

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        log_path, capture_dir = make_session(root, synthetic=False)
        report = validate_capture(log_path, capture_dir)
        assert report["status"] == "ready_for_pair_review", report["blockers"]
        assert report["draws"]["successful_draws_with_resolved_vs_ps_captures"] == 1
        assert report["shader_captures"]["vs3_files"] == 1
        assert report["shader_captures"]["ps3_files"] == 1
        assert report["runtime_map_approval"] == "not_performed"

    with tempfile.TemporaryDirectory() as temporary:
        root = Path(temporary)
        log_path, capture_dir = make_session(
            root, synthetic=False, swap_shader_stages=True
        )
        report = validate_capture(log_path, capture_dir)
        assert report["status"] == "incomplete_capture"
        assert not report["ready_for_pair_review"]
        assert report["draws"]["successful_draws_with_resolved_vs_ps_captures"] == 0
        assert any(
            "No successful draw resolved to both captured VS and PS bytecode" in blocker
            for blocker in report["blockers"]
        )

    print("PASS: GMA capture identity, hook, draw, stage-matching and shader-pair preflight self-tests")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("log", nargs="?", type=Path, help="IVLegacy.log from one GTA IV process")
    parser.add_argument("captures", nargs="?", type=Path, help="matching IVLegacyCaptures directory")
    parser.add_argument("--constants", type=Path, help="optional matching IVLegacyConstants directory")
    parser.add_argument("--json", type=Path, help="optional JSON report path")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        _self_test()
        return 0
    if args.log is None or args.captures is None:
        parser.error("log and captures are required unless --self-test is used")

    try:
        report = validate_capture(args.log, args.captures, args.constants)
    except (OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    print(f"GMA capture preflight: {report['status']}")
    print(
        "draws={observed} successful={successful} captured_VS+PS={paired}; "
        "captures={files} parsed={parsed}; pair_candidates={candidates}".format(
            observed=report["draws"]["observed"],
            successful=report["draws"]["successful"],
            paired=report["draws"]["successful_draws_with_resolved_vs_ps_captures"],
            files=report["shader_captures"]["files"],
            parsed=report["shader_captures"]["parsed"],
            candidates=report["paired_shader_audit"]["manual_pair_candidates"],
        )
    )
    for blocker in report["blockers"]:
        print(f"BLOCKER: {blocker}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}")
    if args.json:
        print(f"JSON report written to: {args.json}")
    return 0 if report["ready_for_pair_review"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
