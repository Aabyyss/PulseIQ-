$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$VenvPython = Join-Path $Root ".venv\Scripts\python.exe"

if (-not (Test-Path $VenvPython)) {
  throw "Virtual environment not found. Run .\setup.ps1 first."
}

Set-Location $Root
& $VenvPython -m uvicorn backend.api_server:app --reload --port 8000
