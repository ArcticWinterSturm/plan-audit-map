@echo off
setlocal
title Plan.Audit.Map - PUBLIC Tunnel for Grok (localhost.run)
echo.
echo =========================================================
echo  Map. Think. Do. - Grok / Remote Public Tunnel
echo =========================================================
echo  Clearing port 8002...

powershell -NoProfile -Command "$procs = (netstat -ano | Select-String ':8002 ') | ForEach-Object { $_.ToString().Trim().Split()[-1] } | Select-Object -Unique; foreach ($p in $procs) { try { Stop-Process -Id $p -Force -ErrorAction Stop; Write-Host \"Killed PID $p\" } catch {} }"

:waitloop
netstat -ano | findstr ":8002 " >nul 2>&1
if %errorlevel%==0 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)
echo  Port 8002 is free.
echo.
echo  No token. After connecting, the PUBLIC URL prints here.
echo  Copy that URL into Grok's MCP server settings.
echo  Keep this window open while using Grok.
echo =========================================================
echo.
if not exist "%~dp0..\dist\index.js" (
  echo [!] dist\index.js not found. Run install.bat first.
  pause & exit /b 1
)
node "%~dp0..\dist\index.js" --remote --tunnel localhostrun
echo.
echo [!] Tunnel stopped. Press any key to close.
pause
