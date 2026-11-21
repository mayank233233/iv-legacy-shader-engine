# IV Legacy Shader Engine — Prototype 0.5.4-alpha

**Target:** 32-bit Windows, Direct3D 9, Shader Model `vs_2_0` / `ps_2_0`.

Prototype 0.5.4-alpha combines the v0.3 standalone D3D9 probe with an experimental Win32/x86 telemetry ASI, shader inventory tools and a conservative offline pixel-shader downlevel audit. The intended game target is the **original PC release, GTAIV.exe file version 1.0.0.0**. The ASI validates that exact version by default. This is still a development foundation, not a playable compatibility fix: it does not inject SM2 replacements into GTA IV, spoof capabilities, or establish that the game can launch on Intel GMA 3100.

## Project contents

| Path | Purpose |
|---|---|
| `shaders/basic_vs20.hlsl` | Generic world/view/projection transform, vertex lighting, view-space fog factor |
| `shaders/basic_ps20.hlsl` | One-texture lit material and fog |
| `shaders/unlit_ps20.hlsl` | One-texture unlit material and fog |
| `shaders/water_ps20.hlsl` | Two-texture scrolling water approximation |
| `shaders/flat_lod_vs20.hlsl` | Position/vertex-colour transform for flat distant geometry |
| `shaders/flat_lod_ps20.hlsl` | Texture-free vertex-colour/fog pass |
| `src/D3D9ShaderProbe.cpp` | Standalone x86 D3D9 capability, shader-creation, draw/present and readback probe |
| `src/IVLegacyASI.cpp` | Experimental GTA IV 1.0.0.0 x86 ASI; main-executable D3D9 factory IAT hook, adapter/device telemetry, shader creation/binding observation and opt-in bounded capture |
| `build/compile_shaders.bat` | FXC compilation and assembly-listing generation for all six shaders |
| `build/build_probe.bat` | x86 MSVC standalone-probe build |
| `build/build_asi.bat` | x86 MSVC ASI/DLL build |
| `tools/analyze_d3d9_shaders.py` | Offline D3D9 SM2/SM3 token-stream inventory for compiled or captured shaders |
| `tools/audit_sm3_to_sm2.py` | Conservative offline audit/lowering candidate generator for a restricted `ps_3_0` pixel-shader subset; unsupported shaders are rejected, not guessed |
| `tools/analyze_asi_log.py` | Correlates shader-object hashes with frame-indexed D3D9 draw calls in `IVLegacy.log` |
| `tools/inspect_gtaiv_executable.py` | Read-only PE32 import/version inspector for the original `GTAIV.exe`; reports normal and delay imports without modifying the file |
| `tools/analyze_asi_constants.py` | Validates float, integer and boolean shader-constant sidecars and resolves them to shader hashes from `IVLegacy.log` |
| `build/run_probe.bat` | Launches the probe after checking its six bytecode files |
| `.github/workflows/windows-x86-build.yml` | Windows x86 compile/build CI; does not run the GPU probe |

All six v0.2 HLSL sources are retained byte-for-byte. They still target only `vs_2_0` and `ps_2_0`.

## v0.5.4-alpha changes

- Added opt-in vertex-input telemetry for D3D9 vertex declarations (slot 86), declaration binding (87), FVF (89), stream source (100), stream frequency (102) and index-buffer binding (104).
- Successful vertex-declaration creation logs each `D3DVERTEXELEMENT9` element: stream, byte offset, data type, method, usage and usage index. Reads are guarded and capped at 64 elements.
- Each draw record now includes the bound declaration pointer or FVF value, index-buffer pointer, and active stream buffer/offset/stride/frequency records.
- Successful device Reset clears declaration, FVF, stream and index-buffer state snapshots.
- Extended `tools/analyze_asi_log.py` to reconstruct vertex declarations and aggregate draw submissions by declaration/FVF layout, stream layout and index-buffer object.
- The synthetic runtime now creates and binds a two-element POSITION/TEXCOORD declaration, a vertex stream with stride 20 and frequency 1, and an index-buffer object. It draws once with the declaration, then switches to FVF `0x00000102` for later calls.
- Windows x86 CI run #165 passed all steps. Its synthetic draw report parsed one declaration with two elements, one stream binding (offset 0, stride 20, frequency 1), one index-buffer binding, and subsequent FVF-based draws.

This remains input-state telemetry only. It does not prove that a real GTA IV vertex declaration or vertex shader is compatible with SM2, and it does not convert any game shader.

