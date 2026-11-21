@echo off
setlocal EnableExtensions
cd /d "%~dp0\.."

set "FXC="
where fxc.exe >nul 2>nul
if not errorlevel 1 for /f "delims=" %%F in ('where fxc.exe') do if not defined FXC set "FXC=%%F"

rem Windows 8.1 SDK commonly uses Windows Kits\8.1\bin\x86\fxc.exe.
if not defined FXC if defined WindowsSdkDir if exist "%WindowsSdkDir%bin\x86\fxc.exe" set "FXC=%WindowsSdkDir%bin\x86\fxc.exe"

rem Some newer SDKs place tools under a versioned directory.
if not defined FXC if defined WindowsSdkDir if defined WindowsSDKVersion if exist "%WindowsSdkDir%bin\%WindowsSDKVersion%x86\fxc.exe" set "FXC=%WindowsSdkDir%bin\%WindowsSDKVersion%x86\fxc.exe"

rem DirectX SDK June 2010 fallback. ProgramFiles(x86) is absent on 32-bit Windows.
if not defined FXC if defined ProgramFiles(x86) if exist "%ProgramFiles(x86)%\Microsoft DirectX SDK (June 2010)\Utilities\bin\x86\fxc.exe" set "FXC=%ProgramFiles(x86)%\Microsoft DirectX SDK (June 2010)\Utilities\bin\x86\fxc.exe"
if not defined FXC if defined ProgramFiles if exist "%ProgramFiles%\Microsoft DirectX SDK (June 2010)\Utilities\bin\x86\fxc.exe" set "FXC=%ProgramFiles%\Microsoft DirectX SDK (June 2010)\Utilities\bin\x86\fxc.exe"

if not defined FXC (
  echo ERROR: fxc.exe was not found. Install a Windows SDK / DirectX SDK containing FXC or add it to PATH.
  exit /b 2
)

if not exist build\out mkdir build\out
del /q build\out\*.vso build\out\*.pso build\out\*.asm >nul 2>nul

echo Using FXC: "%FXC%"
call :compile shaders\basic_vs20.hlsl VSMain vs_2_0 build\out\basic_vs20.vso build\out\basic_vs20.asm || exit /b 1
call :compile shaders\flat_lod_vs20.hlsl VSMain vs_2_0 build\out\flat_lod_vs20.vso build\out\flat_lod_vs20.asm || exit /b 1
call :compile shaders\basic_ps20.hlsl PSMain ps_2_0 build\out\basic_ps20.pso build\out\basic_ps20.asm || exit /b 1
call :compile shaders\unlit_ps20.hlsl PSMain ps_2_0 build\out\unlit_ps20.pso build\out\unlit_ps20.asm || exit /b 1
call :compile shaders\water_ps20.hlsl PSMain ps_2_0 build\out\water_ps20.pso build\out\water_ps20.asm || exit /b 1
call :compile shaders\flat_lod_ps20.hlsl PSMain ps_2_0 build\out\flat_lod_ps20.pso build\out\flat_lod_ps20.asm || exit /b 1

echo.
echo All six shader sources compiled. This does NOT prove that a target driver accepts or renders them.
exit /b 0

:compile
echo Compiling %~1 as %~3...
"%FXC%" /nologo /O3 /T %~3 /E %~2 /Fo %~4 /Fc %~5 %~1
if errorlevel 1 exit /b 1
if not exist "%~4" (
  echo ERROR: FXC returned success but bytecode was not created: %~4
  exit /b 1
)
for %%A in ("%~4") do if %%~zA LEQ 0 (
  echo ERROR: FXC created an empty bytecode file: %~4
  exit /b 1
)
if not exist "%~5" (
  echo ERROR: FXC assembly listing was not created: %~5
  exit /b 1
)
exit /b 0
