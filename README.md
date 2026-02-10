# SEO Analyzer Hybrid Starter

Hybrid starter for SEO page analysis with a web UI and API backend.

## Stack

- Web: Next.js (App Router)
- API: FastAPI + PostgreSQL + Redis Queue
- Audits: HTML checks + Playwright + Lighthouse
- Report export: PDF endpoint per audit
- Auth: users + JWT bearer tokens
- Automation: weekly schedules + email notifications with PDF attachment
- Future desktop path: API-first contract (desktop client can reuse endpoints)

## Project Structure

- `web/` - dashboard UI for starting audits and viewing results
- `backend/` - API endpoints, PostgreSQL store, Redis queue workers, SEO checks
- `desktop/` - notes for future Electron/Tauri client

## Quick Start

### Option A) Docker Compose (recommended)

```bash
docker compose up --build
```

Services:

- API: `http://localhost:8000`
- Web: `http://localhost:3001`
- PostgreSQL: `localhost:5432`
- Redis: `localhost:6379`
- MailHog UI: `http://localhost:8025`

### Option B) Run locally

Local mode works without Docker now:

- DB fallback: SQLite file `backend/seo_analyzer.db`
- Queue fallback: if Redis is down, audits run in background thread

### 1) Backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

In separate terminal run worker:

```bash
cd backend
rq worker audits --url redis://localhost:6379/0
```

### 2) Web

```bash
cd web
npm install
npm run dev
```

Set `NEXT_PUBLIC_API_URL` (optional). Default: `http://localhost:8000`.

## API Endpoints (v1)

Auth:

- `POST /auth/register`
- `POST /auth/login`

- `POST /projects`
- `POST /audits/start`
- `GET /audits/{id}/status`
- `GET /audits/{id}/results`
- `GET /projects/{id}/history`
- `GET /projects/{id}/actions`
- `GET /audits/{id}/report.pdf`
- `POST /schedules`
- `GET /schedules`

## Top 10 Implemented Audit Parameters

- Canonical tag presence and validity
- Meta robots noindex detection
- robots.txt full-site disallow detection
- sitemap.xml availability and basic XML validity
- Content depth (word count / thin content)
- Broken internal links (sampled checks)
- HTTPS enforcement signal
- Mixed content resources on HTTPS pages
- Open Graph metadata completeness
- hreflang basic format validation

## Notes

- Data is persisted in PostgreSQL.
- Audit jobs are queued in Redis and processed by `rq worker`.
- Lighthouse CLI must be available in runtime (`npx lighthouse`).
- Playwright requires Chromium (`playwright install chromium`).
- Protected endpoints require `Authorization: Bearer <token>`.
- Weekly scheduler runs inside API process and enqueues due jobs.
- Emails are sent via SMTP and include generated PDF report.
- Desktop client can call same API without backend changes.
