# Deployment

## Local (supported now)

See the README: `scripts/setup.(sh|ps1)` once, then `scripts/dev.(sh|ps1)`. Data lives in
`backend/pivotpilot.db` (SQLite) and uploads in `backend/data/uploads/`. Delete both to start fresh.

To use PostgreSQL locally instead of SQLite:

```bash
createdb pivotpilot
# backend/.env
DATABASE_URL=postgresql://USER:PASSWORD@localhost/pivotpilot
python -m app.cli init
```

## Clean checkout check

```bash
git clone <repo> && cd pivotpilot-ai
./scripts/setup.sh && ./scripts/dev.sh      # or the .ps1 versions on Windows
# open http://localhost:5173 → Open demo
```

## Hosted (future, outline)

1. **Database: Supabase.** Create a project; copy the connection string to `DATABASE_URL`.
2. **Backend: Render web service.** Root directory `backend`, build command `pip install -r requirements.txt`,
   start command `python -m app.cli init && uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
   Env: `ENVIRONMENT=production`, `APP_SECRET` (random 64 chars), `COOKIE_SECURE=true`, `CORS_ORIGINS=https://<frontend>`,
   plus any AI / Supabase keys. Add a daily cron job: `python -m app.cli cleanup-guests`.
3. **Frontend: Vercel.** Root `frontend`, build `npm run build`, output `dist`. Add a rewrite so `/api/*` proxies
   to the Render URL (keeps the session cookie first-party):
   ```json
   { "rewrites": [{ "source": "/api/:path*", "destination": "https://<backend>.onrender.com/api/:path*" },
                  { "source": "/(.*)", "destination": "/index.html" }] }
   ```
4. **Verify**: `GET /health/ready` returns `database: ok`; open the site and run the demo.
5. **CI**: `.github/workflows/ci.yml` runs lint, type checks, unit/API tests on SQLite and PostgreSQL, the
   production build and the Playwright journey.

Do not report a deployment as working until step 4 passes.
