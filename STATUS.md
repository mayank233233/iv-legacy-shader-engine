# IV Legacy Shader Engine — status

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
| GTA IV ASI telemetry foundation | IMPLEMENTED IN SOURCE; x86 CI build passed; actual game not loaded/tested |
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

 
## GTA IV ASI telemetry foundation (2026-11-21)

### Implemented in source

- Added src/IVLegacyASI.cpp, a 32-bit ASI/DLL module intended for GTA IV 1.0.0.0.
- Bootstrap validates a 32-bit PE host named GTAIV.exe and checks the executable file version resource for 1.0.0.0 by default.
- Creates IVLegacy.log and a default IVLegacy.ini beside the host executable.
- Hooks the main executable's direct d3d9.dll!Direct3DCreate9 import-table entry; if that import is absent, it logs that the hook was not installed.
- Clones the returned IDirect3D9 object's vtable and observes GetAdapterIdentifier, CheckDeviceFormat, CheckDepthStencilMatch, GetDeviceCaps and CreateDevice.
- Clones the returned IDirect3DDevice9 object's vtable and observes device caps, Reset, failed Present calls, shader creation profile tokens, render-target allocation/binding, and depth-stencil allocation/binding.
- Logs PCI VendorId/DeviceId/SubsystemId/Revision, driver identity, shader-model versions, SM2 cap fields, render/depth formats, dimensions, usage and HRESULTs.
- Does not spoof PixelShaderVersion / VertexShaderVersion, does not replace shader bytecode, and does not patch GTA IV executable code.
- Uses per-object vtable copies so original methods remain available and can be called through saved pointers. The ASI must remain loaded for the lifetime of the hooked process; hot-unloading is not supported.

### Verification state

| Check | State |
|---|---|
| ASI source sanity checks | PASS — GitHub Actions run #61 |
| x86 MSVC compile/link | PASS — run #61; ASI produced as PE32 x86 DLL-format module |
| D3D9 synthetic runtime hooks | PASS — run #61; factory, caps/format/device/surface/shader creation and shader binding test paths |
| Bounded SM2 capture | PASS — run #61; two synthetic SM2 shader binaries written and parsed |
| Original GTA IV 1.0.0.0 load / hook execution | NOT RUN |
| Actual GMA 3100 D3D9 driver behaviour | NOT RUN |
| GTA IV shader bytecode capture | NOT RUN |
| Shader bytecode fallback / SM3 reduction | NOT IMPLEMENTED |
| GTA IV scene rendering / FPS | NOT TESTED |

### Important integration boundary

The initial hook is an IAT hook for a direct d3d9.dll!Direct3DCreate9 import in the main executable. It is not a complete d3d9.dll proxy and does not yet handle every possible GetProcAddress, delay-load, or secondary-module creation path. The synthetic CI host tests the method-hook mechanism, not GTA IV's exact binary/import layout. That must be validated before relying on it for game integration.

 
## Prototype 0.4-alpha verification — 2026-11-21