## v0.5-alpha changes

- Added the exported C-linkage `InitializeASI` entry point used by Ultimate ASI Loader. A one-time bootstrap guard also supports loaders that only call `LoadLibrary`.
- The synthetic Windows x86 host resolves `InitializeASI` by its exact export name and calls it before using the hooked D3D9 factory.
- Added opt-in draw telemetry for `DrawPrimitive`, `DrawIndexedPrimitive`, `DrawPrimitiveUP` and `DrawIndexedPrimitiveUP` (D3D9 slots 81–84). Each bounded record includes primitive/count data and the currently bound vertex/pixel shader object addresses.
- Added shader-object creation records that pair the COM shader-object address with its profile, byte count and bytecode hash. This lets diagnostic draw records be correlated with the shader bytecode that created the object.
- Draw logging is disabled by default. Enable `CaptureDrawTelemetry=1` in `IVLegacy.ini`; `CaptureDrawMaxCalls` defaults to 4096 and is clamped to 1–65536.
- Added `tools/audit_sm3_to_sm2.py`, a deliberately restrictive offline pixel-shader downlevel audit. It can emit structurally eligible candidates only for a narrow, declared PS3-to-PS2 subset. It does not translate vertex shaders, arbitrary PS3 features, or unknown interfaces.
- Added frame tags to draw records (successful Present count) and `tools/analyze_asi_log.py` to map logged shader-object addresses to profile/hash records, then aggregate draws by shader pair, method, primitive type and frame.
- Added `tools/inspect_gtaiv_executable.py`, a read-only PE32 inspector for normal/delay imports and Windows file version. It can verify whether a local original `GTAIV.exe` has a direct D3D9 factory import; no game executable is bundled or modified.
- CI now tests the log correlator, PE import inspector, audit tool, ASI export, fake shader objects, all four draw hooks and captured bytecode inventory.

**The audit tool is not a general SM3 translator.** A passing structural audit is only a candidate for further validation; it does not prove visual equivalence or driver acceptance. The two captures in CI are synthetic SM2 test shaders. The audit reports zero eligible conversions for them: the pixel shader is already SM2 and the vertex shader is outside the pixel-only tool's scope.

The original GTA IV 1.0.0.0 executable and GMA 3100 driver have still not been tested. The ASI does not yet replace any GTA IV shader.

## v0.4-alpha changes

- Added a Win32/x86 ASI module with a strict-by-default GTAIV.exe file-version gate for the original PC 1.0.0.0 build.
- Added a main-executable IAT hook for direct d3d9.dll!Direct3DCreate9 imports, then per-object IDirect3D9 and IDirect3DDevice9 vtable instrumentation.
- Records adapter PCI identity, D3D9 capability queries, format checks, device creation, render/depth surface operations, Reset and failed Present calls.
- Observes both shader creation and shader binding. The shader creation hooks capture SM2/SM3 bytecode only when CaptureShaderBytecode=1 is explicitly enabled in IVLegacy.ini; capture has a configurable hard file cap and is disabled by default.
- Added an offline token-stream inventory tool for compiled/captured shader bytecode.
- Added a synthetic 32-bit GTAIV.exe test host. Windows x86 CI passes the ASI runtime smoke test and inventories two synthetic SM2 shaders.

The ASI has **not** been loaded into the actual GTA IV 1.0.0.0 executable. Its main-executable IAT assumption and load timing still need to be checked against that binary. It does not yet replace shaders or provide an SM3-to-SM2 compatibility path.

## v0.3 changes

- FXC discovery checks the common Windows 8.1 SDK `bin\x86` layout, versioned SDK layout, and both Program Files locations for the June 2010 DirectX SDK.
- Texture `UnlockRect` and readback `UnlockRect` HRESULTs are checked and reported.
- Adapter output includes vendor, device, subsystem and revision IDs, description, driver string and driver version. Adapter-identification failure is no longer silent.
- Fixed-function `MaxSimultaneousTextures` is reported as `MaxFixedFunctionTextures`; PS 2.0 extended-capability fields are logged separately.
- The HAL + software vertex-processing baseline is retained. A separate HAL + hardware vertex-processing run is attempted only when the reported caps pass the probe's hardware-VP gate. It never silently falls back to software VP.
- The test quad varies depth. Basic and flat-LOD tests use non-identity WVP/View matrices; the basic vertex test also uses non-uniform world scale and its inverse-transpose normal matrix.
- Test textures contain spatial colour and alpha patterns. Water UV offsets are non-zero, and samplers use wrap addressing.
- Water is tested once without blending and once with source-alpha blending.
- Draw/present success, readback availability and changed-centre-pixel counts are reported separately.
- A Windows x86 GitHub Actions workflow compiles all shaders and builds the x86 probe. It deliberately does not execute the probe on a hosted runner.

