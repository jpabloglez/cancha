import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const replace = vi.fn();
let query = "";
vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace }),
  useSearchParams: () => new URLSearchParams(query),
}));
vi.mock("@/lib/api", () => ({
  getTeams: vi.fn(),
  BACKEND_ORIGIN: "http://api.test",
}));

import { EquiposGrid } from "@/app/equipos/EquiposGrid";
import { getTeams } from "@/lib/api";
import type { Team } from "@/types/api";

const team = (id: number, name: string, city: string | null): Team => ({
  id, name, shortName: name.slice(0, 3), slug: `club-${id}`, city,
  foundedYear: null, officialName: "", arena: "", primaryColor: "",
  secondaryColor: "", website: "", logo: null,
});

const page = (results: Team[]) => ({ count: results.length, next: null, previous: null, results });

describe("EquiposGrid", () => {
  beforeEach(() => {
    query = "";
    replace.mockClear();
    vi.mocked(getTeams).mockReset();
  });
  afterEach(() => vi.useRealTimers());

  it("lists teams as links with their city and a count", async () => {
    vi.mocked(getTeams).mockResolvedValue(
      page([team(1, "Real Alpha", "Madrid"), team(2, "Beta Club", null)]),
    );
    render(<EquiposGrid />);

    const link = await screen.findByRole("link", { name: /Real Alpha/ });
    expect(link).toHaveAttribute("href", "/equipos/club-1");
    expect(screen.getByText("Madrid")).toBeInTheDocument();
    expect(screen.getByText("2 equipos")).toBeInTheDocument();
    expect(getTeams).toHaveBeenCalledWith({ limit: 500, search: undefined });
  });

  it("passes the URL query to the API and reports an empty result", async () => {
    query = "q=zzz";
    vi.mocked(getTeams).mockResolvedValue(page([]));
    render(<EquiposGrid />);

    expect(await screen.findByText('No se encontraron equipos para "zzz".')).toBeInTheDocument();
    expect(getTeams).toHaveBeenCalledWith({ limit: 500, search: "zzz" });
  });

  it("shows the empty state when the API fails", async () => {
    vi.mocked(getTeams).mockRejectedValue(new Error("down"));
    render(<EquiposGrid />);
    expect(await screen.findByText("No hay equipos disponibles.")).toBeInTheDocument();
  });

  it("debounces the filter input into a URL update", async () => {
    vi.mocked(getTeams).mockResolvedValue(page([team(1, "Real Alpha", "Madrid")]));
    render(<EquiposGrid />);
    await screen.findByRole("link", { name: /Real Alpha/ });
    replace.mockClear();

    vi.useFakeTimers({ shouldAdvanceTime: true });
    const input = screen.getByLabelText("Filtrar equipos");
    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).type(input, " bet ");
    await act(async () => {
      vi.advanceTimersByTime(300);
    });

    await waitFor(() =>
      expect(replace).toHaveBeenLastCalledWith("/equipos?q=bet", { scroll: false }),
    );
  });
});
