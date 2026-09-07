"""Parsers for the ACB JSON API (api2.acb.com) — spec §3.3.

Pure functions turning ACB's public JSON API responses into validated
``ingestion.schemas`` objects. ACB's site (acb.com / live.acb.com) is a Next.js
app whose **server-rendered results page only lists a handful of featured
games**, so a full season cannot be enumerated from HTML. The site's own
frontend instead reads a public JSON API at ``api2.acb.com`` (authenticated with
an ``X-APIKEY`` constant shipped to every browser), which is the source used
here (plan: ACB JSON-API discovery 2026-06-27).

Two endpoints are parsed:

* ``/api/seasondata/Competition/matches`` — the schedule. Carries the full
  edition↔season-year map, the round list (to iterate a whole season), and each
  match's teams/score/date/status. Parsed by :func:`parse_matches`.
* ``/api/matchdata/Result/boxscores`` — a single finished game's stat lines
  (per-player and team totals). Parsed by :func:`parse_boxscore`, combined with
  the :class:`MatchHeader` already obtained from the schedule.

ACB splits two- and three-pointers, so total field goals are
``twoPointers + threePointers``. Teams are keyed by their **stable ``clubId``**
(constant across seasons), not the season-specific ``team.id``.
"""

from dataclasses import dataclass, field
from datetime import datetime

from django.utils import timezone
from django.utils.text import slugify

from connectors.parsers.feb import ParsedGame, ParserError
from ingestion.schemas import (
    ExternalRef,
    NormalizedGame,
    NormalizedMediaRef,
    NormalizedPerson,
    NormalizedPersonProfile,
    NormalizedPlayerBoxScore,
    NormalizedStaffEntry,
    NormalizedTeam,
    NormalizedTeamBoxScore,
    NormalizedTeamProfile,
)

#: Rights note + credit recorded on every ACB-sourced media asset.
_ACB_MEDIA_LICENSE = "© ACB / static.acb.com"
_ACB_MEDIA_ATTRIBUTION = "ACB.com"

#: Bumped when ACB parsing logic changes; recorded on each IngestionRun (§3.4).
ACB_PARSER_VERSION = "acb-json-2026.06"

#: ACB's Spanish ``gameRole`` label -> our position code (PG/SG/SF/PF/C).
_POSITION_MAP = {
    "base": "PG",
    "escolta": "SG",
    "alero": "SF",
    "ala": "SF",
    "ala-pivot": "PF",
    "ala-pívot": "PF",
    "alapivot": "PF",
    "pivot": "C",
    "pívot": "C",
}


@dataclass
class MatchHeader:
    """Schedule-level metadata for one game (everything but the stat lines).

    Attributes
    ----------
    external_id : str
        The ACB ``matchId`` as a string (the game's external id).
    home_team_ref, away_team_ref : ExternalRef
        Identities (by ``clubId``) of the home and away teams.
    home_score, away_score : int
        Final scores.
    date : datetime
        Tip-off datetime (timezone-aware).
    round_label : str or None
        Round / matchday label, when known.
    """

    external_id: str
    home_team_ref: ExternalRef
    away_team_ref: ExternalRef
    home_score: int
    away_score: int
    date: datetime
    round_label: str | None = None


@dataclass
class SeasonMatches:
    """Parsed output of one ``Competition/matches`` response.

    Attributes
    ----------
    teams : list of NormalizedTeam
        Teams appearing in the returned matches (keyed by ``clubId``).
    headers : list of MatchHeader
        Headers of the **finished** games in the response (live/scheduled games
        are dropped — ingestion is post-game only).
    round_ids : list of int
        All round ids available for the edition (to iterate a whole season).
    seasons : dict of int to int
        ``editionId`` -> ``seasonStartYear`` map (the catalog mapping).
    current_edition_id : int or None
        The edition the response was scoped to (``selectedFilters.season``).
    """

    teams: list[NormalizedTeam] = field(default_factory=list)
    headers: list[MatchHeader] = field(default_factory=list)
    round_ids: list[int] = field(default_factory=list)
    round_number_by_id: dict[int, int] = field(default_factory=dict)
    seasons: dict[int, int] = field(default_factory=dict)
    current_edition_id: int | None = None


