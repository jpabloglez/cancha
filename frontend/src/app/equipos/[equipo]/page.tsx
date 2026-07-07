import Link from "next/link";
import { notFound } from "next/navigation";

import { MediaImage } from "@/components/MediaImage";
import { SeasonSelector } from "@/components/SeasonSelector";
import { TeamHistoryChart } from "@/components/TeamHistoryChart";
import type { RadarAxis } from "@/components/TeamRadar";
import { TeamRadar } from "@/components/TeamRadar";
import {
  getRoster,
  getSeasons,
  getTeam,
  getTeamSeasonStats,
  getTeamSeasons,
  getTeamStatsHistory,
} from "@/lib/api";
import type {
  RosterEntry,
  RosterStats,
  Season,
  Team,
  TeamSeasonStats,
  TeamStatsHistoryEntry,
} from "@/types/api";

// Axes for the per-game and per-100 radars (same structure, different values).
const BOX_AXES: RadarAxis[] = [
  { key: "points", label: "PTS" },
  { key: "twoMade", label: "T2A" },
  { key: "threeMade", label: "T3A" },
  { key: "ftMade", label: "TLA" },
  { key: "rebOff", label: "RO" },
  { key: "rebDef", label: "RD" },
  { key: "rebounds", label: "REB" },
  { key: "assists", label: "ASI" },
  { key: "turnovers", label: "PER", inverted: true },
  { key: "steals", label: "ROB" },
  { key: "blocks", label: "TAP" },
  { key: "fouls", label: "FP", inverted: true },
];

const ADV_AXES: RadarAxis[] = [
  { key: "ortg", label: "ORtg" },
  { key: "tsPercent", label: "%TR" },
  { key: "pace", label: "Ritmo" },
  { key: "rebDefPct", label: "%RD" },
  { key: "drtg", label: "DRtg", inverted: true },
  { key: "blockPct", label: "%TAP" },
  { key: "stealPct", label: "%ROB" },
  { key: "rebOffPct", label: "%RO" },
  { key: "tovPercent", label: "%PER", inverted: true },
  { key: "efgPercent", label: "%TE" },
];

export default async function TeamPage({
  params,
  searchParams,
}: {
  params: Promise<{ equipo: string }>;
  searchParams: Promise<{ season?: string }>;
}) {
  const { equipo } = await params;
  const { season: seasonParam } = await searchParams;

  let team!: Team;
  let seasonOptions: Season[] = [];
  let selectedSeason: Season | undefined;
  let roster: RosterEntry[] = [];
  let teamStats: TeamSeasonStats | null = null;
  let history: TeamStatsHistoryEntry[] = [];

  try {
    team = await getTeam(equipo);
    const teamSeasons = (await getTeamSeasons(team.id)).results;

    if (teamSeasons.length > 0) {
      const leagueId = teamSeasons[0].league;
      const allSeasons = (await getSeasons(leagueId)).results;
      const participatedIds = new Set(teamSeasons.map((ts) => ts.season));
      seasonOptions = allSeasons.filter((s) => participatedIds.has(s.id));
      selectedSeason =
        seasonOptions.find((s) => String(s.id) === seasonParam) ??
        seasonOptions[0];

      const [rosterRes, statsRes, historyRes] = await Promise.all([
        selectedSeason
          ? getRoster(equipo, selectedSeason.id).catch((): RosterEntry[] => [])
          : Promise.resolve<RosterEntry[]>([]),
        selectedSeason
          ? getTeamSeasonStats(equipo, selectedSeason.id).catch(
              (): TeamSeasonStats | null => null,
            )
          : Promise.resolve<TeamSeasonStats | null>(null),
        getTeamStatsHistory(equipo).catch((): TeamStatsHistoryEntry[] => []),
      ]);
      roster = rosterRes;
      teamStats = statsRes;
      history = historyRes;
    }
  } catch {
    notFound();
  }

  const teamName = team!.shortName || team!.name;
  const teamColor = team!.primaryColor || undefined;

  return (
    <div className="space-y-8">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <TeamHeader team={team!} />
        {seasonOptions.length > 0 && selectedSeason && (
          <SeasonSelector seasons={seasonOptions} selectedId={selectedSeason.id} />
        )}
      </div>

      {teamStats && (
        <section className="space-y-4">
          <h2 className="text-lg font-semibold">
            Estadísticas
            {selectedSeason ? ` · ${selectedSeason.name}` : ""}
            <span className="ml-2 text-sm font-normal text-zinc-500">
              ({teamStats.team.gamesPlayed} partidos)
            </span>
          </h2>
          <div className="grid gap-6 md:grid-cols-3">
            <RadarCard title="Medias por partido">
              <TeamRadar
                teamName={teamName}
                teamColor={teamColor}
                axes={BOX_AXES}
                teamValues={{ ...teamStats.team.perGame }}
                avgValues={{ ...teamStats.leagueAvg.perGame }}
              />
            </RadarCard>
            <RadarCard title="Por 100 posesiones">
              <TeamRadar
                teamName={teamName}
                teamColor={teamColor}
                axes={BOX_AXES}
                teamValues={{ ...teamStats.team.per100 }}
                avgValues={{ ...teamStats.leagueAvg.per100 }}
              />
            </RadarCard>
            <RadarCard title="Estadística avanzada">
              <TeamRadar
                teamName={teamName}
                teamColor={teamColor}
                axes={ADV_AXES}
                teamValues={{ ...teamStats.team.advanced }}
                avgValues={{ ...teamStats.leagueAvg.advanced }}
              />
            </RadarCard>
          </div>
          <StatSummaryTable stats={teamStats} teamName={teamName} />
        </section>
      )}

      {history.length > 0 && (
        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Historial por temporada</h2>
          <TeamHistoryChart history={history} />
          <HistoryTable history={history} selectedSeasonId={selectedSeason?.id} />
        </section>
      )}

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">
          Plantilla{selectedSeason ? ` · ${selectedSeason.name}` : ""}
        </h2>
        {roster.length === 0 ? (
          <p className="text-sm text-zinc-500">No hay plantilla cargada.</p>
        ) : (
          <RosterGrid roster={roster} />
        )}
      </section>
    </div>
  );
}

