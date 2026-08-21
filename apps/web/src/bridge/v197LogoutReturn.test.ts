import { describe, expect, it } from "vitest";

import {
  consumeImmediateLogoutReturn,
  markImmediateLogoutReturn,
} from "./v197LogoutReturn";

function storage(): Pick<Storage, "getItem" | "setItem" | "removeItem"> {
  const values = new Map<string, string>();
  return {
    getItem: key => values.get(key) ?? null,
    setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key),
  };
}

describe("canonical Entry logout return", () => {
  it("consumes the immediate-return marker exactly once", () => {
    const session = storage();
    markImmediateLogoutReturn(session);

    expect(consumeImmediateLogoutReturn(session)).toBe(true);
    expect(consumeImmediateLogoutReturn(session)).toBe(false);
  });
});
