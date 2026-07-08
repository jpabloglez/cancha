"""Competition and season catalog (spec §3.1, §12.2).

The single place that maps an external source's competition + season parameters
onto our canonical ``League`` / ``Season`` rows. This is where the LEB Oro/Plata
↔ Primera/Segunda FEB identity is collapsed onto one ``League`` per tier, keyed
by slug, so seasons before and after the 2024-25 rename never duplicate a league.
"""

from dataclasses import dataclass
from datetime import date

from teams.models import League, Season

from .persistence import upsert_league, upsert_season

#: Most recent season start year with finished games (2025 → 2025/2026).
#: Used only as a fallback when no DB seasons exist yet (initial bootstrap).
LATEST_SEASON_START_YEAR = 2025


@dataclass(frozen=True)
class FebCompetition:
    """Configuration for one FEB competition on baloncestoenvivo.feb.es.

    Attributes
    ----------
    connector_id : str
        Registered connector id (e.g. "feb-primera").
    competition_id : int
        The site's ``g`` query parameter (1 = Primera FEB, 2 = Segunda FEB).
    name_slug : str
        The site's ``nm`` query parameter (e.g. "primerafeb").
    league_name : str
        Canonical league name stored on the ``League`` row.
    league_slug : str
        URL-safe league identifier (the league idempotency key).
    level : int
        Competition tier (2 = Primera FEB, 3 = Segunda FEB).
    """

    connector_id: str
    competition_id: int
    name_slug: str
    league_name: str
    league_slug: str
    level: int

    @property
    def base_url(self) -> str:
        """Return the live-platform base URL hosting this competition's data."""
        return "https://baloncestoenvivo.feb.es"


#: FEB competitions keyed by connector id (spec §3.1; ids confirmed 2026-06-21).
FEB_COMPETITIONS: dict[str, FebCompetition] = {
    "feb-primera": FebCompetition(
        connector_id="feb-primera",
        competition_id=1,
        name_slug="primerafeb",
        league_name="Primera FEB",
        league_slug="primera-feb",
        level=2,
    ),
    "feb-segunda": FebCompetition(
        connector_id="feb-segunda",
        competition_id=2,
        name_slug="segundafeb",
        league_name="Segunda FEB",
        league_slug="segunda-feb",
        level=3,
    ),
}


#: ACB top-division league identity (spec §3.1). Unlike FEB, ACB seasons are
#: keyed by the source's ``editionId``; the editionId↔start-year map is resolved
#: at runtime from the schedule API, so only the league constants live here.
ACB_CONNECTOR_ID = "acb"
ACB_LEAGUE_NAME = "Liga ACB"
ACB_LEAGUE_SLUG = "acb"
ACB_LEAGUE_LEVEL = 1


def season_label(start_year: int) -> str:
    """Return the human-readable season label, e.g. 2024 -> "2024-2025"."""
    return f"{start_year}-{start_year + 1}"


def ensure_acb_league_and_season(start_year: int) -> tuple[League, Season]:
    """Ensure the canonical Liga ACB League and a Season exist.

    Parameters
    ----------
    start_year : int
        Season start year (resolved from the ACB ``editionId`` at ingest time).

    Returns
    -------
    tuple of (League, Season)
        The persisted league and season.

    Notes
    -----
    Season dates are approximate (Sep–Jun); exact dates are not needed for the
    analytics use case and can be refined from real data later.
    """
    league = upsert_league(
        name=ACB_LEAGUE_NAME, slug=ACB_LEAGUE_SLUG, level=ACB_LEAGUE_LEVEL
    )
    season = upsert_season(
        league=league,
        name=season_label(start_year),
        start_date=date(start_year, 9, 1),
        end_date=date(start_year + 1, 6, 30),
    )
    return league, season


def resolve_current_feb_season(connector_id: str) -> str:
    """Return the start-year string for the active FEB season.

    Queries the database for the most recently started season of the
    competition's league. Falls back to :data:`LATEST_SEASON_START_YEAR`
    during initial bootstrap when no seasons exist yet.

    Parameters
    ----------
    connector_id : str
        Registered FEB connector id (e.g. ``"feb-primera"``).

    Returns
    -------
    str
        Season start year as a string, e.g. ``"2025"`` for 2025/2026.

    Raises
    ------
    KeyError
        If *connector_id* is not a registered FEB competition.
    """
    competition = FEB_COMPETITIONS[connector_id]
    season = (
        Season.objects.filter(league__slug=competition.league_slug)
        .order_by("-start_date")
        .first()
    )
    if season is not None:
        return str(season.start_date.year)
    return str(LATEST_SEASON_START_YEAR)


def backfill_start_years(count: int, latest: int = LATEST_SEASON_START_YEAR) -> list[int]:
    """List the ``t`` start years for a backfill, newest first.

    Parameters
    ----------
    count : int
        Number of seasons to include.
    latest : int
        Most recent season start year.

    Returns
    -------
    list of int
        Season start years, e.g. ``[2025, 2024, 2023, 2022, 2021]``.
    """
    return [latest - offset for offset in range(count)]


def ensure_league_and_season(
    competition: FebCompetition, start_year: int
) -> tuple[League, Season]:
    """Ensure the canonical League and Season exist for a competition/season.

    Parameters
    ----------
    competition : FebCompetition
        The competition being ingested.
    start_year : int
        Season start year (the source's ``t`` parameter).

    Returns
    -------
    tuple of (League, Season)
        The persisted league and season.

    Notes
    -----
    Season dates are approximate (Sep–May); exact dates are not needed for the
    analytics use case and can be refined from real data later.
    """
    league = upsert_league(
        name=competition.league_name,
        slug=competition.league_slug,
        level=competition.level,
    )
    season = upsert_season(
        league=league,
        name=season_label(start_year),
        start_date=date(start_year, 9, 1),
        end_date=date(start_year + 1, 5, 31),
    )
    return league, season
