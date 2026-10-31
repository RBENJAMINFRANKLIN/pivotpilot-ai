#!/usr/bin/env bash
# One-time setup on macOS / Linux. Needs Python 3.11+ and Node 20+.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "==> Backend"
cd backend
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements-dev.txt
[ -f .env ] || cp .env.example .env
.venv/bin/python -m app.cli init
cd ../frontend
echo "==> Frontend"
npm install --no-audit --no-fund
echo "Setup complete. Run: ./scripts/dev.sh"
