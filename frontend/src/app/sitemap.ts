import type { MetadataRoute } from "next";

import { getLeagues, getTeams } from "@/lib/api";

const BASE = process.env.NEXT_PUBLIC_SITE_URL ?? "https://basketstats.es";

function url(path: string, priority: number, changeFreq: MetadataRoute.Sitemap[number]["changeFrequency"]): MetadataRoute.Sitemap[number] {
  return { url: `${BASE}${path}`, lastModified: new Date(), changeFrequency: changeFreq, priority };
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const staticRoutes: MetadataRoute.Sitemap = [
    url("/",           1.0, "daily"),
    url("/ligas",      0.9, "weekly"),
    url("/equipos",    0.9, "weekly"),
    url("/jugadores",  0.9, "weekly"),
    url("/lideres",    0.8, "weekly"),
    url("/comparar",   0.6, "monthly"),
    url("/glosario",   0.5, "monthly"),
    url("/acerca-de",  0.4, "monthly"),
  ];

  let dynamicRoutes: MetadataRoute.Sitemap = [];

  try {
    const [leaguesPage, teamsPage] = await Promise.all([
      getLeagues(),
      getTeams({ limit: 500 }),
    ]);

    dynamicRoutes = [
      ...leaguesPage.results.map((l) => url(`/ligas/${l.slug}`, 0.8, "daily")),
      ...teamsPage.results.map((t) => url(`/equipos/${t.slug}`, 0.7, "weekly")),
    ];
  } catch {
    // If the API is unreachable at build time, return static routes only.
  }

  return [...staticRoutes, ...dynamicRoutes];
}