These are expanded diagnostics, not automated proofs of correct matrix math, image quality, or driver stability. The readback's centre pixel remains a smoke check.

## Build requirements

- Windows 8.1 or later with Direct3D 9 runtime support.
- 32-bit/x86 MSVC toolchain. **Visual Studio 2015 (Update 3) or newer** is required by the source's standard-library `std::snprintf` use.
- `fxc.exe` from a Windows SDK or the legacy DirectX SDK (June 2010).
- Direct3D 9 headers and import library (`d3d9.lib`), normally provided by the Windows SDK.

The target machine is expected to be Windows 8.1 x86, Intel GMA 3100 (`VEN_8086&DEV_29C2`), Pentium Dual-Core E5200, 3 GB RAM. The probe reports the actual adapter identity; do not infer the GPU solely from its display name.

## Build and run

Open an **x86 Native Tools Command Prompt** for Visual Studio, change to the repository root, then run:

```bat
build\compile_shaders.bat
build\build_probe.bat
build\build_asi.bat
build\run_probe.bat
```

The compiler script writes six bytecode files (`.vso` / `.pso`) and six FXC assembly listings into `build\out`. The C++ builds write `build\bin\D3D9ShaderProbe.exe` and `build\bin\IVLegacyASI.asi`. The probe writes `D3D9ProbeReport.txt` in the repository root. The ASI writes `IVLegacy.log` and creates `IVLegacy.ini` beside the game executable.

The FXC script searches `PATH`, the unversioned Windows SDK `bin\x86` path, the versioned SDK path, and common DirectX SDK June 2010 locations. If FXC is installed elsewhere, add its directory to `PATH`.

**Do not install the current ASI into the game yet.** The synthetic test verifies the exported loader entry point and D3D9 hook mechanisms, but the original GTAIV.exe import table, actual ASI-loader startup in the game and GMA 3100 driver have not been validated. The plugin does not yet replace any GTA IV shader.

## Test modes and report interpretation

### HAL + software vertex processing

This is the retained baseline. It uses `D3DCREATE_SOFTWARE_VERTEXPROCESSING` with a HAL device. It exercises Direct3D software vertex processing while retaining the driver's HAL rendering path; it is not the Direct3D reference rasterizer and is not a whole-renderer CPU fallback.

### HAL + hardware vertex processing

This is a distinct attempt using `D3DCREATE_HARDWARE_VERTEXPROCESSING`. It is attempted only if the adapter reports hardware transform/lighting and at least `vs_2_0`. A create or render failure is recorded; the probe does not substitute the software-VP result for it.

Each mode attempts five cases:

1. `BASIC_TEXTURED`
2. `UNLIT_TEXTURED`
3. `WATER_TWO_TEXTURE_OPAQUE`
4. `WATER_TWO_TEXTURE_ALPHA_BLEND`
5. `FLAT_LOD`

The summary fields mean:

- `*_DRAW_PRESENT_PASSED`: draw, `EndScene` and `Present` all returned success for the case.
- `*_READBACK_AVAILABLE`: the centre pixel was successfully copied and unlocked.
- `*_PIXEL_CHANGED`: the centre pixel differed from the clear colour.

A readback failure does not undo a successful draw/present result. A changed centre pixel does not prove that the rest of the image is correct. The readback supports only `X8R8G8B8` and `A8R8G8B8` backbuffers.

The adapter report separates fixed-function multitexture capability from the reported `PS20Caps` fields. The latter are diagnostic fields, not evidence that `ps_2_x` is supported.

## GitHub Actions verification

