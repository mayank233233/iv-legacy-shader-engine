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

# Guard the fallback-path null terminators against multi-character wide literals.
malformed_null_literal = "L'" + chr(92) + chr(92) + "0'"
correct_null_literal = "L'" + chr(92) + "0'"
if malformed_null_literal in source:
    fail("fallback path contains a malformed multi-character wide null literal")
if "g_shaderFallbackIniPath[0] == " + correct_null_literal + ")" not in source:
    fail("fallback INI path guard must compare against the wide null character")
if "resolvedPath[0] = " + correct_null_literal + ";" not in source:
    fail("resolved fallback path must be initialized with the wide null character")

# Guard the render-target telemetry null terminator against the same
# multi-character-literal typo in narrow character constants.
malformed_narrow_null_literal = "'" + chr(92) + chr(92) + "0'"
correct_narrow_null_literal = "'" + chr(92) + "0'"
if malformed_narrow_null_literal in source:
    fail("render-target telemetry contains a malformed multi-character null literal")
if "depthTargetBinding[0] == " + correct_narrow_null_literal not in source:
    fail("depth target telemetry must use a single null character escape")

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
    "SET_VIEWPORT",
    "HookDeviceSetViewport",
    "SurfaceSnapshot",
    "UpdateSurfaceSnapshot",
    "ClearSurfaceSnapshot",
    "FormatSurfaceSnapshot",
    "CaptureCurrentSurfaceState",
    "kDeviceSetViewportSlot = 47",
    "kDeviceGetRenderTargetSlot = 38",
    "kDeviceGetDepthStencilSurfaceSlot = 40",
    "DeviceGetRenderTargetFn",
    "DeviceGetDepthStencilSurfaceFn",
    "char message[3072]",
    "char line[3328]",
    "render_targets=%s",
    "depth_target=%s",
    "DEVICE_RESET_REQUEST",
    "CaptureShaderBytecode",
    "CaptureMaxFiles",
    "EnableShaderFallbacks",
    "LoadConfiguredPS2Fallback",
    "ValidateSM20FallbackBytecode",
    "LoadConfiguredSM20Fallback",
    "LoadConfiguredPS2Fallback",
    "LoadConfiguredVS2Fallback",
    "VertexShaderFallbacks",
    "VERTEX_SHADER_FALLBACK_ATTEMPT",
    "VERTEX_SHADER_FALLBACK_APPLIED",
    "VERTEX_SHADER_FALLBACK_OBJECT_MAP",
    "SHADER_FALLBACK_ATTEMPT",
    "SHADER_FALLBACK_APPLIED",
    "SHADER_FALLBACK_OBJECT_MAP",
    "SHADER_FALLBACK_NOT_MAPPED",
    "SHADER_FALLBACK_CREATE_FAILED",
    "SHADER_FALLBACKS_DISABLED reason=strict_version_gate_disabled",
    "CaptureDrawTelemetry",
    "CaptureDrawMaxCalls",
    "EnableFrameProfiler",
    "FrameProfilerWindowFrames",
    "EnableRedundantStateCache",
    "EnableBindingCache",
    "BINDING_CACHE_ENABLED",
    "BINDING_CACHE_DISABLED reason=state_block_api_used",
    "BINDING_CACHE_DISABLED reason=d3dcreate_multithreaded",
    "BINDING_CACHE_DISABLED reason=multiple_device_threads",
    "BINDING_CACHE_DISABLED reason=multiple_device_objects",
    "SHADER_CONSTANT_CACHE_DISABLED reason=multiple_device_objects",
    "SHADER_CONSTANT_CACHE_DISABLED reason=multiple_device_threads",
    "SHADER_CONSTANT_CACHE_DISABLED reason=d3dcreate_multithreaded",
    "SHADER_CONSTANT_CACHE_DISABLED reason=state_block_api_used",
    "SHADER_CONSTANT_CACHE_DISABLED reason=strict_version_gate_disabled",
    "EnableShaderConstantCache",
    "SHADER_CONSTANT_CACHE_ENABLED",
    "D3D9_SHADER_CONSTANT_CACHE_WINDOW",
    "SetShaderFloatConstantsWithCache",
    "SetShaderIntegerConstantsWithCache",
    "SetShaderBooleanConstantsWithCache",
    "InvalidateShaderConstantCache",
    "RecordShaderConstantCacheWindow",
    "BINDING_CACHE_DISABLED reason=strict_version_gate_disabled",
    "STATE_CACHE_DISABLED reason=strict_version_gate_disabled",
    "D3DCREATE_MULTITHREADED",
    "RecordBindingCacheWindow",
    "InvalidateBindingCache",
    "BindingCacheThreadAllowed",
    "shaderConstantCache ? !g_shaderConstantCacheEnabled : !g_bindingCacheEnabled",
    "D3D9_BINDING_CACHE_WINDOW",
    "StateCacheReportFrames",
    "D3D9_STATE_CACHE_WINDOW",
    "STATE_CACHE_DISABLED reason=state_block_api_used",
    "STATE_CACHE_DISABLED reason=multiple_device_threads",
    "SetRenderStateWithCache",
    "SetTextureStageStateWithCache",
    "SetSamplerStateWithCache",
    "InvalidateRedundantStateCache",
    "HookDeviceCreateStateBlock",
    "HookDeviceBeginStateBlock",
    "HookDeviceEndStateBlock",
    "kDeviceGetRenderStateSlot = 58",
    "kDeviceCreateStateBlockSlot = 59",
    "kDeviceBeginStateBlockSlot = 60",
    "kDeviceEndStateBlockSlot = 61",
    "STATE_BLOCK_BEGIN_FORWARD",
    "STATE_BLOCK_BEGIN_RETURN",
    "D3DTEXTURESTAGESTATETYPE state",
    "D3DDEVCAPS_HWTRANSFORMANDLIGHT",
    "HWTransformAndLight=%u",
    "RecordFrameProfile",
    "BeginDrawTiming",
    "EndDrawTiming",
    "FRAME_PROFILE_WINDOW",
    "gpu_time=not_measured",
    "request_software_vp=%u",
    "CaptureShaderConstants",
    "CaptureShaderConstantMaxRecords",
    "CaptureShaderIntegerConstantRange",
    "CaptureShaderBooleanConstantRange",
    "HookDeviceSetVertexShaderConstantI",
    "HookDeviceSetVertexShaderConstantB",
    "HookDeviceSetPixelShaderConstantI",
    "HookDeviceSetPixelShaderConstantB",
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
    "HookDeviceSetRenderState",
    "HookDeviceSetTextureStageState",
    "HookDeviceCreateVertexDeclaration",
    "HookDeviceSetVertexDeclaration",
    "HookDeviceSetFVF",
    "HookDeviceSetStreamSource",
    "HookDeviceSetStreamSourceFreq",
    "HookDeviceSetIndices",
    "HookDeviceCreateVertexBuffer",
    "HookDeviceCreateIndexBuffer",
    "BUFFER_OBJECT_CREATED",
    "VERTEX_DECL_ELEMENT",
    "renderStateHash",
    "textureStageHash",
    "TEXTURE_OBJECT_CREATED",
    "HookDeviceSetTexture",
    "HookDeviceSetVertexShader",
    "HookDeviceSetPixelShader",
    "HookDeviceSetVertexDeclaration",
    "HookDeviceSetFVF",
    "HookDeviceSetSamplerState",
    "g_textureBindingKnown",
    "g_streamFrequencyKnown",
    "g_indicesBindingKnown",
    "g_vertexShaderBindingKnown",
    "g_pixelShaderBindingKnown",
    "g_vertexFormatBindingKnown",
    "g_bindingCacheForwarded",
    "g_bindingCacheSkipped",
    "g_shaderConstantCacheForwarded",
    "g_shaderConstantCacheSkipped",
    "g_cachedShaderFloatConstants",
    "g_cachedShaderIntegerConstants",
    "g_cachedShaderBooleanConstants",
    "HookDeviceSetVertexShaderConstantF",
    "HookDeviceSetPixelShaderConstantF",
    "HookDeviceSetVertexShaderConstantI",
    "HookDeviceSetPixelShaderConstantI",
    "HookDeviceSetVertexShaderConstantB",
    "HookDeviceSetPixelShaderConstantB",
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

