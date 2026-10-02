import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { PositionBadge } from "@/components/PositionBadge";

describe("PositionBadge", () => {
  it("renders nothing without a position", () => {
    const { container } = render(<PositionBadge position={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows the Spanish label by default and the code when short", () => {
    const { rerender } = render(<PositionBadge position="PF" />);
    expect(screen.getByText("Ala-pívot")).toBeInTheDocument();
    rerender(<PositionBadge position="PF" short />);
    expect(screen.getByText("PF")).toBeInTheDocument();
  });

  it("falls back to the raw value for an unknown position", () => {
    render(<PositionBadge position="XX" />);
    expect(screen.getByText("XX")).toBeInTheDocument();
  });
});
