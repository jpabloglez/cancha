import Link from "next/link";

import { getLeagues } from "@/lib/api";
import type { League } from "@/types/api";

// Home page: league selector and project intro (spec §6.1).
// Rendered on the server; falls back gracefully if the API is unreachable
// during local bootstrap (backend not yet seeded).
export default async function HomePage() {
  let leagues: League[] = [];
  let apiError = false;

  try {
    const data = await getLeagues();
    leagues = data.results;
  } catch {
    apiError = true;
  }

  return (
    <div className="space-y-8">
      <section className="space-y-3">
        <h1 className="text-3xl font-bold">Estadísticas de Baloncesto</h1>
        <p className="text-zinc-600 dark:text-zinc-400">
          Estadísticas históricas y avanzadas de la ACB, LEB Oro (Primera FEB) y
          LEB Plata (Segunda FEB). Perfiles de jugadores y equipos, comparativas y
          métricas avanzadas explicadas para todos los públicos.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-xl font-semibold">Ligas</h2>
        {apiError ? (
          <p className="text-sm text-zinc-500">
            La API aún no está disponible. Arranca el backend con{" "}
            <code className="rounded bg-zinc-100 px-1 dark:bg-zinc-800">
              docker compose up
            </code>{" "}
            y carga datos para ver las ligas aquí.
          </p>
        ) : leagues.length === 0 ? (
          <p className="text-sm text-zinc-500">
            Todavía no hay ligas cargadas en la base de datos.
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
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
