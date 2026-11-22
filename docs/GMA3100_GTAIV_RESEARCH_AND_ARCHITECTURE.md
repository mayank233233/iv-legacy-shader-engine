# GMA 3100 GTA IV Compatibility and Optimization Research

**Target game:** Grand Theft Auto IV PC 1.0.0.0  
**Target machine:** ASUS P5KPL-AM IN; Intel GMA 3100 (PCI VEN_8086 / DEV_29C2); Pentium Dual-Core E5200 2.50 GHz; 3 GB DDR2; Windows 8.1 32-bit; 1440×900  
**Objective:** an installable, game-loaded compatibility/optimization mod, with a long-term 30 FPS target.  
**Current baseline:** Prototype 0.5.4-alpha: a standalone SM2 D3D9 probe, an original-version-gated x86 ASI telemetry module, and offline shader, material-state, constant and vertex-input analysis tools. It is not yet a playable GTA IV mod.

## 1. Executive finding

The main blocker is not a normal graphics-quality mismatch. Intel documents GMA 3100 as DirectX 9.0c with **Pixel Shader 2.0 and Vertex Shader Model 2.0**. GTA IV's DD3D60 error is documented as requiring Shader Model 3.0 or higher. DirectX 9.0c API support does not imply Shader Model 3.0 support.

The project therefore has two linked tasks:

1. **Compatibility:** get past the game's capability gate and provide shader programs and render-target behavior that the GMA 3100 driver actually supports.
2. **Performance:** reduce work submitted to the E5200/GMA 3100 and reduce memory/bandwidth pressure.

A mod that merely lies about Shader Model 3.0, changes an INI value, or lowers draw distance cannot solve the first problem. If it reports fake caps but still passes SM3 bytecode to the driver, shader creation or rendering will fail. A 30 FPS result is not established and must not be promised.

## 2. Target platform facts and unknowns

### Confirmed target facts

| Component | Known target | Engineering implication |
|---|---|---|
| GPU | Intel GMA 3100, PCI 8086:29C2 | This is GMA 3100, not GMA X3100. |
| D3D API | Direct3D 9.0c | A D3D9 integration path is appropriate. It does not grant SM3 features. |
| Shader model | Hardware PS 2.0 / VS 2.0 | Baseline SM2 shaders are the safe target; do not assume ps_2_x, vs_2_a, or SM3. |
| GPU design | 400 MHz core; Intel lists up to 1.6 dual-texture GPixel/s; DVMT shares system memory | Fill-rate and memory traffic matter. DVMT is not dedicated VRAM. |
| CPU | Pentium Dual-Core E5200, 2 cores at 2.50 GHz | Render-thread overhead and game-thread work may both constrain frame time. |
| RAM / OS | 3 GB DDR2; Windows 8.1 32-bit | GTA IV has a 32-bit address space and the integrated GPU shares system memory. Avoid unbounded caches and large staging surfaces. |
| Display | 1440×900 | Lower resolution can reduce pixel cost, but does not directly reduce simulation or draw-list CPU cost. |

### Capabilities that remain unknown

Do not substitute generic Direct3D assumptions for exact Intel driver values. The eventual game-loaded plugin must record, from the actual adapter/device:

- VertexShaderVersion, PixelShaderVersion, VS20Caps, PS20Caps.
- NumSimultaneousRTs, MaxSimultaneousTextures, MaxTextureBlendStages.
- MaxVertexShaderConst, PS 2.0 instruction/temp caps and supported shader instructions.
- Render-target and depth-stencil format support through CheckDeviceFormat.
- Filtering, blending, alpha-test, fog, depth, stencil and texture-format support.
- Hardware/software vertex-processing capability, device creation flags and device-reset behavior.
- Actual texture-memory reporting, distinguishing shared DVMT from dedicated memory.

Microsoft's baseline D3D9 capability documentation includes a one-render-target, PS 2.0 baseline. This is a warning, **not proof that this particular GMA driver reports exactly one render target**. The actual caps must be queried by our plugin. Never fake unsupported capabilities before implementing and testing the corresponding fallback.

## 3. GTA IV shader evidence: why a generic SM2 shader is not enough

