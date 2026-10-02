"""Tests for staff persistence, FEB enrichment wiring and the staff endpoint."""

from datetime import datetime

import pytest
from rest_framework.test import APIClient

from ingestion.feb_ingest import enrich_feb_season, ingest_feb_season
from ingestion.persistence import upsert_staff_entry
from ingestion.schemas import ExternalRef, NormalizedPerson, NormalizedStaffEntry
from ingestion.tests.test_feb_enrich import (
    _FakeBoxScoreConnector,
    _FakeProfileConnector,
)
from players.models import Person, StaffEntry
from teams.models import League, Season, Team, TeamSeason


def _team_season() -> TeamSeason:
    """Create a minimal team-season for staff tests."""
    league = League.objects.create(name="L", slug="l", level=1, country="ES")
    season = Season.objects.create(
        league=league, name="2024-2025", start_date=datetime(2024, 9, 1).date()
    )
    team = Team.objects.create(
        name="Club", short_name="CLB", slug="club", source="acb", external_id="9"
    )
    return TeamSeason.objects.create(team=team, season=season, league=league)


def _coach(name: str = "Xavi Pascual") -> tuple[NormalizedPerson, NormalizedStaffEntry]:
    """Build a normalized ACB-style head coach."""
    ref = ExternalRef(source="acb", external_id="staff-xavi-pascual")
    person = NormalizedPerson(
        ref=ref, first_name="Xavi", last_name="Pascual", slug="entrenador-xavi-pascual"
    )
    entry = NormalizedStaffEntry(
        person_ref=ref,
        team_ref=ExternalRef(source="acb", external_id="9"),
        role="head_coach",
    )
    return person, entry


@pytest.mark.django_db
def test_upsert_staff_entry_is_idempotent_and_sets_display_name() -> None:
    """Re-upserting the same coach yields one Person and one StaffEntry."""
    team_season = _team_season()
    person, entry = _coach()

    first = upsert_staff_entry(person, entry, team_season)
    second = upsert_staff_entry(person, entry, team_season)

    assert first.pk == second.pk
    assert Person.objects.filter(external_id="staff-xavi-pascual").count() == 1
    assert StaffEntry.objects.count() == 1
    assert first.person.display_name == "Xavi Pascual"


@pytest.mark.django_db
def test_upsert_staff_entry_distinguishes_roles() -> None:
    """The same person can hold different roles in one team-season."""
    team_season = _team_season()
    person, entry = _coach()
    assistant = entry.model_copy(update={"role": "assistant_coach"})

    upsert_staff_entry(person, entry, team_season)
    upsert_staff_entry(person, assistant, team_season)

    assert StaffEntry.objects.count() == 2


@pytest.mark.django_db
def test_enrich_feb_season_ingests_head_coaches() -> None:
    """FEB enrichment stores one head coach per team, shared Person by c id."""
    ingest_feb_season("feb-primera", "2024", connector=_FakeBoxScoreConnector())
    result = enrich_feb_season(
        "feb-primera", "2024", connector=_FakeProfileConnector(), store_media=False
    )
    assert result.staff_ingested == 2
    assert StaffEntry.objects.filter(role="head_coach").count() == 2
    coach = Person.objects.get(source="feb-primera", external_id="333852")
    assert coach.display_name == "Daniel Angel Garcia Gonzalez"

    # Idempotent on re-run.
    enrich_feb_season(
        "feb-primera", "2024", connector=_FakeProfileConnector(), store_media=False
    )
    assert StaffEntry.objects.count() == 2


@pytest.mark.django_db
def test_team_staff_endpoint_filters_by_season() -> None:
    """GET /teams/{slug}/staff/ returns the latest season by default."""
    team_season = _team_season()
    person, entry = _coach()
    upsert_staff_entry(person, entry, team_season)
    client = APIClient()

    default = client.get("/api/v1/teams/club/staff/")
    assert default.status_code == 200
    body = default.json()
    assert [(s["displayName"], s["role"]) for s in body] == [
        ("Xavi Pascual", "head_coach")
    ]

    other = client.get(f"/api/v1/teams/club/staff/?season={team_season.season_id + 999}")
    assert other.status_code == 200
    assert other.json() == []


@pytest.mark.django_db
def test_staff_endpoint_is_cached_until_the_cache_is_cleared() -> None:
    """Responses are cached; the post-ingest ``cache.clear()`` makes data fresh."""
    from django.core.cache import cache

    team_season = _team_season()
    client = APIClient()
    assert client.get("/api/v1/teams/club/staff/").json() == []

    person, entry = _coach()
    upsert_staff_entry(person, entry, team_season)
    assert client.get("/api/v1/teams/club/staff/").json() == []  # still cached

    cache.clear()
    assert len(client.get("/api/v1/teams/club/staff/").json()) == 1
