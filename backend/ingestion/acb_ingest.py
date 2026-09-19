"""ACB season ingestion orchestration (spec §3.3).

Drives one ACB edition (season) through the pipeline:
``fetch schedule → iterate rounds → fetch box scores → persist → derive rosters
→ recompute aggregates``, using ACB's public JSON API
(:mod:`connectors.parsers.acb`). Kept separate from the Celery task so it can be
unit-tested offline by injecting a connector that returns fixture JSON.

ACB seasons are identified by the source's ``editionId`` (e.g. "90" = 2025/2026);
the editionId↔start-year mapping is resolved from the schedule response rather
than hardcoded.
"""

import json
import logging
from dataclasses import dataclass
from typing import Protocol, cast

from connectors.parsers.acb import (
    MatchHeader,
    ParserError,
    SeasonMatches,
    parse_boxscore,
    parse_matches,
    parse_player_profiles,
    parse_staff_entries,
    parse_team_profiles,
)
from connectors.registry import get_connector
from players.models import PlayerGameStats, RosterEntry
from stats.aggregation import recompute_player_season_aggregates

from .catalog import ACB_CONNECTOR_ID, ensure_acb_league_and_season
from .media import download_media_asset
from .persistence import (
    upsert_game_with_boxscore,
    upsert_person,
    upsert_person_profile,
    upsert_staff_entry,
    upsert_team,
    upsert_team_profile,
    upsert_team_season,
)
from .schemas import (
    NormalizedPersonProfile,
    NormalizedTeam,
    NormalizedTeamProfile,
)

logger = logging.getLogger(__name__)


class _AcbConnectorLike(Protocol):
    """Structural type for connectors that implement the full ACB method set."""

    def fetch_completed_games(self, season_external_id: str) -> object: ...
    def fetch_box_score(self, game_external_id: str) -> object: ...
    def fetch_current_schedule(self) -> object: ...
    def fetch_round_matches(self, edition_id: str, round_id: int) -> object: ...


@dataclass
class IngestResult:
    """Outcome of an ACB season ingestion.

    Attributes
    ----------
    games_ingested : int
        Number of games successfully parsed and persisted.
    games_failed : int
        Number of games skipped because fetching/parsing failed (logged).
    players_enriched : int
        Distinct players whose bio (position/photo) was filled from box scores.
    photos_stored : int
        Player headshots whose binary was downloaded and stored.
    teams_enriched : int
        Distinct teams whose branding (crest/colour) was filled in.
    logos_stored : int
        Team crests whose binary was downloaded and stored.
    """

    games_ingested: int
    games_failed: int
    players_enriched: int = 0
    photos_stored: int = 0
    teams_enriched: int = 0
    logos_stored: int = 0
    staff_ingested: int = 0


def ingest_acb_season(
    edition_id: str,
    *,
    connector: _AcbConnectorLike | None = None,
    store_media: bool = True,
) -> IngestResult:
    """Ingest all finished games of one ACB edition (season).

    Parameters
    ----------
    edition_id : str
        The ACB ``editionId`` (e.g. "90" for 2025/2026).
    connector : SourceConnector or None
        Connector to use; resolved from the registry when omitted. Injectable so
        tests can supply a fixture-backed connector.
    store_media : bool
        Whether to download player headshots (still also gated by
        ``settings.INGEST_STORE_MEDIA`` inside the media task).

    Returns
    -------
    IngestResult
        Counts of ingested/failed games and enriched players / stored photos.

    Raises
    ------
    ParserError
        If the edition's start year cannot be resolved from the schedule.

    Notes
    -----
    A single game that fails is logged and skipped (one bad box score never
    aborts the season); a structural break surfaces as an all-failed run for
    investigation (spec §3.4), mirroring the FEB path. Player position/photo
    enrichment rides along on the box-score payload that is fetched anyway, so it
    needs no extra requests (plan: ACB Phase 2).
    """
    acb = cast(_AcbConnectorLike, connector or get_connector(ACB_CONNECTOR_ID))

    schedule_payload = _json(acb.fetch_completed_games(edition_id))
    schedule = parse_matches(schedule_payload, source=ACB_CONNECTOR_ID)
    start_year = schedule.seasons.get(int(edition_id))
    if start_year is None:
        raise ParserError(
            f"ACB edition {edition_id} not found in the schedule's season map"
        )
    league, season = ensure_acb_league_and_season(start_year)

    headers, teams, team_profiles = _collect_finished_games(
        acb, edition_id, schedule, schedule_payload
    )
    logger.info(
        "ACB edition %s (%s): %d finished games across %d rounds",
        edition_id,
        season.name,
        len(headers),
        len(schedule.round_ids) or 1,
    )

    for team in teams.values():
        team_obj = upsert_team(team)
        upsert_team_season(team=team_obj, season=season, league=league)

    ingested = 0
    failed = 0
    profiles: dict[str, NormalizedPersonProfile] = {}
    # Staff keyed by (team_club_id, person_external_id, role) for deduplication.
    staff_seen: dict[tuple[str, str, str], tuple] = {}
    for header in headers:
        try:
            payload = _json(acb.fetch_box_score(header.external_id))
            parsed = parse_boxscore(
                payload, source=ACB_CONNECTOR_ID, header=header
            )
            for team in parsed.teams:
                team_obj = upsert_team(team)
                upsert_team_season(team=team_obj, season=season, league=league)
            for person in parsed.persons:
                upsert_person(person)
            upsert_game_with_boxscore(parsed.game, season=season)
            for profile in parse_player_profiles(payload, source=ACB_CONNECTOR_ID):
                profiles.setdefault(profile.ref.external_id, profile)
            for person_data, entry_data in parse_staff_entries(
                payload, source=ACB_CONNECTOR_ID
            ):
                key = (
                    entry_data.team_ref.external_id,
                    person_data.ref.external_id,
                    entry_data.role,
                )
                staff_seen.setdefault(key, (person_data, entry_data))
            ingested += 1
        except (ParserError, KeyError, ValueError) as exc:
            logger.warning("Skipping ACB game %s: %s", header.external_id, exc)
            failed += 1

    enriched, photos = _enrich_players(profiles.values(), store_media=store_media)
    teams_enriched, logos = _enrich_teams(
        team_profiles.values(), store_media=store_media
    )
    staff_count = _persist_staff(staff_seen.values(), season=season)
    logger.info(
        "ACB edition %s: %d games ingested, %d failed, %d players enriched, "
        "%d photos stored, %d teams enriched, %d logos stored, %d staff entries",
        edition_id,
        ingested,
        failed,
        enriched,
        photos,
        teams_enriched,
        logos,
        staff_count,
    )

    _rebuild_rosters(season)
    recompute_player_season_aggregates(season.pk)
    return IngestResult(
        games_ingested=ingested,
        games_failed=failed,
        players_enriched=enriched,
        photos_stored=photos,
        teams_enriched=teams_enriched,
        logos_stored=logos,
        staff_ingested=staff_count,
    )


