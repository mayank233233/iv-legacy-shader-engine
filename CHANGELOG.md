# Changelog

## Prototype 0.4-alpha — D3D9 telemetry ASI

- Added a Win32/x86 ASI bootstrap with a strict-by-default GTAIV.exe file-version gate for the original PC 1.0.0.0 release, plus log and INI creation.
- Added the main executable's direct d3d9.dll!Direct3DCreate9 IAT hook and per-object IDirect3D9 / IDirect3DDevice9 vtable instrumentation.
- Added adapter PCI identity, D3D9 caps and format checks, device creation, Reset, failed Present, colour/depth surface, shader creation and shader binding telemetry.
- Added opt-in bounded SM2/SM3 bytecode capture with content hashing; capture is disabled by default.
- Added the offline D3D9 SM2/SM3 token inventory tool and CI inventory of compiled and captured shader bytecode.
- Added a synthetic GTAIV.exe host that exercises the factory/device hooks and two synthetic SM2 captures. Windows x86 CI run #61 passes all steps and uploads artifact 14698909429.
- The synthetic PCI identity 8086:29C2 and reported SM2 caps are test data, not a measurement of the physical GMA 3100.
- The all-loaded-module IAT scanning experiment failed its synthetic runtime test and was rolled back. Current hook scope is the main executable's direct IAT import only.
- No SM3-to-SM2 translation, shader replacement, original-game execution, real GMA 3100 test, gameplay rendering or FPS result exists yet.


## Research update — 2026-11-21

- Added `docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md` with hardware capability findings, sampled GTA IV SM3 shader analysis, Minecraft optimization technique mapping, GTA IV community-mod compatibility notes, and a game-loaded ASI/D3D9 development architecture.
- Changed the next project gate from asking the user to run the standalone probe to developing a GTA IV 1.0.0.0 game-loaded x86 plugin.
- Recorded that the 30 FPS objective is a target and cannot be promised before real in-game measurement.

## Prototype 0.3

- Fixed FXC discovery for Windows 8.1 and versioned Windows SDK layouts.
- Added FXC output-file validation and additional DirectX SDK discovery paths.
- Checked texture and readback unlock HRESULTs.
- Expanded adapter identity and Direct3D capability reporting.
- Added a separate conditional HAL hardware-vertex-processing run while retaining the HAL software-vertex-processing baseline.
- Added non-identity transforms, non-uniform world scale, varying vertex depth, patterned textures and a dedicated alpha-blended water test.
- Split draw/present, readback and centre-pixel-change summaries.
- Added Windows x86 CI for shader compilation and C++ build.
- Removed FXC strict-mode `/Ges`, which rejects the Direct3D 9-era `sampler2D` syntax used by these Shader Model 2.0 shaders.
- Verified all six FXC shader compilations and the x86 MSVC build in GitHub Actions run #10.
- Corrected the build artifact to preserve `build/bin`, `build/out` and `build/run_probe.bat` paths.

## Prototype 0.2

- First standalone D3D9 probe with six generic Shader Model 2.0 HLSL shaders.
- Added bytecode validation, shader creation, four rendering cases, present checks and best-effort backbuffer readback.
