import Link from "next/link";
import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { MediaImage } from "@/components/MediaImage";
import { PlayerStatsSection } from "@/components/PlayerStatsSection";
import { getPlayer, getPlayerStats } from "@/lib/api";
import type { PersonDetail, PlayerSeasonStats } from "@/types/api";

const POSITION_LABELS: Record<string, string> = {
  PG: "Base",
  SG: "Escolta",
  SF: "Alero",
  PF: "Ala-pívot",
  C: "Pívot",
};

export async function generateMetadata({
  params,
}: {
  params: Promise<{ jugador: string }>;
}): Promise<Metadata> {
  try {
    const { jugador } = await params;
    const player = await getPlayer(jugador);
    const name = player.displayName || `${player.firstName} ${player.lastName}`;
    return {
      title: `${name} · Basket Stats`,
      description: `Estadísticas de carrera de ${name}: puntos, rebotes, asistencias y métricas avanzadas en ACB, Primera FEB y Segunda FEB.`,
    };
  } catch {
    return { title: "Jugador · Basket Stats" };
  }
}

export default async function PlayerPage({
  params,
}: {
  params: Promise<{ jugador: string }>;
}) {
  const { jugador } = await params;

  let player!: PersonDetail;
  let stats: PlayerSeasonStats[] = [];

  try {
    [player, stats] = await Promise.all([
      getPlayer(jugador),
      getPlayerStats(jugador),
    ]);
  } catch {
    notFound();
  }

  const fullName = player.displayName || `${player.firstName} ${player.lastName}`;
  const initials = `${player.firstName[0] ?? ""}${player.lastName[0] ?? ""}`;
  const origin = [player.birthCity, player.birthCountry].filter(Boolean).join(", ");
  const positionLabel = player.primaryPosition
    ? (POSITION_LABELS[player.primaryPosition] ?? player.primaryPosition)
    : null;

  const latest = stats.at(-1);

  return (
    <div className="space-y-8">
      {/* ── Header ────────────────────────────────────────────────── */}
      <header className="flex flex-col gap-6 sm:flex-row sm:items-start">
        <MediaImage
          asset={player.photo}
          alt={fullName}
          initials={initials}
          size={112}
        />
        <div className="flex-1 space-y-3">
          <div>
            <h1 className="text-2xl font-bold">{fullName}</h1>
            <p className="text-sm text-zinc-500">
              {[positionLabel, player.nationality].filter(Boolean).join(" · ")}
            </p>
          </div>

          {/* Key bio facts inline */}
          <dl className="flex flex-wrap gap-x-6 gap-y-1 text-sm">
            {origin && <InlineFact label="Origen" value={origin} />}
            {player.birthDate && (
              <InlineFact label="Nac." value={formatDate(player.birthDate)} />
            )}
            {player.heightCm && (
              <InlineFact label="Altura" value={`${player.heightCm} cm`} />
            )}
            {player.weightKg && (
              <InlineFact label="Peso" value={`${player.weightKg} kg`} />
            )}
          </dl>

          {/* Latest season quick stats */}
          {latest && (
            <div className="flex flex-wrap gap-3">
              {(
                [
                  ["PJ", latest.gamesPlayed, 0],
                  ["MIN", latest.minutesPerGame, 1],
                  ["PTS", latest.pointsPerGame, 1],
                  ["REB", latest.reboundsPerGame, 1],
                  ["ASI", latest.assistsPerGame, 1],
                  ["PER", latest.advanced.playerEfficiencyRating, 1],
                ] as [string, number, number][]
              ).map(([label, val, dec]) => (
                <div
                  key={label}
                  className="rounded-lg border border-zinc-200 bg-zinc-50 px-3 py-1.5 text-center dark:border-zinc-700 dark:bg-zinc-800"
                >
                  <p className="text-sm font-bold tabular-nums">
                    {val.toFixed(dec)}
                  </p>
                  <p className="text-[10px] text-zinc-500">{label}</p>
                </div>
              ))}
              <div className="self-end pb-1 text-xs text-zinc-400">
                {latest.seasonName}
              </div>
            </div>
          )}
          {/* Comparar link */}
          <div>
            <Link
              href={`/comparar?ids=${player.slug}`}
              className="inline-block rounded-lg border border-zinc-300 px-3 py-1.5 text-sm text-zinc-600 hover:bg-zinc-50 dark:border-zinc-600 dark:text-zinc-400 dark:hover:bg-zinc-800"
            >
              Comparar con otro jugador →
            </Link>
          </div>
        </div>
      </header>

      {/* ── Career trajectory ─────────────────────────────────────── */}
      {player.career.length > 0 && (
        <section className="space-y-2">
          <h2 className="text-lg font-semibold">Trayectoria</h2>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {player.career.map((c) => (
              <li
                key={`${c.seasonLabel}-${c.clubName}`}
                className="flex items-center justify-between py-2 text-sm"
              >
                <div className="flex items-center gap-2">
                  {c.teamSlug ? (
                    <Link
                      href={`/equipos/${c.teamSlug}`}
                      className="font-medium hover:underline"
                    >
                      {c.clubName}
                    </Link>
                  ) : (
                    <span className="font-medium">{c.clubName}</span>
                  )}
                  {c.leagueName && (
                    <span className="rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] text-zinc-500 dark:bg-zinc-800">
                      {c.leagueName}
                    </span>
                  )}
                </div>
                <span className="text-zinc-400">{c.seasonLabel}</span>
              </li>
            ))}
          </ul>
        </section>
      )}

      {/* ── Career totals ─────────────────────────────────────────── */}
      {stats.length > 0 && (() => {
        const totalGames = stats.reduce((s, r) => s + r.gamesPlayed, 0);
        const w = (fn: (s: PlayerSeasonStats) => number) =>
          totalGames > 0
            ? stats.reduce((acc, r) => acc + fn(r) * r.gamesPlayed, 0) / totalGames
            : 0;
        const totalPts = stats.reduce((s, r) => s + r.pointsPerGame * r.gamesPlayed, 0);
        return (
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Totales históricos</h2>
            <div className="flex flex-wrap gap-3">
              {(
                [
                  ["Partidos", totalGames.toFixed(0)],
                  ["Temporadas", String(stats.length)],
                  ["Pts. totales", totalPts.toFixed(0)],
                  ["PPG carrera", w((s) => s.pointsPerGame).toFixed(1)],
                  ["RPG carrera", w((s) => s.reboundsPerGame).toFixed(1)],
                  ["APG carrera", w((s) => s.assistsPerGame).toFixed(1)],
                  ["PER carrera", w((s) => s.advanced.playerEfficiencyRating).toFixed(1)],
                ] as [string, string][]
              ).map(([label, val]) => (
                <div
                  key={label}
                  className="rounded-lg border border-zinc-200 bg-zinc-50 px-4 py-2 text-center dark:border-zinc-700 dark:bg-zinc-800"
                >
                  <p className="text-base font-bold tabular-nums text-zinc-900 dark:text-zinc-100">{val}</p>
                  <p className="text-[10px] text-zinc-500">{label}</p>
                </div>
              ))}
            </div>
            <p className="text-xs text-zinc-400">
              Basado en {stats.length} temporada{stats.length !== 1 ? "s" : ""} con
              datos disponibles
              {stats.length === 1 && " — el jugador puede haber jugado en otras ligas o épocas sin datos ingresados"}.
            </p>
          </section>
        );
      })()}

      {/* ── Season stats table + radar + trends (interactive) ─────── */}
      <PlayerStatsSection stats={stats} />
    </div>
  );
}

function InlineFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex gap-1">
      <dt className="text-zinc-400">{label}:</dt>
      <dd className="font-medium">{value}</dd>
    </div>
  );
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}