The public [GTA IV Shaders decompilation repository](https://github.com/robi29/GTA-IV-Shaders) contains a win32_30_nv8 shader set, ASM disassemblies and .fxc.xml metadata. Its Git tree lists 1,689 .asm files (856 pixel-shader and 833 vertex-shader listings) and 102 .fxc.xml metadata files. These are important research assets, but the exact mapping between each file, runtime permutation and every shader used by game 1.0.0.0 still has to be established.

Representative shader inspection:

| Shader family / inspected listing | Evidence | Reduction problem |
|---|---|---|
| gta_defaultPS1.asm | ps_3_0; samples s0, s10 and s15; uses shadow-map sampling, lighting and multiple intermediate values | A simple one-texture PS2 material cannot preserve all of this. |
| deferred_lightingPS1.asm | ps_3_0; reads G-buffer samplers s0, s1, s2, s4, s5 and s15; contains if / rep control flow and uses temporary register r31 | The lighting/shadow path exceeds baseline PS2 register/control-flow limits. |
| waterPS1.asm | ps_3_0; uses samplers 0–2 and temporary register r20 | Water/reflection needs a reduced path, not an unchanged compile. |
| gta_treesPS1.asm | ps_3_0; uses samplers 0 and 10 and temporary register r20 | Vegetation alpha, lighting and animation need their own fallback. |
| gta_vehicle_paint1PS1.asm | ps_3_0; two samplers and a larger material program | Vehicle paint/reflection/specular needs a reduced material variant. |

Microsoft's PS 2.0 reference describes 64 arithmetic plus 32 texture instruction slots and 12 temporary registers. PS 3.0 increases the minimum instruction budget to 512, has 32 temporary registers and adds features such as loop control, texldl, a larger constant/input register model and other shader capabilities. Dynamic flow-control instructions are not part of baseline ps_2_0; the ps_2_x extension is a different capability tier and cannot be assumed on this adapter.

**Consequence:** there is no safe mechanical "change ps_3_0 to ps_2_0" operation. Unsupported control flow, instruction budgets, temporary-register pressure, constants, input semantics, texture LOD behavior and render-target formats have to be addressed shader by shader or by replacing entire material/effect families with lower-cost variants.

The decompiled repository's shader metadata records constant-register indices and shader variants. Replacement programs must preserve these interfaces. The files are a reverse-engineering reference, not permission to copy code without checking relevant licences.

### Proposed low-end shader policy

The target is a deliberately reduced visual profile, not pixel-perfect parity with the original high-end renderer:

- Replace complex per-pixel multi-light calculations with ambient plus a small number of simple lights; move suitable diffuse work to vertex lighting.
- Replace cascaded soft-shadow / PCSS loops with no dynamic shadows or a simpler shadow method. If the remaining pass still costs too much, disable it.
- Remove or simplify screen-space and multi-sample effects, advanced reflections, parallax, expensive specular layers, volumetric effects and costly post-processing.
- Use simpler water and glass variants; preserve alpha-tested foliage and essential transparency where possible.
- Keep skinning, vehicle deformation, essential character animation, depth behavior and material alpha semantics. A fallback that renders the world but breaks animated characters or transparent surfaces is not usable.
- Keep each replacement shader within exact reported PS2/VS2 caps. Compilation success alone does not prove compatibility with the game's constants, vertex declarations, blending or depth state.

A low-end forward-style path for selected materials/effects is one possibility, not a confirmed complete replacement for GTA IV's renderer. The actual pass graph, target switching, resource formats and shader permutations must be mapped first. GBufferTextureSampler names in a deferred-lighting shader show that it consumes G-buffer-like inputs; they do not by themselves prove how many simultaneous render targets the GMA must support.

## 4. D3D9 interception and game integration architecture

The intended product is a Win32/x86 game-loaded ASI/plugin plus a D3D9 interception/replacement layer as needed. It is not a new Vulkan renderer and does not require DXVK.

### Layer A — version-aware ASI plugin

**Initial implementation exists in `src/IVLegacyASI.cpp`.** It is a Win32/x86 ASI-style DLL module, not yet a completed compatibility mod.

Implemented in the current source:

- Bootstrap runs from a worker thread started by DLL_PROCESS_ATTACH.
- Validates the host as a 32-bit PE named `GTAIV.exe`; by default it also requires the executable's file-version resource to report 1.0.0.0.
- Creates `IVLegacy.log` and a default `IVLegacy.ini` beside the host executable.
- Supports `EnableD3D9Telemetry` and `StrictGTAIV100` settings.
- Logs target validation, initialization and hook installation failures.
- Does not yet fingerprint the executable by cryptographic hash or validate code signatures. Before adding any game-code patch, we need build-specific PE identity and signature/byte checks. No guessed patch offsets are acceptable.
- The ASI must remain loaded for the life of the process; hot-unloading is unsafe because active IAT/vtable entries point into the module.

ZolikaPatch is the strongest old-version compatibility reference found: its author lists support for 1.0.0.0, 1.0.4.0, 1.0.7.0 and 1.0.8.0. Its fixes include loading, VRAM reporting, high-FPS cutscene/bike issues, crash fixes and graphics/gameplay fixes. The independent [Gillian Guide ZolikaPatch reconstruction](https://github.com/gillian-guide/ZolikaPatch) is a useful source-level study of per-build hooks, signatures, exact x86 register/stack contracts and feature toggles; it is not the original author's source and should not be copied blindly.

### Layer B — Direct3D 9 compatibility instrumentation

**A first hook layer is now implemented.** It is deliberately observational; it does not spoof SM3 caps or substitute shaders.

- The current implementation patches the main executable's import-table entry for a direct `d3d9.dll!Direct3DCreate9` import. It logs a clear failure if that import is not present or the original thunk is unavailable. It does not yet cover every GetProcAddress, delay-load, proxy-DLL or secondary-module loading path.
- After Direct3DCreate9 returns, the plugin clones that object's vtable and observes IDirect3D9 methods: GetAdapterIdentifier, CheckDeviceFormat, CheckDepthStencilMatch, GetDeviceCaps and CreateDevice.
- After CreateDevice succeeds, it clones the returned device object's vtable and observes GetDeviceCaps, Reset, failed Present calls, CreateRenderTarget, CreateDepthStencilSurface, SetRenderTarget, SetDepthStencilSurface, CreateVertexShader and CreatePixelShader.
- The hooks call the original COM methods and log their HRESULTs. The adapter logger records PCI VendorId, DeviceId, SubSysId, Revision, driver version and description. Capability logging records VS/PS versions and available SM2 cap fields. Surface logging records size, format, multisample and usage where exposed.
- Shader creation currently logs only the bytecode version token/profile and HRESULT. It does not yet dump, hash, translate or replace bytecode.
- Current CI has compiled and linked the Win32/x86 ASI. A synthetic GTAIV.exe host and D3D9 hook smoke test have been added to CI; their latest result is tracked in STATUS.md. This validates a controlled test host, not GTA IV's actual import table or physical graphics hardware.

The current hook table is a first instrumentation scaffold, not a full D3D9 proxy. It must be validated against the actual GTA IV 1.0.0.0 binary before we rely on the import-table assumption. The wrapper must continue to preserve COM reference counts, device identity, call ordering, error propagation and lost-device/reset behavior.

### Layer C — Shader translator and fallback library

The realistic first implementation is a **precompiled, hash-indexed fallback library** for selected, well-understood shader variants. A general runtime SM3-to-SM2 compiler is a much larger project.

A proper pipeline should include:

1. Capture/hash each shader bytecode and map it to a decompiled source/FXC metadata entry when possible.
2. Parse the D3D shader token stream into an intermediate representation; preserve declarations, constants, samplers and input/output semantics.
3. Validate features and resource use against the actual GMA caps.
4. Apply explicit lowering passes: remove unsupported branches/loops, unroll only bounded loops, reduce instruction/temp use, replace unsupported texture operations where semantics permit, and eliminate expensive effects when a valid approximation exists.
5. Compile to vs_2_0 / ps_2_0, validate bytecode headers and instruction counts, and cache by source hash + preset + compiler version.
6. Provide a known fallback for every covered shader. If a shader is unknown or cannot be translated, fail safely with a clear diagnostic rather than passing unsupported SM3 bytecode to the driver.

The first shader families to analyse are default/world, normal/specular/reflection, vehicle, pedestrian/skin, trees/alpha, water, shadow, post-FX and deferred-lighting variants. This is a prioritisation list, not an assertion that these cover every runtime shader.

### Layer C — Shader translator and fallback library

The realistic first implementation is a **precompiled, hash-indexed fallback library** for selected, well-understood shader variants. A general runtime SM3-to-SM2 compiler is a much larger project.

A proper pipeline should include:

1. Capture/hash each shader bytecode and map it to a decompiled source/FXC metadata entry when possible.
2. Parse the D3D shader token stream into an intermediate representation; preserve declarations, constants, samplers and input/output semantics.
3. Validate features and resource use against the actual GMA caps.
4. Apply explicit lowering passes: remove unsupported branches/loops, unroll only bounded loops, reduce instruction/temp use, replace unsupported texture operations where semantics permit, and eliminate expensive effects when a valid approximation exists.
5. Compile to vs_2_0 / ps_2_0, validate bytecode headers and instruction counts, and cache by source hash + preset + compiler version.
6. Provide a known fallback for every covered shader. If a shader is unknown or cannot be translated, fail safely with a clear diagnostic rather than passing unsupported SM3 bytecode to the driver.

The first shader families to analyse are default/world, normal/specular/reflection, vehicle, pedestrian/skin, trees/alpha, water, shadow, post-FX and deferred-lighting variants. This is a prioritisation list, not an assertion that these cover every runtime shader.

## 5. What we borrow from Minecraft optimization mods

These are **design principles**, not code ports. Minecraft's renderer, asset formats and APIs differ from RAGE/D3D9, and some modern Minecraft mods require graphics APIs far newer than GMA 3100 can provide.

| Minecraft project | What it actually optimizes | GTA IV adaptation | What not to copy |
|---|---|---|---|
| [Sodium](https://github.com/CaffeineMC/sodium) | Rendering-engine replacement, reduced CPU/GPU overhead, visibility work and efficient buffers | A custom low-end D3D9 submission path: state caching, reusable buffers, conservative render culling, simpler LOD/material passes and fewer avoidable state changes | Sodium itself targets modern OpenGL (official support requires OpenGL 4.5); do not port its renderer or depend on its API. |
| [Lithium](https://github.com/CaffeineMC/lithium) | Removes redundant game/client/server work while preserving behavior | Cache safe deterministic render/asset queries; avoid repeated lookups; update render-only state only when it changes | Do not throttle arbitrary AI, physics, scripts or mission ticks. These are gameplay semantics, not cosmetic work. |
| [ImmediatelyFast](https://github.com/RaphiMC/ImmediatelyFast) | Batches immediate rendering and reduces draw calls and CPU–GPU transfer overhead for entities, particles, text and GUI | Batch only compatible particle/UI/effect work where draw order, blending and state are proven safe; reuse upload buffers | Do not reorder transparent geometry or merge draws across different materials, depth/blend states or transforms. |
| [FerriteCore](https://github.com/embeddedt/FerriteCore) | Reduces memory by deduplicating repeated immutable objects/data structures and avoiding unnecessary allocations | Investigate immutable asset metadata, duplicate CPU-side blobs, interned names and repeated resource descriptors; pool temporary allocations | Do not merge mutable D3D resources or objects whose lifetime, lock or ownership differs. Memory savings do not automatically increase FPS. |
| [OptiFine](https://github.com/sp614x/optifine) | Feature toggles, culling, render-distance controls and visible-only animation updates | Visible-only animation updates, safe LOD/range settings, disable expensive shadows/reflections/post effects | OptiFine's own documentation says Render Regions are not recommended on integrated graphics. Shader packs and modern GL assumptions are not appropriate here. |
| [EntityCulling](https://github.com/tr7zw/entityculling) | Avoids rendering entities not visible to the camera, using visibility tests | Conservative culling of render-only objects with reliable bounds; keep an always-render whitelist for mission-critical/transparent objects | Never cull simulation, collision, AI or mission processing. Heavy asynchronous path tracing may cost too much on a two-core CPU. |
| [ModernFix](https://github.com/embeddedt/ModernFix) | Startup, memory and allocation fixes | Reduce duplicate allocations, improve loading caches and bounded resource reuse | Loading-time gains are not the same as in-game FPS. |

### GTA IV-specific community references

- [ZolikaPatch IV](https://zolika.dev/mods/ivpatch): fixes crashes, VRAM reporting, loading times, high-FPS cutscene/bike issues, shadows, LOD and other engine/game bugs; the author lists 1.0.0.0 support. It is a compatibility/bug-fix reference, not proof of GMA shader compatibility.
- [FusionFix](https://fusionfix.io/games/gtaiv/): broad graphics/gameplay fixes, settings, shader changes, high-FPS fixes and modern API options. Its current legacy add-on is listed only for old versions 1.0.7.0 and 1.0.8.0, not 1.0.0.0. Treat source/ideas as references, not a drop-in base for this target.
- [GTA IV Shaders](https://github.com/robi29/GTA-IV-Shaders): the main public shader-decompilation reference for mapping shader variants and building reduced material equivalents.
- [Gillian's GTA IV Modding Guide — optimization](https://gillian-guide.github.io/optimization/): documents that there is no universal optimization solution. Its DXVK guidance lists modern GPU requirements, including Intel Skylake-generation iGPU or newer for current Windows support. GMA 3100 is far older and this machine has no Vulkan driver, so DXVK is not a viable path.
- [Ultimate ASI Loader](https://github.com/ThirteenAG/Ultimate-ASI-Loader): reference for ASI plugin loading. The plugin must still be built and tested specifically for GTA IV 1.0.0.0 and 32-bit Windows.

Do not bundle other projects' binaries or source files without checking licences, version compatibility and hook conflicts. Reimplement compatible ideas behind our own settings and keep optional overlaps disabled by default.

## D3D9 redundant scalar state cache — experimental implementation

The isolated branch `feature/redundant-d3d9-state-cache` adds the first runtime optimization experiment. It adapts the state-shadowing lesson from ImmediatelyFast/Sodium to the native D3D9 path without replacing GTA IV's renderer.

- It covers only `SetRenderState`, `SetTextureStageState` and `SetSamplerState`. A repeated call is skipped only when the exact state index and value were previously accepted by the original D3D9 method on the same device.
- The feature is opt-in and defaults to off: `[General]`, `EnableRedundantStateCache=1`. `StateCacheReportFrames` selects a 1–600 successful-Present reporting interval (default 120).
- State shadows are invalidated on successful device Reset, failed Present and device creation/hook changes.
- D3D9 state blocks can apply state without passing through these setters. The plugin therefore hooks `CreateStateBlock` (slot 58), `BeginStateBlock` (59) and `EndStateBlock` (60), and disables the cache permanently for that process as soon as any is used. It does not attempt to intercept every `IDirect3DStateBlock9` method.
- The serialized cache lock protects check/call/update ordering. This may itself cost CPU time or contend if callers use the device concurrently; the optimization is not assumed to be faster until measured.
- A failed Present invalidates the shadow, but this is not a formal proof for every lost-device or proxy-driver edge case. Keep the option disabled outside controlled tests until the actual game/driver is validated.

Successful Presents emit `D3D9_STATE_CACHE_WINDOW` with forwarded/skipped counts for each setter family. This proves only that the wrapper suppressed calls in the synthetic test. It does not measure GPU time, prove a GTA IV performance gain or establish 30 FPS on GMA 3100. Compare baseline and enabled builds on the same saved route and report average frame time, 1% lows, API-call counts and stability before retaining the optimization.

## 6. CPU, memory, streaming and renderer optimization plan

Reverse-engineering research in [LibertyFlux's engine notes](https://monstercameron.github.io/LibertyFlux/engine.html) describes a game thread handling scripts, people, vehicles, physics, animation and draw lists; a separate render thread; audio workers; and a streaming path. The page states that parts of the thread ordering are inferred, so use it as an informed map, not an official Rockstar specification. It also inventories large pedestrian-AI, streaming, file/memory and physics subsystems. This reinforces why indiscriminate gameplay throttling is unsafe.

### Highest-priority, lower-risk optimizations

- **D3D9 state cache:** skip redundant state/texture/sampler/shader/stream binds after proving state-shadow correctness. Invalidate the cache on reset, external device calls and any untracked mutations.
- **Buffer/resource reuse:** reuse dynamic vertex/index/upload buffers; avoid repeated allocations and unnecessary Lock/Unlock/copies. Respect D3D9 lock flags and GPU ownership.
- **Safe batching:** start with compatible HUD, particle or effect batches only where depth, blending, material and order are identical. Preserve transparent ordering.
- **Render-only culling:** use existing bounds/visibility data where possible. Do not add an expensive per-object ray test every frame.
- **LOD and density:** use game controls/data first; then investigate version-verified hooks to lower distant geometry, vegetation, decals, lights and shadow ranges. Preserve near-field collision and mission geometry.
- **Shader/effect budget:** remove costly reflection, shadow, water, post-FX and per-pixel lighting features before adding complicated replacement passes.
- **Bounded asset caching:** deduplicate immutable CPU-side data and avoid duplicate parsing/allocations. Do not cache unlimited textures in shared RAM.

### Higher-risk optimizations

- Throttling distant entity updates, AI, physics or script execution.
- Changing streaming thread scheduling or lock behavior.
- Rebuilding/reordering the draw list.
- Merging arbitrary mesh draws.
- Replacing the complete rendering pipeline or moving work across threads.

These require profiling and game-specific reverse engineering; they should not be enabled by default.

### Why multiple passes can be a bad fit

Intel's integrated-graphics developer guidance warns that intermediate render targets and multi-pass rendering can move data through shared system memory repeatedly. Therefore, translating one SM3 pass into many SM2 passes may solve an instruction limit but make performance worse. Prefer a single very simple pass where possible; split only when correctness requires it and the traffic cost is measured.

## 7. Project milestones — real mod, not another standalone probe

| Milestone | Deliverable | Exit condition |
|---|---|---|
| Research baseline | Version/capability matrix, shader-family inventory and known-unknowns list | Architecture and failure modes documented |
| 0.4-alpha — x86 telemetry foundation | Strict 1.0.0.0 version gate, log/config, main-executable Direct3DCreate9 IAT hook, per-object D3D9 vtable telemetry and bounded shader capture | Synthetic Windows x86 D3D9 smoke test passes; actual GTA IV load/import path remains unverified |
| 0.5-alpha — loader and draw telemetry | Exported InitializeASI, opt-in shader-object/hash and frame-indexed draw telemetry | Synthetic Windows x86 runtime test passes; no original-game shader captures |
| 0.5.1-alpha — offline analysis | D3D9 log correlator, read-only PE32 import inspector and restricted PS3-to-PS2 audit candidate tool | Parser/PE/audit self-tests pass; original GTAIV.exe has not yet been inspected |
| 0.5.4-alpha — material and vertex-input inventory | Texture descriptors, sampler/render/texture-stage fingerprints, float/int/bool constants, vertex declarations/elements, FVF, streams and index-buffer correlation | Synthetic Windows x86 run #165 passes; original-game state remains uncaptured |
| 0.5.5-alpha — vertex/index buffer descriptors | Creation size, usage, FVF/index format and pool joined to draw-time stream/index bindings | Synthetic Windows x86 run #172 resolves 4096-byte VB and 1024-byte INDEX16 IB descriptors |
| 0.6 — original-game inventory and first fallback | Verify original executable import/load path, capture real shader/material/input associations, then select one proven fallback family | Evidence from unmodified GTAIV.exe 1.0.0.0 and a tested material fallback on target D3D9 |
| 0.7 — low-end renderer profile | More critical shader families plus safe state caching, reduced effects and LOD options | Game reaches a repeatable playable scene without missing critical materials |
| 0.8 — memory/CPU work | Bounded resource reuse, safe culling and selected render batching | Improvements measured without mission/physics regressions |
| 1.0 — installable compatibility/optimization release | Packaged plugin, presets, reversible install, known limitations and benchmark instructions | Confirmed game loading/rendering on target hardware; FPS stated only after real measurements |

The first test will be a **GTA IV-loaded plugin build**, not a request to run the old standalone probe. The probe remains a developer reference for generic SM2 behavior.

## 8. Performance target and acceptance criteria

**30 FPS is the long-term target, not a prediction.** The machine is below the game's original discrete-GPU class and lacks the required shader model. The GPU is shared-memory and SM2-only, while the CPU has two cores. Even if compatibility is solved, the game thread, render thread, streaming and GPU pixel workload may prevent stable 30 FPS.

Use an evidence-based sequence:

1. The game starts without a shader-model rejection.
2. A scene renders without black/missing critical materials or a device-reset loop.
3. The mod maintains correct mission, pedestrian, vehicle, physics and animation behavior.
4. Measure frame-time percentiles (not just a brief average FPS), CPU/render/GPU wait indicators, shader fallback hit rate, draw count, memory and streaming stalls.
5. Tune resolution and low-end preset (initial candidates: 800×600 and 640×480), then assess whether a stable 30 FPS cap is attainable.
6. Report average and 1% low frame rates only from repeatable in-game tests; do not infer performance from shader compilation or hosted CI.

## 9. Immediate engineering decision

Prototype 0.5.5-alpha passes the complete Windows x86 CI workflow [run #172](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/44891303007). The synthetic host resolves and calls the exported `InitializeASI`, creates and binds fake vertex/pixel shader objects, exercises all four draw methods, maps a synthetic PS3 request to a configured PS2 replacement, and records textures, sampler/render/texture-stage states, float/integer/boolean constants, vertex declarations, FVF, streams, index buffers and buffer creation descriptors.

The offline analyzer now joins draw-time vertex/index buffer pointers to their creation records. The CI fixture verifies a 4096-byte managed vertex buffer and a 1024-byte managed INDEX16 index buffer, together with a POSITION/TEXCOORD declaration, stream offset/stride/frequency and subsequent FVF draws. These are synthetic buffers and layouts, not captures from GTA IV.

The read-only executable inspector can report PE architecture, file version, normal/delay imports, D3D9 factory import presence and SHA-256 without modifying a file. It has **not** been run against the user's original `GTAIV.exe` 1.0.0.0. Until that import table and the actual ASI-loader startup are verified, the main-executable IAT hook remains an assumption.

Draw and resource telemetry records submitted D3D9 state; it does not measure GPU time, vertex processing cost, visible primitives, memory pressure, stalls or FPS. The offline analyzer's grouping and object-pointer joins are diagnostic aids; they are not a complete resource-lifetime or performance profiler.

The offline SM3-to-SM2 tool remains limited to a narrow pixel-shader subset. It does not handle vertex shaders or general SM3 constructs, and emitted bytecode is only a structural candidate. The five shader captures in CI are synthetic fake-COM programs; no actual GTA IV shader has been captured or converted.

Next sequence:
1. Inspect the user's original executable read-only and verify its file version and D3D9 normal/delay-import path.
2. Verify ASI loading through the intended loader on that same original executable.
3. Capture real shader creation, shader-object/hash associations, constants, material textures/samplers/render states, declarations, vertex/index buffer descriptors and render-target requirements.
4. Map real shader hashes and input layouts to GTA IV disassembly/metadata, then identify the smallest shader families that might be preserved on SM2.
5. Implement and validate a guarded fallback for one evidenced material family; unknown shaders remain on the original path and capabilities are never spoofed.

This remains an instrumentation/analysis foundation, not an installable playable mod. The actual GMA 3100 driver, original GTA IV scenes, mission/gameplay integrity and 30 FPS objective remain untested. A compatibility renderer and repeatable frame-time data are required before any performance claim.

## Vertex-stage audit prototype — 2026-11-22

The development branch `feature/vs3-vs2-vertex-audit` adds a read-only structural audit for `vs_3_0` bytecode. It uses the documented baseline `vs_2_0` constraints: 256 instruction slots, 12 temporary registers, 16 input registers, at least 256 float constants, and fixed output classes (position, fog, point size, two colors and eight texture-coordinate outputs). The tool checks a limited straight-line subset and produces a semantic output-mapping plan; it does not emit replacement bytecode.

The initial subset explicitly rejects:
- Static flow control until the IF/loop/subroutine structure and cost can be validated. The parser still validates the two-parameter D3D9 `LOOP aL, i#` instruction form and instruction slot count before rejecting it.
- The two-operand VS3 `sincos` form, because VS2 uses a different four-operand form.
- Vertex texture sampling, predicate registers and VS3-only instructions.
- Relative register addressing and pre-transformed `POSITIONT` outputs.
- Baseline `vs_2_0` address-register update is restricted to `MOVA a0.x`. The `MOV a0` path is documented for `vs_1_1`; arbitrary `MOVA` component write masks are documented only for `vs_2_x` and later.
- Missing writes to the required full-width position output.

The output interface is not treated as a one-source-register/one-destination-register mapping. Microsoft's D3D9 `dcl_usage` reference allows different semantics to occupy disjoint component masks of one VS3 output register (for example, `COLOR0 o3.x`, `TEXCOORD3 o3.yz`, and `FOG o3.w`). The audit retains each declaration separately, checks mask overlap and duplicate semantic identifiers, then plans a split into the ten generic VS2 outputs (`oD0/oD1`, `oT0-oT7`). Standard `COLOR0/1` mappings are preserved. TEXCOORD semantics are compacted in sorted order into `oT0-oT7`; sparse source indices and remapped generic semantics are explicitly flagged for a paired pixel-shader interface rewrite. Sparse component masks such as `.xz` and `.yz` remain valid target masks; the audit no longer treats them as requiring a color-output fallback and does not invent a contiguity rule for the VS2 output bank. Other semantics (including VS3 `FOG`) are allocated to remaining VS2 color/texture outputs and flagged for the same reason. `POSITION0` remains a full-width special output. `PSIZE0` requires a full VS3 declaration mask but only its scalar `.x` value maps to VS2 `oPts.x`. The analyzer makes no claim that these interface rewrites have been implemented in bytecode.

This analyzer is a triage tool for future shader-family work, not a translator or compatibility fix. The CI fixtures are synthetic. No claim is made about the actual GTA IV vertex-shader inventory or GMA 3100 driver.

Specification references:
- [Microsoft: Vertex Shader Differences](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-differences)
- [Microsoft: Registers — vs_2_0](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-vs-2-0)
- [Microsoft: Instructions — vs_2_0](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-instructions-vs-2-0)
- [Microsoft: Flow Control Nesting Limits](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-instructions-flow-control)


### Matrix-instruction audit rules — 2026-11-22

The analyzer now enforces the exact D3D9 vertex-shader matrix-op destination masks and constant spans:

| Instruction | Destination mask | Consecutive matrix constants |
|---|---|---:|
| m4x4 | `.xyzw` | 4 |
| m4x3 | `.xyz` | 3 |
| m3x4 | `.xyzw` | 4 |
| m3x3 | `.xyz` | 3 |
| m3x2 | `.xy` | 2 |

The number of constant registers follows the result dimension (the second dimension of the matrix op). The source matrix register may not be swizzled or negated, and the destination may not alias the vector source. These rules are covered by synthetic boundary and negative fixtures. See the Microsoft [m4x4](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m4x4---vs), [m4x3](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m4x3---vs), [m3x4](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m3x4---vs), [m3x3](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m3x3---vs), and [m3x2](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/m3x2---vs) references.


### Component-aware temporary initialization and input-port checks — 2026-11-22

The VS2 register reference gives temporary registers no default value, a single write port, and three read ports. Each input register has one read port; a single instruction may access only one distinct input register. The Microsoft constant-float register reference further states that one instruction may access only one distinct constant register, while separate sources can swizzle or negate that same vector independently. Matrix instructions encode one base constant whose additional rows are implied by the opcode. The analyzer now checks those input/constant read-port limits and performs straight-line definite-initialization analysis for temporary components.

The component tracker maps source swizzles to the actual source components read. It models DP3/DP4 as xyz/xyzw; CRS according to its cross-product component dependencies; LIT using src.x for dest.y and src.x/src.y/src.w for dest.z (src.z is ignored); DST using its separate src0.y/src0.z and src1.y/src1.w dependencies; NRM using xyz for the normalization factor and src.w only when dest.w is written; SGN using the destination write mask for src0 and marking src1/src2 scratch registers undefined after execution; and matrix operations using the vector dimension of each matrix instruction.

Static flow control remains outside this analysis. IF/loop/call shaders are rejected before a candidate is reported, so the tool never claims that initialization is definite across unanalysed branches or loops.

References: [VS2 register read-port table](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-vs-2-0), [input-register rules](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-input), [LIT](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/lit---vs), [DST](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dst---vs), [NRM](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/nrm---vs), [CRS](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/crs---vs), and [SGN](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/sgn---vs).


### Point-size output mask correction — 2026-11-22

The VS3 PSIZE0 DCL must use a full xyzw declaration mask, and no other semantic may share that register. The point-size value itself is scalar: only x is consumed, so the lowered VS2 point-size output is written through its x component. The analyzer now keeps the full declaration-mask check separate from the x-only effective write check. Synthetic tests cover the valid full-DCL/x-write case and reject a partial PSIZE declaration or y-only output write. See the Microsoft [output DCL usage rules](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dcl-usage-outut-register---vs) and [point-size register reference](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-point-size).


### Constant register read-port rule — 2026-11-22

The previous audit threshold of two distinct float constants was too permissive. The Microsoft reference specifies that any single instruction may access only one constant register; sources within the same instruction may apply independent swizzles and negation to that same constant. The analyzer now enforces one distinct c-register for ordinary instructions. Matrix operations remain valid because their encoded matrix operand is a base c-register and the required consecutive matrix rows are implicit. Tests verify that two sources reading c4 with different swizzles are accepted, an instruction that uses c0 and c1 is rejected, and matrix operations still pass their dedicated constant-span tests.

Reference: [Microsoft — Constant float register](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-constant-float).


### VS3/VS2 output mapping reference audit — 2026-11-22

The output allocation model is grounded in the Microsoft D3D9 `dcl_usage` reference: among the 12 VS3 output registers, one is position, up to ten are general interpolators (any ten register indices may be used), and one optional register is point size. The point-size DCL uses the full write mask even though only scalar `x` is consumed. Distinct semantics may share one output register through non-overlapping component masks. The audit translates this into a diagnostic plan for the ten VS2 generic outputs: two color registers plus eight texture-coordinate registers.

Sparse component masks are preserved; the audit does not force `.xz` or `.yz` masks into another register class. It also does not require a contiguous sequence of used VS2 `oT#` indices. A target semantic such as TEXCOORD3 may be compacted to TEXCOORD0, but the report flags the downstream pixel-shader interface change. POSITION0 and optional PSIZE0 occupy exclusive VS3 source output registers; neither can share an `o#` register with another semantic. The remaining ten registers carry generic interpolators, and the spec allows any ten of the twelve source indices, not just o0-o9.

The standalone synthetic vertex-audit test passed in Windows-independent run #219. The Windows x86 build for the same commit was still running at the last status check. No GTA IV shader capture, game execution or GMA 3100 hardware test has occurred.

Reference: [Microsoft D3D9 dcl_usage output register](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dcl-usage-outut-register---vs), [VS2 output registers](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-vs-2-0), and [VS3 output register model](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dx9-graphics-reference-asm-vs-registers-vs-3-0).


### Special output exclusivity and arbitrary VS3 output indices — 2026-11-22

The Microsoft D3D9 output DCL reference explicitly makes position and point size special register classes, not general varying lanes. The audit now rejects any attempt to pack another semantic into the same VS3 source register as POSITION0 or PSIZE0. The remaining ten registers carry generic interpolators, and the spec allows any ten of the twelve register indices, not just o0-o9.

Synthetic tests now verify:
- Ten generic interpolators plus POSITION0 and PSIZE0, with position at o1 and point size at o10 while general semantics use nonconsecutive remaining indices.
- Ten generic interpolators plus POSITION0 when PSIZE0 is omitted.
- Rejection when an eleventh general interpolator would exceed the VS2 ten-slot output budget.
- Rejection of a TEXCOORD declaration sharing the PSIZE0 or POSITION0 source register.

Standalone vertex-audit CI run #224 passed these cases. The Windows x86 job for the same commit was still in environment setup at the last check. No real GTA IV shader or Intel GMA 3100 hardware has been tested.

Reference: [Microsoft D3D9 dcl_usage output register](https://learn.microsoft.com/en-us/windows/win32/direct3dhlsl/dcl-usage-outut-register---vs).

### Read-only D3D9 render-pipeline capture — 2026-11-22

The current implementation milestone is observation, not a reduced renderer. When draw telemetry is enabled, the ASI snapshots up to four current render-target bindings and the active depth-stencil binding alongside every draw call. Descriptors include dimensions, D3D format, surface type, usage, pool and multisampling metadata. The state is refreshed after successful Set calls and initially queried after device creation/reset with D3D9 getter methods. Failed state changes do not replace the cached state; reset clears old snapshot metadata. Getter-returned COM references are released after the descriptor is copied.

The offline log parser now associates each draw with the captured target/depth descriptors, groups use by surface object/resolution/format/shader pair, and retains adapter identity and driver strings. It also parses vertex/pixel caps, `CheckDeviceFormat` and `CheckDepthStencilMatch` results, device creation parameters, and render/depth surface creation/binding events. These observations let a later real capture tell us which formats are accepted and which surfaces are actually bound at each draw.

**Do not infer pass identity from format or dimensions alone.** The report does not claim that a particular surface is a G-buffer, shadow map, reflection, water or post-process target without correlating the shader pair, draw sequence, state and (eventually) captured image. No render target is suppressed or redirected; no render state, shader capability, LOD, population, physics, mission or game-simulation setting is changed by this telemetry work.

All automated coverage uses synthetic logs/fake D3D9 devices. The normal game render path is unchanged, but actual-game correctness and performance remain unverified until a real capture and gameplay test are possible. The current pixel shader fallback is still opt-in/manual-map only; there is still no runtime VS3 replacement path and no complete shader translator.
### Verification of default-surface capture and Windows build — 2026-11-22

Windows x86 workflow run #239 passed on commit `8034e2508b3a9c71d7a9ec91311de4460432d354`. The job passed repository source checks, compiled the six generic SM2 shader examples, built the D3D9 probe and x86 ASI, and passed the fake-D3D9 runtime smoke test. The latter includes typed `GetRenderTarget` and `GetDepthStencilSurface` stubs and verifies the capture helper invokes them after device creation and successful reset. The independent VS3-to-VS2 audit job also passed.

Artifact: `iv-legacy-shader-engine-windows-x86`, 237,403 bytes, SHA-256 `baaf821d66560a20d2aafebe34982aec5e307ede6e4fa4ce338105f34c8ca556`.

This verifies compilation and synthetic integration only. It does not verify GTA IV 1.0.0.0 startup, render correctness, the GMA 3100 driver's D3D9 capabilities, or frame rate.