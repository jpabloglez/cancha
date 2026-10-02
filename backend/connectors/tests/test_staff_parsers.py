"""Tests for the ACB and FEB coaching-staff parsers (fixtures, no network/DB)."""

import json
from pathlib import Path

import connectors
from connectors.parsers.acb import parse_staff_entries
from connectors.parsers.feb import (
    _split_given_and_surnames,
    parse_coach_from_team_profile,
)

FIXTURES = Path(connectors.__file__).parent / "tests" / "fixtures"


def test_acb_staff_entries_cover_head_and_assistants() -> None:
    """Each team yields one head coach plus its assistants, keyed by clubId."""
    payload = json.loads(
        (FIXTURES / "acb_api_boxscore.json").read_text(encoding="utf-8")
    )
    entries = parse_staff_entries(payload, source="acb")

    assert len(entries) == 8  # 2 head coaches + 3 assistants each
    by_team: dict[str, list[str]] = {}
    for _person, entry in entries:
        by_team.setdefault(entry.team_ref.external_id, []).append(entry.role)
    assert sorted(by_team) == ["13", "2"]
    for roles in by_team.values():
        assert roles.count("head_coach") == 1
        assert roles.count("assistant_coach") == 3

    person, entry = next(e for e in entries if e[0].slug == "entrenador-xavi-pascual")
    assert person.ref.external_id == "staff-xavi-pascual"
    assert (person.first_name, person.last_name) == ("Xavi", "Pascual")
    assert entry.role == "head_coach"
    assert entry.team_ref.external_id == "2"


def test_acb_staff_entries_skip_blank_names_and_missing_club() -> None:
    """Blank names and team blocks without a clubId are ignored."""
    payload = {
        "teamBoxscores": [
            {"team": {}, "headCoach": "Nobody Here"},
            {"team": {"clubId": 5}, "headCoach": "  ", "assistantCoaches": [None, ""]},
        ]
    }
    assert parse_staff_entries(payload, source="acb") == []


def test_feb_coach_parsed_from_team_profile() -> None:
    """The head coach comes from div.box-entrenador with the FEB c id."""
    html = (FIXTURES / "feb_team_profile.html").read_text(encoding="utf-8")
    result = parse_coach_from_team_profile(
        html, source="feb-primera", team_external_id="42"
    )

    assert result is not None
    person, entry = result
    assert person.ref.external_id == "333852"
    assert (person.first_name, person.last_name) == (
        "Daniel Angel",
        "Garcia Gonzalez",
    )
    assert person.slug == "daniel-angel-garcia-gonzalez-feb-primera-333852"
    assert entry.role == "head_coach"
    assert entry.team_ref.external_id == "42"
    assert entry.person_ref == person.ref


def test_feb_coach_without_photo_falls_back_to_name_id() -> None:
    """With no photo URL the external id is derived from the name."""
    html = (
        '<div class="box-entrenador"><div class="nombre">ANA LOPEZ</div></div>'
    )
    result = parse_coach_from_team_profile(
        html, source="feb-primera", team_external_id="1"
    )
    assert result is not None
    assert result[0].ref.external_id == "staff-ana-lopez"


def test_feb_coach_absent_returns_none() -> None:
    """Pages without a coach block (or an empty name) yield None."""
    assert parse_coach_from_team_profile(
        "<html></html>", source="feb-primera", team_external_id="1"
    ) is None
    assert parse_coach_from_team_profile(
        '<div class="box-entrenador"><div class="nombre"> </div></div>',
        source="feb-primera",
        team_external_id="1",
    ) is None


def test_split_given_and_surnames() -> None:
    """Spanish convention: last two words are the surnames."""
    assert _split_given_and_surnames("RUBEN PERELLO PARICIO") == (
        "Ruben",
        "Perello Paricio",
    )
    assert _split_given_and_surnames("JOSE MANUEL DE LA TORRE") == (
        "Jose Manuel De",
        "La Torre",
    )
    assert _split_given_and_surnames("ANA LOPEZ") == ("Ana", "Lopez")
    assert _split_given_and_surnames("PEPE") == ("Pepe", "Pepe")
