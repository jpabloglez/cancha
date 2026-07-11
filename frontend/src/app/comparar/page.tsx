"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { AdvancedRadar } from "@/components/AdvancedRadar";
import type { AdvancedRadarSeries } from "@/components/AdvancedRadar";
import { MediaImage } from "@/components/MediaImage";
import { StatBarComparison } from "@/components/StatBarComparison";
import { getPlayer, getPlayerStats, getPlayers } from "@/lib/api";
import type { Person, PersonDetail, PlayerSeasonStats } from "@/types/api";

function initialsOf(person: Person): string {
  return `${person.firstName[0] ?? ""}${person.lastName[0] ?? ""}`;
}

function fullName(person: Person): string {
  return person.displayName || `${person.firstName} ${person.lastName}`;
}

interface Selected {
  person: PersonDetail;
  allStats: PlayerSeasonStats[];
  activeSeason: string;   // season id or "latest"
}

const MAX_PLAYERS = 4;
const SEARCH_LIMIT = 12;
const DEBOUNCE_MS = 280;

const PLAYER_COLORS = ["#c0612b", "#3b82f6", "#16a34a", "#a855f7"];

export default function ComparePage() {
  const [query, setQuery] = useState("");
  const [searchResults, setSearchResults] = useState<Person[]>([]);
  const [searching, setSearching] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selected, setSelected] = useState<Selected[]>([]);
  const [apiError, setApiError] = useState(false);
  const [bootstrapping, setBootstrapping] = useState(true);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // On mount: read ?ids= from URL and pre-load those players.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const idsParam = params.get("ids");
    if (!idsParam) { setBootstrapping(false); return; }
    const slugs = idsParam.split(",").filter(Boolean).slice(0, MAX_PLAYERS);
    if (slugs.length === 0) { setBootstrapping(false); return; }

    Promise.all(
      slugs.map(async (slug) => {
        const [person, allStats] = await Promise.all([
          getPlayer(slug),
          getPlayerStats(slug),
        ]);
        return { person, allStats, activeSeason: "latest" } satisfies Selected;
      })
    )
      .then((items) => setSelected(items.filter((s) => s.allStats.length > 0)))
      .catch(() => setApiError(true))
      .finally(() => setBootstrapping(false));
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // Keep URL in sync with selected players (slugs only, for sharing).
  useEffect(() => {
    if (bootstrapping) return;
    const slugs = selected.map((s) => s.person.slug).join(",");
    const url = slugs ? `?ids=${slugs}` : window.location.pathname;
    window.history.replaceState(null, "", url);
  }, [selected, bootstrapping]);

  const search = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) { setSearchResults([]); setDropdownOpen(false); return; }
    debounceRef.current = setTimeout(() => {
      setSearching(true);
      getPlayers(SEARCH_LIMIT, q.trim())
        .then((page) => {
          setSearchResults(page.results);
          setDropdownOpen(page.results.length > 0);
        })
        .catch(() => setApiError(true))
        .finally(() => setSearching(false));
    }, DEBOUNCE_MS);
  }, []);

  useEffect(() => { search(query); }, [query, search]);

  async function addPlayer(person: Person) {
    if (selected.length >= MAX_PLAYERS) return;
    if (selected.some((s) => s.person.slug === person.slug)) return;
    setDropdownOpen(false);
    setQuery("");
    try {
      const [detail, allStats] = await Promise.all([
        getPlayer(person.slug),
        getPlayerStats(person.slug),
      ]);
      if (allStats.length > 0) {
        setSelected((prev) => [...prev, { person: detail, allStats, activeSeason: "latest" }]);
      }
    } catch { /* silently skip */ }
  }

  function removePlayer(slug: string) {
    setSelected((prev) => prev.filter((s) => s.person.slug !== slug));
  }

  function setActiveSeason(slug: string, seasonId: string) {
    setSelected((prev) =>
      prev.map((s) => s.person.slug === slug ? { ...s, activeSeason: seasonId } : s)
    );
  }

  function resolveStats(sel: Selected): PlayerSeasonStats | null {
    if (sel.allStats.length === 0) return null;
    if (sel.activeSeason === "latest") return sel.allStats[sel.allStats.length - 1];
    return sel.allStats.find((s) => s.seasonId === sel.activeSeason) ?? sel.allStats[sel.allStats.length - 1];
  }

  const radarSeries: AdvancedRadarSeries[] = selected
    .flatMap((s, i) => {
      const stats = resolveStats(s);
      if (!stats) return [];
      return [{ name: fullName(s.person), stats: stats.advanced, color: PLAYER_COLORS[i] }];
    });

  const barSeries = selected
    .map((s) => {
      const stats = resolveStats(s);
      if (!stats) return null;
      return { name: fullName(s.person), stats };
    })
    .filter((x): x is { name: string; stats: PlayerSeasonStats } => x !== null);

  if (apiError) {
    return (
      <div className="space-y-4">
        <h1 className="text-2xl font-bold">Comparar jugadores</h1>
        <p className="text-sm text-zinc-500">La API no está disponible. Arranca el backend y carga datos.</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Comparar jugadores</h1>

      {/* ── Search bar ─────────────────────────────────────────── */}
      <div className="space-y-3">
        <div className="relative max-w-sm">
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onFocus={() => searchResults.length > 0 && setDropdownOpen(true)}
            onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
            placeholder={selected.length >= MAX_PLAYERS ? "Máximo 4 jugadores" : "Añadir jugador…"}
            disabled={selected.length >= MAX_PLAYERS || bootstrapping}
            className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm placeholder-zinc-400 focus:border-court focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
          />
          {searching && (
            <span className="absolute right-3 top-2.5 text-xs text-zinc-400">…</span>
          )}

          {dropdownOpen && (
            <ul className="absolute z-20 mt-1 w-full rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
              {searchResults.map((p) => {
                const alreadyAdded = selected.some((s) => s.person.slug === p.slug);
                return (
                  <li key={p.slug}>
                    <button
                      onMouseDown={() => addPlayer(p)}
                      disabled={alreadyAdded}
                      className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800"
                    >
                      <MediaImage asset={p.photo} alt={fullName(p)} initials={initialsOf(p)} size={28} />
                      <span>{fullName(p)}</span>
                      {alreadyAdded && <span className="ml-auto text-xs text-zinc-400">Añadido</span>}
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* Selected player chips */}
        {selected.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {selected.map((s, i) => (
              <button
                key={s.person.slug}
                onClick={() => removePlayer(s.person.slug)}
                style={{ backgroundColor: PLAYER_COLORS[i] }}
                className="flex items-center gap-2 rounded-full py-1 pl-1 pr-3 text-sm text-white hover:opacity-90"
                title="Eliminar"
              >
                <MediaImage asset={s.person.photo} alt={fullName(s.person)} initials={initialsOf(s.person)} size={26} />
                <span>{fullName(s.person)} ✕</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {bootstrapping && (
        <p className="text-sm text-zinc-400">Cargando jugadores…</p>
      )}

      {!bootstrapping && selected.length === 0 && (
        <p className="text-sm text-zinc-500">
          Busca y añade al menos dos jugadores para comparar. Puedes compartir el enlace con los jugadores seleccionados.
        </p>
      )}

      {/* ── Per-player season pickers ──────────────────────────── */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-6">
          {selected.map((s, i) => (
            <div key={s.person.slug} className="flex items-center gap-2 text-sm">
              <span
                className="inline-block h-3 w-3 rounded-full"
                style={{ backgroundColor: PLAYER_COLORS[i] }}
              />
              <span className="font-medium text-zinc-700 dark:text-zinc-300">
                {fullName(s.person)}:
              </span>
              <select
                value={s.activeSeason}
                onChange={(e) => setActiveSeason(s.person.slug, e.target.value)}
                className="rounded border border-zinc-300 bg-white px-2 py-0.5 text-xs text-zinc-800 dark:border-zinc-600 dark:bg-zinc-900 dark:text-zinc-200"
              >
                <option value="latest">Última temp.</option>
                {s.allStats.map((st) => (
                  <option key={st.seasonId} value={st.seasonId}>{st.seasonName}</option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {/* ── Charts ─────────────────────────────────────────────── */}
      {barSeries.length >= 1 && (
        <div className="grid gap-8 md:grid-cols-2">
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Promedios básicos</h2>
            <StatBarComparison series={barSeries} />
          </section>
          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Perfil avanzado</h2>
            <AdvancedRadar series={radarSeries} />
          </section>
        </div>
      )}

      {/* ── Stats table ────────────────────────────────────────── */}
      {selected.length >= 1 && (
        <section className="space-y-2 overflow-x-auto">
          <h2 className="text-lg font-semibold">Estadísticas</h2>
          <table className="w-full text-sm">
            <thead className="text-left text-xs text-zinc-500">
              <tr>
                <th className="py-2 pr-4">Estadística</th>
                {selected.map((s, i) => (
                  <th
                    key={s.person.slug}
                    className="px-3 py-2 text-right font-semibold"
                    style={{ color: PLAYER_COLORS[i] }}
                  >
                    {fullName(s.person)}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
              {(
                [
                  { label: "Temporada", fn: (_: PlayerSeasonStats) => _.seasonName, format: (v: string | number) => String(v) },
                  { label: "Partidos (PJ)", fn: (s: PlayerSeasonStats) => s.gamesPlayed, format: (v: string | number) => String(v) },
                  { label: "MIN/PJ", fn: (s: PlayerSeasonStats) => s.minutesPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "PTS/PJ", fn: (s: PlayerSeasonStats) => s.pointsPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "REB/PJ", fn: (s: PlayerSeasonStats) => s.reboundsPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "ASI/PJ", fn: (s: PlayerSeasonStats) => s.assistsPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "ROB/PJ", fn: (s: PlayerSeasonStats) => s.stealsPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "TAP/PJ", fn: (s: PlayerSeasonStats) => s.blocksPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "PÉR/PJ", fn: (s: PlayerSeasonStats) => s.turnoversPerGame, format: (v: string | number) => Number(v).toFixed(1) },
                  { label: "T2%", fn: (s: PlayerSeasonStats) => s.twoPercent, format: (v: string | number) => (Number(v) * 100).toFixed(1) + "%" },
                  { label: "T3%", fn: (s: PlayerSeasonStats) => s.threePercent, format: (v: string | number) => (Number(v) * 100).toFixed(1) + "%" },
                  { label: "TL%", fn: (s: PlayerSeasonStats) => s.ftPercent, format: (v: string | number) => (Number(v) * 100).toFixed(1) + "%" },
                  { label: "TS%", fn: (s: PlayerSeasonStats) => s.advanced.trueShootingPercent, format: (v: string | number) => (Number(v) * 100).toFixed(1) + "%" },
                  { label: "eFG%", fn: (s: PlayerSeasonStats) => s.advanced.effectiveFieldGoalPercent, format: (v: string | number) => (Number(v) * 100).toFixed(1) + "%" },
                  { label: "USO%", fn: (s: PlayerSeasonStats) => s.advanced.usageRate, format: (v: string | number) => (Number(v) * 100).toFixed(1) + "%" },
                  { label: "PER", fn: (s: PlayerSeasonStats) => s.advanced.playerEfficiencyRating, format: (v: string | number) => Number(v).toFixed(1) },
                ] as { label: string; fn: (s: PlayerSeasonStats) => string | number; format: (v: string | number) => string }[]
              ).map(({ label, fn, format }) => (
                <tr key={label} className="hover:bg-zinc-50 dark:hover:bg-zinc-800/30">
                  <td className="py-2 pr-4 text-xs font-medium text-zinc-500">{label}</td>
                  {selected.map((s) => {
                    const stats = resolveStats(s);
                    const val = stats ? fn(stats) : null;
                    return (
                      <td key={s.person.slug} className="px-3 py-2 text-right tabular-nums font-medium">
                        {val != null ? format(val) : "—"}
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      )}
    </div>
  );
}
