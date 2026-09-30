@echo off
setlocal
title Plan.Audit.Map - Stdio Mode (for MCP config file use)
echo.
echo =========================================================
echo  Map. Think. Do. - Stdio Transport Mode
echo.
echo  NOTE: This mode is for clients that connect via stdio
echo  (e.g. Claude Desktop, Qwen Desktop, Antigravity).
echo  It does NOT expose an HTTP/SSE URL.  This window will
echo  look idle while the client talks to the server - that
echo  is normal.
echo.
echo  For Grok or HTTP-based clients, use:
echo    planauditmap_localhost.bat   (open, no token)
echo    planauditmap_token.bat       (token protected)
echo    planauditmap_remote.bat      (public tunnel)
echo =========================================================
echo.
if not exist "%~dp0..\dist\index.js" (
  echo [!] dist\index.js not found. Run install.bat first.
  pause & exit /b 1
)
node "%~dp0..\dist\index.js"
echo.
echo [!] Server stopped. Press any key to close.
pause
