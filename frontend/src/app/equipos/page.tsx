import type { Metadata } from "next";

import { EquiposGrid } from "./EquiposGrid";

export const metadata: Metadata = {
  title: "Equipos · Basket Stats",
  description:
    "Todos los clubes de ACB, Primera FEB y Segunda FEB con estadísticas históricas, plantillas y resultados recientes.",
};

export default function EquiposPage() {
  return (
    <div className="space-y-8">
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">Equipos</h1>
        <p className="text-zinc-500 dark:text-zinc-400">
          Todos los clubes presentes en las bases de datos de ACB, Primera FEB y Segunda FEB.
        </p>
      </header>

      <EquiposGrid />
    </div>
  );
}
