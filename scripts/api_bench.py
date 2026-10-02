#!/usr/bin/env python3
"""HTTP benchmark for the public API (latency per endpoint and concurrent load).

Discovers real URLs from the API itself, so it works against any environment.
Cache busting uses a throw-away query parameter (the API ignores unknown params
but ``cache_page`` keys on the full URL), so cold-path numbers need no server
access.

Usage
-----
    python scripts/api_bench.py endpoints --base http://localhost:8001/api/v1
    python scripts/api_bench.py load --base http://localhost:8001/api/v1 \
        --clients 20 --seconds 30 --cold-ratio 0.0
"""

import argparse
import asyncio
import random
import statistics
import time
import uuid

import httpx


def pct(values: list[float], p: float) -> float:
    """Return the p-th percentile (0-100) of ``values`` in the same unit."""
    if not values:
        return float("nan")
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(round(p / 100 * (len(ordered) - 1))))]


def bust(url: str) -> str:
    """Append a unique query parameter so the response cache cannot hit."""
    return f"{url}{'&' if '?' in url else '?'}_b={uuid.uuid4().hex}"


async def discover(client: httpx.AsyncClient) -> dict[str, list[str]]:
    """Build realistic URL groups (name -> urls) from live API data."""
    get = lambda u: client.get(u)  # noqa: E731
    leagues = (await get("/leagues/")).json()["results"]
    out: dict[str, list[str]] = {"leagues": ["/leagues/"]}
    seasons_by_league = {}
    for lg in leagues:
        seasons_by_league[lg["slug"]] = (await get(f"/seasons/?league={lg['id']}")).json()["results"]
    out["seasons"] = [f"/seasons/?league={lg['id']}" for lg in leagues]
    standings, games, boxscores, rounds = [], [], [], []
    for lg in leagues:
        for s in seasons_by_league[lg["slug"]][:3]:
            standings.append(f"/seasons/{s['id']}/standings/")
            rounds.append(f"/seasons/{s['id']}/rounds/")
            games.append(f"/games/?season={s['id']}&limit=20")
            page = (await get(f"/games/?season={s['id']}&limit=3")).json()["results"]
            boxscores += [f"/games/{g['id']}/boxscore/" for g in page]
    out.update(standings=standings, rounds=rounds, games=games, boxscores=boxscores)
    teams = (await get("/teams/?limit=500")).json()["results"]
    out["teams_list"] = ["/teams/?limit=500", "/teams/?limit=100&search=real"]
    picks = random.Random(1).sample(teams, min(25, len(teams)))
    tp = []
    for t in picks:
        slug = t["slug"]
        ts = (await get(f"/team-seasons/?team={t['id']}")).json()
        results = ts["results"] if isinstance(ts, dict) else ts
        sid = results[0]["season"] if results else None
        tp.append((slug, sid))
    out["team_detail"] = [f"/teams/{s}/" for s, _ in tp]
    out["team_roster"] = [f"/teams/{s}/roster/?season={i}" for s, i in tp if i]
    out["team_staff"] = [f"/teams/{s}/staff/" for s, _ in tp]
    out["team_season_stats"] = [f"/teams/{s}/season-stats/?season={i}" for s, i in tp if i]
    out["team_recent"] = [f"/teams/{s}/recent-games/?limit=10" for s, _ in tp]
    out["team_history"] = [f"/teams/{s}/stats-history/" for s, _ in tp]
    out["team_seasons"] = [f"/team-seasons/?team={t['id']}" for t in picks]
    players = (await get("/players/?limit=60")).json()["results"]
    out["players_list"] = ["/players/?limit=50", "/players/?limit=50&search=garcia"]
    out["player_detail"] = [f"/players/{p['slug']}/" for p in players]
    out["player_stats"] = [f"/players/{p['slug']}/stats/" for p in players]
    ids = [p["id"] for p in players[:4]]
    sid = next((s["id"] for ss in seasons_by_league.values() for s in ss), 1)
    out["compare"] = [f"/players/compare/?ids={','.join(map(str, ids))}&season={sid}"]
    sids = [s["id"] for ss in seasons_by_league.values() for s in ss[:2]]
    out["leaders"] = [f"/stats/leaders/?stat={st}&season={s}&limit=20"
                      for s in sids for st in ("points", "rebounds", "assists", "per")]
    out["alltime"] = [f"/stats/alltime/?stat={st}&limit=25&minGames=50"
                      for st in ("ppg", "per", "ts", "total_points")]
    out["search"] = [f"/search/?q={q}" for q in ("real", "bar", "garcia", "val")]
    out["meta"] = ["/stats/data-freshness/", "/players/player-of-the-day/"]
    return out


