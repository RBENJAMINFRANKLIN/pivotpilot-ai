# Starts the API (new window, port 8000) and the web app (this window, port 5173).
Set-Location (Join-Path $PSScriptRoot "..")
Start-Process powershell -ArgumentList "-NoExit", "-Command", "cd '$PWD\backend'; .\.venv\Scripts\uvicorn app.main:app --reload --port 8000"
Set-Location frontend
npx vite --port 5173
