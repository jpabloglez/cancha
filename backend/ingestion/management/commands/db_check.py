"""Management command: database health check.

Prints entity counts, per-league breakdowns, data-quality indicators, and
(optionally) a comparison against the live API to confirm what the endpoints
expose matches what the database contains.

Examples
--------
Basic DB-only report::

    python manage.py db_check

Include API verification against a running server::

    python manage.py db_check --api-url http://localhost:8000/api/v1

Point at a deployed environment::

    python manage.py db_check --api-url https://api.basketstats.es/api/v1
"""

import json
import urllib.error
import urllib.request
from datetime import datetime, timezone

from django.core.management.base import BaseCommand
from django.db.models import Max, Min
from django.db.models.functions import Lower

from games.models import Game, TeamGameStats
from ingestion.models import DataSource, IngestionRun
from players.models import Person, PlayerGameStats, PlayerSeasonAggregate, RosterEntry
from teams.models import League, Season, Team, TeamSeason

# ── Formatting helpers ────────────────────────────────────────────────────────

W = 60  # total line width

def _hr(char: str = "─") -> str:
    return char * W

def _header(title: str) -> str:
    return f"\n{_hr('═')}\n  {title}\n{_hr('═')}"

def _section(title: str) -> str:
    return f"\n{title}\n{_hr()}"

def _row(label: str, *values: object, width: int = 28) -> str:
    label_col = f"  {label:<{width}}"
    val_cols = "  ".join(f"{v!s:>10}" for v in values)
    return f"{label_col}{val_cols}"

def _fmt_date(dt: datetime | None) -> str:
    if dt is None:
        return "—"
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d")


# ── API helper ────────────────────────────────────────────────────────────────

def _api_count(base_url: str, path: str, timeout: int = 8) -> int | None:
    """Fetch a paginated DRF list endpoint and return the ``count`` field.

    Parameters
    ----------
    base_url : str
        Base API URL (e.g. ``http://localhost:8000/api/v1``).
    path : str
        Endpoint path relative to base (e.g. ``/leagues/``).
    timeout : int
        Request timeout in seconds.

    Returns
    -------
    int or None
        The ``count`` value from the response, or ``None`` on error.
    """
    url = f"{base_url.rstrip('/')}{path}?limit=1"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read())
            return data.get("count")
    except (urllib.error.URLError, json.JSONDecodeError, KeyError):
        return None


# ── Command ───────────────────────────────────────────────────────────────────