**Prototype 0.5.4-alpha Windows x86 CI passed** in [run #165](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44890714743), commit `0750df6203715f6e7986ef84ded862d6c9d8ec26`. All steps passed: six SM2 shaders compiled and inventoried; x86 probe and ASI built; synthetic host exercised the exported `InitializeASI`, D3D9 factory/device hooks, all four draw methods, PS3-to-PS2 fallback-object mapping, texture/material state, float/integer/boolean constants, vertex declarations, stream state, index buffers and FVF. The log analyzer, constant-sidecar parser, shader bytecode inventory, restricted downlevel audit and PE32 inspector self-tests passed.

[Download the Windows x86 artifact](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44890714743/artifacts/14700884610) — artifact ID `14700884610`, 35 files, SHA-256 `639671695847d8609ac9c9feb1790172dcd674b09359632faf85b1f701e21655`.

The runtime log and captures in this build are synthetic fake-COM test data. The synthetic adapter reports `VEN_8086&DEV_29C2`; that is a test fixture, not the physical GMA 3100. The five shader captures and six constant sidecars are not captures from GTA IV.

CI does not inspect the user's original executable, load the ASI inside GTA IV, test the GMA 3100 driver, validate game rendering/gameplay, or measure FPS.

## Known limitations

- No GTA IV executable, game assets, proprietary bytecode, material definitions or render-state interfaces are included or reverse-engineered.
- The x86 ASI is an experimental telemetry plugin for the original PC GTAIV.exe 1.0.0.0 build. It hooks only a direct d3d9.dll!Direct3DCreate9 import in the main executable; it is not a complete D3D9 proxy and does not intercept all GetProcAddress, delay-load, or secondary-module paths. The actual GTA IV import table has not yet been verified.
- No SM3-to-SM2 replacement is integrated into the ASI, no complete shader-family library exists, and no working reduced renderer exists. The offline downlevel tool supports only a restricted pixel-shader subset and must not be treated as a general translator.
- No exact reference-image comparison, shader correctness oracle, frame-time benchmark, performance tuning or device-loss/reset handling exists.
- The patterned texture and non-identity matrix cases exercise more paths than v0.2 but do not independently prove every UV, matrix or normal-transform result.
- Hardware VP may be unavailable or rejected by the driver. The software-VP and hardware-VP results must remain separate.
- A hosted Windows build does not emulate the target GMA 3100 driver.
- No claim is made that GTA IV v1.0.0.0 will launch, render correctly, or achieve 30 FPS on GMA 3100.

## Research and next development direction

The full platform and rendering analysis is in [docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md](docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md). It covers the GMA 3100 SM2.0 limits, GTA IV shader evidence, the GTA IV and Minecraft optimization references, the proposed game-loaded ASI/D3D9 architecture, shader fallback strategy, risks and release gates.

The x86 ASI telemetry foundation passed the synthetic Windows x86 CI test. It validates the host as GTAIV.exe file version 1.0.0.0, exports and invokes InitializeASI in the synthetic test, installs a main-executable IAT hook for Direct3DCreate9, and observes adapter identity, caps, format checks, device creation, render/depth surfaces, Reset, Present failures and shader creation/binding. Opt-in draw telemetry links draw records to active shader-object addresses; bytecode capture and draw telemetry are disabled by default. The plugin does not spoof shader capabilities and does not yet inject shader replacements into GTA IV.

For an eventual check of the **actual original executable**, the read-only inspector can be run against a local copy:
```bat
python tools\inspect_gtaiv_executable.py "C:\path\to\GTAIV.exe" --json GTAIV_import_report.json
```
It reports PE architecture, file version, normal/delay imports and whether a direct `d3d9.dll!Direct3DCreate9` import exists. This has **not** been run on the user's executable yet. After draw telemetry is enabled in a diagnostic run, `tools\analyze_asi_log.py IVLegacy.log --json draw_report.json` groups recorded submissions by shader-object hashes.

Next steps:

1. Verify the original GTA IV 1.0.0.0 executable's D3D9 import path and actual plugin load mechanism.
2. Capture actual game shader bytecode plus the device's true shader caps, render-target formats and draw/shader bindings.
3. Map real runtime shader hashes to the public disassembly/metadata inventory and separate vertex/pixel variants.
4. Expand the offline audit only when an instruction, register, sampler and interface rule is backed by D3D9 specification and test cases; keep unsupported features as explicit rejections.
5. Implement and validate actual SM2 fallback families against known game materials before integrating any replacement hook.

The v0.3 standalone probe remains a developer reference for generic SM2 behavior. The current ASI is not ready to be treated as a playable mod. A game test should wait until a real GTA IV shader/rendering fallback exists, not just because the telemetry plugin compiles.

No GTA IV launch, rendering or FPS claim is made until the game-loaded build has been tested on the target machine. 30 FPS remains a target, not a guarantee.
