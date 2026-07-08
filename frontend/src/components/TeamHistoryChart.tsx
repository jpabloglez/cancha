"use client";

// Multi-series line chart showing a team's key stats per season (spec §6.2,
// plan Phase 4.6). Rendered client-side because Recharts requires browser APIs.

import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { TeamStatsHistoryEntry } from "@/types/api";

interface ChartPoint {
  season: string;
  pts: number;
  reb: number;
  asi: number;
  ortg: number;
  drtg: number;
}

const SERIES = [
  { key: "pts", label: "PTS/PJ", color: "#c0612b" },
  { key: "reb", label: "REB/PJ", color: "#3b82f6" },
  { key: "asi", label: "ASI/PJ", color: "#16a34a" },
] as const;

/**
 * Render a multi-series line chart of team stats across seasons.
 *
 * @param history - Ordered list of per-season team stats (oldest first).
 */
export function TeamHistoryChart({
  history,
}: {
  history: TeamStatsHistoryEntry[];
}) {
  if (history.length < 2) return null;

  const data: ChartPoint[] = [...history]
    .sort((a, b) => a.season.name.localeCompare(b.season.name))
    .map((e) => ({
      season: e.season.name,
      pts: Number(e.team.perGame.points.toFixed(1)),
      reb: Number(e.team.perGame.rebounds.toFixed(1)),
      asi: Number(e.team.perGame.assists.toFixed(1)),
      ortg: Number(e.team.advanced.ortg.toFixed(1)),
      drtg: Number(e.team.advanced.drtg.toFixed(1)),
    }));

  return (
    <ResponsiveContainer width="100%" height={220}>
      <LineChart data={data} margin={{ top: 4, right: 12, bottom: 4, left: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="currentColor" className="opacity-10" />
        <XAxis
          dataKey="season"
          tick={{ fontSize: 11 }}
          tickLine={false}
        />
        <YAxis
          tick={{ fontSize: 11 }}
          tickLine={false}
          axisLine={false}
          width={28}
        />
        <Tooltip
          contentStyle={{ fontSize: 12 }}
          formatter={(value: number, name: string) => [value.toFixed(1), name]}
        />
        <Legend
          iconType="plainline"
          iconSize={16}
          wrapperStyle={{ fontSize: 12 }}
        />
        {SERIES.map((s) => (
          <Line
            key={s.key}
            type="monotone"
            dataKey={s.key}
            name={s.label}
            stroke={s.color}
            strokeWidth={2}
            dot={data.length <= 5}
            activeDot={{ r: 4 }}
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
