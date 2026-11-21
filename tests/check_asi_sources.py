from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "IVLegacyASI.cpp"
BUILD = ROOT / "build" / "build_asi.bat"
SMOKE_SOURCE = ROOT / "tests" / "asi_runtime_smoke.cpp"
SMOKE_RESOURCE = ROOT / "tests" / "test_gtaiv_version.rc"
EXPORT_DEF = ROOT / "src" / "IVLegacyASI.def"

def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)

if not SOURCE.is_file():
    fail("missing game-loaded ASI source")
if not BUILD.is_file():
    fail("missing x86 ASI build script")
if not SMOKE_SOURCE.is_file() or not SMOKE_RESOURCE.is_file() or not EXPORT_DEF.is_file():
    fail("missing D3D9 ASI runtime smoke-test source, version resource or export definition")

source = SOURCE.read_text(encoding="utf-8")
build = BUILD.read_text(encoding="utf-8")

required_source_markers = (
    "GTAIV.exe",
    "InitializePluginOnce",
    "BootstrapWorkerThread",
    "g_bootstrapStarted",
    "g_bootstrapCompleted",
    "TARGET_VERSION_MISMATCH",
    "Direct3DCreate9",
    "D3D9_ADAPTER",
    "D3D9_CHECK_DEVICE_FORMAT",
    "D3D9_CHECK_DEPTH_MATCH",
    "D3D9_GET_DEVICE_CAPS",
    "D3D9_CREATE_DEVICE_REQUEST",
    "CREATE_VERTEX_SHADER",
    "CREATE_PIXEL_SHADER",
    "CREATE_RENDER_TARGET",
    "CREATE_DEPTH_STENCIL_SURFACE",
    "SET_DEPTH_STENCIL_SURFACE",
    "SET_RENDER_TARGET",
    "DEVICE_RESET_REQUEST",
    "CaptureShaderBytecode",
    "CaptureMaxFiles",
    "SHADER_CAPTURE_ENABLED",
    "SHADER_CAPTURED",
    "StrictGTAIV100",
    "EnableD3D9Telemetry",
    "HookD3D9Import",




    "D3D9_INTERFACE_HOOK_INSTALLED",
    "D3D9_DEVICE_HOOK_INSTALLED",
    "D3D9_CHECK_DEVICE_FORMAT",
    "D3D9_CHECK_DEPTH_MATCH",
)

for marker in required_source_markers:
    if marker not in source:
        fail(f"required telemetry hook marker missing: {marker}")

export_definition = EXPORT_DEF.read_text(encoding="utf-8")
if "InitializeASI=_InitializeASI" not in export_definition:
    fail("x86 module definition must export undecorated InitializeASI")
if "src\\IVLegacyASI.def" not in build:
    fail("ASI build must link the InitializeASI module definition")
if 'GetProcAddress(asi, "InitializeASI")' not in SMOKE_SOURCE.read_text(encoding="utf-8"):
    fail("synthetic runtime smoke test must resolve InitializeASI by its public export name")

if "wcscpy_s(g_gameDirectory, MAX_PATH, g_gamePath)" not in source:
    fail("path setup must preserve the full executable path for version validation")

required_vtable_bindings = (
    "kDeviceCreateVertexShaderSlot = 91",
    "kDeviceCreatePixelShaderSlot = 106",
    "kDeviceSetVertexShaderSlot = 92",
    "kDeviceSetPixelShaderSlot = 107",
    "original[kDeviceCreateVertexShaderSlot]",
    "original[kDeviceCreatePixelShaderSlot]",
    "hooked[kDeviceCreateVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceCreateVertexShader)",
    "hooked[kDeviceCreatePixelShaderSlot] = reinterpret_cast<void*>(HookDeviceCreatePixelShader)",
    "hooked[kDeviceSetVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceSetVertexShader)",
    "hooked[kDeviceSetPixelShaderSlot] = reinterpret_cast<void*>(HookDeviceSetPixelShader)",
)
for binding in required_vtable_bindings:
    if binding not in source:
        fail(f"incorrect or missing IDirect3DDevice9 shader vtable binding: {binding}")

smoke_source = SMOKE_SOURCE.read_text(encoding="utf-8")
if "g_fakeDeviceVTable[91] = reinterpret_cast<void*>(FakeDeviceCreateVertexShader)" not in smoke_source:
    fail("synthetic IDirect3DDevice9 CreateVertexShader slot is incorrect")
if "g_fakeDeviceVTable[106] = reinterpret_cast<void*>(FakeDeviceCreatePixelShader)" not in smoke_source:
    fail("synthetic IDirect3DDevice9 CreatePixelShader slot is incorrect")

if "caps->PixelShaderVersion =" in source or "caps->VertexShaderVersion =" in source:
    fail("telemetry plugin must not spoof shader-model capabilities")

if "/LD" not in build or "IVLegacyASI.asi" not in build or "version.lib" not in build:
    fail("ASI build script must produce a version-resource-enabled x86 DLL")

print("PASS: game-loaded ASI source, target gate, D3D9 telemetry hooks and no-cap-spoof rule")
