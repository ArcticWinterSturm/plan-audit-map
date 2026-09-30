@echo off
setlocal
title Plan.Audit.Map - Token-Protected Server (localhost)
echo.
echo =========================================================
echo  Map. Think. Do. - Bearer Token SSE Server
echo  Host:   127.0.0.1
echo  Port:   8002
echo  Token:  my-secure-token-123   (edit this file to change)
echo.
echo  Connect with token in URL:
echo    http://127.0.0.1:8002/sse?token=my-secure-token-123
echo.
echo  OR connect with Bearer header:
echo    URL:           http://127.0.0.1:8002/sse
echo    Authorization: Bearer my-secure-token-123
echo =========================================================
echo.
if not exist "%~dp0..\dist\index.js" (
  echo [!] dist\index.js not found. Run install.bat first.
  pause & exit /b 1
)
node "%~dp0..\dist\index.js" --sse --host 127.0.0.1 --port 8002 --token my-secure-token-123
echo.
echo [!] Server stopped. Press any key to close.
pause