def parse_matches(payload: dict, *, source: str) -> SeasonMatches:
    """Parse a ``Competition/matches`` JSON response.

    Parameters
    ----------
    payload : dict
        Decoded JSON from ``/api/seasondata/Competition/matches``.
    source : str
        Connector id ("acb") used for every ``ExternalRef``.

    Returns
    -------
    SeasonMatches
        Teams, finished-game headers, the round list and the edition↔year map.

    Raises
    ------
    ParserError
        If the response lacks the expected ``teams``/``matches`` structure.
    """
    if not isinstance(payload, dict) or "matches" not in payload:
        raise ParserError("ACB matches payload missing 'matches'")

    teams_by_id: dict[int, dict] = {}
    teams: list[NormalizedTeam] = []
    for raw in payload.get("teams", []):
        teams_by_id[raw["id"]] = raw
        teams.append(_team(raw, source=source))

    headers: list[MatchHeader] = []
    for match in payload["matches"]:
        if str(match.get("matchStatus")) != "FINALIZED":
            continue
        home = teams_by_id.get(match["homeTeamId"])
        away = teams_by_id.get(match["awayTeamId"])
        if home is None or away is None:
            continue
        headers.append(
            MatchHeader(
                external_id=str(match["id"]),
                home_team_ref=_team_ref(home, source),
                away_team_ref=_team_ref(away, source),
                home_score=int(match["homeScore"]),
                away_score=int(match["awayScore"]),
                date=_parse_iso(match["startDateTime"]),
                round_label=_round_label(match),
            )
        )

    available = payload.get("availableFilters", {})
    seasons = {
        int(s["id"]): int(s["seasonStartYear"])
        for s in available.get("seasons", [])
        if s.get("seasonStartYear") is not None
    }
    rounds_raw = available.get("rounds", [])
    round_ids = [int(r["id"]) for r in rounds_raw]
    round_number_by_id = {
        int(r["id"]): int(r["roundNumber"])
        for r in rounds_raw
        if r.get("roundNumber") is not None
    }
    selected = payload.get("selectedFilters", {})
    current = selected.get("season")

    return SeasonMatches(
        teams=teams,
        headers=headers,
        round_ids=round_ids,
        round_number_by_id=round_number_by_id,
        seasons=seasons,
        current_edition_id=int(current) if current is not None else None,
    )


def parse_boxscore(
    payload: dict, *, source: str, header: MatchHeader
) -> ParsedGame:
    """Parse a ``Result/boxscores`` JSON response into a normalized game.

    Parameters
    ----------
    payload : dict
        Decoded JSON from ``/api/matchdata/Result/boxscores``.
    source : str
        Connector id ("acb") used for every ``ExternalRef``.
    header : MatchHeader
        Schedule metadata (teams/score/date) already obtained from
        :func:`parse_matches`; the box score itself carries no date/home-away.

    Returns
    -------
    ParsedGame
        The normalized game plus its two teams and every player.

    Raises
    ------
    ParserError
        If the game is unfinished or a team's stat lines are missing.
    """
    if not payload.get("matchFinished", False):
        raise ParserError(f"ACB game {header.external_id} not finished")

    by_club: dict[str, dict] = {}
    for team_box in payload.get("teamBoxscores", []):
        club_id = str(team_box["team"]["clubId"])
        by_club[club_id] = team_box

    team_boxes: list[NormalizedTeamBoxScore] = []
    player_boxes: list[NormalizedPlayerBoxScore] = []
    persons: list[NormalizedPerson] = []
    teams: list[NormalizedTeam] = []

    for team_ref in (header.home_team_ref, header.away_team_ref):
        team_box = by_club.get(team_ref.external_id)
        if team_box is None:
            raise ParserError(
                f"ACB game {header.external_id}: no box score for club "
                f"{team_ref.external_id}"
            )
        teams.append(_team(team_box["team"], source=source))
        totals = _period_total(team_box)
        team_boxes.append(_team_box(totals["team_total"], team_ref))
        for line in totals["players"]:
            player_boxes.append(_player_box(line, team_ref=team_ref, source=source))
            persons.append(_person(line["player"], source=source))

    game = NormalizedGame(
        ref=ExternalRef(source=source, external_id=header.external_id),
        home_team_ref=header.home_team_ref,
        away_team_ref=header.away_team_ref,
        date=header.date,
        final_score_home=header.home_score,
        final_score_away=header.away_score,
        round=header.round_label,
        team_box_scores=team_boxes,
        player_box_scores=player_boxes,
    )
    return ParsedGame(game=game, teams=teams, persons=persons)


