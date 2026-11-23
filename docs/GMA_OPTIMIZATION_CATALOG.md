# GTA IV performance optimisation catalogue — GMA Edition

Target: GTA IV 1.0.0.0, 32-bit D3D9, Pentium E5200, GMA 3100, 3 GB RAM.
This is a research and implementation backlog, not a claim that 30 changes
have already been implemented. Every runtime change must be independently
switchable, default OFF, reversible to the original path, and benchmarked.

## What community projects demonstrate

- ZolikaPatch documents a reimplemented allocator, faster loading, removal of
  nonfunctional debug code on selected builds, and fixes to streaming/limit
  failures. Its open reconstruction is GPL-3.0; this repository currently has
  no declared project licence. Do not copy its implementation until licensing
  and compatibility are deliberately resolved. Reimplement independently from
  documented behavior and original-game evidence.
- FusionFix is also GPL-3.0. It offers many visual and correctness features,
  but several options add GPU work (AO, volumetric fog, sun shafts, soft/contact
  shadows, anti-aliasing). Those are not performance optimisations for GMA 3100.
- DXVK can reduce D3D9 driver overhead on supported Vulkan GPUs. GMA 3100 does
  not provide the required Vulkan support, so DXVK is not a viable target path.
- The existing IVLegacy redundant D3D9 state cache suppresses duplicate
  render-state, texture-stage-state and sampler-state submissions when enabled.
  It is opt-in and must be measured; its lock/bookkeeping cost may exceed the
  savings on a two-core E5200.
- A separate opt-in D3D9 binding cache has now been implemented for texture,
  vertex-stream (buffer + offset + stride), stream-frequency, index-buffer,
  vertex-shader, pixel-shader, vertex-declaration/FVF, and viewport bindings.
  Viewport state is invalidated after a successful RT0 change because D3D9
  resets the viewport to the target extent. The cache is disabled on state-block
  APIs, multithreaded device creation, non-strict executable mode, or device/thread
  conflicts. Reset attempts and failed Presents invalidate its shadows but do
  not permanently turn the feature off.
- An independent opt-in shader-constant range cache now covers VS/PS float,
  integer and boolean constants. It uses bitwise equality for exact register
  ranges, forwards changed or untracked ranges, and invalidates on Reset and
  failed Present. It is disabled on state-block APIs, multithreaded device
  creation, non-strict executable mode, or device/thread conflicts. Synthetic
  tests cover all six register groups; physical gameplay performance is unknown.

## Render-path observability now available

The ASI records render-target slots, the active depth-stencil surface and the
active viewport for each captured draw when `CaptureDrawTelemetry=1`. It
updates the viewport snapshot from successful `SetViewport` calls and queries
`GetViewport` immediately before each captured draw, so state-block viewport
restores are not missed merely because no explicit SetViewport call occurred.
The viewport record includes origin, dimensions and the bit patterns of MinZ
and MaxZ.

Run the read-only report with:

```sh
python tools/audit_gma_edition_render_path.py IVLegacy.log --width 320 --height 240 --json gma_render_path.json
```

The report exposes viewport-capture completeness, viewport dimensions,
viewport/RT0 extent differences, RT0/depth dimension pairs and conservative
fixed-function candidates. A viewport/RT0 extent difference may be deliberate
cropping; it is not automatically a failure. The audit cannot identify the
main scene target or the correct UI/post-processing insertion point from
surface metadata alone.

**Capture cost:** draw telemetry performs a GetViewport query for each captured
draw and writes detailed per-draw records. Keep it off during clean timing
runs; use bounded captures for render-path discovery.

## 30 candidate optimisations

Legend: **Implemented** = code already exists in this branch; **Measure** =
instrument first; **Prototype** = controlled opt-in experiment; **Reject** =
not safe or not justified yet.

### D3D9 submission / CPU overhead

1. **Redundant render-state suppression** — Implemented, opt-in. Existing cache.
2. **Redundant texture-stage-state suppression** — Implemented, opt-in.
3. **Redundant sampler-state suppression** — Implemented, opt-in.
4. **State-cache break-even measurement** — Implemented analyzer in
   `tools/analyze_state_cache_benchmark.py`; counts skipped API calls but does
   not claim FPS improvement.
5. **Texture and viewport binding deduplication** — Implemented as an
   opt-in experiment. Texture bindings use pointer identity; viewports compare
   the complete D3DVIEWPORT9 structure. A successful RT0 change invalidates the
   viewport shadow because D3D9 resets the viewport to the new target extent.
   State-block APIs and unsupported threading/device conditions disable the
   cache; Reset and failed Present invalidate its shadows.
6. **Vertex/index buffer binding deduplication** — Implemented as an opt-in
   experiment for SetStreamSource (buffer + offset + stride), SetStreamSourceFreq
   (exact divider), and SetIndices. State-block and device lifecycle safeguards
   match the texture cache.
