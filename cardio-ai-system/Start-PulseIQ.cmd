@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo    PulseIQ - Cardiac Screening Workspace
echo ========================================
echo.
echo Starting backend and frontend...

start "PulseIQ Backend" /min powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run-backend.ps1"
timeout /t 3 /nobreak >nul
start "PulseIQ Frontend" /min powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run-frontend.ps1"

echo Waiting for the app to come up...
timeout /t 8 /nobreak >nul
start "" http://localhost:5173

echo.
echo PulseIQ is running in your browser (http://localhost:5173).
echo Two minimised windows (PulseIQ Backend / Frontend) keep it alive -
echo close them or run Stop-PulseIQ.cmd to stop the app.
echo.
echo This launcher closes itself in a moment.
timeout /t 5 /nobreak >nul
exit
