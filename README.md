# IV Legacy Shader Engine — Prototype 0.5.8-alpha

**Target:** 32-bit Windows, Direct3D 9, Shader Model `vs_2_0` / `ps_2_0`.

Prototype 0.5.8-alpha combines the standalone D3D9 probe, experimental Win32/x86 telemetry ASI, restricted offline PS3/VS3-to-SM2 bytecode downlevelers, explicitly approved hash-mapped PS2/VS2 fallback hooks, and opt-in D3D9 optimisation experiments. The GMA Edition development branch adds per-draw viewport/render-target auditing plus independently gated scalar-state, resource-binding and shader-constant caches. The intended game target is the **original PC release, GTAIV.exe file version 1.0.0.0**. The ASI validates that exact version by default. This remains an experimental compatibility foundation, not a playable compatibility fix: it does not spoof device capabilities, translate arbitrary SM3 shaders, implement low-resolution rendering, or establish that GTA IV can launch or render correctly on Intel GMA 3100.

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
| `src/IVLegacyASI.cpp` | Experimental GTA IV 1.0.0.0 x86 ASI; D3D9 telemetry/profiling, opt-in scalar-state/binding/constant caches, per-draw viewport capture and explicit hash-mapped PS2/VS2 shader fallback hooks |
| `build/compile_shaders.bat` | FXC compilation and assembly-listing generation for all six shaders |
| `build/build_probe.bat` | x86 MSVC standalone-probe build |
| `build/build_asi.bat` | x86 MSVC ASI/DLL build |
| `tools/analyze_d3d9_shaders.py` | Offline D3D9 SM2/SM3 token-stream inventory for compiled or captured shaders |
| `tools/audit_sm3_to_sm2.py` | Conservative offline audit/lowering candidate generator for a restricted `ps_3_0` pixel-shader subset; unsupported shaders are rejected, not guessed |
| `tools/audit_vs3_to_vs2.py` | Conservative `vs_3_0` to `vs_2_0` auditor and restricted bytecode emitter; rejects unsupported instructions, packed output semantics and unsafe remaps |
| `tools/audit_shader_pairs.py` | Draw-level VS3/PS3 pairing audit: semantic/component linkage, vertex declaration/FVF layout, captured texture bindings and render-target caps |\n| `tools/lower_shader_pairs.py` | Emits conservative paired VS2/PS2 candidates from audited draw captures; runtime mappings require explicit VS-hash:PS-hash approval |
| `tools/analyze_asi_log.py` | Correlates shader-object hashes with frame-indexed D3D9 draw calls, render/depth descriptors and per-draw viewport snapshots in `IVLegacy.log` |
| `tools/audit_gma_edition_render_path.py` | Read-only RT0/depth/viewport audit and conservative fixed-function candidate report |
| `tools/analyze_state_cache_benchmark.py` | Counts scalar render/texture-stage/sampler state calls forwarded or skipped |
| `tools/analyze_binding_cache_benchmark.py` | Counts texture/stream/index/shader/vertex-format/viewport binding calls forwarded or skipped |
| `tools/analyze_shader_constant_cache.py` | Counts VS/PS float/integer/boolean register-range calls forwarded or skipped |
| `IVLegacy.ini.example` | Template for the independent, default-off GMA Edition cache experiments and reserved renderer switches |
| `docs/GMA_EDITION_PROTOTYPE.md` | Current GMA Edition implementation status, telemetry requirements and pending renderer work |
| `docs/GMA_OPTIMIZATION_CATALOG.md` | Optimisation catalogue, state/cache scope, risks and benchmark protocol |
| `tools/audit_runtime_capability_gaps.py` | Read-only correlation of reported D3D9 caps, requested shader profiles, device creation and failed format checks |
| `tools/inspect_gtaiv_executable.py` | Read-only PE32 import/version inspector for the original `GTAIV.exe`; reports normal and delay imports without modifying the file |
| `tools/analyze_asi_constants.py` | Validates float, integer and boolean shader-constant sidecars and resolves them to shader hashes from `IVLegacy.log` |
| `build/run_probe.bat` | Launches the probe after checking its six bytecode files |
| `.github/workflows/windows-x86-build.yml` | Windows x86 compile/build CI; does not run the GPU probe |

