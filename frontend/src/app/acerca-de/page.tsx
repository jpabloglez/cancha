import Link from "next/link";
import type { Metadata } from "next";

import { CONTACT_EMAIL, GITHUB_URL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Acerca de — Basket Stats",
  description:
    "Qué es Basket Stats, cómo se calculan las estadísticas avanzadas y de dónde provienen los datos.",
};

// Acerca de: methodology, data sources, image-rights notice and takedown
// contact (spec §6.1, §10; docs/team-member-enrichment-plan.md §3).
export default function AcercaDePage() {
  return (
    <div className="mx-auto max-w-2xl space-y-10">
      <header>
        <h1 className="text-2xl font-bold">Acerca de este proyecto</h1>
        <p className="mt-3 text-zinc-600 dark:text-zinc-400">
          Basket Stats es una plataforma abierta y no comercial para visualizar
          estadísticas históricas y avanzadas del baloncesto español: Liga ACB,
          Primera FEB (LEB Oro) y Segunda FEB (LEB Plata). Todos los datos son
          post-partido — no se trabaja con información en vivo ni con partidos
          en curso.
        </p>
      </header>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Estadísticas avanzadas</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Además de las estadísticas básicas de cada partido (puntos, rebotes,
          asistencias…), la plataforma calcula automáticamente cuatro métricas
          avanzadas para cada jugador y temporada:
        </p>
        <dl className="space-y-3 text-sm">
          <div>
            <dt className="font-semibold">
              TS% — True Shooting Percentage
            </dt>
            <dd className="text-zinc-600 dark:text-zinc-400">
              Eficiencia real de anotación que pondera los tiros de dos, tres
              puntos y tiros libres en una sola métrica.
              <span className="ml-1 font-mono text-xs text-zinc-400">
                PTS / (2 × (TC + 0,44 × TL))
              </span>
            </dd>
          </div>
          <div>
            <dt className="font-semibold">
              eFG% — Effective Field Goal Percentage
            </dt>
            <dd className="text-zinc-600 dark:text-zinc-400">
              Ajusta el porcentaje de campo para reflejar que un triple vale
              más que un doble.
              <span className="ml-1 font-mono text-xs text-zinc-400">
                (TC2 + 1,5 × TC3) / TC
              </span>
            </dd>
          </div>
          <div>
            <dt className="font-semibold">USO% — Usage Rate</dt>
            <dd className="text-zinc-600 dark:text-zinc-400">
              Porcentaje de posesiones del equipo que terminan en una acción
              del jugador mientras está en pista. Permite comparar la carga
              ofensiva entre jugadores con distinto tiempo de juego.
            </dd>
          </div>
          <div>
            <dt className="font-semibold">
              PER — Player Efficiency Rating
            </dt>
            <dd className="text-zinc-600 dark:text-zinc-400">
              Índice de rendimiento global (adaptación de la fórmula de John
              Hollinger) que condensa todas las estadísticas de caja en un
              único número por minuto jugado. La media de liga se sitúa
              alrededor de 15.
            </dd>
          </div>
        </dl>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Más definiciones en el{" "}
          <Link href="/glosario" className="underline">
            Glosario
          </Link>
          .
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Fuentes de datos</h2>
        <ul className="list-inside list-disc space-y-1 text-sm text-zinc-600 dark:text-zinc-400">
          <li>
            <strong>ACB.com</strong> — estadísticas y resultados de la Liga
            Endesa (ACB).
          </li>
          <li>
            <strong>FEB.es / Baloncesto en Vivo</strong> — estadísticas y
            resultados de Primera FEB y Segunda FEB.
          </li>
        </ul>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Este es un proyecto de aficionados sin afiliación oficial con la ACB
          ni con la FEB. La recopilación de datos respeta los ficheros{" "}
          <code className="rounded bg-zinc-100 px-1 text-xs dark:bg-zinc-800">
            robots.txt
          </code>{" "}
          de cada fuente y aplica límites de velocidad razonables para no
          sobrecargar sus servidores. Si utilizas los datos de esta plataforma
          en otra publicación, agradecemos que cites a Basket Stats como fuente.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Derechos de imagen</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Los escudos de los clubes y las fotografías de jugadores que se
          muestran pertenecen a la ACB, a la FEB y a los distintos clubes, que
          los ponen a disposición a través de sus canales públicos. Se incluyen
          aquí sin ánimo de lucro y citando su origen. En ningún caso se
          reproducen con intención de vulnerar derechos de autor.
        </p>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          Si eres titular de derechos y consideras que algún contenido vulnera
          tu propiedad intelectual, contáctanos en{" "}
          <a
            href={`mailto:${CONTACT_EMAIL}`}
            className="underline"
          >
            {CONTACT_EMAIL}
          </a>{" "}
          y lo retiraremos a la mayor brevedad.
        </p>
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Código abierto</h2>
        <p className="text-sm text-zinc-600 dark:text-zinc-400">
          El código fuente de esta plataforma (backend Django + frontend
          Next.js) está publicado bajo licencia MIT en{" "}
          <a
            href={GITHUB_URL}
            target="_blank"
            rel="noopener noreferrer"
            className="underline"
          >
            GitHub
          </a>
          . Contribuciones y sugerencias son bienvenidas.
        </p>
      </section>
    </div>
  );
}
