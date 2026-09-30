@echo off
title Plan.Audit.Map — LAN Server (local network IP)
echo.
echo =========================================================
echo  Map. Think. Do. — Local Network SSE Server
echo  Resolves to your LAN IP (e.g. 192.168.x.x)
echo  Port:   8002
echo  Token:  NONE (open access)
echo.
echo  After startup, the server will print its IP.
echo  Use that IP in your MCP client:
echo    http://192.168.x.x:8002/sse
echo =========================================================
echo.
node "C:\Users\User\Documents\MapThinkDo\plan-audit-map-work\dist\index.js" --sse --local --port 8002
echo.
echo [!] Server stopped. Press any key to close.
pause
