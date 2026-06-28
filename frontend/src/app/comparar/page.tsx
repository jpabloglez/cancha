"use client";

// Player comparator (spec §6.1): pick several players and compare their latest
// season side by side with grouped bars and an advanced-metrics radar. Fully
// client-side since selection is interactive.

import { useEffect, useState } from "react";

import { AdvancedRadar } from "@/components/AdvancedRadar";
import { MediaImage } from "@/components/MediaImage";
import { StatBarComparison } from "@/components/StatBarComparison";
import { getPlayers, getPlayerStats } from "@/lib/api";
import type { Person, PlayerSeasonStats } from "@/types/api";

/** Two-letter initials for a player's photo fallback. */
function initialsOf(person: Person): string {
  return `${person.firstName[0] ?? ""}${person.lastName[0] ?? ""}`;
}

interface Selected {
  person: Person;
  stats: PlayerSeasonStats;
}

const MAX_PLAYERS = 4;

export default function ComparePage() {
  const [players, setPlayers] = useState<Person[]>([]);
  const [selected, setSelected] = useState<Selected[]>([]);
  const [loadError, setLoadError] = useState(false);

  useEffect(() => {
    getPlayers(100)
      .then((page) => setPlayers(page.results))
      .catch(() => setLoadError(true));
  }, []);

  async function addPlayer(slug: string) {
    if (!slug || selected.length >= MAX_PLAYERS) return;
    if (selected.some((s) => s.person.slug === slug)) return;
    const person = players.find((p) => p.slug === slug);
    if (!person) return;
    const stats = await getPlayerStats(slug);
    const latest = stats[stats.length - 1];
    if (latest) {
      setSelected((prev) => [...prev, { person, stats: latest }]);
    }
  }

  function removePlayer(slug: string) {
    setSelected((prev) => prev.filter((s) => s.person.slug !== slug));
  }

  const barSeries = selected.map((s) => ({
    name: `${s.person.firstName} ${s.person.lastName}`,
    stats: s.stats,
  }));
  const radarSeries = selected.map((s) => ({
    name: `${s.person.firstName} ${s.person.lastName}`,
    stats: s.stats.advanced,
  }));

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Comparar jugadores</h1>

      {loadError ? (
        <p className="text-sm text-zinc-500">
          La API no está disponible. Arranca el backend y carga datos.
        </p>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <select
              className="rounded border border-zinc-300 bg-transparent px-3 py-2 text-sm dark:border-zinc-700"
              defaultValue=""
              onChange={(e) => {
                void addPlayer(e.target.value);
                e.target.value = "";
              }}
              disabled={selected.length >= MAX_PLAYERS}
            >
              <option value="" disabled>
                Añadir jugador…
              </option>
              {players.map((p) => (
                <option key={p.slug} value={p.slug}>
                  {p.firstName} {p.lastName}
                </option>
              ))}
            </select>
            <div className="flex flex-wrap gap-2">
              {selected.map((s) => (
                <button
                  key={s.person.slug}
                  onClick={() => removePlayer(s.person.slug)}
                  className="flex items-center gap-2 rounded-full bg-court py-1 pl-1 pr-3 text-sm text-white"
                >
                  <MediaImage
                    asset={s.person.photo}
                    alt={`${s.person.firstName} ${s.person.lastName}`}
                    initials={initialsOf(s.person)}
                    size={28}
                  />
                  <span>
                    {s.person.displayName ||
                      `${s.person.firstName} ${s.person.lastName}`}{" "}
                    ✕
                  </span>
                </button>
              ))}
            </div>
          </div>

          {selected.length === 0 ? (
            <p className="text-sm text-zinc-500">
              Añade al menos dos jugadores para comparar.
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
