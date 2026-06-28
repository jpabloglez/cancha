import Link from "next/link";
import { notFound } from "next/navigation";

import { MediaImage } from "@/components/MediaImage";
import { SeasonSelector } from "@/components/SeasonSelector";
import { getGames, getLeague, getSeasons, getStandings } from "@/lib/api";
import type { Game, Season, Standing } from "@/types/api";

// League page: standings, team list and finished games for the selected season
// (spec §6.1). Server-rendered for SEO and fast first paint. The season is
// chosen via the ?season= query param, defaulting to the most recent.
export default async function LeaguePage({
  params,
  searchParams,
}: {
  params: Promise<{ liga: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { liga } = await params;
  const { season: seasonParam } = await searchParams;

  let leagueName: string;
  let seasons: Season[] = [];
  let selected: Season;
  let standings: Standing[] = [];
  let games: Game[] = [];

  try {
    const league = await getLeague(liga);
    leagueName = league.name;
    seasons = (await getSeasons(league.id)).results;
    if (seasons.length === 0) {
      return <EmptyLeague name={leagueName} />;
    }
    // Default to the most recent season (the API returns newest first).
    selected =
      seasons.find((s) => String(s.id) === seasonParam) ?? seasons[0];
    [standings, games] = await Promise.all([
      getStandings(selected.id),
      getGames(selected.id).then((g) => g.results),
    ]);
  } catch {
    notFound();
  }

  return (
    <div className="space-y-8">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">{leagueName}</h1>
          <p className="text-sm text-zinc-500">Temporada {selected.name}</p>
        </div>
        <SeasonSelector seasons={seasons} selectedId={selected.id} />
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Clasificación</h2>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="text-left text-zinc-500">
              <tr>
                <th className="py-2">#</th>
                <th>Equipo</th>
                <th className="text-right">PJ</th>
                <th className="text-right">V</th>
                <th className="text-right">D</th>
                <th className="text-right">PF</th>
                <th className="text-right">PC</th>
                <th className="text-right">Dif</th>
              </tr>
            </thead>
            <tbody>
              {standings.map((row, i) => (
                <tr key={row.teamSeasonId} className="border-t border-zinc-200 dark:border-zinc-800">
                  <td className="py-2">{i + 1}</td>
                  <td>
                    <Link
                      href={`/equipos/${row.teamSlug}`}
                      className="flex items-center gap-2 hover:underline"
                    >
                      <MediaImage
                        asset={row.teamLogo}
                        alt={row.teamName}
                        initials={row.teamName.slice(0, 2).toUpperCase()}
                        color={row.teamPrimaryColor || undefined}
                        rounded="lg"
                        size={24}
                      />
                      {row.teamName}
                    </Link>
                  </td>
                  <td className="text-right">{row.gamesPlayed}</td>
                  <td className="text-right">{row.wins}</td>
                  <td className="text-right">{row.losses}</td>
                  <td className="text-right">{row.pointsFor}</td>
                  <td className="text-right">{row.pointsAgainst}</td>
                  <td className="text-right">{row.pointDifference > 0 ? "+" : ""}{row.pointDifference}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Últimos partidos</h2>
        <ul className="space-y-1 text-sm">
          {games.slice(0, 10).map((game) => (
            <li
              key={game.id}
              className="border-b border-zinc-100 dark:border-zinc-800"
            >
              <Link
                href={`/partidos/${game.id}`}
                className="flex items-center gap-2 py-1.5 hover:bg-zinc-50 dark:hover:bg-zinc-900"
              >
                <span className="flex flex-1 items-center justify-end gap-2 text-right">
                  {game.homeTeam.name}
                  <MediaImage
                    asset={game.homeTeam.logo}
                    alt={game.homeTeam.name}
                    initials={game.homeTeam.name.slice(0, 2).toUpperCase()}
                    color={game.homeTeam.primaryColor || undefined}
                    rounded="lg"
                    size={22}
                  />
                </span>
                <span className="w-20 text-center font-semibold tabular-nums">
                  {game.finalScoreHome} – {game.finalScoreAway}
                </span>
                <span className="flex flex-1 items-center gap-2">
                  <MediaImage
                    asset={game.awayTeam.logo}
                    alt={game.awayTeam.name}
                    initials={game.awayTeam.name.slice(0, 2).toUpperCase()}
                    color={game.awayTeam.primaryColor || undefined}
                    rounded="lg"
                    size={22}
                  />
                  {game.awayTeam.name}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

function EmptyLeague({ name }: { name: string }) {
  return (
    <div className="space-y-2">
      <h1 className="text-2xl font-bold">{name}</h1>
      <p className="text-sm text-zinc-500">No hay temporadas cargadas todavía.</p>
    </div>
  );
}
