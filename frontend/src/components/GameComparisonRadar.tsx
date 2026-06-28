"use client";

// Two radar charts comparing both teams in a single game box score.
// Each axis is normalized so max(home, away) = 100, meaning the stronger
// team on that dimension always reaches the outer ring. Inverted axes
// (turnovers) flip the ratio so "fewer is better" still points outward.

import {
  PolarAngleAxis,
  PolarGrid,
  PolarRadiusAxis,
  Radar,
  RadarChart,
  ResponsiveContainer,
  Tooltip,
} from "recharts";

import type { BoxScore, TeamBoxScore } from "@/types/api";

const DEFAULT_HOME_COLOR = "#c0612b";
const DEFAULT_AWAY_COLOR = "#2563eb";

// ── helpers ───────────────────────────────────────────────────────────────────

function pct(made: number, att: number): number {
  return att > 0 ? (made / att) * 100 : 0;
}

// Normalize a pair of raw values to [0, 100] relative to each other.
// Inverted: lower raw value → higher radar value.
function normPair(
  a: number,
  b: number,
  inverted = false,
): [number, number] {
  if (inverted) {
    const mn = Math.min(a, b);
    if (!mn && !a && !b) return [100, 100];
    if (!a || !b) return a === 0 ? [100, 100] : [mn / a * 100, mn / b * 100];
    return [mn / a * 100, mn / b * 100];
  }
  const mx = Math.max(a, b);
  if (!mx) return [0, 0];
  return [(a / mx) * 100, (b / mx) * 100];
}

// ── axis definitions ──────────────────────────────────────────────────────────

interface AxisDef {
  label: string;
  inverted?: boolean;
  isPercent?: boolean;
  getValue: (t: TeamBoxScore) => number;
}

const SHOOTING_AXES: AxisDef[] = [
  { label: "PTS",  getValue: (t) => t.points },
  { label: "T2%",  isPercent: true, getValue: (t) => pct(t.fieldGoalsMade - t.threePointMade, t.fieldGoalsAtt - t.threePointAtt) },
  { label: "T3%",  isPercent: true, getValue: (t) => pct(t.threePointMade, t.threePointAtt) },
  { label: "TL%",  isPercent: true, getValue: (t) => pct(t.freeThrowsMade, t.freeThrowsAtt) },
  { label: "ASI",  getValue: (t) => t.assists },
  { label: "TC%",  isPercent: true, getValue: (t) => pct(t.fieldGoalsMade, t.fieldGoalsAtt) },
];

const DEFENSE_AXES: AxisDef[] = [
  { label: "REB",  getValue: (t) => t.reboundsOff + t.reboundsDef },
  { label: "RO",   getValue: (t) => t.reboundsOff },
  { label: "BR",   getValue: (t) => t.steals },
  { label: "TAP",  getValue: (t) => t.blocks },
  { label: "BP",   inverted: true, getValue: (t) => t.turnovers },
  { label: "RD",   getValue: (t) => t.reboundsDef },
];

// ── chart data builder ────────────────────────────────────────────────────────

interface DataPoint {
  metric: string;
  home: number;
  away: number;
  rawHome: number;
  rawAway: number;
  isPercent: boolean;
  inverted: boolean;
}

function buildData(
  axes: AxisDef[],
  homeTs: TeamBoxScore,
  awayTs: TeamBoxScore,
): DataPoint[] {
  return axes.map((ax) => {
    const rawHome = ax.getValue(homeTs);
    const rawAway = ax.getValue(awayTs);
    const [hn, an] = normPair(rawHome, rawAway, ax.inverted);
    return {
      metric: ax.label,
      home: +hn.toFixed(1),
      away: +an.toFixed(1),
      rawHome: +rawHome.toFixed(1),
      rawAway: +rawAway.toFixed(1),
      isPercent: ax.isPercent ?? false,
      inverted: ax.inverted ?? false,
    };
  });
}

// ── tooltip ───────────────────────────────────────────────────────────────────

