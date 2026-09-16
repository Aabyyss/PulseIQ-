param(
  [switch]$SkipNodeInstall,
  [switch]$SkipPythonInstall
)

$ErrorActionPreference = "Stop"

function Test-CommandExists {
  param([string]$Name)
  return [bool](Get-Command $Name -ErrorAction SilentlyContinue)
}

Write-Host "=== PulseIQ Setup (Windows) ===" -ForegroundColor Cyan

if (-not (Test-CommandExists "python") -and -not $SkipPythonInstall) {
  if (Test-CommandExists "winget") {
    Write-Host "Installing Python 3.12 via winget..." -ForegroundColor Yellow
    winget install Python.Python.3.12 --accept-source-agreements --accept-package-agreements
  } else {
    throw "Python is not installed and winget is unavailable. Install Python 3.12 manually and rerun."
  }
}

if (-not (Test-CommandExists "node") -and -not $SkipNodeInstall) {
  if (Test-CommandExists "winget") {
    Write-Host "Installing Node.js LTS via winget..." -ForegroundColor Yellow
    winget install OpenJS.NodeJS.LTS --accept-source-agreements --accept-package-agreements
  } else {
    throw "Node.js is not installed and winget is unavailable. Install Node.js LTS manually and rerun."
  }
}

if (-not (Test-CommandExists "python")) {
  throw "Python not found on PATH. Open a new terminal and rerun setup.ps1."
}
if (-not (Test-CommandExists "node")) {
  throw "Node.js not found on PATH. Open a new terminal and rerun setup.ps1."
}

$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root

Write-Host "Creating virtual environment..." -ForegroundColor Yellow
python -m venv .venv

$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  throw "Virtual environment python not found at $VenvPython"
}

Write-Host "Installing backend dependencies..." -ForegroundColor Yellow
& $VenvPython -m pip install --upgrade pip
& $VenvPython -m pip install -r requirements.txt

Write-Host "Installing spaCy model en_core_web_sm..." -ForegroundColor Yellow
& $VenvPython -m spacy download en_core_web_sm

Write-Host "Installing frontend dependencies..." -ForegroundColor Yellow
Set-Location (Join-Path $Root "frontend")
npm install

Write-Host ""
Write-Host "Setup complete." -ForegroundColor Green
Write-Host "Next steps:" -ForegroundColor Green
Write-Host "1) Backend: .\run-backend.ps1   (no API key needed)"
Write-Host "2) Frontend: .\run-frontend.ps1"
Write-Host "3) Open: http://localhost:5173"
