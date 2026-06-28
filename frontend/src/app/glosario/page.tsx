import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Glosario de métricas — Basket Stats",
};

// Plain-language glossary of advanced metrics for a general audience (spec §6.1).
const METRICS = [
  {
    abbr: "TS%",
    name: "True Shooting",
    description:
      "Eficiencia de tiro que tiene en cuenta tiros de 2, de 3 y libres en una sola cifra.",
  },
  {
    abbr: "eFG%",
    name: "Effective Field Goal",
    description:
      "Eficiencia en el tiro de campo dando más valor al triple que al tiro de 2.",
  },
  {
    abbr: "Usage Rate",
    name: "Tasa de uso",
    description:
      "Porcentaje de jugadas del equipo que un jugador finaliza mientras está en pista.",
  },
  {
    abbr: "PER",
    name: "Player Efficiency Rating",
    description:
      "Índice compuesto que resume la producción de un jugador por minuto jugado.",
  },
  {
    abbr: "Pace",
    name: "Ritmo",
    description: "Número estimado de posesiones que juega un equipo por partido.",
  },
];

export default function GlosarioPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Glosario de métricas avanzadas</h1>
      <dl className="space-y-4">
        {METRICS.map((metric) => (
          <div key={metric.abbr} className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
            <dt className="font-semibold">
              {metric.abbr} <span className="text-zinc-500">· {metric.name}</span>
            </dt>
            <dd className="mt-1 text-sm text-zinc-600 dark:text-zinc-400">
              {metric.description}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