def _persist_staff(entries, *, season) -> int:
    """Upsert coaching staff entries for a season.

    Parameters
    ----------
    entries : iterable of (NormalizedPerson, NormalizedStaffEntry)
        Deduplicated staff entries gathered from all game box scores.
    season : Season
        The season these staff entries belong to.

    Returns
    -------
    int
        Number of staff entries successfully persisted.
    """
    from teams.models import TeamSeason

    count = 0
    for person_data, entry_data in entries:
        try:
            team_season = TeamSeason.objects.get(
                team__source=entry_data.team_ref.source,
                team__external_id=entry_data.team_ref.external_id,
                season=season,
            )
            upsert_staff_entry(person_data, entry_data, team_season)
            count += 1
        except Exception as exc:  # noqa: BLE001 - log and continue
            logger.warning(
                "Skipping ACB staff entry %s (%s): %s",
                person_data.ref.external_id,
                entry_data.role,
                exc,
            )
    return count


def _enrich_teams(profiles, *, store_media: bool) -> tuple[int, int]:
    """Persist team branding profiles and download their crests.

    Parameters
    ----------
    profiles : iterable of NormalizedTeamProfile
        Distinct team branding profiles gathered from the schedule.
    store_media : bool
        Whether to attempt downloading each team's crest binary.

    Returns
    -------
    tuple of (int, int)
        ``(teams_enriched, logos_stored)``. Each profile is isolated: one
        failure is logged and skipped so it never aborts the run.
    """
    enriched = 0
    logos = 0
    for profile in profiles:
        try:
            team = upsert_team_profile(profile)
            enriched += 1
            if (
                store_media
                and team.logo_id
                and download_media_asset(team.logo_id)
            ):
                logos += 1
        except Exception as exc:  # noqa: BLE001 - log and continue
            logger.warning(
                "Skipping ACB team enrichment for %s: %s",
                profile.ref.external_id,
                exc,
            )
    return enriched, logos


def _enrich_players(profiles, *, store_media: bool) -> tuple[int, int]:
    """Persist player position/photo profiles and download their headshots.

    Parameters
    ----------
    profiles : iterable of NormalizedPersonProfile
        Distinct player profiles gathered from the season's box scores.
    store_media : bool
        Whether to attempt downloading each player's headshot binary.

    Returns
    -------
    tuple of (int, int)
        ``(players_enriched, photos_stored)``. Each profile is isolated: one
        failure is logged and skipped so it never aborts the run.
    """
    enriched = 0
    photos = 0
    for profile in profiles:
        try:
            person = upsert_person_profile(profile)
            enriched += 1
            if (
                store_media
                and person.photo_id
                and download_media_asset(person.photo_id)
            ):
                photos += 1
        except Exception as exc:  # noqa: BLE001 - log and continue
            logger.warning(
                "Skipping ACB enrichment for %s: %s", profile.ref.external_id, exc
            )
    return enriched, photos


