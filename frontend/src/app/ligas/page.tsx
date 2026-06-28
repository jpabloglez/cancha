import Link from "next/link";

import { MediaImage } from "@/components/MediaImage";
import { getLeagues } from "@/lib/api";
import type { League } from "@/types/api";

export default async function LeaguesPage() {
  let leagues: League[] = [];
  let apiError = false;
  try {
    leagues = (await getLeagues()).results;
  } catch {
    apiError = true;
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Ligas</h1>
      {apiError ? (
        <p className="text-sm text-zinc-500">
          La API no está disponible. Arranca el backend y carga datos.
        </p>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-3">
          {leagues.map((league) => (
            <LeagueCard key={league.id} league={league} />
          ))}
        </ul>
      )}
    </div>
  );
}

function LeagueCard({ league }: { league: League }) {
  const initials = league.name
    .split(/\s+/)
    .map((w) => w[0]?.toUpperCase() ?? "")
    .slice(0, 3)
    .join("");

  return (
    <li>
      <Link
        href={`/ligas/${league.slug}`}
        className="group flex flex-col items-center gap-3 rounded-xl border border-zinc-200 bg-white p-6 text-center transition hover:shadow-md dark:border-zinc-800 dark:bg-zinc-900"
      >
        <MediaImage
          asset={league.logo}
          alt={league.name}
          initials={initials}
          size={72}
          rounded="lg"
        />
        <div>
          <p className="font-semibold group-hover:underline">{league.name}</p>
          <p className="mt-0.5 text-xs text-zinc-500">
            {league.teamsCount > 0
              ? `${league.teamsCount} equipos`
              : "Sin equipos registrados"}
            {league.seasonsCount > 0
              ? ` · ${league.seasonsCount} temporadas`
              : ""}
          </p>
        </div>
      </Link>
    </li>
  );
}
