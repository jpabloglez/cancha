# Connector Implementation Plan — Real ACB / FEB Data

**Status:** Draft for review (do not start coding until approved)
**Date:** 2026-06-21
**Scope:** Replace the synthetic seed pipeline with real, post-game data ingestion
from ACB.com and FEB.es, reusing the existing
`schemas → persistence → aggregation` pipeline.

---

## 1. Context & goal

The backend already has a complete, tested ingestion pipeline that today is fed
only by `seed_demo_data`. The connector work makes that pipeline real: fetch
finished games and box scores from the official sites, normalize them into the
existing Pydantic schemas, and persist them idempotently.

**In scope:** ACB (Liga ACB), FEB Primera (ex-LEB Oro), FEB Segunda (ex-LEB
Plata); current season + historical backfill (5–10 seasons, spec §1.2/§11);
scheduling via Celery Beat; resilience/observability.

**Out of scope (unchanged):** live/in-game data, betting, women's/lower
divisions (Fase 4), shot charts (no public coordinate data).

---

## 2. What already exists (reuse, do not rebuild)

| Layer | File | Reuse as-is? |
|---|---|---|
| Connector interface (Adapter) | `backend/connectors/base.py` — `SourceConnector`, `RawSourcePayload` | Yes — implement the 4 abstract `fetch_*` methods |
| Rate-limited HTTP client | `backend/connectors/http.py` — `RateLimitedClient` | Yes |
| Connector registry | `backend/connectors/registry.py` — `get_connector`, ids `acb`/`feb-primera`/`feb-segunda` | Yes |
| Connector scaffolds | `backend/connectors/{acb,feb}.py` | Fill in (currently raise `NotImplementedError`) |
| Normalized schemas (Pydantic) | `backend/ingestion/schemas.py` — `Normalized{Team,Person,RosterEntry,Game,PlayerBoxScore,TeamBoxScore}`, `ExternalRef` | Yes — connectors emit these |
| Persistence (idempotent upserts) | `backend/ingestion/persistence.py` — `upsert_{league,season,team,team_season,person,roster_entry,game_with_boxscore}` | Yes |
| Aggregation | `backend/stats/aggregation.py` — `recompute_player_season_aggregates` | Yes |
| Audit / orchestration | `backend/ingestion/tasks.py` — `ingest_season`, `recompute_season_aggregates`; `backend/ingestion/models.py` — `DataSource`, `IngestionRun` | Flesh out `ingest_season` |
| Idempotency keys | `source` + `external_id` on `Team`, `Person`, `Game` (unique together) | Yes — connectors set `source` = connector id, `external_id` = source's own id |

**Key gap to fill:** there is no *parse/normalize* layer yet. The seed command
builds `Normalized*` objects by hand; connectors instead need parsers that turn
raw HTML (`RawSourcePayload.data`) into the same `Normalized*` objects.

---

## 3. Compliance gate (BLOCKING — must clear before any fetch)

Per spec §10. Findings so far (2026-06-21):

- **ACB.com `/robots.txt`:** a `User-agent: *` group with `Allow: /`, no
  `Disallow`, no `Crawl-delay`; several AI-bot agents are named separately.
- **FEB.es `/robots.txt`:** only a `Mediapartners-Google` group with `Allow: /`;
  no `*` restrictions (default-permissive).

Both appear to permit general crawling, but before coding we must:

- [ ] Re-read each `robots.txt` carefully, honoring the **per-user-agent
      grouping** (which `Allow`/`Disallow` lines apply to `*` vs named agents).
      Record the snapshot + date in this doc.
- [ ] Read each site's **Terms of Use** (separate from robots.txt) and confirm
      non-commercial, attributed, rate-limited scraping is acceptable.
- [ ] Decide a descriptive **User-Agent** string identifying the project as a
      non-commercial fan project with contact info (already drafted in
      `connectors/http.py`).
- [ ] Confirm **attribution** UI exists (footer/"Acerca de" already credit
      ACB.com/FEB.es and state non-affiliation — verify wording).
- [ ] Set conservative **rate limits** (≥2 s between requests per source,
      exponential backoff on errors) and prefer off-peak scheduling.

**Gate:** do not implement fetch logic until this checklist is signed off.

---

## 4. Phase 0 — Discovery spike (1 source, 1 team, 1 season)

Goal: learn the *actual* page structure before committing parser code (spec §13
step 2). Throwaway notebook/script, no production code.

For **each** source determine and document:

