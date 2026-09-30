@echo off
title Plan.Audit.Map — PUBLIC Tunnel for Grok (localhost.run, no token)
echo.
echo =========================================================
echo  Map. Think. Do. — Grok / Remote Public Tunnel
echo =========================================================
echo  Clearing port 8002...

:: Use PowerShell to kill anything on 8002 (more reliable than for/f)
powershell -NoProfile -Command "$procs = (netstat -ano | Select-String ':8002 ') | ForEach-Object { $_.ToString().Trim().Split()[-1] } | Select-Object -Unique; foreach ($p in $procs) { try { Stop-Process -Id $p -Force -ErrorAction Stop; Write-Host \"Killed PID $p\" } catch {} }"

:: Wait until port is actually free (up to 10 seconds)
:waitloop
netstat -ano | findstr ":8002 " >nul 2>&1
if %errorlevel%==0 (
    timeout /t 1 /nobreak >nul
    goto waitloop
)
echo  Port 8002 is free.
echo.
echo  SSH key:  id_ed25519_planauditmap ^(authenticated^)
echo  No token. After connecting the PUBLIC URL prints here.
echo  Copy that URL into Grok's MCP server settings.
echo  Keep this window open while using Grok.
echo =========================================================
echo.
node "C:\Users\User\Documents\MapThinkDo\plan-audit-map-work\dist\index.js" --remote --tunnel localhostrun
echo.
echo [!] Tunnel stopped. Press any key to close.
pause
