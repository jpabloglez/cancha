"""Offline test of FEB profile enrichment (plan §6.5).

Ingests one box-score game (to create the teams/players), then drives
:func:`ingestion.feb_ingest.enrich_feb_season` with a fixture-backed connector
serving the captured player/team profile pages — asserting bio, branding and
trajectory land on the existing entities, idempotently and without network.
"""

from datetime import UTC, datetime
from pathlib import Path

import pytest

import connectors
from connectors.base import RawSourcePayload, SourceConnector
from ingestion.feb_ingest import enrich_feb_season, ingest_feb_season
from players.models import CareerEntry, Person
from teams.models import MediaAsset, Team

FIXTURES = Path(connectors.__file__).parent / "tests" / "fixtures"


class _FakeBoxScoreConnector(SourceConnector):
    """Serves the box-score fixture so teams/players exist before enrichment."""

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
        return self._payload((FIXTURES / "feb_boxscore.html").read_text(encoding="utf-8"))


class _FakeProfileConnector(_FakeBoxScoreConnector):
    """Serves the captured player/team profile fixtures for enrichment."""

    def fetch_player_profile(self, person_external_id, team_external_id):
        return self._payload(
            (FIXTURES / "feb_player_profile.html").read_text(encoding="utf-8")
        )

    def fetch_team_profile(self, team_external_id):
        return self._payload(
            (FIXTURES / "feb_team_profile.html").read_text(encoding="utf-8")
        )


@pytest.mark.django_db
def test_enrich_feb_season_populates_profiles_and_trajectory() -> None:
    """Enrichment fills bio/branding on existing teams/players and adds career."""
    ingest_feb_season("feb-primera", "2024", connector=_FakeBoxScoreConnector())

    result = enrich_feb_season(
        "feb-primera", "2024", connector=_FakeProfileConnector(), store_media=False
    )

    assert result.teams_enriched == 2
    assert result.players_enriched == 4
    assert result.failures == 0
    assert result.media_stored == 0  # store_media disabled

    # Teams got branding (arena) + a logo MediaAsset reference (no file yet).
    assert Team.objects.filter(source="feb-primera").exclude(arena="").count() == 2
    assert MediaAsset.objects.filter(kind=MediaAsset.Kind.TEAM_LOGO).count() == 2

    # Players got bio (height/position parsed from the fixture) + career timeline.
    assert Person.objects.filter(
        source="feb-primera", height_cm__isnull=False
    ).count() == 4
    # Each of the 4 players reads the same 7-stint fixture, keyed per person.
    assert CareerEntry.objects.count() == 4 * 7


@pytest.mark.django_db
def test_enrich_feb_season_is_idempotent() -> None:
    """Re-running enrichment creates no duplicate career or media rows."""
    ingest_feb_season("feb-primera", "2024", connector=_FakeBoxScoreConnector())
    enrich_feb_season(
        "feb-primera", "2024", connector=_FakeProfileConnector(), store_media=False
    )
    enrich_feb_season(
        "feb-primera", "2024", connector=_FakeProfileConnector(), store_media=False
    )

    assert CareerEntry.objects.count() == 4 * 7
    assert MediaAsset.objects.filter(kind=MediaAsset.Kind.TEAM_LOGO).count() == 2
