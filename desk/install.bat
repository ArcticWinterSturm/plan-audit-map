@echo off
setlocal EnableExtensions EnableDelayedExpansion
setlocal DisableDelayedExpansion
title plan-audit-map-desk installer
echo.
echo =========================================================
echo   plan-audit-map-desk  -  one-shot installer (Windows)
echo   taskbar desk bar + wire tap + SQL viewer + MCP server
echo =========================================================
echo.

cd /d "%~dp0"
set "HERE=%~dp0"
set "DESK=%HERE%desk"
set "SERVER_SRC=%HERE%server"
set "CONNECT=%HERE%connect"
set "REPO="

REM ---- flag parsing ---------------------------------------------------------
if /i "%~1"=="--help" goto :usage
if /i "%~1"=="-h" goto :usage
set "SKIP_INSTALL=0"
if /i "%~1"=="--no-install" set "SKIP_INSTALL=1"
if /i "%~1"=="--with-bar" set "WITH_BAR=1"

REM ---- 1. locate the repo ---------------------------------------------------
echo ==^> 1/6  Locating the plan-audit-map repository
call :is_repo "%HERE%" && set "REPO=%HERE%"
if not defined REPO call :is_repo "%HERE%.." && set "REPO=%HERE%.."
if not defined REPO call :is_repo "%HERE%plan-audit-map" && set "REPO=%HERE%plan-audit-map"
if not defined REPO if not "%~1"=="" if /i not "%~1"=="--no-install" if /i not "%~1"=="--with-bar" (
    if exist "%~1\package.json" set "REPO=%~1"
)
if not defined REPO (
    echo     No repo found next to this folder - cloning a fresh copy.
    where git >nul 2>&1
    if errorlevel 1 (
        echo [X] git not found. Install git, or unzip the repo zip next to
            this folder and re-run.
        goto :fail
    )
    git clone --depth 1 https://github.com/geeknik/plan-audit-map.git "%HERE%plan-audit-map" || goto :fail
    set "REPO=%HERE%plan-audit-map"
)
for %%I in ("%REPO%") do set "REPO=%%~fI"
echo     Repo: %REPO%

REM ---- 2. overlay the enhanced server ---------------------------------------
echo ==^> 2/6  Overlaying enhanced server sources
if exist "%SERVER_SRC%\index.ts"  copy /y "%SERVER_SRC%\index.ts"  "%REPO%\index.ts" >nul
if exist "%SERVER_SRC%\server.ts" copy /y "%SERVER_SRC%\server.ts" "%REPO%\src\server.ts" >nul
if exist "%SERVER_SRC%\config.ts" (
    if not exist "%REPO%\src\utils" mkdir "%REPO%\src\utils"
    copy /y "%SERVER_SRC%\config.ts" "%REPO%\src\utils\config.ts" >nul
)
if exist "%SERVER_SRC%\package.json" copy /y "%SERVER_SRC%\package.json" "%REPO%\package.json" >nul
REM The repo tsconfig includes ./**/*.ts — it must not compile the .ts copies
REM inside THIS folder (they live properly in the repo).  Exclude ourselves.
for %%I in ("%HERE%.") do set "DESKNAME=%%~nxI"
node -e "const fs=require('fs');const p=process.argv[1],self=process.argv[2];let j;try{j=JSON.parse(fs.readFileSync(p,'utf8'));}catch(e){process.exit(0);}j.exclude=Array.from(new Set([...(j.exclude||[]),'node_modules','dist',self]));fs.writeFileSync(p,JSON.stringify(j,null,2)+String.fromCharCode(10));console.log('tsconfig excludes: '+j.exclude.join(', '));" "%REPO%\tsconfig.json" "%DESKNAME%"
echo     done ^(SSE/tunnels/dashboard server, env-aware DB path, EOF fix,
        better-sqlite3 pinned to ^12.5.0 for Node 20^)

