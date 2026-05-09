@echo off
title JARVIS Hand Control System
color 0B
echo.
echo  ============================================
echo   J.A.R.V.I.S  Hand Gesture Control System
echo  ============================================
echo.

if exist venv\Scripts\activate.bat (
    echo  [INFO] Activating virtual environment...
    call venv\Scripts\activate.bat
) else (
    echo  [WARN] No venv found - using system Python
)

echo  [INFO] Starting JARVIS...
echo.

python main.py %*

echo.
echo  [INFO] JARVIS has shut down.
pause
