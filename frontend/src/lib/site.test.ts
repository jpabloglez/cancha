import { afterEach, describe, expect, it, vi } from "vitest";

describe("site constants", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("defaults the GitHub URL to the project repository", async () => {
    vi.stubEnv("NEXT_PUBLIC_GITHUB_URL", "");
    vi.resetModules();
    const { GITHUB_URL } = await import("@/lib/site");
    // An empty string is a set value for `??`, so only unset falls back.
    expect(GITHUB_URL).toBe("");
    vi.unstubAllEnvs();
    delete process.env.NEXT_PUBLIC_GITHUB_URL;
    vi.resetModules();
    const fresh = await import("@/lib/site");
    expect(fresh.GITHUB_URL).toBe("https://github.com/jpabloglez/cancha");
  });

  it("reads the contact email from the environment", async () => {
    vi.stubEnv("NEXT_PUBLIC_CONTACT_EMAIL", "derechos@example.org");
    vi.resetModules();
    const { CONTACT_EMAIL } = await import("@/lib/site");
    expect(CONTACT_EMAIL).toBe("derechos@example.org");
  });
});