def parse_player_profiles(
    payload: dict, *, source: str
) -> list[NormalizedPersonProfile]:
    """Extract player bio enrichment (position + photo) from a box score.

    ACB ships each player's headshot URL and ``gameRole`` position inside the
    box-score payload already fetched for ingestion, so enrichment is a free
    by-product rather than a separate page fetch (unlike FEB).

    Parameters
    ----------
    payload : dict
        Decoded JSON from ``/api/matchdata/Result/boxscores``.
    source : str
        Connector id ("acb") used for every ``ExternalRef``.

    Returns
    -------
    list of NormalizedPersonProfile
        One profile per distinct player appearing in the box score. Players with
        neither a known position nor a photo are omitted (nothing to enrich).
    """
    profiles: dict[str, NormalizedPersonProfile] = {}
    for team_box in payload.get("teamBoxscores", []):
        for line in _period_total(team_box)["players"]:
            profile = _player_profile(line.get("player", {}), source=source)
            if profile is not None:
                profiles.setdefault(profile.ref.external_id, profile)
    return list(profiles.values())


def _player_profile(
    player: dict, *, source: str
) -> NormalizedPersonProfile | None:
    """Build a person profile from an ACB player object, or None if empty."""
    pid = player.get("id")
    if pid is None:
        return None
    position = _position(player.get("gameRole"))
    photo = _photo_ref(player.get("headshotImageUrl"), source=source)
    if position is None and photo is None:
        return None
    nickname = (player.get("nickname") or "").strip()
    first = (player.get("firstName") or "").strip()
    last = (player.get("lastName") or "").strip()
    display_name = nickname or f"{first} {last}".strip() or None
    return NormalizedPersonProfile(
        ref=ExternalRef(source=source, external_id=str(pid)),
        display_name=display_name[:200] if display_name else None,
        primary_position=position,
        photo=photo,
    )


def _photo_ref(url: str | None, *, source: str) -> NormalizedMediaRef | None:
    """Build a media reference for a player headshot URL, or None if absent."""
    if not url:
        return None
    return NormalizedMediaRef(
        source=source,
        source_url=url[:500],
        license=_ACB_MEDIA_LICENSE,
        attribution=_ACB_MEDIA_ATTRIBUTION,
    )


def parse_team_profiles(
    payload: dict, *, source: str
) -> list[NormalizedTeamProfile]:
    """Extract team branding (crest + primary colour) from a schedule response.

    The ``teams`` array of a ``Competition/matches`` response carries each club's
    logo URL and primary colour, so branding enrichment rides along on the
    schedule already fetched for ingestion (no separate fetch).

    Parameters
    ----------
    payload : dict
        Decoded JSON from ``/api/seasondata/Competition/matches`` (any round).
    source : str
        Connector id ("acb") used for every ``ExternalRef``.

    Returns
    -------
    list of NormalizedTeamProfile
        One profile per distinct team (by ``clubId``). Teams with neither a logo
        nor a colour are omitted (nothing to enrich).
    """
    profiles: dict[str, NormalizedTeamProfile] = {}
    for raw in payload.get("teams", []):
        profile = _team_profile(raw, source=source)
        if profile is not None:
            profiles.setdefault(profile.ref.external_id, profile)
    return list(profiles.values())