function RadarCard({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1">
      <p className="text-center text-xs text-zinc-500">{title}</p>
      {children}
    </div>
  );
}

function StatSummaryTable({
  stats,
  teamName,
}: {
  stats: TeamSeasonStats;
  teamName: string;
}) {
  const pg = stats.team.perGame;
  const avg = stats.leagueAvg.perGame;
  const adv = stats.team.advanced;
  const advAvg = stats.leagueAvg.advanced;

  type Row = [string, number, number, boolean?];
  const rows: Row[] = [
    ["PTS", pg.points, avg.points],
    ["REB", pg.rebounds, avg.rebounds],
    ["ASI", pg.assists, avg.assists],
    ["ROB", pg.steals, avg.steals],
    ["TAP", pg.blocks, avg.blocks],
    ["PER", pg.turnovers, avg.turnovers, true],
    ["ORtg", adv.ortg, advAvg.ortg],
    ["DRtg", adv.drtg, advAvg.drtg, true],
    ["%TR", adv.tsPercent, advAvg.tsPercent],
    ["Ritmo", adv.pace, advAvg.pace],
  ];

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-zinc-500">
          <tr>
            <th className="py-1.5 pr-4">Stat</th>
            <th className="text-right">{teamName}</th>
            <th className="text-right">Liga</th>
            <th className="text-right">Dif.</th>
          </tr>
        </thead>
        <tbody>
          {rows.map(([label, team, league, inverted]) => {
            const diff = team - league;
            const good = inverted ? diff < 0 : diff > 0;
            const diffStr = diff > 0 ? `+${diff.toFixed(1)}` : diff.toFixed(1);
            return (
              <tr
                key={label}
                className="border-t border-zinc-100 dark:border-zinc-800"
              >
                <td className="py-1.5 pr-4 font-medium text-zinc-600 dark:text-zinc-400">
                  {label}
                </td>
                <td className="text-right tabular-nums">{team.toFixed(1)}</td>
                <td className="text-right tabular-nums text-zinc-500">
                  {league.toFixed(1)}
                </td>
                <td
                  className={`text-right tabular-nums font-medium ${
                    good
                      ? "text-emerald-600 dark:text-emerald-400"
                      : "text-red-600 dark:text-red-400"
                  }`}
                >
                  {diffStr}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function HistoryTable({
  history,
  selectedSeasonId,
}: {
  history: TeamStatsHistoryEntry[];
  selectedSeasonId?: number;
}) {
  type Col = {
    label: string;
    title: string;
    get: (e: TeamStatsHistoryEntry) => number;
    pct?: boolean;
    inverted?: boolean;
  };
  const cols: Col[] = [
    { label: "PJ", title: "Partidos jugados", get: (e) => e.team.gamesPlayed },
    { label: "PTS", title: "Puntos por partido", get: (e) => e.team.perGame.points },
    { label: "REB", title: "Rebotes por partido", get: (e) => e.team.perGame.rebounds },
    { label: "ASI", title: "Asistencias por partido", get: (e) => e.team.perGame.assists },
    { label: "ROB", title: "Robos por partido", get: (e) => e.team.perGame.steals },
    { label: "TAP", title: "Tapones por partido", get: (e) => e.team.perGame.blocks },
    { label: "PER", title: "Pérdidas por partido", get: (e) => e.team.perGame.turnovers, inverted: true },
    { label: "ORtg", title: "Rating ofensivo (pts/100 pos.)", get: (e) => e.team.advanced.ortg },
    { label: "DRtg", title: "Rating defensivo (pts concedidos/100 pos.)", get: (e) => e.team.advanced.drtg, inverted: true },
    { label: "%TR", title: "Porcentaje real de acierto", get: (e) => e.team.advanced.tsPercent, pct: true },
  ];

  function diffColor(team: number, avg: number, inverted: boolean) {
    const better = inverted ? team < avg : team > avg;
    return better
      ? "text-emerald-600 dark:text-emerald-400"
      : "text-red-500 dark:text-red-400";
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-zinc-500">
          <tr>
            <th className="py-2 pr-4">Temporada</th>
            {cols.map((c) => (
              <th key={c.label} className="px-2 text-right" title={c.title}>
                {c.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {history.map((entry) => {
            const isSelected = entry.season.id === selectedSeasonId;
            return (
              <tr
                key={entry.season.id}
                className={`border-t border-zinc-200 dark:border-zinc-800 ${
                  isSelected ? "bg-zinc-100 dark:bg-zinc-800/60" : ""
                }`}
              >
                <td className="py-2 pr-4">
                  <Link
                    href={`?season=${entry.season.id}`}
                    className="font-medium hover:underline"
                  >
                    {entry.season.name}
                  </Link>
                </td>
                {cols.map((c) => {
                  const val = c.get(entry);
                  const avg = c.label === "PJ"
                    ? entry.leagueAvg.gamesPlayed
                    : c.get({ ...entry, team: entry.leagueAvg });
                  const color =
                    c.label === "PJ" ? "" : diffColor(val, avg, c.inverted ?? false);
                  return (
                    <td
                      key={c.label}
                      className={`px-2 text-right tabular-nums ${color}`}
                      title={`Liga: ${avg.toFixed(1)}${c.pct ? "%" : ""}`}
                    >
                      {val.toFixed(1)}
                      {c.pct ? "%" : ""}
                    </td>
                  );
                })}
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="mt-1 text-xs text-zinc-400">
        Color: verde = por encima de la media de liga · rojo = por debajo. Pasa el ratón por un valor para ver la media.
      </p>
    </div>
  );
}

function RosterGrid({ roster }: { roster: RosterEntry[] }) {
  const sorted = [...roster].sort((a, b) => {
    if (a.jerseyNumber != null && b.jerseyNumber != null)
      return a.jerseyNumber - b.jerseyNumber;
    if (a.jerseyNumber != null) return -1;
    if (b.jerseyNumber != null) return 1;
    return (a.person.lastName ?? "").localeCompare(b.person.lastName ?? "");
  });

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6">
      {sorted.map((entry) => (
        <PlayerCard key={entry.id} entry={entry} />
      ))}
    </div>
  );
}

function PlayerCard({ entry }: { entry: RosterEntry }) {
  const { person, jerseyNumber, position, heightCm, stats } = entry;
  const name =
    person.displayName || `${person.firstName} ${person.lastName}`;
  const initials = `${person.firstName[0] ?? ""}${person.lastName[0] ?? ""}`;

  return (
    <Link
      href={`/jugadores/${person.slug}`}
      className="group block rounded-xl border border-zinc-200 bg-white transition hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
    >
      {/* Photo */}
      <div className="relative h-40 overflow-hidden rounded-t-xl bg-zinc-100 dark:bg-zinc-800">
        <MediaImage
          asset={person.photo}
          alt={name}
          initials={initials}
          fill
          rounded="lg"
        />
        {jerseyNumber != null && (
          <span className="absolute left-2 top-2 rounded-md bg-black/50 px-1.5 py-0.5 text-xs font-bold text-white backdrop-blur-sm">
            #{jerseyNumber}
          </span>
        )}
      </div>

      {/* Info */}
      <div className="p-2.5 space-y-1">
        <p className="truncate text-sm font-semibold leading-tight group-hover:underline">
          {name}
        </p>
        <p className="text-xs text-zinc-500">
          {[position, heightCm ? `${heightCm} cm` : null]
            .filter(Boolean)
            .join(" · ") || "—"}
        </p>
        {stats && <PlayerStatRow stats={stats} />}
      </div>
    </Link>
  );
}

function PlayerStatRow({ stats }: { stats: RosterStats }) {
  const items: [string, number][] = [
    ["PTS", stats.pointsPerGame],
    ["REB", stats.reboundsPerGame],
    ["ASI", stats.assistsPerGame],
  ];
  return (
    <div className="flex justify-between border-t border-zinc-100 pt-1.5 dark:border-zinc-800">
      {items.map(([label, val]) => (
        <div key={label} className="text-center">
          <p className="text-xs font-semibold tabular-nums">{val.toFixed(1)}</p>
          <p className="text-[10px] text-zinc-400">{label}</p>
        </div>
      ))}
    </div>
  );
}

function TeamHeader({ team, note }: { team: Team; note?: string }) {
  const initials = team.shortName || team.name.slice(0, 3).toUpperCase();
  const details = [
    team.city,
    team.arena || null,
    team.foundedYear ? `Fundado en ${team.foundedYear}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  return (
    <header className="flex items-center gap-4">
      <MediaImage
        asset={team.logo}
        alt={team.name}
        initials={initials}
        size={72}
        color={team.primaryColor || undefined}
        rounded="lg"
      />
      <div>
        <h1 className="text-2xl font-bold">{team.officialName || team.name}</h1>
        {details && <p className="text-sm text-zinc-500">{details}</p>}
        {team.website && (
          <a
            href={team.website}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm text-blue-600 hover:underline dark:text-blue-400"
          >
            Sitio oficial
          </a>
        )}
        {note && <p className="text-sm text-zinc-500">{note}</p>}
      </div>
    </header>
  );
}
