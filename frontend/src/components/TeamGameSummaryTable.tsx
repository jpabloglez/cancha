"use client";

import { useState } from "react";

import type { BoxScore, TeamBoxScore } from "@/types/api";

// Classic ACB valoración: PTS + REB + ASI + ROB + TAP - PER - missed FG - missed FT
function valuation(t: TeamBoxScore): number {
  return (
    t.points +
    t.reboundsOff +
    t.reboundsDef +
    t.assists +
    t.steals +
    t.blocks -
    t.turnovers -
    (t.fieldGoalsAtt - t.fieldGoalsMade) -
    (t.freeThrowsAtt - t.freeThrowsMade)
  );
}

function teamMinutes(
  playerStats: BoxScore["playerStats"],
  teamSeasonId: number,
): number {
  return playerStats
    .filter((p) => p.teamSeason === teamSeasonId)
    .reduce((s, p) => s + p.minutesPlayed, 0);
}

// ── column definitions ────────────────────────────────────────────────────────

// Shooting columns carry made+att so totales shows "X/Y" and medias shows "X.X%".
// Counting columns are plain numbers; medias shows per-game average (1 dp).
type CellValue = { made: number; att: number } | number;

interface Col {
  header: string;
  group?: string;
  shooting?: true;   // when true, medias mode renders as shooting percentage
  get: (t: TeamBoxScore, opp: TeamBoxScore) => CellValue;
}

const COLS: Col[] = [
  // counting stats (no group)
  { header: "PT",  get: (t) => t.points },
  { header: "T2",  shooting: true, get: (t) => ({ made: t.fieldGoalsMade - t.threePointMade, att: t.fieldGoalsAtt - t.threePointAtt }) },
  { header: "T3",  shooting: true, get: (t) => ({ made: t.threePointMade, att: t.threePointAtt }) },
  { header: "TC",  shooting: true, get: (t) => ({ made: t.fieldGoalsMade, att: t.fieldGoalsAtt }) },
  { header: "TL",  shooting: true, get: (t) => ({ made: t.freeThrowsMade, att: t.freeThrowsAtt }) },
  // rebounds
  { header: "RO",  group: "REBOTES", get: (t) => t.reboundsOff },
  { header: "RD",  group: "REBOTES", get: (t) => t.reboundsDef },
  { header: "RT",  group: "REBOTES", get: (t) => t.reboundsOff + t.reboundsDef },
  // playmaking / defense
  { header: "AS",  get: (t) => t.assists },
  { header: "BR",  get: (t) => t.steals },
  { header: "BP",  get: (t) => t.turnovers },
  { header: "TAP", get: (t) => t.blocks },
  // fouls
  { header: "FC",  group: "FALTAS", get: (t) => t.fouls },
  { header: "FR",  group: "FALTAS", get: (_t, opp) => opp.fouls },
  // efficiency
  { header: "VA",  get: (t) => valuation(t) },
];

// Build group spans for the second header row
interface GroupSpan { label: string; span: number; startIdx: number }
function buildGroups(): GroupSpan[] {
  const groups: GroupSpan[] = [];
  let i = 0;
  while (i < COLS.length) {
    const g = COLS[i].group;
    if (!g) { i++; continue; }
    let span = 0;
    const startIdx = i;
    while (i < COLS.length && COLS[i].group === g) { span++; i++; }
    groups.push({ label: g, span, startIdx });
  }
  return groups;
}
const GROUPS = buildGroups();

// ── formatting helpers ────────────────────────────────────────────────────────

function fmtCell(col: Col, val: CellValue, medias: boolean, games: number): string {
  if (typeof val === "number") {
    // Counting stat: totales = integer, medias = per-game average (1 dp)
    return medias ? (val / games).toFixed(1) : String(val);
  }
  // Shooting stat
  if (medias) {
    // Medias mode: show shooting percentage (made ÷ att × 100)
    if (!col.shooting) {
      return `${(val.made / games).toFixed(1)}/${(val.att / games).toFixed(1)}`;
    }
    const pct = val.att > 0 ? (val.made / val.att) * 100 : 0;
    return `${pct.toFixed(1)}%`;
  }
  return `${val.made}/${val.att}`;
}

// ── component ─────────────────────────────────────────────────────────────────

