# CANCHA-01 — Continuous Implementation Plan

**Branch:** `CANCHA-01` from `main`
**Date:** 2026-06-28
**Goal:** Move the app from a polished MVP to a fully data-driven, production-ready
web application. All phases are sequenced so each delivers a visible, testable
increment without leaving the app in a broken state.

---

## Current state (as of branch cut)

| Area | Status |
|---|---|
| FEB connectors (box scores + enrichment) | Done — parsers, persistence, enrichment, media |
| ACB connector (JSON API, box scores, player photos) | Done |
| FEB logo scraper (`fetch_feb_logos`) | Done |
| Season aggregates (`PlayerSeasonAggregate`) | Done |
| REST API (all core endpoints) | Done |
| Frontend pages (home, ligas, equipos, jugadores, partidos, lideres, comparar) | Done |
| Dark mode + collapsible nav | Done |
| **ACB backfill** | **Pending** — command exists, not yet run |
| **FEB backfill** | **Pending** — command exists, not yet run |
| **Celery Beat schedule** | Partial — nightly ACB + weekly FEB enrichment registered but not verified live |
| `tsconfig.tsbuildinfo` gitignore | Missing |
| Contact/GitHub env vars | Placeholders |
| ACB staff ingestion | Deferred (no stable id on source) |
| ACB player enrichment (profile pages) | Deferred (profiles are separate from box-score payload) |

---

## Phase 1 — Housekeeping (< 1 hour)

Quick fixes that unblock everything else and reduce noise.

### 1.1 Gitignore `tsconfig.tsbuildinfo`
`frontend/tsconfig.tsbuildinfo` regenerates on every typecheck and keeps
appearing as a stale diff. Add to `.gitignore`.

### 1.2 Set real env vars
In `frontend/.env.local` (never committed):
```
NEXT_PUBLIC_CONTACT_EMAIL=<real address>
NEXT_PUBLIC_GITHUB_URL=https://github.com/<org>/basquetestads
```
Document the vars in a `frontend/.env.example` file (committed).

### 1.3 Backend `.env.example`
Mirror `backend/.env` structure as `backend/.env.example` with placeholder
values so new contributors know what to set.

---

## Phase 2 — Data backfill (medium effort, high value)

This is the single highest-value step: it turns all the polished UI into pages
with real data.

### 2.1 ACB current season
```bash
python manage.py ingest_season --connector acb --season current
```
`resolve_current_edition_id()` already handles finding the live season. Spot-
check a few team/player pages after.

### 2.2 ACB historical backfill (5 seasons)
```bash
python manage.py backfill --connector acb --seasons 5
```
~1 500 games × ~2 req each = ~3 000 requests at ≥2 s/req ≈ 100 min. Run in the
Celery worker; monitor via `IngestionRun` admin.

### 2.3 FEB current seasons (primera + segunda)
```bash
python manage.py ingest_season --connector feb-primera --season 2025
python manage.py ingest_season --connector feb-segunda --season 2025
```

### 2.4 FEB historical backfill (5 seasons, 2020–2024)
```bash
python manage.py backfill --connector feb-primera --seasons 5
python manage.py backfill --connector feb-segunda --seasons 5
```
FEB goes back to 2018; realistic target is 5 seasons per tier.

### 2.5 Player enrichment (FEB profile pages)
After box scores are ingested, enrich player bios and team branding:
```bash
python manage.py enrich_profiles --connector feb-primera --season 2025
python manage.py enrich_profiles --connector feb-segunda --season 2025
```

### 2.6 Player photos (ACB)
ACB player headshots are a free by-product of the box-score fetch (already
implemented in `ingest_acb_season`). Verify `INGEST_STORE_MEDIA=True` in
`backend/.env` and confirm photos appear on player pages after the backfill.

---

## Phase 3 — Celery Beat verification & hardening (small effort)

The Beat tasks are registered in `config/settings.py` but were only unit-tested
offline.

### 3.1 Verify Beat schedule runs end-to-end
Start `docker compose up` with all services and confirm:
- `ingest_current_acb_season` fires at 05:30 and produces a green `IngestionRun`
- `enrich_current_feb_profiles_weekly` fires Monday 06:00
- No duplicate runs (idempotency check)

### 3.2 Add FEB ingest tasks to Beat
The nightly FEB tasks are not yet in `CELERY_BEAT_SCHEDULE`. Add them:
```python
"ingest-current-feb-primera-nightly": {
    "task": "ingestion.tasks.run_ingest_season",
    "schedule": crontab(hour=4, minute=0),
    "args": ("feb-primera", "current"),
},
"ingest-current-feb-segunda-nightly": {
    "task": "ingestion.tasks.run_ingest_season",
    "schedule": crontab(hour=4, minute=30),
    "args": ("feb-segunda", "current"),
},
```
FEB seasons use start-year strings; "current" needs a resolver equivalent to
`resolve_current_edition_id` for ACB. Add `resolve_current_feb_season(connector_id)`
in `ingestion/catalog.py`.

