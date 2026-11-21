# Prototype 0.3 — status

## Implemented in source

- Preserved the six v0.2 generic HLSL shaders and their \`vs_2_0\` / \`ps_2_0\` targets.
- Fixed FXC path discovery for common Windows 8.1 and versioned Windows SDK layouts, with DirectX SDK June 2010 fallbacks.
- Added non-empty bytecode and assembly-output checks after each FXC invocation.
- Added checked HRESULT handling for texture and readback \`UnlockRect\` calls.
- Added complete adapter PCI identity fields and explicit adapter-identification failure logging.
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
| v0.2 archive SHA-256 and ZIP integrity | PASS |
| Six original shader files retained | PASS — source files copied unchanged |
| Local source sanity tests | PASS |
| FXC compilation | NOT RUN in this environment |
| MSVC x86 compilation | NOT RUN in this environment |
| GitHub Actions Windows x86 build | IN PROGRESS — latest run `44876439909` is installing the June 2010 DirectX SDK; FXC compile and MSVC build steps have not run yet |
| D3D9 runtime shader creation | NOT RUN |
| HAL software-VP rendering on GMA 3100 | NOT RUN |
| HAL hardware-VP rendering on GMA 3100 | NOT RUN |
| GMA 3100 readback / repeatability | NOT RUN |
| GTA IV integration | NOT IMPLEMENTED |
| GTA IV launch / FPS | NOT TESTED |

## Important boundary

Prototype 0.3 is source code plus build automation. It is not yet a verified Windows executable and has not been run on the target GPU. CI success, when obtained, will prove only that the shaders compile and the x86 probe builds in the CI environment. It will not prove GMA 3100 driver acceptance, hardware vertex processing, correct rendering, GTA IV compatibility or performance.
