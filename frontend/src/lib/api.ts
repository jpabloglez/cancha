// Typed client for the public Django REST API (spec §6.4).
//
// Reads the base URL from NEXT_PUBLIC_API_BASE_URL so the same code works in
// local dev, preview and production deployments.

import type {
  AllTimeLeaderPage,
  BoxScore,
  Game,
  Leader,
  League,
  Paginated,
  Person,
  PersonDetail,
  PlayerOfTheDay,
  PlayerSeasonStats,
  RosterEntry,
  Season,
  Standing,
  Team,
  TeamSeason,
  TeamSeasonStats,
  TeamStatsHistoryEntry,
} from "@/types/api";

// The browser reaches the API at its public URL (e.g. http://localhost:8000),
// but server-side rendering inside Docker must reach it over the compose
// network (http://backend:8000). API_INTERNAL_BASE_URL covers the latter; it is
// a server-only var (no NEXT_PUBLIC_ prefix) and falls back to the public URL.
const PUBLIC_API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";

const API_BASE_URL =
  typeof window === "undefined"
    ? (process.env.API_INTERNAL_BASE_URL ?? PUBLIC_API_BASE_URL)
    : PUBLIC_API_BASE_URL;

// The public origin of the Django backend (scheme + host + port, no path).
// Used to resolve root-relative media paths returned by the API so images are
// always served from the browser-accessible host, not the internal Docker one.
export const BACKEND_ORIGIN = PUBLIC_API_BASE_URL.replace(/\/api\/v1\/?$/, "");

/**
 * Fetch JSON from an API path, throwing on non-2xx responses.
 *
 * @param path - API path relative to the base URL (e.g. "/leagues/").
 * @param init - Optional fetch options (e.g. Next.js revalidate hints).
 * @returns Parsed JSON body typed as T.
 */
export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const url = `${API_BASE_URL}${path}`;
  const response = await fetch(url, {
    headers: { Accept: "application/json" },
    // Revalidate cached responses periodically; data is post-game (spec §9).
    next: { revalidate: 3600 },
    // Fail fast (rather than hang a build/request) when the API is unreachable.
    signal: AbortSignal.timeout(10000),
    ...init,
  });

  if (!response.ok) {
    throw new Error(`API request failed (${response.status}): ${url}`);
  }

  return (await response.json()) as T;
}

/** Fetch the list of covered leagues. */
export function getLeagues(): Promise<Paginated<League>> {
  return apiFetch<Paginated<League>>("/leagues/");
}

/** Fetch a single league by its slug. */
export function getLeague(slug: string): Promise<League> {
  return apiFetch<League>(`/leagues/${slug}/`);
}

/** Fetch the seasons of a league (most recent first). */
export function getSeasons(leagueId: number): Promise<Paginated<Season>> {
  return apiFetch<Paginated<Season>>(`/seasons/?league=${leagueId}`);
}

/** Fetch the computed standings for a season. */
export function getStandings(seasonId: number): Promise<Standing[]> {
  return apiFetch<Standing[]>(`/seasons/${seasonId}/standings/`);
}

/** Fetch finished games for a season. */
export function getGames(
  seasonId: number,
  opts: { limit?: number; offset?: number } = {},
): Promise<Paginated<Game>> {
  const params = new URLSearchParams({ season: String(seasonId) });
  if (opts.limit) params.set("limit", String(opts.limit));
  if (opts.offset) params.set("offset", String(opts.offset));
  return apiFetch<Paginated<Game>>(`/games/?${params.toString()}`);
}

/** Fetch the full box score (teams + player lines) for a game. */
export function getBoxscore(gameId: number): Promise<BoxScore> {
  return apiFetch<BoxScore>(`/games/${gameId}/boxscore/`);
}

/** Fetch a single team by its slug. */
export function getTeam(slug: string): Promise<Team> {
  return apiFetch<Team>(`/teams/${slug}/`);
}

/** Fetch aggregated stats for every season a team has participated in, newest first. */
export function getTeamStatsHistory(slug: string): Promise<TeamStatsHistoryEntry[]> {
  return apiFetch<TeamStatsHistoryEntry[]>(`/teams/${slug}/stats-history/`);
}

