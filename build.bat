@echo off
setlocal EnableDelayedExpansion

echo ============================================================
echo  OVMS Manager - Build Script
echo ============================================================
echo.

set PYTHON=C:\Users\annguyen209\openvino-env\Scripts\python.exe
set PYINSTALLER=C:\Users\annguyen209\openvino-env\Scripts\pyinstaller.exe
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
if errorlevel 1 (
    echo     WARNING: Icon generation failed, using existing icon.
)

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
    echo     Skipping installer creation - exe folder is ready in dist\
)

echo.
echo ============================================================
echo  Build complete!
echo  Executable : dist\OVMS Manager\OVMS Manager.exe
if exist "dist\installer\OVMS_Manager_Setup_1.0.0.exe" (
    echo  Installer  : dist\installer\OVMS_Manager_Setup_1.0.0.exe
)
echo ============================================================
