"""Competition and team entities (spec §4.2-§4.3).

Holds the stable, time-spanning entities at the top of the data model:
``League`` and ``Team``, the per-season ``Season`` and the ``TeamSeason``
junction that records a team's participation in a given season/league.
"""

from django.db import models


class League(models.Model):
    """Basketball competition (e.g. ACB, LEB Oro, LEB Plata).

    The FEB renamed LEB Oro to "Primera FEB" and LEB Plata to "Segunda FEB"
    from the 2024-25 season; connectors must map both the historical and the
    current name onto the same ``League`` row (spec §3.1, §12.2).

    Attributes
    ----------
    name : str
        Canonical competition name.
    slug : str
        URL-safe identifier used by frontend routes (e.g. "acb").
    level : int
        Competition tier, 1 being the top division.
    country : str
        ISO 3166-1 alpha-2 country code, defaults to Spain.
    """

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=50, unique=True)
    level = models.PositiveSmallIntegerField()
    country = models.CharField(max_length=2, default="ES")

    class Meta:
        ordering = ["level", "name"]

    def __str__(self) -> str:
        """Return the league name for admin and logging output."""
        return self.name


class Season(models.Model):
    """A single season of a given league.

    Attributes
    ----------
    league : League
        League this season belongs to.
    name : str
        Human-readable season label, e.g. "2025-2026".
    start_date : date
        Season start date.
    end_date : date or None
        Season end date, null while the season is ongoing.
    """

    league = models.ForeignKey(
        League, on_delete=models.CASCADE, related_name="seasons"
    )
    name = models.CharField(max_length=20)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["league", "name"], name="unique_season_per_league"
            )
        ]

    def __str__(self) -> str:
        """Return "<league> <season>" for admin and logging output."""
        return f"{self.league.name} {self.name}"


class Team(models.Model):
    """A club entity, stable across seasons.

    Attributes
    ----------
    name : str
        Full team name.
    short_name : str
        Abbreviated name used in compact UI elements.
    slug : str
        URL-safe identifier used by frontend routes.
    city : str or None
        City where the team is based.
    founded_year : int or None
        Year the club was founded.
    """

    name = models.CharField(max_length=150)
    short_name = models.CharField(max_length=20)
    slug = models.SlugField(max_length=60, unique=True)
    city = models.CharField(max_length=100, null=True, blank=True)
    founded_year = models.PositiveSmallIntegerField(null=True, blank=True)
    # Branding/metadata populated by the enrichment pipeline (separate from the
    # box-score path), see docs/team-member-enrichment-plan.md §4.1.
    official_name = models.CharField(max_length=200, blank=True, default="")
    arena = models.CharField(max_length=150, blank=True, default="")
    primary_color = models.CharField(max_length=7, blank=True, default="")
    secondary_color = models.CharField(max_length=7, blank=True, default="")
    website = models.URLField(blank=True, default="")
    logo = models.ForeignKey(
        "teams.MediaAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logo_for_teams",
    )
    # External identity for idempotent ingestion (spec §3.3): a connector
    # re-running must not duplicate rows. ``source`` is the connector id
    # (e.g. "acb", "seed"); ``external_id`` is the source's own key.
    source = models.CharField(max_length=50, db_index=True)
    external_id = models.CharField(max_length=100, db_index=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["source", "external_id"], name="unique_team_external_ref"
            )
        ]

    def __str__(self) -> str:
        """Return the team name for admin and logging output."""
        return self.name


class TeamSeason(models.Model):
    """Participation of a team in a specific season and league.

    A club may change tier across seasons (e.g. promotion/relegation), so the
    league is recorded per participation rather than on ``Team`` (spec §4.2).

    Attributes
    ----------
    team : Team
        The participating club.
    season : Season
        The season of participation.
    league : League
        The league the team competed in that season.
    """

    team = models.ForeignKey(
        Team, on_delete=models.CASCADE, related_name="team_seasons"
    )
    season = models.ForeignKey(
        Season, on_delete=models.CASCADE, related_name="team_seasons"
    )
    league = models.ForeignKey(
        League, on_delete=models.CASCADE, related_name="team_seasons"
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["team", "season"], name="unique_team_per_season"
            )
        ]

    def __str__(self) -> str:
        """Return "<team> @ <season>" for admin and logging output."""
        return f"{self.team.short_name} @ {self.season.name}"