/** Fetch per-game, per-100-possession and advanced stats for a team in a season. */
export function getTeamSeasonStats(
  slug: string,
  seasonId: number,
): Promise<TeamSeasonStats> {
  return apiFetch<TeamSeasonStats>(
    `/teams/${slug}/season-stats/?season=${seasonId}`,
  );
}

/** Fetch a team's roster for a season. */
export function getRoster(slug: string, seasonId: number): Promise<RosterEntry[]> {
  return apiFetch<RosterEntry[]>(`/teams/${slug}/roster/?season=${seasonId}`);
}

/** Fetch the season participations of a team. */
export function getTeamSeasons(teamId: number): Promise<Paginated<TeamSeason>> {
  return apiFetch<Paginated<TeamSeason>>(`/team-seasons/?team=${teamId}`);
}

/** Fetch a single player by their slug. */
export function getPlayer(slug: string): Promise<PersonDetail> {
  return apiFetch<PersonDetail>(`/players/${slug}/`);
}

/** Fetch a player's per-season stats across all their seasons. */
export function getPlayerStats(slug: string): Promise<PlayerSeasonStats[]> {
  return apiFetch<PlayerSeasonStats[]>(`/players/${slug}/stats/`);
}

/** Compare several players for a season. */
export function comparePlayers(
  ids: number[],
  seasonId: number,
): Promise<PlayerSeasonStats[]> {
  return apiFetch<PlayerSeasonStats[]>(
    `/players/compare/?ids=${ids.join(",")}&season=${seasonId}`,
  );
}

/** Fetch the statistical leaders for a stat, optionally scoped to a season. */
export function getLeaders(
  stat: string,
  seasonId?: number,
  limit = 20,
  leagueId?: number,
): Promise<Leader[]> {
  const season = seasonId ? `&season=${seasonId}` : "";
  const league = leagueId ? `&league=${leagueId}` : "";
  return apiFetch<Leader[]>(
    `/stats/leaders/?stat=${stat}&limit=${limit}${season}${league}`,
  );
}

/** List players with optional full-text search and limit. */
export function getPlayers(
  limit = 50,
  search?: string,
): Promise<Paginated<Person>> {
  const params = new URLSearchParams({ limit: String(limit) });
  if (search) params.set("search", search);
  return apiFetch<Paginated<Person>>(`/players/?${params.toString()}`);
}

export interface SearchResults {
  teams: Team[];
  players: Person[];
  leagues: League[];
}

/** Global cross-entity search (min 2 chars). */
export function globalSearch(q: string): Promise<SearchResults> {
  return apiFetch<SearchResults>(`/search/?q=${encodeURIComponent(q)}`);
}

export interface AllTimeLeadersParams {
  stat?: string;
  league?: string;
  seasonFrom?: string;
  seasonTo?: string;
  position?: string;
  nationality?: string;
  minGames?: number;
  limit?: number;
  offset?: number;
}

/** Fetch cross-season cumulative/average statistical leaders. */
export function getAllTimeLeaders(params: AllTimeLeadersParams = {}): Promise<AllTimeLeaderPage> {
  const p = new URLSearchParams();
  if (params.stat) p.set("stat", params.stat);
  if (params.league) p.set("league", params.league);
  if (params.seasonFrom) p.set("seasonFrom", params.seasonFrom);
  if (params.seasonTo) p.set("seasonTo", params.seasonTo);
  if (params.position) p.set("position", params.position);
  if (params.nationality) p.set("nationality", params.nationality);
  if (params.minGames !== undefined) p.set("minGames", String(params.minGames));
  if (params.limit !== undefined) p.set("limit", String(params.limit));
  if (params.offset !== undefined) p.set("offset", String(params.offset));
  return apiFetch<AllTimeLeaderPage>(`/stats/alltime/?${p.toString()}`);
}

/** Fetch the deterministic player of the day (rotates at midnight Madrid time). */
export function getPlayerOfTheDay(): Promise<PlayerOfTheDay> {
  return apiFetch<PlayerOfTheDay>("/players/player-of-the-day/", {
    next: { revalidate: 3600 },
  });
}
