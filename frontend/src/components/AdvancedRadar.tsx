"use client";

// Radar / spider chart of a player's advanced metrics (spec §6.2).
// Each metric is scaled to a 0-100 range so the four axes are comparable on a
// single radial axis; this is a relative visual profile, not absolute values.

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { AdvancedStats } from "@/types/api";

export interface AdvancedRadarSeries {
  name: string;
  stats: AdvancedStats;
  color?: string;
}

const COLORS = ["#c0612b", "#2b6fc0", "#2bb673", "#9b2bc0"];

// Each axis maps the raw API value to a 0-100 visual scale.
// TS%, EFG%, Uso are fractions → multiply by 100.
// PER: elite ≈ 25-30, average ≈ 15 → scale so PER 35 = 100.
const AXES: { key: keyof AdvancedStats; label: string; toViz: (v: number) => number }[] = [
  { key: "trueShootingPercent", label: "TS%", toViz: (v) => v * 100 },
  { key: "effectiveFieldGoalPercent", label: "eFG%", toViz: (v) => v * 100 },
  { key: "usageRate", label: "Uso%", toViz: (v) => v * 100 },
  { key: "playerEfficiencyRating", label: "PER", toViz: (v) => Math.min((v / 35) * 100, 100) },
];

function toRadarData(series: AdvancedRadarSeries[]) {
  return AXES.map((axis) => {
    const row: Record<string, number | string> = { metric: axis.label };
    for (const s of series) {
      row[s.name] = Number(axis.toViz(s.stats[axis.key]).toFixed(1));
    }
    return row;
  });
}

function fmtRaw(key: keyof AdvancedStats, value: number): string {
  const axis = AXES.find((a) => a.key === key);
  if (!axis) return String(value);
  if (key === "playerEfficiencyRating") return value.toFixed(1);
  return `${(value * 100).toFixed(1)}%`;
}

function AdvancedTooltip({
  active,
  payload,
  series,
}: {
  active?: boolean;
  payload?: { name: string; payload: Record<string, string | number> }[];
  series: AdvancedRadarSeries[];
}) {
  if (!active || !payload?.length) return null;
  const metric = payload[0].payload.metric as string;
  const axisKey = AXES.find((a) => a.label === metric)?.key;
  return (
    <div className="rounded border border-zinc-200 bg-white px-3 py-2 text-xs shadow dark:border-zinc-700 dark:bg-zinc-900">
      <p className="mb-1 font-semibold">{metric}</p>
      {series.map((s, i) => (
        <p key={s.name} style={{ color: s.color ?? COLORS[i % COLORS.length] }}>
          {s.name}:{" "}
          {axisKey ? fmtRaw(axisKey, s.stats[axisKey]) : "—"}
        </p>
      ))}
    </div>
  );
}

/**
 * Render a radar chart comparing one or more players' (or seasons') advanced profiles.
 */
export function AdvancedRadar({ series }: { series: AdvancedRadarSeries[] }) {
  const data = toRadarData(series);
  return (
    <ResponsiveContainer width="100%" height={300}>
      <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
        <PolarGrid />
        <PolarAngleAxis dataKey="metric" tick={{ fontSize: 11 }} />
        <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
        {series.map((s, i) => (
          <Radar
            key={s.name}
            name={s.name}
            dataKey={s.name}
            stroke={s.color ?? COLORS[i % COLORS.length]}
            fill={s.color ?? COLORS[i % COLORS.length]}
            fillOpacity={0.25}
          />
        ))}
        <Tooltip content={<AdvancedTooltip series={series} />} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
