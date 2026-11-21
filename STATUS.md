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

