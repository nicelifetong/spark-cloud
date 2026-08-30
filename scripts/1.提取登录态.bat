@echo off
setlocal
set "PYTHONUNBUFFERED=1"
title Spark Cloud - Extract Login State
cd /d "%~dp0\.."

rem ---------- locate python ----------
set PY=
rem "py" launcher only exists if real Python (python.org) was installed - trust it.
where py >nul 2>&1 && set PY=py -3
if not defined PY (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        if not defined PY (
            echo %%i | find /i "WindowsApps" >nul || set "PY=%%i"
        )
    )
)
if not defined PY (
    echo [ERROR] No usable Python found. Two common causes:
    echo.
    echo 1. Only the Microsoft Store "python" alias exists. It opens the
    echo    Store page - it is NOT real Python. Fix: Start menu, search
    echo    "Manage app execution aliases", turn OFF python.exe and
    echo    python3.exe.
    echo 2. Python is not installed. Fix: install Python 3.10+ from
    echo    https://www.python.org/downloads/ and TICK
    echo    "Add python.exe to PATH" during setup.
    echo.
    echo Then delete the .venv folder here if it exists, and run me again.
    pause
    exit /b 1
)

echo =======================================================
echo   Spark Cloud - Extract Douyin Login State
echo =======================================================

echo.
echo [1/3] Preparing virtual environment...
if not exist ".venv\Scripts\python.exe" (
    %PY% -m venv .venv
    if errorlevel 1 ( echo [ERROR] Failed to create venv. & pause & exit /b 1 )
)

echo [2/3] Installing dependencies (first run may take a while)...
".venv\Scripts\python.exe" -m pip install --upgrade pip -q
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [INFO] Retry with China mirror...
    ".venv\Scripts\python.exe" -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
)

echo [3/3] Browser: will use system Edge automatically (no download needed).
echo        Optional: run ".venv\Scripts\python.exe -m playwright install chromium" later.

echo.
echo A browser window will open now. Please log in to Douyin
echo with your phone (scan QR or SMS), then wait a few seconds.
echo.
".venv\Scripts\python.exe" extract.py

echo.
pause
