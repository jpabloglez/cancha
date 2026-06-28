"use client";

// Radar chart comparing a team's stats against the league average.
// All values are normalized to league-average = 100 so every axis shares the
// same radial scale. "Inverted" axes (lower is better: turnovers, DRtg, fouls)
// are flipped so a larger polygon always means a better outcome.

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

const TEAM_COLOR = "#c0612b";
const AVG_COLOR = "#3b82f6";
const MAX_NORMALIZED = 160; // cap to avoid extreme outliers distorting the chart

export interface RadarAxis {
  key: string;
  label: string;
  inverted?: boolean;
}

interface DataPoint {
  metric: string;
  team: number;
  liga: number;
  rawTeam: number;
  rawAvg: number;
}

function normalize(value: number, avg: number, inverted: boolean): number {
  if (!avg || !value) return 100;
  const ratio = inverted ? avg / value : value / avg;
  return Math.min(ratio * 100, MAX_NORMALIZED);
}

function buildData(
  axes: RadarAxis[],
  teamValues: Record<string, number>,
  avgValues: Record<string, number>,
): DataPoint[] {
  return axes.map(({ key, label, inverted = false }) => {
    const tv = teamValues[key] ?? 0;
    const av = avgValues[key] ?? 1;
    return {
      metric: label,
      team: normalize(tv, av, inverted),
      liga: 100,
      rawTeam: tv,
      rawAvg: av,
    };
  });
}

function fmt(v: number) {
  return v % 1 === 0 ? String(v) : v.toFixed(1);
}

function CustomTooltip({
  active,
  payload,
  teamName,
}: {
  active?: boolean;
  payload?: { payload: DataPoint }[];
  teamName: string;
}) {
  if (!active || !payload?.length) return null;
  const { metric, rawTeam, rawAvg } = payload[0].payload;
  return (
    <div className="rounded border border-zinc-200 bg-white px-3 py-2 text-xs shadow dark:border-zinc-700 dark:bg-zinc-900">
      <p className="mb-1 font-semibold">{metric}</p>
      <p style={{ color: TEAM_COLOR }}>
        {teamName}: {fmt(rawTeam)}
      </p>
      <p style={{ color: AVG_COLOR }}>Liga: {fmt(rawAvg)}</p>
    </div>
  );
}

export function TeamRadar({
  teamName,
  teamColor,
  axes,
  teamValues,
  avgValues,
}: {
  teamName: string;
  teamColor?: string;
  axes: RadarAxis[];
  teamValues: Record<string, number>;
  avgValues: Record<string, number>;
}) {
  const data = buildData(axes, teamValues, avgValues);
  const stroke = teamColor || TEAM_COLOR;

  return (
    <ResponsiveContainer width="100%" height={260}>
      <RadarChart data={data} margin={{ top: 10, right: 20, bottom: 10, left: 20 }}>
        <PolarGrid />
        <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10 }} />
        <PolarRadiusAxis
          domain={[0, MAX_NORMALIZED]}
          tick={false}
          axisLine={false}
        />
        <Radar
          name="Liga"
          dataKey="liga"
          stroke={AVG_COLOR}
          fill={AVG_COLOR}
          fillOpacity={0.12}
          strokeDasharray="4 3"
        />
        <Radar
          name={teamName}
          dataKey="team"
          stroke={stroke}
          fill={stroke}
          fillOpacity={0.28}
        />
        <Tooltip content={<CustomTooltip teamName={teamName} />} />
      </RadarChart>
    </ResponsiveContainer>
  );
}
