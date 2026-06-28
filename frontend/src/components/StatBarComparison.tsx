"use client";

// Grouped bar chart comparing players across the basic per-game averages
// (points, rebounds, assists) — spec §6.2.

import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { PlayerSeasonStats } from "@/types/api";

export interface StatBarSeries {
  name: string;
  stats: PlayerSeasonStats;
  color?: string;
}

const COLORS = ["#c0612b", "#2b6fc0", "#2bb673", "#9b2bc0"];

const METRICS: { key: keyof PlayerSeasonStats; label: string }[] = [
  { key: "pointsPerGame", label: "Puntos" },
  { key: "reboundsPerGame", label: "Rebotes" },
  { key: "assistsPerGame", label: "Asistencias" },
];

// Pivot the per-player stats into one row per metric for grouped bars.
function toBarData(series: StatBarSeries[]) {
  return METRICS.map((metric) => {
    const row: Record<string, number | string> = { metric: metric.label };
    for (const s of series) {
      row[s.name] = Number((s.stats[metric.key] as number).toFixed(1));
    }
    return row;
  });
}

/**
 * Render grouped bars comparing the basic averages of several players.
 */
export function StatBarComparison({ series }: { series: StatBarSeries[] }) {
  const data = toBarData(series);
  return (
    <ResponsiveContainer width="100%" height={320}>
      <BarChart data={data}>
        <CartesianGrid strokeDasharray="3 3" />
        <XAxis dataKey="metric" />
        <YAxis />
        <Tooltip />
        <Legend />
        {series.map((s, i) => (
          <Bar
            key={s.name}
            dataKey={s.name}
            fill={s.color ?? COLORS[i % COLORS.length]}
          />
        ))}
      </BarChart>
    </ResponsiveContainer>
  );
}
