# IV Legacy Shader Engine — Prototype 0.4-alpha

**Target:** 32-bit Windows, Direct3D 9, Shader Model `vs_2_0` / `ps_2_0`.

Prototype 0.4-alpha combines the original v0.3 standalone D3D9 probe with an experimental Win32/x86 GTA IV telemetry ASI. The intended game target is the **original PC release, GTAIV.exe file version 1.0.0.0**. The ASI validates that exact version by default. It is instrumentation, not yet a shader compatibility fix: it does not translate or replace SM3 shaders, spoof capabilities, or make GTA IV launch on Intel GMA 3100.

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
| `build/run_probe.bat` | Launches the probe after checking its six bytecode files |
| `.github/workflows/windows-x86-build.yml` | Windows x86 compile/build CI; does not run the GPU probe |

All six v0.2 HLSL sources are retained byte-for-byte. They still target only `vs_2_0` and `ps_2_0`.

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

**Do not install the current ASI into the game yet.** It has passed a synthetic CI host test, but the original GTAIV.exe import table, ASI-loader path and actual GMA 3100 driver have not been validated. It does not yet replace any GTA IV shader.

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

**Prototype 0.4-alpha Windows x86 CI passed** in [run #61](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44884318642). It compiled all six SM2 HLSL shaders, inventoried them, built the x86 probe and ASI, ran the synthetic D3D9 hook test, captured two synthetic SM2 shaders, parsed both captures, and uploaded the 19-file artifact ([download](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44884318642/artifacts/14698909429)). Artifact SHA-256: 57115fe856777802f7470ba93d944b022dce7967dcf654ed8fde6fe183482bb3.

The smoke host reports a **synthetic** adapter identity VEN_8086&DEV_29C2 and SM2 caps. It is a controlled fake COM implementation used to exercise the plugin's hooks. The two captured shader binaries are synthetic SM2 test shaders, **not shaders captured from GTA IV**. This CI run does not test the Intel GMA 3100 driver, the original game executable, an ASI loader, gameplay, image correctness, or FPS.

## Known limitations

- No GTA IV executable, game assets, proprietary bytecode, material definitions or render-state interfaces are included or reverse-engineered.
- The x86 ASI is an experimental telemetry plugin for the original PC GTAIV.exe 1.0.0.0 build. It hooks only a direct d3d9.dll!Direct3DCreate9 import in the main executable; it is not a complete D3D9 proxy and does not intercept all GetProcAddress, delay-load, or secondary-module paths. The actual GTA IV import table has not yet been verified.
- No SM3-to-SM2 bytecode translation, shader replacement library, capability override, or working reduced renderer exists.
- No exact reference-image comparison, shader correctness oracle, frame-time benchmark, performance tuning or device-loss/reset handling exists.
- The patterned texture and non-identity matrix cases exercise more paths than v0.2 but do not independently prove every UV, matrix or normal-transform result.
- Hardware VP may be unavailable or rejected by the driver. The software-VP and hardware-VP results must remain separate.
- A hosted Windows build does not emulate the target GMA 3100 driver.
- No claim is made that GTA IV v1.0.0.0 will launch, render correctly, or achieve 30 FPS on GMA 3100.

## Research and next development direction

The full platform and rendering analysis is in [docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md](docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md). It covers the GMA 3100 SM2.0 limits, GTA IV shader evidence, the GTA IV and Minecraft optimization references, the proposed game-loaded ASI/D3D9 architecture, shader fallback strategy, risks and release gates.

The x86 ASI telemetry foundation is implemented and passed the synthetic Windows x86 CI runtime test. It validates the host as GTAIV.exe file version 1.0.0.0, installs a main-executable IAT hook for Direct3DCreate9, and observes adapter identity, caps, format checks, device creation, shader creation/binding, render/depth surfaces, Reset and Present failures. Optional shader capture is disabled by default. The plugin never spoofs shader capabilities and does not yet replace shader bytecode.

Next steps:

1. Verify the original GTA IV 1.0.0.0 executable's D3D9 import path and actual plugin load mechanism.
2. Capture actual game shader bytecode and map its hashes to the public shader disassembly/metadata inventory.
3. Inventory real device caps, render-target formats, shader profiles and failure points.
4. Implement and validate selected SM2 replacements while preserving the game's vertex, constant, sampler and render-state interfaces.
5. Only then add conservative state caching, resource reuse, render-only culling and low-effect presets.

The v0.3 standalone probe remains a developer reference for generic SM2 behavior. The current ASI is not ready to be treated as a playable mod. A game test should wait until a real GTA IV shader/rendering fallback exists, not just because the telemetry plugin compiles.

No GTA IV launch, rendering or FPS claim is made until the game-loaded build has been tested on the target machine. 30 FPS remains a target, not a guarantee.
