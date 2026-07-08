import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Glosario — Basket Stats",
  description:
    "Definiciones y fórmulas de las estadísticas avanzadas de baloncesto utilizadas en Basket Stats.",
};

const ADVANCED_METRICS = [
  {
    abbr: "TS%",
    name: "True Shooting Percentage",
    description:
      "Eficiencia real de anotación que pondera los tiros de campo de dos y tres puntos y los tiros libres en una sola métrica. Un valor alto indica que el jugador convierte con pocos intentos.",
    formula: "PTS / (2 × (TC + 0,44 × TL))",
    notes: "La media de la liga suele estar entre 50–55 %. Por encima del 60 % es élite.",
  },
  {
    abbr: "eFG%",
    name: "Effective Field Goal Percentage",
    description:
      "Ajusta el porcentaje de campo para reflejar que un triple vale 1,5 veces más que un doble, igualando la comparación entre lanzadores de 2 y de 3.",
    formula: "(TC2 + 1,5 × TC3) / TC",
    notes: "Siempre mayor o igual que el FG% convencional.",
  },
  {
    abbr: "USO%",
    name: "Usage Rate · Tasa de uso",
    description:
      "Porcentaje estimado de posesiones del equipo que terminan en una acción del jugador (intento de campo, tiro libre o pérdida) mientras está en pista.",
    formula: "(TC + TLI×0,44 + PER) / (MIN/5 × (TC_equipo + TLI_equipo×0,44 + PER_equipo))",
    notes:
      "Un titular habitual suele tener un USO% de 18–25 %. Por encima del 30 % indica un rol de primer portador de balón.",
  },
  {
    abbr: "PER",
    name: "Player Efficiency Rating",
    description:
      "Índice compuesto (adaptación de John Hollinger) que resume la producción global de un jugador por minuto jugado, ajustando por el ritmo de la liga.",
    formula: "Suma ponderada de acciones positivas (puntos, rebotes, asistencias, robos, tapones) menos acciones negativas (pérdidas, faltas), dividida entre minutos.",
    notes: "La media de liga se sitúa en torno a 15. Por encima de 25 es considerado temporada de All-Star.",
  },
  {
    abbr: "ORtg",
    name: "Offensive Rating · Rating Ofensivo",
    description:
      "Puntos anotados por el equipo por cada 100 posesiones. Permite comparar la eficiencia ofensiva entre equipos con diferente ritmo de juego.",
    formula: "100 × (PTS_equipo / Posesiones_equipo)",
    notes: "Valores superiores a 110 son generalmente buenos a nivel de élite.",
  },
  {
    abbr: "DRtg",
    name: "Defensive Rating · Rating Defensivo",
    description:
      "Puntos concedidos por el equipo por cada 100 posesiones. Cuanto más bajo, mejor es la defensa.",
    formula: "100 × (PTS_rival / Posesiones_equipo)",
    notes: "En la ACB, valores inferiores a 100 indican una defensa excepcional.",
  },
  {
    abbr: "NetRtg",
    name: "Net Rating · Diferencial de Rating",
    description:
      "Diferencia entre el ORtg y el DRtg. Refleja el margen neto del equipo por cada 100 posesiones, siendo el mejor indicador individual de calidad de equipo.",
    formula: "ORtg − DRtg",
    notes: "Un NetRtg positivo indica que el equipo crea más puntos de los que concede.",
  },
];

const BASIC_ACRONYMS = [
  { abbr: "PJ", name: "Partidos jugados" },
  { abbr: "MIN", name: "Minutos por partido" },
  { abbr: "PTS", name: "Puntos por partido" },
  { abbr: "TC", name: "Tiros de campo intentados" },
  { abbr: "TC%", name: "Porcentaje de tiros de campo" },
  { abbr: "TC2", name: "Tiros de dos puntos convertidos" },
  { abbr: "TC3", name: "Tiros de tres puntos convertidos" },
  { abbr: "TL", name: "Tiros libres intentados" },
  { abbr: "TL%", name: "Porcentaje de tiros libres" },
  { abbr: "TLI", name: "Tiros libres intentados" },
  { abbr: "REB", name: "Rebotes totales por partido" },
  { abbr: "RO", name: "Rebotes ofensivos" },
  { abbr: "RD", name: "Rebotes defensivos" },
  { abbr: "ASI", name: "Asistencias por partido" },
  { abbr: "ROB", name: "Robos por partido" },
  { abbr: "TAP", name: "Tapones por partido" },
  { abbr: "PER", name: "Pérdidas por partido (contexto básico)" },
  { abbr: "FP", name: "Faltas personales por partido" },
];

// Plain-language glossary of advanced metrics for a general audience (spec §6.1).
export default function GlosarioPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-10">
      <header>
        <h1 className="text-2xl font-bold">Glosario de métricas</h1>
        <p className="mt-2 text-sm text-zinc-500">
          Definiciones y fórmulas de las estadísticas avanzadas que aparecen en
          los perfiles de jugadores y equipos.
        </p>
      </header>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Métricas avanzadas</h2>
        <dl className="space-y-4">
          {ADVANCED_METRICS.map((metric) => (
            <div
              key={metric.abbr}
              className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
            >
              <dt className="font-semibold">
                {metric.abbr}{" "}
                <span className="text-zinc-500">· {metric.name}</span>
              </dt>
              <dd className="mt-1 space-y-1.5 text-sm text-zinc-600 dark:text-zinc-400">
                <p>{metric.description}</p>
                <p className="font-mono text-xs text-zinc-400">
                  {metric.formula}
                </p>
                <p className="text-xs italic">{metric.notes}</p>
              </dd>
            </div>
          ))}
        </dl>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-semibold">Acrónimos básicos</h2>
        <div className="grid grid-cols-1 gap-x-6 gap-y-1 text-sm sm:grid-cols-2">
          {BASIC_ACRONYMS.map((a) => (
            <div key={a.abbr} className="flex gap-2 border-b border-zinc-100 py-1.5 dark:border-zinc-800">
              <span className="w-12 shrink-0 font-mono font-semibold">{a.abbr}</span>
              <span className="text-zinc-600 dark:text-zinc-400">{a.name}</span>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
