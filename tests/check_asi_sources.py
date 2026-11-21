from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src" / "IVLegacyASI.cpp"
BUILD = ROOT / "build" / "build_asi.bat"
SMOKE_SOURCE = ROOT / "tests" / "asi_runtime_smoke.cpp"
SMOKE_RESOURCE = ROOT / "tests" / "test_gtaiv_version.rc"

def fail(message: str) -> None:
    print(f"FAIL: {message}")
    raise SystemExit(1)

if not SOURCE.is_file():
    fail("missing game-loaded ASI source")
if not BUILD.is_file():
    fail("missing x86 ASI build script")
if not SMOKE_SOURCE.is_file() or not SMOKE_RESOURCE.is_file():
    fail("missing D3D9 ASI runtime smoke-test source or version resource")

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
    "EnableShaderFallbacks",
    "LoadConfiguredPS2Fallback",
    "ValidatePS20FallbackBytecode",
    "SHADER_FALLBACK_ATTEMPT",
    "SHADER_FALLBACK_APPLIED",
    "SHADER_FALLBACK_OBJECT_MAP",
    "SHADER_FALLBACK_NOT_MAPPED",
    "SHADER_FALLBACK_CREATE_FAILED",
    "SHADER_FALLBACKS_DISABLED reason=strict_version_gate_disabled",
    "CaptureDrawTelemetry",
    "CaptureDrawMaxCalls",
    "CaptureShaderConstants",
    "CaptureShaderConstantMaxRecords",
    "g_shaderConstantCaptureSession",
    "GetSystemTimeAsFileTime",
    "IVLegacyConstants",
    "SHADER_CONSTANT_CAPTURE_ENABLED",
    "SHADER_CONSTANT_CAPTURED",
    "header.version = 2",
    "header.shaderObject",
    "shader_object=%p",
    "CaptureShaderConstantRange",
    "HookDeviceCreateTexture",
    "HookDeviceCreateVolumeTexture",
    "HookDeviceCreateCubeTexture",
    "TEXTURE_OBJECT_CREATED",
    "HookDeviceSetTexture",
    "HookDeviceSetSamplerState",
    "HookDeviceSetVertexShaderConstantF",
    "HookDeviceSetPixelShaderConstantF",
    "SHADER_OBJECT_CREATED",
    "LogDrawTelemetry",
    "g_presentFrameIndex",
    "frameIndex",
    "HookDeviceDrawPrimitive",
    "HookDeviceDrawIndexedPrimitive",
    "HookDeviceDrawPrimitiveUP",
    "HookDeviceDrawIndexedPrimitiveUP",
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

if 'extern "C" __declspec(dllexport) void InitializeASI()' not in source:
    fail("ASI must directly export the C-linkage InitializeASI entry point")
if 'GetProcAddress(asi, "InitializeASI")' not in SMOKE_SOURCE.read_text(encoding="utf-8"):
    fail("synthetic runtime smoke test must resolve InitializeASI by its public export name")

smoke_source = SMOKE_SOURCE.read_text(encoding="utf-8")
if "BuildSyntheticPs3Shader();" not in smoke_source:
    fail("synthetic runtime test must construct a PS3 pixel shader source")
if "mappedShaderVersion != 0xFFFF0200UL" not in smoke_source:
    fail("synthetic runtime test must verify PS2 bytecode was substituted")
if "unmappedShaderVersion != 0xFFFF0300UL" not in smoke_source:
    fail("synthetic runtime test must verify unmapped PS3 bytecode passes through unchanged")
if "EnableShaderFallbacks" not in smoke_source or "ShaderFallbacks" not in smoke_source:
    fail("synthetic runtime test must create an explicit opt-in fallback map")
if "SHADER_FALLBACK_OBJECT_MAP" not in smoke_source or "profile=PS_2_0" not in smoke_source:
    fail("synthetic runtime test must verify shader-object to actual fallback-bytecode correlation")

if "wcscpy_s(g_gameDirectory, MAX_PATH, g_gamePath)" not in source:
    fail("path setup must preserve the full executable path for version validation")

