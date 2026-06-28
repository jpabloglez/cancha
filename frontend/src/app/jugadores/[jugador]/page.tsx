import Link from "next/link";
import { notFound } from "next/navigation";

import { AdvancedRadar } from "@/components/AdvancedRadar";
import type { AdvancedRadarSeries } from "@/components/AdvancedRadar";
import { MediaImage } from "@/components/MediaImage";
import { TrendLine } from "@/components/TrendLine";
import { getPlayer, getPlayerStats } from "@/lib/api";
import type { PersonDetail, PlayerSeasonStats } from "@/types/api";

const POSITION_LABELS: Record<string, string> = {
  PG: "Base",
  SG: "Escolta",
  SF: "Alero",
  PF: "Ala-pívot",
  C: "Pívot",
};

// Up to 3 most-recent seasons shown as overlaid radar series.
const RADAR_COLORS = ["#c0612b", "#3b82f6", "#16a34a"];

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

  // Most recent season for header stats and radar; up to 3 for radar series.
  const latest = stats.at(-1);
  const radarSeries: AdvancedRadarSeries[] = stats
    .slice(-3)
    .map((s, i) => ({
      name: s.seasonName,
      stats: s.advanced,
      color: RADAR_COLORS[i],
    }));

  const makeTrend = (fn: (s: PlayerSeasonStats) => number) =>
    stats.map((s) => ({ label: s.seasonName, value: Number(fn(s).toFixed(1)) }));

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

      {stats.length === 0 ? (
        <p className="text-sm text-zinc-500">
          No hay estadísticas disponibles para este jugador.
        </p>
      ) : (
        <>
          {/* ── Season stats table ──────────────────────────────────── */}
          <section className="space-y-2">
            <h2 className="text-lg font-semibold">Estadísticas por temporada</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-zinc-500">
                  <tr>
                    <th className="py-2 pr-4">Temporada</th>
                    <th className="px-2 text-right" title="Partidos jugados">PJ</th>
                    <th className="px-2 text-right" title="Minutos por partido">MIN</th>
                    <th className="px-2 text-right" title="Puntos por partido">PTS</th>
                    <th className="px-2 text-right" title="Rebotes por partido">REB</th>
                    <th className="px-2 text-right" title="Asistencias por partido">ASI</th>
                    <th className="px-2 text-right" title="True Shooting %">TS%</th>
                    <th className="px-2 text-right" title="Effective Field Goal %">eFG%</th>
                    <th className="px-2 text-right" title="Usage rate">USO%</th>
                    <th className="px-2 text-right" title="Player Efficiency Rating">PER</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.map((s, i) => {
                    const isLatest = i === stats.length - 1;
                    return (
                      <tr
                        key={s.seasonId}
                        className={`border-t border-zinc-200 dark:border-zinc-800 ${
                          isLatest
                            ? "bg-zinc-50 font-medium dark:bg-zinc-800/50"
                            : ""
                        }`}
                      >
                        <td className="py-2 pr-4">{s.seasonName}</td>
                        <td className="px-2 text-right tabular-nums">{s.gamesPlayed}</td>
                        <td className="px-2 text-right tabular-nums">{s.minutesPerGame.toFixed(1)}</td>
                        <td className="px-2 text-right tabular-nums">{s.pointsPerGame.toFixed(1)}</td>
                        <td className="px-2 text-right tabular-nums">{s.reboundsPerGame.toFixed(1)}</td>
                        <td className="px-2 text-right tabular-nums">{s.assistsPerGame.toFixed(1)}</td>
                        <td className="px-2 text-right tabular-nums">
                          {(s.advanced.trueShootingPercent * 100).toFixed(1)}%
                        </td>
                        <td className="px-2 text-right tabular-nums">
                          {(s.advanced.effectiveFieldGoalPercent * 100).toFixed(1)}%
                        </td>
                        <td className="px-2 text-right tabular-nums">
                          {(s.advanced.usageRate * 100).toFixed(1)}%
                        </td>
                        <td className="px-2 text-right tabular-nums">
                          {s.advanced.playerEfficiencyRating.toFixed(1)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>

          {/* ── Advanced radar + trend sparklines ───────────────────── */}
          <div className="grid gap-8 md:grid-cols-2">
            <section className="space-y-2">
              <h2 className="text-lg font-semibold">
                Perfil avanzado
                {radarSeries.length > 1
                  ? ` · últimas ${radarSeries.length} temporadas`
                  : latest
                    ? ` · ${latest.seasonName}`
                    : ""}
              </h2>
              {radarSeries.length > 1 && (
                <div className="flex flex-wrap gap-3 text-xs">
                  {radarSeries.map((s, i) => (
                    <span key={s.name} className="flex items-center gap-1">
                      <span
                        className="inline-block h-2 w-4 rounded"
                        style={{ backgroundColor: RADAR_COLORS[i] }}
                      />
                      {s.name}
                    </span>
                  ))}
                </div>
              )}
              <AdvancedRadar series={radarSeries} />
            </section>

            <section className="space-y-2">
              <h2 className="text-lg font-semibold">Evolución</h2>
              <div className="space-y-1">
                {(
                  [
                    { label: "PTS/PJ", color: "#c0612b", fn: (s: PlayerSeasonStats) => s.pointsPerGame },
                    { label: "REB/PJ", color: "#3b82f6", fn: (s: PlayerSeasonStats) => s.reboundsPerGame },
                    { label: "ASI/PJ", color: "#16a34a", fn: (s: PlayerSeasonStats) => s.assistsPerGame },
                  ] as const
                ).map(({ label, color, fn }) => (
                  <div key={label}>
                    <p className="text-xs font-medium text-zinc-500">{label}</p>
                    <TrendLine
                      points={makeTrend(fn)}
                      metricLabel={label}
                      color={color}
                      compact
                    />
                  </div>
                ))}
              </div>
            </section>
          </div>
        </>
      )}
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
