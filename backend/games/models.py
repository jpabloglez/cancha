"""Game and team-game statistics entities (spec §4.2-§4.3).

Only finished games are ever persisted — the system is post-game by design
and never ingests live or in-progress data (spec §1.3, §3.3).
"""

from django.db import models


class Game(models.Model):
    """A finished game between two team-seasons.

    Attributes
    ----------
    season : teams.Season
        Season the game belongs to.
    home_team_season : teams.TeamSeason
        Home participant.
    away_team_season : teams.TeamSeason
        Away participant.
    date : datetime
        Tip-off date and time (timezone-aware).
    final_score_home : int
        Final points for the home team.
    final_score_away : int
        Final points for the away team.
    round : str or None
        Competition round / matchday label.
    """

    season = models.ForeignKey(
        "teams.Season", on_delete=models.CASCADE, related_name="games"
    )
    home_team_season = models.ForeignKey(
        "teams.TeamSeason", on_delete=models.CASCADE, related_name="home_games"
    )
    away_team_season = models.ForeignKey(
        "teams.TeamSeason", on_delete=models.CASCADE, related_name="away_games"
    )
    date = models.DateTimeField()
    final_score_home = models.PositiveSmallIntegerField()
    final_score_away = models.PositiveSmallIntegerField()
    round = models.CharField(max_length=50, null=True, blank=True)
    # External identity for idempotent ingestion (spec §3.3).
    source = models.CharField(max_length=50, db_index=True)
    external_id = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_game_external_ref"
            )
        ]

    def __str__(self) -> str:
        """Return "home vs away (date)" for admin output."""
        return (
            f"{self.home_team_season.team.short_name} vs "
            f"{self.away_team_season.team.short_name} "
            f"({self.date:%Y-%m-%d})"
        )


class TeamGameStats(models.Model):
    """Aggregated team statistics for a single game, plus pace/possessions.

    Attributes
    ----------
    game : Game
        The game this stat line belongs to.
    team_season : teams.TeamSeason
        The team these totals belong to.
    points, rebounds_off, rebounds_def, assists, steals, blocks,
    turnovers, fouls : int
        Team box score totals.
    field_goals_made, field_goals_att, three_point_made, three_point_att,
    free_throws_made, free_throws_att : int
        Team shooting totals broken down by shot type.
    possessions : float
        Estimated number of possessions for the team in this game.
    pace : float
        Estimated possessions per 40 minutes.
    """

    game = models.ForeignKey(
        Game, on_delete=models.CASCADE, related_name="team_stats"
    )
    team_season = models.ForeignKey(
        "teams.TeamSeason", on_delete=models.CASCADE, related_name="team_game_stats"
    )
    points = models.PositiveSmallIntegerField()
    rebounds_off = models.PositiveSmallIntegerField()
    rebounds_def = models.PositiveSmallIntegerField()
    assists = models.PositiveSmallIntegerField()
    steals = models.PositiveSmallIntegerField()
    blocks = models.PositiveSmallIntegerField()
    turnovers = models.PositiveSmallIntegerField()
    fouls = models.PositiveSmallIntegerField()
    field_goals_made = models.PositiveSmallIntegerField()
    field_goals_att = models.PositiveSmallIntegerField()
    three_point_made = models.PositiveSmallIntegerField()
    three_point_att = models.PositiveSmallIntegerField()
    free_throws_made = models.PositiveSmallIntegerField()
    free_throws_att = models.PositiveSmallIntegerField()
    possessions = models.FloatField(default=0.0)
    pace = models.FloatField(default=0.0)

    class Meta:
        verbose_name_plural = "team game stats"
        constraints = [
            models.UniqueConstraint(
                fields=["game", "team_season"], name="unique_team_stat_per_game"
            )
        ]

    def __str__(self) -> str:
        """Return "<team> — <game>" for admin output."""
        return f"{self.team_season.team.short_name} — {self.game}"
