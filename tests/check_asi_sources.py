from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "IVLegacyASI.cpp"
BUILD = ROOT / "build" / "build_asi.bat"

def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)

if not SOURCE.is_file():
    fail("missing game-loaded ASI source")
if not BUILD.is_file():
    fail("missing x86 ASI build script")

source = SOURCE.read_text(encoding="utf-8")
build = BUILD.read_text(encoding="utf-8")

required_source_markers = (
    "GTAIV.exe",
    "version_is_not_1.0.0.0",
    "Direct3DCreate9",
    "D3D9_GET_DEVICE_CAPS",
    "D3D9_CREATE_DEVICE_REQUEST",
    "CREATE_VERTEX_SHADER",
    "CREATE_PIXEL_SHADER",
    "CREATE_RENDER_TARGET",
    "SET_RENDER_TARGET",
    "DEVICE_RESET_REQUEST",
    "StrictGTAIV100",
    "EnableD3D9Telemetry",
    "HookD3D9Import",
    "D3D9_INTERFACE_HOOK_INSTALLED",
    "D3D9_DEVICE_HOOK_INSTALLED",
)

for marker in required_source_markers:
    if marker not in source:
        fail(f"required telemetry hook marker missing: {marker}")

if "caps->PixelShaderVersion =" in source or "caps->VertexShaderVersion =" in source:
    fail("telemetry plugin must not spoof shader-model capabilities")

if "/LD" not in build or "IVLegacyASI.asi" not in build or "version.lib" not in build:
    fail("ASI build script must produce a version-resource-enabled x86 DLL")

print("PASS: game-loaded ASI source, target gate, D3D9 telemetry hooks and no-cap-spoof rule")
