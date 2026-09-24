@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo    PulseIQ - Cardiac Screening Workspace
echo ========================================
echo.
echo Starting backend and frontend...
echo.

start "PulseIQ Backend" /min powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run-backend.ps1"
timeout /t 3 /nobreak >nul
start "PulseIQ Frontend" /min powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run-frontend.ps1"

echo Waiting for the app to come up...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173

echo.
echo PulseIQ is running:
echo   - App:  http://localhost:5173
echo   - API:  http://localhost:8000/docs
echo.
echo To stop: close the two minimised PulseIQ windows,
echo or run Stop-PulseIQ.cmd.
echo.
pause
