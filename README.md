# Cancha (Basquet Stats)

Open, non-commercial web app for visualizing **advanced basketball statistics**
for the Spanish leagues: **ACB**, **LEB Oro (Primera FEB)** and
**LEB Plata (Segunda FEB)**. Focus on historical, post-game analytics — not
live/in-game data.

Full technical specification: [`docs/especificacion-tecnica-baloncesto-stats.md`](docs/especificacion-tecnica-baloncesto-stats.md).

## Features

### League pages (`/ligas/[liga]`)
- Season selector (URL-driven via `?season=`)
- **Standings table** — W/L record, points for/against, point difference, team
  logos
- **Finished games list** — scores, dates, links to individual box scores

### Team pages (`/equipos/[equipo]`)
- Header with team logo, city, arena, founded year and official website
- **Three radar charts** normalized to league-average = 100 (larger polygon =
  better outcome for all axes, including inverted ones like DRtg and turnovers):
  - *Medias por partido* — PTS, T2A, T3A, TLA, RO, RD, REB, ASI, PER, ROB, TAP, FP
  - *Por 100 posesiones* — same box stats on a possession-adjusted basis
  - *Estadística avanzada* — ORtg, DRtg, Pace, TS%, EFG%, 3-rate, TOV%, ORB%,
    DRB%, STL%, BLK%
- **Season summary table** — PTS / REB / ASI / ROB / TAP / PER / ORtg / DRtg /
  TS% vs league average with colour-coded diff column
- **Season history table** — one row per season, newest first, colour-coded vs
  league average with tooltip showing the average value; clicking a season
  switches the radar to that year
- **Roster cards** — responsive grid (2–6 columns), sorted by jersey number then
  name; each card shows the player photo, jersey number badge, position + height,
  and per-season PTS / REB / ASI averages pulled from the aggregate

### Player pages (`/jugadores/[jugador]`)
- Header with photo, position, nationality, inline bio facts (origin, birth date,
  height, weight) and quick-stat chips (PJ / MIN / PTS / REB / ASI / PER) for
  the most recent season at a glance
- **Career trajectory** — club + league badge per season, linked to team pages
- **Per-season stats table** — PJ / MIN / PTS / REB / ASI / TS% / eFG% / USO% /
  PER with latest season highlighted
- **Advanced-metrics radar** — up to 3 most recent seasons overlaid as separate
  series for career-evolution comparison; axes use correct relative scaling
  (percentages as %, PER scaled to PER 35 = 100)
- **Trend sparklines** — compact PTS / REB / ASI trend lines for the full career

### Leaders (`/lideres`)
- Filterable by stat (PTS / REB / ASI / PER / TS% / USO%), league and season
- Player photo with initials fallback + link to player page
- Team logo and short name with link to team page

### Player comparator (`/comparar`)
- Pick up to 4 players from a searchable list
- **Grouped bar chart** (StatBarComparison) — PTS / REB / ASI / MIN side by side
- **Advanced-metrics radar** — overlaid profiles for all selected players

### Box scores (`/partidos/[partido]`)
- Match header with both club logos and final score
- Per-team player lines with all box-score columns

### Other
- `/glosario` — glossary of all advanced metrics
- `/acerca-de` — project credits and data sources

---

## Architecture (monorepo)

```
backend/    Django + Django REST Framework + Celery + Celery Beat
frontend/   Next.js + React + TypeScript + TailwindCSS + Recharts
```

Backend and frontend are decoupled services communicating over REST/JSON. The
backend exposes **camelCase** JSON (via `djangorestframework-camel-case`) to
match the frontend TypeScript naming. Ingestion runs asynchronously via Celery
workers scheduled with Celery Beat — there is no live/real-time data path by
design.

### Backend apps

