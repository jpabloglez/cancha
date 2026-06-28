import type { Metadata } from "next";

import { CONTACT_EMAIL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Acerca de — Basket Stats",
};

// Methodology, data sources, image-rights notice and takedown contact
// (spec §6.1, §10; docs/team-member-enrichment-plan.md §3).
export default function AcercaDePage() {
  return (
    <div className="space-y-4">
      <h1 className="text-2xl font-bold">Acerca de este proyecto</h1>
      <p className="text-zinc-600 dark:text-zinc-400">
        Plataforma abierta y no comercial para visualizar estadísticas históricas
        y avanzadas de baloncesto español (ACB, LEB Oro / Primera FEB y LEB Plata /
        Segunda FEB). No trabajamos con datos en vivo: la información se procesa
        tras la finalización de cada partido.
      </p>
      <h2 className="text-lg font-semibold">Fuentes de datos</h2>
      <p className="text-zinc-600 dark:text-zinc-400">
        Las estadísticas proceden de fuentes públicas (ACB.com y FEB.es). Este es
        un proyecto de aficionados sin afiliación oficial con la ACB ni la FEB. Las
        estadísticas básicas pertenecen a sus respectivas ligas; su tratamiento y
        presentación son obra de este proyecto. Agradecemos que se cite a esta web
        como fuente al reutilizar los datos.
      </p>
      <h2 className="text-lg font-semibold">Derechos de imagen</h2>
      <p className="text-zinc-600 dark:text-zinc-400">
        Los escudos de los clubes y las fotografías que se muestran pertenecen a la
        ACB, a la FEB y a los distintos clubes, que los ponen a disposición de
        sitios especializados a través de sus canales públicos. Se incluyen aquí
        sin ánimo de lucro y citando su origen. En ningún caso se reproducen con
        intención de vulnerar derechos de autor.
      </p>
      <h2 className="text-lg font-semibold">Retirada de contenido</h2>
      <p className="text-zinc-600 dark:text-zinc-400">
        Si eres titular de derechos y consideras que alguna imagen vulnera tus
        derechos, ponte en contacto con la administración del sitio en{" "}
        <a href={`mailto:${CONTACT_EMAIL}`} className="underline">
          {CONTACT_EMAIL}
        </a>{" "}
        y la retiraremos a la mayor brevedad.
      </p>
      <h2 className="text-lg font-semibold">Licencia</h2>
      <p className="text-zinc-600 dark:text-zinc-400">
        Código abierto bajo licencia MIT.
      </p>
    </div>
  );
}
