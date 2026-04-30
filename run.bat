@echo off
echo Starting OVMS GUI Manager...

:: Try common Python locations in order
set PYTHON=
for %%P in (
    "%LOCALAPPDATA%\Programs\OVMS Manager\_internal\python.exe"
    "%USERPROFILE%\openvino-env\Scripts\python.exe"
    "python.exe"
) do (
    if not defined PYTHON (
        %%P --version >nul 2>&1 && set PYTHON=%%P
    )
)

if not defined PYTHON (
    echo ERROR: Python not found. Please install Python or set up openvino-env.
    pause
    exit /b 1
)

%PYTHON% "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo Application exited with an error. Press any key to close.
    pause >nul
)
