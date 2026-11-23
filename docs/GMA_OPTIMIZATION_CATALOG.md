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
  vertex-stream (buffer + offset + stride), index-buffer, vertex-shader,
  pixel-shader, and vertex-declaration/FVF bindings. It only runs on a
  single-threaded, single-device path, and disables itself on state-block APIs,
  multithreaded device creation, non-strict executable mode, thread/device
  changes, Reset and failed Present. Synthetic smoke coverage exists; real
  GTA IV/GMA performance and behavior are not yet validated.

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
5. **Texture binding deduplication** — Implemented as an opt-in experiment;
   skips identical bound texture pointers. Disabled around state-block APIs,
   Reset/lost-device boundaries and unsupported threading/device conditions.
6. **Vertex/index buffer binding deduplication** — Implemented as an opt-in
   experiment for SetStreamSource (buffer + offset + stride) and SetIndices.
   Stream-frequency state is still forwarded normally; state-block and device
   lifecycle safeguards match the texture cache.
7. **Shader object binding deduplication** — Implemented as an opt-in
   experiment for SetVertexShader and SetPixelShader. It tracks the actual
   shader object passed to the device, including hash-mapped fallback objects.
   State-block and device lifecycle safeguards match the other bindings.
8. **Constant upload range deduplication** — Measure exact byte-identical
   constant ranges; NaNs, partial writes and shader changes complicate equality.
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
2. Run the scalar state cache and binding cache independently OFF and ON on the
   same route. Compare their suppression counters and frame-time distributions.
   The new binding-cache counters are emitted as
   `D3D9_BINDING_CACHE_WINDOW`; skipped-call counts alone do not prove a gain.
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
- Record crashes, visual differences, missing assets, streaming stalls and
  memory use. Any regression disables that feature by default.
