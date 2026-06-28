import Link from "next/link";

import { MediaImage } from "@/components/MediaImage";
import { getLeaders, getLeagues, getSeasons } from "@/lib/api";
import type { Leader, League, Season } from "@/types/api";

// Statistical leaders tables by category (spec §6.1). Server-rendered; the
// active category, league and season are selected via query parameters.
const STATS: { key: string; label: string; isPercent?: boolean }[] = [
  { key: "points", label: "Puntos" },
  { key: "rebounds", label: "Rebotes" },
  { key: "assists", label: "Asistencias" },
  { key: "per", label: "PER" },
  { key: "ts", label: "TS%", isPercent: true },
  { key: "usage", label: "Uso", isPercent: true },
];

/** Initials for the photo fallback, from a display name. */
function initialsOf(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .join("");
}

/** Build a /lideres URL preserving the other selections. */
function hrefWith(
  base: { stat: string; league?: string; season?: string },
  patch: Partial<{ stat: string; league: string; season: string }>,
): string {
  const next = { ...base, ...patch };
  const params = new URLSearchParams();
  params.set("stat", next.stat);
  if (next.league) params.set("league", next.league);
  if (next.season) params.set("season", next.season);
  return `/lideres?${params.toString()}`;
}

export default async function LeadersPage({
  searchParams,
}: {
  searchParams: Promise<{ stat?: string; league?: string; season?: string }>;
}) {
  const { stat, league, season } = await searchParams;
  const active = STATS.find((s) => s.key === stat) ?? STATS[0];
  const base = { stat: active.key, league, season };

  let leagues: League[] = [];
  let seasons: Season[] = [];
  let leaders: Leader[] = [];
  let apiError = false;
  try {
    leagues = (await getLeagues()).results;
    // Seasons are league-scoped, so the season selector only appears once a
    // league is chosen (the API otherwise defaults to that league's latest).
    if (league) {
      seasons = (await getSeasons(Number(league))).results;
    }
    leaders = await getLeaders(
      active.key,
      season ? Number(season) : undefined,
      20,
      league ? Number(league) : undefined,
    );
  } catch {
    apiError = true;
  }

  const format = (value: number) =>
    active.isPercent ? `${(value * 100).toFixed(1)}%` : value.toFixed(1);

  const chip = (selected: boolean) =>
    `rounded-full border px-3 py-1 ${
      selected
        ? "border-court bg-court text-white"
        : "border-zinc-300 dark:border-zinc-700"
    }`;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Líderes estadísticos</h1>

      {/* League selector */}
      {leagues.length > 0 && (
        <nav className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-500">Liga:</span>
          <Link href={hrefWith({ stat: active.key }, {})} className={chip(!league)}>
            Todas
          </Link>
          {leagues.map((l) => (
            <Link
              key={l.id}
              href={hrefWith({ stat: active.key }, { league: String(l.id) })}
              className={chip(league === String(l.id))}
            >
              {l.name}
            </Link>
          ))}
        </nav>
      )}

      {/* Season selector (only when a league is chosen) */}
      {seasons.length > 0 && (
        <nav className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-zinc-500">Temporada:</span>
          <Link
            href={hrefWith({ ...base, season: undefined }, {})}
            className={chip(!season)}
          >
            Última
          </Link>
          {seasons.map((s) => (
            <Link
              key={s.id}
              href={hrefWith(base, { season: String(s.id) })}
              className={chip(season === String(s.id))}
            >
              {s.name}
            </Link>
          ))}
        </nav>
      )}

      {/* Stat category selector */}
      <nav className="flex flex-wrap gap-2 text-sm">
        {STATS.map((s) => (
          <Link
            key={s.key}
            href={hrefWith(base, { stat: s.key })}
            className={chip(s.key === active.key)}
          >
            {s.label}
          </Link>
        ))}
      </nav>

      {apiError ? (
        <p className="text-sm text-zinc-500">
          La API no está disponible. Arranca el backend y carga datos.
        </p>
      ) : leaders.length === 0 ? (
        <p className="text-sm text-zinc-500">No hay datos para esta selección.</p>
      ) : (
        <table className="w-full text-sm">
          <thead className="text-left text-zinc-500">
            <tr>
              <th className="w-8 py-2">#</th>
              <th>Jugador</th>
              <th className="hidden sm:table-cell">Equipo</th>
              <th className="text-right">{active.label}</th>
            </tr>
          </thead>
          <tbody>
            {leaders.map((leader, i) => (
              <tr
                key={`${leader.playerId}-${leader.seasonId}`}
                className="border-t border-zinc-200 dark:border-zinc-800"
              >
                <td className="py-2 text-zinc-500">{i + 1}</td>
                <td>
                  <Link
                    href={`/jugadores/${leader.playerSlug}`}
                    className="flex items-center gap-3 hover:underline"
                  >
                    <MediaImage
                      asset={leader.photo}
                      alt={leader.playerName}
                      initials={initialsOf(leader.playerName)}
                      size={32}
                    />
                    <span>{leader.playerName}</span>
                  </Link>
                </td>
                <td className="hidden sm:table-cell">
                  {leader.team && (
                    <Link
                      href={`/equipos/${leader.team.slug}`}
                      className="flex items-center gap-2 hover:underline"
                    >
                      <MediaImage
                        asset={leader.team.logo}
                        alt={leader.team.name}
                        initials={leader.team.name.slice(0, 2).toUpperCase()}
                        color={leader.team.primaryColor || undefined}
                        rounded="lg"
                        size={20}
                      />
                      <span className="text-zinc-600 dark:text-zinc-400">
                        {leader.team.shortName || leader.team.name}
                      </span>
                    </Link>
                  )}
                </td>
                <td className="text-right tabular-nums">{format(leader.value)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
