import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/lib/api", () => ({
  getLeagues: vi.fn(),
  getTeams: vi.fn(),
}));

import sitemap from "@/app/sitemap";
import { getLeagues, getTeams } from "@/lib/api";

describe("sitemap", () => {
  beforeEach(() => vi.clearAllMocks());

  it("lists static routes plus every league and team", async () => {
    vi.mocked(getLeagues).mockResolvedValue({
      count: 1, next: null, previous: null,
      results: [{ slug: "acb" }],
    } as never);
    vi.mocked(getTeams).mockResolvedValue({
      count: 1, next: null, previous: null,
      results: [{ slug: "club-a" }],
    } as never);

    const urls = (await sitemap()).map((e) => e.url);
    expect(urls).toContain("https://site.test/");
    expect(urls).toContain("https://site.test/ligas/acb");
    expect(urls).toContain("https://site.test/equipos/club-a");
    expect(getTeams).toHaveBeenCalledWith({ limit: 500 });
  });

  it("falls back to static routes when the API is unreachable", async () => {
    vi.mocked(getLeagues).mockRejectedValue(new Error("down"));
    vi.mocked(getTeams).mockRejectedValue(new Error("down"));

    const urls = (await sitemap()).map((e) => e.url);
    expect(urls).toHaveLength(8);
    expect(urls.every((u) => u.startsWith("https://site.test/"))).toBe(true);
    expect(urls.some((u) => u.includes("/equipos/"))).toBe(false);
  });
});
