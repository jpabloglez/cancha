"""Offline end-to-end test of ACB season ingestion (spec §9).

Drives :func:`ingestion.acb_ingest.ingest_acb_season` with a fixture-backed fake
connector (no network): a crafted schedule (one finished game, no extra rounds)
paired with the real ``Result/boxscores`` fixture for that game, asserting the
whole JSON-API path persists the game, derives rosters and recomputes aggregates
— idempotently.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import connectors
from connectors.base import RawSourcePayload, SourceConnector
from games.models import Game
from ingestion.acb_ingest import ingest_acb_season
from players.models import Person, PlayerGameStats, PlayerSeasonAggregate, RosterEntry
from teams.models import League, MediaAsset, Season, Team, TeamSeason

FIXTURES = Path(connectors.__file__).parent / "tests" / "fixtures"

# Minimal schedule: edition 90 = 2025/26, no separate rounds, one finished game
# (matchId 105370) whose home/away clubIds match the box-score fixture.
_SCHEDULE = {
    "availableFilters": {
        "seasons": [{"id": 90, "seasonStartYear": 2025, "seasonEndYear": 2026}],
        "rounds": [],
    },
    "selectedFilters": {"season": 90},
    "teams": [
        {
            "id": 4397,
            "clubId": 13,
            "fullName": "Valencia Basket",
            "abbreviatedName": "VBC",
            "primaryColorHex": "#fc6c0f",
            "logo": "https://static.acb.com/img/valencia.png",
        },
        {
            "id": 4386,
            "clubId": 2,
            "fullName": "Barça",
            "abbreviatedName": "BAR",
            "primaryColorHex": "#154284",
            "logo": "https://static.acb.com/img/barca.png",
        },
    ],
    "matches": [
        {
            "id": 105370,
            "homeTeamId": 4397,
            "awayTeamId": 4386,
            "homeScore": 112,
            "awayScore": 113,
            "startDateTime": "2026-06-18T18:00:00Z",
            "matchStatus": "FINALIZED",
        }
    ],
}


class FakeAcbConnector(SourceConnector):
    """Connector returning fixture JSON instead of hitting the ACB API."""

    id = "acb"

    def _payload(self, data: str) -> RawSourcePayload:
        return RawSourcePayload(source_id=self.id, fetched_at=datetime.now(UTC), data=data)

    def fetch_teams(self, season_external_id: str) -> RawSourcePayload:
        return self._payload(json.dumps(_SCHEDULE))

    def fetch_roster(self, team_external_id, season_external_id):
        raise NotImplementedError

    def fetch_completed_games(self, season_external_id: str) -> RawSourcePayload:
        return self._payload(json.dumps(_SCHEDULE))

    def fetch_round_matches(self, season_external_id, round_id):
        return self._payload(json.dumps(_SCHEDULE))

    def fetch_box_score(self, game_external_id: str) -> RawSourcePayload:
        data = (FIXTURES / "acb_api_boxscore.json").read_text(encoding="utf-8")
        return self._payload(data)

    def fetch_current_schedule(self) -> RawSourcePayload:
        return self._payload(json.dumps(_SCHEDULE))


@pytest.mark.django_db
def test_ingest_acb_season_persists_full_graph() -> None:
    """One game ingests into teams, game, player stats, rosters and aggregates."""
    # store_media=False keeps the test offline (no headshot downloads).
    result = ingest_acb_season("90", connector=FakeAcbConnector(), store_media=False)

    assert result.games_ingested == 1
    assert result.games_failed == 0

    league = League.objects.get(slug="acb")
    assert league.level == 1
    season = Season.objects.get(league=league, name="2025-2026")
    assert Team.objects.filter(source="acb").count() == 2
    assert TeamSeason.objects.filter(season=season).count() == 2
    assert Game.objects.filter(season=season).count() == 1

    game = Game.objects.get(season=season)
    assert (game.final_score_home, game.final_score_away) == (112, 113)

    lines = PlayerGameStats.objects.filter(game__season=season)
    assert lines.count() == 24  # 12 + 12 box-score lines
    assert RosterEntry.objects.count() == 24
    assert PlayerSeasonAggregate.objects.filter(season=season).count() == 24


@pytest.mark.django_db
def test_ingest_acb_season_enriches_positions_and_photo_refs() -> None:
    """Box scores fill player positions and record headshot media references."""
    result = ingest_acb_season("90", connector=FakeAcbConnector(), store_media=False)

    assert result.players_enriched == 24
    assert result.photos_stored == 0  # store_media=False: refs only, no binary

    badio = Person.objects.get(source="acb", external_id="30000107")
    assert badio.primary_position == "SG"  # gameRole "Escolta"
    assert badio.display_name == "Brancou Badio"  # nickname preferred
    assert badio.photo is not None
    assert badio.photo.source_url.startswith("https://static.acb.com/")
    assert badio.photo.attribution == "ACB.com"
    assert badio.photo.is_available is False  # recorded but not yet downloaded
    # Every player got a player-photo asset reference.
    assert MediaAsset.objects.filter(kind=MediaAsset.Kind.PLAYER_PHOTO).count() == 24


@pytest.mark.django_db
def test_ingest_acb_season_enriches_team_branding() -> None:
    """Schedule teams fill team crest references and primary colours."""
    result = ingest_acb_season("90", connector=FakeAcbConnector(), store_media=False)

    assert result.teams_enriched == 2
    assert result.logos_stored == 0  # store_media=False: refs only, no binary

    barca = Team.objects.get(source="acb", external_id="2")
    assert barca.primary_color == "#154284"
    assert barca.official_name == "Barça"
    assert barca.logo is not None
    assert barca.logo.source_url == "https://static.acb.com/img/barca.png"
    assert barca.logo.attribution == "ACB.com"
    assert MediaAsset.objects.filter(kind=MediaAsset.Kind.TEAM_LOGO).count() == 2


@pytest.mark.django_db
def test_ingest_acb_season_is_idempotent() -> None:
    """Re-ingesting the same edition does not duplicate any rows."""
    ingest_acb_season("90", connector=FakeAcbConnector(), store_media=False)
    ingest_acb_season("90", connector=FakeAcbConnector(), store_media=False)

    season = Season.objects.get(name="2025-2026")
    assert Game.objects.filter(season=season).count() == 1
    assert PlayerGameStats.objects.filter(game__season=season).count() == 24
    assert Team.objects.filter(source="acb").count() == 2
    assert RosterEntry.objects.count() == 24
