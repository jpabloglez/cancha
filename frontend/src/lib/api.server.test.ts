// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";

describe("api client on the server", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it("prefers the internal API URL for server-side fetches", async () => {
    vi.stubEnv("API_INTERNAL_BASE_URL", "http://backend:8000/api/v1");
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await import("@/lib/api");
    await apiFetch("/leagues/");
    expect(fetchMock.mock.calls[0][0]).toBe("http://backend:8000/api/v1/leagues/");
  });

  it("falls back to the public URL when no internal URL is set", async () => {
    delete process.env.API_INTERNAL_BASE_URL;
    vi.resetModules();
    const fetchMock = vi.fn().mockResolvedValue(new Response("{}"));
    vi.stubGlobal("fetch", fetchMock);
    const { apiFetch } = await import("@/lib/api");
    await apiFetch("/leagues/");
    expect(fetchMock.mock.calls[0][0]).toBe("http://api.test/api/v1/leagues/");
  });
});
