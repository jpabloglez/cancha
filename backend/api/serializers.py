"""DRF serializers for the public read API (spec §5.2).

These serialize the ORM entities exposed by the read-only public endpoints.
Output is camelCased globally by ``djangorestframework-camel-case``.
"""

from rest_framework import serializers

from games.models import Game, TeamGameStats
from players.models import (
    CareerEntry,
    Person,
    PlayerGameStats,
    PlayerSeasonAggregate,
    RosterEntry,
)
from teams.models import League, MediaAsset, Season, Team, TeamSeason


class MediaAssetSerializer(serializers.ModelSerializer):
    """Serialize a media asset to a servable URL (or null) plus attribution.

    Exposes the stored file URL only when a binary is present and the asset is
    not under a takedown; otherwise ``url`` is null and the frontend falls back
    to a generated avatar/crest (docs/team-member-enrichment-plan.md §4.3). The
    upstream ``source_url`` is intentionally not exposed (no hotlinking).
    """

    url = serializers.SerializerMethodField()

    class Meta:
        model = MediaAsset
        fields = ["url", "attribution", "license"]

    def get_url(self, obj: MediaAsset) -> str | None:
        """Return the media file path, or None if unavailable.

        Returns a root-relative path (e.g. ``/media/...``) so the frontend
        can prepend whichever host serves media in the current environment.
        Using ``build_absolute_uri`` is deliberately avoided: in Docker, SSR
        requests arrive at the internal ``backend`` hostname, which the browser
        cannot resolve, so the embedded URL would be unreachable.

        Parameters
        ----------
        obj : MediaAsset
            The asset being serialized.

        Returns
        -------
        str or None
            Root-relative media path when available, else None.
        """
        if not obj.is_available:
            return None
        return obj.file.url


_LEAGUE_LOGO_FILES: dict[str, str] = {
    "acb": "acb_logo.jpg",
    "primera-feb": "feb_logo.png",
    "segunda-feb": "feb_logo.png",
}


class LeagueSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~teams.models.League`.

    ``seasons_count`` and ``teams_count`` are populated by annotations on the
    viewset queryset, not by ORM relations, so they are declared as read-only
    integer fields rather than relational fields.

    ``logo`` is resolved from a slug→filename map pointing at static files
    already present under ``media/media_assets/leagues/``.
    """

    seasons_count = serializers.IntegerField(read_only=True, default=0)
    teams_count = serializers.IntegerField(read_only=True, default=0)
    logo = serializers.SerializerMethodField()

    class Meta:
        model = League
        fields = [
            "id", "name", "slug", "level", "country",
            "seasons_count", "teams_count", "logo",
        ]

    def get_logo(self, obj: League) -> dict | None:
        """Return a MediaAsset-shaped dict for the league logo, or None.

        Parameters
        ----------
        obj : League
            The league being serialized.

        Returns
        -------
        dict or None
            ``{url, attribution, license}`` matching the MediaAsset shape, or
            None when no logo file is registered for this slug.
        """
        filename = _LEAGUE_LOGO_FILES.get(obj.slug)
        if not filename:
            return None
        return {
            "url": f"/media/media_assets/leagues/{filename}",
            "attribution": "",
            "license": "",
        }


class SeasonSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~teams.models.Season`."""

    class Meta:
        model = Season
        fields = ["id", "league", "name", "start_date", "end_date"]


class TeamSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~teams.models.Team` with branding metadata."""

    logo = MediaAssetSerializer(read_only=True)

    class Meta:
        model = Team
        fields = [
            "id", "name", "short_name", "slug", "city", "founded_year",
            "official_name", "arena", "primary_color", "secondary_color",
            "website", "logo",
        ]


class TeamSeasonSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~teams.models.TeamSeason` with nested team."""

    team = TeamSerializer(read_only=True)

    class Meta:
        model = TeamSeason
        fields = ["id", "team", "season", "league"]


class CareerEntrySerializer(serializers.ModelSerializer):
    """Serialize a single career-timeline (trajectory) entry."""

    team_slug: serializers.SlugRelatedField = serializers.SlugRelatedField(
        source="team", slug_field="slug", read_only=True
    )

    class Meta:
        model = CareerEntry
        fields = ["season_label", "club_name", "league_name", "team_slug"]


class PersonSerializer(serializers.ModelSerializer):
    """Serialize a :class:`~players.models.Person` with biography + photo."""

    photo = MediaAssetSerializer(read_only=True)

    class Meta:
        model = Person
        fields = [
            "id", "first_name", "last_name", "slug", "birth_date", "nationality",
            "display_name", "birth_city", "birth_country", "height_cm",
            "weight_kg", "primary_position", "dominant_hand", "photo",
        ]


class PersonDetailSerializer(PersonSerializer):
    """Player detail: biography plus the full career timeline (trajectory)."""

    career = CareerEntrySerializer(many=True, read_only=True)

    class Meta(PersonSerializer.Meta):
        fields = [*PersonSerializer.Meta.fields, "career"]


class PlayerSeasonAggregateSerializer(serializers.ModelSerializer):
    """Serialize a player's per-season aggregate, basic + advanced metrics."""

    class Meta:
        model = PlayerSeasonAggregate
        fields = [
            "id",
            "person",
            "season",
            "games_played",
            "minutes_per_game",
            "points_per_game",
            "rebounds_per_game",
            "assists_per_game",
            "per",
            "ts_percent",
            "usage_rate",
            "efg_percent",
            "three_point_rate",
            "free_throw_rate",
            "tov_percent",
            "mp_percent",
            "orb_percent",
            "drb_percent",
            "ast_percent",
        ]


class GameSerializer(serializers.ModelSerializer):
    """Serialize a finished :class:`~games.models.Game` with its two teams.

    ``home_team`` / ``away_team`` are nested (name + crest) so games lists and
    box-score headers can render the clubs without a second lookup; the
    ``*_team_season`` ids are kept for matching player/team box-score lines.
    """

    home_team = TeamSerializer(source="home_team_season.team", read_only=True)
    away_team = TeamSerializer(source="away_team_season.team", read_only=True)

    class Meta:
        model = Game
        fields = [
            "id",
            "season",
            "home_team_season",
            "away_team_season",
            "home_team",
            "away_team",
            "date",
            "final_score_home",
            "final_score_away",
            "round",
        ]


class RosterEntrySerializer(serializers.ModelSerializer):
    """Serialize a roster entry with its nested player."""

    person = PersonSerializer(read_only=True)

    class Meta:
        model = RosterEntry
        fields = [
            "id",
            "person",
            "jersey_number",
            "position",
            "height_cm",
            "weight_kg",
        ]


class RosterEntryWithStatsSerializer(RosterEntrySerializer):
    """Extend the roster entry with per-season aggregate stats.

    Requires the serializer context to contain ``agg_by_person``, a dict
    mapping ``person_id`` to a :class:`~players.models.PlayerSeasonAggregate`.
    """

    stats = serializers.SerializerMethodField()

    class Meta(RosterEntrySerializer.Meta):
        fields = [*RosterEntrySerializer.Meta.fields, "stats"]

    def get_stats(self, obj: RosterEntry) -> dict | None:
        """Return rounded per-season averages or None when absent.

        Parameters
        ----------
        obj : RosterEntry
            The roster entry being serialized.

        Returns
        -------
        dict or None
            Keys: games_played, minutes_per_game, points_per_game,
            rebounds_per_game, assists_per_game, per, ts_percent.
        """
        agg_map: dict = self.context.get("agg_by_person", {})
        agg = agg_map.get(obj.person_id)
        if agg is None:
            return None
        return {
            "games_played": agg.games_played,
            "minutes_per_game": round(agg.minutes_per_game, 1),
            "points_per_game": round(agg.points_per_game, 1),
            "rebounds_per_game": round(agg.rebounds_per_game, 1),
            "assists_per_game": round(agg.assists_per_game, 1),
            "per": round(agg.per, 1),
            "ts_percent": round(agg.ts_percent, 1),
        }


class StandingSerializer(serializers.Serializer):
    """A single team's standing row, computed from finished games.

    Attributes
    ----------
    team_season_id : int
        Identifier of the team-season.
    team_name : str
        Full team name.
    team_slug : str
        URL-safe team identifier.
    games_played, wins, losses : int
        Win/loss record.
    points_for, points_against : int
        Total points scored and conceded.
    point_difference : int
        ``points_for - points_against``.
    """

    team_season_id = serializers.IntegerField()
    team_name = serializers.CharField()
    team_slug = serializers.CharField()
    team_logo = MediaAssetSerializer(allow_null=True)
    team_primary_color = serializers.CharField(allow_blank=True)
    games_played = serializers.IntegerField()
    wins = serializers.IntegerField()
    losses = serializers.IntegerField()
    points_for = serializers.IntegerField()
    points_against = serializers.IntegerField()
    point_difference = serializers.IntegerField()


class PlayerBoxScoreSerializer(serializers.ModelSerializer):
    """Serialize one player's line within a game box score."""

    person = PersonSerializer(read_only=True)

    class Meta:
        model = PlayerGameStats
        fields = [
            "person",
            "team_season",
            "minutes_played",
            "points",
            "rebounds_off",
            "rebounds_def",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "fouls",
            "field_goals_made",
            "field_goals_att",
            "three_point_made",
            "three_point_att",
            "free_throws_made",
            "free_throws_att",
        ]


class TeamBoxScoreSerializer(serializers.ModelSerializer):
    """Serialize a team's totals within a game box score."""

    class Meta:
        model = TeamGameStats
        fields = [
            "team_season",
            "points",
            "rebounds_off",
            "rebounds_def",
            "assists",
            "steals",
            "blocks",
            "turnovers",
            "fouls",
            "field_goals_made",
            "field_goals_att",
            "three_point_made",
            "three_point_att",
            "free_throws_made",
            "free_throws_att",
            "possessions",
            "pace",
        ]


class BoxScoreSerializer(serializers.Serializer):
    """Full box score for a game: the game plus team and player lines."""

    game = GameSerializer()
    team_stats = TeamBoxScoreSerializer(many=True)
    player_stats = PlayerBoxScoreSerializer(many=True)


class LeaderSerializer(serializers.Serializer):
    """A single ranked entry in a statistical leaders table.

    Attributes
    ----------
    player_id : int
        Identifier of the player.
    player_name : str
        Full player name.
    player_slug : str
        URL-safe player identifier.
    season_id : int
        Identifier of the season.
    stat : str
        The statistic key being ranked (e.g. "points_per_game").
    value : float
        The player's value for that statistic.
    photo : MediaAsset or None
        The player's headshot reference (``url`` null when none is stored).
    team : Team or None
        The team the player belongs to in this season.
    """

    player_id = serializers.IntegerField()
    player_name = serializers.CharField()
    player_slug = serializers.CharField()
    season_id = serializers.IntegerField()
    stat = serializers.CharField()
    value = serializers.FloatField()
    photo = MediaAssetSerializer(allow_null=True)
    team = TeamSerializer(allow_null=True)


class AllTimeLeaderSerializer(serializers.Serializer):
    """A single entry in the cross-season all-time statistical ranking.

    Attributes
    ----------
    player_id : int
        Person primary key.
    player_name : str
        Full display name.
    player_slug : str
        URL-safe player identifier.
    photo : MediaAsset or None
        Player headshot.
    nationality : str or None
        ISO nationality code.
    primary_position : str or None
        Primary playing position (PG/SG/SF/PF/C).
    total_games : int
        Career games played across all included seasons.
    seasons_count : int
        Number of distinct seasons included.
    leagues : list[str]
        Distinct league slugs the player appeared in.
    total_points : float
        Cumulative career points.
    total_rebounds : float
        Cumulative career rebounds.
    total_assists : float
        Cumulative career assists.
    ppg : float
        Career points per game.
    rpg : float
        Career rebounds per game.
    apg : float
        Career assists per game.
    spg : float
        Career steals per game.
    bpg : float
        Career blocks per game.
    topg : float
        Career turnovers per game.
    two_percent : float
        Games-weighted career two-point percentage.
    three_percent : float
        Games-weighted career three-point percentage.
    ft_percent : float
        Games-weighted career free-throw percentage.
    per : float or None
        Games-weighted career PER.
    ts_percent : float
        Games-weighted career True Shooting percentage.
    stat_value : float
        The primary ranked stat value (mirrors the sorted column).
    """

    player_id = serializers.IntegerField()
    player_name = serializers.CharField()
    player_slug = serializers.CharField()
    photo = MediaAssetSerializer(allow_null=True)
    nationality = serializers.CharField(allow_null=True)
    primary_position = serializers.CharField(allow_null=True)
    total_games = serializers.IntegerField()
    seasons_count = serializers.IntegerField()
    leagues = serializers.ListField(child=serializers.CharField())
    total_points = serializers.FloatField()
    total_rebounds = serializers.FloatField()
    total_assists = serializers.FloatField()
    ppg = serializers.FloatField()
    rpg = serializers.FloatField()
    apg = serializers.FloatField()
    spg = serializers.FloatField()
    bpg = serializers.FloatField()
    topg = serializers.FloatField()
    two_percent = serializers.FloatField()
    three_percent = serializers.FloatField()
    ft_percent = serializers.FloatField()
    per = serializers.FloatField(allow_null=True)
    ts_percent = serializers.FloatField()
    stat_value = serializers.FloatField()


class PlayerOfTheDaySerializer(serializers.Serializer):
    """Player of the day: full bio plus latest season stats.

    Attributes
    ----------
    player : PersonDetail
        Full player bio with career timeline.
    latest_stats : dict or None
        The player's most recent season aggregate, or None if not yet ingested.
    """

    player = PersonDetailSerializer()
    latest_stats = serializers.DictField(allow_null=True)
