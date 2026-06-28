"""Tests for the persistence stage: idempotent upserts (spec §3.3)."""

from datetime import UTC, date, datetime

import pytest

from games.models import Game
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
)
from players.models import PlayerGameStats
from teams.models import Team


def _ref(external_id: str) -> ExternalRef:
    """Build a seed-source external ref for the given id."""
    return ExternalRef(source="seed", external_id=external_id)


def _team(external_id: str, name: str, slug: str) -> NormalizedTeam:
    """Build a minimal normalized team."""
    return NormalizedTeam(
        ref=_ref(external_id), name=name, short_name=name[:3].upper(), slug=slug
    )


def _person(external_id: str, slug: str) -> NormalizedPerson:
    """Build a minimal normalized person."""
    return NormalizedPerson(
        ref=_ref(external_id), first_name="Test", last_name="Player", slug=slug
    )


@pytest.mark.django_db
def test_upsert_team_is_idempotent() -> None:
    """Upserting the same team twice yields a single row."""
    team = _team("t1", "CB Test", "cb-test")
    upsert_team(team)
    upsert_team(team)
    assert Team.objects.filter(source="seed", external_id="t1").count() == 1


@pytest.mark.django_db
def test_upsert_team_updates_changed_fields() -> None:
    """Re-upserting with changed data updates in place, not duplicates."""
    upsert_team(_team("t1", "CB Test", "cb-test"))
    upsert_team(
        NormalizedTeam(
            ref=_ref("t1"), name="CB Renamed", short_name="REN", slug="cb-test"
        )
    )
    teams = Team.objects.filter(source="seed", external_id="t1")
    assert teams.count() == 1
    assert teams.first().name == "CB Renamed"


@pytest.mark.django_db
def test_upsert_game_with_boxscore_is_idempotent() -> None:
    """Re-ingesting a game does not duplicate it or its player lines."""
    league = upsert_league(name="Liga ACB", slug="acb", level=1)
    season = upsert_season(league=league, name="2024-2025", start_date=date(2024, 9, 1))
    home = upsert_team(_team("h", "CB Home", "cb-home"))
    away = upsert_team(_team("a", "CB Away", "cb-away"))
    upsert_team_season(team=home, season=season, league=league)
    upsert_team_season(team=away, season=season, league=league)
    upsert_person(_person("p1", "p-one"))
    upsert_person(_person("p2", "p-two"))

    def line(person_ext: str, team_ext: str, points: int) -> NormalizedPlayerBoxScore:
        return NormalizedPlayerBoxScore(
            person_ref=_ref(person_ext),
            team_ref=_ref(team_ext),
            minutes_played=30,
            points=points,
            rebounds_off=1,
            rebounds_def=4,
            assists=3,
            steals=1,
            blocks=0,
            turnovers=2,
            fouls=2,
            field_goals_made=points // 2,
            field_goals_att=points,
            three_point_made=0,
            three_point_att=2,
            free_throws_made=0,
            free_throws_att=0,
        )

    game = NormalizedGame(
        ref=_ref("g1"),
        home_team_ref=_ref("h"),
        away_team_ref=_ref("a"),
        date=datetime(2024, 9, 10, 19, 0, tzinfo=UTC),
        final_score_home=80,
        final_score_away=78,
        player_box_scores=[line("p1", "h", 20), line("p2", "a", 18)],
    )

    upsert_game_with_boxscore(game, season=season)
    upsert_game_with_boxscore(game, season=season)

    assert Game.objects.filter(source="seed", external_id="g1").count() == 1
    assert PlayerGameStats.objects.filter(game__external_id="g1").count() == 2


@pytest.mark.django_db
def test_strict_schema_rejects_negative_points() -> None:
    """The Pydantic boundary rejects impossible values (spec §3.3)."""
    with pytest.raises(ValueError):
        NormalizedPlayerBoxScore(
            person_ref=_ref("p1"),
            team_ref=_ref("h"),
            minutes_played=10,
            points=-5,
            rebounds_off=0,
            rebounds_def=0,
            assists=0,
            steals=0,
            blocks=0,
            turnovers=0,
            fouls=0,
            field_goals_made=0,
            field_goals_att=0,
            three_point_made=0,
            three_point_att=0,
            free_throws_made=0,
            free_throws_att=0,
        )