def parse_staff_entries(
    payload: dict, *, source: str
) -> list[tuple[NormalizedPerson, NormalizedStaffEntry]]:
    """Extract coaching staff (head coach + assistants) from a box-score payload.

    ACB's ``teamBoxscores`` block carries ``headCoach`` (a name string) and
    ``assistantCoaches`` (a list of name strings) per team. Since the API exposes
    no stable staff ID, the external_id is derived as ``"staff-{slug}"`` from the
    coach's full name, scoped to "acb" — stable enough for deduplication within
    a season.

    Parameters
    ----------
    payload : dict
        Decoded JSON from ``/api/matchdata/Result/boxscores``.
    source : str
        Connector id ("acb") used for every ``ExternalRef``.

    Returns
    -------
    list of (NormalizedPerson, NormalizedStaffEntry)
        One tuple per coach entry. The team_ref ``external_id`` is the ACB
        ``clubId`` (same key used for team deduplication).
    """
    results: list[tuple[NormalizedPerson, NormalizedStaffEntry]] = []
    for team_box in payload.get("teamBoxscores", []):
        club_id = team_box.get("team", {}).get("clubId")
        if club_id is None:
            continue
        team_ref = ExternalRef(source=source, external_id=str(club_id))

        entries: list[tuple[str, str]] = []  # (full_name, role)
        head = (team_box.get("headCoach") or "").strip()
        if head:
            entries.append((head, "head_coach"))
        for name in team_box.get("assistantCoaches") or []:
            name = (name or "").strip()
            if name:
                entries.append((name, "assistant_coach"))

        for full_name, role in entries:
            parts = full_name.rsplit(" ", 1)
            first = parts[0] if len(parts) > 1 else ""
            last = parts[-1]
            name_slug = slugify(full_name)
            if not name_slug:
                continue
            person = NormalizedPerson(
                ref=ExternalRef(source=source, external_id=f"staff-{name_slug}"),
                first_name=first[:100] or last[:100],
                last_name=last[:100],
                slug=f"entrenador-{name_slug}"[:160],
            )
            entry = NormalizedStaffEntry(
                person_ref=person.ref,
                team_ref=team_ref,
                role=role,
            )
            results.append((person, entry))
    return results


def _team_profile(raw: dict, *, source: str) -> NormalizedTeamProfile | None:
    """Build a team branding profile from an ACB team object, or None if empty."""
    club_id = raw.get("clubId")
    if club_id is None:
        return None
    logo = _logo_ref(raw.get("logo"), source=source)
    color = _hex_color(raw.get("primaryColorHex"))
    if logo is None and color is None:
        return None
    official = (raw.get("fullName") or "").strip() or None
    return NormalizedTeamProfile(
        ref=ExternalRef(source=source, external_id=str(club_id)),
        official_name=official[:200] if official else None,
        primary_color=color,
        logo=logo,
    )


def _logo_ref(url: str | None, *, source: str) -> NormalizedMediaRef | None:
    """Build a media reference for a team crest URL, or None if absent."""
    if not url:
        return None
    return NormalizedMediaRef(
        source=source,
        source_url=url[:500],
        license=_ACB_MEDIA_LICENSE,
        attribution=_ACB_MEDIA_ATTRIBUTION,
    )


def _hex_color(value: str | None) -> str | None:
    """Return a ``#rrggbb`` hex colour when well-formed, else None."""
    if not value:
        return None
    text = value.strip()
    if len(text) == 7 and text.startswith("#"):
        return text
    return None


# -- helpers ----------------------------------------------------------------


def _period_total(team_box: dict) -> dict:
    """Return the whole-game (quarter 0) player lines and team totals.

    Returns
    -------
    dict
        ``{"players": list[dict], "team_total": dict}`` where ``team_total`` is
        the ``total`` node (real team totals, including individual stats), not
        the ``team`` node (team-credited stats only).
    """
    for period in team_box.get("statsByPeriods", []):
        if period.get("quarter") == 0:
            stats = period["stats"]
            return {
                "players": stats.get("players", []),
                "team_total": stats.get("total", {}),
            }
    raise ParserError("ACB box score missing the quarter-0 totals period")


def _team(raw: dict, *, source: str) -> NormalizedTeam:
    """Build a normalized team from an ACB team object (keyed by ``clubId``)."""
    club_id = str(raw["clubId"])
    name = raw.get("fullName") or raw.get("shortName") or f"ACB {club_id}"
    short = (raw.get("abbreviatedName") or raw.get("shortName") or name)[:20]
    return NormalizedTeam(
        ref=ExternalRef(source=source, external_id=club_id),
        name=name[:150],
        short_name=short,
        slug=slugify(f"{name}-{source}-{club_id}")[:60],
    )


def _team_ref(raw: dict, source: str) -> ExternalRef:
    """Return the ``clubId``-keyed external ref for an ACB team object."""
    return ExternalRef(source=source, external_id=str(raw["clubId"]))


