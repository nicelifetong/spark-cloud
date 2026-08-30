@echo off
setlocal
set "PYTHONUNBUFFERED=1"
title Spark Cloud - Web Dashboard
cd /d "%~dp0\.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Environment not ready yet.
    echo Please run scripts\1 once first to prepare the environment.
    pause
    exit /b 1
)

if not exist ".env" copy ".env.example" ".env" >nul 2>&1

rem Read custom port from .env (default 8000).
rem NOTE: use _SPK_PORT as temp var, never SPARK_PORT --
rem setting SPARK_PORT would inject it into the process env,
rem making the app think the port is locked by the deployment.
set "_SPK_PORT=8000"
for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
    if /i "%%a"=="SPARK_PORT" set "_SPK_PORT=%%b"
)

echo =======================================================
echo   Spark Cloud - Web Dashboard
echo =======================================================
echo.
echo [*] Starting server at http://127.0.0.1:%_SPK_PORT% ...
echo     The browser will open automatically in a few seconds.
echo.
echo [*] Keep this window open while running. Close = stop.
echo.

rem Open browser after a short delay (server should be ready by then)
start "" /b cmd /c "ping -n 9 127.0.0.1 >nul & start http://127.0.0.1:%_SPK_PORT%"

".venv\Scripts\python.exe" app.py

echo.
echo [*] Server stopped.
echo.
pause
