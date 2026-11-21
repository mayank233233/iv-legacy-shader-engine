# Changelog

## Prototype 0.4-alpha — D3D9 telemetry ASI

- Added a Win32/x86 ASI bootstrap with GTAIV.exe / 1.0.0.0 file-version gating, log and INI creation.
- Added an IAT hook for the main executable's direct d3d9.dll!Direct3DCreate9 import.
- Added per-object IDirect3D9 and IDirect3DDevice9 vtable instrumentation for adapter identity, caps, format checks, device creation, shader profile tokens, render/depth surfaces, Present failures and Reset.
- The telemetry component deliberately does not spoof SM3 capabilities, translate or replace shader bytecode, or patch GTA IV executable instructions.
- Added a synthetic GTAIV.exe host and D3D9 hook runtime smoke test to Windows x86 CI. This test validates the plugin hook mechanism; it is not a substitute for the actual GTA IV executable or GMA 3100 hardware.
- Run #21 compiled and linked the initial x86 ASI; later CI is validating the expanded hook set and synthetic runtime test.


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
