import { describe, expect, it } from "vitest";

import robots from "@/app/robots";

describe("robots", () => {
  it("allows crawling and points at the sitemap on the site URL", () => {
    expect(robots()).toEqual({
      rules: { userAgent: "*", allow: "/" },
      sitemap: "https://site.test/sitemap.xml",
    });
  });
});
