# One-time setup on Windows (PowerShell). Needs Python 3.11+ ("py") and Node 20+.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")
Write-Host "==> Backend"
Set-Location backend
py -3 -m venv .venv
.\.venv\Scripts\python -m pip install -q --upgrade pip
.\.venv\Scripts\pip install -q -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python -m app.cli init
Set-Location ..\frontend
Write-Host "==> Frontend"
npm install --no-audit --no-fund
Write-Host "Setup complete. Run: .\scripts\dev.ps1"
