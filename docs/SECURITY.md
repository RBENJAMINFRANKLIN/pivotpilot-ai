# Security and privacy

## Implemented

- **Sessions**: guest token and local login token in `httpOnly`, `SameSite=Lax` cookies (`Secure` when
  `COOKIE_SECURE=true`). Only a SHA-256 hash of guest tokens is stored. Bearer tokens are also accepted.
- **CSRF**: every state-changing request must carry `X-PivotPilot-Client: web`. Browsers cannot add it
  cross-site without a CORS preflight, which the origin allow-list (`CORS_ORIGINS`) rejects.
- **Authorisation and tenant isolation**: every query filters by the caller's workspace; foreign IDs return 404.
- **Passwords**: scrypt with a random salt. Login and registration are rate-limited.
- **Rate limits** (per IP *and* per workspace): default, auth, upload, AI and guest-creation buckets.
  *Shortcut:* in-memory per process. Use Redis before running more than one instance.
- **Uploads**: magic-byte type check, extension match, 5 MB limit, PDF page limit, encrypted PDFs rejected,
  DOCX zip checks (structure, macros, decompressed size), malformed files rejected with a safe message.
- **Outbound fetch** (job pages, link checks): http/https only, standard ports, DNS resolved and private,
  loopback, link-local and reserved addresses blocked (SSRF), redirects re-checked, robots.txt honoured, size and
  time limits, sites whose terms forbid scraping are not fetched.
- **Untrusted content**: resumes, job posts and web pages are wrapped as untrusted data in AI prompts; AI output
  is schema-validated, and extracted facts must quote the source verbatim or are discarded.
- **Errors**: stable codes and plain messages; no stack traces or internals in responses.
- **Audit log**: sign-in, migrations, resume, job, analysis, plan, assessment and command events. Resume text,
  passwords and answers are never written to audit details or logs.
- **Data deletion**: *Account & privacy → Delete everything* removes the workspace, files and account.
  Guest workspaces expire after `GUEST_RETENTION_DAYS`; run `python -m app.cli cleanup-guests` daily.
- **Storage**: resumes live in the database and a server folder (or private Supabase bucket), never in browser storage.
- **AI disclosure**: the privacy page states whether resume text is sent to a hosted AI provider.
  `AI_SEND_RESUME_TO_HOSTED=false` keeps it local; the default `rules` provider sends nothing anywhere.
- **Security headers**: `X-Content-Type-Options`, `X-Frame-Options: DENY`, `Referrer-Policy`, `Cache-Control: no-store`.

## Before production

See [FUTURE.md](FUTURE.md): HTTPS, a strong `APP_SECRET`, `COOKIE_SECURE=true`, PostgreSQL with automated
backups (Supabase daily backups or `pg_dump` cron), a Redis rate limiter, dependency scanning (`pip-audit`,
`npm audit`, Dependabot), and a scheduled guest clean-up.
