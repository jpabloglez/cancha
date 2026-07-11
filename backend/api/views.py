"""Public, read-only API views (spec §5.1-§5.2).

All endpoints are unauthenticated reads (the app is consultation-only, spec
§6.4). ViewSets are read-only; the §5.2 endpoints that don't map cleanly to a
single model (standings, roster, player stats, compare, boxscore, leaders) are
implemented as viewset ``@action``s or standalone views.
"""

import hashlib
import re

from django.db.models import (
    Count,
    ExpressionWrapper,
    F,
    FloatField,
    Max,
    Q,
    QuerySet,
    Sum,
)
from django.db.models.functions import Cast
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view
from rest_framework.filters import SearchFilter
from rest_framework.generics import get_object_or_404
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from games.models import Game, TeamGameStats
from players.models import Person, PlayerSeasonAggregate, RosterEntry
from teams.models import League, Season, Team, TeamSeason

from .serializers import (
    AllTimeLeaderSerializer,
    BoxScoreSerializer,
    GameSerializer,
    LeaderSerializer,
    LeagueSerializer,
    PersonDetailSerializer,
    PersonSerializer,
    PlayerOfTheDaySerializer,
    PlayerSeasonAggregateSerializer,
    RosterEntryWithStatsSerializer,
    SeasonSerializer,
    StandingSerializer,
    TeamSeasonSerializer,
    TeamSerializer,
)

# Public stat keys -> PlayerSeasonAggregate fields used by the leaders endpoint.
LEADER_STATS = {
    "points": "points_per_game",
    "rebounds": "rebounds_per_game",
    "assists": "assists_per_game",
    "minutes": "minutes_per_game",
    "per": "per",
    "ts": "ts_percent",
    "efg": "efg_percent",
    "usage": "usage_rate",
}

# Public stat keys -> annotation names used by the all-time leaders endpoint.
ALLTIME_STATS = {
    "ppg": "ppg",
    "rpg": "rpg",
    "apg": "apg",
    "spg": "spg",
    "bpg": "bpg",
    "topg": "topg",
    "total_points": "total_points",
    "total_rebounds": "total_rebounds",
    "total_assists": "total_assists",
    "per": "per_weighted",
    "ts": "ts_weighted",
    "two_pct": "two_pct_weighted",
    "three_pct": "three_pct_weighted",
    "ft_pct": "ft_pct_weighted",
    "games": "total_games",
}

# Leaderboard qualification: a player must have played at least this fraction of
# the most-played player's games to rank, so 1–2 game flukes (which can spike
# rate stats like PER/TS%) don't top the table. Overridable via ``?minGames=``.
LEADER_QUALIFY_FRACTION = 0.3


def _aggregate_to_stats(aggregate: PlayerSeasonAggregate) -> dict:
    """Shape a season aggregate into the §5.3 nested player-stats contract.

    Parameters
    ----------
    aggregate : PlayerSeasonAggregate
        The materialized season aggregate.

    Returns
    -------
    dict
        Payload matching ``stats.serializers.PlayerSeasonStatsSerializer``.
    """
    return {
        "player_id": str(aggregate.person_id),
        "season_id": str(aggregate.season_id),
        "season_name": aggregate.season.name,
        "games_played": aggregate.games_played,
        "minutes_per_game": aggregate.minutes_per_game,
        "points_per_game": aggregate.points_per_game,
        "rebounds_per_game": aggregate.rebounds_per_game,
        "assists_per_game": aggregate.assists_per_game,
        "steals_per_game": aggregate.steals_per_game,
        "blocks_per_game": aggregate.blocks_per_game,
        "turnovers_per_game": aggregate.turnovers_per_game,
        "fouls_per_game": aggregate.fouls_per_game,
        "two_percent": aggregate.two_percent,
        "three_percent": aggregate.three_percent,
        "ft_percent": aggregate.ft_percent,
        "advanced": {
            "true_shooting_percent": aggregate.ts_percent,
            "effective_field_goal_percent": aggregate.efg_percent,
            "usage_rate": aggregate.usage_rate,
            "player_efficiency_rating": aggregate.per,
        },
    }


@api_view(["GET"])
def health(request: Request) -> Response:
    """Liveness probe used by the platform and local checks.

    Parameters
    ----------
    request : rest_framework.request.Request
        Incoming request (unused).

    Returns
    -------
    rest_framework.response.Response
        ``{"status": "ok"}`` with HTTP 200.
    """
    return Response({"status": "ok"})


class LeagueViewSet(viewsets.ReadOnlyModelViewSet):
    """List and retrieve covered leagues (``/leagues``)."""

    queryset = League.objects.annotate(
        seasons_count=Count("seasons", distinct=True),
        teams_count=Count("team_seasons__team", distinct=True),
    )
    serializer_class = LeagueSerializer
    lookup_field = "slug"


class SeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve seasons and expose computed standings (``/seasons``)."""

    queryset = Season.objects.select_related("league").all()
    serializer_class = SeasonSerializer
    filterset_fields = ["league"]

    @action(detail=True)
    def standings(self, request: Request, pk: str | None = None) -> Response:
        """Return the standings for a season, computed from finished games.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request.
        pk : str or None
            Season primary key from the URL.

        Returns
        -------
        rest_framework.response.Response
            Standing rows ordered by wins then point difference.
        """
        season = self.get_object()
        rows: dict[int, dict] = {}

        def row_for(team_season: TeamSeason) -> dict:
            return rows.setdefault(
                team_season.id,
                {
                    "team_season_id": team_season.id,
                    "team_name": team_season.team.name,
                    "team_slug": team_season.team.slug,
                    "team_logo": team_season.team.logo,
                    "team_primary_color": team_season.team.primary_color,
                    "games_played": 0,
                    "wins": 0,
                    "losses": 0,
                    "points_for": 0,
                    "points_against": 0,
                    "point_difference": 0,
                },
            )

        games = Game.objects.filter(season=season).select_related(
            "home_team_season__team__logo", "away_team_season__team__logo"
        )
        for game in games:
            home = row_for(game.home_team_season)
            away = row_for(game.away_team_season)
            home["games_played"] += 1
            away["games_played"] += 1
            home["points_for"] += game.final_score_home
            home["points_against"] += game.final_score_away
            away["points_for"] += game.final_score_away
            away["points_against"] += game.final_score_home
            if game.final_score_home >= game.final_score_away:
                home["wins"] += 1
                away["losses"] += 1
            else:
                away["wins"] += 1
                home["losses"] += 1

        for row in rows.values():
            row["point_difference"] = row["points_for"] - row["points_against"]

        ordered = sorted(
            rows.values(),
            key=lambda r: (r["wins"], r["point_difference"]),
            reverse=True,
        )
        return Response(
            StandingSerializer(
                ordered, many=True, context={"request": request}
            ).data
        )

    @action(detail=True)
    def rounds(self, request: Request, pk: str | None = None) -> Response:
        """Return the distinct round labels for a season, sorted numerically.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request.
        pk : str or None
            Season primary key from the URL.

        Returns
        -------
        rest_framework.response.Response
            ``{"rounds": ["J1", "J2", ..., "J34"]}`` — labels that have at least
            one finished game, in ascending round order.  Rounds without a
            numeric suffix (e.g. playoff labels from older ingestion) are appended
            after the numbered ones.
        """
        season = self.get_object()
        labels = (
            Game.objects.filter(season=season)
            .exclude(round__isnull=True)
            .order_by()
            .values_list("round", flat=True)
            .distinct()
        )

        def _sort_key(label: str) -> tuple[int, str]:
            m = re.match(r"J(\d+)$", label)
            return (int(m.group(1)), "") if m else (10000, label)

        sorted_labels = sorted(labels, key=_sort_key)
        return Response({"rounds": sorted_labels})


def _tgs_aggregates(qs: QuerySet) -> dict:
    """Sum every counting stat over a TeamGameStats queryset.

    Parameters
    ----------
    qs : QuerySet
        A ``TeamGameStats`` queryset (already filtered to the desired scope).

    Returns
    -------
    dict
        Annotation dict with ``games`` (count) plus ``tot_*`` sums for each
        box-score field and possessions.
    """
    return qs.aggregate(
        games=Count("id"),
        tot_pts=Sum("points"),
        tot_reb_off=Sum("rebounds_off"),
        tot_reb_def=Sum("rebounds_def"),
        tot_ast=Sum("assists"),
        tot_stl=Sum("steals"),
        tot_blk=Sum("blocks"),
        tot_tov=Sum("turnovers"),
        tot_fouls=Sum("fouls"),
        tot_fgm=Sum("field_goals_made"),
        tot_fga=Sum("field_goals_att"),
        tot_tpm=Sum("three_point_made"),
        tot_tpa=Sum("three_point_att"),
        tot_ftm=Sum("free_throws_made"),
        tot_fta=Sum("free_throws_att"),
        tot_poss=Sum("possessions"),
    )


def _build_team_stats(own: dict, opp: dict) -> dict:
    """Build per-game, per-100 and advanced blocks from aggregated totals.

    Parameters
    ----------
    own : dict
        Output of ``_tgs_aggregates`` for the focal team(s).
    opp : dict
        Output of ``_tgs_aggregates`` for the opposing team(s) in the same
        games.  At league-average level ``own`` and ``opp`` are the same dict
        (the league is its own opponent on aggregate).

    Returns
    -------
    dict
        ``{gamesPlayed, perGame, per100, advanced}`` ready for JSON output.
    """
    g = own["games"] or 1
    poss = max(own["tot_poss"] or 0, 1)
    opp_poss = max(opp.get("tot_poss") or poss, 1)
    opp_reb_off = opp.get("tot_reb_off") or 0
    opp_reb_def = opp.get("tot_reb_def") or 0
    opp_fga = max(opp.get("tot_fga") or 1, 1)
    opp_tpa = opp.get("tot_tpa") or 0
    opp_pts = opp.get("tot_pts") or 0

    pts = own["tot_pts"] or 0
    fgm = own["tot_fgm"] or 0
    fga = max(own["tot_fga"] or 0, 1)
    tpm = own["tot_tpm"] or 0
    tpa = own["tot_tpa"] or 0
    ftm = own["tot_ftm"] or 0
    fta = own["tot_fta"] or 0
    tov = own["tot_tov"] or 0
    reb_off = own["tot_reb_off"] or 0
    reb_def = own["tot_reb_def"] or 0
    stl = own["tot_stl"] or 0
    blk = own["tot_blk"] or 0

    two_made = fgm - tpm

    def pg(v: float) -> float:
        return round(v / g, 1)

    def p100(v: float) -> float:
        return round(v / poss * 100, 1)

    per_game = {
        "points": pg(pts),
        "twoMade": round(two_made / g, 1),
        "threeMade": pg(tpm),
        "ftMade": pg(ftm),
        "rebOff": pg(reb_off),
        "rebDef": pg(reb_def),
        "rebounds": pg(reb_off + reb_def),
        "assists": pg(own["tot_ast"] or 0),
        "turnovers": pg(tov),
        "steals": pg(stl),
        "blocks": pg(blk),
        "fouls": pg(own["tot_fouls"] or 0),
    }

    per_100 = {
        "points": p100(pts),
        "twoMade": round(two_made / poss * 100, 1),
        "threeMade": p100(tpm),
        "ftMade": p100(ftm),
        "rebOff": p100(reb_off),
        "rebDef": p100(reb_def),
        "rebounds": p100(reb_off + reb_def),
        "assists": p100(own["tot_ast"] or 0),
        "turnovers": p100(tov),
        "steals": p100(stl),
        "blocks": p100(blk),
        "fouls": p100(own["tot_fouls"] or 0),
    }

    ts_denom = max(2 * (fga + 0.44 * fta), 1)
    tov_denom = max(fga + 0.44 * fta + tov, 1)
    reb_off_denom = max(reb_off + opp_reb_def, 1)
    reb_def_denom = max(reb_def + opp_reb_off, 1)
    opp_two_att = max(opp_fga - opp_tpa, 1)

    advanced = {
        "ortg": round(pts / poss * 100, 1),
        "drtg": round(opp_pts / poss * 100, 1),
        "pace": round((own["tot_poss"] or 0) / g, 1),
        "tsPercent": round(pts / ts_denom * 100, 1),
        "efgPercent": round((fgm + 0.5 * tpm) / fga * 100, 1),
        "threeRate": round(tpa / fga * 100, 1),
        "ftRate": round(fta / fga * 100, 1),
        "tovPercent": round(tov / tov_denom * 100, 1),
        "rebOffPct": round(reb_off / reb_off_denom * 100, 1),
        "rebDefPct": round(reb_def / reb_def_denom * 100, 1),
        "stealPct": round(stl / opp_poss * 100, 1),
        "blockPct": round(blk / opp_two_att * 100, 1),
    }

    return {"gamesPlayed": g, "perGame": per_game, "per100": per_100, "advanced": advanced}


class TeamViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve teams and expose a season roster (``/teams``)."""

    queryset = Team.objects.select_related("logo").all()
    serializer_class = TeamSerializer
    lookup_field = "slug"
    filter_backends = [SearchFilter]
    search_fields = ["name", "short_name", "city"]

    @action(detail=True)
    def roster(self, request: Request, slug: str | None = None) -> Response:
        """Return a team's roster for the season given by ``?season=``.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request; requires a ``season`` query parameter.
        slug : str or None
            Team slug from the URL.

        Returns
        -------
        rest_framework.response.Response
            Roster entries, or HTTP 400 if ``season`` is missing.
        """
        season_id = request.query_params.get("season")
        if not season_id:
            return Response(
                {"detail": "Missing required 'season' query parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        team = self.get_object()
        team_season = TeamSeason.objects.filter(
            team=team, season_id=season_id
        ).first()
        if team_season is None:
            return Response([])
        entries = list(
            team_season.roster_entries.select_related("person", "person__photo").all()
        )
        person_ids = [e.person_id for e in entries]
        agg_by_person = {
            a.person_id: a
            for a in PlayerSeasonAggregate.objects.filter(
                person_id__in=person_ids, season_id=season_id
            )
        }
        return Response(
            RosterEntryWithStatsSerializer(
                entries,
                many=True,
                context={"request": request, "agg_by_person": agg_by_person},
            ).data
        )

    @action(detail=True, url_path="season-stats")
    def season_stats(self, request: Request, slug: str | None = None) -> Response:
        """Return per-game, per-100-possessions and advanced stats for a season.

        Parameters
        ----------
        request : rest_framework.request.Request
            Requires a ``season`` query parameter (season primary key).
        slug : str or None
            Team slug from the URL.

        Returns
        -------
        rest_framework.response.Response
            ``{team: {...}, leagueAvg: {...}}`` or HTTP 400/404.
        """
        season_id = request.query_params.get("season")
        if not season_id:
            return Response(
                {"detail": "Missing required 'season' query parameter."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        team = self.get_object()
        team_season = TeamSeason.objects.filter(
            team=team, season_id=season_id
        ).first()
        if team_season is None:
            return Response(
                {"detail": "Team did not participate in this season."},
                status=status.HTTP_404_NOT_FOUND,
            )

        own_qs = TeamGameStats.objects.filter(team_season=team_season)
        own_agg = _tgs_aggregates(own_qs)
        if not own_agg["games"]:
            return Response(
                {"detail": "No game stats recorded for this team in this season."},
                status=status.HTTP_404_NOT_FOUND,
            )

        game_ids = list(own_qs.values_list("game_id", flat=True))
        opp_agg = _tgs_aggregates(
            TeamGameStats.objects.filter(game_id__in=game_ids).exclude(
                team_season=team_season
            )
        )

        # League average: aggregate all TGS for the season; the league is its
        # own opponent on aggregate (DRtg_avg == ORtg_avg, etc.).
        league_agg = _tgs_aggregates(
            TeamGameStats.objects.filter(game__season_id=season_id)
        )
        n_teams = max(
            TeamSeason.objects.filter(season_id=season_id).count(), 1
        )
        league_stats = _build_team_stats(league_agg, league_agg)
        # gamesPlayed for the league is per-team average, not the sum.
        league_stats["gamesPlayed"] = round(
            (league_agg["games"] or 0) / n_teams
        )

        return Response(
            {
                "team": _build_team_stats(own_agg, opp_agg),
                "leagueAvg": league_stats,
            }
        )

    @action(detail=True, url_path="recent-games")
    def recent_games(self, request: Request, slug: str | None = None) -> Response:
        """Return the most recent finished games for this team in a season.

        Parameters
        ----------
        request : rest_framework.request.Request
            Optional ``season`` query parameter (season pk); defaults to the
            most recent season this team participated in.  Optional ``limit``
            (default 10, max 50).
        slug : str or None
            Team slug from the URL.

        Returns
        -------
        rest_framework.response.Response
            List of game objects enriched with a ``result`` field (``"W"`` /
            ``"L"``) indicating this team's outcome, newest first.
        """
        team = self.get_object()
        season_id = request.query_params.get("season")
        try:
            limit = min(int(request.query_params.get("limit", 10)), 50)
        except ValueError:
            limit = 10

        if season_id:
            team_season = TeamSeason.objects.filter(
                team=team, season_id=season_id
            ).first()
        else:
            team_season = (
                TeamSeason.objects.filter(team=team)
                .order_by("-season__start_date")
                .select_related("season")
                .first()
            )

        if team_season is None:
            return Response([])

        games = (
            Game.objects.filter(
                Q(home_team_season=team_season) | Q(away_team_season=team_season)
            )
            .select_related(
                "home_team_season__team__logo",
                "away_team_season__team__logo",
            )
            .order_by("-date")[:limit]
        )

        rows = []
        for game in games:
            is_home = game.home_team_season_id == team_season.id
            team_score = game.final_score_home if is_home else game.final_score_away
            opp_score = game.final_score_away if is_home else game.final_score_home
            data = GameSerializer(game, context={"request": request}).data
            data["result"] = "W" if team_score > opp_score else "L"
            data["isHome"] = is_home
            rows.append(data)

        return Response(rows)

    @action(detail=True, url_path="stats-history")
    def stats_history(self, request: Request, slug: str | None = None) -> Response:
        """Return per-season aggregated stats for all seasons this team played.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request (no query params required).
        slug : str or None
            Team slug from the URL.

        Returns
        -------
        rest_framework.response.Response
            List of ``{season, team, leagueAvg}`` entries ordered newest first.
        """
        team = self.get_object()
        team_seasons = (
            TeamSeason.objects.filter(team=team)
            .select_related("season")
            .order_by("-season__start_date")
        )

        rows = []
        for ts in team_seasons:
            own_qs = TeamGameStats.objects.filter(team_season=ts)
            own_agg = _tgs_aggregates(own_qs)
            if not own_agg["games"]:
                continue

            game_ids = list(own_qs.values_list("game_id", flat=True))
            opp_agg = _tgs_aggregates(
                TeamGameStats.objects.filter(game_id__in=game_ids).exclude(
                    team_season=ts
                )
            )
            league_agg = _tgs_aggregates(
                TeamGameStats.objects.filter(game__season_id=ts.season_id)
            )
            n_teams = max(
                TeamSeason.objects.filter(season_id=ts.season_id).count(), 1
            )
            league_stats = _build_team_stats(league_agg, league_agg)
            league_stats["gamesPlayed"] = round(
                (league_agg["games"] or 0) / n_teams
            )

            rows.append(
                {
                    "season": {
                        "id": ts.season_id,
                        "name": ts.season.name,
                        "startDate": str(ts.season.start_date),
                    },
                    "team": _build_team_stats(own_agg, opp_agg),
                    "leagueAvg": league_stats,
                }
            )

        return Response(rows)


class TeamSeasonViewSet(viewsets.ReadOnlyModelViewSet):
    """List team-season participations, filterable by team/season/league."""

    queryset = TeamSeason.objects.select_related("team", "season", "league").all()
    serializer_class = TeamSeasonSerializer
    filterset_fields = ["team", "season", "league"]


class PersonViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve players and expose season stats + comparison."""

    queryset = Person.objects.select_related("photo").all()
    serializer_class = PersonSerializer
    lookup_field = "slug"
    filter_backends = [SearchFilter]
    search_fields = ["first_name", "last_name", "display_name"]

    def get_serializer_class(self):
        """Use the detail serializer (with career timeline) on retrieve.

        Returns
        -------
        type[rest_framework.serializers.Serializer]
            ``PersonDetailSerializer`` for the detail view, else the list one.
        """
        if self.action == "retrieve":
            return PersonDetailSerializer
        return PersonSerializer

    def get_queryset(self) -> QuerySet[Person]:
        """Prefetch the career timeline (and its teams) on the detail view.

        Returns
        -------
        django.db.models.QuerySet
            Person queryset, with ``career`` prefetched for retrieve.
        """
        qs = super().get_queryset()
        if self.action == "retrieve":
            qs = qs.prefetch_related("career__team")
        return qs

    @action(detail=True)
    def stats(self, request: Request, slug: str | None = None) -> Response:
        """Return a player's per-season stats (basic + advanced).

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request; optional ``season`` query parameter filters to one
            season, otherwise all of the player's seasons are returned.
        slug : str or None
            Player slug from the URL.

        Returns
        -------
        rest_framework.response.Response
            One stats object (when ``season`` given) or a list across seasons.
        """
        person = self.get_object()
        aggregates = PlayerSeasonAggregate.objects.filter(
            person=person
        ).select_related("season")
        season_id = request.query_params.get("season")
        if season_id:
            aggregate = get_object_or_404(aggregates, season_id=season_id)
            return Response(_aggregate_to_stats(aggregate))
        payload = [_aggregate_to_stats(a) for a in aggregates.order_by("season_id")]
        return Response(payload)

    @action(detail=False)
    def compare(self, request: Request) -> Response:
        """Compare several players for a season (``?ids=1,2&season=``).

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request; ``ids`` is a comma-separated player id list and
            ``season`` selects the season.

        Returns
        -------
        rest_framework.response.Response
            A list of player-stats objects, or HTTP 400 on missing params.
        """
        ids_param = request.query_params.get("ids")
        season_id = request.query_params.get("season")
        if not ids_param or not season_id:
            return Response(
                {"detail": "Both 'ids' and 'season' query parameters are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        person_ids = [pid for pid in ids_param.split(",") if pid.strip()]
        aggregates = PlayerSeasonAggregate.objects.filter(
            person_id__in=person_ids, season_id=season_id
        ).select_related("season")
        return Response([_aggregate_to_stats(a) for a in aggregates])

    @action(detail=False, url_path="player-of-the-day")
    def player_of_the_day(self, request: Request) -> Response:
        """Return a deterministic daily featured player with their latest stats.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request (no query params used).

        Returns
        -------
        rest_framework.response.Response
            ``{ player: PersonDetail, latestStats: dict | null }`` where the
            player rotates once per calendar day (Madrid time).
        """
        total = Person.objects.count()
        if total == 0:
            return Response(
                {"detail": "No players available."}, status=status.HTTP_404_NOT_FOUND
            )
        today = timezone.localdate().isoformat()
        idx = int(hashlib.sha256(today.encode()).hexdigest(), 16) % total
        person = (
            Person.objects.select_related("photo")
            .prefetch_related("career__team")
            .order_by("id")[idx]
        )
        latest_agg = (
            PlayerSeasonAggregate.objects.filter(person=person)
            .select_related("season")
            .order_by("-season__start_date")
            .first()
        )
        payload = {
            "player": person,
            "latest_stats": _aggregate_to_stats(latest_agg) if latest_agg else None,
        }
        return Response(
            PlayerOfTheDaySerializer(payload, context={"request": request}).data
        )


class PlayerSeasonAggregateViewSet(viewsets.ReadOnlyModelViewSet):
    """List player season aggregates, filterable by player/season."""

    queryset = PlayerSeasonAggregate.objects.select_related("person", "season").all()
    serializer_class = PlayerSeasonAggregateSerializer
    filterset_fields = ["person", "season"]


class GameViewSet(viewsets.ReadOnlyModelViewSet):
    """List/retrieve finished games and expose full box scores."""

    queryset = Game.objects.select_related(
        "season",
        "home_team_season__team__logo",
        "away_team_season__team__logo",
    ).all()
    serializer_class = GameSerializer
    filterset_fields = ["season", "round", "home_team_season", "away_team_season"]

    @action(detail=True)
    def boxscore(self, request: Request, pk: str | None = None) -> Response:
        """Return the full box score for a finished game.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request.
        pk : str or None
            Game primary key from the URL.

        Returns
        -------
        rest_framework.response.Response
            Game info plus team totals and per-player lines.
        """
        game = self.get_object()
        payload = {
            "game": game,
            "team_stats": game.team_stats.all(),
            "player_stats": game.player_stats.select_related(
                "person", "person__photo"
            ).all(),
        }
        return Response(
            BoxScoreSerializer(payload, context={"request": request}).data
        )


class LeadersView(APIView):
    """Statistical leaders ranking (``/stats/leaders``, spec §5.2)."""

    def get(self, request: Request) -> Response:
        """Return the top players for a statistic.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request; query params: ``stat`` (default "points"),
            optional ``league``, optional ``season`` (defaults to the latest),
            optional ``limit`` (default 20).

        Returns
        -------
        rest_framework.response.Response
            Ranked leader rows, or HTTP 400 for an unknown stat.
        """
        stat = request.query_params.get("stat", "points")
        field = LEADER_STATS.get(stat)
        if field is None:
            return Response(
                {"detail": f"Unknown stat '{stat}'. Allowed: {sorted(LEADER_STATS)}."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        aggregates: QuerySet[PlayerSeasonAggregate] = (
            PlayerSeasonAggregate.objects.select_related(
                "person", "person__photo", "season"
            )
        )
        league_id = request.query_params.get("league")
        season_id = request.query_params.get("season")
        if season_id:
            aggregates = aggregates.filter(season_id=season_id)
        else:
            # Default to the latest season *within the chosen league* (or the
            # latest overall when no league is filtered) so a league-only
            # selection doesn't collide with an unrelated global latest season.
            seasons = Season.objects.all()
            if league_id:
                seasons = seasons.filter(league_id=league_id)
            latest = seasons.order_by("-start_date").first()
            if latest is not None:
                aggregates = aggregates.filter(season=latest)
        if league_id:
            aggregates = aggregates.filter(season__league_id=league_id)

        try:
            limit = min(int(request.query_params.get("limit", 20)), 100)
        except ValueError:
            limit = 20

        aggregates = self._qualify(aggregates, request.query_params.get("minGames"))

        # Secondary sort by person id so ties break deterministically.
        ranked = list(aggregates.order_by(f"-{field}", "person_id")[:limit])

        # Bulk-fetch the team each player belongs to in their respective seasons
        # so we can add team context without N+1 queries.
        person_ids = [agg.person_id for agg in ranked]
        season_ids = {agg.season_id for agg in ranked}
        roster_entries = RosterEntry.objects.filter(
            person_id__in=person_ids,
            team_season__season_id__in=season_ids,
        ).select_related("team_season__team__logo")
        # Map (person_id, season_id) → team for O(1) lookup below.
        team_map: dict[tuple[int, int], Team] = {
            (re.person_id, re.team_season.season_id): re.team_season.team
            for re in roster_entries
        }

        rows = [
            {
                "player_id": agg.person_id,
                "player_name": (
                    agg.person.display_name
                    or f"{agg.person.first_name} {agg.person.last_name}"
                ),
                "player_slug": agg.person.slug,
                "season_id": agg.season_id,
                "stat": stat,
                "value": getattr(agg, field),
                "photo": agg.person.photo,
                "team": team_map.get((agg.person_id, agg.season_id)),
            }
            for agg in ranked
        ]
        return Response(
            LeaderSerializer(rows, many=True, context={"request": request}).data
        )

    @staticmethod
    def _qualify(
        aggregates: QuerySet[PlayerSeasonAggregate], min_games_param: str | None
    ) -> QuerySet[PlayerSeasonAggregate]:
        """Drop players below the games-played qualification threshold.

        Parameters
        ----------
        aggregates : QuerySet[PlayerSeasonAggregate]
            The already season/league-filtered aggregates.
        min_games_param : str or None
            Explicit ``?minGames=`` override; when absent the threshold adapts to
            the most-played player's games (``LEADER_QUALIFY_FRACTION``).

        Returns
        -------
        QuerySet[PlayerSeasonAggregate]
            Aggregates restricted to qualifying players.
        """
        if min_games_param is not None:
            try:
                threshold = max(int(min_games_param), 0)
            except ValueError:
                threshold = 0
        else:
            max_games = (
                aggregates.aggregate(m=Max("games_played"))["m"] or 0
            )
            threshold = max(1, round(max_games * LEADER_QUALIFY_FRACTION))
        if threshold <= 1:
            return aggregates
        return aggregates.filter(games_played__gte=threshold)


class AllTimeLeadersView(APIView):
    """Cross-season cumulative and average statistical ranking (``/stats/alltime/``)."""

    _DEFAULT_MIN_GAMES = 20

    def get(self, request: Request) -> Response:
        """Return the top players ranked by a career statistic across all seasons.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request; supported query params:
            ``stat`` (default "ppg"), ``league`` (slug), ``season_from``
            (start year, inclusive), ``season_to`` (end year, inclusive),
            ``position`` (PG/SG/SF/PF/C), ``nationality`` (ISO code,
            case-insensitive substring), ``minGames`` (int, default 20),
            ``limit`` (int, default 10, max 50), ``offset`` (int, default 0).

        Returns
        -------
        rest_framework.response.Response
            ``{ count, results: [AllTimeLeader] }`` ordered by the requested
            stat descending, or HTTP 400 for an unknown stat key.
        """
        stat = request.query_params.get("stat", "ppg")
        sort_field = ALLTIME_STATS.get(stat)
        if sort_field is None:
            return Response(
                {
                    "detail": (
                        f"Unknown stat '{stat}'. Allowed: {sorted(ALLTIME_STATS)}."
                    )
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            limit = min(int(request.query_params.get("limit", 10)), 50)
        except ValueError:
            limit = 10
        try:
            offset = max(int(request.query_params.get("offset", 0)), 0)
        except ValueError:
            offset = 0
        try:
            min_games = max(int(request.query_params.get("minGames", self._DEFAULT_MIN_GAMES)), 0)
        except ValueError:
            min_games = self._DEFAULT_MIN_GAMES

        qs: QuerySet[PlayerSeasonAggregate] = PlayerSeasonAggregate.objects.all()

        league_slug = request.query_params.get("league")
        if league_slug:
            qs = qs.filter(season__league__slug=league_slug)

        season_from = request.query_params.get("seasonFrom")
        season_to = request.query_params.get("seasonTo")
        if season_from:
            qs = qs.filter(season__start_date__year__gte=int(season_from))
        if season_to:
            qs = qs.filter(season__start_date__year__lte=int(season_to))

        position = request.query_params.get("position")
        if position:
            qs = qs.filter(person__primary_position=position)

        nationality = request.query_params.get("nationality")
        if nationality:
            qs = qs.filter(person__nationality__icontains=nationality)

        # Expressions for weighted-sum totals (weight = games_played).
        _f: FloatField = FloatField()

        def _w(field: str) -> ExpressionWrapper:
            return ExpressionWrapper(F(field) * F("games_played"), output_field=_f)

        annotated = (
            qs.values("person_id")
            .annotate(
                total_games=Sum("games_played"),
                total_points=Sum(_w("points_per_game")),
                total_rebounds=Sum(_w("rebounds_per_game")),
                total_assists=Sum(_w("assists_per_game")),
                steals_total=Sum(_w("steals_per_game")),
                blocks_total=Sum(_w("blocks_per_game")),
                turnovers_total=Sum(_w("turnovers_per_game")),
                fouls_total=Sum(_w("fouls_per_game")),
                per_total=Sum(_w("per")),
                ts_total=Sum(_w("ts_percent")),
                two_pct_total=Sum(_w("two_percent")),
                three_pct_total=Sum(_w("three_percent")),
                ft_pct_total=Sum(_w("ft_percent")),
                seasons_count=Count("season", distinct=True),
            )
            .annotate(
                games_float=Cast(F("total_games"), output_field=_f),
            )
            .annotate(
                ppg=ExpressionWrapper(F("total_points") / F("games_float"), output_field=_f),
                rpg=ExpressionWrapper(F("total_rebounds") / F("games_float"), output_field=_f),
                apg=ExpressionWrapper(F("total_assists") / F("games_float"), output_field=_f),
                spg=ExpressionWrapper(F("steals_total") / F("games_float"), output_field=_f),
                bpg=ExpressionWrapper(F("blocks_total") / F("games_float"), output_field=_f),
                topg=ExpressionWrapper(F("turnovers_total") / F("games_float"), output_field=_f),
                per_weighted=ExpressionWrapper(F("per_total") / F("games_float"), output_field=_f),
                ts_weighted=ExpressionWrapper(F("ts_total") / F("games_float"), output_field=_f),
                two_pct_weighted=ExpressionWrapper(F("two_pct_total") / F("games_float"), output_field=_f),
                three_pct_weighted=ExpressionWrapper(F("three_pct_total") / F("games_float"), output_field=_f),
                ft_pct_weighted=ExpressionWrapper(F("ft_pct_total") / F("games_float"), output_field=_f),
            )
            .filter(total_games__gte=min_games)
        )

        total_count = annotated.count()
        ranked = list(annotated.order_by(f"-{sort_field}", "person_id")[offset : offset + limit])

        person_ids = [r["person_id"] for r in ranked]
        persons = {
            p.pk: p
            for p in Person.objects.filter(pk__in=person_ids).select_related("photo")
        }

        from collections import defaultdict

        league_map: dict[int, list[str]] = defaultdict(list)
        for pid, slug in (
            PlayerSeasonAggregate.objects.filter(person_id__in=person_ids)
            .values_list("person_id", "season__league__slug")
            .distinct()
        ):
            if slug not in league_map[pid]:
                league_map[pid].append(slug)

        rows = []
        for row in ranked:
            person = persons.get(row["person_id"])
            if person is None:
                continue
            full_name = (
                person.display_name
                or f"{person.first_name} {person.last_name}"
            )
            stat_val = row.get(sort_field) or 0.0
            rows.append(
                {
                    "player_id": person.pk,
                    "player_name": full_name,
                    "player_slug": person.slug,
                    "photo": person.photo,
                    "nationality": person.nationality,
                    "primary_position": person.primary_position,
                    "total_games": row["total_games"],
                    "seasons_count": row["seasons_count"],
                    "leagues": league_map[person.pk],
                    "total_points": row["total_points"] or 0.0,
                    "total_rebounds": row["total_rebounds"] or 0.0,
                    "total_assists": row["total_assists"] or 0.0,
                    "ppg": row["ppg"] or 0.0,
                    "rpg": row["rpg"] or 0.0,
                    "apg": row["apg"] or 0.0,
                    "spg": row["spg"] or 0.0,
                    "bpg": row["bpg"] or 0.0,
                    "topg": row["topg"] or 0.0,
                    "two_percent": row["two_pct_weighted"] or 0.0,
                    "three_percent": row["three_pct_weighted"] or 0.0,
                    "ft_percent": row["ft_pct_weighted"] or 0.0,
                    "per": row["per_weighted"],
                    "ts_percent": row["ts_weighted"] or 0.0,
                    "stat_value": float(stat_val),
                }
            )

        return Response(
            {
                "count": total_count,
                "results": AllTimeLeaderSerializer(
                    rows, many=True, context={"request": request}
                ).data,
            }
        )


class GlobalSearchView(APIView):
    """Cross-entity search: teams, players, leagues (``/search/``, plan §5.1).

    Returns up to 5 hits per entity type for the ``?q=`` query string.
    Results are sorted by relevance within each type (case-insensitive
    containment on the most natural name fields).
    """

    MAX_PER_TYPE = 5

    def get(self, request: Request) -> Response:
        """Return mixed search results across teams, players and leagues.

        Parameters
        ----------
        request : rest_framework.request.Request
            Incoming request; query param ``q`` is required (min 2 chars).

        Returns
        -------
        rest_framework.response.Response
            ``{ teams: [...], players: [...], leagues: [...] }`` where each
            list uses the standard serializer shape for that entity.
        """
        q = request.query_params.get("q", "").strip()
        if len(q) < 2:
            return Response({"teams": [], "players": [], "leagues": []})

        teams = (
            Team.objects.filter(name__icontains=q)
            .select_related("logo")
            .order_by("name")[: self.MAX_PER_TYPE]
        )
        players = (
            Person.objects.filter(
                Q(display_name__icontains=q)
                | Q(last_name__icontains=q)
                | Q(first_name__icontains=q)
            )
            .select_related("photo")
            .order_by("last_name", "first_name")[: self.MAX_PER_TYPE]
        )
        leagues = (
            League.objects.filter(name__icontains=q).order_by("level")[
                : self.MAX_PER_TYPE
            ]
        )

        return Response(
            {
                "teams": TeamSerializer(
                    teams, many=True, context={"request": request}
                ).data,
                "players": PersonSerializer(
                    players, many=True, context={"request": request}
                ).data,
                "leagues": LeagueSerializer(
                    leagues, many=True, context={"request": request}
                ).data,
            }
        )


# ---------------------------------------------------------------------------
# Data freshness
# ---------------------------------------------------------------------------


@api_view(["GET"])
def data_freshness(request: Request) -> Response:
    """Return the date of the most recent ingested game per league.

    Returns
    -------
    Response
        ``{"lastUpdated": "YYYY-MM-DD" | null, "byLeague": [{"slug", "name", "lastGameDate"}]}``
    """
    leagues = League.objects.all().order_by("level")
    by_league = []
    overall_max = None
    for league in leagues:
        agg = Game.objects.filter(season__league=league).aggregate(last=Max("date"))
        last = agg["last"]
        if last:
            # Normalize to date string regardless of whether the field is datetime or date.
            last_date = last.date() if hasattr(last, "date") else last
            last_str = last_date.isoformat()
            if overall_max is None or last_date > overall_max:
                overall_max = last_date
        else:
            last_str = None
        by_league.append({"slug": league.slug, "name": league.name, "lastGameDate": last_str})
    return Response(
        {
            "lastUpdated": overall_max.isoformat() if overall_max else None,
            "byLeague": by_league,
        }
    )
