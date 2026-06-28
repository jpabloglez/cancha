import Link from "next/link";

import { getLeagues } from "@/lib/api";
import type { League } from "@/types/api";

// Leagues index: lists every covered competition (spec §6.1). Linked from the
// main navigation; each entry deep-links to the league detail page.
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
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {leagues.map((league) => (
            <li key={league.id}>
              <Link
                href={`/ligas/${league.slug}`}
                className="block rounded-lg border border-zinc-200 p-4 hover:border-court dark:border-zinc-800"
              >
                <span className="font-medium">{league.name}</span>
                <span className="block text-xs text-zinc-500">
                  Nivel {league.level}
                </span>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
