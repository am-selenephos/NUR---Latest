import { afterEach, describe, expect, it, vi } from "vitest";

import { V197ApiClient, V197ApiError, type V197Session } from "./v197ApiClient";

function response(status: number, body: unknown): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    text: async () => typeof body === "string" ? body : JSON.stringify(body),
  } as Response;
}

const created: V197Session = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@nur.app",
  profile: { chosen_name: "Owner", locale: "en", writing_preference: "default" },
  orbit: { id: "22222222-2222-2222-2222-222222222222", title: "Private Orbit", kind: "PERSONAL", status: "ACTIVE" },
};

describe("V197 presentation auth recovery", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it("turns a hung API request into a twelve-second diagnostic", async () => {
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn((_url: string, init?: RequestInit) => new Promise((_resolve, reject) => {
      init?.signal?.addEventListener("abort", () => reject(new DOMException("Aborted", "AbortError")), { once: true });
    })));
    const assertion = expect(new V197ApiClient().get("/auth/me")).rejects.toMatchObject({
      status: 0,
      message: "NUR API did not respond within 12 seconds. Check API readiness.",
    });
    await vi.advanceTimersByTimeAsync(12_000);
    await assertion;
  });

  it("does not treat malformed API output as a successful identity", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(200, "<html>not JSON</html>")));
    await expect(new V197ApiClient().get("/auth/me")).rejects.toEqual(
      new V197ApiError("NUR API returned an invalid response for /auth/me.", 200),
    );
  });

  it("propagates non-401 session failures instead of inventing anonymity", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(response(503, { detail: "database not ready" })));
    await expect(new V197ApiClient().session()).rejects.toMatchObject({ status: 503, message: "database not ready" });
  });

  it("fails closed when a signed-in owner snapshot cannot load required state", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("/api/v1/universe/live")) {
        return Promise.resolve(response(503, { detail: "owner ledger unavailable" }));
      }
      return Promise.resolve(response(200, {}));
    }));

    await expect(new V197ApiClient().snapshot(created)).rejects.toThrow(
      "NUR could not load the signed-in owner state from /universe/live. owner ledger unavailable",
    );
  });

  it("verifies that signup created the active browser session", async () => {
    const fetchMock = vi.fn()
      .mockResolvedValueOnce(response(201, created))
      .mockResolvedValueOnce(response(200, created));
    vi.stubGlobal("fetch", fetchMock);
    await expect(new V197ApiClient().register({
      chosen_name: "Owner", email: "owner@nur.app", password: "strong-passphrase", consent: true,
    })).resolves.toEqual(created);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(String(fetchMock.mock.calls[1][0])).toContain("/api/v1/auth/me");
  });

  it("blocks signup navigation when the browser session belongs to another identity", async () => {
    const other = { ...created, id: "33333333-3333-3333-3333-333333333333" };
    vi.stubGlobal("fetch", vi.fn()
      .mockResolvedValueOnce(response(201, created))
      .mockResolvedValueOnce(response(200, other)));
    await expect(new V197ApiClient().register({
      chosen_name: "Owner", email: "owner@nur.app", password: "strong-passphrase", consent: true,
    })).rejects.toMatchObject({ status: 409 });
  });
});