class Command(BaseCommand):
    """Print a health-check report comparing database records to API output."""

    help = "Summarise entity counts in the DB and optionally verify against the API."

    def add_arguments(self, parser) -> None:
        """Register command-line options.

        Parameters
        ----------
        parser : argparse.ArgumentParser
            Parser provided by Django's command framework.
        """
        parser.add_argument(
            "--api-url",
            default="",
            metavar="URL",
            help="Base API URL to verify counts against (e.g. http://localhost:8000/api/v1). "
                 "Omit to skip API verification.",
        )

    def handle(self, *args, **options) -> None:
        """Run the health-check report.

        Parameters
        ----------
        *args
            Unused positional arguments.
        **options
            Parsed command options; ``api_url`` triggers API verification.
        """
        api_url: str = options["api_url"].strip()
        now = datetime.now(tz=timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        self.stdout.write(_header(f"DATABASE HEALTH CHECK — {now}"))

        self._entity_counts()
        self._per_league_breakdown()
        self._data_quality()
        self._ingestion_runs()

        if api_url:
            self._api_verification(api_url)

        self.stdout.write("")

    # ── Sections ──────────────────────────────────────────────────────────────

    def _entity_counts(self) -> None:
        """Print raw and deduplicated entity counts."""
        self.stdout.write(_section("ENTITY COUNTS"))
        self.stdout.write(_row("Entity", "DB rows", "Unique", width=32))
        self.stdout.write("  " + _hr("·"))

        leagues     = League.objects.count()
        seasons     = Season.objects.count()
        teams_raw   = Team.objects.count()
        team_dedup  = (
            Team.objects
            .annotate(name_lower=Lower("name"))
            .values("name_lower")
            .distinct()
            .count()
        )
        team_seasons = TeamSeason.objects.count()
        players_raw  = Person.objects.count()
        players_slug = Person.objects.values("slug").distinct().count()
        games        = Game.objects.count()
        player_stats = PlayerGameStats.objects.count()
        team_stats   = TeamGameStats.objects.count()
        roster_rows  = RosterEntry.objects.count()
        aggregates   = PlayerSeasonAggregate.objects.count()
        data_sources = DataSource.objects.count()

        def row(label: str, raw: int, unique: int | None = None) -> None:
            note = ""
            if unique is not None and unique != raw:
                note = f"  ← {raw - unique} duplicates"
            uniq_str = str(unique) if unique is not None else "—"
            self.stdout.write(_row(label, raw, uniq_str, width=32) + note)

        row("Leagues",                 leagues)
        row("Seasons",                 seasons)
        row("Teams (raw rows)",        teams_raw,   team_dedup)
        row("TeamSeasons",             team_seasons)
        row("Players (Person)",        players_raw, players_slug)
        row("Games",                   games)
        row("PlayerGameStats lines",   player_stats)
        row("TeamGameStats lines",     team_stats)
        row("RosterEntries",           roster_rows)
        row("PlayerSeasonAggregates",  aggregates)
        row("DataSources",             data_sources)

    def _per_league_breakdown(self) -> None:
        """Print per-league game and team counts with date ranges."""
        self.stdout.write(_section("PER-LEAGUE BREAKDOWN"))
        self.stdout.write(
            f"  {'League':<22}  {'Seasons':>7}  {'Teams':>6}  "
            f"{'Games':>6}  {'No round':>8}  {'First game':<11}  {'Last game':<11}"
        )
        self.stdout.write("  " + _hr("·"))

        for league in League.objects.order_by("level"):
            seasons = Season.objects.filter(league=league).count()
            teams   = (
                TeamSeason.objects.filter(league=league)
                .values("team")
                .distinct()
                .count()
            )
            games_qs  = Game.objects.filter(season__league=league)
            games     = games_qs.count()
            no_round  = games_qs.filter(round__isnull=True).count()
            dates     = games_qs.aggregate(first=Min("date"), last=Max("date"))
            first_d   = _fmt_date(dates["first"])
            last_d    = _fmt_date(dates["last"])

            no_round_str = f"{no_round}" if no_round else "—"
            self.stdout.write(
                f"  {league.name:<22}  {seasons:>7}  {teams:>6}  "
                f"{games:>6}  {no_round_str:>8}  {first_d:<11}  {last_d:<11}"
            )

    def _data_quality(self) -> None:
        """Print data-quality indicators."""
        self.stdout.write(_section("DATA QUALITY"))
        self.stdout.write(_row("Check", "Count", "Status", width=36))
        self.stdout.write("  " + _hr("·"))

        total_games = Game.objects.count()

        def quality_row(label: str, bad: int, total: int) -> None:
            pct = bad / total * 100 if total else 0
            status = self.style.SUCCESS("OK") if bad == 0 else self.style.WARNING(f"{pct:.1f}%")
            self.stdout.write(_row(label, bad, status, width=36))

        games_no_round = Game.objects.filter(round__isnull=True).count()
        games_no_box   = (
            Game.objects
            .filter(player_stats__isnull=True)
            .distinct()
            .count()
        )
        games_no_team_stats = (
            Game.objects
            .filter(team_stats__isnull=True)
            .distinct()
            .count()
        )
        players_no_stats = (
            Person.objects
            .filter(season_aggregates__isnull=True)
            .count()
        )
        teams_no_logo = Team.objects.filter(logo__isnull=True).count()
        players_no_photo = Person.objects.filter(photo__isnull=True).count()

        quality_row("Games missing round label",      games_no_round,      total_games)
        quality_row("Games missing player box score", games_no_box,        total_games)
        quality_row("Games missing team box score",   games_no_team_stats, total_games)
        quality_row("Players with no season stats",   players_no_stats,    Person.objects.count())
        quality_row("Teams with no logo",             teams_no_logo,       Team.objects.count())
        quality_row("Players with no photo",          players_no_photo,    Person.objects.count())

    def _ingestion_runs(self) -> None:
        """Print the last five ingestion runs."""
        self.stdout.write(_section("LAST 5 INGESTION RUNS"))
        self.stdout.write(
            f"  {'Started':<20}  {'Source':<20}  {'Status':<10}  {'Records':>8}"
        )
        self.stdout.write("  " + _hr("·"))

        runs = IngestionRun.objects.select_related("data_source").order_by("-started_at")[:5]
        if not runs:
            self.stdout.write("  (no runs recorded)")
            return

        for run in runs:
            started  = _fmt_date(run.started_at) if run.started_at else "—"
            source   = run.data_source.connector_id if run.data_source else "—"
            status   = run.status
            records  = run.records_processed if run.records_processed is not None else "—"
            if status == "success":
                status_str = self.style.SUCCESS(status)
            elif status == "failed":
                status_str = self.style.ERROR(status)
            else:
                status_str = status
            self.stdout.write(
                f"  {started:<20}  {source:<20}  {status_str:<10}  {records!s:>8}"
            )

    def _api_verification(self, api_url: str) -> None:
        """Fetch live API counts and compare them against the database.

        Parameters
        ----------
        api_url : str
            Base API URL to query.
        """
        self.stdout.write(_section(f"API VERIFICATION  ({api_url})"))
        self.stdout.write(_row("Endpoint", "API count", "DB count", "Match", width=26))
        self.stdout.write("  " + _hr("·"))

        # (path, db_count, label)
        deduped_teams = (
            Team.objects
            .annotate(name_lower=Lower("name"))
            .values("name_lower")
            .distinct()
            .count()
        )

        checks = [
            ("/leagues/",  League.objects.count(),    "Leagues"),
            ("/seasons/",  Season.objects.count(),    "Seasons"),
            ("/teams/",    deduped_teams,             "Teams (deduped)"),
            ("/players/",  Person.objects.count(),    "Players"),
            ("/games/",    Game.objects.count(),      "Games"),
        ]

        all_ok = True
        for path, db_count, label in checks:
            api_count = _api_count(api_url, path)
            if api_count is None:
                match_str = self.style.WARNING("UNREACHABLE")
                all_ok = False
            elif api_count == db_count:
                match_str = self.style.SUCCESS("✓")
            else:
                match_str = self.style.ERROR(f"✗  (Δ {api_count - db_count:+d})")
                all_ok = False

            api_str = str(api_count) if api_count is not None else "—"
            self.stdout.write(
                _row(f"{label} ({path})", api_str, db_count, match_str, width=26)
            )

        self.stdout.write("  " + _hr("·"))
        if all_ok:
            summary = self.style.SUCCESS("All counts match.")
        else:
            summary = self.style.WARNING("Some discrepancies found.")
        self.stdout.write(f"  {summary}")