required_vtable_bindings = (
    "kDeviceCreateVertexShaderSlot = 91",
    "kDeviceCreatePixelShaderSlot = 106",
    "kDeviceSetVertexShaderSlot = 92",
    "kDeviceSetPixelShaderSlot = 107",
    "kDeviceDrawPrimitiveSlot = 81",
    "kDeviceDrawIndexedPrimitiveSlot = 82",
    "kDeviceDrawPrimitiveUPSlot = 83",
    "kDeviceDrawIndexedPrimitiveUPSlot = 84",
    "kDeviceSetTextureSlot = 65",
    "kDeviceSetSamplerStateSlot = 69",
    "kDeviceSetVertexShaderConstantFSlot = 94",
    "kDeviceSetPixelShaderConstantFSlot = 109",
    "kDeviceCreateTextureSlot = 23",
    "kDeviceCreateVolumeTextureSlot = 24",
    "kDeviceCreateCubeTextureSlot = 25",
    "original[kDeviceCreateTextureSlot]",
    "original[kDeviceCreateVolumeTextureSlot]",
    "original[kDeviceCreateCubeTextureSlot]",
    "original[kDeviceCreateVertexShaderSlot]",
    "original[kDeviceCreatePixelShaderSlot]",
    "hooked[kDeviceCreateVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceCreateVertexShader)",
    "hooked[kDeviceCreatePixelShaderSlot] = reinterpret_cast<void*>(HookDeviceCreatePixelShader)",
    "hooked[kDeviceSetVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceSetVertexShader)",
    "hooked[kDeviceSetPixelShaderSlot] = reinterpret_cast<void*>(HookDeviceSetPixelShader)",
    "hooked[kDeviceDrawPrimitiveSlot] = reinterpret_cast<void*>(HookDeviceDrawPrimitive)",
    "hooked[kDeviceDrawIndexedPrimitiveSlot] = reinterpret_cast<void*>(HookDeviceDrawIndexedPrimitive)",
    "hooked[kDeviceDrawPrimitiveUPSlot] = reinterpret_cast<void*>(HookDeviceDrawPrimitiveUP)",
    "hooked[kDeviceDrawIndexedPrimitiveUPSlot] = reinterpret_cast<void*>(HookDeviceDrawIndexedPrimitiveUP)",
    "hooked[kDeviceSetTextureSlot] = reinterpret_cast<void*>(HookDeviceSetTexture)",
    "hooked[kDeviceSetSamplerStateSlot] = reinterpret_cast<void*>(HookDeviceSetSamplerState)",
    "hooked[kDeviceCreateTextureSlot] = reinterpret_cast<void*>(HookDeviceCreateTexture)",
    "hooked[kDeviceCreateVolumeTextureSlot] = reinterpret_cast<void*>(HookDeviceCreateVolumeTexture)",
    "hooked[kDeviceCreateCubeTextureSlot] = reinterpret_cast<void*>(HookDeviceCreateCubeTexture)",
    "hooked[kDeviceSetVertexShaderConstantFSlot] =",
    "hooked[kDeviceSetPixelShaderConstantFSlot] =",
)
for binding in required_vtable_bindings:
    if binding not in source:
        fail(f"incorrect or missing IDirect3DDevice9 shader vtable binding: {binding}")

smoke_source = SMOKE_SOURCE.read_text(encoding="utf-8")
if "g_fakeDeviceVTable[91] = reinterpret_cast<void*>(FakeDeviceCreateVertexShader)" not in smoke_source:
    fail("synthetic IDirect3DDevice9 CreateVertexShader slot is incorrect")
if "g_fakeDeviceVTable[106] = reinterpret_cast<void*>(FakeDeviceCreatePixelShader)" not in smoke_source:
    fail("synthetic IDirect3DDevice9 CreatePixelShader slot is incorrect")
expected_draw_test_markers = (
    "g_fakeDeviceVTable[65] = reinterpret_cast<void*>(FakeDeviceSetTexture)",
    "g_fakeDeviceVTable[69] = reinterpret_cast<void*>(FakeDeviceSetSamplerState)",
    "g_fakeDeviceVTable[94] = reinterpret_cast<void*>(FakeDeviceSetVertexShaderConstantF)",
    "g_fakeDeviceVTable[109] = reinterpret_cast<void*>(FakeDeviceSetPixelShaderConstantF)",
    "g_fakeDeviceVTable[23] = reinterpret_cast<void*>(FakeDeviceCreateTexture)",
    "device->CreateTexture(",
    'HasText("TEXTURE_OBJECT_CREATED type=2D")',
    "device->SetTexture(",
    "device->SetSamplerState(",
    "device->SetVertexShaderConstantF(",
    "device->SetPixelShaderConstantF(",
    'L"General", L"CaptureShaderConstants", L"1"',
    "IVLegacyConstants",
    "g_fakeDeviceVTable[81] = reinterpret_cast<void*>(FakeDeviceDrawPrimitive)",
    "g_fakeDeviceVTable[82] = reinterpret_cast<void*>(FakeDeviceDrawIndexedPrimitive)",
    "g_fakeDeviceVTable[83] = reinterpret_cast<void*>(FakeDeviceDrawPrimitiveUP)",
    "g_fakeDeviceVTable[84] = reinterpret_cast<void*>(FakeDeviceDrawIndexedPrimitiveUP)",
    "device->DrawPrimitive(",
    "device->DrawIndexedPrimitive(",
    "device->DrawPrimitiveUP(",
    "device->DrawIndexedPrimitiveUP(",
    'L"General", L"CaptureDrawTelemetry", L"1"',
    'L"General", L"CaptureShaderConstants", L"1"',
    "g_fakeDeviceVTable[65] = reinterpret_cast<void*>(FakeDeviceSetTexture)",
    "g_fakeDeviceVTable[69] = reinterpret_cast<void*>(FakeDeviceSetSamplerState)",
    "g_fakeDeviceVTable[94] = reinterpret_cast<void*>(FakeDeviceSetVertexShaderConstantF)",
    "g_fakeDeviceVTable[109] = reinterpret_cast<void*>(FakeDeviceSetPixelShaderConstantF)",
    "device->SetTexture(",
    "device->SetSamplerState(",
    "device->SetVertexShaderConstantF(",
    "device->SetPixelShaderConstantF(",
    'HasText("frame=1")',
)
for marker in expected_draw_test_markers:
    if marker not in smoke_source:
        fail(f"synthetic D3D9 draw telemetry coverage is missing: {marker}")


if "caps->PixelShaderVersion =" in source or "caps->VertexShaderVersion =" in source:
    fail("telemetry plugin must not spoof shader-model capabilities")

if "/LD" not in build or "IVLegacyASI.asi" not in build or "version.lib" not in build:
    fail("ASI build script must produce a version-resource-enabled x86 DLL")

print("PASS: game-loaded ASI source, target gate, D3D9 telemetry hooks and no-cap-spoof rule")
