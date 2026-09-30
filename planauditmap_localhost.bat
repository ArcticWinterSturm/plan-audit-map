@echo off
title Plan.Audit.Map — Open Server (localhost, no token)
echo.
echo =========================================================
echo  Map. Think. Do. — Open SSE Server
echo  Host:   127.0.0.1
echo  Port:   8002
echo  Token:  NONE (open access)
echo  URL:    http://127.0.0.1:8002/sse
echo.
echo  Use this URL in any MCP client:
echo    http://127.0.0.1:8002/sse
echo =========================================================
echo.
node "C:\Users\User\Documents\MapThinkDo\plan-audit-map-work\dist\index.js" --sse --host 127.0.0.1 --port 8002
echo.
echo [!] Server stopped. Press any key to close.
pause