export function TeamGameSummaryTable({ box }: { box: BoxScore }) {
  const [medias, setMedias] = useState(false);

  const { game, teamStats, playerStats } = box;
  const homeTs = teamStats.find((t) => t.teamSeason === game.homeTeamSeason)!;
  const awayTs = teamStats.find((t) => t.teamSeason === game.awayTeamSeason)!;
  const homeMin = teamMinutes(playerStats, game.homeTeamSeason);
  const awayMin = teamMinutes(playerStats, game.awayTeamSeason);

  // For a single game PART = 1; formula stays clean if extended to N games later.
  const GAMES = 1;

  const rows = [
    { team: game.homeTeam, own: homeTs, opp: awayTs, minutes: homeMin },
    { team: game.awayTeam, own: awayTs, opp: homeTs, minutes: awayMin },
  ];

  // Which columns need a group header above them?
  const groupSet = new Set(GROUPS.map((g) => g.startIdx));

  return (
    <div className="space-y-2">
      {/* Toggle */}
      <div className="flex items-center justify-end gap-2 text-sm">
        <span className={medias ? "text-zinc-400" : "font-medium"}>Totales</span>
        <button
          role="switch"
          aria-checked={medias}
          onClick={() => setMedias((m) => !m)}
          className={`relative inline-flex h-5 w-9 flex-shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors focus:outline-none ${
            medias ? "bg-blue-600" : "bg-zinc-300 dark:bg-zinc-600"
          }`}
        >
          <span
            className={`pointer-events-none inline-block h-4 w-4 translate-x-0 rounded-full bg-white shadow ring-0 transition-transform ${
              medias ? "translate-x-4" : "translate-x-0"
            }`}
          />
        </button>
        <span className={medias ? "font-medium" : "text-zinc-400"}>Medias</span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-zinc-200 dark:border-zinc-700">
        <table className="w-full text-xs">
          {/* Group header row: spans grouped columns, single empty cell for ungrouped */}
          <thead>
            <tr className="bg-blue-950 text-white">
              <th className="px-3 py-2" />
              <th className="px-2 py-2" />
              <th className="px-2 py-2" />
              {(() => {
                const cells: React.ReactNode[] = [];
                let i = 0;
                while (i < COLS.length) {
                  const grp = GROUPS.find((g) => g.startIdx === i);
                  if (grp) {
                    cells.push(
                      <th
                        key={`gh-${i}`}
                        colSpan={grp.span}
                        className="border-l border-blue-800 px-2 py-2 text-center text-[11px] font-bold uppercase tracking-widest"
                      >
                        {grp.label}
                      </th>,
                    );
                    i += grp.span;
                  } else {
                    cells.push(<th key={`gh-${i}`} className="px-2 py-2" />);
                    i++;
                  }
                }
                return cells;
              })()}
            </tr>
            {/* Column label row */}
            <tr className="bg-blue-900 text-white">
              <th className="px-3 py-1.5 text-left text-[11px] font-bold uppercase tracking-widest">
                Equipo
              </th>
              <th className="px-2 py-1.5 text-right text-[11px] font-bold">PART</th>
              <th className="px-2 py-1.5 text-right text-[11px] font-bold">MIN</th>
              {COLS.map((col, i) => (
                <th
                  key={col.header}
                  className={`px-2 py-1.5 text-right text-[11px] font-bold ${
                    groupSet.has(i) ? "border-l border-blue-800" : ""
                  }`}
                >
                  {col.header}
                </th>
              ))}
            </tr>
          </thead>

          {/* Data rows */}
          <tbody>
            {rows.map(({ team, own, opp, minutes }, rowIdx) => (
              <tr
                key={team.id}
                className={`border-t border-zinc-200 dark:border-zinc-700 ${
                  rowIdx % 2 === 0
                    ? "bg-white dark:bg-zinc-900"
                    : "bg-zinc-50 dark:bg-zinc-800/50"
                }`}
              >
                <td className="px-3 py-2 font-semibold uppercase tracking-wide">
                  {team.shortName || team.name}
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{GAMES}</td>
                <td className="px-2 py-2 text-right tabular-nums">
                  {medias ? (minutes / GAMES).toFixed(1) : minutes}
                </td>
                {COLS.map((col, i) => (
                  <td
                    key={col.header}
                    className={`px-2 py-2 text-right tabular-nums ${
                      groupSet.has(i)
                        ? "border-l border-zinc-200 dark:border-zinc-700"
                        : ""
                    } ${col.header === "PT" || col.header === "VA" ? "font-semibold" : ""}`}
                  >
                    {fmtCell(col, col.get(own, opp), medias, GAMES)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
