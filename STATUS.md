# Prototype 0.3 — status

## Implemented in source

- Preserved all six v0.2 HLSL shader files byte-for-byte; SHA-256 comparisons against the original v0.2 archive passed.
- Fixed FXC path discovery for common Windows 8.1 and versioned Windows SDK layouts, with DirectX SDK June 2010 fallback.
- Removed FXC strict-mode `/Ges`: the legacy D3D9 `sampler2D` declarations are valid for these SM2 shaders, but strict mode rejects them as deprecated syntax.
- Added non-empty bytecode and assembly-output checks after each FXC invocation.
- Added checked HRESULT handling for texture and readback `UnlockRect` calls.
- Added adapter PCI identity fields and explicit adapter-identification failure logging.
- Renamed the fixed-function texture capability field and logged PS 2.0 extended-capability fields separately.
- Retained the HAL/software-VP baseline and added a separate conditional HAL/hardware-VP test path.
- Added a non-identity WVP/View transform, non-uniform world scale and inverse-transpose normal matrix.
- Varied vertex depth to exercise fog interpolation.
- Added patterned colour/alpha textures, non-zero water UV offsets and wrap addressing.
- Added a separate alpha-blended water case.
- Split draw/present, readback-available and pixel-changed counters.
- Added Windows x86 GitHub Actions compilation/build workflow and source sanity checks.

## Verification state

| Check | State |
|---|---|
| Original v0.2 archive SHA-256 and ZIP integrity | PASS — `34cd5c3efa2d15bbf0fec1e6035ba90346c6c495c82d14cd3ebbcba5a69a29aa` |
| Six original shader files | PASS — byte-for-byte SHA-256 matches against the original archive |
| Source sanity tests | PASS — GitHub Actions run #10 |
| FXC compilation | PASS — all six shaders compiled as `vs_2_0` / `ps_2_0` |
| MSVC x86 compilation | PASS — `D3D9ShaderProbe.exe` built successfully with x86 MSVC |
| Compiled bytecode headers | PASS — two VS files report `0xFFFE0200`, four PS files report `0xFFFF0200`; all end with `D3DSIO_END` |
| Executable architecture | PASS — downloaded artifact inspected as PE32 Intel i386 |
| GitHub Actions Windows x86 build | PASS — [run #10](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44877200271), commit `0aeeeab9c60038ae0bbecc7d9004dfae843cc5f1` |
| Windows x86 build artifact | PASS — [download artifact](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44877200271/artifacts/14696049437), ID `14696049437`; includes repository-relative `build/` paths; expires 2027-02-19 |
| D3D9 runtime shader creation | NOT RUN |
| HAL software-VP rendering on GMA 3100 | NOT RUN |
| HAL hardware-VP rendering on GMA 3100 | NOT RUN |
| GMA 3100 readback / repeatability | NOT RUN |
| GTA IV integration | NOT IMPLEMENTED |
| GTA IV launch / FPS | NOT TESTED |

## Build artifact details

- Artifact: `iv-legacy-shader-engine-windows-x86.zip`
- Contains `build/bin/D3D9ShaderProbe.exe`, six files under `build/out/` (`.vso` / `.pso`), six matching FXC assembly listings, and `build/run_probe.bat`. Extract over the repository root to preserve the expected paths.
- SHA-256: `95c4a622c5137fe49be912013fc08891bccf6fe23ab7f94ba914c256a7d8c51c`

## Important boundary

Prototype 0.3 now has a successful hosted Windows x86 compile. It is **not** yet a verified D3D9 runtime on the target computer and has not been run on the GMA 3100. CI success proves that the shader sources compile and the x86 probe links in the hosted environment. It does not prove GMA 3100 driver acceptance, hardware vertex processing, rendering correctness, GTA IV compatibility or performance.


## Research and architecture work (2026-11-21)

- Added [GMA 3100 / GTA IV compatibility and optimization research](docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md).
- Confirmed from Intel documentation that GMA 3100 is D3D9.0c with PS 2.0 / VS 2.0, while GTA IV's DD3D60 requirement is documented as SM3.0 or higher.
- Inspected the public GTA IV shader decompilation tree: 1,689 ASM listings (856 PS / 833 VS) and 102 FXC XML metadata files. Inspected representative default, deferred-lighting, water, tree and vehicle shaders; the samples use ps_3_0. The deferred-lighting sample uses six samplers, r31 and dynamic if/rep flow control.
- Studied PS 2.0 vs PS 3.0 instruction, temporary-register and control-flow limits. A profile-token rename is not a valid conversion.
- Compared Sodium, Lithium, ImmediatelyFast, FerriteCore, OptiFine, EntityCulling and ModernFix. Recorded transferable techniques and features that must not be copied directly.
- Studied GTA IV community references including ZolikaPatch, FusionFix, GTA IV Shaders, the optimization guide and ASI loader.
- Updated README: the next development gate is a GTA IV 1.0.0.0 game-loaded x86 plugin, not asking the user to run the standalone v0.3 probe.
- Runtime caps from the actual GMA driver, shader-to-runtime permutation coverage, target formats and the attainable FPS remain unknown until a game-loaded build records/validates them.
