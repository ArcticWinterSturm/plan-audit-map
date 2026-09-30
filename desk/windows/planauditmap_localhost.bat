@echo off
setlocal
title Plan.Audit.Map - Open SSE Server (localhost, no token)
echo.
echo =========================================================
echo  Map. Think. Do. - Open SSE Server
echo  Host:   127.0.0.1
echo  Port:   8002
echo  Token:  NONE (open access)
echo  URL:    http://127.0.0.1:8002/sse
echo.
echo  Use this URL in any MCP client:
echo    http://127.0.0.1:8002/sse
echo =========================================================
echo.
if not exist "%~dp0..\dist\index.js" (
  echo [!] dist\index.js not found. Run install.bat first.
  pause & exit /b 1
)
node "%~dp0..\dist\index.js" --sse --host 127.0.0.1 --port 8002
echo.
echo [!] Server stopped. Press any key to close.
pause
