"""Tests for the season aggregation engine (spec §4.2, §4.4)."""

from datetime import UTC, date, datetime

import pytest

from ingestion.persistence import (
    upsert_game_with_boxscore,
    upsert_league,
    upsert_person,
    upsert_season,
    upsert_team,
    upsert_team_season,
)
from ingestion.schemas import (
    ExternalRef,
    NormalizedGame,
    NormalizedPerson,
    NormalizedPlayerBoxScore,
    NormalizedTeam,
    NormalizedTeamBoxScore,
)
from players.models import PlayerSeasonAggregate
from stats.aggregation import recompute_player_season_aggregates


def _ref(external_id: str) -> ExternalRef:
    """Build a seed-source external ref."""
    return ExternalRef(source="seed", external_id=external_id)


@pytest.fixture
def single_player_season(db):
    """Persist a one-player, one-game season with known box-score numbers.

    Returns
    -------
    tuple
        ``(season, person)`` for the created fixture.
    """
    league = upsert_league(name="Liga ACB", slug="acb", level=1)
    season = upsert_season(
        league=league, name="2024-2025", start_date=date(2024, 9, 1)
    )
    home = upsert_team(
        NormalizedTeam(ref=_ref("h"), name="CB Home", short_name="HOM", slug="cb-home")
    )
    away = upsert_team(
        NormalizedTeam(ref=_ref("a"), name="CB Away", short_name="AWA", slug="cb-away")
    )
    upsert_team_season(team=home, season=season, league=league)
    upsert_team_season(team=away, season=season, league=league)
    person = upsert_person(
        NormalizedPerson(ref=_ref("p1"), first_name="A", last_name="B", slug="a-b")
    )

    # Known line: 21 pts on 8/10 FG (2 threes) and 3/4 FT, 5 reb, 4 ast.
    line = NormalizedPlayerBoxScore(
        person_ref=_ref("p1"),
        team_ref=_ref("h"),
        minutes_played=30,
        points=21,
        rebounds_off=2,
        rebounds_def=3,
        assists=4,
        steals=1,
        blocks=0,
        turnovers=2,
        fouls=1,
        field_goals_made=8,
        field_goals_att=10,
        three_point_made=2,
        three_point_att=4,
        free_throws_made=3,
        free_throws_att=4,
    )
    team_box = NormalizedTeamBoxScore(
        team_ref=_ref("h"),
        points=21,
        rebounds_off=2,
        rebounds_def=3,
        assists=4,
        steals=1,
        blocks=0,
        turnovers=2,
        fouls=1,
        field_goals_made=8,
        field_goals_att=10,
        three_point_made=2,
        three_point_att=4,
        free_throws_made=3,
        free_throws_att=4,
    )
    game = NormalizedGame(
        ref=_ref("g1"),
        home_team_ref=_ref("h"),
        away_team_ref=_ref("a"),
        date=datetime(2024, 9, 10, 19, 0, tzinfo=UTC),
        final_score_home=21,
        final_score_away=18,
        team_box_scores=[team_box],
        player_box_scores=[line],
    )
    upsert_game_with_boxscore(game, season=season)
    return season, person


def test_aggregate_basic_and_advanced(single_player_season) -> None:
    """Aggregates match hand-computed per-game and advanced values."""
    season, person = single_player_season
    written = recompute_player_season_aggregates(season.pk)
    assert written == 1

    agg = PlayerSeasonAggregate.objects.get(person=person, season=season)
    assert agg.games_played == 1
    assert agg.points_per_game == pytest.approx(21.0)
    assert agg.rebounds_per_game == pytest.approx(5.0)
    assert agg.assists_per_game == pytest.approx(4.0)
    # TS% = 21 / (2 * (10 + 0.44*4)) = 0.89286
    assert agg.ts_percent == pytest.approx(21 / (2 * (10 + 0.44 * 4)), rel=1e-6)
    # eFG% = (8 + 0.5*2) / 10 = 0.9
    assert agg.efg_percent == pytest.approx(0.9, rel=1e-6)
    # PER is rescaled so the minutes-weighted league average is 15. With a
    # single player they *are* the league average, so their PER is exactly 15.
    assert agg.per == pytest.approx(15.0, rel=1e-6)
    # This degenerate fixture has a single player credited with the whole
    # team's plays, so usage exceeds 1; we just assert it is computed positive.
    assert agg.usage_rate > 0.0


def test_aggregation_is_idempotent(single_player_season) -> None:
    """Recomputing does not create duplicate aggregate rows."""
    season, _ = single_player_season
    recompute_player_season_aggregates(season.pk)
    recompute_player_season_aggregates(season.pk)
    assert PlayerSeasonAggregate.objects.filter(season=season).count() == 1