7. **Shader object binding deduplication** — Implemented as an opt-in
   experiment for SetVertexShader and SetPixelShader. It tracks the actual
   shader object passed to the device, including hash-mapped fallback objects.
   State-block and device lifecycle safeguards match the other bindings.
8. **Shader constant upload deduplication** — Implemented as an independent
   opt-in cache for VS/PS float (256-register shadow), integer and boolean
   (16-register shadows). It compares the full updated range bitwise, updates
   the shadow only after successful device calls, invalidates on Reset and
   failed Present, and disables on state-block API use.
9. **Draw-call batching** — Prototype only for proven compatible static groups;
   preserve ordering, blend/depth state, material, transform and visibility.
10. **D3D9 state transition sorting** — Reject as a global reorder; GTA IV's
    transparent and multipass ordering is semantically significant.

### Geometry, visibility and world submission

11. **Frustum culling audit** — Measure objects submitted but outside view.
12. **Occlusion culling audit** — Measure before implementing; avoid adding CPU
    occlusion work that costs more than the hidden draw calls.
13. **Static geometry cache** — Prototype only on verified immutable,
    non-streaming groups with bounded lifetime and exact state compatibility.
14. **Spatially bounded batching** — Prototype small cells; never merge the
    entire city into one huge buffer.
15. **LOD distance reduction** — Prefer supported game settings/data first;
    avoid patching global distance constants without map-specific tests.
16. **Pedestrian/vehicle population reduction** — Measure simulation cost;
    preserve mission scripts and traffic safety constraints.
17. **Distant object update throttling** — Prototype only after identifying
    independent update functions and proving no gameplay/timing dependency.
18. **Animation update throttling** — Measure; player, nearby peds and scripted
    actors must remain full-rate.
19. **Shadow caster culling** — High potential but needs light/frustum evidence;
    do not disable shadow draws based only on draw-call order.
20. **Reflection scene simplification** — Measure reflection passes and
    candidate object sets; never assume all reflections are optional.

### GPU pixel / shader workload

21. **Internal resolution reduction** — Prototype 320x240/400x300 after
    identifying the actual scene RT, matching depth, viewport and UI boundary.
22. **Post-process pass elimination** — Identify each pass first; disable one
    pass at a time, with original path fallback.
23. **Shadow-map resolution reduction** — Prototype only after identifying
    exact shadow resources and checking format/MSAA support.
24. **Shadow filtering simplification** — Compare shader instruction and
    bandwidth cost; retain correct depth bias and cascade behavior.
25. **Reflection resolution/update reduction** — Prototype after tracing
    reflection target lifecycle and update frequency.
26. **Texture filtering reduction** — Use sampler-state measurements; test
    texture aliasing and driver cost, not just visual quality.
27. **Texture mip bias / lower mip selection** — Measure VRAM and bandwidth;
    avoid forcing base mip or disabling mipmaps globally.
28. **Remove AO, volumetric fog, sun shafts, SMAA/FXAA and DOF** — For GMA,
    avoid adding these effects; only intercept if the target build actually
    executes the pass and fallback is safe.

### Memory, streaming and I/O

29. **Allocator/streaming analysis** — Profile allocations, stalls, working set,
    page faults and disk reads. Study ZolikaPatch's allocator behavior, but
    don't transplant allocator code or raise memory limits on a 32-bit process.
30. **Resource lifetime and cache policy** — Track repeated create/destroy,
    texture residency, buffer lifetime and streaming churn; prototype bounded
    reuse only after proving ownership and device-reset correctness.

## Priority for this machine

1. Get a clean baseline with telemetry mostly OFF; instrumentation itself adds
   CPU and disk work.
2. Run scalar state, binding and shader-constant caches independently OFF and
   ON on the same route. Compare suppression counters and frame-time
   distributions. Binding and constant cache windows are emitted separately;
   skipped-call counts alone do not prove a gain. Keep draw telemetry off for
   timed runs because per-draw GetViewport queries and log writes add work.
3. Capture a full route and identify CPU draw-call overhead, scene target,
   post-process passes, shadows and texture churn.
4. Only then choose between low-resolution rendering (GPU-bound evidence),
   draw/state reduction (CPU-bound evidence), or streaming/memory work
   (stutter / paging evidence).
5. Keep a separate benchmark for each feature; never infer a bottleneck from
   one metric such as Present duration.

## Benchmark protocol

- Same game executable, save, route, weather/time, camera and graphics settings.
- Warm-up before capture; at least three repeat runs per configuration.
- Compare median and p95 frame time, not only average FPS.
- Capture a no-instrumentation baseline and a telemetry run; telemetry can
  change performance.
- Separate CPU API time from GPU execution time. The current profiler reports
  `gpu_time=not_measured`.
- Summarize binding-cache skipped calls with
  `tools/analyze_binding_cache_benchmark.py IVLegacy.log` and constant-cache
  skipped calls with `tools/analyze_shader_constant_cache.py IVLegacy.log`.
  These counts are not FPS or frame-time measurements.
- Record crashes, visual differences, missing assets, streaming stalls and
  memory use. Any regression disables that feature by default.