if "BuildSyntheticVs3Shader();" not in smoke_source or "g_syntheticVs3VertexShader" not in smoke_source:
    fail("synthetic runtime test must create a VS3 vertex shader input")
if "device->GetRenderState(" not in smoke_source or "GetRenderState slot 58 was overwritten" not in smoke_source:
    fail("synthetic runtime test must prove GetRenderState slot 58 remains intact")
if "device->CreateStateBlock(" not in smoke_source or "device->EndStateBlock(" not in smoke_source:
    fail("synthetic runtime test must exercise CreateStateBlock and EndStateBlock in addition to BeginStateBlock")
if "g_fakeLastVertexShaderVersion" not in smoke_source or "mappedVertexShaderVersion != 0xFFFE0200UL" not in smoke_source:
    fail("synthetic runtime test must verify the VS3-to-VS2 fallback profile")
if 'L"VertexShaderFallbacks"' not in smoke_source or "VERTEX_SHADER_FALLBACK_APPLIED" not in smoke_source:
    fail("synthetic runtime test must exercise the vertex-shader fallback map")

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
    "kDeviceSetVertexShaderConstantISlot = 96",
    "kDeviceSetVertexShaderConstantBSlot = 98",
    "kDeviceSetPixelShaderConstantFSlot = 109",
    "kDeviceSetPixelShaderConstantISlot = 111",
    "kDeviceSetPixelShaderConstantBSlot = 113",
    "kDeviceCreateTextureSlot = 23",
    "kDeviceCreateVolumeTextureSlot = 24",
    "kDeviceCreateCubeTextureSlot = 25",
    "kDeviceSetRenderStateSlot = 57",
    "kDeviceGetRenderStateSlot = 58",
    "kDeviceCreateStateBlockSlot = 59",
    "kDeviceBeginStateBlockSlot = 60",
    "kDeviceEndStateBlockSlot = 61",
    "kDeviceSetTextureStageStateSlot = 67",
    "kDeviceCreateVertexDeclarationSlot = 86",
    "kDeviceSetVertexDeclarationSlot = 87",
    "kDeviceSetFVFSlot = 89",
    "kDeviceSetStreamSourceSlot = 100",
    "kDeviceSetStreamSourceFreqSlot = 102",
    "kDeviceSetIndicesSlot = 104",
    "kDeviceCreateVertexBufferSlot = 26",
    "kDeviceCreateIndexBufferSlot = 27",
    "kDeviceGetRenderTargetSlot = 38",
    "kDeviceGetDepthStencilSurfaceSlot = 40",
    "DeviceGetRenderTargetFn",
    "DeviceGetDepthStencilSurfaceFn",
    "CaptureCurrentSurfaceState",
    "original[kDeviceCreateVertexBufferSlot]",
    "original[kDeviceCreateIndexBufferSlot]",
    "original[kDeviceCreateVertexDeclarationSlot]",
    "original[kDeviceSetVertexDeclarationSlot]",
    "original[kDeviceSetFVFSlot]",
    "original[kDeviceSetStreamSourceSlot]",
    "original[kDeviceSetStreamSourceFreqSlot]",
    "original[kDeviceSetIndicesSlot]",
    "original[kDeviceCreateTextureSlot]",
    "original[kDeviceCreateVolumeTextureSlot]",
    "original[kDeviceCreateCubeTextureSlot]",
    "original[kDeviceCreateVertexShaderSlot]",
    "original[kDeviceCreatePixelShaderSlot]",
    "hooked[kDeviceCreateVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceCreateVertexShader)",
    "hooked[kDeviceCreatePixelShaderSlot] = reinterpret_cast<void*>(HookDeviceCreatePixelShader)",
    "hooked[kDeviceSetVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceSetVertexShader)",
    "hooked[kDeviceSetPixelShaderSlot] = reinterpret_cast<void*>(HookDeviceSetPixelShader)",
    "hooked[kDeviceDrawPrimitiveSlot] =",
    "reinterpret_cast<void*>(HookDeviceDrawPrimitive)",
    "hooked[kDeviceDrawIndexedPrimitiveSlot] =",
    "reinterpret_cast<void*>(HookDeviceDrawIndexedPrimitive)",
    "hooked[kDeviceDrawPrimitiveUPSlot] =",
    "reinterpret_cast<void*>(HookDeviceDrawPrimitiveUP)",
    "hooked[kDeviceDrawIndexedPrimitiveUPSlot] =",
    "reinterpret_cast<void*>(HookDeviceDrawIndexedPrimitiveUP)",
    "hooked[kDeviceSetViewportSlot] = reinterpret_cast<void*>(HookDeviceSetViewport)",
    "hooked[kDeviceSetTextureSlot] = reinterpret_cast<void*>(HookDeviceSetTexture)",
    "hooked[kDeviceSetStreamSourceSlot] = reinterpret_cast<void*>(HookDeviceSetStreamSource)",
    "hooked[kDeviceSetStreamSourceFreqSlot] =",
    "hooked[kDeviceSetIndicesSlot] = reinterpret_cast<void*>(HookDeviceSetIndices)",
    "if (g_captureShaderConstants || g_shaderConstantCacheEnabled)",
    "hooked[kDeviceSetVertexShaderSlot] = reinterpret_cast<void*>(HookDeviceSetVertexShader)",
    "hooked[kDeviceSetPixelShaderSlot] = reinterpret_cast<void*>(HookDeviceSetPixelShader)",
    "hooked[kDeviceSetVertexDeclarationSlot] =",
    "hooked[kDeviceSetFVFSlot] = reinterpret_cast<void*>(HookDeviceSetFVF)",
    "hooked[kDeviceSetSamplerStateSlot] = reinterpret_cast<void*>(HookDeviceSetSamplerState)",
    "hooked[kDeviceCreateTextureSlot] = reinterpret_cast<void*>(HookDeviceCreateTexture)",
    "hooked[kDeviceCreateVolumeTextureSlot] = reinterpret_cast<void*>(HookDeviceCreateVolumeTexture)",
    "hooked[kDeviceCreateCubeTextureSlot] = reinterpret_cast<void*>(HookDeviceCreateCubeTexture)",
    "hooked[kDeviceSetRenderStateSlot] = reinterpret_cast<void*>(HookDeviceSetRenderState)",
    "hooked[kDeviceCreateStateBlockSlot] = reinterpret_cast<void*>(HookDeviceCreateStateBlock)",
    "hooked[kDeviceBeginStateBlockSlot] = reinterpret_cast<void*>(HookDeviceBeginStateBlock)",
    "hooked[kDeviceEndStateBlockSlot] = reinterpret_cast<void*>(HookDeviceEndStateBlock)",
    "hooked[kDeviceSetTextureStageStateSlot] = reinterpret_cast<void*>(HookDeviceSetTextureStageState)",
    "hooked[kDeviceCreateVertexDeclarationSlot] =",
    "hooked[kDeviceSetVertexDeclarationSlot] =",
    "hooked[kDeviceSetFVFSlot] =",
    "hooked[kDeviceSetStreamSourceSlot] =",
    "hooked[kDeviceSetStreamSourceFreqSlot] =",
    "hooked[kDeviceSetIndicesSlot] =",
    "hooked[kDeviceCreateVertexBufferSlot] =",
    "hooked[kDeviceCreateIndexBufferSlot] =",
    "hooked[kDeviceSetVertexShaderConstantFSlot] =",
    "hooked[kDeviceSetPixelShaderConstantFSlot] =",
    "hooked[kDeviceSetVertexShaderConstantISlot] =",
    "hooked[kDeviceSetVertexShaderConstantBSlot] =",
    "hooked[kDeviceSetPixelShaderConstantISlot] =",
    "hooked[kDeviceSetPixelShaderConstantBSlot] =",
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
    "g_fakeDeviceVTable[57] = reinterpret_cast<void*>(FakeDeviceSetRenderState)",
    "g_fakeDeviceVTable[58] = reinterpret_cast<void*>(FakeDeviceGetRenderState)",
    "g_fakeDeviceVTable[59] = reinterpret_cast<void*>(FakeDeviceCreateStateBlock)",
    "g_fakeDeviceVTable[60] = reinterpret_cast<void*>(FakeDeviceBeginStateBlock)",
    "g_fakeDeviceVTable[61] = reinterpret_cast<void*>(FakeDeviceEndStateBlock)",
    "g_fakeDeviceVTable[67] = reinterpret_cast<void*>(FakeDeviceSetTextureStageState)",
    "g_fakeDeviceVTable[86] = reinterpret_cast<void*>(FakeDeviceCreateVertexDeclaration)",
    "g_fakeDeviceVTable[87] = reinterpret_cast<void*>(FakeDeviceSetVertexDeclaration)",
    "g_fakeDeviceVTable[89] = reinterpret_cast<void*>(FakeDeviceSetFVF)",
    "g_fakeDeviceVTable[100] = reinterpret_cast<void*>(FakeDeviceSetStreamSource)",
    "g_fakeDeviceVTable[102] = reinterpret_cast<void*>(FakeDeviceSetStreamSourceFreq)",
    "g_fakeDeviceVTable[104] = reinterpret_cast<void*>(FakeDeviceSetIndices)",
    "g_fakeDeviceVTable[26] = reinterpret_cast<void*>(FakeDeviceCreateVertexBuffer)",
    "g_fakeDeviceVTable[27] = reinterpret_cast<void*>(FakeDeviceCreateIndexBuffer)",
    "g_fakeDeviceVTable[38] = reinterpret_cast<void*>(FakeDeviceGetRenderTarget)",
    "g_fakeDeviceVTable[40] = reinterpret_cast<void*>(FakeDeviceGetDepthStencilSurface)",
    "InterlockedIncrement(&g_fakeGetRenderTargetCount)",
    "InterlockedIncrement(&g_fakeGetDepthStencilSurfaceCount)",
    'return Fail("initial surface inventory did not call the typed D3D9 getter slots")',
    'return Fail("surface inventory was not refreshed after successful Reset")',
    "device->CreateVertexBuffer(",
    "device->CreateIndexBuffer(",
    'HasText("BUFFER_OBJECT_CREATED type=VB")',
    'HasText("BUFFER_OBJECT_CREATED type=IB")',
    "device->CreateVertexDeclaration(",
    "device->SetVertexDeclaration(",
    "device->SetFVF(",
    "device->SetStreamSource(",
    "device->SetStreamSourceFreq(",
    "device->SetIndices(",
    "D3DVERTEXELEMENT9 declarationElements[3]",
    'HasText("VERTEX_DECL_ELEMENT")',
    "device->CreateTexture(",
    "device->SetRenderState(",
    "device->SetTextureStageState(",
    'HasText("TEXTURE_OBJECT_CREATED type=2D")',
    "device->SetTexture(",
    "device->SetSamplerState(",
    "device->SetVertexShaderConstantF(",
    "device->SetPixelShaderConstantF(",
    "device->SetVertexShaderConstantI(",
    "device->SetPixelShaderConstantI(",
    "device->SetVertexShaderConstantB(",
    "device->SetPixelShaderConstantB(",
    'L"General", L"EnableRedundantStateCache", L"1"',
    'L"General", L"EnableBindingCache", L"1"',
    'L"General", L"EnableShaderConstantCache", L"1"',
    'L"General", L"StateCacheReportFrames", L"1"',
    "vertex float-constant cache did not skip exact ranges",
    "pixel float-constant cache did not skip exact ranges",
    "vertex integer-constant cache did not skip exact ranges",
    "pixel integer-constant cache did not skip exact ranges",
    "vertex boolean-constant cache did not skip exact ranges",
    "pixel boolean-constant cache did not skip exact ranges",
    "Reset did not invalidate shader-constant range cache state",
    "state-block API use did not disable shader-constant suppression",
    "g_fakeSetTextureCalls",
    "g_fakeSetStreamSourceCalls",
    "g_fakeSetStreamSourceFreqCalls",
    "stream-frequency cache did not suppress identical divider state",
    "Reset did not invalidate stream-frequency cache state",
    "state-block API use did not disable stream-frequency suppression",
    "stream_freq_forwarded=3 stream_freq_skipped=3",
    "g_fakeSetIndicesCalls",
    "g_fakeSetVertexShaderCalls",
    "g_fakeSetPixelShaderCalls",
    "g_fakeSetVertexDeclarationCalls",
    "g_fakeSetFVFCalls",
    "texture binding cache did not suppress duplicate bindings",
    "vertex-stream cache did not compare buffer, offset and stride",
    "index-buffer cache did not suppress duplicate and preserve changed bindings",
    "vertex-shader binding cache did not suppress duplicates",
    "pixel-shader binding cache did not suppress duplicates",
    "vertex-declaration cache did not suppress identical layout bindings",
    "FVF cache did not suppress identical FVF bindings",
    "Reset did not invalidate vertex-shader binding cache state",
    "state-block API use did not disable shader-binding suppression",
    "Reset did not invalidate texture-binding cache state",
    "state-block API use did not disable texture-binding suppression",
    "device->BeginStateBlock(",
    "g_fakeSetRenderStateCalls",
    "g_fakeSetTextureStageStateCalls",
    "g_fakeSetSamplerStateCalls",
    "STATE_CACHE_DISABLED reason=state_block_api_used",
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
    'L"General", L"EnableFrameProfiler", L"1"',
    'L"General", L"FrameProfilerWindowFrames", L"1"',
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
    'HasText("FRAME_PROFILE_WINDOW samples=1")',
    'HasText("avg_draw_calls=4.00")',
    'HasText("gpu_time=not_measured")',
)
for marker in expected_draw_test_markers:
    if marker not in smoke_source:
        fail(f"synthetic D3D9 draw telemetry coverage is missing: {marker}")


if "caps->PixelShaderVersion =" in source or "caps->VertexShaderVersion =" in source:
    fail("telemetry plugin must not spoof shader-model capabilities")

if "/LD" not in build or "IVLegacyASI.asi" not in build or "version.lib" not in build:
    fail("ASI build script must produce a version-resource-enabled x86 DLL")

print("PASS: game-loaded ASI source, target gate, D3D9 telemetry hooks and no-cap-spoof rule")