All six v0.2 HLSL sources are retained byte-for-byte. They still target only `vs_2_0` and `ps_2_0`.

## GMA Edition renderer optimisation work

The active development branch is `feature/gma-edition-renderer-prototype`. Its current work is limited to D3D9 state-call suppression and read-only render-path discovery; it does not replace or downscale GTA IV's scene renderer.

Three independent caches are disabled by default:

- `EnableRedundantStateCache=0`: render state, texture-stage state and sampler state.
- `EnableBindingCache=0`: textures, vertex streams (including offset/stride), stream-frequency dividers, index buffers, VS/PS objects, vertex declaration/FVF and viewport.
- `EnableShaderConstantCache=0`: VS/PS float, integer and boolean register ranges.

State-block APIs disable the caches because they can mutate tracked state outside the intercepted setter calls. Binding and shader-constant caches also require strict GTA IV 1.0.0.0 mode and a single-threaded, single-device path. Reset attempts and failed Presents invalidate shadow state. All three switches remain OFF unless deliberately benchmarking this branch.

With `CaptureDrawTelemetry=1`, each captured draw includes its render-target/depth and viewport context. `tools/audit_gma_edition_render_path.py` reports viewport coverage and RT0/depth/viewport relationships; it does not classify the main scene target or implement redirection. The draw-time GetViewport query and detailed logging add overhead, so telemetry should be disabled for clean timing runs.

