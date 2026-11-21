# GMA 3100 GTA IV Compatibility and Optimization Research

**Target game:** Grand Theft Auto IV PC 1.0.0.0  
**Target machine:** ASUS P5KPL-AM IN; Intel GMA 3100 (PCI VEN_8086 / DEV_29C2); Pentium Dual-Core E5200 2.50 GHz; 3 GB DDR2; Windows 8.1 32-bit; 1440×900  
**Objective:** an installable, game-loaded compatibility/optimization mod, with a long-term 30 FPS target.  
**Current baseline:** IV Legacy Shader Engine Prototype 0.3. It is a standalone D3D9 test harness, not the game mod.

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
| Research baseline | This document, version/capability matrix, shader-family inventory and known-unknowns list | Architecture and failure modes documented |
| 0.4 — game-loaded x86 foundation | ASI/plugin skeleton for 1.0.0.0, version detection, log/config, safe startup/shutdown | Plugin loads in game and exits safely; no fake SM3 report |
| 0.5 — D3D9 instrumentation | In-game caps, format, shader-creation, render-target, state and draw telemetry | Real game's requested feature set is known |
| 0.6 — first low-end shader family | A small set of mapped SM2 fallbacks (e.g. unlit/default materials) | Known surfaces render with documented visual compromises |
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

Do not keep expanding the generic six-shader demo as if it were GTA IV. Keep v0.3 as a verified SM2 tool, then begin a separate game-loaded x86 plugin branch inside this repository. First instrument the real D3D9 device without lying about capabilities; inventory shader creations and render-target use. In parallel, map the decompiled GTA shader metadata to exact runtime variants. Only then implement the first selected SM2 fallbacks.

This is the shortest honest path toward a real mod. The difficult part is the compatibility renderer; performance settings alone cannot bypass the missing Shader Model 3.0 requirement.
