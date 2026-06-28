"""ACB.com connector (Liga ACB / Liga Endesa).

Primary source for the top Spanish division (spec §3.1). ACB's website is a
Next.js app whose server-rendered results page only lists a few featured games,
so this connector instead reads the site's own **public JSON API** at
``api2.acb.com`` (plan: ACB JSON-API discovery 2026-06-27). The API is
authenticated with an ``X-APIKEY`` constant that the ACB frontend ships to every
browser, so it is treated here as a public client key, sent on every request
through a rate-limited, DB-cached client (:mod:`connectors.cache`). No headless
browser is needed.

Endpoints used (see :mod:`connectors.parsers.acb`):

* ``/api/seasondata/Competition/matches`` — the schedule (per edition / round).
* ``/api/matchdata/Result/boxscores`` — one finished game's stat lines.
"""

from datetime import UTC, datetime

from .base import RawSourcePayload, SourceConnector
from .cache import fetch_or_cache
from .http import RateLimitedClient

#: Public JSON API host backing acb.com / live.acb.com.
ACB_API_BASE = "https://api2.acb.com"
#: Public client key the ACB frontend ships to every browser (sent as X-APIKEY).
ACB_API_KEY = "0dd94928-6f57-4c08-a3bd-b1b2f092976e"
#: ``competitionId`` of the top division (Liga Endesa) in the ACB API.
ACB_LIGA_COMPETITION_ID = 1


class AcbConnector(SourceConnector):
    """Adapter for ACB's public JSON API (api2.acb.com).

    Parameters
    ----------
    client : RateLimitedClient or None
        Optional pre-configured HTTP client; a polite default carrying the
        ``X-APIKEY`` header is created if omitted.

    Attributes
    ----------
    id : str
        Connector identifier ("acb").
    competition_id : int
        ACB ``competitionId`` this connector serves (1 = Liga Endesa).
    """

    id = "acb"
    competition_id = ACB_LIGA_COMPETITION_ID

    def __init__(self, client: RateLimitedClient | None = None) -> None:
        self._client = client or RateLimitedClient(
            min_interval_seconds=2.0,
            extra_headers={"X-APIKEY": ACB_API_KEY, "Accept": "application/json"},
        )

    # -- URL builders --------------------------------------------------------

    def _matches_url(
        self, edition_id: str | None, round_id: int | None = None
    ) -> str:
        """Build the schedule URL for an edition (optionally one round).

        Passing ``edition_id=None`` omits the ``editionId`` parameter, which the
        API resolves to the current edition (used to discover the live season).
        """
        url = (
            f"{ACB_API_BASE}/api/seasondata/Competition/matches"
            f"?competitionId={self.competition_id}"
        )
        if edition_id is not None:
            url = f"{url}&editionId={edition_id}"
        if round_id is not None:
            return f"{url}&roundId={round_id}&isRoundSelected=true"
        return f"{url}&isRoundSelected=false"

    def _boxscore_url(self, match_id: str) -> str:
        """Build the box-score URL for a match id."""
        return f"{ACB_API_BASE}/api/matchdata/Result/boxscores?matchId={match_id}"

    # -- Fetch methods (return raw JSON-text payloads) -----------------------

    def _fetch(self, url: str) -> RawSourcePayload:
        """Fetch a URL through the rate-limited, DB-cached path."""
        content = fetch_or_cache(url, source=self.id, client=self._client)
        return RawSourcePayload(
            source_id=self.id, fetched_at=datetime.now(UTC), data=content
        )

    def fetch_teams(self, season_external_id: str) -> RawSourcePayload:
        """Fetch the schedule for an edition (teams are embedded; see base)."""
        return self._fetch(self._matches_url(season_external_id))

    def fetch_roster(
        self, team_external_id: str, season_external_id: str
    ) -> RawSourcePayload:
        """Not used: ACB rosters are derived from box scores during ingestion.

        Raises
        ------
        NotImplementedError
            Always — roster membership is reconstructed from player box scores
            in the ingestion orchestration, mirroring the FEB connector.
        """
        raise NotImplementedError(
            "ACB rosters are derived from box scores during ingestion"
        )

    def fetch_completed_games(self, season_external_id: str) -> RawSourcePayload:
        """Fetch the full-edition schedule (round list + finished games).

        Parameters
        ----------
        season_external_id : str
            The ACB ``editionId`` (e.g. "90" for 2025/2026).
        """
        return self._fetch(self._matches_url(season_external_id))

    def fetch_current_schedule(self) -> RawSourcePayload:
        """Fetch the current edition's schedule (no ``editionId`` parameter).

        The API resolves the omitted edition to the live season, so this is used
        to discover the current ``editionId`` across season rollovers.
        """
        return self._fetch(self._matches_url(None))

    def fetch_round_matches(
        self, season_external_id: str, round_id: int
    ) -> RawSourcePayload:
        """Fetch one round's matches for an edition (full-season iteration).

        Parameters
        ----------
        season_external_id : str
            The ACB ``editionId``.
        round_id : int
            The round id to fetch (from the schedule's round list).
        """
        return self._fetch(self._matches_url(season_external_id, round_id))

    def fetch_box_score(self, game_external_id: str) -> RawSourcePayload:
        """Fetch a finished ACB box score (see base class).

        Parameters
        ----------
        game_external_id : str
            The ACB ``matchId`` (e.g. "105370").
        """
        return self._fetch(self._boxscore_url(game_external_id))


def build_acb_connector() -> AcbConnector:
    """Construct the ACB connector with a polite, API-key-bearing HTTP client.

    Returns
    -------
    AcbConnector
        Connector configured for ACB's public JSON API.
    """
    return AcbConnector()
