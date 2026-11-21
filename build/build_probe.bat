@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
where cl.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: cl.exe not found. Run this from a Visual Studio x86 Native Tools Command Prompt.
  exit /b 2
)
if not exist build\bin mkdir build\bin
cl.exe /nologo /EHsc /W4 /O2 /Fe:build\bin\D3D9ShaderProbe.exe src\D3D9ShaderProbe.cpp /link d3d9.lib user32.lib
if errorlevel 1 exit /b 1
if not exist build\bin\D3D9ShaderProbe.exe (
  echo ERROR: compiler returned success but executable was not created.
  exit /b 1
)
echo Build succeeded: build\bin\D3D9ShaderProbe.exe
