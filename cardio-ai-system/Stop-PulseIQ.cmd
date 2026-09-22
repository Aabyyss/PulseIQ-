@echo off
setlocal

echo ========================================
echo    PulseIQ - Stop Servers
echo ========================================
echo.

powershell -NoProfile -Command "Get-NetTCPConnection -LocalPort 8000,5173 -State Listen -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess -Unique | ForEach-Object { Stop-Process -Id $_ -Force -ErrorAction SilentlyContinue }"

echo Backend (port 8000) and frontend (port 5173) stopped.
echo.
pause
