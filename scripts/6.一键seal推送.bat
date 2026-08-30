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
echo [1/4] Sealing data -^> vault\data.enc ...
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
echo [2/4] Looking for git ...
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

rem ---- Step 3: repository (auto login + auto create, or reuse saved URL) ----
set "FRESH=0"
if exist ".git" goto :remote

echo.
echo [3/4] First run: preparing repository ...
echo [*] Initializing local repository ...
"%GIT%" init -q
"%GIT%" symbolic-ref HEAD refs/heads/main
"%GIT%" config user.name "spark"
"%GIT%" config user.email "spark@local"
set "FRESH=1"

rem Preferred path: GitHub CLI login (browser pops) + auto-create private repo
call :ghflow
if not errorlevel 1 goto :remote

rem Fallback: manual URL paste
echo.
echo Falling back to manual setup.
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
call :setremote

rem ---- Step 3.5: connection + login gate (browser pops HERE on first push) ----
:remote
echo.
echo [3.5/4] Testing GitHub connection and login ...
"%GIT%" ls-remote origin >nul 2>"%TEMP%\spark_git_err.txt"
if not errorlevel 1 goto :remoteok
call :diag
set /p ANS3=Fixed? Retry connection now? [Y/n]:
if /i "%ANS3%"=="n" goto :pushfail
timeout /t 3 /nobreak >nul
goto :remote
:remoteok
echo [OK] GitHub reachable and login accepted.

rem ---- Step 4: commit and push ----
echo.
echo [4/4] Committing and pushing ...
"%GIT%" add -A
"%GIT%" commit -q -m "chore: seal update" 2>nul
if "%FRESH%"=="1" (
    "%GIT%" push -u origin main 2>"%TEMP%\spark_git_err.txt"
) else (
    "%GIT%" push -u origin main 2>"%TEMP%\spark_git_err.txt"
    if errorlevel 1 (
        echo [*] Remote moved by Actions. Syncing and retrying ...
        "%GIT%" add -A
        "%GIT%" commit -q -m "chore: seal update" 2>nul
        rem Empty remote has no main ref - pull may fail, that is fine.
        "%GIT%" pull --rebase -q origin main 2>nul
        call :fixrebase
        "%GIT%" push -u origin main 2>"%TEMP%\spark_git_err.txt"
    )
)
set "TRIES=0"
:retry
if not errorlevel 1 goto :pushed
rem First push rejected because remote already has history? Rebase local onto it.
findstr /i "fetch first rejected" "%TEMP%\spark_git_err.txt" >nul 2>nul
if errorlevel 1 goto :noresync
echo [*] Remote already has history. Moving local commit on top of it ...
"%GIT%" fetch -q origin 2>nul
"%GIT%" reset --soft origin/main 2>nul
"%GIT%" commit -q -m "chore: seal update" 2>nul
:noresync
call :diag
set /p ANS2=Retry push now? [Y/n]:
if /i "%ANS2%"=="n" goto :pushfail
set /a TRIES+=1
if "%TRIES%"=="3" goto :pushfail
timeout /t 3 /nobreak >nul
call :fixrebase
"%GIT%" push -u origin main 2>"%TEMP%\spark_git_err.txt"
goto :retry
:pushed
echo.
echo [DONE] Pushed. GitHub Actions picks it up on the next 30-min tick.
pause
exit /b 0
:pushfail
echo.
echo [WARN] Push still failing. Git said:
type "%TEMP%\spark_git_err.txt" 2>nul
echo Check: repo URL correct, network OK, or push manually via GitHub Desktop.
pause
exit /b 1

rem ===================== subroutines =====================

