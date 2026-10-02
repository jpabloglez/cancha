import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { MediaImage } from "@/components/MediaImage";
import type { MediaAsset } from "@/types/api";

const asset = (url: string | null): MediaAsset => ({
  url,
  attribution: "FEB.es",
  license: "free",
});

describe("MediaImage", () => {
  it("prefixes root-relative media paths with the backend origin", () => {
    render(<MediaImage asset={asset("/media/logos/a.png")} alt="Club A" initials="CA" />);
    const img = screen.getByAltText("Club A");
    expect(img).toHaveAttribute("src", "http://api.test/media/logos/a.png");
    expect(img).toHaveAttribute("title", "FEB.es");
  });

  it("uses absolute URLs as they are", () => {
    render(<MediaImage asset={asset("https://cdn.test/a.png")} alt="Club A" initials="CA" />);
    expect(screen.getByAltText("Club A")).toHaveAttribute("src", "https://cdn.test/a.png");
  });

  it.each([null, asset(null)])("shows initials when there is no usable asset (%#)", (a) => {
    render(<MediaImage asset={a} alt="Club A" initials="CA" color="#112233" />);
    const fallback = screen.getByLabelText("Club A");
    expect(fallback).toHaveTextContent("CA");
    expect(fallback).toHaveStyle({ backgroundColor: "#112233" });
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });
});
