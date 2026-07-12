"""Golden tests for the FEB parser against a saved box-score fixture (spec §9)."""

from pathlib import Path

import pytest

from connectors.parsers.feb import ParserError, parse_box_score, parse_game_ids, parse_game_round_map

FIXTURES = Path(__file__).parent / "fixtures"


def _boxscore_html() -> str:
    """Return the representative FEB box-score fixture HTML."""
    return (FIXTURES / "feb_boxscore.html").read_text(encoding="utf-8")


def test_parse_game_ids_dedupes_in_order() -> None:
    """Game ids parse from both legacy and clean links, deduped, in order."""
    html = (
        '<a href="Partido.aspx?p=111">A</a>'        # legacy
        '<a href="/partido/222">B</a>'              # clean URL
        '<a href="Partido.aspx?p=111">A again</a>'  # duplicate
    )
    assert parse_game_ids(html) == ["111", "222"]


def test_parse_box_score_teams_and_score() -> None:
    """Two teams parsed in order with scores taken from the totals rows."""
    parsed = parse_box_score(
        _boxscore_html(), source="feb-primera", game_external_id="999"
    )
    assert parsed.game.ref.external_id == "999"
    assert [t.ref.external_id for t in parsed.teams] == ["100", "200"]
    assert [t.name for t in parsed.teams] == ["CB ALFA", "CB BETA"]
    assert parsed.game.final_score_home == 23
    assert parsed.game.final_score_away == 30
    assert parsed.game.date.year == 2025
    assert parsed.game.date.month == 1
    assert parsed.game.date.day == 18


def test_parse_box_score_player_line_mapping() -> None:
    """Columns map to the right schema fields (incl. duplicate-TC handling)."""
    parsed = parse_box_score(
        _boxscore_html(), source="feb-primera", game_external_id="999"
    )
    assert len(parsed.game.player_box_scores) == 4

    gil = next(
        p for p in parsed.game.player_box_scores if p.person_ref.external_id == "11"
    )
    assert gil.team_ref.external_id == "100"
    assert gil.minutes_played == 30
    assert gil.points == 15
    # TC (first occurrence) = field goals; T3 = threes; TL = free throws.
    assert (gil.field_goals_made, gil.field_goals_att) == (6, 12)
    assert (gil.three_point_made, gil.three_point_att) == (1, 3)
    assert (gil.free_throws_made, gil.free_throws_att) == (2, 2)
    assert gil.rebounds_off == 1
    assert gil.rebounds_def == 4
    assert gil.assists == 3
    assert gil.steals == 2  # BR
    assert gil.turnovers == 1  # BP
    assert gil.blocks == 0  # TF
    assert gil.fouls == 2  # FC


def test_parse_box_score_team_totals() -> None:
    """Team totals row maps to the team box score."""
    parsed = parse_box_score(
        _boxscore_html(), source="feb-primera", game_external_id="999"
    )
    home_total = parsed.game.team_box_scores[0]
    assert home_total.points == 23
    assert (home_total.field_goals_made, home_total.field_goals_att) == (8, 19)
    assert home_total.assists == 4


def test_parse_box_score_rejects_wrong_structure() -> None:
    """A page without two box-score tables fails loudly (spec §3.4)."""
    with pytest.raises(ParserError):
        parse_box_score(
            "<html><body>nope</body></html>",
            source="feb-primera",
            game_external_id="1",
        )


def test_parse_game_round_map_extracts_jornada_labels() -> None:
    """Games under a 'Jornada N' header map to 'JN' round labels."""
    html = (
        '<h1 class="titulo-modulo">Jornada 3 18/10/2024</h1>'
        '<div>'
        '  <a href="/partido/1001">Partido 1</a>'
        '  <a href="/partido/1002">Partido 2</a>'
        '</div>'
        '<h1 class="titulo-modulo">Jornada 4 25/10/2024</h1>'
        '<div>'
        '  <a href="/partido/2001">Partido 3</a>'
        '</div>'
        '<h1 class="titulo-modulo">Play-off cuartos</h1>'
        '<div>'
        '  <a href="/partido/9001">Playoff game</a>'
        '</div>'
    )
    result = parse_game_round_map(html)
    assert result == {"1001": "J3", "1002": "J3", "2001": "J4"}


def test_parse_game_round_map_ignores_non_jornada_headers() -> None:
    """Headers without 'Jornada N' (e.g. playoff labels) are skipped."""
    html = (
        '<h1 class="titulo-modulo">Semifinales</h1>'
        '<div><a href="/partido/5555">game</a></div>'
    )
    assert parse_game_round_map(html) == {}


def test_shooting_handles_spanish_decimals_and_blanks() -> None:
    """Shooting cells with comma decimals and blanks parse to (made, att)."""
    from connectors.parsers.feb import _shooting

    assert _shooting("8/19 42,1%") == (8, 19)
    assert _shooting("") == (0, 0)
    assert _shooting("-") == (0, 0)
