# IV Legacy Shader Engine — Prototype 0.3

**Target:** 32-bit Windows, Direct3D 9, Shader Model `vs_2_0` / `ps_2_0`.

Prototype 0.3 is an experimental D3D9 shader-compatibility and reduction probe. It is **not** a GTA IV renderer, game patch, shader translator, or evidence that GTA IV will run on Intel GMA 3100.

## Project contents

| Path | Purpose |
|---|---|
| `shaders/basic_vs20.hlsl` | Generic world/view/projection transform, vertex lighting, view-space fog factor |
| `shaders/basic_ps20.hlsl` | One-texture lit material and fog |
| `shaders/unlit_ps20.hlsl` | One-texture unlit material and fog |
| `shaders/water_ps20.hlsl` | Two-texture scrolling water approximation |
| `shaders/flat_lod_vs20.hlsl` | Position/vertex-colour transform for flat distant geometry |
| `shaders/flat_lod_ps20.hlsl` | Texture-free vertex-colour/fog pass |
| `src/D3D9ShaderProbe.cpp` | x86 D3D9 capability, shader-creation, draw/present and readback probe |
| `build/compile_shaders.bat` | FXC compilation and assembly-listing generation for all six shaders |
| `build/build_probe.bat` | x86 MSVC build |
| `build/run_probe.bat` | Launches the probe after checking its six bytecode files |
| `.github/workflows/windows-x86-build.yml` | Windows x86 compile/build CI; does not run the GPU probe |

All six v0.2 HLSL sources are retained byte-for-byte. They still target only `vs_2_0` and `ps_2_0`.

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
build\run_probe.bat
```

The compiler script writes six bytecode files (`.vso` / `.pso`) and six FXC assembly listings into `build\out`. The C++ build writes `build\bin\D3D9ShaderProbe.exe`. The probe writes `D3D9ProbeReport.txt` in the repository root.

The FXC script searches `PATH`, the unversioned Windows SDK `bin\x86` path, the versioned SDK path, and common DirectX SDK June 2010 locations. If FXC is installed elsewhere, add its directory to `PATH`.

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

## GitHub Actions boundary

**Prototype 0.3 Windows x86 CI passed** in [run #10](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44877200271). The workflow compiled all six HLSL files with FXC, built the 32-bit C++ executable with MSVC, staged the outputs under the repository-relative `build/` folder, and uploaded the 14-file artifact ([download](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44877200271/artifacts/14696049437)). Extract the artifact over the repository root; it supplies `build/bin/D3D9ShaderProbe.exe`, `build/out/` bytecode and assembly files, and `build/run_probe.bat`. CI does **not** run the D3D9 windowed probe, validate a physical graphics driver, or prove hardware vertex-shader execution. Passing CI cannot replace running `build\run_probe.bat` on the actual GMA 3100 machine.

## Known limitations

- No GTA IV executable, game assets, proprietary bytecode, material definitions or render-state interfaces are included or reverse-engineered.
- No D3D9 proxy DLL, ASI plugin, injection, hook, runtime interception, bytecode translation or game integration exists.
- No exact reference-image comparison, shader correctness oracle, frame-time benchmark, performance tuning or device-loss/reset handling exists.
- The patterned texture and non-identity matrix cases exercise more paths than v0.2 but do not independently prove every UV, matrix or normal-transform result.
- Hardware VP may be unavailable or rejected by the driver. The software-VP and hardware-VP results must remain separate.
- A hosted Windows build does not emulate the target GMA 3100 driver.
- No claim is made that GTA IV v1.0.0.0 will launch, render correctly, or achieve 30 FPS on GMA 3100.

## Research and next development direction

The full platform and rendering analysis is in [docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md](docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md). It covers the GMA 3100 SM2.0 limits, GTA IV shader evidence, the GTA IV and Minecraft optimization references, the proposed game-loaded ASI/D3D9 architecture, shader fallback strategy, risks and release gates.

The next development work is a **GTA IV 1.0.0.0 game-loaded x86 plugin**, not another standalone shader demo:

1. Create a version-aware ASI/plugin foundation with safe startup/shutdown, config and logs.
2. Instrument the real D3D9 device without reporting fake capabilities.
3. Inventory the game's shader creation, render-target and format requirements.
4. Build selected SM2 fallback shaders while preserving the game's constant/vertex interfaces.
5. Add conservative state caching, buffer/resource reuse, visible-only rendering and reduced-effects options after instrumentation identifies safe targets.

The v0.3 standalone probe remains a developer reference for generic SM2 behavior. The next requested user test should be an installable GTA IV-loaded mod build, not the probe.

No GTA IV launch, rendering or FPS claim is made until the game-loaded build has been tested on the target machine. 30 FPS remains a target, not a guarantee.
