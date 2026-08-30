@echo off
setlocal
cd /d "%~dp0\.."

rem ======================================================
rem  Spark Cloud - Headless seal and push (Task Scheduler)
rem  No prompts, no pause. Safe to run unattended.
rem  Requires: .seal_key file + repo already set up (run 6 once by hand).
rem ======================================================

if not exist ".venv\Scripts\python.exe" exit /b 1
if not exist ".seal_key" exit /b 1
if not exist ".git" exit /b 1

set "DATA_KEY="
set /p DATA_KEY=<.seal_key
if not defined DATA_KEY exit /b 1

rem ---- locate git (PATH / Program Files / GitHub Desktop, no installs) ----
set "GIT="
where git >nul 2>nul && set "GIT=git"
if not defined GIT if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT (
    for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if not defined GIT if exist "%%D\resources\app\git\cmd\git.exe" set "GIT=%%D\resources\app\git\cmd\git.exe"
    )
)
if not defined GIT exit /b 1

rem ---- seal (log to auto-seal.log) ----
echo [%date% %time%] auto seal start >> auto-seal.log
".venv\Scripts\python.exe" scripts\gh_run.py seal >> auto-seal.log 2>&1
if errorlevel 1 (
    echo [%date% %time%] SEAL FAILED >> auto-seal.log
    exit /b 1
)
if not exist "vault\data.enc" exit /b 1

rem ---- commit only if something actually changed ----
"%GIT%" add -A
"%GIT%" commit -q -m "chore: auto seal update" 2>nul
set "AHEAD="
for /f %%B in ('"%GIT%" rev-list origin/main..main --count 2^>nul') do set "AHEAD=%%B"
if "%AHEAD%"=="0" exit /b 0

rem ---- push with retry + auto rebase ----
set /a TRIES=0
:retry
"%GIT%" push -q 2>nul
if not errorlevel 1 (
    echo [%date% %time%] pushed OK >> auto-seal.log
    exit /b 0
)
"%GIT%" add -A
"%GIT%" commit -q -m "chore: auto seal update" 2>nul
"%GIT%" pull --rebase -q origin main 2>nul
call :fixrebase
"%GIT%" push -q 2>nul
if not errorlevel 1 (
    echo [%date% %time%] pushed OK after retry >> auto-seal.log
    exit /b 0
)
set /a TRIES+=1
if "%TRIES%"=="3" (
    echo [%date% %time%] PUSH FAILED after retries >> auto-seal.log
    exit /b 1
)
timeout /t 10 /nobreak >nul
goto :retry

:fixrebase
if not exist .git\rebase-merge exit /b 0
"%GIT%" checkout --theirs vault\data.enc 2>nul
"%GIT%" add vault\data.enc
"%GIT%" -c core.editor=true rebase --continue
exit /b 0
