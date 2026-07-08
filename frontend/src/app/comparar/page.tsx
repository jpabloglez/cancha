"use client";

// Player comparator (spec §6.1): pick up to 4 players via a debounced search
// input and compare their latest season side by side with grouped bars and an
// advanced-metrics radar. Fully client-side since selection is interactive.

import { useCallback, useEffect, useRef, useState } from "react";

import { AdvancedRadar } from "@/components/AdvancedRadar";
import { MediaImage } from "@/components/MediaImage";
import { StatBarComparison } from "@/components/StatBarComparison";
import { getPlayers, getPlayerStats } from "@/lib/api";
import type { Person, PlayerSeasonStats } from "@/types/api";

function initialsOf(person: Person): string {
  return `${person.firstName[0] ?? ""}${person.lastName[0] ?? ""}`;
}

interface Selected {
  person: Person;
  stats: PlayerSeasonStats;
}

const MAX_PLAYERS = 4;
const SEARCH_LIMIT = 12;
const DEBOUNCE_MS = 280;

export default function ComparePage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<Person[]>([]);
  const [searching, setSearching] = useState(false);
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const [selected, setSelected] = useState<Selected[]>([]);
  const [apiError, setApiError] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Debounced search: fires 280 ms after the user stops typing.
  const search = useCallback((q: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!q.trim()) {
      setResults([]);
      setDropdownOpen(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      setSearching(true);
      getPlayers(SEARCH_LIMIT, q.trim())
        .then((page) => {
          setResults(page.results);
          setDropdownOpen(page.results.length > 0);
        })
        .catch(() => setApiError(true))
        .finally(() => setSearching(false));
    }, DEBOUNCE_MS);
  }, []);

  useEffect(() => {
    search(query);
  }, [query, search]);

  async function addPlayer(person: Person) {
    if (selected.length >= MAX_PLAYERS) return;
    if (selected.some((s) => s.person.slug === person.slug)) return;
    setDropdownOpen(false);
    setQuery("");
    try {
      const allStats = await getPlayerStats(person.slug);
      const latest = allStats[allStats.length - 1];
      if (latest) setSelected((prev) => [...prev, { person, stats: latest }]);
    } catch {
      /* silently skip if stats unavailable */
    }
  }

  function removePlayer(slug: string) {
    setSelected((prev) => prev.filter((s) => s.person.slug !== slug));
  }

  const barSeries = selected.map((s) => ({
    name: s.person.displayName || `${s.person.firstName} ${s.person.lastName}`,
    stats: s.stats,
  }));
  const radarSeries = selected.map((s) => ({
    name: s.person.displayName || `${s.person.firstName} ${s.person.lastName}`,
    stats: s.stats.advanced,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Comparar jugadores</h1>

      {apiError ? (
        <p className="text-sm text-zinc-500">
          La API no está disponible. Arranca el backend y carga datos.
        </p>
      ) : (
        <>
          {/* ── Search bar + selected chips ──────────────────────────── */}
          <div className="space-y-3">
            <div className="relative max-w-sm">
              <input
                ref={inputRef}
                type="search"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                onFocus={() => results.length > 0 && setDropdownOpen(true)}
                onBlur={() => setTimeout(() => setDropdownOpen(false), 150)}
                placeholder={
                  selected.length >= MAX_PLAYERS
                    ? "Máximo 4 jugadores"
                    : "Buscar jugador…"
                }
                disabled={selected.length >= MAX_PLAYERS}
                className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm placeholder-zinc-400 focus:border-court focus:outline-none disabled:cursor-not-allowed disabled:opacity-50 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100"
              />
              {searching && (
                <span className="absolute right-3 top-2.5 text-xs text-zinc-400">
                  …
                </span>
              )}

              {/* Dropdown */}
              {dropdownOpen && (
                <ul className="absolute z-20 mt-1 w-full rounded-lg border border-zinc-200 bg-white shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
                  {results.map((p) => {
                    const alreadyAdded = selected.some(
                      (s) => s.person.slug === p.slug,
                    );
                    return (
                      <li key={p.slug}>
                        <button
                          onMouseDown={() => addPlayer(p)}
                          disabled={alreadyAdded}
                          className="flex w-full items-center gap-3 px-3 py-2 text-left text-sm hover:bg-zinc-50 disabled:opacity-40 dark:hover:bg-zinc-800"
                        >
                          <MediaImage
                            asset={p.photo}
                            alt={`${p.firstName} ${p.lastName}`}
                            initials={initialsOf(p)}
                            size={28}
                          />
                          <span>
                            {p.displayName ||
                              `${p.firstName} ${p.lastName}`}
                          </span>
                          {alreadyAdded && (
                            <span className="ml-auto text-xs text-zinc-400">
                              Añadido
                            </span>
                          )}
                        </button>
                      </li>
                    );
                  })}
                </ul>
              )}
            </div>

            {/* Selected chips */}
            {selected.length > 0 && (
              <div className="flex flex-wrap gap-2">
                {selected.map((s) => (
                  <button
                    key={s.person.slug}
                    onClick={() => removePlayer(s.person.slug)}
                    className="flex items-center gap-2 rounded-full bg-court py-1 pl-1 pr-3 text-sm text-white hover:opacity-90"
                    title="Eliminar"
                  >
                    <MediaImage
                      asset={s.person.photo}
                      alt={`${s.person.firstName} ${s.person.lastName}`}
                      initials={initialsOf(s.person)}
                      size={26}
                    />
                    <span>
                      {s.person.displayName ||
                        `${s.person.firstName} ${s.person.lastName}`}{" "}
                      ✕
                    </span>
                  </button>
                ))}
              </div>
            )}
          </div>

          {/* ── Comparison panels ─────────────────────────────────────── */}
          {selected.length === 0 ? (
            <p className="text-sm text-zinc-500">
              Busca y añade al menos dos jugadores para comparar.
            </p>
          ) : (
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
        </>
      )}
    </div>
  );
}