### 3.3 IngestionRun admin polish
- Add `records_processed`, `status`, `error_log` to the admin list view.
- Add a "Re-run" admin action that re-enqueues a failed run.

---

## Phase 4 — Frontend UX improvements (medium effort)

With real data flowing, some UI gaps become visible.

### 4.1 Liga page — game list pagination
The games list currently loads all games for a season at once. Add
server-side pagination (`?page=N`) or an infinite-scroll with a "Cargar más"
button. Limit the initial load to the 20 most recent finished games.

### 4.2 Liga page — standings visual polish
Add win/loss colour coding (green/red) and highlight the promotion/relegation
cutoff lines (top 2 up, bottom 4 down for Primera FEB).

### 4.3 Jugadores page — career timeline
The `CareerEntry` model and API are in place but the player page only shows
`RosterEntry` rows for in-system seasons. Render the full `careerTimeline` from
`PersonDetail` as a vertical timeline (season · club · league).

### 4.4 Comparar page — search UX
The current picker loads all players in a single dropdown. Replace with a
debounced search input that calls `GET /api/v1/players/?search=<q>` (needs a
`SearchFilter` on the backend viewset) so the list stays manageable with hundreds
of players.

### 4.5 Lideres page — season/league filter persistence in URL
Already implemented via query params. Verify Back-button behaviour and add a
"Temporada actual" shortcut link.

### 4.6 Equipos page — team season history chart
The `getTeamStatsHistory` data already exists. Render an interactive line chart
(Recharts `LineChart`) showing PTS, REB, ASI per season for the team. Currently
this is wired to `TrendLine` components; upgrade to a multi-series `LineChart`
with a legend.

---

## Phase 5 — Search & discovery (medium effort)

### 5.1 Global search endpoint
Add a `GET /api/v1/search/?q=<query>` endpoint that returns top matches across
teams, players, and games (DRF `SearchFilter` on three querysets, merged and
ranked by type). Max 5 results per type.

### 5.2 Global search UI
A `<SearchBar>` component in the NavBar (client component, `useRouter`-driven)
that opens a results dropdown. Keyboard-navigable (↑↓ arrows + Enter). Appears on
`md+` screens inline; collapses to a search icon on mobile.

---

## Phase 6 — Production readiness (before public launch)

### 6.1 Django production settings
- `DEBUG=False`, `ALLOWED_HOSTS`, `SECRET_KEY` from env.
- `django-storages` + S3 (or local + Nginx) for `MEDIA_ROOT` serving.
- `whitenoise` for `STATIC_ROOT`.
- `CONN_MAX_AGE` for DB connection pooling.

### 6.2 Dockerfile optimisation
- Multi-stage build for the frontend (builder → slim runner).
- Pin exact base image digests.
- Add `HEALTHCHECK` instructions to all services.

### 6.3 CI pipeline (GitHub Actions)
Currently: path-filtered lint + test jobs. Extend to:
- **Backend:** `pytest` + `ruff` + `mypy --strict` on `backend/**` changes.
- **Frontend:** `tsc --noEmit` + `next lint` + `next build` on `frontend/**`.
- **Coverage gate:** fail if `pytest --cov` drops below 80%.

### 6.4 `acerca-de` page — real content
Replace placeholder text with actual project description, data sources section,
methodology note (what advanced metrics mean and how they're computed), and the
legal/rights section (already partially in the footer).

---

## Sequencing / priority matrix

| Priority | Phase | Effort | Value |
|---|---|---|---|
| **P0** | 1 — Housekeeping | Trivial | Keeps repo clean |
| **P0** | 2.1–2.3 — Current season backfill | Small | Real data in every page |
| **P1** | 2.4–2.6 — Historical + enrichment | Medium | Full player/team profiles |
| **P1** | 3 — Beat verification | Small | App self-updates |
| **P2** | 4 — Frontend UX | Medium | Polished experience |
| **P2** | 5 — Search | Medium | Discoverability |
| **P3** | 6 — Production | Medium | Public launch readiness |

---

## Starting point on this branch

Begin with **Phase 1** (housekeeping) — all three tasks commit cleanly and take
< 30 min — then move immediately into **Phase 2.1** (ACB current season ingest)
so the branch has tangible data-driven progress to show.