- [ ] URL patterns for: season team list, team roster, season schedule/results
      (finished games only), and a game box score. Capture example URLs +
      the source's own ids for season/team/game/player.
- [ ] **Rendering mode:** is the data in the server-rendered HTML (→
      `httpx` + `BeautifulSoup`/`lxml`) or injected by JavaScript (→
      `Playwright`)? FEB pages are ASP.NET `.aspx` (likely server-rendered);
      verify ACB.
- [ ] Whether any **JSON/XHR endpoint** backs the page (cheaper + more stable
      than HTML scraping — prefer it if present and permitted).
- [ ] Historical availability: how far back do box scores exist, and do older
      seasons use a different layout? (spec §12.2 risk).
- [ ] The LEB Oro/Plata → Primera/Segunda FEB naming across seasons.

**Deliverable:** a short findings note appended to this doc, plus 3–5 saved HTML
samples per source committed as test fixtures (§9).

### Phase 0 findings — FEB (recorded 2026-06-21)

Data lives on **`baloncestoenvivo.feb.es`** (Genius/FEB live platform),
**server-rendered HTML** — `httpx` + `BeautifulSoup`/`lxml`, **no Playwright**.

- Competition id `g`: **1 = Primera FEB**, **2 = Segunda FEB** (confirmed). Season
  param `t` = season start year (`t=2024` → 2024/2025). Slug `nm=primerafeb` /
  `nm=segundafeb`.
- **Results/calendar:** `…/resultados.aspx?g=<g>&t=<t>&nm=<nm>` — links each game to
  the box score.
- **Standings:** `…/clasificacion.aspx?g=<g>&t=<t>&nm=<nm>`.
- **Box score (acta):** `…/Partido.aspx?p=<game_id>` (e.g. `p=2471977`). Self-
  contained: both teams, final score, and two player tables.
- **Identity:** player/team links are `…/Jugador.aspx?i=<team_id>&c=<player_id>` →
  person `external_id = c`, team `external_id = i`. Game `external_id = p`.
- **Box-score columns (in order):** `MIN, PT, T2, T3, TC, TL, RO, RD, RT, AS, BR,
  BP, TF, TC, MT, FC, FR, VA, +/-`. Mapping to our schema: `TC`(1st)=field goals
  made/att, `T3`=threes, `TL`=free throws, `RO/RD`=off/def rebounds, `AS`=assists,
  `BR`=steals, `BP`=turnovers, `TF`=blocks, `FC`=fouls, `PT`=points, `MIN`="mm:ss".
  Shooting cells are `made/att pct%` (e.g. `10/15 66,7%`). **Gotcha:** `TC` appears
  twice (field goals + tapones-contra) → map headers by **first occurrence**.

**Validated against live raw HTML (2026-06-21):** the FEB connector + parser were
run against the real site and confirmed working:

- Legacy `.aspx` URLs **301-redirect** to clean paths `/<section>/<nm>/<g>/<t>`
  (the client now follows redirects). Box score: `/partido/<id>`.
- **Full-season enumeration uses the `calendario` page**, which lists every game
  at once (306 games for Primera FEB 2024/2025) — avoiding the per-jornada
  ASP.NET postback the `resultados` page would require.
- The box-score table has a **two-row header** (group row + detail row starting
  `I, D, Jugador, …`); the column index is taken from the detail row. Shooting
  cells render `made/att <span>pct%</span>` (read with a separator). The team
  totals row is `class="row-total"`. The parser handles all of this; verified on
  real games (e.g. HLA ALICANTE 64 - REAL VALLADOLID 73, 20 player lines).
- Season dropdown exposes `t` back to 2018, so the 5-season backfill is feasible.

The golden-test fixture mirrors this real structure. A full-season production run
(306 box-score fetches) was **not** executed here — only spot-checks — to stay
polite to the source.

### Phase 0 findings — ACB (recorded 2026-06-21)

