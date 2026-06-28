"""Golden tests for the FEB profile parsers, against captured real fixtures.

No network and no DB — pure parsing of `feb_player_profile.html` /
`feb_team_profile.html` (real pages captured in Phase 0, plan §5.3).
"""

from datetime import date
from pathlib import Path

import pytest

import connectors
from connectors.parsers.feb import (
    ParserError,
    parse_player_profile,
    parse_team_profile,
)

FIXTURES = Path(connectors.__file__).parent / "tests" / "fixtures"


def _player_html() -> str:
    return (FIXTURES / "feb_player_profile.html").read_text(encoding="utf-8")


def _team_html() -> str:
    return (FIXTURES / "feb_team_profile.html").read_text(encoding="utf-8")


def test_parse_player_profile_bio() -> None:
    """Bio fields (name, birth, origin, physicals, position) parse correctly."""
    profile = parse_player_profile(
        _player_html(), source="feb-primera", person_external_id="1997161"
    )
    assert profile.ref.external_id == "1997161"
    assert profile.display_name == "Ismael Tamba Villen"
    assert profile.birth_date == date(2001, 7, 19)
    assert profile.birth_city == "Puente Genil"
    assert profile.nationality == "ES"
    assert profile.height_cm == 204
    assert profile.weight_kg is None  # "- Kg" on the page
    assert profile.primary_position == "C"  # "Pívot"
    assert profile.photo is None  # FEB exposes no portrait


def test_parse_player_profile_trajectory_links_known_team() -> None:
    """Trajectory rows normalise season/league and link the club's team id."""
    profile = parse_player_profile(
        _player_html(), source="feb-primera", person_external_id="1997161"
    )
    assert len(profile.career) == 7
    current = next(c for c in profile.career if c.season_label == "2024-2025")
    assert current.league_name == "PRIMERA FEB"
    assert current.team_ref is not None
    assert current.team_ref.external_id == "952158"
    # An older stint still parses, with its own club link.
    oldest = next(c for c in profile.career if c.season_label == "2019-2020")
    assert oldest.league_name == "LIGA EBA"
    assert oldest.club_name.startswith("UNICAJA")


def test_parse_team_profile() -> None:
    """Team page yields arena, city and the crest logo reference."""
    profile = parse_team_profile(
        _team_html(), source="feb-primera", team_external_id="952158"
    )
    assert profile.arena == "PABELLÓN ALAMEDA"
    assert profile.city == "Morón de la Frontera"
    assert profile.logo is not None
    assert profile.logo.source_url == (
        "https://imagenes.feb.es/Imagen.aspx?i=952158&ti=1"
    )
    assert profile.logo.attribution == "FEB.es"


def test_parse_player_profile_rejects_unrecognised_page() -> None:
    """A page without the name block fails loudly (structural-change guard)."""
    with pytest.raises(ParserError):
        parse_player_profile(
            "<html><body><p>nope</p></body></html>",
            source="feb-primera",
            person_external_id="1",
        )
