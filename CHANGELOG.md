## Prototype 0.5.4-alpha — vertex input telemetry

- Added opt-in hooks for D3D9 vertex declaration creation/binding, FVF binding, stream source/frequency and index-buffer binding at slots 86, 87, 89, 100, 102 and 104.
- Logged bounded `D3DVERTEXELEMENT9` declaration elements, including stream, byte offset, type, method, usage and usage index.
- Added declaration/FVF, index-buffer and stream-buffer/offset/stride/frequency state to frame-indexed draw records; successful Reset clears the cached input bindings.
- Extended the offline draw analyzer to reconstruct declaration elements and aggregate draws by vertex input layout, stream and index-buffer.
- Synthetic test creates a POSITION float3 + TEXCOORD float2 declaration, binds a fake vertex stream and index buffer, draws once with the declaration, then switches to FVF `0x00000102`.
- Windows x86 CI run #165 passes all steps, including the new vertex input runtime smoke test and analyzer assertions. Artifact 14700884610; SHA-256 `639671695847d8609ac9c9feb1790172dcd674b09359632faf85b1f701e21655`.
- These are synthetic D3D9 inputs. No original GTA IV vertex declarations or shaders have been captured or translated.

## Prototype 0.5.1-alpha — frame-aware draw analysis and executable inspection

- Added the successful-Present frame index to opt-in D3D9 draw records.
- Added `tools/analyze_asi_log.py` to correlate shader object addresses with bytecode profile/hash records and summarize draw calls by shader pair, draw method, primitive type and frame.
- Added a deterministic parser test for shader correlation, unresolved pointers, draw totals and failure records.
- Added `tools/inspect_gtaiv_executable.py`, a read-only PE32 inspector for normal and delay imports, D3D9 factory imports, Windows file version and file SHA-256. It has only been tested with a synthetic PE fixture; the original game executable has not been inspected.
- Latest Windows x86 CI run #93 passes every step, including the log-correlator and PE inspector self-tests, ASI build, exported `InitializeASI` runtime call, frame-indexed synthetic draw-hook test and captured-shader audits.
- Artifact 14700107779; SHA-256 `967a6c752d4c88d6aaf0760850ada91a6da3c5a36ede1468e41f89ecb6b1e6c2`.
- The synthetic captures remain SM2 test programs. No original GTA IV shader is captured, translated or injected.

## Prototype 0.5-alpha — loader and shader/draw telemetry

- Exported the undecorated C-linkage `InitializeASI` entry point required by Ultimate ASI Loader; added a guarded one-time initialization path and a DllMain worker fallback for LoadLibrary-only loaders.
- Extended the synthetic x86 host test to resolve and call `InitializeASI` with `GetProcAddress`.
- Added opt-in D3D9 draw telemetry for methods at vtable slots 81–84: DrawPrimitive, DrawIndexedPrimitive, DrawPrimitiveUP and DrawIndexedPrimitiveUP.
- Draw records include primitive/count metadata and current vertex/pixel shader object addresses. Successful shader creation records pair each object address with its bytecode profile, size and hash.
- Draw telemetry is disabled by default; `CaptureDrawTelemetry=1` enables it, and `CaptureDrawMaxCalls` bounds it.
- Added `tools/audit_sm3_to_sm2.py`, a restrictive offline PS3.0-to-PS2.0 audit/lowering candidate generator with explicit rejection paths, input remapping and PS2 instruction/register/dependent-read limits. It does not handle vertex shaders or general SM3 programs.
- Windows x86 CI run #81 passes the ASI build, exported-entry-point check, synthetic D3D9 shader/draw hook test, two-shader capture/inventory, and audit-tool self-tests. Artifact 14700061775, SHA-256 `4dbc2376cf9a5bf04375e69d386f201a8b55f50552eeee4464ec78fc8634fd9c`.
- The two captured files in CI are synthetic SM2 test programs. The offline audit correctly marks the pixel shader as already PS2 and rejects the vertex shader as outside its PS-only scope; no real GTA IV shader has been converted.
- No actual GTA IV 1.0.0.0 runtime, GMA 3100 rendering, or FPS result exists yet.

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