def resolve_past_edition_ids(
    count: int,
    connector: _AcbConnectorLike | None = None,
) -> list[str]:
    """Return the editionIds of the N most recent ACB seasons, newest first.

    Parameters
    ----------
    count : int
        Number of past editions to return.
    connector : SourceConnector or None
        Connector to use; resolved from the registry when omitted.

    Returns
    -------
    list of str
        Edition ids sorted by descending start year, e.g.
        ``["90", "89", "88", "87", "86"]`` for count=5 ending at 2025/26.
    """
    acb_connector = cast(_AcbConnectorLike, connector or get_connector(ACB_CONNECTOR_ID))
    schedule = parse_matches(
        _json(acb_connector.fetch_current_schedule()), source=ACB_CONNECTOR_ID
    )
    # seasons dict: {edition_id: start_year}; pick the N most-recent by start_year.
    items = sorted(schedule.seasons.items(), key=lambda kv: kv[1], reverse=True)
    return [str(edition_id) for edition_id, _ in items[:count]]


def resolve_current_edition_id(
    connector: _AcbConnectorLike | None = None,
) -> str:
    """Resolve ACB's current edition id from the schedule API.

    Parameters
    ----------
    connector : SourceConnector or None
        Connector to use; resolved from the registry when omitted.

    Returns
    -------
    str
        The current ``editionId`` (``selectedFilters.season``).

    Raises
    ------
    ParserError
        If the current edition cannot be determined.
    """
    acb_connector = cast(_AcbConnectorLike, connector or get_connector(ACB_CONNECTOR_ID))
    # Omitting editionId makes the API return the live edition (selectedFilters).
    schedule = parse_matches(
        _json(acb_connector.fetch_current_schedule()), source=ACB_CONNECTOR_ID
    )
    if schedule.current_edition_id is None:
        raise ParserError("Could not resolve ACB current edition id")
    return str(schedule.current_edition_id)


def _collect_finished_games(
    connector: _AcbConnectorLike,
    edition_id: str,
    schedule: SeasonMatches,
    schedule_payload: dict,
) -> tuple[list[MatchHeader], dict[str, NormalizedTeam], dict[str, NormalizedTeamProfile]]:
    """Gather finished-game headers, teams and branding across all rounds.

    Parameters
    ----------
    connector : SourceConnector
        The ACB connector.
    edition_id : str
        The ACB ``editionId``.
    schedule : SeasonMatches
        The already-parsed full-edition schedule (round list + first batch).
    schedule_payload : dict
        The raw schedule JSON, mined for team branding (crest/colour) alongside
        each round's payload.

    Returns
    -------
    tuple
        ``(headers, teams, team_profiles)`` — de-duplicated finished-game
        headers, ``clubId`` -> ``NormalizedTeam`` and ``clubId`` ->
        ``NormalizedTeamProfile`` (branding).

    Notes
    -----
    The base schedule response only lists the current round, so each round is
    fetched explicitly; a round that fails to fetch is logged and skipped.
    """
    headers: dict[str, MatchHeader] = {h.external_id: h for h in schedule.headers}
    teams: dict[str, NormalizedTeam] = {t.ref.external_id: t for t in schedule.teams}
    team_profiles: dict[str, NormalizedTeamProfile] = {
        p.ref.external_id: p
        for p in parse_team_profiles(schedule_payload, source=ACB_CONNECTOR_ID)
    }

    for round_id in schedule.round_ids:
        try:
            payload = _json(connector.fetch_round_matches(edition_id, round_id))
            batch = parse_matches(payload, source=ACB_CONNECTOR_ID)
        except (ParserError, KeyError, ValueError) as exc:
            logger.warning("Skipping ACB round %s: %s", round_id, exc)
            continue
        # Derive the round label from the schedule's id→number map so we don't
        # depend on the per-round payload including roundNumber in match objects
        # (it doesn't when isRoundSelected=false was used for the initial fetch).
        round_number = schedule.round_number_by_id.get(round_id)
        round_label = f"J{round_number}" if round_number is not None else None
        for header in batch.headers:
            if round_label is not None:
                header.round_label = round_label
            # Always overwrite so round-specific labels take precedence over the
            # initial schedule header (which had round_label=None).
            headers[header.external_id] = header
        for team in batch.teams:
            teams.setdefault(team.ref.external_id, team)
        for profile in parse_team_profiles(payload, source=ACB_CONNECTOR_ID):
            team_profiles.setdefault(profile.ref.external_id, profile)

    return list(headers.values()), teams, team_profiles


def _rebuild_rosters(season) -> None:
    """Reconstruct roster membership from the season's player box scores.

    Parameters
    ----------
    season : teams.Season
        The season whose rosters to rebuild.

    Notes
    -----
    Mirrors the FEB path: only membership (person ↔ team-season) is recorded
    here; richer roster fields (jersey, position, photo) are backfilled by the
    profile/enrichment path.
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


def _json(payload) -> dict:
    """Decode a connector payload's JSON-text body into a dict."""
    data = payload.data
    if isinstance(data, dict):
        return data
    parsed = json.loads(data)
    assert isinstance(parsed, dict), f"Expected JSON object, got {type(parsed).__name__}"
    return parsed