ACB.com is now a **Next.js / React, JavaScript-rendered** site → **Playwright is
required** (confirms decision #4). Data/box scores live on **`live.acb.com`**.

- Results: `acb.com/es/liga/partidos` (filter `?editionId=<season>`; current
  `editionId=90`). Standings: `/es/liga/clasificacion`.
- **Box score:** `live.acb.com/es/partidos/<match-slug-id>/estadisticas`
  (e.g. `valencia-basket-vs-barca-105370`; trailing number = match id).
- Player: `/es/liga/jugadores/<slug-id>` (e.g. `jean-montero-30000514`);
  team slug-ids like `valencia-basket-13`.

**Status:** the Playwright fetch path (`connectors/browser.py`) and
`AcbConnector` URL builders are implemented; the **ACB parser**
(`connectors/parsers/acb.py`) is the remaining piece and needs captured rendered
HTML (or, preferably, the JSON/`__NEXT_DATA__` API behind the Next.js app) before
it can be written. ACB ingestion is gated until then (`ingest_season` raises for
non-FEB connectors).

### Phase 0 re-evaluation — ACB parser feasibility (recorded 2026-06-24)

Fetched live (robots: both `acb.com` and `live.acb.com` are `User-agent: *`
`Allow: /`) and saved as fixtures (`connectors/tests/fixtures/acb_boxscore.html`,
`acb_partidos.html`). **The earlier "Playwright required" verdict is only partly
true** — the box score is *mixed* SSR:

- ✅ **Player stat tables are server-rendered** (real data in the raw HTML, no JS):
  header `Jugador, Min, Pts, T2, T2%, T3, T3%, TL, …, RO, RD, RT, As, Pér, Rec,
  Tap, …, Fp, Fr, +/-, Val`, plus per-team `Equipo` and **`Totales`** rows (team
  totals → also the final score). Each player row links
  `…/liga/jugadores/<slug>-<id>` ⇒ stable player `external_id`. Field goals must
  be summed from **T2 + T3** (ACB splits them; our schema wants total FG).
  Page renders each team table **twice** (responsive) → dedupe by player-id set.
- ✅ **Results page** (`acb.com/es/liga/partidos`) is SSR enough to list game
  links `live.acb.com/partidos/<home>-vs-<away>-<id>/…` **with the final score in
  the link text** ("112 - 113"); teams/home-away come from the slug.
- ❌ **Match header is JS-hydrated** — in raw HTML the team names are `XXXXX`, the
  **date is `00/00/0000`**, score `00`, tabs `Loading…`. So team *display names*
  (recoverable from logo `alt` + slug) are OK, but the **game date is the real
  gap**: it is not in either page's SSR.

**Verdict / recommended approach (no full Playwright needed for stats):**
1. Parse player + team-totals stats and the game list with `httpx` +
   BeautifulSoup, exactly like FEB — the bulk of the work is unblocked.
2. Resolve the **date** (the one missing field) by one of: (a) a *single*
   Playwright render of the box-score header per game, (b) reading the Next.js
   RSC payload (`self.__next_f.push(...)` chunks carry it), or (c) an ACB
   JSON/XHR endpoint if one is found. Recommend a short spike on (b)/(c) before
   committing to (a), since avoiding Playwright keeps the worker image light.
3. Team `external_id`: no `/equipos` link in the box score; derive a stable slug
   from the match slug (`valencia-basket`, `barca`) for v1 and document the
   cross-season club-unification caveat (same as FEB).

**Net:** ACB box-score ingestion is **feasible without Playwright for everything
except the game date**, which needs a small targeted fetch — a meaningfully
smaller and lighter task than the original "render every page" assumption.

### Phase 1 — ACB parser implemented (recorded 2026-06-27)

Spike option (b) **succeeded**: the game date *is* in the SSR document, inside
the Next.js RSC payload. `self.__next_f.push([n,"…"])` chunks decode (per-chunk
`json.loads`, UTF-8-safe — `unicode_escape` corrupts "Barça") into a stream
carrying an **`initialMatchHeader`** JSON object with `start`
("2026-06-18T18:00:00Z"), `status` ("FINALIZED"), `currentHomeScore` /
`currentAwayScore`, and per-team metadata including a **stable `clubId`** (13 =
Valencia, 2 = Barça) — better than a slug-derived id, so the cross-season
club-unification caveat is **resolved** for ACB. **No Playwright is needed at
all.**

Done:
- `connectors/parsers/acb.py` (`ACB_PARSER_VERSION = "acb-2026.06"`):
  `parse_game_ids(html)` and `parse_box_score(html, *, source, game_external_id)`
  → `ParsedGame`. Metadata from the RSC `initialMatchHeader`; player/team-totals
  stat lines from the SSR tables (FG = T2 + T3); two responsive table copies
  de-duplicated by first-player id; the two tables mapped to home/away by
  matching each `Totales` points to the header score. Non-`FINALIZED` headers
  raise `ParserError` (no live ingestion).
- `connectors/tests/test_acb_parser.py`: 5 golden tests against the real
  fixtures (header/date/score/clubId, team-totals reconciliation, both rosters
  with stable ids, game-id listing, non-finalized rejection). Green, no network.
- `connectors/acb.py` rewritten to fetch via the **httpx** rate-limited,
  DB-cached path (`fetch_or_cache`), dropping the Playwright `_render`; registry
  uses `build_acb_connector`.

### Phase 2 — ACB switched to the JSON API + ingestion wired (recorded 2026-06-27)

Discovery while wiring revealed the SSR results page **cannot enumerate a full
season** — it lists only ~4 featured games (the rest is loaded by XHR per
round). The site's own frontend reads a **public JSON API** at `api2.acb.com`,
authenticated with a constant `X-APIKEY` header shipped to every browser. Per
user decision (2026-06-27) the ACB connector was **switched to this JSON API**
(it is far richer and supports full-season + full-history enumeration), treating
the key as a public client constant, used politely (rate-limited, same UA),
documented here with non-affiliation. The earlier HTML box-score parser and its
`.html` fixtures were removed.

Endpoints (discovered in the Next.js JS bundles; base host found as
`baseUrl:"https://api2.acb.com"`, header `X-APIKEY:0dd94928-…`):
- `GET /api/seasondata/Competition/matches?competitionId=1&editionId=<e>[&roundId=<r>&isRoundSelected=true]`
  — schedule. `availableFilters.seasons` = full editionId↔year map (back to
  1983/84; **editionId = seasonStartYear − 1935**, resolved at runtime, not
  hardcoded); `availableFilters.rounds` = round list to iterate a whole season;
  `matches[]` carry id/scores/`startDateTime`/`matchStatus` + `teams[]` map
  team.id→stable `clubId`. Omitting `editionId` returns the **current** edition
  (`selectedFilters.season`) — used to resolve the live season across rollovers
  (`editionId=current` 400s). competitionId 1=Liga Endesa, 2=Copa, 3=Supercopa,
  10=Minicopa.
- `GET /api/matchdata/Result/boxscores?matchId=<id>` — one finished game.
  `teamBoxscores[].statsByPeriods` quarter 0 = whole game; its `stats.total`
  node is the real team total (the `team` node is team-credited stats only);
  `stats.players[]` are per-player lines. FG = `twoPointers + threePointers`.
  Also exposes (not yet ingested) **player headshot photos**, `gameRole`
  positions, shirt numbers, head/assistant **coaches**, arena, attendance,
  referees.

Implemented:
- `connectors/parsers/acb.py` (rewritten, `ACB_PARSER_VERSION="acb-json-2026.06"`):
  `parse_matches(payload) -> SeasonMatches` (teams, finished-game `MatchHeader`s,
  round_ids, seasons map, current_edition_id) and
  `parse_boxscore(payload, *, header) -> ParsedGame`.
- `connectors/acb.py`: `AcbConnector` over `api2.acb.com` via the rate-limited,
  DB-cached client (`RateLimitedClient(extra_headers={"X-APIKEY":…})`); methods
  `fetch_completed_games`/`fetch_round_matches`/`fetch_current_schedule`/
  `fetch_box_score`; `build_acb_connector` in the registry.
- `ingestion/catalog.py`: `ensure_acb_league_and_season` (Liga ACB, slug "acb",
  level 1). `ingestion/acb_ingest.py`: `ingest_acb_season(edition_id)` (resolve
  start-year from the schedule → iterate rounds → fetch box scores → persist →
  rebuild rosters → recompute aggregates) + `resolve_current_edition_id`.
- `ingestion/tasks.py`: `run_ingest_season` now dispatches ACB; new nightly Beat
  task `ingest_current_acb_season` (`config/settings.py`, 05:30). `ingest_season`
  management command accepts `--connector acb --season <editionId>`.
- Tests: `connectors/tests/test_acb_parser.py` (JSON golden, 5) +
  `ingestion/tests/test_acb_ingest.py` (offline full-graph + idempotency, 2).
  Fixtures `acb_api_matches.json`, `acb_api_boxscore.json`. 49 backend tests
  pass; ruff clean. **Live-verified end to end**: edition 90 → round 1 (9
  finished games) → real box score (Unicaja 86–68 Surne Bilbao, 24 lines, team
  totals reconcile exactly).

**Player enrichment DONE (2026-06-27):** since ACB ships each player's headshot
URL + `gameRole` position inside the box-score payload already fetched for
ingestion, enrichment is a free by-product (no extra requests, unlike FEB's
separate profile pages). `parse_player_profiles(payload) ->
list[NormalizedPersonProfile]` (position via `_POSITION_MAP`, photo
`NormalizedMediaRef` to `static.acb.com`, `display_name` = nickname) runs inline
in `ingest_acb_season`: profiles are de-duplicated per player across the season,
persisted via `upsert_person_profile`, and headshots downloaded through the
existing gated `download_media_asset` (`INGEST_STORE_MEDIA` + `store_media`
flag). `IngestResult` gained `players_enriched` / `photos_stored`. Live-verified:
Brancou Badio → position SG, headshot stored (154 KB JPEG, `is_available`).
Tests: `test_parse_player_profiles` + `test_ingest_acb_season_enriches_*`
(offline, `store_media=False`). 51 backend tests pass.

**Remaining (follow-ups):** ACB **coaches** are bare name strings in the boxscore
(no stable id), so staff ingestion is deferred until a keyed source is found
(would otherwise need synthetic name-slug ids). A first real full-season ACB
backfill is still pending (heavy — ~300 games/edition; gate on politeness + ToS
re-check) — wired and one command away: `ingest_season --connector acb --season
<editionId>`.

---

## 5. Target architecture (how connectors plug in)

```
Celery Beat ─▶ ingest_season(connector_id, season_external_id)
                  │
                  ├─ resolve League/Season via ingestion/catalog.py
                  ├─ connector.fetch_teams ──▶ parse ─▶ NormalizedTeam[]      ─▶ persistence.upsert_team / upsert_team_season
                  ├─ connector.fetch_roster ─▶ parse ─▶ NormalizedRosterEntry ─▶ persistence.upsert_person / upsert_roster_entry
                  ├─ connector.fetch_completed_games ─▶ parse ─▶ game refs
                  ├─ for each game: connector.fetch_box_score ─▶ parse ─▶ NormalizedGame ─▶ persistence.upsert_game_with_boxscore
                  └─ recompute_season_aggregates(season.pk)
              (wrapped in an IngestionRun audit record; retries w/ backoff)
```

### New modules to add

| Module | Responsibility |
|---|---|
| `connectors/parsers/acb.py`, `connectors/parsers/feb.py` | Pure functions: `RawSourcePayload` → `Normalized*` (no I/O, no DB). Unit-testable against saved HTML. |
| `connectors/cache.py` | Optional raw-response cache (filesystem keyed by URL hash, TTL) so parsers can be re-run without re-hitting the source (spec §3.4). |
| `ingestion/catalog.py` | Config mapping source season ids → our `League`/`Season` (names, slugs, levels, date ranges). The single place that encodes the LEB→FEB league identity. |
| `ingestion/management/commands/ingest_season.py` | Manual trigger: `ingest_season --connector acb --season 2024`. |
| `ingestion/management/commands/backfill.py` | Enqueue `ingest_season` tasks across N historical seasons, rate-limited. |

### Connector implementation contract

Each `fetch_*` method:
1. Builds the source URL (from `external_id`s).
2. Fetches through `RateLimitedClient` (optionally via `connectors/cache.py`).
3. Returns `RawSourcePayload(source_id, fetched_at, data=<raw html/json>)`.

Parsing lives in `connectors/parsers/*` (separation keeps fetch and parse
independently testable and lets us re-parse cached raw payloads).

---

## 6. Normalization & identity

- `source` field = connector id: `"acb"`, `"feb-primera"`, `"feb-segunda"`.
- `external_id` = the source's own stable id (from URL/markup) for team, person,
  game. Never a positional/derived value that can drift between runs.
- Reuse existing `ExternalRef(source, external_id)` throughout `Normalized*`.
- Parsers must **validate at the boundary** — `Normalized*` are strict
  (`extra="forbid"`); a structural change in the source raises immediately
  rather than silently persisting garbage (spec §3.3).
- `upsert_game_with_boxscore` already runs in a transaction, so a half-parsed
  game never lands in the DB.

**League identity (spec §3.1/§12.2):** `ingestion/catalog.py` maps both the
historical (LEB Oro/Plata) and current (Primera/Segunda FEB) names/URLs onto a
single `League` row per tier, keyed by slug (`primera-feb`, `segunda-feb`), so
pre- and post-2024-25 seasons don't create duplicate leagues.

---

## 7. Orchestration, scheduling & backfill

- **Flesh out `ingest_season`** (currently a scaffold) to run the Section 5 flow
  inside its existing `IngestionRun` + retry/backoff envelope.
- **Celery Beat:** register a periodic task (via `django_celery_beat` DB
  scheduler, already configured) to ingest the *current* season of each
  connector **post-jornada** (e.g. nightly), never during games (spec §3.3).
- **Backfill:** `backfill` command enqueues one `ingest_season` per
  (connector, season) for the last 5–10 seasons, spaced out and rate-limited.
  Idempotent, so it can resume after failures.
- **Aggregates:** `ingest_season` calls `recompute_season_aggregates(season.pk)`
  at the end (the hook already exists).

---

## 8. Resilience & observability (spec §3.4)

- [ ] Per-connector rate limit + exponential backoff (Celery `autoretry_for`
      already wired on `ingest_season`).
- [ ] Raw-response cache to re-parse without re-fetching when a parser bug is
      found.
- [ ] **Parser versioning:** each parser exposes a version; record
      `connector_id` + parser version on `IngestionRun`. On unexpected
      structure, fail loudly (controlled error + alert), never persist partial.
- [ ] `IngestionRun` already records start/finish/status/records/error_log —
      ensure every run path updates it.
- [ ] Structured logging + optional Sentry (SDK already in settings) for
      repeated failures (spec §3.4 monitoring).

---

## 9. Testing strategy

- **Golden parser tests:** commit real (small) HTML samples per source under
  `backend/connectors/tests/fixtures/`; assert parser output equals expected
  `Normalized*`. No network in CI.
- **Persistence/idempotency:** reuse the existing pattern in
  `ingestion/tests/test_persistence.py` — run a parsed fixture through
  `upsert_*` twice, assert no duplicates.
- **End-to-end (offline):** feed a fixture game through
  `parse → upsert_game_with_boxscore → recompute_player_season_aggregates` and
  assert metrics, mirroring `stats/tests/test_aggregation.py`.
- Keep `seed_demo_data` for local/dev/CI so the frontend never depends on live
  scraping.

---

## 10. Phased milestones

| Phase | Outcome |
|---|---|
| **0. Discovery** | URL/structure/rendering documented; robots.txt + ToS gate cleared; HTML fixtures saved. |
| **1. FEB Primera PoC** | One connector end-to-end for one team/season (likely server-rendered `.aspx`, simplest). Parser + fetch + catalog + golden tests. Validates the whole real path. |
| **2. FEB Segunda + ACB** | Generalize; add ACB (Playwright only if required by discovery). |
| **3. Current-season schedule** | Celery Beat nightly ingestion of the in-progress season per connector. |
| **4. Historical backfill** | `backfill` last 5–10 seasons per league; handle older-layout gaps; monitor `IngestionRun`s. |

Recommended starting point: **FEB Primera** (server-rendered, single shared
connector class already parameterized for both FEB tiers).

---

## 11. Risks & open questions

- **Source structure changes** break parsers — mitigated by parser versioning +
  controlled failures + golden tests (spec §12.2).
- **JS-rendered pages** would force Playwright (heavier worker image, slower).
  Discovery decides; prefer any JSON/XHR endpoint if available.
- **Historical gaps / layout drift** in older seasons — backfill must tolerate
  missing data and per-season parser variants.
- **ToS ambiguity** — if a site's terms disallow scraping, pause and evaluate an
  official API/data licence alternative (spec §10).
- **Player identity across seasons/sources** — relies on stable source ids; if a
  source lacks them, we need a dedup strategy (out of scope for v1; document).

---

## 12. Definition of done (v1)

- [ ] Compliance gate (§3) signed off and recorded.
- [ ] FEB Primera + Segunda + ACB connectors implement all four `fetch_*`
      methods with parsers emitting valid `Normalized*`.
- [ ] `ingest_season` runs the full flow under `IngestionRun`, idempotently.
- [ ] Current season ingested on a Celery Beat schedule.
- [ ] ≥5 seasons backfilled per league (best-effort given source availability).
- [ ] Golden parser tests + idempotency tests green in CI; no network in tests.
- [ ] Frontend shows real standings/players/leaders from ingested data.

---

## 13. Open decisions for reviewer

1. **Start source:** FEB Primera first (recommended) — agree?
2. **Backfill depth:** target 5 or 10 seasons for v1?
3. **Raw cache backend:** filesystem (simple) vs a DB model (queryable) — default
   to filesystem unless you want auditability.
4. **Playwright:** acceptable to add to the worker image if ACB needs it, or
   keep strictly `httpx`-only and defer any JS-rendered source?
