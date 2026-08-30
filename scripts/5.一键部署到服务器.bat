@echo off
setlocal
set "PYTHONUNBUFFERED=1"
title Spark Cloud - Deploy to Server
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Environment not ready yet.
    echo Please run scripts\1 once first to prepare the environment.
    pause
    exit /b 1
)

".venv\Scripts\python.exe" scripts\deploy_remote.py

pause
