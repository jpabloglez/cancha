# Team & Player Enrichment Plan — Logos, Bios, Photos, Trajectory

**Status:** Reviewer decisions recorded 2026-06-24 (see §10); ready to plan Phase 0/1
**Date:** 2026-06-24 (updated 2026-06-24 with media/trajectory/cadence decisions)
**Scope:** Extend ingestion beyond box-score statistics to the *descriptive* data
that makes team and player pages rich: team branding (logo, colours, arena),
player biography (full name, birth place / origin, nationality, height/weight,
position, photo) and player **trajectory** (career history across clubs/seasons).
Reuses the existing `fetch → parse → Normalized* → persistence → aggregate`
pipeline; adds a parallel **profile** path and a **media** path alongside it.

---

## 0. Implementation status (updated 2026-06-24)

**Phase 1 foundation — DONE and verified (offline, seed-driven):**

- Data model: `Person` bio fields, `Team` branding fields, `MediaAsset`
  (with `taken_down` + `is_available`), `CareerEntry`; migrations applied.
- Pipeline: `Normalized{MediaRef,CareerEntry,PersonProfile,TeamProfile}` schemas;
  `upsert_{media_asset,team_profile,person_profile,career_entry}` with
  fill/refresh-never-clobber semantics; `INGEST_STORE_MEDIA` + `MEDIA_*` settings.
- Seed: `seed_demo_data` now emits deterministic branding, bio, photos
  (reference-only) and a 3-stint career timeline per player.
- API: `TeamSerializer`/`PersonSerializer` enriched; `MediaAssetSerializer`
  (null url ⇒ frontend fallback, no upstream hotlink); `PersonDetailSerializer`
  with career; `MediaImage` component + enriched player/team pages.
- Tests: 30 backend tests green (7 new enrichment tests); frontend `tsc` + lint clean.

**Phase 0 discovery — DONE (2026-06-24):** FEB player/team profile pages captured
live as fixtures, DOM/URL patterns + per-field availability + the logo asset host
(`imagenes.feb.es`, verified to serve `image/jpeg`) documented in §5.3. Only
player *photos* are unavailable on FEB (positions **are** available via `Puesto`).

**Phase 1 FEB enrichment coding — DONE and verified (2026-06-24):**

- Parsers `parse_player_profile` / `parse_team_profile` (`connectors/parsers/feb.py`,
  version `feb-2026.06p`) + golden tests against the real fixtures.
- Connector `fetch_player_profile` / `fetch_team_profile` (`/jugador/<i>/<c>`,
  `/equipo/<i>`); optional default methods on `SourceConnector`.
- `enrich_feb_season` orchestration (per-entity isolated) + `enrich_profiles`
  management command + `enrich_season` / weekly `enrich_current_feb_profiles`
  Celery tasks (audit-wrapped in `IngestionRun`).
- `download_media_asset` (+ Celery task): Option C storage, `INGEST_STORE_MEDIA`
  gate, checksum dedupe, content-type/size checks, honours `taken_down`.
- 41 backend tests green (parser golden + enrichment idempotency + media gating).
  **Live-validated:** HLA ALICANTE logo downloaded & stored, players enriched
  (e.g. nationality `ESTADOS UNIDOS`→`US`, position `Base`→`PG`).

**Attribution + takedown — DONE (2026-06-24):**

- Frontend: footer image-rights notice + takedown contact (`mailto`, from
  `NEXT_PUBLIC_CONTACT_EMAIL`); "Acerca de" rewritten with *Derechos de imagen* /
  *Retirada de contenido* sections (the old false "no logos" claim removed).
- Backend: `MediaAsset.take_down()` (deletes the binary, sets the flag, keeps
  provenance; blocks re-download) + Django-admin `MediaAsset` registration with a
  *take down* / *clear takedown* action and inline `taken_down` toggle.
- 42 backend tests green (added takedown-removes-binary test); FE tsc + lint clean.

**Weekly schedule — DONE (2026-06-24):** `enrich-current-feb-profiles-weekly`
added to `CELERY_BEAT_SCHEDULE` (`ingestion.tasks.enrich_current_feb_profiles`,
`crontab(hour=6, minute=0, day_of_week=1)` = Mon 06:00 Europe/Madrid, after the
nightly ingestion). DatabaseScheduler syncs it on Beat startup; task + schedule
verified registered.

