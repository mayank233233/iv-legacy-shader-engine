@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."
where cl.exe >nul 2>nul
if errorlevel 1 (
  echo ERROR: cl.exe not found. Run this from a Visual Studio x86 Native Tools Command Prompt.
  exit /b 2
)
if not exist build\bin mkdir build\bin
cl.exe /nologo /LD /EHsc /W4 /O2 /DWIN32 /D_WINDOWS /Fe:build\bin\IVLegacyASI.asi src\IVLegacyASI.cpp /link version.lib
if errorlevel 1 exit /b 1
if not exist build\bin\IVLegacyASI.asi (
  echo ERROR: compiler returned success but IVLegacyASI.asi was not created.
  exit /b 1
)
echo Build succeeded: build\bin\IVLegacyASI.asi