:setremote
"%GIT%" remote add origin "%REPO_URL%" 2>nul
"%GIT%" remote set-url origin "%REPO_URL%"
echo %REPO_URL%>.seal_repo.txt
echo [OK] Repository configured. Saved URL to .seal_repo.txt (won't be committed).
exit /b 0

:ghflow
rem Locate GitHub CLI (gh) - the official tool that can log in and create repos
set "GH="
where gh >nul 2>nul && set "GH=gh"
if not defined GH if exist "%ProgramFiles%\GitHub CLI\gh.exe" set "GH=%ProgramFiles%\GitHub CLI\gh.exe"
if defined GH goto :havgh
echo.
echo [GH] To log in to GitHub and create the repo automatically,
echo      the GitHub CLI (official tool) is needed.
set /p ANS5=Install it now with winget? (1-2 minutes) [Y/n]:
if /i "%ANS5%"=="n" exit /b 1
echo [*] Installing GitHub CLI via winget ...
winget install --id GitHub.cli -e --accept-source-agreements --accept-package-agreements
if exist "%ProgramFiles%\GitHub CLI\gh.exe" (
    set "GH=%ProgramFiles%\GitHub CLI\gh.exe"
) else (
    where gh >nul 2>nul && set "GH=gh"
)
if not defined GH (
    echo [WARN] GitHub CLI install failed.
    exit /b 1
)
echo [OK] GitHub CLI installed.
:havgh
echo [*] Checking GitHub login ...
"%GH%" auth status >nul 2>nul
if not errorlevel 1 goto :ghlogged
echo.
echo =======================================================
echo   A browser window will open to log in to GitHub.
echo   1. When the black window asks, press Enter.
echo   2. GitHub shows a one-time code - type it in the browser.
echo   3. Log in with the account that should own the repo.
echo =======================================================
"%GH%" auth login --hostname github.com --git-protocol https --web
if errorlevel 1 (
    echo [WARN] Login failed or cancelled.
    exit /b 1
)
:ghlogged
"%GH%" auth setup-git >nul 2>nul
echo [*] Getting your GitHub username ...
"%GH%" api user --jq .login >"%TEMP%\spark_ghuser.txt" 2>nul
set "GHUSER="
set /p GHUSER=<"%TEMP%\spark_ghuser.txt"
if not defined GHUSER (
    echo [WARN] Could not read GitHub username.
    exit /b 1
)
echo [*] Creating private repo %GHUSER%/spark-cloud (reused if it already exists) ...
"%GH%" repo create spark-cloud --private >nul 2>nul
echo [*] Writing repo secret DATA_KEY and enabling Actions ...
"%GH%" secret set DATA_KEY --body "%DATA_KEY%" -R "%GHUSER%/spark-cloud" >nul 2>nul
"%GH%" api -X PUT "repos/%GHUSER%/spark-cloud/actions/permissions" -f enabled=true >nul 2>nul
set "REPO_URL=https://github.com/%GHUSER%/spark-cloud.git"
call :setremote
echo [OK] Repo ready: %REPO_URL%
exit /b 0

:clearcred
echo [*] Clearing saved GitHub login. On the next try a browser will open -
echo     log in with the account that OWNS the private repo.
(echo protocol=https
echo host=github.com
echo.) | "%GIT%" credential reject
exit /b 0

:fixrebase
if not exist .git\rebase-merge exit /b 0
echo [*] Vault conflict - keeping the newest local seal ...
"%GIT%" checkout --theirs vault\data.enc 2>nul
"%GIT%" add vault\data.enc
"%GIT%" -c core.editor=true rebase --continue
exit /b 0

:diag
findstr /i "resolve connect timed refused certificate SSL" "%TEMP%\spark_git_err.txt" >nul 2>nul
if errorlevel 1 goto :diag_login
echo.
echo [NETWORK] Cannot reach github.com.
echo 1. Open https://github.com in your browser to test.
echo 2. Browser CAN open it? Your PC has a proxy, git does not use it. Run:
echo    "%GIT%" config --global http.proxy http://127.0.0.1:7890
echo    ^(port: Clash 7890, v2rayN 10808/10809 - see your proxy app^)
echo    To undo later: "%GIT%" config --global --unset http.proxy
echo 3. Browser CANNOT open it? Change network ^(phone hotspot^) and rerun.
goto :eof
:diag_login
findstr /i "Authentication Username terminal prompt" "%TEMP%\spark_git_err.txt" >nul 2>nul
if errorlevel 1 goto :diag_repo
echo.
echo [LOGIN] GitHub login required. A browser window should have opened.
echo If nothing popped up: log in at https://github.com once, then rerun.
goto :eof
:diag_repo
findstr /i "not found" "%TEMP%\spark_git_err.txt" >nul 2>nul
if errorlevel 1 goto :diag_raw
echo.
echo [REPO] Repository not found. URL in use:
"%GIT%" remote get-url origin 2>nul
echo.
echo Case A - URL is WRONG ^(typo / wrong name / full-width Chinese chars^):
echo         delete file .seal_repo.txt, rerun, paste the correct URL again.
set /p ANS4=Case B - URL is correct? Clear saved GitHub login and retry? [y/N]:
if /i "%ANS4%"=="y" (
    call :clearcred
    goto :eof
)
echo Case C - Let the script log in to GitHub and create/use the repo
echo         automatically ^(no URL pasting needed^).
set /p ANS6=Try auto login + auto repo now? [y/N]:
if /i "%ANS6%"=="y" call :ghflow
goto :eof
:diag_raw
echo.
echo [GIT-ERR] Raw git message:
type "%TEMP%\spark_git_err.txt" 2>nul
goto :eof

:desktop
echo   1. Open GitHub Desktop
echo   2. Type any summary (e.g. seal) -^> click "Commit to main"
echo   3. Click "Push origin"
echo.
pause
