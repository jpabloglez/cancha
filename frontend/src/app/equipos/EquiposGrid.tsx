"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import { MediaImage } from "@/components/MediaImage";
import { getTeams } from "@/lib/api";
import type { Team } from "@/types/api";

function SearchInput({ initialQuery }: { initialQuery: string }) {
  const router = useRouter();
  const [value, setValue] = useState(initialQuery);

  useEffect(() => {
    const timer = setTimeout(() => {
      const params = new URLSearchParams();
      if (value.trim()) params.set("q", value.trim());
      router.replace(`/equipos${params.toString() ? `?${params}` : ""}`, {
        scroll: false,
      });
    }, 250);
    return () => clearTimeout(timer);
  }, [value, router]);

  return (
    <input
      type="search"
      value={value}
      onChange={(e) => setValue(e.target.value)}
      placeholder="Filtrar por nombre o ciudad…"
      aria-label="Filtrar equipos"
      className="w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm placeholder-zinc-400 outline-none focus:border-zinc-500 dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100 sm:w-72"
    />
  );
}

function TeamCard({ team }: { team: Team }) {
  const initials = team.shortName
    ? team.shortName.slice(0, 2).toUpperCase()
    : team.name.slice(0, 2).toUpperCase();

  return (
    <Link
      href={`/equipos/${team.slug}`}
      className="group flex items-center gap-4 rounded-xl border border-zinc-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-700 dark:bg-zinc-900"
    >
      <MediaImage
        asset={team.logo}
        alt={team.name}
        initials={initials}
        color={team.primaryColor || undefined}
        rounded="lg"
        size={48}
      />
      <div className="min-w-0 flex-1">
        <p className="truncate font-semibold group-hover:underline">{team.name}</p>
        {team.city && (
          <p className="truncate text-sm text-zinc-500 dark:text-zinc-400">{team.city}</p>
        )}
      </div>
      <span className="shrink-0 text-zinc-400 dark:text-zinc-600">→</span>
    </Link>
  );
}

const SKELETON_COUNT = 12;

function Skeleton() {
  return (
    <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: SKELETON_COUNT }).map((_, i) => (
        <div
          key={i}
          className="h-20 animate-pulse rounded-xl border border-zinc-100 bg-zinc-100 dark:border-zinc-800 dark:bg-zinc-800"
        />
      ))}
    </div>
  );
}

function EquiposContent() {
  const searchParams = useSearchParams();
  const query = searchParams.get("q") ?? "";

  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    getTeams({ limit: 500, search: query || undefined })
      .then((page) => setTeams(page.results))
      .catch(() => setTeams([]))
      .finally(() => setLoading(false));
  }, [query]);

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-center gap-3">
        <SearchInput initialQuery={query} />
        {!loading && teams.length > 0 && (
          <span className="text-sm text-zinc-400">
            {teams.length} equipo{teams.length !== 1 ? "s" : ""}
          </span>
        )}
      </div>

      {loading ? (
        <Skeleton />
      ) : teams.length === 0 ? (
        <p className="text-zinc-400">
          {query
            ? `No se encontraron equipos para "${query}".`
            : "No hay equipos disponibles."}
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {teams.map((team) => (
            <TeamCard key={team.id} team={team} />
          ))}
        </div>
      )}
    </div>
  );
}

export function EquiposGrid() {
  return (
    <Suspense fallback={<Skeleton />}>
      <EquiposContent />
    </Suspense>
  );
}
