"""Advanced basketball metrics engine (spec §4.4).

Vectorized, NumPy-based implementations of the standard derived metrics the
platform exposes beyond the raw box score: TS%, eFG%, Usage Rate, an
uncorrected PER and pace. All functions operate element-wise over equally
shaped arrays so a whole season can be computed in a single call.
"""

import numpy as np


def calculate_true_shooting_percent(
    points: np.ndarray,
    field_goals_att: np.ndarray,
    free_throws_att: np.ndarray,
) -> np.ndarray:
    """Compute True Shooting percentage (TS%).

    Parameters
    ----------
    points : np.ndarray
        Total points scored.
    field_goals_att : np.ndarray
        Field goal attempts (2P + 3P).
    free_throws_att : np.ndarray
        Free throw attempts.

    Returns
    -------
    np.ndarray
        TS% as a fraction in [0, 1]; 0 where there were no scoring attempts.

    Notes
    -----
    TS% = PTS / (2 * (FGA + 0.44 * FTA)).
    """
    denominator = 2.0 * (field_goals_att + 0.44 * free_throws_att)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denominator > 0, points / denominator, 0.0)


def calculate_effective_field_goal_percent(
    field_goals_made: np.ndarray,
    three_point_made: np.ndarray,
    field_goals_att: np.ndarray,
) -> np.ndarray:
    """Compute Effective Field Goal percentage (eFG%).

    Parameters
    ----------
    field_goals_made : np.ndarray
        Made field goals (2P + 3P).
    three_point_made : np.ndarray
        Made three-pointers.
    field_goals_att : np.ndarray
        Field goal attempts (2P + 3P).

    Returns
    -------
    np.ndarray
        eFG% as a fraction in [0, 1]; 0 where there were no attempts.

    Notes
    -----
    eFG% = (FGM + 0.5 * 3PM) / FGA.
    """
    numerator = field_goals_made + 0.5 * three_point_made
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(field_goals_att > 0, numerator / field_goals_att, 0.0)


def estimate_possessions(
    field_goals_att: np.ndarray,
    free_throws_att: np.ndarray,
    turnovers: np.ndarray,
    offensive_rebounds: np.ndarray,
) -> np.ndarray:
    """Estimate the number of possessions used.

    Parameters
    ----------
    field_goals_att : np.ndarray
        Field goal attempts.
    free_throws_att : np.ndarray
        Free throw attempts.
    turnovers : np.ndarray
        Turnovers committed.
    offensive_rebounds : np.ndarray
        Offensive rebounds collected.

    Returns
    -------
    np.ndarray
        Estimated possessions.

    Notes
    -----
    POSS = FGA + 0.44 * FTA - OREB + TOV (common single-team approximation).
    """
    return field_goals_att + 0.44 * free_throws_att - offensive_rebounds + turnovers


def calculate_pace(
    possessions: np.ndarray, minutes_played: np.ndarray, regulation_minutes: float = 40.0
) -> np.ndarray:
    """Compute pace (possessions normalized to a regulation game).

    Parameters
    ----------
    possessions : np.ndarray
        Estimated possessions for the team.
    minutes_played : np.ndarray
        Team minutes played (40 for a regulation FIBA game, more with overtime).
    regulation_minutes : float
        Length of a regulation game in minutes (FIBA: 40).

    Returns
    -------
    np.ndarray
        Possessions per regulation game; 0 where no minutes were played.
    """
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(
            minutes_played > 0,
            possessions * regulation_minutes / minutes_played,
            0.0,
        )


