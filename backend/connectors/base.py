"""Common contract that every data-source connector must implement.

Each external source is wrapped by an independent connector implementing this
interface, following the Adapter pattern (spec §3.2). Source-specific logic
must never leak outside its connector module.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass
class RawSourcePayload:
    """Raw payload returned by a connector before normalization.

    Each connector returns data in its own shape; normalization happens in a
    later pipeline stage (spec §3.3).

    Attributes
    ----------
    source_id : str
        Identifier of the connector that produced this payload.
    fetched_at : datetime
        Timestamp at which the data was fetched from the source.
    data : Any
        Raw, source-specific payload (HTML, JSON, etc.).
    """

    source_id: str
    fetched_at: datetime
    data: Any


class SourceConnector(ABC):
    """Common interface every source connector must implement.

    Keeps ingestion logic decoupled from source-specific details, following
    the Adapter pattern.

    Attributes
    ----------
    id : str
        Unique identifier for this connector, e.g. "acb", "feb-leb-oro".
    """

    id: str

    @abstractmethod
    def fetch_teams(self, season_external_id: str) -> RawSourcePayload:
        """Fetch the list of teams for a given season.

        Parameters
        ----------
        season_external_id : str
            Identifier of the season as used by the external source.

        Returns
        -------
        RawSourcePayload
            Raw team list payload, not yet normalized.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_roster(
        self, team_external_id: str, season_external_id: str
    ) -> RawSourcePayload:
        """Fetch the full roster for a given team and season.

        Parameters
        ----------
        team_external_id : str
            Identifier of the team as used by the external source.
        season_external_id : str
            Identifier of the season as used by the external source.

        Returns
        -------
        RawSourcePayload
            Raw roster payload, not yet normalized.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_completed_games(self, season_external_id: str) -> RawSourcePayload:
        """Fetch completed games for a given season (no live games).

        Parameters
        ----------
        season_external_id : str
            Identifier of the season as used by the external source.

        Returns
        -------
        RawSourcePayload
            Raw payload listing finished games only.
        """
        raise NotImplementedError

    @abstractmethod
    def fetch_box_score(self, game_external_id: str) -> RawSourcePayload:
        """Fetch the final box score for a finished game.

        Parameters
        ----------
        game_external_id : str
            Identifier of the game as used by the external source.

        Returns
        -------
        RawSourcePayload
            Raw box score payload, not yet normalized.
        """
        raise NotImplementedError

    # -- Enrichment (optional; not every source exposes profile pages) --------

    def fetch_player_profile(
        self, person_external_id: str, team_external_id: str
    ) -> RawSourcePayload:
        """Fetch a player's profile page (bio + trajectory).

        Optional: connectors whose source has profile pages override this; the
        default signals the capability is unavailable (spec §3.2).

        Parameters
        ----------
        person_external_id : str
            Identifier of the player as used by the external source.
        team_external_id : str
            Identifier of a team the player belongs to (some sources key the
            player URL on both ids).

        Returns
        -------
        RawSourcePayload
            Raw player profile payload, not yet normalized.
        """
        raise NotImplementedError(
            f"{self.id} does not expose player profile pages"
        )

    def fetch_team_profile(self, team_external_id: str) -> RawSourcePayload:
        """Fetch a team's profile page (branding / metadata / crest).

        Optional: see :meth:`fetch_player_profile`.

        Parameters
        ----------
        team_external_id : str
            Identifier of the team as used by the external source.

        Returns
        -------
        RawSourcePayload
            Raw team profile payload, not yet normalized.
        """
        raise NotImplementedError(
            f"{self.id} does not expose team profile pages"
        )
