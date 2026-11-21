@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
if not exist build\bin\D3D9ShaderProbe.exe (
  echo ERROR: Probe executable not found. Run build\build_probe.bat first.
  exit /b 2
)
for %%F in (basic_vs20.vso flat_lod_vs20.vso basic_ps20.pso unlit_ps20.pso water_ps20.pso flat_lod_ps20.pso) do (
  if not exist "build\out\%%F" (
    echo ERROR: Compiled shader missing: build\out\%%F. Run build\compile_shaders.bat first.
    exit /b 2
  )
)
start "IV Legacy Shader Engine D3D9 Probe" /wait build\bin\D3D9ShaderProbe.exe
exit /b %errorlevel%
