@echo off
title Plan.Audit.Map — Stdio Mode (for MCP config file use)
echo.
echo =========================================================
echo  Map. Think. Do. — Stdio Transport Mode
echo.
echo  NOTE: This mode is for clients that connect via stdio
echo  (e.g. Antigravity mcp_config.json, Claude Desktop).
echo  It does NOT expose an HTTP/SSE URL.
echo.
echo  For Grok or HTTP-based clients, use:
echo    planauditmap_localhost.bat  (open, no token)
echo    planauditmap_token.bat      (token protected)
echo =========================================================
echo.
node "C:\Users\User\Documents\MapThinkDo\plan-audit-map-work\dist\index.js"
echo.
echo [!] Server stopped. Press any key to close.
pause
