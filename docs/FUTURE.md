# Future work and placeholders

The local prototype keeps every interface in place so these can be filled in without restructuring.

| Area | Status now | What to do |
|---|---|---|
| **Supabase Auth** | Backend verifies Supabase JWTs (HS256 secret or JWKS) when `AUTH_MODE=supabase`; local email/password is the default | Add `@supabase/supabase-js` sign-in to `frontend/src/pages/Settings.tsx` (`AuthForm`) and send the access token as `Authorization: Bearer` from `lib/api.ts` |
| **Supabase Storage** | `SupabaseStorage` class implemented, not exercised locally | Create a private `resumes` bucket; set `STORAGE_BACKEND=supabase` + service-role key |
| **Supabase Postgres** | Works today: set `DATABASE_URL` and run `python -m app.cli init` | Enable daily backups / PITR |
| **Live resource discovery** | `YouTubeDiscovery` / `WebSearchDiscovery` in `services/resources.py` return nothing until configured | Implement `search()` with the YouTube Data API v3 (`search.list` + `videos.list` for verified durations) and Google Programmable Search restricted to provider domains; dedupe by canonical URL; store as `source=youtube/search` |
| **Link verification schedule** | `python -m app.cli verify-resources` and a per-resource "Check link now" button | Run the CLI daily (cron / Render cron job) |
| **AI providers** | Claude (`anthropic`) and OpenAI-compatible local endpoints implemented and unit-tested with fakes; default `rules` | Set `AI_PROVIDER` and keys; test against the real provider |
| **AI plan narratives / resource re-ranking** | Deterministic text and ranking (`ranking-v1`) | Optional LLM re-ordering of already-retrieved resources only |
| **Rate limiting** | In-memory, per process | Redis-backed limiter for multi-instance deployments |
| **Docker** | Not used for the local demo | Add `backend/Dockerfile` (python:3.13-slim, `uvicorn app.main:app`) and `frontend/Dockerfile` (build + static server) |
| **Hosting** | Local only | Render (backend), Vercel (frontend with an `/api` rewrite to the backend so cookies stay first-party), Supabase (DB). See DEPLOYMENT.md |
| **Voice** | Plain text fields that accept dictation (Wispr Flow tested by design, not on a device here) | Validate on Windows/macOS with Wispr Flow installed |
| **Question bank** | 88 curated questions across 16 skills | Expand per role family; expert review of AI-generated questions |
| **Frontend bundle** | One ~800 kB chunk | Route-level code splitting with `React.lazy` |
