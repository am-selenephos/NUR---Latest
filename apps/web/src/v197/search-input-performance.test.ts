import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { V197ApiClient } from "../bridge/v197ApiClient";
import { MAP_ROUTE, renderV197Map } from "../bridge/v197Map";
import { ORBIT_ROUTE, renderV197Orbit } from "../bridge/v197Orbit";
import { TIMELINE_ROUTE, renderV197Timeline } from "../bridge/v197Timeline";
import { V197_SEARCH_DEBOUNCE_MS } from "../bridge/v197SearchInput";

const EMPTY_GRAPH = {
  nodes: [],
  edges: [],
  system_regions: [],
  counts: {},
  suggested_changes: { candidate_edges: [], suggestions: [] },
  staleness: {},
  permissions: {},
  future_paths: [],
};

const EMPTY_ORBIT_FIELD = {
  people: [],
  groups: [],
  relationships: [],
  layout: [],
  thread_counts: {},
};

const EMPTY_TIMELINE_FLOW = {
  now: "2026-08-13T12:00:00.000Z",
  entries: [],
  unscheduled: [],
  phases: [],
  dependencies: [],
  counts: { total: 0, past: 0, present: 0, future: 0, unscheduled: 0 },
};

type RenderSurface = (
  doc: Document,
  route: string,
  api: V197ApiClient,
) => Promise<boolean>;

const SURFACES: Array<{
  name: string;
  route: string;
  rootId: string;
  searchSelector: string;
  render: RenderSurface;
}> = [
  {
    name: "Map",
    route: MAP_ROUTE,
    rootId: "nur-map-root",
    searchSelector: ".nur-map-search",
    render: renderV197Map,
  },
  {
    name: "Orbit",
    route: ORBIT_ROUTE,
    rootId: "nur-orbit-root",
    searchSelector: ".nur-orbit-search",
    render: renderV197Orbit,
  },
  {
    name: "Timeline",
    route: TIMELINE_ROUTE,
    rootId: "nur-timeline-root",
    searchSelector: ".nur-timeline-search",
    render: renderV197Timeline,
  },
];

function responseFor(input: RequestInfo | URL): Response {
  const pathname = new URL(String(input), "http://localhost").pathname;
  let body: unknown = {};
  if (pathname === "/api/v1/map/views") body = { default_view_id: "" };
  else if (pathname === "/api/v1/map") body = EMPTY_GRAPH;
  else if (pathname === "/api/v1/orbit-field") body = EMPTY_ORBIT_FIELD;
  else if (pathname === "/api/v1/orbit-threads") body = [];
  else if (pathname === "/api/v1/timeline/flow") body = EMPTY_TIMELINE_FLOW;
  return new Response(JSON.stringify(body), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

describe("V197 surface search input performance", () => {
  beforeEach(() => {
    document.body.innerHTML = '<section class="nur-viewport"></section>';
    document.body.className = "";
    vi.useFakeTimers();
    vi.stubGlobal("fetch", vi.fn(async input => responseFor(input)));
  });

  afterEach(() => {
    vi.clearAllTimers();
    vi.useRealTimers();
    vi.unstubAllGlobals();
    document.body.innerHTML = "";
    document.body.className = "";
  });

  it.each(SURFACES)(
    "$name settles rapid typing before repaint and preserves focus and selection",
    async ({ route, rootId, searchSelector, render }) => {
      const api = new V197ApiClient();
      expect(await render(document, route, api)).toBe(true);

      const rootBefore = document.getElementById(rootId);
      const searchBefore = document.querySelector<HTMLInputElement>(searchSelector);
      expect(rootBefore).not.toBeNull();
      expect(searchBefore).not.toBeNull();
      searchBefore?.focus();

      for (const character of "hello") {
        searchBefore!.value += character;
        searchBefore!.dispatchEvent(new Event("input", { bubbles: true }));
        vi.advanceTimersByTime(20);
      }
      searchBefore?.setSelectionRange(1, 4);

      expect(document.getElementById(rootId)).toBe(rootBefore);
      expect(document.querySelector(searchSelector)).toBe(searchBefore);

      await vi.advanceTimersByTimeAsync(V197_SEARCH_DEBOUNCE_MS + 1);

      const rootAfter = document.getElementById(rootId);
      const searchAfter = document.querySelector<HTMLInputElement>(searchSelector);
      expect(rootAfter).not.toBeNull();
      expect(rootAfter).not.toBe(rootBefore);
      expect(searchAfter).not.toBe(searchBefore);
      expect(searchAfter?.value).toBe("hello");
      expect(document.activeElement).toBe(searchAfter);
      expect(searchAfter?.selectionStart).toBe(1);
      expect(searchAfter?.selectionEnd).toBe(4);
    },
  );

  it.each(SURFACES)(
    "$name cancels a pending search commit when its route unmounts",
    async ({ route, rootId, searchSelector, render }) => {
      const api = new V197ApiClient();
      expect(await render(document, route, api)).toBe(true);
      const search = document.querySelector<HTMLInputElement>(searchSelector);
      expect(search).not.toBeNull();
      search!.value = "stale route";
      search!.dispatchEvent(new Event("input", { bubbles: true }));

      expect(await render(document, "/universe", api)).toBe(false);
      await vi.advanceTimersByTimeAsync(V197_SEARCH_DEBOUNCE_MS + 1);

      expect(document.getElementById(rootId)).toBeNull();
      expect(document.getElementById("nur-surface-host")).toBeNull();
    },
  );
});
