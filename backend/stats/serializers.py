"""DRF serializers for statistics endpoints (spec §5.3).

JSON is rendered in camelCase project-wide via ``djangorestframework-camel-case``
(configured in settings ``REST_FRAMEWORK``), so these snake_case field names map
to camelCase keys consumed by the TypeScript frontend.
"""

from rest_framework import serializers


class AdvancedStatsSerializer(serializers.Serializer):
    """Advanced, derived statistics for a player-season.

    Attributes
    ----------
    true_shooting_percent : float
        Shooting efficiency accounting for 2P, 3P and free throws.
    effective_field_goal_percent : float
        Field goal efficiency weighting three-pointers higher.
    usage_rate : float
        Percentage of team plays used by the player while on court.
    player_efficiency_rating : float
        Per-minute composite production index.
    """

    true_shooting_percent = serializers.FloatField()
    effective_field_goal_percent = serializers.FloatField()
    usage_rate = serializers.FloatField()
    player_efficiency_rating = serializers.FloatField()


class PlayerSeasonStatsSerializer(serializers.Serializer):
    """Aggregated per-season statistics for a single player.

    Attributes
    ----------
    player_id : str
        Identifier of the player.
    season_id : str
        Identifier of the season.
    games_played : int
        Number of games played in the season.
    minutes_per_game, points_per_game, rebounds_per_game,
    assists_per_game : float
        Basic per-game averages.
    advanced : AdvancedStatsSerializer
        Nested advanced metrics block.
    """

    player_id = serializers.CharField()
    season_id = serializers.CharField()
    season_name = serializers.CharField()
    games_played = serializers.IntegerField()
    minutes_per_game = serializers.FloatField()
    points_per_game = serializers.FloatField()
    rebounds_per_game = serializers.FloatField()
    assists_per_game = serializers.FloatField()
    advanced = AdvancedStatsSerializer()
