@echo off
setlocal
set "PYTHONUNBUFFERED=1"
title Spark Cloud - Extract Login State
cd /d "%~dp0\.."

rem ---------- locate python ----------
set PY=
where python >nul 2>&1 && set PY=python
if not defined PY where py >nul 2>&1 && set PY=py -3
if not defined PY (
    echo [ERROR] Python not found.
    echo Please install Python 3.10+ from https://www.python.org/downloads/
    echo and tick "Add Python to PATH" during installation.
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
