"""Persistence stage of the ingestion pipeline (spec §3.3).

The single write path from validated :mod:`ingestion.schemas` objects into the
Django ORM. Every function is idempotent: it keys on the external/natural keys
defined in the models, so re-ingesting the same data updates rather than
duplicates rows (``update_or_create``). Connectors and the seed command share
this module so the "validate → persist" boundary is identical for both.
"""

from datetime import date

import numpy as np
from django.db import transaction

from games.models import Game, TeamGameStats
from players.models import CareerEntry, Person, PlayerGameStats, RosterEntry, StaffEntry
from stats.metrics import estimate_possessions
from teams.models import League, MediaAsset, Season, Team, TeamSeason

from .schemas import (
    ExternalRef,
    NormalizedCareerEntry,
    NormalizedGame,
    NormalizedMediaRef,
    NormalizedPerson,
    NormalizedPersonProfile,
    NormalizedRosterEntry,
    NormalizedStaffEntry,
    NormalizedTeam,
    NormalizedTeamBoxScore,
    NormalizedTeamProfile,
)


def upsert_league(
    *, name: str, slug: str, level: int, country: str = "ES"
) -> League:
    """Create or update a league keyed by its slug.

    Parameters
    ----------
    name : str
        Canonical competition name.
    slug : str
        URL-safe identifier (the idempotency key).
    level : int
        Competition tier (1 = top division).
    country : str
        ISO 3166-1 alpha-2 code.

    Returns
    -------
    League
        The persisted league.
    """
    league, _ = League.objects.update_or_create(
        slug=slug,
        defaults={"name": name, "level": level, "country": country},
    )
    return league


def upsert_season(
    *, league: League, name: str, start_date: date, end_date: date | None = None
) -> Season:
    """Create or update a season keyed by ``(league, name)``.

    Parameters
    ----------
    league : League
        Owning league.
    name : str
        Season label, e.g. "2025-2026" (idempotency key with league).
    start_date : date
        Season start.
    end_date : date or None
        Season end, null while ongoing.

    Returns
    -------
    Season
        The persisted season.
    """
    season, _ = Season.objects.update_or_create(
        league=league,
        name=name,
        defaults={"start_date": start_date, "end_date": end_date},
    )
    return season


def upsert_team(team: NormalizedTeam) -> Team:
    """Create or update a team keyed by ``(source, external_id)``.

    Parameters
    ----------
    team : NormalizedTeam
        Validated team payload.

    Returns
    -------
    Team
        The persisted team.
    """
    obj, _ = Team.objects.update_or_create(
        source=team.ref.source,
        external_id=team.ref.external_id,
        defaults={
            "name": team.name,
            "short_name": team.short_name,
            "slug": team.slug,
            "city": team.city,
            "founded_year": team.founded_year,
        },
    )
    return obj


def upsert_team_season(
    *, team: Team, season: Season, league: League
) -> TeamSeason:
    """Create or update a team-season keyed by ``(team, season)``.

    Parameters
    ----------
    team : Team
        Participating club.
    season : Season
        Season of participation.
    league : League
        League competed in that season.

    Returns
    -------
    TeamSeason
        The persisted team-season.
    """
    team_season, _ = TeamSeason.objects.update_or_create(
        team=team, season=season, defaults={"league": league}
    )
    return team_season


def upsert_person(person: NormalizedPerson) -> Person:
    """Create or update a person keyed by ``(source, external_id)``.

    Parameters
    ----------
    person : NormalizedPerson
        Validated person payload.

    Returns
    -------
    Person
        The persisted person.
    """
    obj, _ = Person.objects.update_or_create(
        source=person.ref.source,
        external_id=person.ref.external_id,
        defaults={
            "first_name": person.first_name,
            "last_name": person.last_name,
            "slug": person.slug,
            "birth_date": person.birth_date,
            "nationality": person.nationality,
        },
    )
    return obj


