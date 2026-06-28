"""Season aggregation: per-game stats -> materialized season aggregates.

The recompute step of the pipeline (spec §3.3, §4.2). Reads every
``PlayerGameStats`` row for a season, computes basic per-game averages and the
advanced metrics from :mod:`stats.metrics` on season totals, and upserts one
``PlayerSeasonAggregate`` per player. Kept idempotent so it can run after every
ingestion without duplicating rows.
"""

from collections import defaultdict

import numpy as np

from players.models import PlayerGameStats, PlayerSeasonAggregate
from teams.models import Season

from .metrics import (
    calculate_effective_field_goal_percent,
    calculate_player_efficiency_rating,
    calculate_true_shooting_percent,
    calculate_usage_rate,
    scale_per_to_league_average,
)

# Total player-minutes a team logs in a regulation FIBA game (5 players * 40).
# Seed/ingested games are post-game and assumed regulation length here; this is
# the denominator basis for Usage Rate.
_TEAM_MINUTES_PER_GAME = 200.0


def recompute_player_season_aggregates(season_id: int) -> int:
    """Recompute every player's season aggregate for one season.

    Parameters
    ----------
    season_id : int
        Primary key of the season to aggregate.

    Returns
    -------
    int
        Number of player aggregates written (created or updated).

    Notes
    -----
    Advanced metrics are computed on season *totals* (not by averaging per-game
    percentages), which is the standard, mathematically correct way to combine
    shooting efficiency across games.
    """
    season = Season.objects.get(pk=season_id)

    player_lines: dict[int, list[PlayerGameStats]] = defaultdict(list)
    lines = PlayerGameStats.objects.filter(game__season=season).select_related(
        "person", "game", "team_season"
    )
    for line in lines:
        player_lines[line.person_id].append(line)

    # Team totals per (game, team_season) for the Usage Rate denominator.
    from games.models import TeamGameStats

    team_stats_map = {
        (t.game_id, t.team_season_id): t
        for t in TeamGameStats.objects.filter(game__season=season)
    }

    # Build every player's aggregate first; the PER scale is a league-wide step
    # (it needs the minutes-weighted league average), applied before writing.
    built: list[tuple[int, dict[str, float]]] = [
        (person_id, _build_aggregate(person_lines, team_stats_map))
        for person_id, person_lines in player_lines.items()
    ]
    _scale_per(built)

    written = 0
    for person_id, aggregate in built:
        PlayerSeasonAggregate.objects.update_or_create(
            person_id=person_id,
            season=season,
            defaults=aggregate,
        )
        written += 1

    return written


def _scale_per(built: list[tuple[int, dict[str, float]]]) -> None:
    """Rescale every aggregate's PER in place to a league average of 15.

    Parameters
    ----------
    built : list of (int, dict)
        ``(person_id, aggregate)`` pairs. Each aggregate carries the unscaled
        per-minute ``per`` plus ``minutes_per_game`` and ``games_played`` used to
        recover the player's total minutes for the league weighting.

    Notes
    -----
    Mutates each aggregate's ``per`` value; a degenerate league (no minutes)
    leaves the values unchanged (see :func:`stats.metrics.scale_per_to_league_average`).
    """
    if not built:
        return
    unscaled = np.array([agg["per"] for _, agg in built])
    minutes = np.array(
        [agg["minutes_per_game"] * agg["games_played"] for _, agg in built]
    )
    scaled = scale_per_to_league_average(unscaled, minutes)
    for (_, agg), value in zip(built, scaled, strict=True):
        agg["per"] = float(value)


def _build_aggregate(
    person_lines: list[PlayerGameStats],
    team_stats_map: dict[tuple[int, int], "object"],
) -> dict[str, float]:
    """Compute the aggregate field values for one player in a season.

    Parameters
    ----------
    person_lines : list of PlayerGameStats
        All of the player's game lines in the season.
    team_stats_map : dict
        Lookup of ``(game_id, team_season_id) -> TeamGameStats`` used for the
        Usage Rate team-totals denominator.

    Returns
    -------
    dict of str to float
        Field values for :class:`~players.models.PlayerSeasonAggregate`.
    """
    minutes = np.array([line.minutes_played for line in person_lines], dtype=float)
    points = np.array([line.points for line in person_lines], dtype=float)
    rebounds = np.array(
        [line.rebounds_off + line.rebounds_def for line in person_lines], dtype=float
    )
    assists = np.array([line.assists for line in person_lines], dtype=float)
    steals = np.array([line.steals for line in person_lines], dtype=float)
    blocks = np.array([line.blocks for line in person_lines], dtype=float)
    turnovers = np.array([line.turnovers for line in person_lines], dtype=float)
    fga = np.array([line.field_goals_att for line in person_lines], dtype=float)
    fgm = np.array([line.field_goals_made for line in person_lines], dtype=float)
    tpm = np.array([line.three_point_made for line in person_lines], dtype=float)
    fta = np.array([line.free_throws_att for line in person_lines], dtype=float)
    ftm = np.array([line.free_throws_made for line in person_lines], dtype=float)

    games_played = len(person_lines)

    # Season totals, fed to the metric functions as single-element arrays.
    tot_points = np.array([points.sum()])
    tot_fga = np.array([fga.sum()])
    tot_fta = np.array([fta.sum()])
    tot_fgm = np.array([fgm.sum()])
    tot_tpm = np.array([tpm.sum()])
    tot_minutes = np.array([minutes.sum()])
    tot_turnovers = np.array([turnovers.sum()])

    ts_percent = float(
        calculate_true_shooting_percent(tot_points, tot_fga, tot_fta)[0]
    )
    efg_percent = float(
        calculate_effective_field_goal_percent(tot_fgm, tot_tpm, tot_fga)[0]
    )
    per = float(
        calculate_player_efficiency_rating(
            points=tot_points,
            rebounds=np.array([rebounds.sum()]),
            assists=np.array([assists.sum()]),
            steals=np.array([steals.sum()]),
            blocks=np.array([blocks.sum()]),
            turnovers=tot_turnovers,
            missed_field_goals=np.array([(fga - fgm).sum()]),
            missed_free_throws=np.array([(fta - ftm).sum()]),
            minutes_played=tot_minutes,
        )[0]
    )

    # Usage Rate denominator: team totals over the same set of games.
    team_fga = team_fta = team_tov = 0.0
    for line in person_lines:
        team_line = team_stats_map.get((line.game_id, line.team_season_id))
        if team_line is None:
            continue
        team_fga += team_line.field_goals_att
        team_fta += team_line.free_throws_att
        team_tov += team_line.turnovers
    usage_rate = float(
        calculate_usage_rate(
            tot_fga,
            tot_fta,
            tot_turnovers,
            tot_minutes,
            np.array([team_fga]),
            np.array([team_fta]),
            np.array([team_tov]),
            np.array([_TEAM_MINUTES_PER_GAME * games_played]),
        )[0]
    )

    return {
        "games_played": games_played,
        "minutes_per_game": float(minutes.mean()),
        "points_per_game": float(points.mean()),
        "rebounds_per_game": float(rebounds.mean()),
        "assists_per_game": float(assists.mean()),
        "per": per,
        "ts_percent": ts_percent,
        "usage_rate": usage_rate,
        "efg_percent": efg_percent,
    }
