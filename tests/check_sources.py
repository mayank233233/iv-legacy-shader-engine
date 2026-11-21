from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
SHADERS = {
    "basic_vs20.hlsl": "vs_2_0",
    "flat_lod_vs20.hlsl": "vs_2_0",
    "basic_ps20.hlsl": "ps_2_0",
    "unlit_ps20.hlsl": "ps_2_0",
    "water_ps20.hlsl": "ps_2_0",
    "flat_lod_ps20.hlsl": "ps_2_0",
}


def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)


compile_script = (ROOT / "build" / "compile_shaders.bat").read_text(encoding="utf-8")
cpp = (ROOT / "src" / "D3D9ShaderProbe.cpp").read_text(encoding="utf-8")

for filename, profile in SHADERS.items():
    path = ROOT / "shaders" / filename
    if not path.is_file():
        fail(f"missing shader: {filename}")
    expected_entry = rf":compile\s+shaders\\{re.escape(filename)}\s+\w+\s+{re.escape(profile)}\b"
    if not re.search(expected_entry, compile_script, flags=re.IGNORECASE):
        fail(f"compile script does not map {filename} to {profile}")

for marker in (
    "bin\\x86\\fxc.exe",
    "%WindowsSDKVersion%x86\\fxc.exe",
    "Microsoft DirectX SDK (June 2010)",
    "UnlockRect",
    "unlockHr",
    "ADAPTER_IDENTIFIER_FAIL",
    "MaxFixedFunctionTextures",
    "D3DCREATE_SOFTWARE_VERTEXPROCESSING",
    "D3DCREATE_HARDWARE_VERTEXPROCESSING",
    "WATER_TWO_TEXTURE_ALPHA_BLEND",
    "_DRAW_PRESENT_PASSED",
    "_READBACK_AVAILABLE",
    "_PIXEL_CHANGED",
):
    if marker not in compile_script and marker not in cpp:
        fail(f"required v0.3 marker missing: {marker}")

if "ps_3_0" in compile_script or "vs_3_0" in compile_script or "ps_2_x" in compile_script:
    fail("unexpected shader profile in compile script")

if len(re.findall(r"call :compile shaders\\", compile_script, flags=re.IGNORECASE)) != 6:
    fail("expected exactly six FXC compile entries")

print("PASS: six shader sources, SM2 compile entries and v0.3 probe markers are present")
