import type { Metadata } from "next";
import Link from "next/link";

import { CONTACT_EMAIL } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: "Estadísticas de Baloncesto — ACB / LEB Oro / LEB Plata",
  description:
    "Estadísticas históricas y avanzadas de baloncesto español. Proyecto de aficionados, no oficial.",
};

// UI copy is in Spanish (spec §9); identifiers/comments remain in English.
const NAV_LINKS = [
  { href: "/ligas", label: "Ligas" },
  { href: "/comparar", label: "Comparar" },
  { href: "/lideres", label: "Líderes" },
  { href: "/glosario", label: "Glosario" },
  { href: "/acerca-de", label: "Acerca de" },
];

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es">
      <body className="min-h-screen flex flex-col">
        <header className="border-b border-zinc-200 dark:border-zinc-800">
          <nav className="mx-auto max-w-5xl flex items-center gap-6 px-4 py-4">
            <Link href="/" className="font-bold text-court">
              Basket Stats
            </Link>
            <ul className="flex gap-4 text-sm">
              {NAV_LINKS.map((link) => (
                <li key={link.href}>
                  <Link href={link.href} className="hover:underline">
                    {link.label}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>
        </header>
        <main className="mx-auto max-w-5xl w-full flex-1 px-4 py-8">{children}</main>
        <footer className="border-t border-zinc-200 dark:border-zinc-800 px-4 py-6 text-xs text-zinc-500">
          <div className="mx-auto max-w-5xl space-y-2">
            <p>
              Proyecto de aficionados, no afiliado oficialmente a la ACB ni a la
              FEB. Datos procedentes de fuentes públicas (ACB.com, FEB.es). Código
              abierto bajo licencia MIT.
            </p>
            <p>
              Los escudos y fotografías pertenecen a la ACB, la FEB y los clubes;
              se muestran sin ánimo de lucro y citando su origen. Si eres titular
              de derechos y deseas la retirada de una imagen, escríbenos a{" "}
              <a href={`mailto:${CONTACT_EMAIL}`} className="underline">
                {CONTACT_EMAIL}
              </a>
              . Más información en{" "}
              <Link href="/acerca-de" className="underline">
                Acerca de
              </Link>
              .
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
