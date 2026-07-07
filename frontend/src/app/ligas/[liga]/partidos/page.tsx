import Link from "next/link";
import { notFound } from "next/navigation";

import { MediaImage } from "@/components/MediaImage";
import { SeasonSelector } from "@/components/SeasonSelector";
import { getGames, getLeague, getSeasons } from "@/lib/api";
import type { Game, Season } from "@/types/api";

const PAGE_SIZE = 30;

export default async function LeagueGamesPage({
  params,
  searchParams,
}: {
  params: Promise<{ liga: string }>;
  searchParams: Promise<{ season?: string; page?: string }>;
}) {
  const { liga } = await params;
  const { season: seasonParam, page: pageParam } = await searchParams;

  const page = Math.max(1, Number(pageParam ?? "1") || 1);
  const offset = (page - 1) * PAGE_SIZE;

  let leagueName: string;
  let seasons: Season[] = [];
  let selected!: Season;
  let games: Game[] = [];
  let totalCount = 0;

  try {
    const league = await getLeague(liga);
    leagueName = league.name;
    seasons = (await getSeasons(league.id)).results;
    if (seasons.length === 0) notFound();

    selected = seasons.find((s) => String(s.id) === seasonParam) ?? seasons[0];
    const result = await getGames(selected.id, { limit: PAGE_SIZE, offset });
    games = result.results;
    totalCount = result.count;
  } catch {
    notFound();
  }

  const totalPages = Math.ceil(totalCount / PAGE_SIZE);

  function hrefPage(p: number) {
    const params = new URLSearchParams({ season: String(selected.id), page: String(p) });
    return `/ligas/${liga}/partidos?${params.toString()}`;
  }

  // Group by round label if available, otherwise by month.
  const groupKey = (g: Game) => {
    if (g.round) return g.round;
    const d = new Date(g.date);
    return d.toLocaleDateString("es-ES", { month: "long", year: "numeric" });
  };
  const byGroup = games.reduce<Record<string, Game[]>>((acc, g) => {
    const key = groupKey(g);
    (acc[key] ??= []).push(g);
    return acc;
  }, {});

  return (
    <div className="space-y-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="text-sm text-zinc-500">
            <Link href={`/ligas/${liga}`} className="hover:underline">
              {leagueName}
            </Link>
            {" / "}Partidos
          </div>
          <h1 className="text-2xl font-bold">Temporada {selected.name}</h1>
          <p className="text-sm text-zinc-500">{totalCount} partidos</p>
        </div>
        <SeasonSelector seasons={seasons} selectedId={selected.id} />
      </header>

      {Object.entries(byGroup).map(([group, groupGames]) => (
        <section key={group} className="space-y-1">
          <h2 className="text-xs font-semibold uppercase tracking-wide text-zinc-400">
            {group}
          </h2>
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {groupGames.map((game) => (
              <li key={game.id}>
                <Link
                  href={`/partidos/${game.id}`}
                  className="flex items-center gap-2 py-2 text-sm hover:bg-zinc-50 dark:hover:bg-zinc-900"
                >
                  <span className="w-24 shrink-0 text-xs text-zinc-400">
                    {new Date(game.date).toLocaleDateString("es-ES", {
                      day: "numeric",
                      month: "short",
                    })}
                  </span>
                  <span className="flex flex-1 items-center justify-end gap-2 text-right">
                    {game.homeTeam.name}
                    <MediaImage
                      asset={game.homeTeam.logo}
                      alt={game.homeTeam.name}
                      initials={game.homeTeam.name.slice(0, 2).toUpperCase()}
                      color={game.homeTeam.primaryColor || undefined}
                      rounded="lg"
                      size={20}
                    />
                  </span>
                  <span className="w-20 shrink-0 text-center font-semibold tabular-nums">
                    {game.finalScoreHome} – {game.finalScoreAway}
                  </span>
                  <span className="flex flex-1 items-center gap-2">
                    <MediaImage
                      asset={game.awayTeam.logo}
                      alt={game.awayTeam.name}
                      initials={game.awayTeam.name.slice(0, 2).toUpperCase()}
                      color={game.awayTeam.primaryColor || undefined}
                      rounded="lg"
                      size={20}
                    />
                    {game.awayTeam.name}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        </section>
      ))}

      {/* Pagination */}
      {totalPages > 1 && (
        <nav className="flex items-center justify-center gap-2 text-sm">
          {page > 1 && (
            <Link
              href={hrefPage(page - 1)}
              className="rounded-lg border border-zinc-300 px-3 py-1.5 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              ← Anterior
            </Link>
          )}
          <span className="text-zinc-500">
            Página {page} de {totalPages}
          </span>
          {page < totalPages && (
            <Link
              href={hrefPage(page + 1)}
              className="rounded-lg border border-zinc-300 px-3 py-1.5 hover:bg-zinc-50 dark:border-zinc-700 dark:hover:bg-zinc-800"
            >
              Siguiente →
            </Link>
          )}
        </nav>
      )}
    </div>
  );
}