def upsert_roster_entry(
    entry: NormalizedRosterEntry, *, team_season: TeamSeason
) -> RosterEntry:
    """Create or update a roster entry keyed by ``(person, team_season)``.

    Parameters
    ----------
    entry : NormalizedRosterEntry
        Validated roster payload (references the player by external ref).
    team_season : TeamSeason
        The team-season this entry belongs to.

    Returns
    -------
    RosterEntry
        The persisted roster entry.
    """
    person = _resolve_person(entry.person_ref)
    roster_entry, _ = RosterEntry.objects.update_or_create(
        person=person,
        team_season=team_season,
        defaults={
            "jersey_number": entry.jersey_number,
            "position": entry.position,
            "height_cm": entry.height_cm,
            "weight_kg": entry.weight_kg,
        },
    )
    return roster_entry


@transaction.atomic
def upsert_game_with_boxscore(game: NormalizedGame, *, season: Season) -> Game:
    """Create or update a finished game and its full box score.

    Idempotent across the game, its team totals and every player line. Runs in
    a single transaction so a partially-parsed game never lands in the DB
    (spec §3.3: never persist corrupt/partial data).

    Parameters
    ----------
    game : NormalizedGame
        Validated game payload including team and player box scores.
    season : Season
        Season the game belongs to (used to resolve team-seasons).

    Returns
    -------
    Game
        The persisted game.
    """
    home_ts = _resolve_team_season(game.home_team_ref, season=season)
    away_ts = _resolve_team_season(game.away_team_ref, season=season)

    game_obj, _ = Game.objects.update_or_create(
        source=game.ref.source,
        external_id=game.ref.external_id,
        defaults={
            "season": season,
            "home_team_season": home_ts,
            "away_team_season": away_ts,
            "date": game.date,
            "final_score_home": game.final_score_home,
            "final_score_away": game.final_score_away,
            "round": game.round,
        },
    )

    for team_box in game.team_box_scores:
        _upsert_team_game_stats(team_box, game=game_obj, season=season)

    for player_box in game.player_box_scores:
        person = _resolve_person(player_box.person_ref)
        team_season = _resolve_team_season(player_box.team_ref, season=season)
        PlayerGameStats.objects.update_or_create(
            game=game_obj,
            person=person,
            defaults={
                "team_season": team_season,
                "minutes_played": player_box.minutes_played,
                "points": player_box.points,
                "rebounds_off": player_box.rebounds_off,
                "rebounds_def": player_box.rebounds_def,
                "assists": player_box.assists,
                "steals": player_box.steals,
                "blocks": player_box.blocks,
                "turnovers": player_box.turnovers,
                "fouls": player_box.fouls,
                "field_goals_made": player_box.field_goals_made,
                "field_goals_att": player_box.field_goals_att,
                "three_point_made": player_box.three_point_made,
                "three_point_att": player_box.three_point_att,
                "free_throws_made": player_box.free_throws_made,
                "free_throws_att": player_box.free_throws_att,
            },
        )

    return game_obj


def _upsert_team_game_stats(
    team_box: NormalizedTeamBoxScore, *, game: Game, season: Season
) -> TeamGameStats:
    """Persist a team's box-score totals, deriving possessions and pace.

    Parameters
    ----------
    team_box : NormalizedTeamBoxScore
        Validated team totals.
    game : Game
        The persisted game these totals belong to.
    season : Season
        Season used to resolve the team-season.

    Returns
    -------
    TeamGameStats
        The persisted team stat line.

    Notes
    -----
    Possessions reuse :func:`stats.metrics.estimate_possessions`; pace assumes a
    40-minute regulation game (seed data has no overtime), so pace equals
    possessions per regulation game.
    """
    team_season = _resolve_team_season(team_box.team_ref, season=season)
    possessions = float(
        estimate_possessions(
            np.array([float(team_box.field_goals_att)]),
            np.array([float(team_box.free_throws_att)]),
            np.array([float(team_box.turnovers)]),
            np.array([float(team_box.rebounds_off)]),
        )[0]
    )
    team_stats, _ = TeamGameStats.objects.update_or_create(
        game=game,
        team_season=team_season,
        defaults={
            "points": team_box.points,
            "rebounds_off": team_box.rebounds_off,
            "rebounds_def": team_box.rebounds_def,
            "assists": team_box.assists,
            "steals": team_box.steals,
            "blocks": team_box.blocks,
            "turnovers": team_box.turnovers,
            "fouls": team_box.fouls,
            "field_goals_made": team_box.field_goals_made,
            "field_goals_att": team_box.field_goals_att,
            "three_point_made": team_box.three_point_made,
            "three_point_att": team_box.three_point_att,
            "free_throws_made": team_box.free_throws_made,
            "free_throws_att": team_box.free_throws_att,
            "possessions": possessions,
            "pace": possessions,
        },
    )
    return team_stats


