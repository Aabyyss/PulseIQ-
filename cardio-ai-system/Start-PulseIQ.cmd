@echo off
setlocal

cd /d "%~dp0"

echo ========================================
echo    PulseIQ - AI Heart Health Intelligence
echo ========================================
echo.
echo This will start backend and frontend in separate windows.
echo No API keys required - everything runs free and local.
echo.

start "PulseIQ Backend" powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run-backend.ps1"

timeout /t 3 /nobreak >nul
start "PulseIQ Frontend" powershell -NoExit -ExecutionPolicy Bypass -File "%~dp0run-frontend.ps1"

echo.
echo Backend and frontend are starting.
echo Open this in your browser:
echo http://localhost:5173
echo.
pause
