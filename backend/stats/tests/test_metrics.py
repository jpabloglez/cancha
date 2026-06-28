"""Unit tests for the advanced metrics engine (spec §4.4).

These run without a database (pure NumPy), validating the formulas and the
divide-by-zero guards on representative inputs.
"""

import numpy as np

from stats.metrics import (
    calculate_effective_field_goal_percent,
    calculate_player_efficiency_rating,
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