REM ---- 3. toolchain ---------------------------------------------------------
echo ==^> 3/6  Checking the toolchain
where node >nul 2>&1 || (echo [X] node not found ^(need 20+^): https://nodejs.org & goto :fail)
for /f "delims=" %%v in ('node --version') do set "NODE_VER=%%v"
set "NODE_MAJOR=%NODE_VER:~1,2%"
if %NODE_MAJOR% LSS 20 (echo [X] Node 20+ required, found %NODE_VER% & goto :fail)
for /f "delims=" %%p in ('where node') do set "NODE_BIN=%%p" & goto :gotnode
:gotnode
echo     node: %NODE_VER% (%NODE_BIN%)

set "PY_BIN="
where py >nul 2>&1 && (for /f "delims=" %%p in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do set "PY_BIN=%%p")
if not defined PY_BIN where python >nul 2>&1 && (for /f "delims=" %%p in ('python -c "import sys;print(sys.executable)" 2^>nul') do set "PY_BIN=%%p")
if defined PY_BIN (echo     python: %PY_BIN%) else (
    echo     [!] python not found - the desk bar / viewer need it:
            https://www.python.org/downloads/ ^(tick "Add to PATH"^)
)

REM ---- 4. npm install + build ------------------------------------------------
echo ==^> 4/6  Installing dependencies and building
cd /d "%REPO%"
if "%SKIP_INSTALL%"=="1" (
    echo     skipping npm install (--no-install)
) else (
    call npm install --no-audit --no-fund
    if errorlevel 1 (
        echo     [!] npm install failed - retrying with scripts disabled + native rebuild
        call npm install --no-audit --no-fund --ignore-scripts || goto :npm_fail
        call npm rebuild better-sqlite3 || goto :npm_fail
    )
)
call npx tsc || (echo [X] build ^(tsc^) failed & goto :fail)
if not exist "%REPO%\dist\index.js" (echo [X] dist\index.js missing after build & goto :fail)
node "%REPO%\dist\index.js" --help >nul 2>&1 || (echo [X] built server failed --help smoke test & goto :fail)
echo     dist\index.js built and responds to --help

REM ---- 5. desk-bar config + connection JSONs ---------------------------------
echo ==^> 5/6  Writing config and resolving connection JSONs
if not defined PY_BIN (
    echo     [!] skipping config/JSON resolution ^(no python^)
    goto :step6
)
set "CONF_DIR=%USERPROFILE%\.plan-audit-map"
if defined PLAN_AUDIT_MAP_HOME set "CONF_DIR=%PLAN_AUDIT_MAP_HOME%"
if not exist "%CONF_DIR%" mkdir "%CONF_DIR%"

%PY_BIN% "%HERE%tools\install_helpers.py" "%DESK%" "%REPO%\dist\index.js" "%PY_BIN%" "%CONF_DIR%\desk-bar.json" "%NODE_BIN%" "%CONNECT%"
if errorlevel 1 (echo     [!] config/JSON resolution had problems) else echo     wrote %CONF_DIR%\desk-bar.json + connect\*.local.json

:step6
REM ---- 6. summary -------------------------------------------------------------
echo ==^> 6/6  Done
if "%WITH_BAR%"=="1" (
    if defined PY_BIN %PY_BIN% "%DESK%\planauditmap_launcher.py" --start-bar && echo     desk bar started || echo     [!] bar did not start
)
echo.
echo =========================================================
echo   INSTALL COMPLETE
echo.
echo     server        %REPO%\dist\index.js
echo     desk stack    %DESK%
echo     config        %CONF_DIR%\desk-bar.json
echo     connections   %CONNECT%\*.local.json   (paste-ready)
echo.
echo   Try it now:
echo     "%DESK%\..\windows\start_desk_bar.bat"     (bar helper)
echo     "%PY_BIN%" "%DESK%\planauditmap_viewer.py"   (SQL viewer)
echo     node "%REPO%\dist\index.js" --sse --port 8002
echo.
echo   Connect an MCP client: open connect\plan-audit-map.stdio+desk.local.json
echo   and paste it into your client config (see connect\README.md).
echo =========================================================
exit /b 0

:is_repo
if exist "%~1\package.json" (findstr /c:"@geeknik/plan-audit-map" "%~1\package.json" >nul 2>&1 && exit /b 0)
exit /b 1

:npm_fail
echo [X] npm install failed. Native modules need build tools:
     https://github.com/nodejs/node-gyp#on-windows
     (npm install -g windows-build-tools OR Visual Studio Build Tools)
goto :fail

:usage
echo Usage: install.bat [--no-install] [--with-bar] [path-to-repo]
exit /b 0

:fail
echo.
echo [X] INSTALL FAILED - see messages above.
exit /b 1
