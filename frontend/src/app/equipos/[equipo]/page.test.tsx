import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const notFound = vi.fn(() => {
  throw new Error("NEXT_NOT_FOUND");
});
vi.mock("next/navigation", () => ({
  notFound: () => notFound(),
  useRouter: () => ({ push: vi.fn() }),
  usePathname: () => "/equipos/club-a",
}));
vi.mock("@/lib/api", () => ({
  BACKEND_ORIGIN: "http://api.test",
  getTeam: vi.fn(),
  getTeamSeasons: vi.fn(),
  getSeasons: vi.fn(),
  getRoster: vi.fn(),
  getTeamStaff: vi.fn(),
  getTeamSeasonStats: vi.fn(),
  getTeamStatsHistory: vi.fn(),
  getTeamRecentGames: vi.fn(),
}));
// Chart components rely on layout measurement that jsdom does not provide.
vi.mock("@/components/TeamRadar", () => ({ TeamRadar: () => <div data-testid="radar" /> }));
vi.mock("@/components/TeamHistoryChart", () => ({
  TeamHistoryChart: () => <div data-testid="history-chart" />,
}));

import TeamPage, { generateMetadata } from "@/app/equipos/[equipo]/page";
import * as api from "@/lib/api";
import type { Season, StaffEntry, Team } from "@/types/api";

const team: Team = {
  id: 10, name: "Club Alpha", shortName: "ALP", slug: "club-a", city: "Madrid",
  foundedYear: null, officialName: "", arena: "", primaryColor: "#112233",
  secondaryColor: "", website: "", logo: null,
};
const season = (id: number, name: string): Season => ({
  id, name, league: 1, startDate: "2024-09-01", endDate: null,
});
const staff = (id: number, name: string, role: string): StaffEntry => ({
  id, firstName: name, lastName: "", displayName: name, slug: `s-${id}`, role,
});
const paged = <T,>(results: T[]) => ({ count: results.length, next: null, previous: null, results });

function mockHappyPath(staffRows: StaffEntry[]) {
  vi.mocked(api.getTeam).mockResolvedValue(team);
  vi.mocked(api.getTeamSeasons).mockResolvedValue(
    paged([
      { id: 1, team, season: 1, league: 1 },
      { id: 2, team, season: 2, league: 1 },
    ]),
  );
  vi.mocked(api.getSeasons).mockResolvedValue(
    paged([season(2, "2025-2026"), season(1, "2024-2025"), season(9, "2020-2021")]),
  );
  vi.mocked(api.getRoster).mockResolvedValue([]);
  vi.mocked(api.getTeamStaff).mockResolvedValue(staffRows);
  vi.mocked(api.getTeamSeasonStats).mockRejectedValue(new Error("no stats"));
  vi.mocked(api.getTeamStatsHistory).mockResolvedValue([]);
  vi.mocked(api.getTeamRecentGames).mockResolvedValue([]);
}

const renderPage = async (seasonParam?: string) =>
  render(
    await TeamPage({
      params: Promise.resolve({ equipo: "club-a" }),
      searchParams: Promise.resolve({ season: seasonParam }),
    }),
  );

describe("team page", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("shows the head coach and assistants for the selected season", async () => {
    mockHappyPath([
      staff(1, "Ana Coach", "head_coach"),
      staff(2, "Luis Aid", "assistant_coach"),
    ]);
    await renderPage();

    const heading = screen.getByRole("heading", { name: /Cuerpo técnico/ });
    expect(heading).toHaveTextContent("2025-2026");
    const section = heading.closest("section") as HTMLElement;
    expect(within(section).getByText("Entrenador principal")).toBeInTheDocument();
    expect(within(section).getByText("Ana Coach")).toBeInTheDocument();
    expect(within(section).getByText("Luis Aid")).toBeInTheDocument();
    expect(api.getTeamStaff).toHaveBeenCalledWith("club-a", 2);
  });

  it("hides the staff section when there is no staff", async () => {
    mockHappyPath([]);
    await renderPage();
    expect(screen.queryByRole("heading", { name: /Cuerpo técnico/ })).not.toBeInTheDocument();
    expect(screen.getByText("No hay plantilla cargada.")).toBeInTheDocument();
  });

  it("honours ?season= and only offers seasons the club played", async () => {
    mockHappyPath([]);
    await renderPage("1");

    expect(api.getRoster).toHaveBeenCalledWith("club-a", 1);
    expect(screen.getByRole("heading", { name: /Plantilla/ })).toHaveTextContent("2024-2025");
    const options = screen.getAllByRole("option").map((o) => o.textContent);
    expect(options).toEqual(["2025-2026", "2024-2025"]); // 2020-2021 not played
  });

  it("falls back to the latest season for an unknown ?season=", async () => {
    mockHappyPath([]);
    await renderPage("999");
    expect(api.getRoster).toHaveBeenCalledWith("club-a", 2);
  });

  it("triggers a 404 when the team cannot be loaded", async () => {
    vi.mocked(api.getTeam).mockRejectedValue(new Error("404"));
    await expect(renderPage()).rejects.toThrow("NEXT_NOT_FOUND");
    expect(notFound).toHaveBeenCalled();
  });

  it("builds metadata from the team and degrades when the API fails", async () => {
    vi.mocked(api.getTeam).mockResolvedValue(team);
    const ok = await generateMetadata({ params: Promise.resolve({ equipo: "club-a" }) });
    expect(ok.title).toBe("Club Alpha · Basket Stats");
    vi.mocked(api.getTeam).mockRejectedValue(new Error("down"));
    const fallback = await generateMetadata({ params: Promise.resolve({ equipo: "club-a" }) });
    expect(fallback.title).toBe("Equipo · Basket Stats");
  });
});
