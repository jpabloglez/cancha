"""FEB.es connector (Primera FEB / LEB Oro and Segunda FEB / LEB Plata).

Primary source for the FEB competitions (spec §3.1). Data comes from the live
platform ``baloncestoenvivo.feb.es`` as server-rendered HTML, fetched through a
rate-limited client and cached in the DB (``connectors.cache``). One connector
class is parameterized by :class:`~ingestion.catalog.FebCompetition`, so both
tiers share a single implementation while mapping the historical (LEB Oro/Plata)
and current (Primera/Segunda FEB) names onto the same ``League`` (spec §12.2).
"""

from datetime import UTC, datetime

from ingestion.catalog import FEB_COMPETITIONS, FebCompetition

from .base import RawSourcePayload, SourceConnector
from .cache import fetch_or_cache
from .http import RateLimitedClient


class FebConnector(SourceConnector):
    """Adapter for a single FEB competition on baloncestoenvivo.feb.es.

    Parameters
    ----------
    competition : FebCompetition
        Competition configuration (id ``g``, slug ``nm``, league mapping).
    client : RateLimitedClient or None
        Optional pre-configured HTTP client; a polite default is created if
        omitted.

    Attributes
    ----------
    id : str
        Connector identifier (e.g. "feb-primera").
    competition : FebCompetition
        The competition this connector serves.
    """

    def __init__(
        self, competition: FebCompetition, client: RateLimitedClient | None = None
    ) -> None:
        self.competition = competition
        self.id = competition.connector_id
        self._client = client or RateLimitedClient(min_interval_seconds=2.0)

    # -- URL builders --------------------------------------------------------
    #
    # The site uses clean paths "/<section>/<nm>/<g>/<t>" (legacy ".aspx?g=&t="
    # URLs 301-redirect to these). The full-season schedule lives on the
    # *calendario* page, which lists every game's box-score link at once — so no
    # per-jornada (ASP.NET postback) navigation is needed (verified 2026-06-21).

    def _calendar_url(self, season_external_id: str) -> str:
        """Build the full-season calendar URL (lists all games)."""
        c = self.competition
        return f"{c.base_url}/calendario/{c.name_slug}/{c.competition_id}/{season_external_id}"

    def _standings_url(self, season_external_id: str) -> str:
        """Build the standings URL for a season (used for the team list)."""
        c = self.competition
        return f"{c.base_url}/clasificacion/{c.name_slug}/{c.competition_id}/{season_external_id}"

    def _box_score_url(self, game_external_id: str) -> str:
        """Build the box-score (acta) URL for a game id (``p``)."""
        return f"{self.competition.base_url}/partido/{game_external_id}"

    def _player_profile_url(
        self, team_external_id: str, person_external_id: str
    ) -> str:
        """Build the player profile URL ``/jugador/<i>/<c>`` (plan §5.3)."""
        base = self.competition.base_url
        return f"{base}/jugador/{team_external_id}/{person_external_id}"

    def _team_profile_url(self, team_external_id: str) -> str:
        """Build the team profile URL ``/equipo/<i>`` (plan §5.3)."""
        return f"{self.competition.base_url}/equipo/{team_external_id}"

    # -- Fetch methods (return raw HTML payloads) ----------------------------

    def _fetch(self, url: str) -> RawSourcePayload:
        """Fetch a URL through the rate-limited, DB-cached path."""
        content = fetch_or_cache(url, source=self.id, client=self._client)
        return RawSourcePayload(
            source_id=self.id, fetched_at=datetime.now(UTC), data=content
        )

    def fetch_teams(self, season_external_id: str) -> RawSourcePayload:
        """Fetch the standings page (team list) for a season (see base class)."""
        return self._fetch(self._standings_url(season_external_id))

    def fetch_roster(
        self, team_external_id: str, season_external_id: str
    ) -> RawSourcePayload:
        """Not used: FEB rosters are derived from box scores during ingestion.

        Raises
        ------
        NotImplementedError
            Always — roster membership is reconstructed from player box scores
            in the ingestion orchestration, so no separate roster page is
            fetched for the FEB MVP.
        """
        raise NotImplementedError(
            "FEB rosters are derived from box scores during ingestion"
        )

    def fetch_completed_games(self, season_external_id: str) -> RawSourcePayload:
        """Fetch the season calendar listing all games (see base class).

        The calendar lists the whole season's games; only finished games carry a
        box-score link, so parsing it yields exactly the playable actas.
        """
        return self._fetch(self._calendar_url(season_external_id))

    def fetch_box_score(self, game_external_id: str) -> RawSourcePayload:
        """Fetch a final FEB box score / acta (see base class)."""
        return self._fetch(self._box_score_url(game_external_id))

    def fetch_player_profile(
        self, person_external_id: str, team_external_id: str
    ) -> RawSourcePayload:
        """Fetch a FEB player profile page (bio + trajectory; see base class)."""
        return self._fetch(
            self._player_profile_url(team_external_id, person_external_id)
        )

    def fetch_team_profile(self, team_external_id: str) -> RawSourcePayload:
        """Fetch a FEB team profile page (branding + crest; see base class)."""
        return self._fetch(self._team_profile_url(team_external_id))


def build_primera_feb_connector() -> FebConnector:
    """Construct the connector for Primera FEB (formerly LEB Oro).

    Returns
    -------
    FebConnector
        Connector configured for the Primera FEB competition.
    """
    return FebConnector(FEB_COMPETITIONS["feb-primera"])


def build_segunda_feb_connector() -> FebConnector:
    """Construct the connector for Segunda FEB (formerly LEB Plata).

    Returns
    -------
    FebConnector
        Connector configured for the Segunda FEB competition.
    """
    return FebConnector(FEB_COMPETITIONS["feb-segunda"])
