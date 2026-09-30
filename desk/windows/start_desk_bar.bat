@echo off
setlocal
title MapThinkDo Desk Bar - start / stop / status
echo.
echo =========================================================
echo  MapThinkDo taskbar desk bar helper
echo =========================================================
echo.
where py >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

:menu
echo   1 - start the desk bar (click it later for the overview)
echo   2 - stop the desk bar
echo   3 - open the SQL viewer now
echo   4 - print a ready-to-paste mcpServers entry
echo   5 - open the Intervention paste bar (circular-CoT rescue)
echo   6 - exit
set /p choice="choice: "
if "%choice%"=="1" goto start
if "%choice%"=="2" goto stop
if "%choice%"=="3" goto viewer
if "%choice%"=="4" goto cfg
if "%choice%"=="5" goto ivp
goto :eof

:start
%PY% "%~dp0..\desk\planauditmap_launcher.py" --start-bar
goto menu

:stop
%PY% "%~dp0..\desk\planauditmap_launcher.py" --stop-bar
goto menu

:viewer
set PYTHONW=%~dp0..\desk
start "" pythonw "%~dp0..\desk\planauditmap_viewer.py"
goto menu

:cfg
%PY% "%~dp0..\desk\planauditmap_launcher.py" --print-mcp-config
echo.
goto menu

:ivp
%PY% "%~dp0..\desk\planauditmap_launcher.py" --open-intervention
goto menu