# -- Enrichment (profiles, media, career) ----------------------------------
#
# Profile upserts run *after* the box-score path has created the Team/Person.
# They fill or refresh descriptive fields only — a value the source omits
# (``None``) is left untouched, and identity fields are never written here
# (docs/team-member-enrichment-plan.md §6.3).


def upsert_media_asset(ref: NormalizedMediaRef, *, kind: str) -> MediaAsset:
    """Create or update a media asset keyed by its source URL (idempotent).

    Records provenance and attribution immediately; the binary itself is
    downloaded by a separate gated task, so ``file`` is never written here and an
    already-downloaded file or a ``taken_down`` flag is never cleared.

    Parameters
    ----------
    ref : NormalizedMediaRef
        Validated media reference (source URL + optional license/attribution).
    kind : str
        One of :class:`teams.models.MediaAsset.Kind` (logo / photo).

    Returns
    -------
    MediaAsset
        The persisted asset record.
    """
    defaults: dict[str, str] = {"kind": kind, "source": ref.source}
    if ref.license is not None:
        defaults["license"] = ref.license
    if ref.attribution is not None:
        defaults["attribution"] = ref.attribution
    asset, _ = MediaAsset.objects.update_or_create(
        source_url=ref.source_url, defaults=defaults
    )
    return asset


def upsert_team_profile(profile: NormalizedTeamProfile) -> Team:
    """Fill/refresh branding metadata on an existing team (idempotent).

    Parameters
    ----------
    profile : NormalizedTeamProfile
        Validated branding payload referencing an already-persisted team.

    Returns
    -------
    Team
        The enriched team.

    Raises
    ------
    Team.DoesNotExist
        If no team exists for ``profile.ref`` (the box-score path must run first).
    """
    team = Team.objects.get(
        source=profile.ref.source, external_id=profile.ref.external_id
    )
    _set_if_present(team, "official_name", profile.official_name)
    _set_if_present(team, "arena", profile.arena)
    _set_if_present(team, "primary_color", profile.primary_color)
    _set_if_present(team, "secondary_color", profile.secondary_color)
    _set_if_present(team, "website", profile.website)
    _set_if_present(team, "city", profile.city)
    _set_if_present(team, "founded_year", profile.founded_year)
    if profile.logo is not None:
        team.logo = upsert_media_asset(
            profile.logo, kind=MediaAsset.Kind.TEAM_LOGO
        )
    team.save()
    return team


def upsert_person_profile(profile: NormalizedPersonProfile) -> Person:
    """Fill/refresh biography on an existing person and rebuild their career.

    Parameters
    ----------
    profile : NormalizedPersonProfile
        Validated bio payload referencing an already-persisted person.

    Returns
    -------
    Person
        The enriched person.

    Raises
    ------
    Person.DoesNotExist
        If no person exists for ``profile.ref`` (box-score path must run first).
    """
    person = _resolve_person(profile.ref)
    _set_if_present(person, "display_name", profile.display_name)
    _set_if_present(person, "birth_date", profile.birth_date)
    _set_if_present(person, "birth_city", profile.birth_city)
    _set_if_present(person, "birth_country", profile.birth_country)
    _set_if_present(person, "nationality", profile.nationality)
    _set_if_present(person, "height_cm", profile.height_cm)
    _set_if_present(person, "weight_kg", profile.weight_kg)
    _set_if_present(person, "primary_position", profile.primary_position)
    _set_if_present(person, "dominant_hand", profile.dominant_hand)
    if profile.photo is not None:
        person.photo = upsert_media_asset(
            profile.photo, kind=MediaAsset.Kind.PLAYER_PHOTO
        )
    person.save()
    for entry in profile.career:
        upsert_career_entry(entry, person=person)
    return person


