# Project Context for Claude Code

## Overview

Open, non-commercial, public web application for visualizing advanced basketball
statistics for Spanish leagues: ACB, LEB Oro (Primera FEB) and LEB Plata (Segunda
FEB). Focus on historical, post-game analytics for teams, players and technical
staff — **not** live/in-game data.

Full technical specification: see `docs/spec.md`.

## Architecture (monorepo)

```
backend/    Django + Django REST Framework + Celery + Celery Beat
frontend/   Next.js + React + TypeScript + TailwindCSS
```

- Backend and frontend are decoupled services communicating over REST/JSON
  (CORS handled via `django-cors-headers`).
- Backend exposes camelCase JSON via `djangorestframework-camel-case` to match
  frontend TypeScript naming conventions.
- Ingestion runs asynchronously via Celery workers, scheduled with Celery Beat.
  There is no live/real-time data path by design.

## Coding conventions

- **All code must be written in English**: identifiers, comments, and
  documentation — even though the product spec and UI copy are in Spanish.
- **Python docstrings always use NumPy style** (`Parameters` / `Returns` /
  `Attributes` / `Notes` sections), for every function and class, regardless
  of size.
- Use explicit, typed code: Python type hints throughout `backend/`; strict
  TypeScript (`strict: true`) throughout `frontend/`.
- Source connectors follow the **Adapter pattern**: one connector per data
  source under `backend/connectors/`, implementing the common
  `SourceConnector` interface. Never hardcode source-specific logic outside
  a connector module.
- Ingestion never targets live/in-progress games — only completed games and
  finalized box scores.

## Data model (summary)

Core entities: `League`, `Season`, `Team`, `TeamSeason`, `Person`,
`RosterEntry`, `StaffEntry`, `Game`, `PlayerGameStats`, `TeamGameStats`,
`PlayerSeasonAggregate`, `DataSource`, `IngestionRun`.
See `docs/spec.md` §4 for full field-level detail and the Django model
reference implementation.

## Data sources

- ACB.com (Liga ACB).
- FEB.es (LEB Oro / Primera FEB, LEB Plata / Segunda FEB), e.g.
  `https://www.feb.es/primerafeb/estadisticas.aspx`.
- Additional sources may be added later if needed (see `docs/spec.md` §3.1).
- **Historical backfill target: 5-10 past seasons per league**, in addition
  to the current season.
- Respect each source's `robots.txt` and terms of use; rate-limit all
  connectors (see `docs/spec.md` §10).

## Local development

- **Docker Compose** is the standard local dev environment. Services: `db`
  (PostgreSQL), `redis`, `backend` (Django), `worker` (Celery), `frontend`
  (Next.js dev server). See `docker-compose.yml` at the repo root.
- Backend env vars live in `backend/.env`; frontend env vars live in
  `frontend/.env.local`. Never commit either file.

## Workflow

- **Solo developer project.** Favor a simple trunk-based workflow
  (short-lived branches merged directly into `main`) over a heavyweight
  PR/review process. CI checks (lint + tests) are the main safety net.
- Repository is **open source under the MIT license**.
- CI (GitHub Actions) uses path filters so `backend/` and `frontend/`
  workflows only run when their respective folder changes.

## Out of scope (do not implement)

- Live/in-game scoring, play-by-play, or any real-time data path.
- Betting, gambling, or odds-related features.
- Reproducing copyrighted media (video, official club/league logos, etc.)
  without rights; use original design assets instead.
