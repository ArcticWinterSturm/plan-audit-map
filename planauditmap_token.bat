@echo off
title Plan.Audit.Map — Token-Protected Server (localhost)
echo.
echo =========================================================
echo  Map. Think. Do. — Bearer Token SSE Server
echo  Host:   127.0.0.1
echo  Port:   8002
echo  Token:  my-secure-token-123
echo.
echo  Connect with token in URL:
echo    http://127.0.0.1:8002/sse?token=my-secure-token-123
echo.
echo  OR connect with Bearer header:
echo    URL:           http://127.0.0.1:8002/sse
echo    Authorization: Bearer my-sec...-123
echo =========================================================
echo.
node "C:\Users\User\Documents\MapThinkDo\plan-audit-map-work\dist\index.js" --sse --host 127.0.0.1 --port 8002 --token my-secure-token-123
echo.
echo [!] Server stopped. Press any key to close.
pause