def _team_box(total: dict, team_ref: ExternalRef) -> NormalizedTeamBoxScore:
    """Build team totals from the ``total`` stats node (FG = 2pt + 3pt)."""
    return NormalizedTeamBoxScore(
        team_ref=team_ref,
        points=_int(total, "points"),
        rebounds_off=_int(total, "offRebounds"),
        rebounds_def=_int(total, "defRebounds"),
        assists=_int(total, "assists"),
        steals=_int(total, "steals"),
        blocks=_int(total, "blocks"),
        turnovers=_int(total, "turnovers"),
        fouls=_int(total, "personalFouls"),
        field_goals_made=_int(total, "twoPointersMade") + _int(total, "threePointersMade"),
        field_goals_att=_int(total, "twoPointersAttempted")
        + _int(total, "threePointersAttempted"),
        three_point_made=_int(total, "threePointersMade"),
        three_point_att=_int(total, "threePointersAttempted"),
        free_throws_made=_int(total, "freeThrowsMade"),
        free_throws_att=_int(total, "freeThrowsAttempted"),
    )


def _player_box(
    line: dict, *, team_ref: ExternalRef, source: str
) -> NormalizedPlayerBoxScore:
    """Build a player box score from a stat line (FG = 2pt + 3pt)."""
    return NormalizedPlayerBoxScore(
        person_ref=ExternalRef(source=source, external_id=str(line["player"]["id"])),
        team_ref=team_ref,
        minutes_played=_minutes(line.get("playTime")),
        points=_int(line, "points"),
        rebounds_off=_int(line, "offRebounds"),
        rebounds_def=_int(line, "defRebounds"),
        assists=_int(line, "assists"),
        steals=_int(line, "steals"),
        blocks=_int(line, "blocks"),
        turnovers=_int(line, "turnovers"),
        fouls=_int(line, "personalFouls"),
        field_goals_made=_int(line, "twoPointersMade") + _int(line, "threePointersMade"),
        field_goals_att=_int(line, "twoPointersAttempted")
        + _int(line, "threePointersAttempted"),
        three_point_made=_int(line, "threePointersMade"),
        three_point_att=_int(line, "threePointersAttempted"),
        free_throws_made=_int(line, "freeThrowsMade"),
        free_throws_att=_int(line, "freeThrowsAttempted"),
    )


def _person(player: dict, *, source: str) -> NormalizedPerson:
    """Build a normalized person from an ACB player object.

    ACB exposes full ``firstName`` / ``lastName`` directly; the headshot photo
    and ``gameRole`` position are captured later by the profile path, keeping
    the box-score path parallel to FEB.
    """
    first = (player.get("firstName") or "").strip()
    last = (player.get("lastName") or "").strip()
    if not last:
        last = (player.get("firstInitialAndLastName") or "-").strip() or "-"
    first = first or last
    pid = str(player["id"])
    return NormalizedPerson(
        ref=ExternalRef(source=source, external_id=pid),
        first_name=first[:100],
        last_name=last[:100],
        slug=slugify(f"{first}-{last}-{source}-{pid}")[:160],
    )


def _position(game_role: str | None) -> str | None:
    """Map an ACB Spanish ``gameRole`` to a position code, or None."""
    if not game_role:
        return None
    return _POSITION_MAP.get(game_role.strip().lower())


def _parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 datetime (trailing ``Z``) into an aware datetime."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed)
    return parsed


def _round_label(match: dict) -> str | None:
    """Best-effort round/matchday label from a match object."""
    number = match.get("roundNumber") or match.get("weekNumber")
    if number is not None:
        return f"J{number}"
    return None


def _int(obj: dict, key: str) -> int:
    """Read a non-negative integer stat, treating None/missing as 0."""
    value = obj.get(key)
    if value is None:
        return 0
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return 0


def _minutes(play_time: str | None) -> int:
    """Convert an ACB ``"mm:ss"`` play-time into whole minutes (capped at 60)."""
    if not play_time:
        return 0
    text = str(play_time).strip()
    minutes_part = text.split(":", 1)[0] if ":" in text else text
    try:
        return min(max(int(minutes_part), 0), 60)
    except ValueError:
        return 0


__all__ = [
    "ACB_PARSER_VERSION",
    "MatchHeader",
    "ParserError",
    "SeasonMatches",
    "parse_boxscore",
    "parse_matches",
    "parse_player_profiles",
    "parse_team_profiles",
]
