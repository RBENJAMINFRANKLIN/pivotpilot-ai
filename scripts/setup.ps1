# One-time setup on Windows (PowerShell). Needs Python 3.11+ and Node.js 20+.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

# Find Python: the "py" launcher first, then "python" (ignoring the Microsoft Store placeholder).
$python = $null
if (Get-Command py -ErrorAction SilentlyContinue) {
    $python = "py"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $out = & python --version 2>&1
    if ("$out" -match "Python 3\.(\d+)" -and [int]$Matches[1] -ge 11) { $python = "python" }
}
if (-not $python) {
    Write-Host "Python 3.11 or newer was not found." -ForegroundColor Red
    Write-Host "Install it with:  winget install -e --id Python.Python.3.13"
    Write-Host "   or download from https://www.python.org/downloads/ and tick 'Add python.exe to PATH'."
    Write-Host "Then CLOSE and REOPEN PowerShell and run .\scripts\setup.ps1 again."
    exit 1
}
if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
    Write-Host "Node.js (npm) was not found." -ForegroundColor Red
    Write-Host "Install it with:  winget install -e --id OpenJS.NodeJS.LTS"
    Write-Host "   or download the LTS version from https://nodejs.org"
    Write-Host "Then CLOSE and REOPEN PowerShell and run .\scripts\setup.ps1 again."
    exit 1
}

Write-Host "==> Backend"
Set-Location backend
if ($python -eq "py") { py -3 -m venv .venv } else { python -m venv .venv }
.\.venv\Scripts\python -m pip install -q --upgrade pip
.\.venv\Scripts\python -m pip install -q -r requirements-dev.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.\.venv\Scripts\python -m app.cli init
Set-Location ..\frontend
Write-Host "==> Frontend"
npm install --no-audit --no-fund
Set-Location ..
Write-Host "Setup complete. Run: .\scripts\dev.ps1" -ForegroundColor Green