def upsert_career_entry(
    entry: NormalizedCareerEntry, *, person: Person
) -> CareerEntry:
    """Create or update a career-timeline entry keyed by ``(source, external_id)``.

    Parameters
    ----------
    entry : NormalizedCareerEntry
        Validated career stint.
    person : Person
        The player the stint belongs to.

    Returns
    -------
    CareerEntry
        The persisted career entry.
    """
    team: Team | None = None
    if entry.team_ref is not None:
        team = Team.objects.filter(
            source=entry.team_ref.source, external_id=entry.team_ref.external_id
        ).first()
    career_entry, _ = CareerEntry.objects.update_or_create(
        source=entry.ref.source,
        external_id=entry.ref.external_id,
        defaults={
            "person": person,
            "season_label": entry.season_label,
            "club_name": entry.club_name,
            "league_name": entry.league_name or "",
            "team": team,
        },
    )
    return career_entry


def _set_if_present(obj: object, field: str, value: object) -> None:
    """Set ``obj.field = value`` only when ``value`` is not None.

    Enforces the fill/refresh-never-clobber rule for profile upserts: a field the
    source did not provide (``None``) keeps its existing value.

    Parameters
    ----------
    obj : object
        The model instance to mutate (saved by the caller).
    field : str
        Attribute name to set.
    value : object
        Candidate value; ignored when None.
    """
    if value is not None:
        setattr(obj, field, value)


def upsert_staff_entry(
    person_data: NormalizedPerson,
    entry_data: NormalizedStaffEntry,
    team_season: "TeamSeason",
) -> StaffEntry:
    """Create or update a coaching staff entry for a team-season.

    The person is upserted first (by ``source`` + ``external_id``), then the
    ``StaffEntry`` is upserted keyed on ``(person, team_season, role)``.

    Parameters
    ----------
    person_data : NormalizedPerson
        Normalized coach identity (name + slug derived from their full name).
    entry_data : NormalizedStaffEntry
        Role and team reference.
    team_season : TeamSeason
        The team-season this staff entry belongs to.

    Returns
    -------
    StaffEntry
        The persisted (created or existing) staff entry.
    """
    person, _ = Person.objects.update_or_create(
        source=person_data.ref.source,
        external_id=person_data.ref.external_id,
        defaults={
            "first_name": person_data.first_name,
            "last_name": person_data.last_name,
            "slug": person_data.slug,
        },
    )
    staff_entry, _ = StaffEntry.objects.get_or_create(
        person=person,
        team_season=team_season,
        role=entry_data.role,
    )
    return staff_entry


def _resolve_person(ref: ExternalRef) -> Person:
    """Resolve a person by external ref, raising if missing.

    Parameters
    ----------
    ref : ExternalRef
        External identity of the person.

    Returns
    -------
    Person
        The matching person.

    Raises
    ------
    Person.DoesNotExist
        If no person was previously persisted under ``ref``.
    """
    return Person.objects.get(source=ref.source, external_id=ref.external_id)


def _resolve_team_season(ref: ExternalRef, *, season: Season) -> TeamSeason:
    """Resolve a team-season by the team's external ref and a season.

    Parameters
    ----------
    ref : ExternalRef
        External identity of the team.
    season : Season
        Season the team participated in.

    Returns
    -------
    TeamSeason
        The matching team-season.

    Raises
    ------
    TeamSeason.DoesNotExist
        If the team has no participation row for ``season``.
    """
    team = Team.objects.get(source=ref.source, external_id=ref.external_id)
    return TeamSeason.objects.get(team=team, season=season)
