"""Unit tests for the advanced metrics engine (spec §4.4).

These run without a database (pure NumPy), validating the formulas and the
divide-by-zero guards on representative inputs.
"""

import numpy as np

from stats.metrics import (
    calculate_ast_percent,
    calculate_effective_field_goal_percent,
    calculate_free_throw_rate,
    calculate_player_efficiency_rating,
    calculate_rebound_percent,
    calculate_three_point_rate,
    calculate_tov_percent,
    calculate_true_shooting_percent,
    calculate_usage_rate,
    estimate_possessions,
)


def test_true_shooting_percent_basic() -> None:
    """TS% matches the closed-form value for a simple line."""
    # 20 pts on 10 FGA and 4 FTA -> 20 / (2 * (10 + 0.44*4)) = 0.8503...
    result = calculate_true_shooting_percent(
        np.array([20.0]), np.array([10.0]), np.array([4.0])
    )
    np.testing.assert_allclose(result, [20.0 / (2 * (10 + 0.44 * 4))])


def test_true_shooting_percent_zero_attempts() -> None:
    """TS% is 0 (not NaN) when there are no scoring attempts."""
    result = calculate_true_shooting_percent(
        np.array([0.0]), np.array([0.0]), np.array([0.0])
    )
    np.testing.assert_array_equal(result, [0.0])


def test_effective_field_goal_percent_weights_threes() -> None:
    """eFG% credits a made three more than a made two."""
    # 5 FGM incl. 2 threes on 10 FGA -> (5 + 0.5*2)/10 = 0.6
    result = calculate_effective_field_goal_percent(
        np.array([5.0]), np.array([2.0]), np.array([10.0])
    )
    np.testing.assert_allclose(result, [0.6])


def test_estimate_possessions() -> None:
    """Possessions follow FGA + 0.44*FTA - OREB + TOV."""
    result = estimate_possessions(
        np.array([80.0]), np.array([20.0]), np.array([12.0]), np.array([10.0])
    )
    np.testing.assert_allclose(result, [80 + 0.44 * 20 - 10 + 12])


def test_usage_rate_zero_minutes_is_zero() -> None:
    """USG% is 0 when the player logged no minutes."""
    result = calculate_usage_rate(
        np.array([5.0]),
        np.array([2.0]),
        np.array([1.0]),
        np.array([0.0]),
        np.array([80.0]),
        np.array([20.0]),
        np.array([12.0]),
        np.array([200.0]),
    )
    np.testing.assert_array_equal(result, [0.0])


def test_player_efficiency_rating_normalizes_by_minutes() -> None:
    """Uncorrected PER divides net production by minutes played."""
    result = calculate_player_efficiency_rating(
        points=np.array([20.0]),
        rebounds=np.array([10.0]),
        assists=np.array([5.0]),
        steals=np.array([2.0]),
        blocks=np.array([1.0]),
        turnovers=np.array([3.0]),
        missed_field_goals=np.array([6.0]),
        missed_free_throws=np.array([1.0]),
        minutes_played=np.array([30.0]),
    )
    expected = (20 + 10 + 5 + 2 + 1 - 6 - 1 - 3) / 30
    np.testing.assert_allclose(result, [expected])


def test_three_point_rate_basic() -> None:
    """3PAr = 3PA / FGA."""
    result = calculate_three_point_rate(np.array([6.0]), np.array([15.0]))
    np.testing.assert_allclose(result, [0.4])


def test_three_point_rate_zero_fga() -> None:
    """3PAr is 0 (not NaN) when there were no field goal attempts."""
    result = calculate_three_point_rate(np.array([0.0]), np.array([0.0]))
    np.testing.assert_array_equal(result, [0.0])


def test_free_throw_rate_basic() -> None:
    """FTr = FTA / FGA."""
    result = calculate_free_throw_rate(np.array([5.0]), np.array([10.0]))
    np.testing.assert_allclose(result, [0.5])


def test_tov_percent_basic() -> None:
    """TOV% = TOV / (FGA + 0.44·FTA + TOV)."""
    # 3 TOV, 10 FGA, 4 FTA -> 3 / (10 + 0.44*4 + 3)
    result = calculate_tov_percent(np.array([3.0]), np.array([10.0]), np.array([4.0]))
    expected = 3.0 / (10.0 + 0.44 * 4.0 + 3.0)
    np.testing.assert_allclose(result, [expected])


def test_tov_percent_zero_possessions() -> None:
    """TOV% is 0 (not NaN) when the denominator is zero."""
    result = calculate_tov_percent(np.array([0.0]), np.array([0.0]), np.array([0.0]))
    np.testing.assert_array_equal(result, [0.0])


def test_rebound_percent_basic() -> None:
    """REB% = player_reb / (player_reb + opponent_reb)."""
    result = calculate_rebound_percent(np.array([4.0]), np.array([6.0]))
    np.testing.assert_allclose(result, [0.4])


def test_rebound_percent_zero_both() -> None:
    """REB% is 0 (not NaN) when both sides are zero."""
    result = calculate_rebound_percent(np.array([0.0]), np.array([0.0]))
    np.testing.assert_array_equal(result, [0.0])


def test_ast_percent_basic() -> None:
    """AST% ≈ AST / team_FGM."""
    result = calculate_ast_percent(np.array([5.0]), np.array([20.0]))
    np.testing.assert_allclose(result, [0.25])


def test_ast_percent_zero_team_fgm() -> None:
    """AST% is 0 (not NaN) when the team made no field goals."""
    result = calculate_ast_percent(np.array([3.0]), np.array([0.0]))
    np.testing.assert_array_equal(result, [0.0])
