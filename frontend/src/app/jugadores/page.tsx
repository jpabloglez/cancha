import Link from "next/link";

import { AllTimeLeaderboard } from "@/components/AllTimeLeaderboard";
import { MediaImage } from "@/components/MediaImage";
import { PositionBadge } from "@/components/PositionBadge";
import { getAllTimeLeaders, getLeagues, getPlayerOfTheDay, getSeasons } from "@/lib/api";
import type { AllTimeLeader, PlayerOfTheDay } from "@/types/api";

// ---------------------------------------------------------------------------
// Player-of-the-day card
// ---------------------------------------------------------------------------

function PlayerOfTheDayCard({ data }: { data: PlayerOfTheDay }) {
  const { player, latestStats } = data;
  const fullName = player.displayName || `${player.firstName} ${player.lastName}`;
  const initials = `${player.firstName[0] ?? ""}${player.lastName[0] ?? ""}`;

  return (
    <div className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-700 dark:bg-zinc-900">
      <p className="mb-4 text-xs font-semibold uppercase tracking-widest text-orange-600">
        Jugador del día
      </p>
      <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
        <MediaImage asset={player.photo} alt={fullName} initials={initials} size={80} />
        <div className="flex-1 space-y-2">
          <div>
            <Link
              href={`/jugadores/${player.slug}`}
              className="text-xl font-bold hover:underline"
            >
              {fullName}
            </Link>
            <div className="mt-1 flex items-center gap-2">
              <PositionBadge position={player.primaryPosition} />
              {player.nationality && (
                <span className="text-sm text-zinc-500">{player.nationality}</span>
              )}
              {player.heightCm && (
                <span className="text-sm text-zinc-500">{player.heightCm} cm</span>
              )}
            </div>
          </div>

          {latestStats && (
            <div className="flex flex-wrap gap-4 pt-1">
              {[
                { label: "PPG", val: latestStats.pointsPerGame.toFixed(1) },
                { label: "RPG", val: latestStats.reboundsPerGame.toFixed(1) },
                { label: "APG", val: latestStats.assistsPerGame.toFixed(1) },
                { label: "PER", val: latestStats.advanced.playerEfficiencyRating.toFixed(1) },
                { label: "TS%", val: (latestStats.advanced.trueShootingPercent * 100).toFixed(1) + "%" },
              ].map(({ label, val }) => (
                <div key={label} className="text-center">
                  <div className="text-lg font-bold text-zinc-900 dark:text-zinc-100">{val}</div>
                  <div className="text-xs text-zinc-400">{label}</div>
                </div>
              ))}
              <div className="text-center">
                <div className="text-lg font-bold text-zinc-900 dark:text-zinc-100">
                  {latestStats.gamesPlayed}
                </div>
                <div className="text-xs text-zinc-400">PJ · {latestStats.seasonName}</div>
              </div>
            </div>
          )}
        </div>

        <Link
          href={`/jugadores/${player.slug}`}
          className="whitespace-nowrap rounded-lg border border-zinc-200 px-4 py-2 text-sm hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
        >
          Ver perfil →
        </Link>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Player search bar (client interaction handled via Link + search params)
// ---------------------------------------------------------------------------

function PlayerSearchHint() {
  return (
    <div className="rounded-xl border border-zinc-200 bg-zinc-50 p-4 dark:border-zinc-700 dark:bg-zinc-800/40">
      <p className="text-sm text-zinc-500 dark:text-zinc-400">
        Para buscar un jugador específico usa la barra de búsqueda en la parte superior de la página.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page
// ---------------------------------------------------------------------------

export const metadata = {
  title: "Jugadores · Cancha",
  description: "Clasificación histórica y estadísticas acumuladas de jugadores de ACB, Primera FEB y Segunda FEB.",
};

export default async function JugadoresPage() {
  let playerOfTheDay: PlayerOfTheDay | null = null;
  let initialRows: AllTimeLeader[] = [];
  let initialCount = 0;
  let seasonYears: string[] = [];

  try {
    const [potd, allTime, leaguesPage] = await Promise.all([
      getPlayerOfTheDay(),
      getAllTimeLeaders({ stat: "ppg", limit: 10, minGames: 20 }),
      getLeagues(),
    ]);
    playerOfTheDay = potd;
    initialRows = allTime.results;
    initialCount = allTime.count;

    // Collect all season start years across all leagues for the season filter.
    const seasonResponses = await Promise.all(
      leaguesPage.results.map((l) => getSeasons(l.id))
    );
    const yearsSet = new Set<string>();
    for (const resp of seasonResponses) {
      for (const s of resp.results) {
        yearsSet.add(String(new Date(s.startDate).getFullYear()));
      }
    }
    seasonYears = Array.from(yearsSet).sort((a, b) => Number(b) - Number(a));
  } catch {
    // If the API is down, render an empty state rather than a server error.
  }

  return (
    <div className="space-y-10">
      {/* ── Header ──────────────────────────────────────────────────── */}
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Jugadores</h1>
        <p className="text-zinc-500 dark:text-zinc-400">
          Estadísticas históricas acumuladas de todas las temporadas disponibles.
        </p>
      </header>

      {/* ── Search hint ─────────────────────────────────────────────── */}
      <PlayerSearchHint />

      {/* ── Player of the day ───────────────────────────────────────── */}
      {playerOfTheDay && <PlayerOfTheDayCard data={playerOfTheDay} />}

      {/* ── All-time leaderboard ────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Clasificación histórica</h2>
        <AllTimeLeaderboard
          initialRows={initialRows}
          initialCount={initialCount}
          seasons={seasonYears}
        />
      </section>
    </div>
  );
}
