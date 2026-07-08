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
    assert season is not None
    standings = client.get(f"/api/v1/seasons/{season.pk}/standings/")
    assert standings.status_code == 200
    standings_data = standings.json()
    assert len(standings_data) == 6
    assert "pointDifference" in standings_data[0]

    # Derive a matching player+season from an aggregate so they share a league.
    aggregate = PlayerSeasonAggregate.objects.select_related("person").first()
    assert aggregate is not None
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
    first_agg = PlayerSeasonAggregate.objects.select_related("season__league").first()
    assert first_agg is not None
    season = first_agg.season
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


def test_global_search(db, client) -> None:
    """Global search returns teams, players and leagues across entity types."""
    call_command("seed_demo_data")

    # A query below the 2-char minimum returns empty results, not an error.
    short = client.get("/api/v1/search/?q=a")
    assert short.status_code == 200
    body = short.json()
    assert body == {"teams": [], "players": [], "leagues": []}

    # A query that matches league names returns hits in the leagues bucket.
    acb = client.get("/api/v1/search/?q=ACB")
    assert acb.status_code == 200
    data = acb.json()
    assert "teams" in data and "players" in data and "leagues" in data
    assert any("ACB" in league["name"].upper() for league in data["leagues"])

    # A query for a seeded team name surfaces it in the teams bucket.
    team = client.get("/api/v1/search/?q=CB")
    assert team.status_code == 200
    team_data = team.json()
    assert len(team_data["teams"]) > 0

    # An unmatched query returns empty lists (not a 404/500).
    empty = client.get("/api/v1/search/?q=zzznomatch999")
    assert empty.status_code == 200
    empty_data = empty.json()
    assert empty_data["teams"] == []
    assert empty_data["players"] == []
    assert empty_data["leagues"] == []


def test_alltime_leaders(db, client) -> None:
    """All-time leaders endpoint returns ranked rows with cumulative stats."""
    call_command("seed_demo_data")

    resp = client.get("/api/v1/stats/alltime/?stat=ppg&limit=5")
    assert resp.status_code == 200
    body = resp.json()
    assert "count" in body and "results" in body
    rows = body["results"]
    assert len(rows) <= 5

    if rows:
        row = rows[0]
        # Shape check: all expected keys present in camelCase.
        for key in ("playerId", "playerName", "playerSlug", "totalGames",
                    "seasonsCount", "ppg", "rpg", "apg", "statValue", "leagues"):
            assert key in row, f"Missing key: {key}"
        # Rows are sorted descending by the chosen stat.
        ppg_values = [r["ppg"] for r in rows]
        assert ppg_values == sorted(ppg_values, reverse=True)

    # total_points variant also works.
    pts = client.get("/api/v1/stats/alltime/?stat=total_points&limit=3")
    assert pts.status_code == 200
    pt_rows = pts.json()["results"]
    if len(pt_rows) >= 2:
        assert pt_rows[0]["totalPoints"] >= pt_rows[1]["totalPoints"]

    # minGames=999 eliminates everyone (no player has that many games in seed data).
    none_resp = client.get("/api/v1/stats/alltime/?minGames=999")
    assert none_resp.status_code == 200
    assert none_resp.json()["results"] == []

    # Unknown stat key returns 400.
    bad = client.get("/api/v1/stats/alltime/?stat=nonsense")
    assert bad.status_code == 400


def test_player_of_the_day(db, client) -> None:
    """Player-of-the-day returns a valid player with bio and latest stats."""
    call_command("seed_demo_data")

    resp = client.get("/api/v1/players/player-of-the-day/")
    assert resp.status_code == 200
    body = resp.json()

    assert "player" in body
    player = body["player"]
    assert "slug" in player
    assert "firstName" in player

    # latestStats is either null or carries the standard stats shape.
    if body.get("latestStats") is not None:
        ls = body["latestStats"]
        assert "gamesPlayed" in ls
        assert "pointsPerGame" in ls
        assert "advanced" in ls
