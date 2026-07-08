import Link from "next/link";
import { notFound } from "next/navigation";

import { MediaImage } from "@/components/MediaImage";
import { SeasonSelector } from "@/components/SeasonSelector";
import { getGames, getLeague, getSeasons, getStandings } from "@/lib/api";
import type { Game, Season, Standing } from "@/types/api";

interface ZoneConfig {
  /** Top N rows in the promotion zone (green left border). */
  promotion?: number;
  promotionLabel?: string;
  /** Bottom N rows in the relegation zone (red left border). */
  relegation?: number;
  relegationLabel?: string;
  /** Top N rows in the playoff zone (orange left border). */
  playoff?: number;
  playoffLabel?: string;
}

const ZONE_CONFIG: Record<string, ZoneConfig> = {
  acb: { playoff: 8, playoffLabel: "Playoff" },
  "primera-feb": {
    promotion: 2,
    promotionLabel: "Ascenso ACB",
    relegation: 4,
    relegationLabel: "Descenso",
  },
  "segunda-feb": { promotion: 4, promotionLabel: "Ascenso Primera FEB" },
};

function rowZone(
  pos: number,
  total: number,
  zones: ZoneConfig,
): "promotion" | "playoff" | "relegation" | null {
  if (zones.promotion && pos <= zones.promotion) return "promotion";
  if (zones.playoff && pos <= zones.playoff) return "playoff";
  if (zones.relegation && pos > total - zones.relegation) return "relegation";
  return null;
}

const ZONE_BORDER: Record<string, string> = {
  promotion: "border-l-2 border-l-green-500",
  playoff: "border-l-2 border-l-orange-400",
  relegation: "border-l-2 border-l-red-500",
};

const ZONE_LABEL_COLOR: Record<string, string> = {
  promotion: "bg-green-100 text-green-700 dark:bg-green-900/40 dark:text-green-300",
  playoff: "bg-orange-100 text-orange-700 dark:bg-orange-900/40 dark:text-orange-300",
  relegation: "bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300",
};

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
                <th className="py-2 pr-2">#</th>
                <th>Equipo</th>
                <th className="text-right">PJ</th>
                <th className="text-right text-green-600 dark:text-green-400">V</th>
                <th className="text-right text-red-500 dark:text-red-400">D</th>
                <th className="text-right">PF</th>
                <th className="text-right">PC</th>
                <th className="text-right">Dif</th>
              </tr>
            </thead>
            <tbody>
              {standings.map((row, i) => {
                const pos = i + 1;
                const zones = ZONE_CONFIG[liga] ?? {};
                const zone = rowZone(pos, standings.length, zones);
                const prevZone = i > 0
                  ? rowZone(i, standings.length, zones)
                  : null;
                const zoneLabel =
                  zone === "promotion" && pos === 1
                    ? zones.promotionLabel
                    : zone === "playoff" && pos === 1
                      ? zones.playoffLabel
                      : zone === "relegation" && pos === standings.length - (zones.relegation ?? 0) + 1
                        ? zones.relegationLabel
                        : null;
                const showDivider = zone !== prevZone && i > 0;
                return (
                  <>
                    {showDivider && (
                      <tr key={`divider-${i}`} aria-hidden>
                        <td
                          colSpan={8}
                          className="h-px bg-zinc-200 p-0 dark:bg-zinc-700"
                        />
                      </tr>
                    )}
                    <tr
                      key={row.teamSeasonId}
                      className={`border-t border-zinc-200 dark:border-zinc-800 ${
                        zone ? ZONE_BORDER[zone] : ""
                      }`}
                    >
                      <td className="py-2 pr-2 text-zinc-400">{pos}</td>
                      <td>
                        <div className="flex items-center gap-2">
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
                          {zoneLabel && zone && (
                            <span
                              className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${ZONE_LABEL_COLOR[zone]}`}
                            >
                              {zoneLabel}
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="text-right tabular-nums">{row.gamesPlayed}</td>
                      <td className="text-right tabular-nums font-medium text-green-600 dark:text-green-400">
                        {row.wins}
                      </td>
                      <td className="text-right tabular-nums text-red-500 dark:text-red-400">
                        {row.losses}
                      </td>
                      <td className="text-right tabular-nums">{row.pointsFor}</td>
                      <td className="text-right tabular-nums">{row.pointsAgainst}</td>
                      <td className="text-right tabular-nums">
                        {row.pointDifference > 0 ? "+" : ""}
                        {row.pointDifference}
                      </td>
                    </tr>
                  </>
                );
              })}
            </tbody>
          </table>
        </div>
        {Object.keys(ZONE_CONFIG[liga] ?? {}).length > 0 && (
          <div className="flex flex-wrap gap-3 text-xs text-zinc-500">
            {ZONE_CONFIG[liga]?.promotion && (
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-0.5 rounded bg-green-500" />
                {ZONE_CONFIG[liga].promotionLabel}
              </span>
            )}
            {ZONE_CONFIG[liga]?.playoff && (
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-0.5 rounded bg-orange-400" />
                {ZONE_CONFIG[liga].playoffLabel}
              </span>
            )}
            {ZONE_CONFIG[liga]?.relegation && (
              <span className="flex items-center gap-1.5">
                <span className="h-3 w-0.5 rounded bg-red-500" />
                {ZONE_CONFIG[liga].relegationLabel}
              </span>
            )}
          </div>
        )}
      </section>

      <section className="space-y-3">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">Últimos partidos</h2>
          {games.length > 0 && (
            <Link
              href={`/ligas/${liga}/partidos?season=${selected.id}&page=1`}
              className="text-sm text-court hover:underline"
            >
              Ver todos →
            </Link>
          )}
        </div>
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
