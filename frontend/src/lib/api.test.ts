import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  apiFetch,
  getAllTimeLeaders,
  getGames,
  getTeamRecentGames,
  getTeams,
  getTeamStaff,
} from "@/lib/api";

const BASE = "http://api.test/api/v1";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("api client", () => {
  const fetchMock = vi.fn();

  beforeEach(() => {
    fetchMock.mockReset();
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ ok: true })));
    vi.stubGlobal("fetch", fetchMock);
  });
  afterEach(() => vi.unstubAllGlobals());

  const calledUrl = () => fetchMock.mock.calls[0][0] as string;

  it("requests the base URL plus path with a JSON accept header", async () => {
    await apiFetch("/leagues/");
    expect(calledUrl()).toBe(`${BASE}/leagues/`);
    expect(fetchMock.mock.calls[0][1].headers).toEqual({ Accept: "application/json" });
  });

  it("returns the parsed JSON body", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ count: 2 })));
    await expect(apiFetch<{ count: number }>("/x/")).resolves.toEqual({ count: 2 });
  });

  it("throws with the status and URL on a non-2xx response", async () => {
    fetchMock.mockImplementation(() => Promise.resolve(jsonResponse({ detail: "no" }, 404)));
    await expect(apiFetch("/missing/")).rejects.toThrow(
      `API request failed (404): ${BASE}/missing/`,
    );
  });

  it("lets callers override fetch options", async () => {
    await apiFetch("/x/", { next: { revalidate: 5 } } as RequestInit);
    expect(fetchMock.mock.calls[0][1].next).toEqual({ revalidate: 5 });
  });

  it("builds the team staff URL with and without a season", async () => {
    await getTeamStaff("club-a");
    expect(calledUrl()).toBe(`${BASE}/teams/club-a/staff/`);
    fetchMock.mockClear();
    await getTeamStaff("club-a", 7);
    expect(calledUrl()).toBe(`${BASE}/teams/club-a/staff/?season=7`);
  });

  it("builds game list queries from the provided options only", async () => {
    await getGames(3, { limit: 20, offset: 40, round: "J5" });
    const url = new URL(calledUrl());
    expect(url.pathname).toBe("/api/v1/games/");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      season: "3",
      limit: "20",
      offset: "40",
      round: "J5",
    });
    fetchMock.mockClear();
    await getGames(3);
    expect(calledUrl()).toBe(`${BASE}/games/?season=3`);
  });

  it("builds team list and recent-game queries", async () => {
    await getTeams();
    expect(calledUrl()).toBe(`${BASE}/teams/`);
    fetchMock.mockClear();
    await getTeams({ limit: 500, search: "real madrid" });
    expect(new URL(calledUrl()).searchParams.get("search")).toBe("real madrid");
    fetchMock.mockClear();
    await getTeamRecentGames("club-a", { season: 2, limit: 10 });
    expect(calledUrl()).toBe(`${BASE}/teams/club-a/recent-games/?season=2&limit=10`);
  });

  it("only sends all-time leader filters that were set (including zero)", async () => {
    await getAllTimeLeaders({ stat: "ppg", minGames: 0, league: "acb" });
    const params = new URL(calledUrl()).searchParams;
    expect(Object.fromEntries(params)).toEqual({ stat: "ppg", league: "acb", minGames: "0" });
  });
});
