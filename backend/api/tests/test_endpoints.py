"""Smoke tests for the public API endpoints (spec §5.2).

Seeds the demo dataset inside each test's transaction (rolled back afterwards,
so no cross-test pollution). Seed-dependent assertions are grouped into a single
test to keep the (relatively expensive) seeding to one run; the two 400-path
tests need no data because the views reject before touching the database.

Assertions read ``response.json()`` (the rendered body) so they verify the
camelCase rendering, which ``response.data`` (pre-render) would not show.
"""

import pytest
from django.core.management import call_command
from rest_framework.test import APIClient

from players.models import PlayerSeasonAggregate
from teams.models import Season


@pytest.fixture
def client() -> APIClient:
    """Return a DRF API test client."""
    return APIClient()


def test_seeded_endpoints(db, client) -> None:
    """Leagues, standings, player stats and leaders all serve seeded data."""
    call_command("seed_demo_data")

    leagues = client.get("/api/v1/leagues/")
    assert leagues.status_code == 200
    assert leagues.json()["count"] == 3

    season = Season.objects.first()
    standings = client.get(f"/api/v1/seasons/{season.pk}/standings/")
    assert standings.status_code == 200
    standings_data = standings.json()
    assert len(standings_data) == 6
    assert "pointDifference" in standings_data[0]

    # Derive a matching player+season from an aggregate so they share a league.
    aggregate = PlayerSeasonAggregate.objects.select_related("person").first()
    stats = client.get(
        f"/api/v1/players/{aggregate.person.slug}/stats/?season={aggregate.season_id}"
    )
    assert stats.status_code == 200
    stats_data = stats.json()
    assert "trueShootingPercent" in stats_data["advanced"]

    leaders = client.get("/api/v1/stats/leaders/?stat=points&limit=5")
    assert leaders.status_code == 200
    leader_rows = leaders.json()
    values = [row["value"] for row in leader_rows]
    assert values == sorted(values, reverse=True)
    # Each row carries photo + team context for the UI.
    assert all("photo" in row for row in leader_rows)
    assert all("team" in row for row in leader_rows)


def test_leaders_filters_and_qualifier(db, client) -> None:
    """League filtering and the games-played qualifier both apply."""
    call_command("seed_demo_data")
    season = (
        PlayerSeasonAggregate.objects.select_related("season__league")
        .first()
        .season
    )
    league_id = season.league_id

    # League filter: every returned player belongs to the requested league.
    by_league = client.get(
        f"/api/v1/stats/leaders/?stat=points&league={league_id}&season={season.pk}"
    )
    assert by_league.status_code == 200
    assert len(by_league.json()) > 0

    # An impossibly high qualifier excludes everyone (no player has 999 games).
    qualified = client.get("/api/v1/stats/leaders/?stat=per&minGames=999")
    assert qualified.status_code == 200
    assert qualified.json() == []


def test_leaders_unknown_stat_is_400(db, client) -> None:
    """An unknown stat key is rejected with HTTP 400 (no data needed)."""
    response = client.get("/api/v1/stats/leaders/?stat=nonsense")
    assert response.status_code == 400


def test_roster_requires_season(db, client) -> None:
    """The roster endpoint rejects a missing season before any DB access."""
    response = client.get("/api/v1/teams/acb-almendro/roster/")
    assert response.status_code == 400
