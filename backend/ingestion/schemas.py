"""Canonical normalized schemas for the ingestion pipeline (spec §3.3).

These strict Pydantic models are the contract between the *normalize* stage and
the *persist* stage. Connectors (and the seed command) translate heterogeneous
raw payloads into these shapes; :mod:`ingestion.persistence` is the only code
that turns them into ORM rows. Every entity a connector creates carries the
``source`` + ``external_id`` pair used for idempotent upserts.

Notes
-----
Validation here is deliberately strict (``extra="forbid"``) so a source that
silently changes shape fails loudly at the boundary rather than persisting
corrupt data (spec §3.3, tolerance to source changes).
"""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class _Strict(BaseModel):
    """Base model forbidding unknown fields and validating on assignment."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ExternalRef(_Strict):
    """Identity of a record as exposed by an external source.

    Attributes
    ----------
    source : str
        Connector id that produced the record (e.g. "acb", "seed").
    external_id : str
        The source's own stable identifier for the record.
    """

    source: str = Field(min_length=1, max_length=50)
    external_id: str = Field(min_length=1, max_length=100)


class NormalizedTeam(_Strict):
    """A club normalized to the canonical model.

    Attributes
    ----------
    ref : ExternalRef
        External identity used for idempotent upsert.
    name : str
        Full team name.
    short_name : str
        Abbreviated name for compact UI.
    slug : str
        URL-safe identifier.
    city : str or None
        Home city.
    founded_year : int or None
        Year the club was founded.
    """

    ref: ExternalRef
    name: str = Field(min_length=1, max_length=150)
    short_name: str = Field(min_length=1, max_length=20)
    slug: str = Field(min_length=1, max_length=60)
    city: str | None = None
    founded_year: int | None = Field(default=None, ge=1850, le=2100)


class NormalizedPerson(_Strict):
    """A person (player or staff) normalized to the canonical model.

    Attributes
    ----------
    ref : ExternalRef
        External identity used for idempotent upsert.
    first_name, last_name : str
        Given and family names.
    slug : str
        URL-safe identifier.
    birth_date : date or None
        Date of birth.
    nationality : str or None
        ISO 3166-1 alpha-2 nationality code.
    """

    ref: ExternalRef
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    slug: str = Field(min_length=1, max_length=160)
    birth_date: date | None = None
    nationality: str | None = Field(default=None, min_length=2, max_length=2)


class NormalizedRosterEntry(_Strict):
    """A player's roster membership for a team-season.

    Attributes
    ----------
    person_ref : ExternalRef
        Identity of the player.
    jersey_number : int or None
        Shirt number.
    position : str or None
        Playing position (PG, SG, SF, PF, C).
    height_cm : int or None
        Height in centimeters.
    weight_kg : int or None
        Weight in kilograms.
    """

    person_ref: ExternalRef
    jersey_number: int | None = Field(default=None, ge=0, le=99)
    position: str | None = Field(default=None, max_length=2)
    height_cm: int | None = Field(default=None, ge=120, le=260)
    weight_kg: int | None = Field(default=None, ge=40, le=200)


class NormalizedMediaRef(_Strict):
    """Reference to an external image (logo / photo) plus its attribution.

    The persistence stage records the provenance immediately; the binary itself
    is downloaded by a separate gated task (``INGEST_STORE_MEDIA``), so a media
    ref never carries the file bytes (docs/team-member-enrichment-plan.md §4.2).

    Attributes
    ----------
    source : str
        Connector id that recorded the asset.
    source_url : str
        Absolute URL of the asset (provenance + idempotency key).
    license : str or None
        Short rights note (e.g. "©ACB via mediacenter.acb.com").
    attribution : str or None
        Human-readable credit shown alongside the asset.
    """

    source: str = Field(min_length=1, max_length=50)
    source_url: str = Field(min_length=1, max_length=500)
    license: str | None = Field(default=None, max_length=200)
    attribution: str | None = Field(default=None, max_length=200)


class NormalizedCareerEntry(_Strict):
    """A single club/season stint in a player's career timeline.

    Attributes
    ----------
    ref : ExternalRef
        External identity of the stint (idempotent upsert key).
    season_label : str
        Season as printed by the source, e.g. "2019-2020".
    club_name : str
        Club name as printed.
    league_name : str or None
        Competition name when available.
    team_ref : ExternalRef or None
        Identity of a known team when the stint maps onto one; null otherwise.
    """

    ref: ExternalRef
    season_label: str = Field(min_length=1, max_length=20)
    club_name: str = Field(min_length=1, max_length=150)
    league_name: str | None = Field(default=None, max_length=100)
    team_ref: ExternalRef | None = None


class NormalizedPersonProfile(_Strict):
    """Biographic enrichment for an existing person (spec §4.2).

    Emitted by the *profile* path, separate from the box-score path that creates
    the ``Person``. All fields are optional: a source that omits one leaves the
    existing value untouched (persistence is fill/refresh, never clobber).

    Attributes
    ----------
    ref : ExternalRef
        Identity of the (already-persisted) person to enrich.
    display_name : str or None
        Source's preferred full name.
    birth_date : date or None
        Date of birth.
    birth_city, birth_country : str or None
        Place of birth (city, ISO 3166-1 alpha-2 country) — the player's origin.
    nationality : str or None
        ISO 3166-1 alpha-2 nationality code.
    height_cm, weight_kg : int or None
        Latest-known physicals (per-season values stay on ``RosterEntry``).
    primary_position : str or None
        Main playing position (PG, SG, SF, PF, C).
    dominant_hand : str or None
        Dominant hand ("R"/"L"), when known.
    photo : NormalizedMediaRef or None
        Reference to the player's photo.
    career : list of NormalizedCareerEntry
        Career timeline (trajectory) entries.
    """

    ref: ExternalRef
    display_name: str | None = Field(default=None, max_length=200)
    birth_date: date | None = None
    birth_city: str | None = Field(default=None, max_length=100)
    birth_country: str | None = Field(default=None, min_length=2, max_length=2)
    nationality: str | None = Field(default=None, min_length=2, max_length=2)
    height_cm: int | None = Field(default=None, ge=120, le=260)
    weight_kg: int | None = Field(default=None, ge=40, le=200)
    primary_position: str | None = Field(default=None, max_length=2)
    dominant_hand: str | None = Field(default=None, max_length=1)
    photo: NormalizedMediaRef | None = None
    career: list[NormalizedCareerEntry] = Field(default_factory=list)


class NormalizedTeamProfile(_Strict):
    """Branding / metadata enrichment for an existing team (spec §4.2).

    Emitted by the profile path, separate from the box-score path that creates
    the ``Team``. All fields are optional (fill/refresh, never clobber identity).

    Attributes
    ----------
    ref : ExternalRef
        Identity of the (already-persisted) team to enrich.
    official_name : str or None
        Full legal / sponsor name.
    arena : str or None
        Home pavilion name.
    primary_color, secondary_color : str or None
        Club colours as hex strings (for original branding, not the logo).
    website : str or None
        Official club website.
    city : str or None
        Home city (refreshed when the profile carries it).
    founded_year : int or None
        Year the club was founded.
    logo : NormalizedMediaRef or None
        Reference to the club crest/logo.
    """

    ref: ExternalRef
    official_name: str | None = Field(default=None, max_length=200)
    arena: str | None = Field(default=None, max_length=150)
    primary_color: str | None = Field(default=None, max_length=7)
    secondary_color: str | None = Field(default=None, max_length=7)
    website: str | None = Field(default=None, max_length=200)
    city: str | None = Field(default=None, max_length=100)
    founded_year: int | None = Field(default=None, ge=1850, le=2100)
    logo: NormalizedMediaRef | None = None


class NormalizedPlayerBoxScore(_Strict):
    """A single player's box-score line in a game.

    Attributes
    ----------
    person_ref : ExternalRef
        Identity of the player.
    team_ref : ExternalRef
        Identity of the team the player represented.
    minutes_played, points, rebounds_off, rebounds_def, assists, steals,
    blocks, turnovers, fouls : int
        Standard counting statistics.
    field_goals_made, field_goals_att, three_point_made, three_point_att,
    free_throws_made, free_throws_att : int
        Shooting statistics by shot type.
    """

    person_ref: ExternalRef
    team_ref: ExternalRef
    minutes_played: int = Field(ge=0, le=60)
    points: int = Field(ge=0)
    rebounds_off: int = Field(ge=0)
    rebounds_def: int = Field(ge=0)
    assists: int = Field(ge=0)
    steals: int = Field(ge=0)
    blocks: int = Field(ge=0)
    turnovers: int = Field(ge=0)
    fouls: int = Field(ge=0)
    field_goals_made: int = Field(ge=0)
    field_goals_att: int = Field(ge=0)
    three_point_made: int = Field(ge=0)
    three_point_att: int = Field(ge=0)
    free_throws_made: int = Field(ge=0)
    free_throws_att: int = Field(ge=0)


class NormalizedTeamBoxScore(_Strict):
    """A team's aggregated box-score totals in a game.

    Attributes
    ----------
    team_ref : ExternalRef
        Identity of the team.
    points, rebounds_off, rebounds_def, assists, steals, blocks, turnovers,
    fouls : int
        Team box-score totals.
    field_goals_made, field_goals_att, three_point_made, three_point_att,
    free_throws_made, free_throws_att : int
        Team shooting totals by shot type.
    """

    team_ref: ExternalRef
    points: int = Field(ge=0)
    rebounds_off: int = Field(ge=0)
    rebounds_def: int = Field(ge=0)
    assists: int = Field(ge=0)
    steals: int = Field(ge=0)
    blocks: int = Field(ge=0)
    turnovers: int = Field(ge=0)
    fouls: int = Field(ge=0)
    field_goals_made: int = Field(ge=0)
    field_goals_att: int = Field(ge=0)
    three_point_made: int = Field(ge=0)
    three_point_att: int = Field(ge=0)
    free_throws_made: int = Field(ge=0)
    free_throws_att: int = Field(ge=0)


class NormalizedGame(_Strict):
    """A finished game with both teams' and all players' box scores.

    Attributes
    ----------
    ref : ExternalRef
        External identity used for idempotent upsert.
    home_team_ref, away_team_ref : ExternalRef
        Identities of the participating teams.
    date : datetime
        Tip-off datetime (timezone-aware).
    final_score_home, final_score_away : int
        Final scores.
    round : str or None
        Competition round / matchday label.
    team_box_scores : list of NormalizedTeamBoxScore
        Team totals (typically two entries).
    player_box_scores : list of NormalizedPlayerBoxScore
        Per-player lines for the game.
    """

    ref: ExternalRef
    home_team_ref: ExternalRef
    away_team_ref: ExternalRef
    date: datetime
    final_score_home: int = Field(ge=0)
    final_score_away: int = Field(ge=0)
    round: str | None = Field(default=None, max_length=50)
    team_box_scores: list[NormalizedTeamBoxScore] = Field(default_factory=list)
    player_box_scores: list[NormalizedPlayerBoxScore] = Field(default_factory=list)