- Exact target: original PC GTAIV.exe file version 1.0.0.0; the default plugin gate rejects other file versions. No later patch or Complete Edition is a target.
- Current CI: [Windows x86 run #61](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44884318642), commit b707bb8361580dedc457dfe51ea13068a67b9846, all workflow steps passed.
- Artifact: [iv-legacy-shader-engine-windows-x86](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44884318642/artifacts/14698909429), artifact ID 14698909429; SHA-256 57115fe856777802f7470ba93d944b022dce7967dcf654ed8fde6fe183482bb3.
- Artifact contents: IVLegacyASI.asi, build/bin/D3D9ShaderProbe.exe, six SM2 bytecode files and six FXC assembly listings, compiled shader inventory JSON, two captured synthetic SM2 binaries and their inventory JSON, and the probe launcher.
- The synthetic host reports PCI ID 8086:29C2 and SM2 caps, but those values are supplied by a fake COM implementation. It tests hook logic only; it is not the Intel driver or the original game.
- The two captured bytecode files are the synthetic CI host's SM2 test shaders. They are not GTA IV's proprietary/runtime shaders.
- Shader creation and binding hooks cover the verified D3D9 method slots: CreateVertexShader 91, SetVertexShader 92, CreatePixelShader 106, SetPixelShader 107.
- The factory interception currently patches the direct d3d9.dll!Direct3DCreate9 import in the main executable's IAT. The experimental all-loaded-module scan was rolled back after it failed the synthetic test. Dynamic GetProcAddress, delay-load and secondary-module paths are not covered by the current build.
- The ASI uses DLL entry-point loading and is built with the .asi extension, but its behavior through a real ASI loader has not been verified.

### Remaining gates

| Gate | State |
|---|---|
| Confirm actual original GTAIV.exe PE import table and direct D3D9 factory path | NOT VERIFIED |
| Load plugin inside original GTA IV 1.0.0.0 via the intended loader | NOT TESTED |
| Capture real GTA IV SM3 shaders and map hashes to game variants | NOT RUN |
| Implement the first actual SM2 fallback shader(s) | NOT IMPLEMENTED |
| Replace or safely lower unsupported SM3 shader requests | NOT IMPLEMENTED |
| Render GTA IV scenes on Intel GMA 3100 | NOT TESTED |
| Measure FPS / 30 FPS objective | NOT TESTED |


 
## Prototype 0.5-alpha verification — 2026-11-21

- Exact target remains the original PC `GTAIV.exe` file version `1.0.0.0`; the strict gate rejects other versions by default.
- Latest Windows x86 CI: [run #81](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44885590397), commit `6e495c21bd026247160e90374a593f1c8851fa26`; all workflow steps passed.
- Artifact: [iv-legacy-shader-engine-windows-x86](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44885590397/artifacts/14700061775), ID `14700061775`; SHA-256 `4dbc2376cf9a5bf04375e69d386f201a8b55f50552eeee4464ec78fc8634fd9c`.
- Added C-linkage exported `InitializeASI`; synthetic host resolves it by exact export name and invokes it. The DllMain worker fallback is guarded against duplicate initialization.
- Added opt-in `CaptureDrawTelemetry=1` hooks for `DrawPrimitive`, `DrawIndexedPrimitive`, `DrawPrimitiveUP`, and `DrawIndexedPrimitiveUP`, using verified slots 81–84. Logging is capped by `CaptureDrawMaxCalls` (default 4096; clamp 1–65536); disabled by default.
- Added shader object/hash records so the object addresses in draw telemetry can be correlated to a shader's profile and bytecode hash.
- The synthetic host exercises shader creation/binding and all four draw methods. Its fake adapter identity 8086:29C2 and SM2 caps are test fixtures, not a measurement of the physical GMA 3100.
- Artifact has two synthetic SM2 captures: one pixel shader and one vertex shader. The offline inventory parses both successfully.
- The restricted offline pixel-shader downlevel audit reports **zero** eligible files in this artifact: the pixel shader is already PS2.0, and the vertex shader is outside the tool's PS-only scope. Its self-tests do exercise a separate, tiny synthetic PS3.0 candidate and explicit rejection cases.
- The audit tool is not a general SM3 translator. It accepts only a limited PS3.0 subset and performs structural screening; candidates still require D3D9 runtime, driver and visual validation.
- The original GTA IV executable, actual ASI-loader game session, GMA 3100 driver, game shader capture, scene rendering, and FPS remain **not tested**.

### Next engineering gates

| Gate | State |
|---|---|
| Confirm original GTAIV.exe direct D3D9 factory import and import timing | NOT VERIFIED |
| Load the exported ASI through the actual loader in GTA IV 1.0.0.0 | NOT TESTED |
| Capture real game PS3.0 and VS3.0 bytecode and correlate draws | NOT RUN |
| Expand audit/lowering only for specification-backed shader cases | IN PROGRESS — offline PS subset only |
| Integrate a real fallback into device shader creation safely | NOT IMPLEMENTED |
| Render original GTA IV scenes on GMA 3100 | NOT TESTED |
| Measure average / 1% low FPS against the 30 FPS objective | NOT TESTED |


 
## Prototype 0.5.1-alpha verification — 2026-11-21

- Exact game target remains the original PC GTA IV `GTAIV.exe` file version `1.0.0.0`; the ASI version gate is strict by default.
- Latest Windows x86 CI: [run #93](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44886129718), commit `272d9d44ac83e08007510bc60beafdb50b39680f`; all workflow steps passed.
- Artifact: [iv-legacy-shader-engine-windows-x86](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44886129718/artifacts/14700107779), artifact ID `14700107779`; SHA-256 `967a6c752d4c88d6aaf0760850ada91a6da3c5a36ede1468e41f89ecb6b1e6c2`.
- Exported C-linkage `InitializeASI` is resolved by exact name and invoked by the synthetic host. The one-time initialization guard prevents duplicate bootstrap between the ASI-loader entry point and the LoadLibrary fallback.
- Opt-in draw telemetry now records successful-Present frame index, draw method, primitive type/count, active VS/PS object addresses and HRESULT. It covers DrawPrimitive, DrawIndexedPrimitive, DrawPrimitiveUP and DrawIndexedPrimitiveUP at D3D9 slots 81–84. It remains disabled by default and is bounded by CaptureDrawMaxCalls.
- Shader object creation is logged with stage, object address, profile, byte count and bytecode hash. The new offline `tools/analyze_asi_log.py` correlates those records with draw submissions and aggregates by shader pair, method, primitive type and frame. Its deterministic log fixture test passes in CI.
- Added `tools/inspect_gtaiv_executable.py`, a read-only PE32 x86 inspector for normal/delay imports, D3D9 factory import presence, file version and SHA-256. Its synthetic PE self-test passes. **It has not yet been run against the user's original GTAIV.exe.**
- The captured files remain synthetic SM2 test shaders: one VS2.0 and one PS2.0. The offline downlevel audit reports zero eligible conversions for these captures (the PS is already PS2; the VS is outside the pixel-only audit tool's scope). The audit's separate synthetic PS3.0 self-test exercises a restricted candidate path, not a real GTA IV shader.
- CI success does not verify original-game ASI loading, the Intel GMA 3100 driver, visual correctness, gameplay, or FPS.

### Remaining integration gates

| Gate | State |
|---|---|
| Inspect actual original GTAIV.exe file version and PE32 import tables | TOOL READY; FILE NOT INSPECTED |
| Verify direct or delay-loaded d3d9.dll!Direct3DCreate9 import in original GTAIV.exe | NOT VERIFIED |
| Load ASI through actual loader in original GTA IV 1.0.0.0 | NOT TESTED |
| Capture real game PS3.0/VS3.0 bytecode and correlate with draws | NOT RUN |
| Map real runtime shaders to GTA IV shader disassembly/metadata | NOT RUN |
| Implement and integrate real SM2 replacement shaders | NOT IMPLEMENTED |
| Render original GTA IV scenes on Intel GMA 3100 | NOT TESTED |
| Measure FPS / 30 FPS objective | NOT TESTED |


 
## Prototype 0.5.4-alpha verification — 2026-11-21

- Exact target remains original PC GTA IV `GTAIV.exe` file version `1.0.0.0`; strict gate remains enabled by default.
- Latest Windows x86 CI: [run #165](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44890714743), commit `0750df6203715f6e7986ef84ded862d6c9d8ec26`; all workflow steps passed.
- Artifact: [iv-legacy-shader-engine-windows-x86](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44890714743/artifacts/14700884610), artifact ID `14700884610`; SHA-256 `639671695847d8609ac9c9feb1790172dcd674b09359632faf85b1f701e21655`.
- Added opt-in vertex-input hooks at D3D9 slots: CreateVertexDeclaration 86, SetVertexDeclaration 87, SetFVF 89, SetStreamSource 100, SetStreamSourceFreq 102, SetIndices 104.
- Declaration creation records each element's stream, offset, type, method, usage and usage index. It is guarded against unreadable input and capped at 64 declaration elements.
- Each opt-in draw record now carries active declaration/FVF, index-buffer pointer and per-stream vertex-buffer pointer/offset/stride/frequency.
- Successful Reset clears the cached declaration, FVF, index-buffer and stream state.
- Synthetic test creates a POSITION float3 + TEXCOORD float2 declaration, sets a stream with offset 0/stride 20/frequency 1, binds a fake index buffer and draws. It then switches to FVF `0x00000102` and exercises later draw calls.
- Offline `tools/analyze_asi_log.py` reconstructs the declaration elements and groups draw submissions by declaration/FVF layout, stream layout and index-buffer object. Its deterministic parser fixture passes.
- Run #165 passed source sanity, six SM2 shader compiles, x86 probe/ASI builds, synthetic D3D9 runtime, captured shader inventory, constant-sidecar parsing, fallback audit and artifact staging.
- Artifact runtime evidence remains synthetic. It contains five fake-COM shader captures, six synthetic constant sidecars and a synthetic `IVLegacy.log`; none are proprietary GTA IV shader/material captures.
- Actual original GTA IV 1.0.0.0, real ASI-loader session, physical GMA 3100, real game rendering, mission/gameplay integrity and FPS remain untested.

### Remaining integration gates

| Gate | State |
|---|---|
| Inspect original GTAIV.exe file version and PE32 normal/delay imports | TOOL READY; FILE NOT INSPECTED |
| Verify original game's D3D9 factory import path and ASI load timing | NOT VERIFIED |
| Capture real GTA IV shader bytecode, constants, declarations, streams and material state | NOT RUN |
| Map real shader families to SM2 fallbacks and prove material equivalence | NOT IMPLEMENTED |
| Load a real compatibility renderer in original GTA IV 1.0.0.0 | NOT TESTED |
| Render GTA IV scenes on Intel GMA 3100 | NOT TESTED |
| Measure average / 1% low FPS against the 30 FPS objective | NOT TESTED |


 
## Prototype 0.5.5-alpha verification — 2026-11-21

- Exact target remains original PC GTA IV `GTAIV.exe` file version `1.0.0.0`; strict gate remains enabled by default.
- Latest Windows x86 CI: [run #172](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44891303007), commit `fd0f9e9c4eeafb30a4aa7de2893b7ba4f551d589`; all steps passed.
- Artifact: [iv-legacy-shader-engine-windows-x86](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44891303007/artifacts/14701424322), artifact ID `14701424322`; SHA-256 `bf39064f10d794d89c2ba04f96b6bc93b0be07a37a43a37fab897bea06dcf148`.
- Added opt-in buffer creation hooks at D3D9 slots CreateVertexBuffer 26 and CreateIndexBuffer 27. They log buffer object address, byte length, usage flags, FVF or index format, and pool.
- The offline draw analyzer resolves each bound vertex stream and index-buffer object to its creation descriptor. It exposes buffer lengths and formats alongside declaration/FVF, stream stride/offset/frequency, shader hashes and material-state fingerprints.
- Synthetic test creates a managed 4096-byte vertex buffer and a managed 1024-byte INDEX16 index buffer, binds both, and verifies the first draw resolves each pointer to its correct descriptor.
- Run #172 passed source sanity, six SM2 shader compiles, x86 probe/ASI builds, synthetic D3D9 runtime, log analysis, constant sidecar parsing, fallback audit, and artifact staging.
- All buffer descriptors, shader captures, constants and adapter identifiers in this artifact are synthetic fake-COM test data. They are not GTA IV resources or observations from the physical GMA 3100.

### Remaining integration gates

| Gate | State |
|---|---|
| Inspect original GTAIV.exe file version and PE32 normal/delay imports | TOOL READY; FILE NOT INSPECTED |
| Verify original game's D3D9 factory import path and ASI load timing | NOT VERIFIED |
| Capture real GTA IV shader bytecode, constants, material state, vertex declarations and buffer descriptors | NOT RUN |
| Map real game shader families and vertex input layouts to SM2-compatible fallbacks | NOT IMPLEMENTED |
| Load a real compatibility renderer in original GTA IV 1.0.0.0 | NOT TESTED |
| Render original GTA IV scenes on Intel GMA 3100 | NOT TESTED |
| Measure average / 1% low FPS against the 30 FPS objective | NOT TESTED |



## Vertex-stage audit development — 2026-11-22

- Added `tools/audit_vs3_to_vs2.py` on development branch `feature/vs3-vs2-vertex-audit`.
- It parses VS3.0 token streams and compares a conservative straight-line subset against baseline VS2.0 instruction slots, temporary/input/float-constant register bounds, sampler/predicate restrictions and output semantic mapping.
- It requires a real write to the mapped position output; a DCL declaration alone is not treated as a write.
- It rejects static flow control, the VS3.0 `sincos` operand form, vertex texture sampling, relative addressing and unhandled output semantics rather than guessing.
- It emits an audit report and mapping plan only. It does **not** emit VS2 bytecode or demonstrate compatibility with any GTA IV shader.
- Synthetic self-tests cover a simple candidate, excessive temporary register, vertex sampler, VS3-only texture lookup, unsupported output semantic, declaration-without-write, output register overflow, version-sensitive `sincos`, slot-budget overflow and truncated bytecode.
- The self-test is wired into both the standalone vertex-audit workflow and Windows x86 source-sanity workflow. Standalone vertex-audit validation passed in run #219; the full Windows x86 build for that commit was still running at the last check.
- All fixtures are synthetic; no original GTA IV shader or GMA 3100 device has been inspected.


## Vertex output-interface audit expansion — 2026-11-22

- Corrected the VS3 output model: multiple DCL declarations may describe disjoint component masks on the same output register, each carrying a distinct semantic.
- The analyzer now preserves each declaration separately, rejects overlapping masks and duplicate semantic identifiers, and fans writes from one source register into the mapped VS2 output targets in its diagnostic plan.
- Direct `COLOR0/1` mappings are preserved. TEXCOORD semantics are compacted into consecutive `oT0-oT7` outputs; sparse source indices are flagged when the corresponding pixel-shader semantic must be rewritten. Other generic semantics are allocated to remaining VS2 interpolation outputs and flagged for the same paired pixel-shader change.
- VS3 `FOG` is treated as a generic varying, not as the legacy scalar `oFog` register. `POSITION0` and `PSIZE0` are treated as special outputs with full-mask requirements.
- Added tests for packed semantic mappings, repeated semantic declarations, overlapping masks, point-size masks, undeclared/unwritten components, and TEXCOORD output-register constraints.
- The tool remains diagnostic-only and emits no VS2 bytecode. All tests use synthetic tokens, not captured GTA IV shaders.
- Latest Windows x86 CI after this expansion: run #187 is queued; prior run #185 failed on an outdated assertion, not on the output mapping implementation.
- Corrected D3D9 LOOP operand arity to two parameter tokens (`aL,i#`) and restricted VS2 address-register writes to MOVA; MOV-to-a0 is now a negative regression case.
- Windows CI captures a separate `captured_vertex_shader_downlevel_audit.json` report alongside the pixel-shader audit. The synthetic SM2-only capture batch is expected to contain zero VS3 shaders and is reported as skipped, not as a successful conversion.


## Matrix operand audit expansion — 2026-11-22

- Tightened matrix destination masks to the per-instruction D3D9 requirements: m4x4 `.xyzw`, m4x3 `.xyz`, m3x4 `.xyzw`, m3x3 `.xyz`, and m3x2 `.xy`.
- Confirmed each matrix instruction reads consecutive float constants equal to the result dimension: 4, 3, 4, 3 and 2 registers respectively. The earlier apparent mismatch was a false alarm; the existing span table was already correct.
- Added matrix destination/vector-source alias rejection and regression fixtures for exact masks, valid m4x3/m3x4/m3x2 forms, constant-register boundary overflow, and aliasing.
- Tightened baseline address-register handling to `MOVA a0.x`; MOV-to-a0 is rejected as a VS1.1 form, and vector masks on MOVA are rejected for VS2.0.
- Windows x86 CI run #201 passed with the complete pipeline, including the matrix fixtures.


## Component-aware vertex data-flow audit — 2026-11-22

- Added straight-line temporary initialization tracking at component level. Source swizzles are mapped to the physical components read; partial writes accumulate, and only reads from unwritten components are rejected.
- Added opcode-specific source dependencies for DP3/DP4, CRS, LIT, DST, NRM, SGN and matrix-vector operations. Tests cover LIT's ignored z channel and exponent w, DST source-specific channels, NRM's mandatory xyz and optional w, and CRS component dependencies.
- SGN src1/src2 temporary scratch registers are marked undefined after execution, matching the D3D9 reference; later reads are rejected.
- Enforced baseline VS2 input/constant read-port limits: one distinct vertex input register and one distinct float-constant register per ordinary instruction. Same-constant multi-source swizzles are accepted; matrix operations retain their implicit consecutive-row behavior. Positive and negative fixtures are included.
- Run #207 passed both jobs: independent Ubuntu analyzer compilation/self-tests and the complete Windows x86 build.
- Run #206's Windows build failed before source tests because Chocolatey returned HTTP 504 while resolving the DirectX SDK package. It did not reach analyzer tests; run #207 subsequently passed the full Windows path.
- The tool remains diagnostic-only and emits no VS2 bytecode. No actual GTA IV VS3 shader or GMA 3100 hardware has been tested.

- Corrected point-size handling: PSIZE0 DCL must declare xyzw, while the scalar output write is x-only. Added tests for the valid form and invalid declaration/y-only write.
- Run #208's independent Ubuntu vertex-audit job passed the point-size tests; the Windows x86 build is still running at the DirectX SDK install step.

- Microsoft’s constant-float register page clarified that ordinary instructions may access only one distinct c-register (not two). Updated the audit and tests; see https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-constant-float.


## VS3-to-VS2 output mapping corrections — 2026-11-22

- Rechecked output declaration behavior against Microsoft's D3D9 `dcl_usage` reference. Different semantic declarations may share one VS3 `o#` register when their DCL component masks are unique and non-overlapping.
- Added a regression fixture for Microsoft's documented packing pattern: `COLOR0 o3.x`, `TEXCOORD3 o3.yz`, and `FOG o3.w`. The report maps the source lanes into separate VS2 outputs and marks pixel-shader interface remapping where required.
- Removed the false restriction that a sparse TEXCOORD component mask must be moved to a color output. Masks such as `.yz` and `.xz` are retained on the mapped four-component output.
- Removed the undocumented check that VS2 `oT#` outputs must be used contiguously or have a contiguous component mask.
- The report now includes both the VS3 declared component mask and the target VS2 component mask. `PSIZE0` maps its scalar source `.x` to `oPts.x`; its VS3 declaration still requires the full mask.
- Standalone vertex-audit CI run #219 passed the self-test job after these changes. The run's separate Windows x86 build job was still in progress at the last status check.
- The analyzer remains report-only: no output-splitting or pixel-shader relink bytecode is generated, and no real GTA IV shaders have been audited.


## VS3 special output slot and arbitrary-index boundary checks — 2026-11-22

- Enforced that the `POSITION0` and optional `PSIZE0` source registers are exclusive and cannot share their source `o#` with another semantic.
- Added boundary fixtures for ten generic interpolators plus position and point size, ten interpolators plus position with no point-size declaration, and an over-capacity case with eleven generic interpolators.
- The valid full-bank fixture deliberately places `POSITION0` at `o1`, `PSIZE0` at `o10`, and spreads the ten general interpolators across other nonconsecutive indices, verifying that source register numbers are not hard-wired to output classes.
- Standalone vertex-audit CI run #224 passed. Its Windows x86 build job was still running environment setup at the last status check.
- This validates synthetic declaration and write-mask layouts only. No actual GTA IV shader or target GPU has been tested.

## Render/depth surface and adapter capability telemetry — 2026-11-22

- Added read-only per-draw snapshots for up to four active D3D9 render-target slots and the depth-stencil surface. Each record includes surface pointer, dimensions, format, surface type, usage, pool and multisample settings.
- After successful `CreateDevice` and `Reset`, the ASI queries the standard D3D9 `GetRenderTarget` / `GetDepthStencilSurface` methods (vtable slots 38 and 40) to capture the initial implicit surfaces. Missing getter entries are skipped safely.
- Successful `SetRenderTarget` / `SetDepthStencilSurface` calls refresh snapshots. Failed state changes do not update cached state. Reset clears stale snapshots before re-querying.
- No arguments, capabilities, render states, targets or game simulation are modified. No pass is dropped. The larger log buffers preserve full draw records with the added surface descriptors.
- `tools/analyze_asi_log.py` now parses the per-draw descriptors and produces surface usage summaries grouped by object, resolution, format and shader pair. It also parses adapter ID/driver details, vertex/pixel shader caps, format support checks, depth-format match checks, device-create events and render/depth-surface creation/binding records.
- Adapter strings with spaces and split driver-version fields have regression coverage.
- Static source checks cover getter slots and the read-only snapshot path. Parser fixtures cover multiple render-target slots, depth descriptors, format support/failure, shader-model caps and older logs with no new fields.
- Latest run #236 has the independent vertex-audit job passing; the full Windows x86 job was still installing the legacy DirectX SDK at the last status check.
- CI uses fake D3D9 devices and synthetic logs. No actual GTA IV 1.0.0.0 execution, GMA 3100 driver capture or FPS measurement has occurred.
- `main` remains untouched. All work stays on `feature/vs3-vs2-vertex-audit`.
## Final Windows verification for the render-pipeline capture update — 2026-11-22

- Run #239 passed both jobs on commit `8034e2508b3a9c71d7a9ec91311de4460432d354`.
- The Windows x86 job passed source sanity, six SM2 shader builds, D3D9 probe build, ASI build, synthetic D3D9 runtime smoke, shader inventory and artifact upload.
- The smoke test exercises signature-correct `GetRenderTarget` and `GetDepthStencilSurface` stubs on successful device creation and reset. It confirms the telemetry path does not call generic zero-argument fake vtable stubs.
- The standalone VS3-to-VS2 audit self-tests also passed.
- Artifact: `iv-legacy-shader-engine-windows-x86`, 237,403 bytes, SHA-256 `baaf821d66560a20d2aafebe34982aec5e307ede6e4fa4ce338105f34c8ca556`, run #239.
- These are Windows CI and synthetic tests only. They do not establish that GTA IV 1.0.0.0 launches, renders correctly, or reaches any FPS on an Intel GMA 3100.
- Branch `feature/vs3-vs2-vertex-audit` remains separate; `main` was not changed.

## Draw-level paired VS3/PS3 compatibility audit — 2026-11-22

- Created isolated development branch `feature/paired-shader-interface-audit` from `feature/vs3-vs2-vertex-audit`; `main` and the previous development branch are unchanged.
- Added `tools/audit_shader_pairs.py`, a read-only analysis tool that correlates each logged draw's active VS/PS object hashes with captured bytecode using the ASI's FNV-1a 64-bit hash.
- The tool currently targets `vs_3_0 + ps_3_0` pairs. It reuses the existing conservative stage auditors, checks original VS-output / PS-input semantics and component masks, and identifies cases where the independently generated VS2 and PS2 register allocations would require a coordinated relink.
- Packed PS3 input registers carrying multiple semantics are reported explicitly because the current PS3-to-PS2 lowerer cannot split one input register across multiple PS2 registers.
- Added per-draw vertex-input checks against captured `D3DVERTEXELEMENT9` declarations or a limited common-FVF decoder, including stream binding, stride, declaration method and first-element allocation span. Unknown FVF encodings fail closed.
- Added checks for non-null texture bindings at declared/used pixel sampler stages, active render-target count versus the captured device limit, shader-model floor, captured VS2/PS2 temporary-register limits and pixel instruction-slot limits.
- Interpolation DCL modifiers, absent detailed blend/depth/alpha/sampler-state values, and unvalidated full draw vertex/index ranges remain visible as warnings. The tool does not infer state meaning from hashes.
- Added synthetic self-tests for semantic matching, sparse TEXCOORD relinking, packed pixel inputs, explicit vertex declarations, FVF decoding, device caps and end-to-end hash-to-draw correlation.
- Wired the paired audit's syntax check and self-test into the Ubuntu audit job and Windows x86 build job in `.github/workflows/windows-x86-build.yml`.
- **Verification pending:** the new branch's GitHub Actions run has not yet been confirmed. A passing synthetic self-test will establish only parser/decision logic, not real-game compatibility.
- No actual original GTA IV shader capture, original executable import inspection, ASI-loaded gameplay session, physical GMA 3100 render, screenshot comparison or FPS measurement has been performed.
- The tool emits no replacement bytecode, does not modify D3D9 state, does not spoof capabilities and does not drop rendering passes.

- Follow-up audit hardening: required texture bindings are now checked only for samplers actually sampled by the pixel shader; unused sampler declarations do not create false missing-texture failures.
- `DrawPrimitiveUP` and `DrawIndexedPrimitiveUP` are explicitly marked capture-incomplete because the current telemetry does not record their transient per-draw vertex/index memory layout and ranges.


## D3D9 capability audit and QPC frame profiler — 2026-11-22

- Added to isolated branch `feature/d3d9-capability-frame-profiler`, based on `feature/paired-shader-interface-audit`; the previous branches and `main` are unchanged.
- The ASI now logs `D3DCAPS9.DevCaps`, `D3DDEVCAPS_HWTRANSFORMANDLIGHT`, `VertexProcessingCaps`, `MaxStreams`, `MaxStreamStride`, `MaxVertexIndex` and `MaxPrimitiveCount` from both interface and device capability queries.
- `CreateDevice` logging records hardware/mixed/software vertex-processing request flags separately from the advertised HW-T&L capability. A requested processing mode is not treated as proof of the driver's internal execution path.
- Added optional `EnableFrameProfiler=1`, disabled by default, with configurable windows of 1–600 frames (default 120). Uses QueryPerformanceCounter and captures successful Present-return intervals, Present-call wall time, and wall time inside all four D3D9 draw methods.
- Summary output includes average, P50, P95, P99 and maximum frame intervals, Present time, draw API time, unattributed interval time, average draw calls and draw failures. Logging occurs per window, not once per frame.
- Draw-method hooks are installed for profiler-only mode without enabling the verbose draw-state telemetry hooks.
- The profiler explicitly reports `gpu_time=not_measured`. Present/draw API wall times may include driver waits; unattributed time includes simulation and non-draw API work and is not a direct world-simulation measurement.
- Extended the synthetic Windows runtime test: its fake D3D9 caps advertise HW-T&L, CreateDevice requests software VP, four fake draw methods execute between Present calls, and the test requires a one-sample profile summary showing four draw calls.
- **Verification PASS:** [Windows x86 CI run #254](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44999020323), commit `3984059b4c65ced1c7917ffbb03a711e075bdf50`. Both `vertex-audit` and `build` jobs passed, including source sanity, SM2 shader compilation, x86 probe/ASI builds, the synthetic D3D9 runtime test, captured-shader inventory and artifact upload.
- Artifact: [iv-legacy-shader-engine-windows-x86](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44999020323/artifacts/14744669712), ID `14744669712`, 242,306 bytes.
- The synthetic runtime test verified the HW-T&L cap log, software-VP request logging, and a one-frame profile summary containing four draw calls. These values are synthetic fixtures, not actual GMA 3100 measurements.
- **Not tested:** original GTA IV 1.0.0.0 loading, the physical GMA 3100 capability response, real-game Present cadence, fixed-function rendering performance, GPU execution time or FPS.


## Conservative D3D9 scalar state cache — 2026-11-22

- Created isolated branch `feature/redundant-d3d9-state-cache` from the most advanced `feature/d3d9-capability-frame-profiler` branch; `main` and the existing feature branches were not modified.
- Added an experimental, opt-in state-shadow optimization for only `IDirect3DDevice9::SetRenderState` (slot 57), `SetTextureStageState` (slot 67) and `SetSamplerState` (slot 69). A setter is skipped only when the same device's last successful call for that exact state index already established the identical value.
- The optimization is disabled by default. It uses a serialized state-cache critical section, records forwarded/skipped calls per configured Present window and continues to use the existing state snapshots for draw analysis.
- State is invalidated on successful Reset, failed Present and device-hook installation. `CreateStateBlock`, `BeginStateBlock` and `EndStateBlock` hooks permanently disable the optimization for that process before forwarding the state-block API call. The first thread to use the cache is recorded; a different thread reaching a tracked setter or Present permanently disables the cache.
- The synthetic Windows x86 runtime test now checks two duplicate hits per state group, forwarded/skipped counts, Reset invalidation and automatic state-block disable.
- **Verification pending:** the new branch has not yet completed GitHub Actions. CI's fake D3D9 tests do not establish real-driver timing or game correctness.
- **Not measured:** no GTA IV 1.0.0.0 gameplay session, physical GMA 3100 state-call profile, average/1% low FPS or 30 FPS result. This feature is an experiment intended to be benchmarked with `EnableRedundantStateCache=1`; leave it disabled otherwise.
