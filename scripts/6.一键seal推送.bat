@echo off
setlocal
title Spark Cloud - Seal and Push (Route D)
cd /d "%~dp0\.."

echo =======================================================
echo   Spark Cloud - Seal vault and push to GitHub
echo   (Route D: update data on GitHub Actions)
echo =======================================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] Environment not ready yet.
    echo Please run scripts\1 once first to prepare the environment.
    pause
    exit /b 1
)

rem ---- DATA_KEY: from .seal_key file (first line) or ask ----
set "DATA_KEY="
if exist ".seal_key" set /p DATA_KEY=<.seal_key
if not defined DATA_KEY (
    echo Tip: save your key into file ".seal_key" to skip this prompt next time.
    set /p DATA_KEY=Enter DATA_KEY passphrase: 
)
if not defined DATA_KEY (
    echo [ERROR] DATA_KEY is empty.
    pause
    exit /b 1
)

rem ---- Step 1: seal ----
echo.
echo [1/3] Sealing data -^> vault\data.enc ...
".venv\Scripts\python.exe" scripts\gh_run.py seal
if errorlevel 1 (
    echo [ERROR] Seal failed. Is the passphrase correct?
    pause
    exit /b 1
)
if not exist "vault\data.enc" (
    echo [ERROR] vault\data.enc was not created.
    pause
    exit /b 1
)
echo [OK] vault\data.enc is ready.

rem ---- Step 2: locate git (PATH / Program Files / GitHub Desktop / winget) ----
echo.
echo [2/3] Looking for git ...
set "GIT="
where git >nul 2>nul && set "GIT=git"
if not defined GIT if exist "%ProgramFiles%\Git\cmd\git.exe" set "GIT=%ProgramFiles%\Git\cmd\git.exe"
if not defined GIT (
    for /d %%D in ("%LOCALAPPDATA%\GitHubDesktop\app-*") do (
        if not defined GIT if exist "%%D\resources\app\git\cmd\git.exe" set "GIT=%%D\resources\app\git\cmd\git.exe"
    )
)
if defined GIT goto :havgit

echo Git not found. Install it automatically with winget? (about 1-2 minutes)
set /p ANS=Install now? [Y/n]: 
if /i "%ANS%"=="n" goto :desktop
echo [*] Installing Git via winget ...
winget install --id Git.Git -e --accept-source-agreements --accept-package-agreements
if exist "%ProgramFiles%\Git\cmd\git.exe" (
    set "GIT=%ProgramFiles%\Git\cmd\git.exe"
) else (
    where git >nul 2>nul && set "GIT=git"
)
if not defined GIT (
    echo [ERROR] Git install failed. Use GitHub Desktop instead:
    goto :desktop
)
echo [OK] Git installed.

:havgit
echo Using git: %GIT%

rem ---- Repo setup: init once, remember remote URL ----
set "FRESH=0"
if exist ".git" goto :remote

echo [*] First run: initializing local repository ...
"%GIT%" init -q
"%GIT%" symbolic-ref HEAD refs/heads/main
"%GIT%" config user.name "spark"
"%GIT%" config user.email "spark@local"
set "FRESH=1"

set "REPO_URL="
if exist ".seal_repo.txt" set /p REPO_URL=<.seal_repo.txt
if not defined REPO_URL (
    echo.
    echo Create a PRIVATE repo on github.com first (New repository -^> Private).
    echo Repo URL looks like: https://github.com/yourname/yourrepo.git
    set /p REPO_URL=Paste your repo URL: 
)
if not defined REPO_URL (
    echo [ERROR] Repo URL is empty.
    pause
    exit /b 1
)
echo %REPO_URL%>.seal_repo.txt
"%GIT%" remote add origin "%REPO_URL%"
echo [OK] Repository configured. Saved URL to .seal_repo.txt (won't be committed).

rem ---- Step 3: commit and push ----
:remote
echo.
echo [3/3] Committing and pushing ...
"%GIT%" add -A
"%GIT%" commit -q -m "chore: seal update" 2>nul
if "%FRESH%"=="1" (
    "%GIT%" push -u origin main
) else (
    "%GIT%" push
    if errorlevel 1 (
        echo [*] Remote moved by Actions. Syncing and retrying ...
        "%GIT%" add -A
        "%GIT%" commit -q -m "chore: seal update" 2>nul
        "%GIT%" pull --rebase -q origin main
        "%GIT%" push
    )
)
set "TRIES=0"
:retry
if not errorlevel 1 goto :pushed
echo.
echo A browser window may have opened for GitHub login.
echo Complete the login there, then come back to this window.
set /p ANS2=Retry push now? [Y/n]: 
if /i "%ANS2%"=="n" goto :pushfail
set /a TRIES+=1
if "%TRIES%"=="3" goto :pushfail
"%GIT%" push
goto :retry
:pushed
echo.
echo [DONE] Pushed. GitHub Actions picks it up on the next 30-min tick.
pause
exit /b 0
:pushfail
echo.
echo [WARN] Push still failing. Check: repo URL correct, network OK,
echo        or push manually via GitHub Desktop.
pause
exit /b 1

:desktop
echo   1. Open GitHub Desktop
echo   2. Type any summary (e.g. seal) -^> click "Commit to main"
echo   3. Click "Push origin"
echo.
pause
