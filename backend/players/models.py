"""People, roster/staff links and player statistics (spec §4.2-§4.3).

``Person`` is the shared base entity for anyone in the system — players and
technical staff alike. Roster and staff entries link a person to a specific
team-season, and ``PlayerGameStats`` / ``PlayerSeasonAggregate`` hold the
box-score and derived statistics respectively.
"""

from django.db import models


class Person(models.Model):
    """Base entity for any individual: player or technical staff member.

    Attributes
    ----------
    first_name : str
        Given name.
    last_name : str
        Family name.
    slug : str
        URL-safe identifier used by frontend routes.
    birth_date : date or None
        Date of birth.
    nationality : str or None
        ISO 3166-1 alpha-2 country code of nationality.
    """

    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=160, unique=True)
    birth_date = models.DateField(null=True, blank=True)
    nationality = models.CharField(max_length=2, null=True, blank=True)
    # Biography populated by the enrichment pipeline (separate from the
    # box-score path), see docs/team-member-enrichment-plan.md §4.1. ``height_cm``
    # / ``weight_kg`` here are the latest-known values for the bio card; the
    # per-season values live on ``RosterEntry``.
    display_name = models.CharField(max_length=200, blank=True, default="")
    birth_city = models.CharField(max_length=100, blank=True, default="")
    birth_country = models.CharField(max_length=2, blank=True, default="")
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)
    primary_position = models.CharField(max_length=2, blank=True, default="")
    dominant_hand = models.CharField(max_length=1, blank=True, default="")
    photo = models.ForeignKey(
        "teams.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="photo_for_persons",
    )
    # External identity for idempotent ingestion (spec §3.3).
    source = models.CharField(max_length=50, db_index=True)
    external_id = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["last_name", "first_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_person_external_ref"
            )
        ]

    def __str__(self) -> str:
        """Return "<first> <last>" for admin and logging output."""
        return f"{self.first_name} {self.last_name}"


class CareerEntry(models.Model):
    """A single club/season stint in a player's career timeline (trajectory).

    ``RosterEntry`` only covers team-seasons inside the leagues we ingest;
    ``CareerEntry`` records the full timeline a source exposes — including clubs
    or competitions we don't model — as mostly free text
    (docs/team-member-enrichment-plan.md §4.4). Populated solely from the FEB/ACB
    player-page season histories for now; nothing is fabricated. When a stint
    maps onto a known club, ``team`` is linked so the UI can deep-link.

    Attributes
    ----------
    person : Person
        The player whose career this entry belongs to.
    season_label : str
        Season as printed by the source, e.g. "2019-2020".
    club_name : str
        Club name as printed (may be a foreign or youth club we don't model).
    league_name : str
        Competition name, when the source provides it.
    team : teams.Team or None
        Linked club when the stint maps to a known team; null otherwise.
    source : str
        Connector id that produced the entry.
    external_id : str
        The source's own stable id for this stint (idempotency key).
    """

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="career"
    )
    season_label = models.CharField(max_length=20)
    club_name = models.CharField(max_length=150)
    league_name = models.CharField(max_length=100, blank=True, default="")
    team = models.ForeignKey(
        "teams.Team",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="career_entries",
    )
    source = models.CharField(max_length=50, db_index=True)
    external_id = models.CharField(max_length=100, db_index=True)

    class Meta:
        verbose_name_plural = "career entries"
        ordering = ["-season_label", "club_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"],
                name="unique_career_entry_external_ref",
            )
        ]

    def __str__(self) -> str:
        """Return "<person> — <season>: <club>" for admin output."""
        return f"{self.person} — {self.season_label}: {self.club_name}"


