# Architecture

A **modular monolith**: one FastAPI backend and one React single-page app. No microservices, queues or vector
databases.

```
Browser (React SPA, :5173) ──/api──▶ FastAPI (:8000) ──▶ SQLAlchemy ──▶ SQLite (local) / PostgreSQL
        │                              │
        │ httpOnly session cookie       ├─ AI provider abstraction ──▶ rules | Claude | local OpenAI-compatible
        │                              ├─ Storage abstraction ──▶ local folder | Supabase Storage (placeholder)
        │                              └─ Outbound fetch (job pages, link checks) with SSRF + robots.txt guards
```

## Backend modules (`backend/app`)

| Module | Responsibility |
|---|---|
| `deps.py` | Resolves the caller (Bearer token → auth cookie → guest cookie) to a **workspace** |
| `models.py` | 30 normalised tables; every user-owned row has `workspace_id` |
| `services/workspaces.py` | Guest workspaces, atomic guest → account migration, deletion, retention clean-up |
| `services/resume.py` | PDF/DOCX/text extraction, sections, dated roles, skills with source excerpts |
| `services/jobs.py` | Safe job-page fetch with paste fallback, competency map with excerpts and importance |
| `services/scoring.py` | Versioned deterministic scores (`scoring-v1`): quality, fit, experience, gaps, readiness |
| `services/assessment.py` | Adaptive diagnostic engine (`adaptive-v1`) |
| `services/evidence.py` | Evidence types and proficiency estimates (claimed vs assessed kept separate) |
| `services/resources.py` | Curated catalogue, link verification, deterministic ranking, discovery placeholders |
| `services/planning.py` | Planner (`planner-v1`): capacity-bounded schedule, feasibility, versions, revision |
| `services/projects.py`, `interviews.py`, `applications.py` | Portfolio projects, mock interviews, application analytics |
| `services/commands.py` | Natural-language commands: parse → validate → confirm → execute |
| `ai/llm.py` | Provider selection per task, budgets, schema validation, grounding hooks, usage logs, fallbacks |

## Tenancy

A **workspace** owns all data. Guests get a workspace tied to a random token in an httpOnly cookie (only its
SHA-256 hash is stored). Signed-in users get one workspace per account. Every query filters by `workspace_id`;
IDs are random UUIDs and a foreign workspace's row returns 404, the same as a missing one.

Guest → account migration (`POST /api/v1/auth/migrate-guest`) runs in one transaction: lock the guest row,
insert a `guest_migrations` row (unique per guest workspace, so a second import is impossible), keep one
active goal, renumber resume versions, merge profile gaps, move every owned table, delete the guest workspace.

## AI usage

| Task | Default (rules) | With an AI provider |
|---|---|---|
| Resume extraction | Section/date/skill parser | Adds roles/education; items must quote the resume verbatim or are dropped |
| Job analysis | Section + keyword classifier | Adds requirements; each must quote the posting verbatim |
| Question generation | Curated bank only | Extra questions for skills without coverage; structurally validated, labelled AI-generated |
| Subjective answers | Not scored (excluded) | Rubric scores with schema validation |
| Interview feedback | Transparent heuristic rubric | Rubric scores + feedback, same rubric |
| Command parsing | Regex parser | Proposes an action; same validation and confirmation |
| Numbers, schedules, quiz scoring, statistics | Always deterministic code | Never AI |

If the provider fails or the daily budget is used, tasks with a rule-based version fall back to it; tasks without
one return a clear `503` error, and saved data stays available.