async def timed(client: httpx.AsyncClient, url: str) -> tuple[float, int]:
    """GET ``url`` and return (milliseconds, status)."""
    t = time.perf_counter()
    try:
        r = await client.get(url)
        status = r.status_code
    except httpx.HTTPError:
        status = 0
    return (time.perf_counter() - t) * 1000, status


async def endpoints(base: str, samples: int) -> None:
    """Report cold (cache-busted) and warm latency per URL group, sequentially."""
    async with httpx.AsyncClient(base_url=base, timeout=60) as client:
        groups = await discover(client)
        print(f"{'group':20} {'n':>3} {'cold p50':>9} {'cold p95':>9} {'cold max':>9} "
              f"{'warm p50':>9} {'err':>4}")
        for name, urls in groups.items():
            cold, warm, err = [], [], 0
            for url in random.Random(2).sample(urls, min(samples, len(urls))):
                ms, st = await timed(client, bust(url))
                cold.append(ms); err += st != 200
                await timed(client, url)
                ms, st = await timed(client, url)
                warm.append(ms); err += st != 200
            print(f"{name:20} {len(cold):3d} {pct(cold,50):9.0f} {pct(cold,95):9.0f} "
                  f"{max(cold):9.0f} {pct(warm,50):9.0f} {err:4d}")


# Rough traffic shape of a browsing session: league/team/player pages dominate.
MIX = {
    "leagues": 3, "seasons": 3, "standings": 8, "games": 6, "boxscores": 6,
    "teams_list": 5, "team_detail": 6, "team_roster": 6, "team_staff": 4,
    "team_season_stats": 6, "team_recent": 5, "team_history": 6, "team_seasons": 5,
    "players_list": 4, "player_detail": 6, "player_stats": 6, "compare": 2,
    "leaders": 6, "alltime": 4, "search": 5, "meta": 2,
}


async def load(base: str, clients: int, seconds: int, cold_ratio: float) -> None:
    """Hammer the API with concurrent virtual users and report percentiles."""
    limits = httpx.Limits(max_connections=clients * 2)
    async with httpx.AsyncClient(base_url=base, timeout=60, limits=limits) as client:
        groups = await discover(client)
        names = [n for n in MIX if groups.get(n)]
        weights = [MIX[n] for n in names]
        lat: dict[str, list[float]] = {n: [] for n in names}
        errors: dict[str, int] = {n: 0 for n in names}
        stop = time.monotonic() + seconds
        rng = random.Random(3)

        async def user() -> None:
            while time.monotonic() < stop:
                n = rng.choices(names, weights)[0]
                url = rng.choice(groups[n])
                if rng.random() < cold_ratio:
                    url = bust(url)
                ms, st = await timed(client, url)
                lat[n].append(ms)
                errors[n] += st != 200
                await asyncio.sleep(rng.uniform(0, 0.05))

        t0 = time.monotonic()
        await asyncio.gather(*(user() for _ in range(clients)))
        elapsed = time.monotonic() - t0

    allv = [v for vs in lat.values() for v in vs]
    print(f"clients={clients} cold_ratio={cold_ratio} requests={len(allv)} "
          f"rps={len(allv)/elapsed:.0f} errors={sum(errors.values())}")
    print(f"overall p50={pct(allv,50):.0f}ms p95={pct(allv,95):.0f}ms "
          f"p99={pct(allv,99):.0f}ms max={max(allv):.0f}ms mean={statistics.mean(allv):.0f}ms")
    print(f"{'group':20} {'n':>6} {'p50':>7} {'p95':>7} {'max':>7} {'err':>4}")
    for n in sorted(names, key=lambda k: -pct(lat[k], 95) if lat[k] else 0):
        if lat[n]:
            print(f"{n:20} {len(lat[n]):6d} {pct(lat[n],50):7.0f} {pct(lat[n],95):7.0f} "
                  f"{max(lat[n]):7.0f} {errors[n]:4d}")


def main() -> None:
    """Parse arguments and run the chosen benchmark."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("mode", choices=["endpoints", "load"])
    ap.add_argument("--base", default="http://localhost:8000/api/v1")
    ap.add_argument("--samples", type=int, default=10)
    ap.add_argument("--clients", type=int, default=20)
    ap.add_argument("--seconds", type=int, default=30)
    ap.add_argument("--cold-ratio", type=float, default=0.0)
    a = ap.parse_args()
    if a.mode == "endpoints":
        asyncio.run(endpoints(a.base, a.samples))
    else:
        asyncio.run(load(a.base, a.clients, a.seconds, a.cold_ratio))


if __name__ == "__main__":
    main()
