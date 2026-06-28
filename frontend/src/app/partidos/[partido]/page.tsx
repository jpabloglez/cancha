import Link from "next/link";
import { notFound } from "next/navigation";

import { MediaImage } from "@/components/MediaImage";
import { getBoxscore } from "@/lib/api";
import type { BoxScore, PlayerBoxScore, Team } from "@/types/api";

// Game box score (spec §6.1): header with both clubs + final score, then a
// per-team table of player lines. Server-rendered.
export default async function BoxScorePage({
  params,
}: {
  params: Promise<{ partido: string }>;
}) {
  const { partido } = await params;

  let box: BoxScore;
  try {
    box = await getBoxscore(Number(partido));
  } catch {
    notFound();
  }

  const { game, playerStats } = box;
  const date = new Date(game.date).toLocaleDateString("es-ES", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });

  const linesFor = (teamSeasonId: number) =>
    playerStats
      .filter((p) => p.teamSeason === teamSeasonId)
      .sort((a, b) => b.points - a.points);

  return (
    <div className="space-y-8">
      {/* Scoreboard header */}
      <header className="flex items-center justify-center gap-4 sm:gap-8">
        <TeamHeading team={game.homeTeam} align="right" />
        <div className="text-center">
          <div className="text-3xl font-bold tabular-nums">
            {game.finalScoreHome} – {game.finalScoreAway}
          </div>
          <p className="mt-1 text-xs text-zinc-500">
            {game.round ? `${game.round} · ` : ""}
            {date}
          </p>
        </div>
        <TeamHeading team={game.awayTeam} align="left" />
      </header>

      <PlayerTable team={game.homeTeam} lines={linesFor(game.homeTeamSeason)} />
      <PlayerTable team={game.awayTeam} lines={linesFor(game.awayTeamSeason)} />
    </div>
  );
}

function TeamHeading({ team, align }: { team: Team; align: "left" | "right" }) {
  return (
    <Link
      href={`/equipos/${team.slug}`}
      className={`flex flex-1 items-center gap-3 hover:underline ${
        align === "right" ? "justify-end text-right" : "justify-start"
      }`}
    >
      {align === "left" && <TeamCrest team={team} />}
      <span className="font-semibold">{team.name}</span>
      {align === "right" && <TeamCrest team={team} />}
    </Link>
  );
}

function TeamCrest({ team }: { team: Team }) {
  return (
    <MediaImage
      asset={team.logo}
      alt={team.name}
      initials={team.name.slice(0, 2).toUpperCase()}
      color={team.primaryColor || undefined}
      rounded="lg"
      size={48}
    />
  );
}

function PlayerTable({ team, lines }: { team: Team; lines: PlayerBoxScore[] }) {
  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-2 text-lg font-semibold">
        <MediaImage
          asset={team.logo}
          alt={team.name}
          initials={team.name.slice(0, 2).toUpperCase()}
          color={team.primaryColor || undefined}
          rounded="lg"
          size={24}
        />
        {team.name}
      </h2>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-zinc-500">
            <tr>
              <th className="py-2">Jugador</th>
              <th className="text-right">Min</th>
              <th className="text-right">Pts</th>
              <th className="text-right">Reb</th>
              <th className="text-right">As</th>
              <th className="text-right">TC</th>
              <th className="text-right">T3</th>
              <th className="text-right">TL</th>
            </tr>
          </thead>
          <tbody>
            {lines.map((line) => {
              const name =
                line.person.displayName ||
                `${line.person.firstName} ${line.person.lastName}`;
              return (
                <tr
                  key={line.person.id}
                  className="border-t border-zinc-200 dark:border-zinc-800"
                >
                  <td className="py-2">
                    <Link
                      href={`/jugadores/${line.person.slug}`}
                      className="flex items-center gap-3 hover:underline"
                    >
                      <MediaImage
                        asset={line.person.photo}
                        alt={name}
                        initials={`${line.person.firstName[0] ?? ""}${
                          line.person.lastName[0] ?? ""
                        }`}
                        size={28}
                      />
                      <span>{name}</span>
                    </Link>
                  </td>
                  <td className="text-right tabular-nums">{line.minutesPlayed}</td>
                  <td className="text-right font-medium tabular-nums">
                    {line.points}
                  </td>
                  <td className="text-right tabular-nums">
                    {line.reboundsOff + line.reboundsDef}
                  </td>
                  <td className="text-right tabular-nums">{line.assists}</td>
                  <td className="text-right tabular-nums">
                    {line.fieldGoalsMade}/{line.fieldGoalsAtt}
                  </td>
                  <td className="text-right tabular-nums">
                    {line.threePointMade}/{line.threePointAtt}
                  </td>
                  <td className="text-right tabular-nums">
                    {line.freeThrowsMade}/{line.freeThrowsAtt}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
