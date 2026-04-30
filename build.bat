@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  OVMS Manager - Build Script
echo ============================================================
echo.

:: Locate Python and PyInstaller using standard system discovery.
:: Prefer the python on PATH (most likely to have project deps installed).
set PYTHON=
set PYINSTALLER=

:: 1. Try python3 / python on PATH (preferred — has project packages installed)
for %%P in (python3 python) do (
    if not defined PYTHON (
        where %%P >nul 2>&1 && set PYTHON=%%P
    )
)
if defined PYTHON goto :found_python

:: 2. Fall back to py launcher
where py >nul 2>&1
if %errorlevel% == 0 (
    set PYTHON=py -3
    echo [Python] Using Windows py launcher
    goto :found_python
)

if defined PYTHON goto :found_python

echo ERROR: Python 3 not found. Install from python.org or via 'winget install Python.Python.3.12'
exit /b 1

:found_python
:: Locate pyinstaller via pip if not already on PATH
where pyinstaller >nul 2>&1
if %errorlevel% == 0 (
    set PYINSTALLER=pyinstaller
) else (
    for /f "delims=" %%P in ('%PYTHON% -c "import sysconfig; print(sysconfig.get_path(\"scripts\"))" 2^>nul') do (
        if exist "%%P\pyinstaller.exe" set PYINSTALLER=%%P\pyinstaller.exe
    )
)
if not defined PYINSTALLER (
    echo [PyInstaller] Not found. Installing...
    %PYTHON% -m pip install pyinstaller --quiet
    set PYINSTALLER=%PYTHON% -m PyInstaller
)

set ISCC="C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
set PROJECT_DIR=%~dp0

:: Step 1 - Clean previous build
echo [1/4] Cleaning previous build...
if exist dist rmdir /s /q dist
if exist build rmdir /s /q build
echo     Done.

:: Step 2 - Regenerate icon
echo [2/4] Generating app icon...
%PYTHON% -c "import sys; sys.path.insert(0, '.'); from app.icon import build_icon; build_icon(force=True); print('    Icon OK')"
if errorlevel 1 echo     WARNING: Icon generation failed, using existing icon.

:: Step 3 - PyInstaller
echo [3/4] Building executable with PyInstaller...
%PYINSTALLER% ovms_manager.spec --noconfirm --clean
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)
echo     Executable built: dist\OVMS Manager\

:: Step 4 - Inno Setup (optional)
echo [4/4] Creating installer with Inno Setup...
if exist %ISCC% (
    mkdir dist\installer 2>nul
    %ISCC% installer.iss
    if errorlevel 1 (
        echo     WARNING: Inno Setup failed. Exe-only build is still available.
    ) else (
        echo     Installer: dist\installer\OVMS_Manager_Setup_1.0.0.exe
    )
) else (
    echo     Inno Setup not found at %ISCC%
    echo     Download from https://jrsoftware.org/isinfo.php
    echo     Skipping installer creation.
)

echo.
echo ============================================================
echo  Build complete!
echo  Executable : dist\OVMS Manager\OVMS Manager.exe
if exist "dist\installer\OVMS_Manager_Setup_1.0.0.exe" (
    echo  Installer  : dist\installer\OVMS_Manager_Setup_1.0.0.exe
)
echo ============================================================
