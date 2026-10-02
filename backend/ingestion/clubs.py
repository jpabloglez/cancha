"""Infer clubs that span seasons from per-season team rows.

FEB issues a new team id (and frequently a new sponsor name) each season, so the
same club shows up as several ``Team`` rows. This module links them by comparing
rosters of consecutive seasons — player ids are stable across seasons — with an
exact (normalized) name match as a fallback.
"""

import re
import unicodedata
from collections import defaultdict
from datetime import date

from django.db import transaction
from django.utils.text import slugify

from players.models import RosterEntry
from teams.models import Club, ClubLinkOverride, Team, TeamSeason

#: Shared players that on their own identify a club across consecutive seasons.
STRONG_SHARED_PLAYERS = 5
#: Shared players needed when the team names also share a distinctive word.
MIN_SHARED_PLAYERS = 3
#: Words too generic to link two team names (sponsors/legal forms excluded
#: implicitly: a sponsor change leaves the city/club word in common).
_GENERIC_TOKENS = frozenset(
    {"club", "baloncesto", "basket", "basquet", "basketball", "deportivo", "sad"}
)


def name_tokens(name: str) -> set[str]:
    """Return the distinctive words (4+ letters) of a team name.

    Parameters
    ----------
    name : str
        Team name as printed by the source.

    Returns
    -------
    set of str
        Lower-case, accent-free words excluding generic basketball terms.
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    words = re.findall(r"[a-z0-9]{4,}", stripped.lower())
    return {w for w in words if w not in _GENERIC_TOKENS}


def normalize_name(name: str) -> str:
    """Return a comparison key for a team name.

    Parameters
    ----------
    name : str
        Team name as printed by the source.

    Returns
    -------
    str
        Lower-case, accent-free name containing only letters and digits.
    """
    stripped = "".join(
        c for c in unicodedata.normalize("NFKD", name) if not unicodedata.combining(c)
    )
    return re.sub(r"[^a-z0-9]", "", stripped.lower())


def match_consecutive(
    previous: dict[int, set[int]],
    following: dict[int, set[int]],
    names: dict[int, str],
    forbidden: frozenset[frozenset[int]] = frozenset(),
) -> list[tuple[int, int]]:
    """Pair teams of two consecutive seasons that belong to the same club.

    Parameters
    ----------
    previous, following : dict of int to set of int
        ``team_id -> player ids`` for the earlier and later season.
    names : dict of int to str
        ``team_id -> team name``, used for the exact-name fallback.
    forbidden : frozenset of frozenset of int
        Team-id pairs that must never be paired (manual "separate" overrides).

    Returns
    -------
    list of (int, int)
        ``(previous_team_id, following_team_id)`` pairs, one-to-one. Identical
        normalized names pair first; the rest are paired by roster overlap
        (greatest first): at least ``STRONG_SHARED_PLAYERS`` shared players, or
        ``MIN_SHARED_PLAYERS`` when the names share a distinctive word.
    """
    pairs: list[tuple[int, int]] = []
    used_prev: set[int] = set()
    used_next: set[int] = set()

    # 1) Identical normalized name in consecutive seasons: same club, and it
    #    must not be re-assigned by roster overlap below.
    by_name = {normalize_name(names[t]): t for t in previous}
    for f_id in following:
        key = normalize_name(names[f_id])
        p_id = by_name.get(key) if key else None
        if (
            p_id is not None
            and p_id not in used_prev
            and frozenset((p_id, f_id)) not in forbidden
        ):
            pairs.append((p_id, f_id))
            used_prev.add(p_id)
            used_next.add(f_id)

    # 2) Remaining teams: roster overlap, greatest first.
    candidates = sorted(
        (
            (overlap, p_id, f_id)
            for p_id, p_players in previous.items()
            if p_id not in used_prev
            for f_id, f_players in following.items()
            if f_id not in used_next
            if frozenset((p_id, f_id)) not in forbidden
            if (overlap := len(p_players & f_players)) >= MIN_SHARED_PLAYERS
            and (
                overlap >= STRONG_SHARED_PLAYERS
                or name_tokens(names[p_id]) & name_tokens(names[f_id])
            )
        ),
        key=lambda c: (-c[0], c[1], c[2]),
    )
    for _overlap, p_id, f_id in candidates:
        if p_id in used_prev or f_id in used_next:
            continue
        pairs.append((p_id, f_id))
        used_prev.add(p_id)
        used_next.add(f_id)
    return pairs


def _find(parent: dict[int, int], x: int) -> int:
    """Union-find root lookup with path compression."""
    while parent[x] != x:
        parent[x] = parent[parent[x]]
        x = parent[x]
    return x


def link_clubs() -> dict[str, int]:
    """Group teams of the same league/source into clubs and persist the links.

    Returns
    -------
    dict
        ``{"clubs": n, "teams_linked": m}`` — clubs spanning at least two teams
        and the number of teams assigned to them.

    Notes
    -----
    Manual :class:`~teams.models.ClubLinkOverride` rows are honoured: "separate"
    pairs are never paired directly and "merge" pairs are always joined.
    Idempotent: groups are recomputed from scratch each run and attached to an
    existing club of its members when that club is not already taken by another
    group; clubs left without teams are deleted and unmatched teams get
    ``club=None``.
    """
    rows = list(
        TeamSeason.objects.order_by("season__start_date")
        .values_list("id", "team_id", "team__name", "team__source", "season_id",
                     "season__start_date", "league_id")
    )
    names: dict[int, str] = {}
    parent: dict[int, int] = {}
    by_league: dict[tuple[int, str], dict[int, dict[int, int]]] = defaultdict(
        lambda: defaultdict(dict)
    )
    start_of: dict[int, date] = {}
    ts_team: dict[int, int] = {}
    for ts_id, team_id, name, source, season_id, start, league_id in rows:
        names[team_id] = name
        parent.setdefault(team_id, team_id)
        by_league[(league_id, source)][season_id][ts_id] = team_id
        start_of[season_id] = start
        ts_team[ts_id] = team_id

    rosters: dict[int, set[int]] = defaultdict(set)
    for ts_id, person_id in RosterEntry.objects.values_list(
        "team_season_id", "person_id"
    ):
        rosters[ts_id].add(person_id)

    forbidden: frozenset[frozenset[int]] = frozenset(
        frozenset((a, b))
        for a, b in ClubLinkOverride.objects.filter(
            kind=ClubLinkOverride.Kind.SEPARATE
        ).values_list("team_a_id", "team_b_id")
    )

    for seasons in by_league.values():
        ordered = sorted(seasons, key=lambda s: start_of[s])
        for earlier, later in zip(ordered, ordered[1:], strict=False):
            prev = {t: rosters[ts] for ts, t in seasons[earlier].items()}
            nxt = {t: rosters[ts] for ts, t in seasons[later].items()}
            for a, b in match_consecutive(prev, nxt, names, forbidden):
                ra, rb = _find(parent, a), _find(parent, b)
                if ra != rb:
                    parent[rb] = ra

    # Exact (normalized) name within a source family links teams across leagues
    # and across gaps, e.g. a club promoted/relegated between Primera and Segunda.
    by_name: dict[tuple[str, str], int] = {}
    for _ts, team_id, name, source, *_rest in rows:
        key = (normalize_name(name), source.split("-")[0])
        if not key[0]:
            continue
        if key in by_name and frozenset((by_name[key], team_id)) not in forbidden:
            ra, rb = _find(parent, by_name[key]), _find(parent, team_id)
            if ra != rb:
                parent[rb] = ra
        else:
            by_name[key] = team_id

    for a, b in ClubLinkOverride.objects.filter(
        kind=ClubLinkOverride.Kind.MERGE
    ).values_list("team_a_id", "team_b_id"):
        if a in parent and b in parent:
            ra, rb = _find(parent, a), _find(parent, b)
            if ra != rb:
                parent[rb] = ra

    groups: dict[int, set[int]] = defaultdict(set)
    for team_id in parent:
        groups[_find(parent, team_id)].add(team_id)

    clubs = 0
    linked_ids: set[int] = set()
    claimed: set[int] = set()
    with transaction.atomic():
        # Largest groups first so a club id is reused by the group that holds
        # most of its former members.
        for members in sorted(groups.values(), key=len, reverse=True):
            if len(members) < 2:
                continue
            former = [
                c
                for c in Team.objects.filter(pk__in=members)
                .order_by("club_id")
                .values_list("club_id", flat=True)
                .distinct()
                if c and c not in claimed
            ]
            latest = _latest_team(members)
            club = (
                Club.objects.get(pk=former[0])
                if former
                else Club(slug=_unique_club_slug(latest.name))
            )
            club.name = latest.name
            club.save()
            claimed.add(club.pk)
            Team.objects.filter(pk__in=members).update(club=club)
            linked_ids |= members
            clubs += 1
        Team.objects.exclude(pk__in=linked_ids).update(club=None)
        Club.objects.exclude(pk__in=claimed).delete()
    linked = len(linked_ids)
    return {"clubs": clubs, "teams_linked": linked}


def _latest_team(team_ids: set[int]) -> Team:
    """Return the team of a group with the most recent season."""
    ts = (
        TeamSeason.objects.filter(team_id__in=team_ids)
        .select_related("team")
        .order_by("-season__start_date")
        .first()
    )
    assert ts is not None
    return ts.team


def _unique_club_slug(name: str) -> str:
    """Return a club slug unique among existing clubs."""
    base = slugify(name)[:50] or "club"
    slug, n = base, 2
    while Club.objects.filter(slug=slug).exists():
        slug, n = f"{base}-{n}", n + 1
    return slug
