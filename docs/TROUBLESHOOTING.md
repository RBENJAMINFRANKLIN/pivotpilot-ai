# Troubleshooting

| Problem | Fix |
|---|---|
| Web app says "Cannot reach the PivotPilot server" | The backend is not running. Start it (`scripts/dev.*`) and check http://localhost:8000/health |
| `py` / `python3` not found | Install Python 3.11+ from python.org (Windows: tick "Add to PATH") |
| `npm` not found | Install Node.js 20+ LTS from nodejs.org |
| PowerShell blocks the scripts | `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then run again |
| Port 8000 or 5173 already in use | Stop the other program, or change `--port` in `scripts/dev.*` (and `VITE_API_PROXY`) |
| "Too many requests" | Rate limits are per IP. Wait a minute, or raise `RATE_LIMIT_*` in `backend/.env` for local testing |
| Upload rejected: "No readable text" | The PDF is a scanned image. Paste the text instead |
| Job link says "please paste" | The site blocks automated reading or the posting expired. Paste the description |
| Start completely fresh | Stop the servers, delete `backend/pivotpilot.db` and `backend/data/`, run `python -m app.cli init` |
| Database schema errors after pulling changes | `python -m app.cli init` (applies new migrations) |
