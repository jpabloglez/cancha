"""Offline end-to-end test of FEB season ingestion (spec §9).

Drives :func:`ingestion.feb_ingest.ingest_feb_season` with a fixture-backed fake
connector (no network), asserting the whole path persists games, derives rosters
and recomputes aggregates — idempotently.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

import connectors
from connectors.base import RawSourcePayload, SourceConnector
from games.models import Game
from ingestion.feb_ingest import ingest_feb_season
from players.models import PlayerGameStats, PlayerSeasonAggregate, RosterEntry
from teams.models import League, Season, Team, TeamSeason

FIXTURES = Path(connectors.__file__).parent / "tests" / "fixtures"


class FakeFebConnector(SourceConnector):
    """Connector returning fixture HTML instead of hitting the network."""

    id = "feb-primera"

    def _payload(self, data: str) -> RawSourcePayload:
        return RawSourcePayload(source_id=self.id, fetched_at=datetime.now(UTC), data=data)

    def fetch_teams(self, season_external_id: str) -> RawSourcePayload:
        return self._payload("")

    def fetch_roster(self, team_external_id, season_external_id):
        raise NotImplementedError

    def fetch_completed_games(self, season_external_id: str) -> RawSourcePayload:
        return self._payload('<a href="Partido.aspx?p=999">game</a>')

    def fetch_box_score(self, game_external_id: str) -> RawSourcePayload:
        html = (FIXTURES / "feb_boxscore.html").read_text(encoding="utf-8")
        return self._payload(html)


@pytest.mark.django_db
def test_ingest_feb_season_persists_full_graph() -> None:
    """One game ingests into teams, game, player stats, rosters and aggregates."""
    result = ingest_feb_season("feb-primera", "2024", connector=FakeFebConnector())

    assert result.games_ingested == 1
    assert result.games_failed == 0

    league = League.objects.get(slug="primera-feb")
    season = Season.objects.get(league=league, name="2024-2025")
    assert Team.objects.filter(source="feb-primera").count() == 2
    assert TeamSeason.objects.filter(season=season).count() == 2
    assert Game.objects.filter(season=season).count() == 1
    assert PlayerGameStats.objects.filter(game__season=season).count() == 4
    assert RosterEntry.objects.count() == 4
    assert PlayerSeasonAggregate.objects.filter(season=season).count() == 4


@pytest.mark.django_db
def test_ingest_feb_season_is_idempotent() -> None:
    """Re-ingesting the same season does not duplicate any rows."""
    ingest_feb_season("feb-primera", "2024", connector=FakeFebConnector())
    ingest_feb_season("feb-primera", "2024", connector=FakeFebConnector())

    season = Season.objects.get(name="2024-2025")
    assert Game.objects.filter(season=season).count() == 1
    assert PlayerGameStats.objects.filter(game__season=season).count() == 4
    assert Team.objects.filter(source="feb-primera").count() == 2
    assert RosterEntry.objects.count() == 4
