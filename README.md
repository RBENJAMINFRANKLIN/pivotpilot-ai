# PivotPilot AI

A career-transition coach for professionals moving into a new role. It compares your resume with a real
job description, checks your skills with an adaptive quiz, builds a week-by-week learning plan that fits the
hours you actually have, and tracks progress, mock interviews and job applications on one dashboard.

This repository is a **local prototype**: everything runs on your computer with one command, using SQLite
and no external services. Production pieces (hosted login, cloud storage, live course search, Docker,
hosting) have clearly marked placeholders; see [docs/FUTURE.md](docs/FUTURE.md).

## Run it locally

You need **Python 3.11+** and **Node.js 20+**.

**Windows (PowerShell)**

```powershell
.\scripts\setup.ps1     # one time: installs everything and creates the database
.\scripts\dev.ps1       # every time: starts the API and the web app
```

**macOS / Linux**

```bash
./scripts/setup.sh      # one time
./scripts/dev.sh        # every time
```

Then open **http://localhost:5173** and choose **Start as a guest**, **Sign in**, or **Open demo**
(a fictional teacher moving into data analysis, with every screen filled in).

API docs (OpenAPI): http://localhost:8000/api/docs

**Single-server mode**: after `cd frontend && npm run build`, the backend also serves the web app, so
`uvicorn app.main:app --port 8000` alone gives you everything at http://localhost:8000.

**Public demo link (Render, free)**: push this repo to GitHub, then in Render choose
*New + → Blueprint*, pick the repository and click *Apply*. `render.yaml` builds the web app and serves it
from the API at `https://pivotpilot-ai.onrender.com` (the name may differ). The free plan sleeps when idle and
the demo database resets on restart.

<details><summary>Manual steps (if you prefer)</summary>

```bash
cd backend
python -m venv .venv && .venv/bin/pip install -r requirements-dev.txt   # Windows: .venv\Scripts\pip
cp .env.example .env
.venv/bin/python -m app.cli init        # create tables + load skills, questions, resources
.venv/bin/uvicorn app.main:app --reload --port 8000

cd ../frontend
npm install
npx vite --port 5173                     # proxies /api to :8000
```
</details>

## The journey

1. Create a career goal (current → target role). Several goals can be saved; one is active.
2. Upload a PDF/DOCX resume or paste/dictate your background. Check and correct what was extracted.
3. Add the target job: a link (falls back to pasted text if the site blocks reading), pasted text, or a role template.
4. Set your deadline, weekly hours, budget and preferred formats.
5. **Fit analysis**: resume quality, role fit and experience alignment as separate scores, each requirement shown
   with the job's sentence next to the resume line that supports it.
6. **Adaptive assessment**: questions from the job's required skills, harder or easier as you go, every mandatory
   skill covered, answers revealed only at the end. Results show score, accuracy, difficulty and confidence;
   too little evidence is reported as "not enough evidence", never as a made-up number.
7. **Learning plan**: prerequisite-ordered weekly plan of lessons, practice, checkpoint quizzes, revision and a
   portfolio project. Never exceeds your weekly hours; flags unrealistic deadlines with alternatives;
   provisional until you take the assessment.
8. **Progress loop**: tick tasks off; finishing a course prompts a checkpoint quiz; quiz results update your
   proficiency and the plan is revised automatically when the evidence justifies it (completed work is kept).
9. **Projects, mock interviews and applications**, all feeding the dashboard's readiness indicators.
10. **Dictation-friendly command box** (works with Wispr Flow or any dictation tool): say *"I can study 8 hours a week"*,
    *"I applied for a data analyst role at Acme"* or *"I finished today's task"*, review the proposed change,
    confirm, see the result. See [docs/WISPR_FLOW.md](docs/WISPR_FLOW.md).

## Tests

```bash
cd backend && .venv/bin/pytest -q                    # 81 API/service tests (SQLite)
TEST_DATABASE_URL=postgresql+psycopg://... pytest -q # same tests on PostgreSQL
cd frontend && npx vitest run                        # component tests
cd frontend && npx playwright test                   # browser end-to-end (servers must be running,
                                                     # or set E2E_START_SERVERS=1)
```

## Project layout

```
backend/   FastAPI + SQLAlchemy + Alembic (Python)
  app/api/v1/      versioned REST endpoints (/api/v1)
  app/services/    scoring, assessment engine, planner, resources, interviews, commands, ...
  app/ai/          provider abstraction: rules (default) | Anthropic Claude | OpenAI-compatible local
  app/seed/        skill taxonomy, question bank, curated resources, interview & project templates
  alembic/         database migrations
  tests/           pytest suite
frontend/  React + TypeScript + Vite + Tailwind + TanStack Query + React Hook Form + Zod + Recharts
  e2e/             Playwright journey tests
docs/      architecture, scoring, API, security, deployment, future work
scripts/   setup and run scripts (Windows + macOS/Linux)
```

## Documentation

- [Architecture](docs/ARCHITECTURE.md) · [Scoring & assessment methodology](docs/SCORING.md) · [API](docs/API.md)
- [Security & privacy](docs/SECURITY.md) · [Deployment](docs/DEPLOYMENT.md) · [Troubleshooting](docs/TROUBLESHOOTING.md)
- [Future work & placeholders](docs/FUTURE.md) · [Wispr Flow demo](docs/WISPR_FLOW.md)

The adaptive quiz reuses interaction patterns from [QuizBlitz Live Quiz](https://github.com/RBENJAMINFRANKLIN/quizblitz-live-quiz)
(same author): public question projection without answer keys, one answer per open question, server-side timing and
scoring, and the colour + shape answer tiles. No code was copied; the patterns were re-implemented in Python/React.