| App | Responsibility |
|---|---|
| `connectors` | Source adapters (ACB, FEB) implementing the `SourceConnector` interface |
| `ingestion` | `DataSource` / `IngestionRun` audit models and Celery ETL tasks |
| `stats` | Advanced metrics engine (TS%, eFG%, Usage Rate, PER, ORtg, DRtg, Pace …) |
| `teams` | `League`, `Season`, `Team`, `TeamSeason` |
| `players` | `Person`, `RosterEntry`, `StaffEntry`, `PlayerGameStats`, `PlayerSeasonAggregate` |
| `games` | `Game`, `TeamGameStats` |
| `api` | Versioned public REST API mounted at `/api/v1/` |

### Frontend components

| Component | Description |
|---|---|
| `TeamRadar` | Radar chart normalized to league-average = 100; inverted axes supported |
| `AdvancedRadar` | Player advanced-metric radar; supports multiple overlaid seasons |
| `TrendLine` | Season-over-season metric trend; `compact` prop for mini sparklines |
| `StatBarComparison` | Grouped bar chart for side-by-side player comparison |
| `MediaImage` | Renders stored media assets (logos, photos) with initials fallback; handles Docker-internal vs browser URL resolution |
| `SeasonSelector` | URL-driven season picker shared across league, team pages |

---

## Local development

Docker Compose is the standard environment. Services: `db` (PostgreSQL),
`redis`, `backend` (Django), `worker` (Celery worker + Beat), `frontend`
(Next.js).

```bash
# 1. Create local env files from the templates
cp backend/.env.example backend/.env
cp frontend/.env.local.example frontend/.env.local

# 2. Start the stack
docker compose up --build

# 3. Apply migrations (first run)
docker compose exec backend python manage.py migrate
docker compose exec backend python manage.py createsuperuser

# 4. Load deterministic demo data (fictional leagues/teams/players/games)
docker compose exec backend python manage.py seed_demo_data
```

- Backend API: http://localhost:8000/api/v1/ (health: `/api/v1/health/`)
- Django admin: http://localhost:8000/admin/
- Frontend: http://localhost:3000

`seed_demo_data` exercises the full pipeline (Pydantic validate → persist →
recompute aggregates) with synthetic data, so the API and frontend work
end-to-end without scraping. It is idempotent and deterministic.

### Makefile shortcuts (run from repo root)

```bash
make up            # docker compose up --build
make down          # docker compose down
make logs          # tail all service logs
make logs-backend  # tail only the backend
make logs-frontend # tail only the frontend
make shell-backend # bash shell in the backend container
make migrate       # run migrations
make seed          # seed_demo_data
make test          # pytest in the backend container
```

The pattern `make logs-<service>`, `make shell-<service>`, `make restart-<service>` works for any Compose service name.

### Key API endpoints (`/api/v1`)

| Endpoint | Description |
|---|---|
| `GET /leagues/` | All covered leagues |
| `GET /seasons/?league=` | Seasons for a league |
| `GET /seasons/{id}/standings/` | W/L standings |
| `GET /teams/{slug}/` | Team detail |
| `GET /teams/{slug}/roster/?season=` | Roster with per-season stat averages |
| `GET /teams/{slug}/season-stats/?season=` | Per-game, per-100, advanced team stats + league avg |
| `GET /teams/{slug}/stats-history/` | Season-by-season history, newest first |
| `GET /players/{slug}/` | Player bio + career |
| `GET /players/{slug}/stats/` | Per-season aggregates (basic + advanced) |
| `GET /players/compare/?ids=&season=` | Multi-player comparison |
| `GET /games/{id}/boxscore/` | Full box score |
| `GET /stats/leaders/?stat=&league=&season=` | Statistical leaders |

### Running checks without Docker

```bash
# Backend
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python manage.py check
python manage.py makemigrations
pytest

# Frontend
cd frontend
npm install
npm run lint
npm run typecheck
```

## License

Open source under the [MIT License](LICENSE). Fan project, not officially
affiliated with the ACB or the FEB.
