"use client";

import { useState } from "react";

import { AdvancedRadar } from "@/components/AdvancedRadar";
import type { AdvancedRadarSeries } from "@/components/AdvancedRadar";
import { TrendLine } from "@/components/TrendLine";
import type { PlayerSeasonStats } from "@/types/api";

const RADAR_COLORS = ["#c0612b", "#3b82f6", "#16a34a"];

interface Props {
  stats: PlayerSeasonStats[];
}

export function PlayerStatsSection({ stats }: Props) {
  const [selectedSeasonId, setSelectedSeasonId] = useState<string | "all">("all");

  if (stats.length === 0) {
    return (
      <p className="text-sm text-zinc-500">
        No hay estadísticas disponibles para este jugador.
      </p>
    );
  }

  const visibleStats =
    selectedSeasonId === "all"
      ? stats
      : stats.filter((s) => s.seasonId === selectedSeasonId);

  // Radar: up to 3 most-recent from the visible selection.
  const radarSource = selectedSeasonId === "all" ? stats.slice(-3) : visibleStats;
  const radarSeries: AdvancedRadarSeries[] = radarSource.map((s, i) => ({
    name: s.seasonName,
    stats: s.advanced,
    color: RADAR_COLORS[i % RADAR_COLORS.length],
  }));

  const makeTrend = (fn: (s: PlayerSeasonStats) => number) =>
    stats.map((s) => ({ label: s.seasonName, value: Number(fn(s).toFixed(1)) }));

  const pct = (v: number) => `${(v * 100).toFixed(1)}%`;

  return (
    <>
      {/* ── Season filter ────────────────────────────────────────── */}
      <div className="flex flex-wrap items-center gap-3">
        <span className="text-sm font-medium text-zinc-500">Temporada:</span>
        <div className="flex flex-wrap gap-1">
          <button
            onClick={() => setSelectedSeasonId("all")}
            className={`rounded-full px-3 py-1 text-sm transition-colors ${
              selectedSeasonId === "all"
                ? "bg-orange-600 text-white"
                : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            }`}
          >
            Todas ({stats.length})
          </button>
          {stats.map((s) => (
            <button
              key={s.seasonId}
              onClick={() => setSelectedSeasonId(s.seasonId)}
              className={`rounded-full px-3 py-1 text-sm transition-colors ${
                selectedSeasonId === s.seasonId
                  ? "bg-orange-600 text-white"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
              }`}
            >
              {s.seasonName}
            </button>
          ))}
        </div>
        {stats.length === 1 && (
          <p className="text-xs text-zinc-400">
            Solo hay datos para esta temporada. El jugador puede haber jugado en
            otras ligas o temporadas no disponibles.
          </p>
        )}
      </div>

      {/* ── Per-season stats table ───────────────────────────────── */}
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
                <th className="px-2 text-right" title="Robos por partido">ROB</th>
                <th className="px-2 text-right" title="Tapones por partido">TAP</th>
                <th className="px-2 text-right" title="Pérdidas por partido">PÉR</th>
                <th className="px-2 text-right" title="Faltas por partido">FLT</th>
                <th className="px-2 text-right" title="% tiro de 2">T2%</th>
                <th className="px-2 text-right" title="% tiro de 3">T3%</th>
                <th className="px-2 text-right" title="% tiros libres">TL%</th>
                <th className="px-2 text-right" title="True Shooting %">TS%</th>
                <th className="px-2 text-right" title="Effective Field Goal %">eFG%</th>
                <th className="px-2 text-right" title="Usage rate">USO%</th>
                <th className="px-2 text-right" title="Player Efficiency Rating">PER</th>
                <th className="px-2 text-right" title="Tasa de intentos de 3 (3PA/FGA)">3PAr</th>
                <th className="px-2 text-right" title="Tasa de tiros libres (FTA/FGA)">TLr</th>
                <th className="px-2 text-right" title="Tasa de pérdidas">T.P.%</th>
                <th className="px-2 text-right" title="% rebote ofensivo">RO%</th>
                <th className="px-2 text-right" title="% rebote defensivo">RD%</th>
                <th className="px-2 text-right" title="% asistencias (proxy)">ASI%</th>
              </tr>
            </thead>
            <tbody>
              {visibleStats.map((s) => {
                const isSelected = selectedSeasonId === s.seasonId;
                return (
                  <tr
                    key={s.seasonId}
                    onClick={() =>
                      setSelectedSeasonId(
                        selectedSeasonId === s.seasonId ? "all" : s.seasonId
                      )
                    }
                    className={`cursor-pointer border-t border-zinc-200 dark:border-zinc-800 ${
                      isSelected
                        ? "bg-orange-50 font-medium dark:bg-orange-950/20"
                        : "hover:bg-zinc-50 dark:hover:bg-zinc-800/50"
                    }`}
                  >
                    <td className="py-2 pr-4">{s.seasonName}</td>
                    <td className="px-2 text-right tabular-nums">{s.gamesPlayed}</td>
                    <td className="px-2 text-right tabular-nums">{s.minutesPerGame.toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{s.pointsPerGame.toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{s.reboundsPerGame.toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{s.assistsPerGame.toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{(s.stealsPerGame ?? 0).toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{(s.blocksPerGame ?? 0).toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{(s.turnoversPerGame ?? 0).toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{(s.foulsPerGame ?? 0).toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.twoPercent ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.threePercent ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.ftPercent ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.trueShootingPercent)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.effectiveFieldGoalPercent)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.usageRate)}</td>
                    <td className="px-2 text-right tabular-nums">{s.advanced.playerEfficiencyRating.toFixed(1)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.threePointRate ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{(s.advanced.freeThrowRate ?? 0).toFixed(2)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.tovPercent ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.orbPercent ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.drbPercent ?? 0)}</td>
                    <td className="px-2 text-right tabular-nums">{pct(s.advanced.astPercent ?? 0)}</td>
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
              ? ` · ${radarSeries.map((s) => s.name).join(" / ")}`
              : radarSeries[0]
                ? ` · ${radarSeries[0].name}`
                : ""}
          </h2>
          {radarSeries.length > 1 && (
            <div className="flex flex-wrap gap-3 text-xs">
              {radarSeries.map((s, i) => (
                <span key={s.name} className="flex items-center gap-1">
                  <span
                    className="inline-block h-2 w-4 rounded"
                    style={{ backgroundColor: RADAR_COLORS[i % RADAR_COLORS.length] }}
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
          {stats.length < 2 ? (
            <p className="text-sm text-zinc-400">
              Se necesitan al menos 2 temporadas para mostrar la evolución.
            </p>
          ) : (
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
          )}
        </section>
      </div>
    </>
  );
}
