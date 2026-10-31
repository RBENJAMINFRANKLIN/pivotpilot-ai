#!/usr/bin/env bash
# Starts the API on :8000 and the web app on :5173. Ctrl+C stops both.
set -euo pipefail
cd "$(dirname "$0")/.."
(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
API=$!
trap 'kill $API 2>/dev/null' EXIT
cd frontend && npx vite --port 5173
