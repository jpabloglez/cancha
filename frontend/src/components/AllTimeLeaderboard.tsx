"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

import { MediaImage } from "@/components/MediaImage";
import { PositionBadge } from "@/components/PositionBadge";
import { getAllTimeLeaders } from "@/lib/api";
import type { AllTimeLeader } from "@/types/api";

// ---------------------------------------------------------------------------
// Stat definitions
// ---------------------------------------------------------------------------

interface StatDef {
  key: string;
  label: string;
  col: keyof AllTimeLeader;
  decimals: number;
}

const STATS: StatDef[] = [
  { key: "ppg",          label: "PPG",            col: "ppg",          decimals: 1 },
  { key: "rpg",          label: "RPG",            col: "rpg",          decimals: 1 },
  { key: "apg",          label: "APG",            col: "apg",          decimals: 1 },
  { key: "spg",          label: "Robos/PJ",       col: "spg",          decimals: 1 },
  { key: "bpg",          label: "Tapones/PJ",     col: "bpg",          decimals: 1 },
  { key: "topg",         label: "Pérdidas/PJ",    col: "topg",         decimals: 1 },
  { key: "two_pct",      label: "T2%",            col: "twoPercent",   decimals: 1 },
  { key: "three_pct",    label: "T3%",            col: "threePercent", decimals: 1 },
  { key: "ft_pct",       label: "TL%",            col: "ftPercent",    decimals: 1 },
  { key: "total_points", label: "Pts. totales",   col: "totalPoints",  decimals: 0 },
  { key: "total_rebounds",label:"Reb. totales",   col: "totalRebounds",decimals: 0 },
  { key: "total_assists",label: "Asis. totales",  col: "totalAssists", decimals: 0 },
  { key: "per",          label: "PER",            col: "per",          decimals: 1 },
  { key: "ts",           label: "TS%",            col: "tsPercent",    decimals: 1 },
  { key: "games",        label: "Partidos",       col: "totalGames",   decimals: 0 },
];

const POSITIONS = ["PG", "SG", "SF", "PF", "C"];
const ROWS_OPTIONS = [10, 25, 50];
const LEAGUE_OPTIONS = [
  { value: "",              label: "Todas las ligas" },
  { value: "acb",           label: "Liga ACB" },
  { value: "primera-feb",   label: "Primera FEB" },
  { value: "segunda-feb",   label: "Segunda FEB" },
];

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface Filters {
  stat: string;
  league: string;
  seasonFrom: string;
  seasonTo: string;
  position: string;
  minGames: number;
  limit: number;
}

function defaultFilters(): Filters {
  return { stat: "ppg", league: "", seasonFrom: "", seasonTo: "", position: "", minGames: 20, limit: 10 };
}

// ---------------------------------------------------------------------------
// Export helper
// ---------------------------------------------------------------------------

