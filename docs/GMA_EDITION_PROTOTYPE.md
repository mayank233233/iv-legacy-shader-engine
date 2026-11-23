# GMA Edition renderer prototype

## Scope and safety rule

Branch: `feature/gma-edition-renderer-prototype`

Every future runtime experiment must be independently switchable, default OFF,
revert to the original D3D9 call on any unsupported condition, and include a
repeatable benchmark. This branch does not claim GTA IV compatibility or a
30 FPS result.

## Phase 0: capture the actual render path

The existing ASI already logs render-target creation/binding, depth-stencil
creation/binding, draw calls, shader objects, FVF and vertex declarations.
Run the game with telemetry and analyze the resulting log:

```sh
python tools/audit_gma_edition_render_path.py IVLegacy.log --width 320 --height 240 --json gma_render_path.json
```

The report checks whether the observed RT0/depth dimensions match and lists
only conservative fixed-function *candidates*: draws with both programmable
shader pointers null, a nonzero FVF, and no vertex declaration. Candidate
status is not approval to replay or modify a draw.

### Missing evidence before low-resolution redirection

- The ASI now observes `SetViewport` (IDirect3DDevice9 slot 47) when draw
  telemetry is enabled. This records viewport rectangles but does not modify
  them. The synthetic x86 smoke test exercises the slot and verifies forwarding.
- A full frame trace must correlate each viewport change with the active RT0,
  depth surface and draw sequence before any viewport or target redirection.
- A surface created at the backbuffer dimensions is not necessarily the main
  scene target. Establish its identity from a complete frame trace.
- RT0 and depth must be paired by actual successful bindings, format,
  multisample type and lifetime; dimensions alone are insufficient.
- The current `Present` hook forwards the game's frame. A fullscreen upscale
  inserted there would normally include UI already rendered into the source.
  UI ordering and post-processing must be traced before choosing the upscale
  insertion point.
- `StretchRect` filter/format support must be checked on the target device.
  Failure must preserve the original presentation path.

Therefore `LowResEnabled` is a reserved configuration switch, not an
implemented runtime feature in this phase.

## Phase 1: fixed-function evidence

A draw is only a candidate when the capture proves both shaders are null and
an FVF (not a programmable vertex declaration) is active. The report does not
replay the draw. Nulling shaders on a declaration-based GTA IV draw is not a
valid fixed-function conversion: the declaration must be represented by a
compatible FVF and the vertex stream must satisfy that FVF. Textures, blending,
depth, transforms, clipping and material state also affect output.

A future replay harness must use a captured, isolated test scene or synthetic
buffers. It must not replace arbitrary live game draws.

## Benchmark interpretation

Use the same save, camera route, settings and capture duration. Compare frame
time distributions and draw/API CPU time. The existing profiler's Present
duration is CPU-side time spent in the call, not GPU time. A low-resolution
test that does not improve frame time does not, by itself, prove the machine is
CPU-bound; driver synchronization, fill rate, memory bandwidth and other
bottlenecks remain possible.

## Current acceptance status

- Original renderer unchanged: yes; this phase is read-only.
- Low-resolution render target redirection: not implemented.
- UI-sharp upscale: not implemented or claimed.
- Fixed-function live draw replacement: not implemented.
- Fixed-function candidate audit: implemented, diagnostic only.
- SetViewport telemetry: implemented. An opt-in viewport-state cache is now
  included in `EnableBindingCache=0`; it compares the complete D3DVIEWPORT9
  structure and invalidates after successful RT0 changes, Reset and state-block
  API use. Synthetic test coverage is included; hardware/game validation is
  pending.
- D3D9 binding cache: implemented as an independent `EnableBindingCache=0`
  experiment for textures, vertex streams (buffer + offset + stride),
  stream-frequency divider values, index buffers, vertex/pixel shaders,
  vertex-declaration/FVF and viewport state. Viewport shadow is invalidated
  after RT0 changes. It disables
  on state-block APIs, D3DCREATE_MULTITHREADED, non-strict executable mode,
  device/thread changes, Reset and failed Present.
- Shader constant cache: implemented separately as
  `EnableShaderConstantCache=0` for VS/PS float, integer and boolean register
  ranges. It compares exact register bytes, updates shadows only after
  successful setters, and shares the same version/thread/device/state-block
  protections. It invalidates its shadow on Reset and failed Present.
  Synthetic tests cover duplicate/changed values and lifecycle invalidation.
  Neither cache has a physical GTA IV/GMA performance result.
- Windows x86 CI: validates Python audit and existing ASI build; not a game/GMA
  hardware acceptance test.
