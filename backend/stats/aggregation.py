"""Season aggregation: per-game stats -> materialized season aggregates.

The recompute step of the pipeline (spec §3.3, §4.2). Reads every
``PlayerGameStats`` row for a season, computes basic per-game averages and the
advanced metrics from :mod:`stats.metrics` on season totals, and upserts one
``PlayerSeasonAggregate`` per player. Kept idempotent so it can run after every
ingestion without duplicating rows.
"""

from collections import defaultdict

import numpy as np

from games.models import TeamGameStats
from players.models import PlayerGameStats, PlayerSeasonAggregate
from teams.models import Season

from .metrics import (
    calculate_ast_percent,
    calculate_effective_field_goal_percent,
    calculate_free_throw_rate,
    calculate_player_efficiency_rating,
    calculate_rebound_percent,
    calculate_three_point_rate,
    calculate_tov_percent,
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

    # Team totals per (game, team_season) for the Usage Rate denominator and
    # opponent-stats lookups (rebound/assist percentages).
    team_stats_map = {
        (t.game_id, t.team_season_id): t
        for t in TeamGameStats.objects.filter(game__season=season)
    }

    # game_id -> [team_season_id, ...] lets _build_aggregate find the opponent row.
    game_to_team_ids: dict[int, list[int]] = defaultdict(list)
    for game_id, ts_id in team_stats_map:
        game_to_team_ids[game_id].append(ts_id)

    # Build every player's aggregate first; the PER scale is a league-wide step
    # (it needs the minutes-weighted league average), applied before writing.
    built: list[tuple[int, dict[str, float]]] = [
        (person_id, _build_aggregate(person_lines, team_stats_map, game_to_team_ids))
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
    team_stats_map: dict[tuple[int, int], "TeamGameStats"],
    game_to_team_ids: dict[int, list[int]],
) -> dict[str, float]:
    """Compute the aggregate field values for one player in a season.

    Parameters
    ----------
    person_lines : list of PlayerGameStats
        All of the player's game lines in the season.
    team_stats_map : dict
        Lookup of ``(game_id, team_season_id) -> TeamGameStats`` used for the
        Usage Rate team-totals denominator and opponent-stat lookups.
    game_to_team_ids : dict
        Lookup of ``game_id -> [team_season_id, ...]`` used to find the
        opponent's ``TeamGameStats`` row for rebound/assist percentages.

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
    tpa = np.array([line.three_point_att for line in person_lines], dtype=float)
    fouls = np.array([line.fouls for line in person_lines], dtype=float)
    reb_off = np.array([line.rebounds_off for line in person_lines], dtype=float)
    reb_def = np.array([line.rebounds_def for line in person_lines], dtype=float)

    tot_points = np.array([points.sum()])
    tot_fga = np.array([fga.sum()])
    tot_fta = np.array([fta.sum()])
    tot_fgm = np.array([fgm.sum()])
    tot_tpm = np.array([tpm.sum()])
    tot_tpa = np.array([tpa.sum()])
    tot_ftm = np.array([ftm.sum()])
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

    # Team and opponent totals over the same set of games.
    team_fga = team_fta = team_tov = team_fgm = 0.0
    opp_reb_off = opp_reb_def = 0.0  # used for DRB% and ORB% respectively
    for line in person_lines:
        my_ts_id = line.team_season_id
        game_id = line.game_id
        team_line = team_stats_map.get((game_id, my_ts_id))
        if team_line is not None:
            team_fga += team_line.field_goals_att
            team_fta += team_line.free_throws_att
            team_tov += team_line.turnovers
            team_fgm += team_line.field_goals_made
        opp_ts_ids = [tid for tid in game_to_team_ids.get(game_id, []) if tid != my_ts_id]
        if opp_ts_ids:
            opp_line = team_stats_map.get((game_id, opp_ts_ids[0]))
            if opp_line is not None:
                opp_reb_off += opp_line.rebounds_off
                opp_reb_def += opp_line.rebounds_def

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

    p_orb = np.array([reb_off.sum()])
    p_drb = np.array([reb_def.sum()])
    orb_percent = float(
        calculate_rebound_percent(p_orb, np.array([opp_reb_def]))[0]
    )
    drb_percent = float(
        calculate_rebound_percent(p_drb, np.array([opp_reb_off]))[0]
    )
    ast_percent = float(
        calculate_ast_percent(np.array([assists.sum()]), np.array([team_fgm]))[0]
    )
    three_point_rate = float(calculate_three_point_rate(tot_tpa, tot_fga)[0])
    free_throw_rate = float(calculate_free_throw_rate(tot_fta, tot_fga)[0])
    tov_percent = float(calculate_tov_percent(tot_turnovers, tot_fga, tot_fta)[0])
    mp_percent = float(tot_minutes[0]) / (games_played * 40.0) if games_played > 0 else 0.0

    # Shooting percentages from season totals (accurate; not averages of averages).
    s_two_att = float((tot_fga - tot_tpa)[0])
    s_two_made = float((tot_fgm - tot_tpm)[0])
    s_three_att = float(tot_tpa[0])
    s_three_made = float(tot_tpm[0])
    s_ft_att = float(tot_fta[0])
    s_ft_made = float(tot_ftm[0])

    two_percent = s_two_made / s_two_att if s_two_att > 0 else 0.0
    three_percent = s_three_made / s_three_att if s_three_att > 0 else 0.0
    ft_percent = s_ft_made / s_ft_att if s_ft_att > 0 else 0.0

    return {
        "games_played": games_played,
        "minutes_per_game": float(minutes.mean()),
        "points_per_game": float(points.mean()),
        "rebounds_per_game": float(rebounds.mean()),
        "assists_per_game": float(assists.mean()),
        "steals_per_game": float(steals.mean()),
        "blocks_per_game": float(blocks.mean()),
        "turnovers_per_game": float(turnovers.mean()),
        "fouls_per_game": float(fouls.mean()),
        "two_percent": two_percent,
        "three_percent": three_percent,
        "ft_percent": ft_percent,
        "per": per,
        "ts_percent": ts_percent,
        "usage_rate": usage_rate,
        "efg_percent": efg_percent,
        "three_point_rate": three_point_rate,
        "free_throw_rate": free_throw_rate,
        "tov_percent": tov_percent,
        "mp_percent": mp_percent,
        "orb_percent": orb_percent,
        "drb_percent": drb_percent,
        "ast_percent": ast_percent,
    }