function exportCsv(rows: AllTimeLeader[], stat: string) {
  const headers = [
    "#", "Jugador", "Posición", "Nac.", "Partidos", "Temp.", "Ligas",
    "PPG", "RPG", "APG", "ROB/PJ", "TAP/PJ", "PÉR/PJ",
    "T2%", "T3%", "TL%", "PER", "TS%",
    "Pts tot.", "Reb. tot.", "Asis. tot.",
  ];
  const pct = (v: number) => (v * 100).toFixed(1) + "%";
  const lines = rows.map((r, i) =>
    [
      i + 1,
      r.playerName,
      r.primaryPosition ?? "",
      r.nationality ?? "",
      r.totalGames,
      r.seasonsCount,
      r.leagues.join("|"),
      r.ppg.toFixed(1),
      r.rpg.toFixed(1),
      r.apg.toFixed(1),
      r.spg.toFixed(1),
      r.bpg.toFixed(1),
      r.topg.toFixed(1),
      pct(r.twoPercent),
      pct(r.threePercent),
      pct(r.ftPercent),
      r.per != null ? r.per.toFixed(1) : "",
      pct(r.tsPercent),
      r.totalPoints.toFixed(0),
      r.totalRebounds.toFixed(0),
      r.totalAssists.toFixed(0),
    ].join(",")
  );
  const csv = [headers.join(","), ...lines].join("\n");
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `historico-${stat}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

interface Props {
  initialRows?: AllTimeLeader[];
  initialCount?: number;
  seasons?: string[];
}

export function AllTimeLeaderboard({ initialRows = [], initialCount = 0, seasons = [] }: Props) {
  const [filters, setFilters] = useState<Filters>(defaultFilters());
  const [rows, setRows] = useState<AllTimeLeader[]>(initialRows);
  const [count, setCount] = useState(initialCount);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(false);
  const fetchId = useRef(0);

  const activeStat = STATS.find((s) => s.key === filters.stat) ?? STATS[0];

  const fetchData = useCallback(
    async (f: Filters, off: number) => {
      const id = ++fetchId.current;
      setLoading(true);
      try {
        const data = await getAllTimeLeaders({
          stat: f.stat,
          league: f.league || undefined,
          seasonFrom: f.seasonFrom || undefined,
          seasonTo: f.seasonTo || undefined,
          position: f.position || undefined,
          minGames: f.minGames,
          limit: f.limit,
          offset: off,
        });
        if (id === fetchId.current) {
          setRows(data.results);
          setCount(data.count);
        }
      } catch {
        if (id === fetchId.current) { setRows([]); setCount(0); }
      } finally {
        if (id === fetchId.current) setLoading(false);
      }
    },
    []
  );

  // Re-fetch whenever filters or offset change (skip on first render if initial data provided).
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current && initialRows.length > 0) {
      isFirstRender.current = false;
      return;
    }
    isFirstRender.current = false;
    fetchData(filters, offset);
  }, [filters, offset, fetchData]); // eslint-disable-line react-hooks/exhaustive-deps

  const setFilter = <K extends keyof Filters>(key: K, val: Filters[K]) => {
    setFilters((prev) => ({ ...prev, [key]: val }));
    setOffset(0);
  };

  const totalPages = Math.ceil(count / filters.limit);
  const currentPage = Math.floor(offset / filters.limit) + 1;

  return (
    <div className="space-y-4">
      {/* ── Stat tabs ─────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1">
        {STATS.map((s) => (
          <button
            key={s.key}
            onClick={() => setFilter("stat", s.key)}
            className={`rounded-full px-3 py-1 text-sm font-medium transition-colors ${
              filters.stat === s.key
                ? "bg-orange-600 text-white"
                : "bg-zinc-100 text-zinc-700 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-300 dark:hover:bg-zinc-700"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {/* ── Filters row ───────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-3 text-sm">
        {/* League */}
        <select
          value={filters.league}
          onChange={(e) => setFilter("league", e.target.value)}
          className="rounded border border-zinc-300 bg-white px-2 py-1 text-zinc-800 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
        >
          {LEAGUE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>{o.label}</option>
          ))}
        </select>

        {/* Position */}
        <select
          value={filters.position}
          onChange={(e) => setFilter("position", e.target.value)}
          className="rounded border border-zinc-300 bg-white px-2 py-1 text-zinc-800 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
        >
          <option value="">Todas posiciones</option>
          {POSITIONS.map((p) => (
            <option key={p} value={p}>{p}</option>
          ))}
        </select>

        {/* Season range */}
        {seasons.length > 0 && (
          <>
            <select
              value={filters.seasonFrom}
              onChange={(e) => setFilter("seasonFrom", e.target.value)}
              className="rounded border border-zinc-300 bg-white px-2 py-1 text-zinc-800 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
            >
              <option value="">Desde...</option>
              {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
            <select
              value={filters.seasonTo}
              onChange={(e) => setFilter("seasonTo", e.target.value)}
              className="rounded border border-zinc-300 bg-white px-2 py-1 text-zinc-800 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
            >
              <option value="">Hasta...</option>
              {seasons.map((s) => <option key={s} value={s}>{s}</option>)}
            </select>
          </>
        )}

        {/* Min games */}
        <label className="flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
          Mín. partidos:
          <input
            type="number"
            min={0}
            max={500}
            value={filters.minGames}
            onChange={(e) => setFilter("minGames", Math.max(0, Number(e.target.value)))}
            className="w-16 rounded border border-zinc-300 bg-white px-2 py-1 text-zinc-800 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
          />
        </label>

        {/* Rows per page */}
        <div className="ml-auto flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
          Filas:
          {ROWS_OPTIONS.map((n) => (
            <button
              key={n}
              onClick={() => setFilter("limit", n)}
              className={`rounded px-2 py-0.5 text-xs ${
                filters.limit === n
                  ? "bg-zinc-800 text-white dark:bg-zinc-200 dark:text-zinc-900"
                  : "bg-zinc-100 text-zinc-600 hover:bg-zinc-200 dark:bg-zinc-800 dark:text-zinc-400"
              }`}
            >
              {n}
            </button>
          ))}
        </div>

        {/* Export */}
        <button
          onClick={() => exportCsv(rows, filters.stat)}
          disabled={rows.length === 0}
          className="flex items-center gap-1 rounded border border-zinc-300 px-3 py-1 text-xs text-zinc-600 hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-600 dark:text-zinc-400 dark:hover:bg-zinc-800"
        >
          ↓ CSV
        </button>
      </div>

      {/* ── Table ─────────────────────────────────────────────────── */}
      <div className={`overflow-x-auto rounded-xl border border-zinc-200 dark:border-zinc-700 transition-opacity ${loading ? "opacity-50" : ""}`}>
        <table className="w-full text-sm">
          <thead className="border-b border-zinc-200 bg-zinc-50 text-left text-xs font-semibold uppercase tracking-wider text-zinc-500 dark:border-zinc-700 dark:bg-zinc-800/60 dark:text-zinc-400">
            <tr>
              <th className="px-3 py-2 text-right">#</th>
              <th className="px-3 py-2">Jugador</th>
              <th className="px-3 py-2">Pos.</th>
              <th className="px-3 py-2 text-right text-orange-600">{activeStat.label}</th>
              <th className="px-3 py-2 text-right">PJ</th>
              <th className="px-3 py-2 text-right">Temp.</th>
              <th className="px-3 py-2 text-right">PPG</th>
              <th className="px-3 py-2 text-right">RPG</th>
              <th className="px-3 py-2 text-right">APG</th>
              <th className="px-3 py-2 text-right" title="Robos por partido">ROB</th>
              <th className="px-3 py-2 text-right" title="Tapones por partido">TAP</th>
              <th className="px-3 py-2 text-right" title="Pérdidas por partido">PÉR</th>
              <th className="px-3 py-2 text-right" title="Porcentaje de tiro de 2">T2%</th>
              <th className="px-3 py-2 text-right" title="Porcentaje de tiro de 3">T3%</th>
              <th className="px-3 py-2 text-right" title="Porcentaje de tiro libre">TL%</th>
              <th className="px-3 py-2 text-right" title="Player Efficiency Rating">PER</th>
              <th className="px-3 py-2 text-right" title="True Shooting %">TS%</th>
              <th className="px-3 py-2 text-right">Ligas</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {rows.length === 0 && !loading && (
              <tr>
                <td colSpan={18} className="px-4 py-8 text-center text-zinc-400">
                  Sin resultados para los filtros seleccionados.
                </td>
              </tr>
            )}
            {rows.map((r, i) => {
              const val = r[activeStat.col as keyof AllTimeLeader] as number | null;
              const isPct = ["twoPercent", "threePercent", "ftPercent", "tsPercent"].includes(activeStat.col as string);
              const displayVal = val != null
                ? isPct ? (val * 100).toFixed(activeStat.decimals) + "%" : val.toFixed(activeStat.decimals)
                : "—";
              const num = (v: number, d = 1) => v.toFixed(d);
              const pct = (v: number) => (v * 100).toFixed(1) + "%";
              return (
                <tr key={r.playerId} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/40">
                  <td className="px-3 py-2 text-right text-xs text-zinc-400">{offset + i + 1}</td>
                  <td className="px-3 py-2">
                    <Link href={`/jugadores/${r.playerSlug}`} className="flex min-w-[140px] items-center gap-2 hover:underline">
                      <MediaImage asset={r.photo} alt={r.playerName} initials={r.playerName.slice(0, 2)} size={28} />
                      <span className="font-medium text-zinc-900 dark:text-zinc-100">{r.playerName}</span>
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    <PositionBadge position={r.primaryPosition} short />
                  </td>
                  <td className="px-3 py-2 text-right font-mono font-semibold text-orange-600">{displayVal}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-600 dark:text-zinc-400">{r.totalGames}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-zinc-600 dark:text-zinc-400">{r.seasonsCount}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.ppg)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.rpg)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.apg)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.spg)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.bpg)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{num(r.topg)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct(r.twoPercent)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct(r.threePercent)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct(r.ftPercent)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.per != null ? num(r.per) : "—"}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{pct(r.tsPercent)}</td>
                  <td className="px-3 py-2 text-xs text-zinc-400">{r.leagues.join(", ")}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* ── Pagination ────────────────────────────────────────────── */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm text-zinc-500">
          <span>{count} jugadores · página {currentPage}/{totalPages}</span>
          <div className="flex gap-2">
            <button
              disabled={offset === 0}
              onClick={() => setOffset(Math.max(0, offset - filters.limit))}
              className="rounded border border-zinc-300 px-3 py-1 hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-600 dark:hover:bg-zinc-800"
            >
              ← Anterior
            </button>
            <button
              disabled={offset + filters.limit >= count}
              onClick={() => setOffset(offset + filters.limit)}
              className="rounded border border-zinc-300 px-3 py-1 hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-600 dark:hover:bg-zinc-800"
            >
              Siguiente →
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