class RosterEntry(models.Model):
    """Link between a player and a team for a given season.

    Attributes
    ----------
    person : Person
        The player.
    team_season : teams.TeamSeason
        The team-season this roster entry belongs to.
    jersey_number : int or None
        Shirt number worn by the player.
    position : str or None
        Playing position (PG, SG, SF, PF, C).
    height_cm : int or None
        Player height in centimeters.
    weight_kg : int or None
        Player weight in kilograms.
    """

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="roster_entries"
    )
    team_season = models.ForeignKey(
        "teams.TeamSeason", on_delete=models.CASCADE, related_name="roster_entries"
    )
    jersey_number = models.PositiveSmallIntegerField(null=True, blank=True)
    position = models.CharField(max_length=2, null=True, blank=True)
    height_cm = models.PositiveSmallIntegerField(null=True, blank=True)
    weight_kg = models.PositiveSmallIntegerField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "team_season"],
                name="unique_player_per_team_season",
            )
        ]

    def __str__(self) -> str:
        """Return "<person> (<team_season>)" for admin output."""
        return f"{self.person} ({self.team_season})"


class StaffEntry(models.Model):
    """Link between a technical staff member and a team for a given season.

    Attributes
    ----------
    person : Person
        The staff member.
    team_season : teams.TeamSeason
        The team-season this staff entry belongs to.
    role : str
        Role within the staff (head coach, assistant, GM, physio…).
    """

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="staff_entries"
    )
    team_season = models.ForeignKey(
        "teams.TeamSeason", on_delete=models.CASCADE, related_name="staff_entries"
    )
    role = models.CharField(max_length=50)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "team_season", "role"],
                name="unique_staff_role_per_team_season",
            )
        ]

    def __str__(self) -> str:
        """Return "<role>: <person>" for admin output."""
        return f"{self.role}: {self.person}"


class PlayerGameStats(models.Model):
    """Box score statistics for a single player in a single game.

    Attributes
    ----------
    game : games.Game
        The game this stat line belongs to.
    person : Person
        The player.
    team_season : teams.TeamSeason
        The team the player represented in this game.
    minutes_played : int
        Minutes played in the game.
    points, rebounds_off, rebounds_def, assists, steals, blocks,
    turnovers, fouls : int
        Standard box score counting statistics.
    field_goals_made, field_goals_att, three_point_made, three_point_att,
    free_throws_made, free_throws_att : int
        Shooting statistics broken down by shot type.
    """

    game = models.ForeignKey(
        "games.Game", on_delete=models.CASCADE, related_name="player_stats"
    )
    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="game_stats"
    )
    team_season = models.ForeignKey(
        "teams.TeamSeason", on_delete=models.CASCADE, related_name="player_game_stats"
    )
    minutes_played = models.PositiveSmallIntegerField()
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

    class Meta:
        verbose_name_plural = "player game stats"
        constraints = [
            models.UniqueConstraint(
                fields=["game", "person"], name="unique_player_stat_per_game"
            )
        ]

    def __str__(self) -> str:
        """Return "<person> — <game>" for admin output."""
        return f"{self.person} — {self.game}"


class PlayerSeasonAggregate(models.Model):
    """Materialized per-season averages and advanced metrics for a player.

    Recomputed by the statistics engine after each ingestion run rather than
    queried live, to keep aggregate endpoints cheap (spec §4.2, §4.4).

    Attributes
    ----------
    person : Person
        The player.
    season : teams.Season
        The season the aggregate summarizes.
    games_played : int
        Number of games included in the aggregate.
    minutes_per_game, points_per_game, rebounds_per_game,
    assists_per_game : float
        Basic per-game averages.
    per, ts_percent, usage_rate, efg_percent : float
        Derived advanced metrics (spec §4.4).
    """

    person = models.ForeignKey(
        Person, on_delete=models.CASCADE, related_name="season_aggregates"
    )
    season = models.ForeignKey(
        "teams.Season", on_delete=models.CASCADE, related_name="player_aggregates"
    )
    games_played = models.PositiveSmallIntegerField(default=0)
    minutes_per_game = models.FloatField(default=0.0)
    points_per_game = models.FloatField(default=0.0)
    rebounds_per_game = models.FloatField(default=0.0)
    assists_per_game = models.FloatField(default=0.0)
    per = models.FloatField(default=0.0)
    ts_percent = models.FloatField(default=0.0)
    usage_rate = models.FloatField(default=0.0)
    efg_percent = models.FloatField(default=0.0)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["person", "season"], name="unique_aggregate_per_season"
            )
        ]

    def __str__(self) -> str:
        """Return "<person> — <season>" for admin output."""
        return f"{self.person} — {self.season}"