**Remaining:**

- Set a real `NEXT_PUBLIC_CONTACT_EMAIL` (placeholder `derechos@basketstats.example`).
- A full-season enrichment run (currently only spot-checked, to stay polite) —
  gate on site ToS reading.
- ACB profiles (after the ACB box-score parser).

---

## 1. Context & goal

The box-score pipeline (`docs/connectors-implementation-plan.md`) now populates
real games, player stat lines and season aggregates for the FEB competitions.
What is still missing is everything that is *not* a number on an acta:

- **Teams** have only `name`, `short_name`, `city`, `founded_year`. No logo, no
  colours, no arena, no official/long name.
- **Persons** are created from box scores as `first_name` / `last_name` only
  (parsed from "SURNAME, NAME"); `birth_date`, `nationality` are left null, and
  there is no photo, origin, height/weight, primary position, or career history.
- **Trajectory** is implicit: a player's `RosterEntry` rows across our seasons
  give an in-league path, but not the full career (youth teams, foreign clubs,
  prior seasons we don't ingest) that a "trajectory" section needs.

**Goal:** add the data model, collection and ingestion needed to fill these gaps,
so `equipos/[equipo]` and `jugadores/[jugador]` pages can show a logo, a bio
card, a photo and a career timeline — sourced and attributed correctly.

**In scope:** FEB Primera/Segunda first (already-wired connector), then ACB.
**Out of scope (unchanged):** live data, betting, and — pending the §3 gate —
storing/serving copyrighted media without a clear basis.

---

## 2. Gap analysis — what we have vs. what we want

| Entity | Have today | Want to add | Likely source |
|---|---|---|---|
| `Team` | name, short_name, city, founded_year | official/long name, **logo**, primary/secondary colours, arena/pavilion, website | FEB/ACB team page + platform asset CDN |
| `Person` (bio) | first/last name, (null) birth_date, (null) nationality | **photo**, birth place (city + country = *origin*), confirmed nationality, height, weight, primary position, dominant hand | FEB/ACB player page |
| `RosterEntry` | jersey, position, height, weight (mostly null) | populate jersey/position/height/weight per team-season | team roster page |
| **Trajectory** | implicit via RosterEntry in our leagues | explicit career timeline incl. clubs/leagues we don't ingest | player page "trayectoria" / external |
| Staff | role only | photo, bio (lower priority) | team staff page |

---

## 3. Compliance & copyright gate (BLOCKING)

Logos and player photos are **copyrighted media**. `CLAUDE.md` / spec §"Out of
scope" cautions against *"reproducing copyrighted media (video, official
club/league logos, etc.) without rights."*

**Decision (2026-06-24): Option C — download & store**, following the
**dbasket.net precedent** for an open, non-commercial Spanish-basketball
project. dbasket.net states that ACB logos/images are made freely available to
specialist sites via **`mediacenter.acb.com`**, and that FEB and the clubs own
theirs; it stores and displays them in good faith with a contact-for-takedown
notice, and credits the leagues as the data source. We adopt the same posture:

- **Prefer official free-distribution channels** for assets where they exist —
  ACB's `mediacenter.acb.com` first; FEB / club official assets otherwise.
  Record the exact `source_url` per asset.
- **Store** the asset (`MediaAsset.file`, §4.2) with **per-asset
  `license`/`attribution`** and provenance URL.
- **Attribution + good-faith takedown:** the site footer / "Acerca de" credits
  ACB.com and FEB.es as image/data sources, states non-affiliation and
  non-commercial intent, and provides a **contact address for rights holders to
  request removal** (mirroring dbasket.net's wording). Add a flag/field to take
  a specific asset down on request.
- **Data attribution:** likewise credit ACB/FEB as the source of the underlying
  statistics in any public/press-facing context.

Before media collection starts:

- [ ] Re-confirm robots.txt / ToS coverage for the **player/team profile pages
      and the asset hosts** (`mediacenter.acb.com`, FEB/Genius CDN) — the
      box-score gate (connectors plan §3) covered acta/calendar/standings only.
- [ ] Implement the **attribution footer + takedown contact** before the first
      stored image is served publicly.
- [ ] Keep `INGEST_STORE_MEDIA` (§6.4) a setting so storage can be paused if a
      host's terms turn out to disallow it.

**Gate:** textual enrichment (bio, origin, height/weight, position, trajectory,
team metadata) proceeds once page-level ToS is confirmed. **Media storage
proceeds under Option C** once the attribution/takedown UI is in place and the
asset-host ToS is confirmed.

---

## 4. Data model changes

### 4.1 Field additions (textual — safe to implement first)

`teams.Team`
- `official_name: CharField(blank)` — full legal/sponsor name.
- `arena: CharField(blank)` — home pavilion name.
- `primary_color`, `secondary_color: CharField(7, blank)` — hex, for original
  crest/branding rendering (not the official logo).
- `website: URLField(blank)`.

`players.Person` (bio)
- `display_name: CharField(blank)` — source's preferred full name.
- `birth_city: CharField(blank)`, `birth_country: CharField(2, blank)` — *origin*.
- `height_cm`, `weight_kg: PositiveSmallIntegerField(null)` — current physicals.
  **Decision (2026-06-24): keep both** — `Person` holds the stable "latest known"
  value (for the bio card), `RosterEntry` keeps the per-season value (physicals
  can change year to year). Profile upserts refresh `Person`; box-score/roster
  ingestion fills `RosterEntry`.
- `primary_position: CharField(2, blank)`.
- `dominant_hand: CharField(1, blank)` — optional.
- Existing `birth_date` / `nationality` get populated (today they are null).

These are nullable/blank additions → backwards-compatible migrations; the
box-score path keeps working unchanged.

### 4.2 New model — `MediaAsset` (media, gated)

A single table for any external image, so policy/attribution lives in one place
and nothing is hardwired onto `Team`/`Person`.

```
class MediaAsset(models.Model):
    kind: CharField(choices=team_logo|player_photo|staff_photo)
    source: CharField           # connector id
    source_url: URLField        # provenance (always recorded)
    file: ImageField(null)      # populated ONLY if storage is approved (§3)
    license: CharField(blank)   # e.g. "©FEB — referenced, not stored"
    attribution: CharField(blank)
    checksum: CharField(blank)  # dedupe identical downloads
    fetched_at: DateTimeField
    UniqueConstraint(source, source_url)
```

`Team.logo` / `Person.photo` = nullable FK to `MediaAsset`. Add a
`taken_down: BooleanField(default=False)` so a specific asset can be hidden on a
rights-holder request (§3) without deleting its provenance record. The frontend
serves `file` when present and not taken down, else a fallback (initials avatar /
generated crest).

### 4.3 Media policy — DECIDED: Option C (download & store)

Chosen per §3 (dbasket.net precedent). Assets are downloaded from official
free-distribution channels (`mediacenter.acb.com` for ACB; FEB/club assets
otherwise), stored, attributed, and removable on request. Options A (reference-
only) and B (hotlink) are recorded for context but **not** adopted:

| Option | What we serve | Status |
|---|---|---|
| A. Reference-only | nothing stored; fallback only | not chosen |
| B. Hotlink source CDN | `<img src=source_url>` | not chosen |
| **C. Download & store (CHOSEN)** | served from our storage, attributed, takedown flag | adopted — offline-safe, full control; carries attribution + good-faith takedown duty |

### 4.4 New model — `CareerEntry` (trajectory)

`RosterEntry` only covers team-seasons inside *our* ingested leagues. A player's
trajectory includes clubs/leagues we don't model. Add a lightweight, mostly
free-text timeline:

```
class CareerEntry(models.Model):
    person: FK(Person, related_name="career")
    season_label: CharField        # "2019-2020" as printed by source
    club_name: CharField           # free text (may be a foreign/youth club)
    league_name: CharField(blank)
    team: FK(teams.Team, null)     # linked when it maps to a known club
    source, external_id: CharField # idempotency
    ordering by season_label desc
    UniqueConstraint(source, external_id) / (person, season_label, club_name)
```

When `club_name`/season match a known `TeamSeason`, link `team` so the timeline
can deep-link; otherwise it renders as plain text.

**Decision (2026-06-24): FEB/ACB sources only for now.** Trajectory is populated
solely from the FEB and ACB player-page season histories — no external career
sources (youth/foreign clubs absent from those pages are simply not shown, never
fabricated). Broader career sourcing is deferred.

---

## 5. Data sources & per-field availability

### 5.1 FEB (baloncestoenvivo.feb.es)

- **Player page** `…/Jugador.aspx?i=<team_id>&c=<player_id>` (clean path
  `/jugador/<…>`): typically exposes photo, full name, birth date, nationality,
  height, position, jersey, and a per-season stat history. The `c=<player_id>`
  is already captured as our `Person.external_id`, so profile fetches reuse it.
- **Team page** / roster: club crest, roster (jersey/position/height per player),
  coach. Crest/photos served from the Genius/FEB asset CDN.
- **Trajectory:** the player page's season history table is the primary
  trajectory source for FEB; clubs outside FEB may be absent.

### 5.2 ACB (live.acb.com — JS-rendered, Playwright)

- **Player** `/es/liga/jugadores/<slug-id>`: photo, bio, height/position, career.
- **Team** `…/equipos/<slug-id>`: crest, arena, roster.
- Blocked on the ACB parser (still a stub in the connectors plan); enrich ACB
  only after that lands. Prefer the `__NEXT_DATA__`/JSON payload over scraping
  rendered DOM for bio fields.

**Phase 0 (discovery) is required again** for the profile pages: capture 2–3 real
player pages + a team page per source as fixtures, confirm field locations and
rendering mode, and record findings in this doc — exactly as done for box scores.

### 5.3 Phase 0 findings — FEB profiles (recorded 2026-06-24)

Captured live and saved as fixtures
(`backend/connectors/tests/fixtures/feb_player_profile.html`,
`feb_team_profile.html`). Both pages are **server-rendered HTML** on
`baloncestoenvivo.feb.es` (no JS, no Playwright). Legacy `.aspx` URLs 301-redirect
to clean paths, same as the box-score pages.

**Player page** — `Jugador.aspx?i=<team_id>&c=<player_id>` → `/jugador/<i>/<c>`
(the `i`/`c` are already in our DB as `Team.external_id` / `Person.external_id`):
- **Name:** `div.nombre` → `"SURNAME(S), NAME"` (same comma convention as the
  box-score `_person()` parser — reuse it).
- **Bio:** repeated `div.nodo`, each with a `span.label` followed by the value:
  - `Fecha Nacimiento` → `"19/07/2001 Puente Genil (Córdoba)"` — **date + birth
    place** in one cell. Split: first token = `birth_date` (DD/MM/YYYY); the
    remainder = origin (`birth_city` + province in parens).
  - `Altura` → `"204 cm"`; `Peso` → `"- Kg"` (dash ⇒ missing); `Nacionalidad`
    → `"ESPAÑA"` (**country name in Spanish caps**, not an ISO code → needs a
    name→alpha-2 map; unknown ⇒ leave null).
- **No player photo.** FEB player pages carry only competition/team crests, never
  a portrait → `NormalizedPersonProfile.photo` is always `None` for FEB. (Player
  photos would only come from ACB later.)
- **Position:** the `Puesto` nodo **does** give the position in Spanish
  (`Base/Escolta/Alero/Ala-Pívot/Pívot`) → mapped to `PG/SG/SF/PF/C`
  (`primary_position`). *(Corrected after coding: an earlier Phase 0 note claimed
  FEB had no positions — it does.)* The jersey is a per-team number prefix in
  `div.jugador`, already covered by `RosterEntry`.
- **Trajectory:** `h1 "Trayectoria Nacional"` + table with header
  `Temp. | Categ. | Club [Equipo] | Licencia | Fecha alta | Fecha baja`. One row
  per stint: `season_label` from `Temp.` (`"19/20"` → normalise to `2019-2020`),
  `league_name` from `Categ.` (`LIGA EBA`, `LEB PLATA`, …), `club_name` from
  `Club [Equipo]`. The club cell often links `Equipo.aspx?i=<i>` ⇒ set
  `team_ref` (links to a known club when we have that `i`). Career entry
  `external_id = f"{player_c}:{season}:{i or club}"`.

**Team page** — `Equipo.aspx?i=<i>` → `/equipo/<i>`:
- **Crest/logo:** `img src="https://imagenes.feb.es/Imagen.aspx?i=<i>&ti=1"`
  (`ti=1` = crest). **Verified it returns `image/jpeg`, ~30 KB** — Option C
  storage is viable. Asset host = **`imagenes.feb.es`** (FEB's own image host,
  freely served — the FEB analogue of ACB's `mediacenter.acb.com`); record it in
  the §3 asset-host ToS check.
- **Name/official name:** header text adjacent to the crest (e.g.
  `"C.B. NATURAVIA MORÓN"`). Team name is also already in our DB from box scores.
- **Metadata:** `div.nodo` blocks — a club group (`Dirección` → parse city +
  province from `"… 41530 Morón de la Frontera (Sevilla)"`, `Web` → website,
  `E-mail`) and a pavilion group (`Nombre` → `arena` = `"PABELLÓN ALAMEDA"`).
- **Colours:** only kit swatches (`Equipación Titular/Reserva`), not clean hex →
  **defer** `primary/secondary_color` for FEB (leave blank).

**Net effect for FEB:** trajectory + birth date/place + height + (sometimes)
weight + nationality + **position** (`Puesto`) + **team logo + arena + city +
website** are all available; **only player photos are not.** ACB (later) is
expected to add photos via its JSON payload.

**Connector URL builders to add (Phase 1):**
`_player_profile_url(i, c) = /jugador/<i>/<c>`,
`_team_profile_url(i) = /equipo/<i>`,
logo `source_url = https://imagenes.feb.es/Imagen.aspx?i=<i>&ti=1`.

---

## 6. Collection & ingestion methods

### 6.1 New connector fetch methods

Add to `SourceConnector` (and implement per connector):
- `fetch_player_profile(person_external_id, team_external_id) -> RawSourcePayload`
- `fetch_team_profile(team_external_id, season_external_id) -> RawSourcePayload`

Both go through the existing `RateLimitedClient` + `fetch_or_cache` (DB
`RawDocument`) path, so caching/rate-limiting/parser-rerun all come for free. For
FEB these build `/jugador/…` and team URLs from ids we already store.

### 6.2 New parsers & schemas

- `connectors/parsers/feb.py` (+ `acb.py`): pure functions
  `parse_player_profile(payload) -> NormalizedPersonProfile` and
  `parse_team_profile(payload) -> NormalizedTeamProfile` — no I/O, unit-tested
  against fixtures, bumping the existing parser version.
- `ingestion/schemas.py`: add strict `NormalizedPersonProfile` (bio fields +
  `career: list[NormalizedCareerEntry]` + optional `photo_url`) and
  `NormalizedTeamProfile` (branding + `logo_url`). Strict (`extra="forbid"`) so a
  layout change fails loudly.

### 6.3 Persistence

- `ingestion/persistence.py`: `upsert_person_profile`, `upsert_team_profile`,
  `upsert_career_entry`, `upsert_media_asset` — idempotent `update_or_create`
  keyed by `(source, external_id)` / `source_url`. Profile upserts **only fill
  empty fields / refresh known ones**; they never clobber box-score-derived
  identity. `upsert_media_asset` writes `source_url`+attribution and skips `file`
  unless storage is enabled (§3/§4.3).

### 6.4 Media pipeline (Option C — enabled)

A `download_media_asset(asset_id)` Celery task: rate-limited fetch from the
recorded `source_url` (preferring `mediacenter.acb.com` / official FEB-club
assets), content-type + size validation, checksum dedupe (skip re-download of an
unchanged asset), store to `MediaAsset.file`, set `license`/`attribution`. Gated
by a setting `INGEST_STORE_MEDIA` (default **True** now that Option C is chosen,
but flippable to pause storage if a host's terms change). Respects the
`taken_down` flag — a taken-down asset is never re-downloaded.

### 6.5 Orchestration

Extend `ingest_feb_season` with an **enrichment phase** after games/rosters:
for each `Person`/`Team` touched this run, fetch+parse+upsert the profile (and
queue media if enabled). Guarded so a single failed profile doesn't abort the
run (per-entity try/except + logged to `IngestionRun.error_log`), mirroring the
backfill's per-season isolation. Add a standalone
`enrich_profiles --connector --season` command and a lower-frequency Beat task
(profiles change far less often than scores — weekly, not nightly).

---

## 7. Testing strategy

- **Golden profile parser tests:** commit small real player/team HTML fixtures
  under `connectors/tests/fixtures/`; assert parser → `Normalized*Profile`.
- **Idempotency:** run a profile fixture through `upsert_*_profile` twice → no
  dups, no clobbering of existing bio.
- **Non-clobber test:** a profile run must not overwrite `Person` identity or
  null-out fields when the source omits them.
- **Media gating test:** with `INGEST_STORE_MEDIA=False`, `upsert_media_asset`
  records `source_url` and leaves `file` empty.
- Keep `seed_demo_data` producing plausible bio/trajectory/colours so the
  frontend renders enriched pages offline (extend the seed accordingly).

---

## 8. Phased milestones

| Phase | Outcome |
|---|---|
| **0. Discovery** | Player/team page structure + rendering documented per source; profile-page ToS confirmed; fixtures saved; media policy decided. |
| **1. Textual enrichment (FEB)** | Bio fields + `CareerEntry` model/migrations; FEB profile fetch/parse/persist; bio + trajectory on player pages; team metadata (no logo). |
| **2. Media (Option C)** | `MediaAsset` + download task storing logos/photos from `mediacenter.acb.com` / FEB-club assets; attribution footer + takedown contact + `taken_down` flag; frontend fallbacks when absent/taken down. |
| **3. ACB** | Add profile parsing once the ACB box-score parser exists. |
| **4. Schedule** | Weekly Beat enrichment task; backfill profiles for already-ingested persons/teams. |

Recommended start: **Phase 1, FEB** — purely additive, no copyright exposure,
immediate visible payoff on existing pages.

---

## 9. Risks & open questions

- **Copyright (primary risk):** logos/photos — managed (not eliminated) by the
  Option C posture: official free-distribution sources, per-asset attribution,
  good-faith takedown contact + `taken_down` flag, and the `INGEST_STORE_MEDIA`
  kill-switch to pause storage if a host's terms change (§3).
- **Sparse/empty bio fields:** FEB pages may omit birth place/height — model
  everything nullable; never fail a run on a missing optional field.
- **Identity across sources:** the same player on ACB and FEB has different ids;
  cross-source person unification is **out of scope for v1** (document only).
- **Trajectory completeness:** FEB season history won't include foreign/youth
  clubs; `CareerEntry` stores what the source gives, no fabrication.
- **Extra request volume:** one profile fetch per player/team — mitigated by the
  DB cache, weekly cadence, and only enriching entities touched in a run.

---

## 10. Reviewer decisions (resolved 2026-06-24)

1. **Media policy → Option C (download & store).** Follow the dbasket.net
   precedent: source from official free-distribution channels
   (`mediacenter.acb.com` for ACB; FEB/club assets otherwise), store with
   per-asset attribution, credit ACB/FEB as image+data source, and provide a
   good-faith takedown contact + per-asset `taken_down` flag (§3, §4.2–4.3, §6.4).
2. **Trajectory depth → FEB/ACB player-page histories only** for now; no external
   career sources; nothing fabricated (§4.4).
3. **Physicals → keep both** `Person` (latest known) and `RosterEntry` (per
   season) (§4.1).
4. **Cadence → weekly** Beat enrichment task (§6.5).

### Remaining pre-implementation checks (not decisions — execution gates)
- [x] Phase 0 discovery on profile pages + asset hosts; save fixtures.
      (2026-06-24 — FEB done, see §5.3; ACB pending its box-score parser.)
- [~] robots.txt: `baloncestoenvivo.feb.es` returns **no robots.txt (404)** ⇒
      default-permissive, and it's the same host already cleared for box scores;
      asset host `imagenes.feb.es` identified. **ToS reading itself still pending**
      (human task) before a large production media run.
- [ ] Ship attribution footer + takedown contact before serving stored media.