**Latest integrated synthetic verification:** [Windows x86 CI run #45101202585](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/45101202585) passed both jobs. This is not a GTA IV gameplay or physical GMA 3100 benchmark. Low-resolution redirection, a UI-aware upscale, live fixed-function draw replacement and a general SM3 translator remain unimplemented. No 30 FPS result is established.

The latest complete integrated code run is #45101202585 (both jobs passed). A newer run #45145510926, triggered by the sample INI update, has passed the audit job but its Windows build remains in progress at the DirectX SDK installation step; it is not yet a complete pass.

See [GMA Edition prototype status](docs/GMA_EDITION_PROTOTYPE.md), [optimization catalogue](docs/GMA_OPTIMIZATION_CATALOG.md), and [GMA 3100 architecture research](docs/GMA3100_GTAIV_RESEARCH_AND_ARCHITECTURE.md).



## v0.5.8-alpha changes

- Added `tools/lower_shader_pairs.py`: uses the captured draw-level pair audit, both stage downlevelers and recorded adapter limits before emitting matched VS2/PS2 candidate files.
- Runtime mappings are approved as explicit source VS-hash:PS-hash pairs. The generator refuses stage hashes that are also observed with unapproved partners, preventing a shared shader from being mapped to incompatible SM2 interfaces.
- Corrected the D3D9 state-block vtable indices: `GetRenderState=58`, `CreateStateBlock=59`, `BeginStateBlock=60`, `EndStateBlock=61`. The failed run #295 used 58/59/60 for the three state-block hooks; that replaced GetRenderState and shifted the remaining hooks.
- Extended the synthetic x86 smoke test to verify the slot-58 GetRenderState path and all three state-block hooks. Windows x86 CI run #314 passed both build and paired-audit jobs after these additions.
- Run #314 artifact 14756277716 contains the latest 109-line `IVLegacy.log`. It confirms BeginStateBlock enter/disable/forward/return, then CreateStateBlock and EndStateBlock reach their originals. The fake Create/End methods intentionally return `D3DERR_INVALIDCALL`, which the test expects and verifies.
- These CI results are synthetic test-host evidence only; they do not demonstrate GTA IV startup, rendering on the GMA 3100, image equivalence or genuine FPS.

## v0.5.7-alpha changes

- Added a restricted `vs_3_0` → `vs_2_0` bytecode emitter for the existing straight-line subset that passes the conservative VS2 instruction/register/output audit.
- The emitter removes VS3 output DCL instructions and remaps each single-semantic VS3 output register to the selected fixed VS2 output register. It rejects output registers packing multiple semantics because splitting their component writes is not implemented.
- Added x86 ASI vertex-shader creation fallback: a captured VS3 source hash can be mapped through `[VertexShaderFallbacks]` to a VS2 bytecode file. The hook validates the VS2 profile, logs the replacement/object mapping, and retries the original VS3 shader if replacement creation fails.
- Generalised the runtime bytecode-envelope validator for both VS2 and PS2 and retained separate `[ShaderFallbacks]` and `[VertexShaderFallbacks]` INI sections.
- Both offline converters now require an explicit `--approved-source-hash` before writing a runtime fallback-map entry. Bytecode emission or a stage-level audit alone is not proof that its paired shader, declarations, constants, render states and material are compatible.
- Added synthetic coverage for VS2 bytecode emission, packed-output rejection, map-section preservation and the VS3→VS2 runtime creation fallback.
- Extended Windows x86 CI to emit the synthetic VS2 candidate and verify that both fallback-map sections survive. **CI verification for this branch is pending.** No GTA IV gameplay session or GMA 3100 render test has been run.

## v0.5.6-alpha changes

- Added an opt-in D3D9 state cache for repeated `SetRenderState`, `SetTextureStageState` and `SetSamplerState` calls. It skips only a consecutive setter whose last call on the same device succeeded with the identical state/value.
- The cache is **disabled by default** (`EnableRedundantStateCache=0`). Enable it only for controlled tests with the matching GTA IV 1.0.0.0 build and retain a way to remove the ASI.
- State shadows are invalidated after successful `Reset`, failed `Present` and a newly hooked device. The cache disables itself permanently for that process as soon as `CreateStateBlock`, `BeginStateBlock` or `EndStateBlock` is used, because applying a D3D9 state block would bypass the tracked setters. It also disables permanently if the tracked setters and `Present` are observed on different threads.
- Per-window forwarded/skipped counters are logged by successful Presents. Set `StateCacheReportFrames` to control the reporting interval (1–600, default 120).
- The Windows synthetic runtime test covers duplicate suppression, counter output, Reset invalidation and the state-block safety fallback.
- This is an experimental CPU-side API-call optimization. CI verification and real-game/GMA 3100 benchmarks are required before claiming any FPS gain; no 30 FPS result is implied.

## v0.5.5-alpha changes

- Added opt-in D3D9 `CreateVertexBuffer` and `CreateIndexBuffer` hooks at slots 26 and 27.
- Successful buffer creation logs object address, byte length, usage flags, FVF (vertex buffer) or index format (index buffer), and memory pool.
- The draw analyzer now resolves stream and index-buffer pointers to those creation descriptors, so a draw report includes the bound buffer's size and format rather than an opaque address alone.
- The synthetic host creates a 4,096-byte managed vertex buffer and a 1,024-byte managed INDEX16 buffer, binds them through stream 0 and SetIndices, and submits draws.
- Windows x86 CI run #172 checks both buffer descriptors are present and correctly associated with the first draw. It also retains the declaration/FVF, stream, material-state and shader/constant correlation checks.

These descriptors are synthetic test allocations. They do not describe GTA IV's actual vertex/index buffers.

## Draw-level paired shader compatibility audit (development branch)

The new `tools/audit_shader_pairs.py` joins each captured draw's VS/PS object hashes to the captured bytecode and checks the pair as a unit. It reuses the conservative VS3 and PS3 auditors, compares output/input semantics and component masks, reports when the independent VS2/PS2 register allocations require a coordinated relink, and flags packed PS3 input registers that the current PS2 lowerer cannot split.

For each draw it also checks the vertex shader's declared inputs against the captured `D3DVERTEXELEMENT9` layout (or a deliberately limited common FVF decoder), bound stream/stride and recorded vertex-buffer span; checks that declared/used pixel samplers have non-null texture bindings; compares active render targets with device limits; and constrains VS2 temporary/constant registers plus PS2 temporary registers/instruction slots to the captured adapter caps (including `MaxVertexShaderConst`).

**Important limits:** the tool is diagnostic-only. It does not rewrite bytecode, change render state, or establish runtime driver acceptance or image equivalence. The present log stores hashes/counts for sampler/render/texture-stage states rather than every individual blend, depth, alpha-test and sampler-state value; each result therefore warns that these state semantics still need manual review. FVF support is intentionally partial and rejects unknown layouts. The initial audit targets VS3.0 + PS3.0 pairs; unresolved shader captures or missing draw state are reported as incomplete rather than guessed.

Run the synthetic tests with:

```sh
python tools/audit_shader_pairs.py --self-test
```

To audit a real capture:

```sh
python tools/audit_shader_pairs.py IVLegacy.log IVLegacyCaptures --report paired_shader_audit.json
```

The log and bytecode directory must come from the same game process/session. Hash correlation uses the plugin's FNV-1a 64-bit content hash. Synthetic tests validate parser and decision logic only; they are not captures from GTA IV or an Intel GMA 3100.

## Vertex-stage compatibility audit (development branch)

The offline `tools/audit_vs3_to_vs2.py` checks a deliberately narrow, straight-line `vs_3_0` subset against baseline `vs_2_0` instruction and register limits. It checks instruction slots, temporary/input/constant register ranges, sampler and predicate use, source/destination token modifiers, matrix operand forms, position and point-size outputs, and output-component write masks.

The output audit follows the VS3 declaration model: different semantics may occupy disjoint component masks of the same output register, provided their DCL write masks are unique and non-overlapping. The report preserves each semantic mapping separately, allocates direct `COLOR0/1` semantics to their VS2 color outputs, and compacts TEXCOORD semantics into `oT0-oT7` outputs. A sparse source sequence such as only `TEXCOORD1` can therefore map to `oT0`; the changed link semantic is recorded and flagged because the paired pixel-shader input declaration must also be updated. Sparse component masks such as `.yz` and `.xz` are preserved on the target four-component output; the audit does not impose an undocumented contiguous-mask or consecutive-use requirement on VS2 output registers. The VS3 position and point-size source registers are reserved: neither can share its register with another semantic. The other ten slots are general interpolators and may be any ten of the twelve source indices. Other generic varyings are assigned to remaining VS2 color/texture outputs and carry the same explicit interface-remap flag. `FOG` is treated as a generic VS3 varying, not silently converted to the special VS2 fog register. `POSITION0` requires a full declaration and full output write. `PSIZE0` requires the VS3 full DCL declaration mask, but only source component `.x` is mapped to the scalar VS2 point-size output `oPts.x`.

The auditor rejects static flow-control programs, version-sensitive `sincos`, vertex texture sampling, relative register addressing and pre-transformed `POSITIONT` outputs. It validates the D3D9 `LOOP` token form as two parameters (`aL,i#`) before rejecting flow control. For baseline `vs_2_0`, it accepts `MOVA a0.x` only; `MOV a0` is a `vs_1_1` form, and arbitrary vector write masks on `MOVA` are documented for `vs_2_x` and later.

Matrix forms are checked against their exact instruction contracts: `m4x4` writes `.xyzw` and reads four consecutive constants; `m4x3` writes `.xyz` and reads three; `m3x4` writes `.xyzw` and reads four; `m3x3` writes `.xyz` and reads three; `m3x2` writes `.xy` and reads two. The auditor rejects matrix destination/vector-source aliasing and modified matrix-source operands. For shaders accepted by this restricted subset, the tool can now emit `.vs20.vso` bytecode: VS3 output DCLs are removed and output-register destinations are rewritten to the corresponding VS2 fixed outputs. A source output register carrying multiple semantics is rejected because component-split write rewriting is not implemented. TEXCOORD or generic-semantic remaps are also withheld from the runtime map until the paired pixel shader has been rewritten and reviewed. CI uses synthetic bytecode fixtures only. The analyzer also performs component-aware temporary initialization checks for straight-line programs. It follows source swizzles and the channels consumed by DP3/DP4, CRS, LIT, DST, NRM, SGN and matrix operations. It treats SGN scratch temporaries as undefined after execution and rejects later reads from them. It checks the VS2 read-port limits of one distinct vertex input register and one distinct float-constant register per instruction. Multiple sources may independently swizzle or negate that same constant register; matrix operations name a base constant whose following rows are implicit. Flow-control shaders remain rejected, so initialization is not guessed across branches or loops.

See the [Microsoft VS3 output declaration rules](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dcl-usage-outut-register---vs), [VS2 output registers](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-vs-2-0), [VS2 destination masks](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-modifiers-masking), and the per-opcode [m4x4](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m4x4---vs), [m4x3](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m4x3---vs), [m3x4](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m3x4---vs), [m3x3](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m3x3---vs), and [m3x2](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m3x2---vs) requirements.

### Emit VS2 bytecode candidates

Run the strict auditor and emit only the bytecode candidates that pass its checks:

```sh
python tools/audit_vs3_to_vs2.py IVLegacyCaptures \
  --emit-dir build/bin/IVLegacyFallbacks \
  --fallback-prefix IVLegacyFallbacks \
  --report build/bin/vertex_downlevel.json
```

The output files are candidates, not certified replacements. The tool reports a source FNV-1a hash and a relative fallback path. For a real adapter, set `--max-temps` and `--max-float-constants` to the values captured from that adapter (`VS20Temps` and `MaxVertexShaderConst` in `IVLegacy.log)); the default limits are the baseline VS2 ceilings, not measured GMA 3100 values. The paired audit independently checks captured limits. Only after reviewing the paired shader, render states, vertex layout, constants and actual output should an explicitly approved hash be added to the runtime map:

```sh
python tools/audit_vs3_to_vs2.py IVLegacyCaptures \
  --emit-dir build/bin/IVLegacyFallbacks \
  --fallback-ini build/bin/IVLegacyShaderFallbacks.ini \
  --fallback-prefix IVLegacyFallbacks \
  --approved-source-hash 0123456789ABCDEF
```

Use the real 16-digit source hash from the JSON report, not the example above. The pixel-shader converter uses the same explicit-approval rule. Both tools preserve the other shader-stage section in the same INI. Runtime replacement remains opt-in through `EnableShaderFallbacks=1`; unknown or unapproved hashes continue through the original code path.

**The current implementation does not remove GTA IV's initial SM3 device-capability requirement.** The game may check shader-model capabilities and abort before it ever calls `CreateVertexShader` or `CreatePixelShader`. The current ASI deliberately does not lie about GMA 3100 capabilities. Whether the game reaches shader creation on this adapter must be measured separately. Even if it does, every relevant shader pair, declaration, constant layout, texture binding, render target, blend/depth state and required effect must be validated. Missing features such as MRT formats, depth textures or other fixed-function/device capabilities cannot be solved by rewriting shader bytecode alone.

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

**Prototype 0.5.5-alpha Windows x86 CI passed** in [run #172](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44891303007), commit `fd0f9e9c4eeafb30a4aa7de2893b7ba4f551d589`. All workflow steps passed: six SM2 shaders compiled and inventoried; x86 probe and ASI built; synthetic D3D9 tests exercised the exported `InitializeASI`, shader fallback object mapping, all four draw methods, texture/material state, float/integer/boolean constants, vertex declarations, FVF, streams, index buffers, and both buffer-creation methods. Offline checks verified that draw-time VB/IB pointers resolve to creation descriptors.

[Download the Windows x86 artifact](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44891303007/artifacts/14701424322) — artifact ID `14701424322`, 35 files, SHA-256 `bf39064f10d794d89c2ba04f96b6bc93b0be07a37a43a37fab897bea06dcf148`.

All runtime captures and hardware values in CI are synthetic fake-COM test data, not captures from GTA IV or measurements from the physical GMA 3100. CI does not inspect the actual original executable, load the ASI inside GTA IV, verify rendering/gameplay, or measure FPS.

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


The auditor also validates setup instructions: `DCL`, `DEF`, `DEFB`, and `DEFI` must precede executable instructions, and constant definitions must target the matching float, boolean, or integer constant register classes. `DEFB` follows the D3D9 rule that zero is false and nonzero is true. These setup opcodes are checked as setup records, not mistaken for arithmetic source reads.

## GTA IV render-pipeline inventory (read-only development work)

The D3D9 ASI now records the render/depth surface state associated with draw submissions when `CaptureDrawTelemetry=1`:

- Active render-target slots (up to four): object address, dimensions, format, resource type, usage, pool and multisample settings.
- Active depth-stencil surface with the same descriptor fields.
- Initial/current surfaces are queried after device creation and successful reset when the D3D9 vtable provides the standard getter slots. Explicit `SetRenderTarget` and `SetDepthStencilSurface` snapshots update only after the original API call succeeds.
- Surface snapshots are cleared after a successful device reset. Getter references are released after their descriptors are copied.
- The log buffer was enlarged so the additional per-draw surface descriptors do not crowd out the trailing shader/state/HRESULT fields.

`tools/analyze_asi_log.py` attaches these descriptors to each draw and groups usage by surface, resolution, format and shader pair. It also inventories adapter identity, VS/PS capability versions, relevant shader caps, `CheckDeviceFormat` results, depth-format match results, device creation parameters and render/depth-surface creation/binding events. Adapter description and driver strings are retained as full text.

This is deliberately **observability only**: it does not replace shaders, skip render targets, change D3D9 state, spoof caps, lower resolution, alter LODs, or disable game simulation. A surface is not labelled as a G-buffer, shadow map, reflection or water target from its format alone; that requires correlating shader pairs, pass order and captured contents. The synthetic tests validate parsing and hooks, not GTA IV rendering or GMA 3100 behavior.

The current code still does not implement a complete VS3-to-VS2 translator or an SM3-compatible renderer. The pixel and vertex fallback hooks are opt-in and hash-mapped; paired candidate generation adds an offline path for reviewed VS3/PS3 draw pairs. No emitted shader pair has yet been validated on the physical GMA 3100, and arbitrary SM3 programs remain unsupported.

## D3D9 capability audit and QPC frame profiler (development branch)

The ASI's capability records now include `D3DCAPS9.DevCaps`, the `D3DDEVCAPS_HWTRANSFORMANDLIGHT` result, `VertexProcessingCaps`, stream limits and maximum vertex/primitive values. `CreateDevice` logging separately records whether the caller requested hardware, mixed or software vertex processing. The capability bit is evidence of what the driver advertises; it does not by itself prove that fixed-function rendering will be faster for GTA IV.

Optional profiling is disabled by default. Enable it in `IVLegacy.ini`:

```ini
[General]
EnableFrameProfiler=1
FrameProfilerWindowFrames=120
```

The profiler measures successful-`Present`-return intervals, wall time spent inside `Present`, and wall time inside the four D3D9 draw methods (`DrawPrimitive`, `DrawIndexedPrimitive`, and both `UP` variants). It emits average, P50, P95, P99 and maximum frame intervals, plus draw-call and Present summaries, once per configured sample window.

`draw_api_ms` is elapsed time inside the D3D9 API call, not a pure count of CPU instructions; it can include driver stalls. `unattributed_ms` is the interval remaining after subtracting measured draw and Present call durations. It includes game simulation, other D3D9 calls and other work, so it is not a direct measurement of world-simulation time. **GPU execution time is not measured** by this profiler (`gpu_time=not_measured`).

The Windows synthetic smoke test enables a one-frame window, advertises a fake HW-T&L capability, requests software vertex processing, submits four synthetic draw calls and checks the profiler summary. Those values verify the instrumentation path only. They are not measurements from the physical GMA 3100 or GTA IV.


## Runtime capability-gap audit

Run the read-only analyzer against a real `IVLegacy.log`:

```bat
py -3 tools\\audit_runtime_capability_gaps.py IVLegacy.log --json capability-gap-report.json
py -3 tools\\audit_runtime_capability_gaps.py --self-test
```

It compares the adapter's reported VS/PS version caps with the shader profiles observed at runtime, and records whether D3D9 device creation was requested before or after the first caps record. It also lists failed format/depth-match checks. This helps distinguish a shader-model rejection from later resource-format or device-creation failures.

The report is intentionally conservative: a profile above the reported cap proves that passing that shader through unchanged is unsupported, but the log alone cannot prove why GTA IV exits. Likewise, seeing a device-creation request does not prove the renderer initialized successfully. The tool does not spoof capabilities or patch the game's gate. It is an evidence-gathering step before implementing any cap override.

A cap override is unsafe until every affected feature has a working fallback. In particular, advertising SM3 while still forwarding SM3 bytecode to the GMA 3100 driver would simply move the failure to shader creation. The intended order remains: record real caps, identify the exact gate, build and validate SM2 replacements for observed shader pairs, then consider narrowly scoped capability presentation.
