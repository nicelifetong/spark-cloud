@echo off
setlocal
set "PYTHONUNBUFFERED=1"
title Spark Cloud - Run Now
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Environment not ready yet.
    echo Please run scripts\1 once first to prepare the environment.
    pause
    exit /b 1
)

echo =======================================================
echo   Spark Cloud - Run Now
echo =======================================================
echo.
echo Choose mode:
echo   [1] Real send (default)
echo   [2] Dry run (do NOT really send)
echo   [3] Sync contacts only
echo.
set /p CHOICE=Enter 1/2/3, blank = 1: 

if "%CHOICE%"=="2" (
    echo.
    echo [*] Dry run...
    ".venv\Scripts\python.exe" cli.py run --dry
) else if "%CHOICE%"=="3" (
    echo.
    echo [*] Sync contacts...
    ".venv\Scripts\python.exe" cli.py sync
) else (
    echo.
    echo [*] Real send...
    ".venv\Scripts\python.exe" cli.py run
)

echo.
pause