def _media_asset_upload_path(instance: "MediaAsset", filename: str) -> str:
    """Route uploaded files to the correct subfolder based on asset kind.

    Parameters
    ----------
    instance : MediaAsset
        The asset being saved (``kind`` must already be set).
    filename : str
        Original filename provided by the uploader.

    Returns
    -------
    str
        Relative path under ``MEDIA_ROOT``, e.g.
        ``media_assets/players/player_photo_1.jpg``.
    """
    subdir = "teams" if instance.kind == "team_logo" else "players"
    return f"media_assets/{subdir}/{filename}"


class MediaAsset(models.Model):
    """An external image (team logo, player or staff photo) with provenance.

    Centralises media handling so licensing, attribution and takedown live in
    one place (docs/team-member-enrichment-plan.md §4.2). Following the
    dbasket.net precedent for open, non-commercial Spanish-basketball sites,
    assets are sourced from official free-distribution channels (ACB
    ``mediacenter.acb.com``; FEB / club assets otherwise), stored with per-asset
    attribution, and removable on a rights-holder request via ``taken_down``
    without losing the provenance record (spec §10).

    Lives in the ``teams`` app — the lowest app in the dependency graph — so both
    ``Team`` and ``players.Person`` can reference it without a circular import.

    Attributes
    ----------
    kind : str
        Asset category (team logo, player photo, staff photo).
    source : str
        Connector id that recorded the asset (e.g. "acb", "feb-primera").
    source_url : str
        Absolute URL the asset was (or would be) fetched from — the provenance
        and idempotency key.
    file : FileField
        The stored binary, populated only when ``INGEST_STORE_MEDIA`` is enabled
        and the download succeeded; empty otherwise (the frontend then falls
        back to a generated avatar/crest).
    license : str
        Short license / rights note (e.g. "©ACB via mediacenter.acb.com").
    attribution : str
        Human-readable credit displayed alongside the asset.
    checksum : str
        SHA-256 of the stored bytes, used to skip re-downloading unchanged files.
    taken_down : bool
        When True the asset is hidden and never re-downloaded (rights request).
    fetched_at : datetime or None
        When the file was last downloaded; null while only referenced.
    """

    class Kind(models.TextChoices):
        TEAM_LOGO = "team_logo", "Team logo"
        PLAYER_PHOTO = "player_photo", "Player photo"
        STAFF_PHOTO = "staff_photo", "Staff photo"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    source = models.CharField(max_length=50, db_index=True)
    source_url = models.URLField(max_length=500, unique=True)
    file = models.FileField(upload_to=_media_asset_upload_path, blank=True)
    license = models.CharField(max_length=200, blank=True, default="")
    attribution = models.CharField(max_length=200, blank=True, default="")
    checksum = models.CharField(max_length=64, blank=True, default="")
    taken_down = models.BooleanField(default=False)
    fetched_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["kind", "source_url"]

    @property
    def is_available(self) -> bool:
        """Return whether the stored file may be served (present, not taken down).

        Returns
        -------
        bool
            True when a binary is stored and the asset is not under a takedown.
        """
        return bool(self.file) and not self.taken_down

    def take_down(self) -> None:
        """Honour a rights-holder takedown request for this asset.

        Sets ``taken_down``, deletes the stored binary and clears the checksum,
        while keeping the row for provenance. The download stage refuses to
        re-fetch a taken-down asset, so the removal is permanent until explicitly
        cleared (docs/team-member-enrichment-plan.md §3).

        Returns
        -------
        None
            Persists the change to the database.
        """
        self.taken_down = True
        if self.file:
            self.file.delete(save=False)
        self.checksum = ""
        self.save(update_fields=["taken_down", "file", "checksum"])

    def __str__(self) -> str:
        """Return "<kind>: <source_url>" for admin output."""
        return f"{self.kind}: {self.source_url}"
