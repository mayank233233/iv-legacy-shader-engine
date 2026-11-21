# Changelog

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
