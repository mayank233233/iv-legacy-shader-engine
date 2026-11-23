# GMA Edition renderer prototype

**Development branch:** `feature/gma-edition-renderer-prototype`  
**Target:** GTA IV PC 1.0.0.0, Win32/D3D9, Pentium Dual-Core E5200, Intel GMA 3100, 3 GB RAM, Windows 8.1 x86.

## Scope and acceptance rule

This branch is building a set of reversible, independently controlled optimisations around the existing GTA IV D3D9 renderer. It is not yet a replacement renderer or a verified playable GMA 3100 compatibility mod.

Every runtime optimisation must default OFF, preserve the original D3D9 call when it cannot safely prove a duplicate, and invalidate any state it can no longer trust. Synthetic tests establish that the hooks and safeguards execute on the tested fake D3D9 host; they do not establish performance on the physical GMA 3100.

## Current controls

The runtime experiments use the `[General]` section of `IVLegacy.ini`:

```ini
[General]
EnableRedundantStateCache=0
EnableBindingCache=0
EnableShaderConstantCache=0
StateCacheReportFrames=120
CaptureDrawTelemetry=0
CaptureDrawMaxCalls=4096
EnableFrameProfiler=0
FrameProfilerWindowFrames=120
StrictGTAIV100=1
```

All three optimisation caches are independently opt-in and default OFF:

- **`EnableRedundantStateCache`** shadows `SetRenderState`, `SetTextureStageState` and `SetSamplerState`. It uses a serialized lock and suppresses only a repeated state/value previously accepted by the original D3D9 call.
- **`EnableBindingCache`** covers `SetTexture`, `SetStreamSource` (buffer, offset and stride), `SetStreamSourceFreq` (divider), `SetIndices`, `SetVertexShader`, `SetPixelShader`, `SetVertexDeclaration` / `SetFVF`, and `SetViewport`. Pointer-based bindings compare the actual object pointer; stream and viewport state include their additional parameters.
- **`EnableShaderConstantCache`** covers VS and PS float, integer and boolean constant setters. Float ranges are shadowed for up to 256 registers per stage; integer and boolean ranges are shadowed for up to 16 registers per stage. Equality is byte-exact over the submitted register range.

The binding and shader-constant caches share a single-device/single-thread guard. They are disabled when state-block APIs are used, when a multithreaded D3D9 device is requested, when strict GTA IV 1.0.0.0 mode is disabled, or when an unexpected device/thread is encountered. A Reset attempt and failed Present invalidate their shadows rather than permanently disabling the caches. The scalar state cache has its own lock/thread checks and state-block fallback. These protections are conservative safeguards, not proof that every external device-state mutation is covered.

`StateCacheReportFrames` controls the reporting interval (1–600 successful-Present frames; default 120). The logs use `D3D9_STATE_CACHE_WINDOW`, `D3D9_BINDING_CACHE_WINDOW` and `D3D9_SHADER_CONSTANT_CACHE_WINDOW`. The corresponding analyzers count forwarded and skipped calls. A high skip rate is not an FPS measurement: the comparisons, thread checks, bookkeeping and cache maintenance can cost more than the avoided D3D9 calls.

Shader bytecode fallback is a separate pre-existing option, `EnableShaderFallbacks`, using explicitly approved hash mappings. It is not a general SM3 translator and is not automatically enabled by the GMA Edition caches.

## Phase 0: capture the actual render path

Enable bounded draw telemetry only for a capture:

```ini
[General]
CaptureDrawTelemetry=1
CaptureDrawMaxCalls=4096
```

Then run the read-only render-path audit:

```sh
python tools/audit_gma_edition_render_path.py IVLegacy.log --width 320 --height 240 --json gma_render_path.json
```

The ASI records, per draw, the current render-target bindings (up to four slots), the depth-stencil surface, active shaders, vertex layout/bindings and viewport. Viewport capture works in two ways:

- A successful `SetViewport` updates the observed viewport snapshot.
- Immediately before each captured draw, the ASI calls the D3D9 `GetViewport` method to refresh the snapshot. This catches viewport changes made indirectly by state-block application, which do not necessarily pass through the `SetViewport` hook.

Each captured `DRAW_CALL` can therefore include `viewport=x:y:width:height:minZBits:maxZBits`. The offline parser and audit report viewport dimensions, whether viewport capture is complete for the captured draws, viewport/RT0 extent differences, and matching or mismatching RT0/depth dimensions. A viewport/RT0 extent difference may be intentional cropping; it is evidence to inspect, not automatically an error.

