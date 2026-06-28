import type { Metadata } from "next";
import Link from "next/link";

import { NavBar } from "@/components/NavBar";
import { CONTACT_EMAIL, GITHUB_URL } from "@/lib/site";
import "./globals.css";

export const metadata: Metadata = {
  title: "Estadísticas de Baloncesto — ACB / LEB Oro / LEB Plata",
  description:
    "Estadísticas históricas y avanzadas de baloncesto español. Proyecto de aficionados, no oficial.",
};

// Inline script that runs before first paint to apply the saved theme and
// prevent a flash of unstyled (light) content. Default is dark.
const THEME_SCRIPT = `(function(){try{var t=localStorage.getItem('theme');document.documentElement.classList.toggle('dark',t!=='light')}catch(e){document.documentElement.classList.add('dark')}})();`;

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="es" suppressHydrationWarning>
      {/* suppressHydrationWarning: the inline script mutates className before
          React hydrates, so the server/client mismatch is intentional. */}
      <head>
        {/* eslint-disable-next-line @next/next/no-sync-scripts */}
        <script dangerouslySetInnerHTML={{ __html: THEME_SCRIPT }} />
      </head>
      <body className="flex min-h-screen flex-col bg-[--background] text-[--foreground]">
        <NavBar />

        <main className="mx-auto w-full max-w-5xl flex-1 px-4 py-8">
          {children}
        </main>

        <footer className="mt-8 border-t border-zinc-200 dark:border-zinc-800">
          <div className="mx-auto max-w-5xl px-4 py-8">
            <div className="flex flex-col gap-6 sm:flex-row sm:items-start sm:justify-between">
              {/* Left: identity + disclaimer */}
              <div className="space-y-2 text-xs text-zinc-500 dark:text-zinc-400">
                <p className="font-semibold text-zinc-700 dark:text-zinc-300">
                  Basket Stats
                </p>
                <p>
                  Proyecto de aficionados, no afiliado oficialmente a la ACB ni a
                  la FEB. Datos procedentes de fuentes públicas (ACB.com, FEB.es).
                  Código abierto bajo licencia MIT.
                </p>
                <p>
                  Los escudos y fotografías pertenecen a la ACB, la FEB y los
                  clubes; se muestran sin ánimo de lucro citando su origen. Si
                  eres titular de derechos y deseas la retirada de una imagen,
                  escríbenos a{" "}
                  <a
                    href={`mailto:${CONTACT_EMAIL}`}
                    className="underline underline-offset-2 hover:text-zinc-700 dark:hover:text-zinc-200"
                  >
                    {CONTACT_EMAIL}
                  </a>
                  .
                </p>
              </div>

              {/* Right: nav links */}
              <nav aria-label="Pie de página">
                <ul className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
                  <li>
                    <Link
                      href="/acerca-de"
                      className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                    >
                      Acerca de
                    </Link>
                  </li>
                  <li>
                    <Link
                      href="/glosario"
                      className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                    >
                      Glosario
                    </Link>
                  </li>
                  <li>
                    <a
                      href={`mailto:${CONTACT_EMAIL}`}
                      className="text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                    >
                      Contacto
                    </a>
                  </li>
                  <li>
                    <a
                      href={GITHUB_URL}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="flex items-center gap-1.5 text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                    >
                      <GitHubIcon />
                      GitHub
                    </a>
                  </li>
                </ul>
              </nav>
            </div>

            <p className="mt-6 text-xs text-zinc-400 dark:text-zinc-600">
              © {new Date().getFullYear()} Basket Stats · MIT License · Más
              información en{" "}
              <Link href="/acerca-de" className="underline underline-offset-2">
                Acerca de
              </Link>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}

function GitHubIcon() {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      width="15"
      height="15"
      viewBox="0 0 24 24"
      fill="currentColor"
      aria-hidden="true"
    >
      <path d="M12 0C5.37 0 0 5.37 0 12c0 5.3 3.44 9.8 8.21 11.39.6.11.82-.26.82-.58v-2.03c-3.34.73-4.04-1.61-4.04-1.61-.55-1.39-1.34-1.76-1.34-1.76-1.09-.74.08-.73.08-.73 1.2.08 1.84 1.24 1.84 1.24 1.07 1.83 2.8 1.3 3.49 1 .11-.78.42-1.3.76-1.6-2.67-.3-5.47-1.33-5.47-5.93 0-1.31.47-2.38 1.24-3.22-.12-.3-.54-1.52.12-3.18 0 0 1.01-.32 3.3 1.23a11.5 11.5 0 0 1 3-.4c1.02 0 2.04.14 3 .4 2.28-1.55 3.29-1.23 3.29-1.23.66 1.66.24 2.88.12 3.18.77.84 1.24 1.91 1.24 3.22 0 4.61-2.81 5.63-5.48 5.92.43.37.81 1.1.81 2.22v3.29c0 .32.21.7.82.58C20.56 21.8 24 17.3 24 12c0-6.63-5.37-12-12-12z" />
    </svg>
  );
}
