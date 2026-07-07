"""FEB season ingestion orchestration (spec §3.3).

Drives one season of one FEB competition through the pipeline:
``fetch (connector) → parse → persist → derive rosters → recompute aggregates``.
Kept separate from the Celery task so it can be unit-tested offline by injecting
a connector that returns fixture HTML.
"""

import logging
from dataclasses import dataclass

from connectors.base import SourceConnector
from connectors.parsers.feb import (
    ParserError,
    parse_box_score,
    parse_game_ids,
    parse_player_profile,
    parse_team_profile,
)
from connectors.registry import get_connector
from players.models import PlayerGameStats, RosterEntry
from stats.aggregation import recompute_player_season_aggregates
from teams.models import TeamSeason

from .catalog import FEB_COMPETITIONS, ensure_league_and_season
from .media import download_media_asset
from .persistence import (
    upsert_game_with_boxscore,
    upsert_person,
    upsert_person_profile,
    upsert_team,
    upsert_team_profile,
    upsert_team_season,
)

logger = logging.getLogger(__name__)


@dataclass
class IngestResult:
    """Outcome of a season ingestion.

    Attributes
    ----------
    games_ingested : int
        Number of games successfully parsed and persisted.
    games_failed : int
        Number of games skipped because parsing failed (logged, not fatal).
    """

    games_ingested: int
    games_failed: int


def ingest_feb_season(
    connector_id: str,
    season_external_id: str,
    *,
    connector: SourceConnector | None = None,
) -> IngestResult:
    """Ingest all finished games of one FEB season.

    Parameters
    ----------
    connector_id : str
        FEB connector id ("feb-primera" or "feb-segunda").
    season_external_id : str
        Season start year as used by the source (the ``t`` parameter).
    connector : SourceConnector or None
        Connector to use; resolved from the registry when omitted. Injectable
        so tests can supply a fixture-backed connector.

    Returns
    -------
    IngestResult
        Counts of ingested and failed games.

    Notes
    -----
    A single game that fails to parse is logged and skipped (so one bad acta
    doesn't abort the whole season); a structural break that affects every game
    surfaces as an all-failed run for investigation (spec §3.4).
    """
    competition = FEB_COMPETITIONS[connector_id]
    league, season = ensure_league_and_season(competition, int(season_external_id))
    connector = connector or get_connector(connector_id)

    results = connector.fetch_completed_games(season_external_id)
    game_ids = parse_game_ids(results.data)
    logger.info(
        "FEB %s %s: %d finished games found",
        connector_id,
        season_external_id,
        len(game_ids),
    )

    ingested = 0
    failed = 0
    for game_id in game_ids:
        try:
            payload = connector.fetch_box_score(game_id)
            parsed = parse_box_score(
                payload.data, source=connector_id, game_external_id=game_id
            )
            for team in parsed.teams:
                team_obj = upsert_team(team)
                upsert_team_season(team=team_obj, season=season, league=league)
            for person in parsed.persons:
                upsert_person(person)
            upsert_game_with_boxscore(parsed.game, season=season)
            ingested += 1
        except ParserError as exc:
            logger.warning("Skipping FEB game %s: %s", game_id, exc)
            failed += 1

    _rebuild_rosters(season)
    recompute_player_season_aggregates(season.pk)
    return IngestResult(games_ingested=ingested, games_failed=failed)


@dataclass
class EnrichResult:
    """Outcome of a season profile-enrichment run.

    Attributes
    ----------
    teams_enriched : int
        Teams whose branding profile was fetched and persisted.
    players_enriched : int
        Players whose bio/trajectory profile was fetched and persisted.
    media_stored : int
        Media assets (logos) whose binary was downloaded and stored.
    failures : int
        Entities skipped because their fetch/parse failed (logged, not fatal).
    """

    teams_enriched: int
    players_enriched: int
    media_stored: int
    failures: int


