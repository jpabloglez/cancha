import Link from "next/link";

import { MediaImage } from "@/components/MediaImage";
import { apiFetch, getLeagues, getPlayers } from "@/lib/api";
import type { League, Paginated, Team } from "@/types/api";

export default async function HomePage() {
  // All three fetches run in parallel; any failure falls back gracefully.
  const [leaguesData, teamsData, playersData] = await Promise.all([
    getLeagues().catch((): null => null),
    apiFetch<Paginated<Team>>("/teams/?limit=1").catch((): null => null),
    getPlayers(1).catch((): null => null),
  ]);

  const leagues = leaguesData?.results ?? [];
  const totalTeams     = teamsData?.count ?? null;
  const totalPlayers   = playersData?.count ?? null;
  const totalSeasons   = leagues.reduce((s, l) => s + l.seasonsCount, 0) || null;
  const apiError       = leaguesData === null && teamsData === null;

  return (
    <div className="space-y-12">
      {/* ── Hero ─────────────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          Estadísticas de Baloncesto
        </h1>
        <p className="max-w-2xl text-zinc-500 dark:text-zinc-400">
          Estadísticas históricas y avanzadas de la ACB, LEB Oro (Primera FEB)
          y LEB Plata (Segunda FEB). Perfiles de jugadores y equipos,
          comparativas y métricas avanzadas explicadas para todos los públicos.
        </p>
      </section>

      {/* ── Summary stats cards ──────────────────────────────────────────── */}
      {!apiError && (
        <section aria-label="Resumen de datos">
          <ul className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            <StatCard value={leagues.length || null} label="Ligas" icon={<TrophyIcon />} />
            <StatCard value={totalSeasons}  label="Temporadas"  icon={<CalendarIcon />} />
            <StatCard value={totalTeams}    label="Equipos"     icon={<ShieldIcon />}   />
            <StatCard value={totalPlayers}  label="Jugadores"   icon={<PersonIcon />}   />
          </ul>
        </section>
      )}

      {/* ── League cards ─────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Ligas</h2>
        {apiError ? (
          <p className="text-sm text-zinc-500">
            La API no está disponible. Arranca el backend con{" "}
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
          <ul className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {leagues.map((league) => (
              <LeagueCard key={league.id} league={league} />
            ))}
          </ul>
        )}
      </section>

      {/* ── Quick links ──────────────────────────────────────────────────── */}
      <section className="space-y-4">
        <h2 className="text-xl font-semibold">Explorar</h2>
        <ul className="flex flex-wrap gap-3">
          {[
            { href: "/lideres",  label: "Líderes estadísticos" },
            { href: "/comparar", label: "Comparar jugadores" },
            { href: "/glosario", label: "Glosario de métricas" },
          ].map(({ href, label }) => (
            <li key={href}>
              <Link
                href={href}
                className="inline-block rounded-lg border border-zinc-200 px-4 py-2 text-sm font-medium text-zinc-700 transition-colors hover:border-court hover:text-court dark:border-zinc-700 dark:text-zinc-300 dark:hover:border-court dark:hover:text-court"
              >
                {label}
              </Link>
            </li>
          ))}
        </ul>
      </section>
    </div>
  );
}

// ── Stat card ─────────────────────────────────────────────────────────────────

function StatCard({
  value,
  label,
  icon,
}: {
  value: number | null;
  label: string;
  icon: React.ReactNode;
}) {
  return (
    <li className="flex flex-col gap-2 rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900">
      <span className="text-court">{icon}</span>
      <span className="text-2xl font-bold tabular-nums text-zinc-900 dark:text-zinc-50">
        {value !== null ? value.toLocaleString("es-ES") : "—"}
      </span>
      <span className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        {label}
      </span>
    </li>
  );
}

// ── League card ───────────────────────────────────────────────────────────────

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
              : "Sin equipos"}
            {league.seasonsCount > 0
              ? ` · ${league.seasonsCount} temporadas`
              : ""}
          </p>
        </div>
      </Link>
    </li>
  );
}

// ── Stat icons (inline SVG) ───────────────────────────────────────────────────

function TrophyIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M6 9H4a2 2 0 0 1-2-2V5h4" />
      <path d="M18 9h2a2 2 0 0 0 2-2V5h-4" />
      <path d="M12 17v4" />
      <path d="M8 21h8" />
      <path d="M6 5h12v6a6 6 0 0 1-12 0V5z" />
    </svg>
  );
}

function CalendarIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function PersonIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20c0-4 3.6-7 8-7s8 3 8 7" />
    </svg>
  );
}
