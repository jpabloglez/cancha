import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
  usePathname: () => "/equipos/club-a",
}));

import { SeasonSelector } from "@/components/SeasonSelector";
import type { Season } from "@/types/api";

const season = (id: number, name: string): Season => ({
  id, name, league: 1, startDate: "2024-09-01", endDate: null,
});

describe("SeasonSelector", () => {
  beforeEach(() => push.mockClear());

  it("renders nothing when there is at most one season", () => {
    const { container } = render(
      <SeasonSelector seasons={[season(1, "2024-2025")]} selectedId={1} />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("lists the seasons with the selected one active", () => {
    render(
      <SeasonSelector
        seasons={[season(2, "2025-2026"), season(1, "2024-2025")]}
        selectedId={1}
      />,
    );
    expect(screen.getByRole("combobox")).toHaveValue("1");
    expect(screen.getAllByRole("option").map((o) => o.textContent)).toEqual([
      "2025-2026",
      "2024-2025",
    ]);
  });

  it("navigates to the chosen season on the current path", async () => {
    render(
      <SeasonSelector
        seasons={[season(2, "2025-2026"), season(1, "2024-2025")]}
        selectedId={2}
      />,
    );
    await userEvent.selectOptions(screen.getByRole("combobox"), "1");
    expect(push).toHaveBeenCalledWith("/equipos/club-a?season=1");
  });
});