def enrich_feb_season(
    connector_id: str,
    season_external_id: str,
    *,
    connector: SourceConnector | None = None,
    store_media: bool = True,
) -> EnrichResult:
    """Enrich an already-ingested FEB season with profiles, trajectory and logos.

    Runs *after* box-score ingestion has created the teams/players: it fetches
    each team's and player's profile page, persists bio/branding/career, and
    (optionally) downloads team crests. Heavier and slower-changing than the
    box-score path, so it is driven on its own (weekly) cadence rather than per
    matchday (plan §6.5).

    Parameters
    ----------
    connector_id : str
        FEB connector id ("feb-primera" or "feb-segunda").
    season_external_id : str
        Season start year as used by the source (the ``t`` parameter).
    connector : SourceConnector or None
        Connector to use; resolved from the registry when omitted. Injectable so
        tests can supply a fixture-backed connector.
    store_media : bool
        Whether to download team logos (still also gated by
        ``settings.INGEST_STORE_MEDIA`` inside the media task).

    Returns
    -------
    EnrichResult
        Counts of enriched teams/players, stored media and per-entity failures.

    Notes
    -----
    Each entity is isolated: one failing profile is logged and skipped so a
    single bad page never aborts the run (spec §3.4), mirroring the per-game and
    per-season isolation elsewhere in the pipeline.
    """
    competition = FEB_COMPETITIONS[connector_id]
    _league, season = ensure_league_and_season(competition, int(season_external_id))
    connector = connector or get_connector(connector_id)

    teams = 0
    players = 0
    media = 0
    failures = 0

    for team_season in TeamSeason.objects.filter(season=season).select_related("team"):
        team_i = team_season.team.external_id
        try:
            payload = connector.fetch_team_profile(team_i)
            profile = parse_team_profile(payload.data, source=connector_id, team_external_id=team_i)
            team = upsert_team_profile(profile)
            teams += 1
            if store_media and team.logo_id and download_media_asset(team.logo_id):
                media += 1
        except Exception as exc:  # noqa: BLE001 - log and continue
            logger.warning("Skipping FEB team profile %s: %s", team_i, exc)
            failures += 1

    for person_c, team_i in _season_player_team_pairs(season):
        try:
            payload = connector.fetch_player_profile(person_c, team_i)
            person_profile = parse_player_profile(
                payload.data, source=connector_id, person_external_id=person_c
            )
            upsert_person_profile(person_profile)
            players += 1
        except Exception as exc:  # noqa: BLE001 - log and continue
            logger.warning("Skipping FEB player profile %s: %s", person_c, exc)
            failures += 1

    logger.info(
        "FEB %s %s enrichment: %d teams, %d players, %d logos, %d failures",
        connector_id,
        season_external_id,
        teams,
        players,
        media,
        failures,
    )
    return EnrichResult(
        teams_enriched=teams,
        players_enriched=players,
        media_stored=media,
        failures=failures,
    )


def _season_player_team_pairs(season) -> list[tuple[str, str]]:
    """Return distinct (player ``c``, team ``i``) external-id pairs for a season.

    One representative team per player is enough to build the player profile URL
    (``/jugador/<i>/<c>``); a player who appears for two teams in a season yields
    the first pair seen.
    """
    pairs: dict[str, str] = {}
    rows = (
        PlayerGameStats.objects.filter(game__season=season)
        .values_list("person__external_id", "team_season__team__external_id")
        .distinct()
    )
    for person_external_id, team_external_id in rows:
        pairs.setdefault(person_external_id, team_external_id)
    return list(pairs.items())


def _rebuild_rosters(season) -> None:
    """Reconstruct roster membership from the season's player box scores.

    Parameters
    ----------
    season : teams.Season
        The season whose rosters to rebuild.

    Notes
    -----
    FEB box scores don't expose jersey/position/height, so only membership
    (person ↔ team-season) is recorded here; richer fields can be backfilled
    from team pages later.
    """
    pairs = (
        PlayerGameStats.objects.filter(game__season=season)
        .values_list("person_id", "team_season_id")
        .distinct()
    )
    for person_id, team_season_id in pairs:
        RosterEntry.objects.get_or_create(
            person_id=person_id, team_season_id=team_season_id
        )
