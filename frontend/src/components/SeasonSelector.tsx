"use client";

// Season selector for league pages. Navigates to ?season=<id> so the
// server-rendered page re-fetches standings/games for the chosen season.

import { usePathname, useRouter } from "next/navigation";

import type { Season } from "@/types/api";

export function SeasonSelector({
  seasons,
  selectedId,
}: {
  seasons: Season[];
  selectedId: number;
}) {
  const router = useRouter();
  const pathname = usePathname();

  if (seasons.length <= 1) {
    return null;
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      <span className="text-zinc-500">Temporada</span>
      <select
        value={selectedId}
        onChange={(e) => router.push(`${pathname}?season=${e.target.value}`)}
        className="rounded border border-zinc-300 bg-transparent px-2 py-1 dark:border-zinc-700"
      >
        {seasons.map((season) => (
          <option key={season.id} value={season.id}>
            {season.name}
          </option>
        ))}
      </select>
    </label>
  );
}
