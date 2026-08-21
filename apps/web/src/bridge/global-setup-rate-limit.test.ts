import { describe, expect, it } from "vitest";

import { rateLimitPattern } from "../../e2e/global-setup";

describe("Playwright rate-limit cleanup scope", () => {
  it("targets the unnamespaced production-shaped limiter keys", () => {
    expect(rateLimitPattern(undefined)).toBe("rl:*");
    expect(rateLimitPattern(" ")).toBe("rl:*");
  });

  it("targets only this run's namespaced limiter keys", () => {
    expect(rateLimitPattern("nurclosure")).toBe("nurclosure:rl:*");
    expect(rateLimitPattern("nurtest:abc123:")).toBe("nurtest:abc123:rl:*");
  });
});
