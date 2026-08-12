import { describe, expect, it } from "vitest";

import {
  routeForPage,
  routeForWorldFocus,
  routeForWorldTab,
} from "../bridge/v197Events";

describe("V197 navigation route ownership", () => {
  it("keeps canonical page routes stable", () => {
    expect(routeForPage("today")).toBe("/today");
    expect(routeForPage("systems")).toBe("/systems");
    expect(routeForPage("missing")).toBeNull();
  });

  it("separates the Insights world lens from Candidate Insights", () => {
    expect(routeForWorldTab("insights")).toBe("/universe/insights");
    expect(routeForWorldFocus("insights")).toBe("/universe/insights/candidates");
  });

  it("keeps bridge-native world tabs on their canonical routes", () => {
    expect(routeForWorldTab("map")).toBe("/universe/map");
    expect(routeForWorldTab("orbits")).toBe("/universe/orbits");
    expect(routeForWorldTab("timeline")).toBe("/universe/timeline");
    expect(routeForWorldTab("missing")).toBeNull();
  });
});
