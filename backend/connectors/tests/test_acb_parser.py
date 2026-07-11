"""Golden tests for the ACB JSON-API parsers, against captured real responses.

No network and no DB — pure parsing of `acb_api_matches.json` (a
``Competition/matches`` response for the current Liga edition) and
`acb_api_boxscore.json` (the ``Result/boxscores`` response for the finalised
Valencia Basket vs Barça play-off game 105370), both captured live (plan: ACB
JSON-API discovery 2026-06-27).
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

import connectors
from connectors.parsers.acb import (
    MatchHeader,
    ParserError,
    parse_boxscore,
    parse_matches,
    parse_player_profiles,
    parse_team_profiles,
)
from ingestion.schemas import ExternalRef

FIXTURES = Path(connectors.__file__).parent / "tests" / "fixtures"


def _matches() -> dict:
    return json.loads((FIXTURES / "acb_api_matches.json").read_text(encoding="utf-8"))


def _boxscore() -> dict:
    return json.loads(
        (FIXTURES / "acb_api_boxscore.json").read_text(encoding="utf-8")
    )


def _game_105370_header() -> MatchHeader:
    """Header for the box-score fixture (home Valencia 112, away Barça 113)."""
    return MatchHeader(
        external_id="105370",
        home_team_ref=ExternalRef(source="acb", external_id="13"),
        away_team_ref=ExternalRef(source="acb", external_id="2"),
        home_score=112,
        away_score=113,
        date=datetime(2026, 6, 18, 18, 0, tzinfo=UTC),
    )


def test_parse_matches_season_map_and_rounds() -> None:
    """The schedule yields the editionId↔year map and the round list."""
    schedule = parse_matches(_matches(), source="acb")
    assert schedule.current_edition_id == 90
    assert schedule.seasons[90] == 2025
    assert schedule.seasons[48] == 1983  # full history back to 1983/84
    assert len(schedule.round_ids) > 0


def test_parse_matches_round_number_by_id() -> None:
    """round_number_by_id maps each round id to its matchday number."""
    schedule = parse_matches(_matches(), source="acb")
    # Fixture has id=5884 → roundNumber=1, id=5885 → roundNumber=2, etc.
    assert schedule.round_number_by_id[5884] == 1
    assert schedule.round_number_by_id[5885] == 2
    assert schedule.round_number_by_id[5916] == 33


def test_parse_matches_finished_headers() -> None:
    """Only FINALIZED games become headers, keyed to teams by clubId."""
    schedule = parse_matches(_matches(), source="acb")
    assert len(schedule.headers) == 2
    by_id = {h.external_id: h for h in schedule.headers}
    game = by_id["105372"]  # Barça (home) 80 - 88 Valencia (away)
    assert game.home_team_ref.external_id == "2"
    assert game.away_team_ref.external_id == "13"
    assert (game.home_score, game.away_score) == (80, 88)
    assert game.date == datetime(2026, 6, 22, 18, 0, tzinfo=UTC)
    # Teams are exposed by their stable clubId.
    club_ids = {t.ref.external_id for t in schedule.teams}
    assert {"2", "13"} <= club_ids


def test_parse_boxscore_team_totals() -> None:
    """Team totals come from the quarter-0 'total' node (FG = 2pt + 3pt)."""
    parsed = parse_boxscore(
        _boxscore(), source="acb", header=_game_105370_header()
    )
    by_team = {tb.team_ref.external_id: tb for tb in parsed.game.team_box_scores}
    valencia = by_team["13"]
    assert valencia.points == 112
    assert valencia.field_goals_made == 43  # 36 two + 7 three
    assert valencia.three_point_made == 7
    assert valencia.free_throws_made == 19
    assert (
        2 * (valencia.field_goals_made - valencia.three_point_made)
        + 3 * valencia.three_point_made
        + valencia.free_throws_made
        == valencia.points
    )
    barca = by_team["2"]
    assert barca.points == 113


def test_parse_boxscore_players_and_game() -> None:
    """Both rosters parse with stable ids, real names, and the game header."""
    parsed = parse_boxscore(
        _boxscore(), source="acb", header=_game_105370_header()
    )
    game = parsed.game
    assert game.ref.external_id == "105370"
    assert game.final_score_home == 112
    assert game.final_score_away == 113
    assert game.date == datetime(2026, 6, 18, 18, 0, tzinfo=UTC)
    assert {pb.team_ref.external_id for pb in game.player_box_scores} == {"13", "2"}
    assert all(
        pb.field_goals_made >= pb.three_point_made for pb in game.player_box_scores
    )
    names = {(p.first_name, p.last_name) for p in parsed.persons}
    assert ("El Hadji", "Badio") in names


def test_parse_player_profiles() -> None:
    """Player profiles carry position, preferred name and a headshot ref."""
    profiles = parse_player_profiles(_boxscore(), source="acb")
    assert len(profiles) == 24
    by_id = {p.ref.external_id: p for p in profiles}
    badio = by_id["30000107"]
    assert badio.primary_position == "SG"  # gameRole "Escolta"
    assert badio.display_name == "Brancou Badio"  # nickname preferred
    assert badio.photo is not None
    assert badio.photo.source_url.startswith("https://static.acb.com/")
    assert badio.photo.attribution == "ACB.com"


def test_parse_team_profiles() -> None:
    """Team profiles carry official name, primary colour and a crest ref."""
    profiles = parse_team_profiles(_matches(), source="acb")
    by_id = {p.ref.external_id: p for p in profiles}
    barca = by_id["2"]
    assert barca.official_name == "Barça"
    assert barca.primary_color == "#154284"
    assert barca.logo is not None
    assert barca.logo.source_url.startswith("https://static.acb.com/")
    assert barca.logo.attribution == "ACB.com"


def test_parse_boxscore_rejects_unfinished() -> None:
    """An unfinished match fails loudly (no live ingestion)."""
    payload = _boxscore()
    payload["matchFinished"] = False
    with pytest.raises(ParserError):
        parse_boxscore(payload, source="acb", header=_game_105370_header())