**Capture overhead warning:** `GetViewport` is queried for every captured draw. Draw telemetry also formats and writes large per-draw records. Do not use a telemetry-heavy capture as the clean FPS baseline. Keep `CaptureDrawTelemetry=0` for normal performance runs.

### What the render-path audit does not establish

- It does not prove that an observed render target is the main scene target. Surface dimensions and formats alone cannot label a target as a G-buffer, shadow map, reflection, water or post-processing surface.
- Matching RT0/depth dimensions are necessary evidence for a simple redirect, but not sufficient. Format compatibility, multisample mode, surface lifetime, actual binding sequence and device support must also be established.
- A viewport that differs from the RT0 extent may be intentional. The audit exposes the difference but does not infer its purpose.
- A Present-time upscale may include UI and post-processing already rendered into the source. The correct insertion point and UI ordering remain unknown.
- `StretchRect` format/filter support must be queried on the target device; any unsupported path must fall back to original presentation.

Therefore `LowResEnabled` in the example INI is a reserved placeholder, not an implemented runtime feature.

## Phase 1: fixed-function evidence

The read-only audit lists a draw as a *candidate* only when both programmable shaders are null, a nonzero FVF is active and no vertex declaration is bound. Candidate status does not approve replay or replacement.

Nulling shaders on an arbitrary live draw is not a fixed-function conversion. The vertex layout must be expressible by the active FVF, and the stream data, textures, transforms, clipping, material, alpha, blend and depth state must all be compatible. A future probe must use an isolated captured scene or synthetic geometry; it must not replace arbitrary GTA IV draws.

## Benchmark interpretation

The optional QPC frame profiler records Present-return intervals and CPU wall time inside Present and the four D3D9 draw methods. It reports frame-time distributions and call counts, but explicitly emits `gpu_time=not_measured`. API wall time can include driver waits; unattributed interval time is not a direct measurement of world simulation.

Use the same executable, save, route, camera, weather, time and game settings. Warm up first and repeat each configuration. Compare median and P95 frame time as well as average FPS, crashes, visual differences, streaming stalls and memory use. Run each cache independently before combining them. Keep telemetry mostly OFF during the actual timing runs.

## Current acceptance status

### Implemented in source; synthetic Windows x86 coverage

- Adapter/device capability, format/depth checks and D3D9 device-creation telemetry.
- Render-target and depth-stencil creation/binding snapshots.
- Per-draw viewport capture, including a draw-time `GetViewport` refresh; parser and GMA render-path audit for viewport coverage and extent differences.
- Read-only fixed-function candidate classification.
- Opt-in scalar D3D9 state cache, binding cache and shader-constant cache, with independent switches and lifecycle fallbacks.
- Benchmark analyzers for scalar-state, binding and shader-constant suppression counters.
- Existing restricted, manually hash-mapped VS2/PS2 fallback hooks and offline shader-pair audit/lowering tools. These remain separate from the new renderer optimisations.

### Not implemented

- Low-resolution scene render-target redirection.
- A correctly placed upscale path that preserves UI sharpness.
- Live fixed-function conversion/replacement of GTA IV draw calls.
- General SM3-to-SM2 translation or a complete SM2 forward renderer.
- New GMA-specific geometry batching, culling, population/AI throttling, allocator replacement or streaming scheduler changes.

### Verification and limits

- Latest integrated Windows x86 workflow: [run #45101202585](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/45101202585), on code commit `9765a43665565e4c48c2c69f79603c62072a33a6`; both `build` and `vertex-audit` jobs passed. The current branch head adds subsequent documentation-only commits.
- The passing workflow validates the tested x86 build, synthetic D3D9 hook/runtime tests, source checks and offline audit self-tests. It does not run GTA IV or the physical GMA 3100.
- A later CI run, [#45145510926](https://github.com/mayank233233/iv-legacy-shader-engine/actions/runs/45145510926), was triggered by the example INI template update (`e3d44902de286f72dc32077fe5f9ae8ecfffa43e`). Its `vertex-audit` job passed; the Windows `build` job was still at legacy DirectX SDK installation at the latest status check. It is not counted as a passing full build.
- No real GTA IV 1.0.0.0 gameplay capture, image-equivalence test, physical driver validation, in-game frame-time benchmark or genuine 30 FPS result has been established.
- The long-term target remains 30 genuinely rendered FPS, not a promise or result.