function GameTooltip({
  active,
  payload,
  homeName,
  awayName,
  homeColor,
  awayColor,
}: {
  active?: boolean;
  payload?: { payload: DataPoint }[];
  homeName: string;
  awayName: string;
  homeColor: string;
  awayColor: string;
}) {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const fmt = (v: number) => d.isPercent ? `${v.toFixed(1)}%` : String(v);
  return (
    <div className="rounded border border-zinc-200 bg-white px-3 py-2 text-xs shadow dark:border-zinc-700 dark:bg-zinc-900">
      <p className="mb-1 font-semibold">{d.metric}</p>
      <p style={{ color: homeColor }}>
        {homeName}: {fmt(d.rawHome)}
      </p>
      <p style={{ color: awayColor }}>
        {awayName}: {fmt(d.rawAway)}
      </p>
      {d.inverted && (
        <p className="mt-1 text-[10px] text-zinc-400">
          (Eje invertido — menos es mejor)
        </p>
      )}
    </div>
  );
}

// ── single radar ──────────────────────────────────────────────────────────────

function OneRadar({
  title,
  data,
  homeColor,
  awayColor,
  homeName,
  awayName,
}: {
  title: string;
  data: DataPoint[];
  homeColor: string;
  awayColor: string;
  homeName: string;
  awayName: string;
}) {
  return (
    <div className="space-y-1">
      <p className="text-center text-xs font-semibold uppercase tracking-wide text-zinc-500">
        {title}
      </p>
      <ResponsiveContainer width="100%" height={260}>
        <RadarChart data={data} margin={{ top: 10, right: 24, bottom: 10, left: 24 }}>
          <PolarGrid />
          <PolarAngleAxis dataKey="metric" tick={{ fontSize: 10 }} />
          <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
          <Radar
            name={awayName}
            dataKey="away"
            stroke={awayColor}
            fill={awayColor}
            fillOpacity={0.18}
            strokeDasharray="4 3"
          />
          <Radar
            name={homeName}
            dataKey="home"
            stroke={homeColor}
            fill={homeColor}
            fillOpacity={0.28}
          />
          <Tooltip
            content={
              <GameTooltip
                homeName={homeName}
                awayName={awayName}
                homeColor={homeColor}
                awayColor={awayColor}
              />
            }
          />
        </RadarChart>
      </ResponsiveContainer>
    </div>
  );
}

// ── public component ──────────────────────────────────────────────────────────

export function GameComparisonRadar({ box }: { box: BoxScore }) {
  const { game, teamStats } = box;

  const homeTs = teamStats.find((t) => t.teamSeason === game.homeTeamSeason)!;
  const awayTs = teamStats.find((t) => t.teamSeason === game.awayTeamSeason)!;

  const homeColor = game.homeTeam.primaryColor || DEFAULT_HOME_COLOR;
  const awayColor = game.awayTeam.primaryColor || DEFAULT_AWAY_COLOR;
  const homeName = game.homeTeam.shortName || game.homeTeam.name;
  const awayName = game.awayTeam.shortName || game.awayTeam.name;

  const shootingData = buildData(SHOOTING_AXES, homeTs, awayTs);
  const defenseData  = buildData(DEFENSE_AXES,  homeTs, awayTs);

  return (
    <div className="space-y-3">
      {/* Legend */}
      <div className="flex justify-center gap-6 text-xs">
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-3 w-5 rounded"
            style={{ backgroundColor: homeColor, opacity: 0.85 }}
          />
          {homeName}
        </span>
        <span className="flex items-center gap-1.5">
          <span
            className="inline-block h-0.5 w-5 border-t-2 border-dashed"
            style={{ borderColor: awayColor }}
          />
          {awayName}
        </span>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <OneRadar
          title="Tiro y anotación"
          data={shootingData}
          homeColor={homeColor}
          awayColor={awayColor}
          homeName={homeName}
          awayName={awayName}
        />
        <OneRadar
          title="Rebotes y control"
          data={defenseData}
          homeColor={homeColor}
          awayColor={awayColor}
          homeName={homeName}
          awayName={awayName}
        />
      </div>
      <p className="text-center text-[10px] text-zinc-400">
        Cada eje normalizado al máximo entre los dos equipos = 100. BP invertido: menos pérdidas → mayor área.
      </p>
    </div>
  );
}