def calculate_usage_rate(
    field_goals_att: np.ndarray,
    free_throws_att: np.ndarray,
    turnovers: np.ndarray,
    minutes_played: np.ndarray,
    team_field_goals_att: np.ndarray,
    team_free_throws_att: np.ndarray,
    team_turnovers: np.ndarray,
    team_minutes_played: np.ndarray,
) -> np.ndarray:
    """Compute Usage Rate (USG%).

    Parameters
    ----------
    field_goals_att, free_throws_att, turnovers : np.ndarray
        Player scoring-possession-ending events.
    minutes_played : np.ndarray
        Player minutes played.
    team_field_goals_att, team_free_throws_att, team_turnovers : np.ndarray
        Team totals over the same games.
    team_minutes_played : np.ndarray
        Team minutes played over the same games (typically 200 for 5 players).

    Returns
    -------
    np.ndarray
        USG% as a fraction in [0, 1]; 0 where the denominator is zero.

    Notes
    -----
    USG% = ((FGA + 0.44*FTA + TOV) * (TeamMP / 5))
           / (MP * (TeamFGA + 0.44*TeamFTA + TeamTOV)).
    """
    player_plays = field_goals_att + 0.44 * free_throws_att + turnovers
    team_plays = team_field_goals_att + 0.44 * team_free_throws_att + team_turnovers
    denominator = minutes_played * team_plays
    numerator = player_plays * (team_minutes_played / 5.0)
    with np.errstate(divide="ignore", invalid="ignore"):
        return np.where(denominator > 0, numerator / denominator, 0.0)


def calculate_player_efficiency_rating(
    points: np.ndarray,
    rebounds: np.ndarray,
    assists: np.ndarray,
    steals: np.ndarray,
    blocks: np.ndarray,
    turnovers: np.ndarray,
    missed_field_goals: np.ndarray,
    missed_free_throws: np.ndarray,
    minutes_played: np.ndarray,
) -> np.ndarray:
    """Compute a simplified, uncorrected Player Efficiency Rating (PER).

    This is the unadjusted/uncorrected version of PER (does not apply league
    pace or position adjustments), intended as a quick relative indicator
    rather than the official Hollinger formula.

    Parameters
    ----------
    points : np.ndarray
        Total points scored per game.
    rebounds : np.ndarray
        Total rebounds (offensive + defensive) per game.
    assists : np.ndarray
        Total assists per game.
    steals : np.ndarray
        Total steals per game.
    blocks : np.ndarray
        Total blocks per game.
    turnovers : np.ndarray
        Total turnovers per game.
    missed_field_goals : np.ndarray
        Missed field goal attempts per game.
    missed_free_throws : np.ndarray
        Missed free throw attempts per game.
    minutes_played : np.ndarray
        Minutes played per game.

    Returns
    -------
    np.ndarray
        Uncorrected PER value per game, normalized by minutes played.

    Notes
    -----
    All input arrays must share the same shape and represent the same set of
    games, ordered consistently across arrays.
    """
    production = (
        points
        + rebounds
        + assists
        + steals
        + blocks
        - missed_field_goals
        - missed_free_throws
        - turnovers
    )
    with np.errstate(divide="ignore", invalid="ignore"):
        per = np.where(minutes_played > 0, production / minutes_played, 0.0)
    return per


#: League-average PER, the value the normalized scale is anchored to (Hollinger).
PER_LEAGUE_AVERAGE = 15.0


def scale_per_to_league_average(
    unscaled_per: np.ndarray,
    minutes_played: np.ndarray,
    league_average: float = PER_LEAGUE_AVERAGE,
) -> np.ndarray:
    """Scale per-minute PER values so the league average equals 15.

    :func:`calculate_player_efficiency_rating` returns an *unscaled*, per-minute
    rating (production divided by minutes), which sits below 1. Hollinger's PER
    rescales that so the **minutes-weighted league average is 15.0**, giving the
    familiar ~10–30 player range. This applies that final normalization across a
    whole league/season (the only stage where the league average is known).

    Parameters
    ----------
    unscaled_per : np.ndarray
        Each player's unscaled per-minute rating.
    minutes_played : np.ndarray
        Each player's total minutes (the weighting for the league average), in
        the same order as ``unscaled_per``.
    league_average : float
        Target minutes-weighted average for the scaled output (default 15.0).

    Returns
    -------
    np.ndarray
        Scaled PER values. Returned unchanged when total minutes or league
        production is non-positive (nothing to anchor against).

    Notes
    -----
    The minutes-weighted mean of the per-minute rating equals total league
    production over total league minutes, so the scale factor is
    ``league_average / (Σ unscaled_per·minutes / Σ minutes)``.
    """
    total_minutes = float(minutes_played.sum())
    total_production = float((unscaled_per * minutes_played).sum())
    if total_minutes <= 0 or total_production <= 0:
        return unscaled_per
    league_unscaled = total_production / total_minutes
    return unscaled_per * (league_average / league_unscaled)
