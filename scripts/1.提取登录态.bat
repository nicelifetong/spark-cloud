@echo off
setlocal
set "PYTHONUNBUFFERED=1"
rem If a Chromium download is ever needed, pull it from the China mirror.
set "PLAYWRIGHT_DOWNLOAD_HOST=https://cdn.npmmirror.com/binaries/playwright"
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
rem ---------- auto-install python if missing ----------
if defined PY goto :pypath

echo [INFO] Python not found. Installing it automatically now
echo        (silent install, may take a few minutes)...

where winget >nul 2>&1 && goto :winget_install

echo [INFO] winget not available. Downloading Python 3.12 from python.org...
curl.exe -L -o "%TEMP%\python-installer.exe" https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
if errorlevel 1 (
    echo [ERROR] Download failed. Check internet, or install manually:
    echo         https://www.python.org/downloads/  tick "Add python.exe to PATH"
    pause
    exit /b 1
)
goto :run_installer

:winget_install
echo [INFO] Installing via winget...
winget install -e --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
if errorlevel 1 (
    echo [WARN] winget failed. Falling back to direct download...
    curl.exe -L -o "%TEMP%\python-installer.exe" https://www.python.org/ftp/python/3.12.8/python-3.12.8-amd64.exe
    if errorlevel 1 (
        echo [ERROR] Download failed. Check internet, or install manually:
        echo         https://www.python.org/downloads/  tick "Add python.exe to PATH"
        pause
        exit /b 1
    )
)

:run_installer
echo [INFO] Running silent installer (per-user, Add to PATH)...
"%TEMP%\python-installer.exe" /quiet InstallAllUsers=0 PrependPath=1 Include_test=0
if errorlevel 1 (
    echo [ERROR] Installer failed. Install manually:
    echo         https://www.python.org/downloads/  tick "Add python.exe to PATH"
    pause
    exit /b 1
)

rem PATH changes only apply to NEW windows - probe known install locations.
set "PYP=%LOCALAPPDATA%\Programs\Python\Python312\python.exe"
if exist "%PYP%" goto :found
set "PYP=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if exist "%PYP%" goto :found
set "PYP=%ProgramFiles%\Python312\python.exe"
if exist "%PYP%" goto :found
where py >nul 2>&1 && (set "PY=py -3" & goto :pypath)
echo [INFO] Python installed, but this window can't see it yet.
echo        Close this window, open a NEW one, and run me again.
pause
exit /b 1

:found
set "PY=%PYP%"
for %%d in ("%PYP%") do set "PATH=%%~dpd;%%~dpdScripts;%PATH%"
goto :pypath

:pypath
rem normalize "py -3" launcher to a full python.exe path (spaces-proof)
if "%PY%"=="py -3" (
    for /f "delims=" %%i in ('py -3 -c "import sys;print(sys.executable)"') do set "PY=%%i"
)
echo Using python: %PY%

echo =======================================================
echo   Spark Cloud - Extract Douyin Login State
echo =======================================================

echo.
echo [1/3] Preparing virtual environment...
if not exist ".venv\Scripts\python.exe" (
    "%PY%" -m venv .venv
    if errorlevel 1 ( echo [ERROR] Failed to create venv. & pause & exit /b 1 )
)

echo [2/3] Installing dependencies (first run may take a while)...
rem China mirror by default - much faster than official PyPI there.
".venv\Scripts\python.exe" -m pip install --upgrade pip -q -i https://pypi.tuna.tsinghua.edu.cn/simple
".venv\Scripts\python.exe" -m pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple
if errorlevel 1 (
    echo [INFO] Mirror failed, retrying with official PyPI...
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt
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
