@echo off
setlocal
title Plan.Audit.Map - LAN Server (local network IP)
echo.
echo =========================================================
echo  Map. Think. Do. - Local Network SSE Server
echo  Resolves to your LAN IP (e.g. 192.168.x.x)
echo  Port:   8002
echo  Token:  NONE (open on your LAN - use with care)
echo.
echo  After startup the server prints its IP.
echo  Use that IP in your MCP client:
echo    http://192.168.x.x:8002/sse
echo =========================================================
echo.
if not exist "%~dp0..\dist\index.js" (
  echo [!] dist\index.js not found. Run install.bat first.
  pause & exit /b 1
)
node "%~dp0..\dist\index.js" --sse --local --port 8002
echo.
echo [!] Server stopped. Press any key to close.
pause
