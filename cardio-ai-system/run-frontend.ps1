$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$Frontend = Join-Path $Root "frontend"

if (-not (Test-Path (Join-Path $Frontend "node_modules\vite\bin\vite.js"))) {
  throw "Frontend dependencies not found. Run .\setup.ps1 first."
}

Set-Location $Frontend
# Invoke Vite through node directly: npx/npm .ps1 shims can be blocked by
# Windows script policy in spawned shells, killing the dev server silently.
node node_modules\vite\bin\vite.js --port 5173 --strictPort
