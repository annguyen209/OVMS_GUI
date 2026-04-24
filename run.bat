@echo off
echo Starting OVMS GUI Manager...
"C:\Users\annguyen209\openvino-env\Scripts\python.exe" "%~dp0main.py"
if errorlevel 1 (
    echo.
    echo Application exited with an error. Press any key to close.
    pause >nul
)
