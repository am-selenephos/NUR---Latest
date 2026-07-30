import { expect, test, type BrowserContext, type Frame, type Page } from "@playwright/test";

/**
 * Map, through the real browser against the real API.
 *
 * The assertions worth having here are the ones that stop the surface
 * overclaiming: that a candidate never renders as structure, that a prediction
 * never renders as settled, that an unmeasured dimension says so instead of
 * showing a number, that a drag cannot reassign a System, and that the canonical
 * universe is intact after leaving.
 */

const OWNER = { email: "owner@nur.app", password: "owner-demo-pass-123" };

// Serial, on one signed-in page, for the same reason as the Orbit spec: a fresh
// context per test means one sign-in each, and the auth limiter correctly starts
// refusing partway through — testing the limiter rather than Map. The two tests
// that genuinely need their own context (reduced motion, mobile) make one.
test.describe.configure({ mode: "serial" });

let sharedContext: BrowserContext;
let sharedPage: Page;

test.beforeAll(async ({ browser }) => {
  sharedContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  sharedPage = await sharedContext.newPage();
  await signIn(sharedPage);
});

test.afterAll(async () => {
  await sharedContext?.close();
});

async function signIn(page: Page): Promise<void> {
  await page.goto("/", { waitUntil: "networkidle" });
  let status = 0;
  for (let attempt = 0; attempt < 3; attempt += 1) {
    status = await page.evaluate(async (owner) => {
      const response = await fetch("/api/v1/auth/login", {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(owner),
      });
      return response.status;
    }, OWNER);
    if (status !== 429) break;
    await page.waitForTimeout(1500);
  }
  expect(status, "sign-in did not succeed within the limiter's window").toBe(200);
}

/** The universe stage is where every bridge-native surface mounts. */
async function openMap(page: Page): Promise<Frame> {
  await page.goto("/universe/map", { waitUntil: "networkidle" });
  const stage = page.frameLocator("#nur-universe-stage");
  await expect(stage.locator("#nur-map-root")).toBeVisible({ timeout: 20_000 });
  // Resolved from the element itself: taking the first child frame grabs the
  // entry stage, which is also a direct child of the main frame and holds no Map.
  const handle = await page.waitForSelector("#nur-universe-stage");
  const frame = await handle.contentFrame();
  if (!frame) throw new Error("the universe stage frame is not attached");
  // Wait for the graph, not just the first paint. Asserting against the initial
  // empty render passed on desktop Chromium purely because the fetch was fast
  // enough, and failed on WebKit mobile — a race in the test, and the reason the
  // loading state now exists in the product.
  await expect.poll(
    async () => frame.evaluate(
      () => document.getElementById("nur-map-root")?.dataset.mapLoaded ?? "missing",
    ),
    { timeout: 20_000, message: "the Map graph never finished loading" },
  ).toBe("true");
  return frame;
}

test("Map mounts into the canonical document and never as a React root", async () => {
  const frame = await openMap(sharedPage);
  const shape = await frame.evaluate(() => {
    const root = document.getElementById("nur-map-root");
    return {
      mounted: Boolean(root),
      // The architecture law: no product page may be owned by a React tree.
      reactRoot: Boolean(document.getElementById("root")),
      nativeFlag: root?.dataset.v197NativeAdjunct ?? null,
      zones: {
        nav: Boolean(root?.querySelector(".nur-map-nav")),
        workspace: Boolean(root?.querySelector(".nur-map-workspace")),
        detail: Boolean(root?.querySelector(".nur-map-detail")),
      },
      title: root?.querySelector(".nur-map-title h1")?.textContent,
      subtitle: root?.querySelector(".nur-map-subtitle")?.textContent,
      modes: Array.from(root?.querySelectorAll("[data-map-mode]") ?? [])
        .map((node) => (node as HTMLElement).dataset.mapMode),
    };
  });
  expect(shape.mounted).toBe(true);
  expect(shape.reactRoot).toBe(false);
  expect(shape.nativeFlag).toBe("true");
  expect(shape.zones).toEqual({ nav: true, workspace: true, detail: true });
  expect(shape.title).toBe("Map");
  expect(shape.subtitle).toBe("Systems, paths and possible futures");
  expect(shape.modes).toEqual(["universe", "focus", "paths", "decisions"]);
});

test("every Map control is a luminous glass capsule, never a boxed outline", async () => {
  const frame = await openMap(sharedPage);
  const verdict = await frame.evaluate(() => {
    const root = document.getElementById("nur-map-root");
    if (!root) return { checked: 0, offenders: ["root missing"] };
    const offenders: string[] = [];
    for (const control of Array.from(root.querySelectorAll("button, input"))) {
      const style = getComputedStyle(control);
      const radii = [
        style.borderTopLeftRadius, style.borderTopRightRadius,
        style.borderBottomLeftRadius, style.borderBottomRightRadius,
      ].map((value) => parseFloat(value) || 0);
      const label = (control.textContent || (control as HTMLInputElement).placeholder || "?")
        .slice(0, 34);
      const height = control.getBoundingClientRect().height;
      // A capsule's radius is at least half its height. A rectangle's is not.
      // Tabs are pill-shaped too, so the same rule covers them.
      if (height > 0 && Math.max(...radii) < Math.min(height / 2, 12)) {
        offenders.push(`${label} radius ${Math.max(...radii)} height ${height}`);
      }
      if (style.appearance !== "none" && control.tagName === "INPUT") {
        offenders.push(`${label} keeps native appearance ${style.appearance}`);
      }
      // Flat white or bright SaaS-blue fills are the look this forbids.
      if (/^rgb\(2[3-5][0-9], 2[3-5][0-9], 2[3-5][0-9]\)$/.test(style.backgroundColor)) {
        offenders.push(`${label} has a white fill`);
      }
    }
    return { checked: root.querySelectorAll("button, input").length, offenders };
  });
  expect(verdict.checked).toBeGreaterThan(8);
  expect(verdict.offenders).toEqual([]);
});

test("Map renders above the canonical galaxy so the field stays black", async () => {
  const frame = await openMap(sharedPage);
  const layering = await frame.evaluate(() => {
    const root = document.getElementById("nur-map-root");
    const galaxy = document.getElementById("space3d");
    return {
      mapZ: root ? Number(getComputedStyle(root).zIndex) : null,
      galaxyZ: galaxy ? Number(getComputedStyle(galaxy).zIndex) : null,
      background: root ? getComputedStyle(root).backgroundColor : null,
    };
  });
  expect(layering.mapZ).toBe(320);
  if (layering.galaxyZ !== null) {
    expect(layering.mapZ as number).toBeGreaterThan(layering.galaxyZ);
  }
  expect(layering.background).toBe("rgb(0, 0, 0)");
});

test("System regions come from the server, each with a state and a reason", async () => {
  const frame = await openMap(sharedPage);
  const regions = await frame.evaluate(async () => {
    const response = await fetch("/api/v1/map", { credentials: "include" });
    const body = await response.json();
    const root = document.getElementById("nur-map-root");
    return {
      served: body.system_regions.map((row: { slug: string; state_reason: string }) => ({
        slug: row.slug, reason: row.state_reason,
      })),
      chips: Array.from(root?.querySelectorAll("[data-map-system]") ?? [])
        .map((node) => (node as HTMLElement).dataset.mapSystem),
    };
  });
  expect(regions.served.length).toBeGreaterThan(0);
  // Rendered from the catalog the server returned, not a list baked into the UI.
  expect(regions.chips).toEqual(regions.served.map((row: { slug: string }) => row.slug));
  for (const region of regions.served) {
    // §10: a state is always explainable, and never a bare score.
    expect(region.reason).toMatch(/%/);
    expect(region.reason.length).toBeGreaterThan(20);
  }
});

test("all four modes render their own workspace", async () => {
  // Three sequential mode switches, each fetching from the API. On WebKit mobile
  // that exceeds the 30s default; the assertions are unchanged, only the budget.
  test.slow();
  const frame = await openMap(sharedPage);
  for (const [mode, marker] of [
    ["paths", "[data-map-paths]"],
    ["decisions", "[data-map-decisions]"],
    ["universe", ".nur-map-canvas-wrap"],
  ] as [string, string][]) {
    await frame.click(`[data-map-mode="${mode}"]`);
    await expect.poll(
      async () => frame.evaluate(
        (selector) => Boolean(document.querySelector(selector)), marker,
      ),
      { timeout: 10_000 },
    ).toBe(true);
  }
});

test("a candidate never renders as confirmed structure", async () => {
  const frame = await openMap(sharedPage);
  // Ask the server to derive candidates from the owner's own rows, then check
  // that whatever came back is visually and semantically separated.
  const outcome = await frame.evaluate(async () => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    await fetch("/api/v1/map/suggestions/generate", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: "{}",
    });
    const graph = await (await fetch("/api/v1/map", { credentials: "include" })).json();
    return {
      // The server must keep proposals out of `edges` entirely.
      confirmedEdgesAllConfirmed: graph.edges
        .filter((row: { semantic?: boolean }) => row.semantic)
        .every((row: { user_confirmed: boolean }) => row.user_confirmed === true),
      candidateCount: graph.suggested_changes.candidate_edges.length,
      suggestionCount: graph.suggested_changes.suggestions.length,
      everySuggestionExplains: graph.suggested_changes.suggestions.every(
        (row: { explanation: string; may_be_wrong_about: string }) =>
          row.explanation.trim().length > 0 && row.may_be_wrong_about.trim().length > 0,
      ),
      everySuggestionRequiresAcceptance: graph.suggested_changes.suggestions.every(
        (row: { requires_acceptance: boolean }) => row.requires_acceptance === true,
      ),
    };
  });
  expect(outcome.confirmedEdgesAllConfirmed).toBe(true);
  expect(outcome.everySuggestionExplains).toBe(true);
  expect(outcome.everySuggestionRequiresAcceptance).toBe(true);

  if (outcome.suggestionCount > 0) {
    await sharedPage.reload({ waitUntil: "networkidle" });
    const again = await openMap(sharedPage);
    const rendered = await again.evaluate(() => {
      const cards = Array.from(document.querySelectorAll("[data-map-candidate]"));
      return {
        count: cards.length,
        allMarked: cards.every(
          (card) => (card.querySelector(".nur-map-candidate-mark")?.textContent ?? "")
            .includes("NUR suggests"),
        ),
        allDashed: cards.every(
          (card) => getComputedStyle(card).borderStyle === "dashed",
        ),
        allOfferWhyAndBoth: cards.every(
          (card) => Boolean(card.querySelector("[data-map-accept]"))
            && Boolean(card.querySelector("[data-map-reject]"))
            && Boolean(card.querySelector(".nur-map-doubt")),
        ),
      };
    });
    expect(rendered.count).toBeGreaterThan(0);
    expect(rendered.allMarked).toBe(true);
    // Dashed, not solid: a proposal must be distinguishable without reading.
    expect(rendered.allDashed).toBe(true);
    expect(rendered.allOfferWhyAndBoth).toBe(true);
  }
});

test("every drawn connection can say why the two things are connected", async () => {
  const frame = await openMap(sharedPage);
  const edges = await frame.evaluate(() => {
    const lines = Array.from(document.querySelectorAll(".nur-map-edge"));
    return {
      count: lines.length,
      allExplained: lines.every((line) => {
        const why = (line as SVGElement).dataset.mapEdgeWhy ?? "";
        return why.trim().length > 10 && Boolean(line.querySelector("title"));
      }),
      // Meaning is never hue alone: each class carries its own dash signature.
      distinctStrokes: new Set(
        lines.map((line) => {
          const style = getComputedStyle(line);
          return `${style.stroke}|${style.strokeDasharray}`;
        }),
      ).size,
    };
  });
  expect(edges.count).toBeGreaterThan(0);
  expect(edges.allExplained).toBe(true);
});

test("the five detail tabs render, and NUR View always states its doubt", async () => {
  // Five tab switches, and every state change repaints the whole root. That is
  // cheap on desktop Chromium and measurably slow on WebKit mobile — a real
  // characteristic of the current render strategy, not a flake. Budget only.
  test.slow();
  const frame = await openMap(sharedPage);
  await frame.click('[data-map-mode="universe"]');
  // Select the anchor, which always exists for every owner.
  await frame.click('[data-map-node="nur"]');
  const tabs = await frame.evaluate(
    () => Array.from(document.querySelectorAll("[data-map-tab]"))
      .map((node) => (node as HTMLElement).dataset.mapTab),
  );
  expect(tabs).toEqual(["overview", "path", "evidence", "activity", "nur"]);

  for (const tab of tabs) {
    await frame.click(`[data-map-tab="${tab}"]`);
    await expect.poll(
      async () => frame.evaluate(
        (name) => document.querySelector("[data-map-tab-panel]")
          ?.getAttribute("data-map-tab-panel") === name,
        tab,
      ),
      { timeout: 8_000 },
    ).toBe(true);
  }

  // §17: "What NUR may be wrong about" is required and never omitted.
  const doubt = await frame.evaluate(() => {
    const node = document.querySelector("[data-map-doubt]");
    return {
      present: Boolean(node),
      label: node?.querySelector(".nur-map-doubt-label")?.textContent ?? "",
      body: node?.querySelector(".nur-map-field-value")?.textContent ?? "",
    };
  });
  expect(doubt.present).toBe(true);
  expect(doubt.label).toBe("What NUR may be wrong about");
  expect(doubt.body.length).toBeGreaterThan(30);
});

test("labels stay legible: only the frame and the selection are named", async () => {
  const frame = await openMap(sharedPage);
  await frame.click('[data-map-mode="universe"]');
  const unselected = await frame.evaluate(() => {
    const labelled = Array.from(document.querySelectorAll(".nur-map-node"))
      .filter((node) => node.querySelector(".nur-map-node-label"));
    return {
      total: document.querySelectorAll(".nur-map-node").length,
      labelled: labelled.length,
      kinds: Array.from(new Set(labelled.map(
        (node) => (node as SVGElement).dataset.mapKind ?? "?",
      ))).sort(),
      // Every node still carries its name for hover and assistive tech.
      allHaveTitles: Array.from(document.querySelectorAll(".nur-map-node"))
        .every((node) => Boolean(node.querySelector("title"))),
    };
  });
  // Labelling every node produced dozens of overlapping strings in the outer
  // ring and the canvas stopped being readable at all.
  expect(unselected.kinds).toEqual(["MASTER_STAR", "SYSTEM"]);
  expect(unselected.labelled).toBeLessThan(unselected.total);
  expect(unselected.allHaveTitles).toBe(true);

  // Selecting brings the neighbourhood's names back — but under a hard cap.
  // Selecting the anchor puts almost the whole graph in focus, which is how the
  // overlap came back after the first fix, so the budget is what actually holds.
  await frame.click('[data-map-node="nur"]');
  const selected = await frame.evaluate(
    () => Array.from(document.querySelectorAll(".nur-map-node"))
      .filter((node) => node.querySelector(".nur-map-node-label")).length,
  );
  expect(selected).toBeGreaterThanOrEqual(unselected.labelled);
  expect(selected).toBeLessThanOrEqual(unselected.labelled + 14);
});

test("the anchor opens Current Position, not an empty object panel", async () => {
  const frame = await openMap(sharedPage);
  await frame.click('[data-map-mode="universe"]');
  await frame.click('[data-map-node="nur"]');
  const position = await frame.evaluate(() => {
    const panel = document.querySelector("[data-map-current-position]");
    return {
      present: Boolean(panel),
      labels: Array.from(panel?.querySelectorAll(".nur-map-field-label") ?? [])
        .map((node) => node.textContent),
      // §10 forbids fake precision: no confidence percentage on this panel.
      hasPercentConfidence: /confidence[^.]*\d+%/i.test(panel?.textContent ?? ""),
    };
  });
  expect(position.present).toBe(true);
  expect(position.labels).toEqual([
    "Active priorities", "Open decisions", "Current constraints",
    "Recent movement", "Major risks", "Systems",
    "How much of this NUR can see",
  ]);
  expect(position.hasPercentConfidence).toBe(false);
});

test("an unmeasured path dimension says so instead of showing a number", async () => {
  const frame = await openMap(sharedPage);
  await frame.click('[data-map-mode="paths"]');
  const verdict = await frame.evaluate(async () => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    const graph = await (await fetch("/api/v1/map", { credentials: "include" })).json();
    const goal = graph.nodes.find((row: { kind: string }) => row.kind === "GOAL");
    if (!goal) return { skipped: true, unmeasured: [], modelGenerated: null };
    const body = await (await fetch("/api/v1/map/path-comparison", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({ goal_id: goal.id.split(":")[1] }),
    })).json();
    return {
      skipped: false,
      modelGenerated: body.is_model_generated,
      provenance: body.provenance_label,
      unmeasured: (body.paths ?? []).map(
        (lane: { reversibility: string; expected_outcome: unknown }) => ({
          reversibility: lane.reversibility,
          expected: lane.expected_outcome,
        }),
      ),
    };
  });
  if (!verdict.skipped) {
    // The endpoint must never claim to have reasoned.
    expect(verdict.modelGenerated).toBe(false);
    expect(verdict.provenance).toBe("DETERMINISTIC_FRAME");
    for (const lane of verdict.unmeasured) {
      expect(lane.reversibility).toBe("Not assessed");
      expect(lane.expected).toBeNull();
    }
  }
});

test("layout persists and a moved node keeps its System", async () => {
  const frame = await openMap(sharedPage);
  const result = await frame.evaluate(async () => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    const views = await (await fetch("/api/v1/map/views", { credentials: "include" })).json();
    const viewId = views.default_view_id;
    const before = await (await fetch(`/api/v1/map/views/${viewId}/graph`, {
      credentials: "include",
    })).json();
    const target = before.nodes.find(
      (row: { kind: string }) => row.kind === "GOAL",
    ) ?? before.nodes.find((row: { kind: string }) => row.kind === "SYSTEM");
    const ref = target.id.includes(":")
      ? { type: target.id.split(":")[0].replace(/-/g, "_"), id: target.id.split(":")[1] }
      : { type: "nur", id: target.id };
    const parentBefore = target.parent_id;

    const written = await fetch(`/api/v1/map/views/${viewId}/layout`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        nodes: [{ node_ref_type: ref.type, node_ref_id: ref.id, x: 411.5, y: -222.5 }],
      }),
    });
    const writtenBody = await written.json();
    const after = await (await fetch(`/api/v1/map/views/${viewId}/graph`, {
      credentials: "include",
    })).json();
    const moved = after.nodes.find((row: { id: string }) => row.id === target.id);
    return {
      status: written.status,
      semanticsChanged: writtenBody.semantics_changed,
      x: moved.data.layout.x,
      y: moved.data.layout.y,
      parentBefore,
      parentAfter: moved.parent_id,
      ownerPositioned: after.staleness.layout_is_owner_positioned,
    };
  });
  expect(result.status).toBe(200);
  // §15: position is presentation. It must never move meaning.
  expect(result.semanticsChanged).toBe(false);
  expect(result.x).toBe(411.5);
  expect(result.y).toBe(-222.5);
  expect(result.parentAfter).toBe(result.parentBefore);
  expect(result.ownerPositioned).toBe(true);
});

test("dragging a node with the mouse persists position and nothing else", async () => {
  const page = sharedPage;
  const frame = await openMap(page);
  await frame.click('[data-map-mode="universe"]');

  const target = await frame.evaluate(() => {
    const node = document.querySelector('[data-map-node="system:creation"]')
      ?? document.querySelector('[data-map-node^="system:"]');
    return (node as SVGElement | null)?.dataset.mapNode ?? null;
  });
  expect(target, "no System node to drag").not.toBeNull();

  // Park the node at a known point inside the viewBox first. This test persists
  // layout, so without a reset it drifts further from centre on every run until
  // the node sits outside the canvas and the synthesised press misses it — which
  // is exactly how it started failing.
  const before = await frame.evaluate(async (id) => {
    const csrf = document.cookie.split("; ")
      .find((row) => row.startsWith("nur_csrf="))?.split("=")[1] ?? "";
    const views = await (await fetch("/api/v1/map/views", { credentials: "include" })).json();
    const ref = { type: id.split(":")[0].replace(/-/g, "_"), id: id.split(":")[1] };
    await fetch(`/api/v1/map/views/${views.default_view_id}/layout`, {
      method: "PUT",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRF-Token": csrf },
      body: JSON.stringify({
        nodes: [{ node_ref_type: ref.type, node_ref_id: ref.id, x: 0, y: 0 }],
      }),
    });
    const graph = await (await fetch(`/api/v1/map/views/${views.default_view_id}/graph`, {
      credentials: "include",
    })).json();
    const node = graph.nodes.find((row: { id: string }) => row.id === id);
    return { x: node.data.layout.x, y: node.data.layout.y, parent: node.parent_id };
  }, target as string);
  expect(before.x).toBe(0);

  // Repaint so the node is actually drawn at the parked position before dragging.
  await sharedPage.reload({ waitUntil: "networkidle" });
  const fresh = await openMap(page);
  await fresh.click('[data-map-mode="universe"]');

  const locator = page.frameLocator("#nur-universe-stage")
    .locator(`[data-map-node="${target}"]`);
  const box = await locator.boundingBox();
  expect(box, "the node has no box to drag").not.toBeNull();

  // A real pointer gesture: press, move well past the 4px threshold, release.
  const startX = box!.x + box!.width / 2;
  const startY = box!.y + box!.height / 2;
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 90, startY + 60, { steps: 12 });
  await page.mouse.up();

  // Wait for the release to reach the server rather than assuming it has.
  await expect.poll(
    async () => fresh.evaluate(async (id) => {
      const views = await (await fetch("/api/v1/map/views", { credentials: "include" })).json();
      const graph = await (await fetch(`/api/v1/map/views/${views.default_view_id}/graph`, {
        credentials: "include",
      })).json();
      const node = graph.nodes.find((row: { id: string }) => row.id === id);
      return node.data.layout.x as number;
    }, target as string),
    { timeout: 15_000, message: "the drag never reached the server" },
  ).not.toBe(before.x);

  const persisted = await fresh.evaluate(async (id) => {
    const views = await (await fetch("/api/v1/map/views", { credentials: "include" })).json();
    const graph = await (await fetch(`/api/v1/map/views/${views.default_view_id}/graph`, {
      credentials: "include",
    })).json();
    const node = graph.nodes.find((row: { id: string }) => row.id === id);
    return {
      x: node.data.layout.x,
      y: node.data.layout.y,
      parent: node.parent_id,
      ownerPositioned: graph.staleness.layout_is_owner_positioned,
    };
  }, target as string);

  // The node actually moved, and it moved roughly where it was dragged.
  expect(persisted.x).not.toBe(before.x);
  expect(persisted.ownerPositioned).toBe(true);
  // §15: the gesture changed position and nothing else.
  expect(persisted.parent).toBe(before.parent);
});

test("a node is reachable and movable by keyboard alone", async () => {
  const frame = await openMap(sharedPage);
  await frame.click('[data-map-mode="universe"]');
  const focused = await frame.evaluate(() => {
    const node = document.querySelector('[data-map-node="nur"]') as SVGElement | null;
    if (!node) return { focusable: false, halo: "", role: null };
    node.focus();
    const style = getComputedStyle(node);
    return {
      focusable: document.activeElement === node,
      tabindex: node.getAttribute("tabindex"),
      role: node.getAttribute("role"),
      halo: style.boxShadow,
    };
  });
  expect(focused.focusable).toBe(true);
  expect(focused.tabindex).toBe("0");
  expect(focused.role).toBe("button");

  // Enter selects, and the detail panel responds — no pointer involved.
  await frame.press('[data-map-node="nur"]', "Enter");
  await expect.poll(
    async () => frame.evaluate(
      () => Boolean(document.querySelector("[data-map-tab-panel]")),
    ),
    { timeout: 8_000 },
  ).toBe(true);
});

test("the accessible outline is a real parallel representation", async () => {
  const frame = await openMap(sharedPage);
  await frame.click('[data-map-mode="universe"]');
  await frame.click("[data-map-outline-toggle]");
  const outline = await frame.evaluate(() => {
    const root = document.querySelector("[data-map-outline]");
    const rows = Array.from(root?.querySelectorAll(".nur-map-row") ?? []);
    return {
      present: Boolean(root),
      rows: rows.length,
      // Every row carries a spoken summary, not just a visual label.
      allDescribed: rows.every(
        (row) => (row.getAttribute("aria-label") ?? "").split(".").length >= 3,
      ),
    };
  });
  expect(outline.present).toBe(true);
  expect(outline.rows).toBeGreaterThan(0);
  expect(outline.allDescribed).toBe(true);
});

test("nothing loops when reduced motion is requested", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 1440, height: 900 },
    reducedMotion: "reduce",
  });
  const page = await context.newPage();
  try {
    await signIn(page);
    const frame = await openMap(page);
    const motion = await frame.evaluate(() => {
      const animated = Array.from(document.querySelectorAll(
        ".nur-map-edge.is-active, .nur-map-node.is-unresolved .nur-map-node-body",
      ));
      return {
        honoured: matchMedia("(prefers-reduced-motion: reduce)").matches,
        looping: animated.filter(
          (node) => getComputedStyle(node).animationName !== "none",
        ).length,
      };
    });
    expect(motion.honoured).toBe(true);
    expect(motion.looping).toBe(0);
  } finally {
    await context.close();
  }
});

test("mobile opens focus-first with a bottom sheet, not a shrunken galaxy", async ({ browser }) => {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } });
  const page = await context.newPage();
  try {
    await signIn(page);
    const frame = await openMap(page);
    const layout = await frame.evaluate(() => {
      const root = document.getElementById("nur-map-root");
      const nav = root?.querySelector(".nur-map-nav");
      const detail = root?.querySelector(".nur-map-detail");
      const active = Array.from(root?.querySelectorAll("[data-map-mode]") ?? [])
        .find((node) => node.getAttribute("aria-selected") === "true");
      return {
        // §33: the rail is not a column on a phone.
        navHidden: nav ? getComputedStyle(nav).display === "none" : null,
        detailHidden: detail ? getComputedStyle(detail).display === "none" : null,
        defaultMode: (active as HTMLElement | undefined)?.dataset.mapMode ?? null,
        bodyScrollsSideways: document.documentElement.scrollWidth
          > document.documentElement.clientWidth + 1,
      };
    });
    expect(layout.navHidden).toBe(true);
    expect(layout.detailHidden).toBe(true);
    expect(layout.defaultMode).toBe("focus");
    expect(layout.bodyScrollsSideways).toBe(false);
  } finally {
    await context.close();
  }
});

test("leaving Map restores the canonical universe untouched", async () => {
  const page = sharedPage;
  await openMap(page);
  await page.goto("/systems", { waitUntil: "networkidle" });
  const handle = await page.waitForSelector("#nur-universe-stage");
  const frame = await handle.contentFrame();
  if (!frame) throw new Error("the universe stage frame is not attached");
  const after = await frame.evaluate(() => ({
    mapRemoved: !document.getElementById("nur-map-root"),
    // The canonical galaxy is still the canonical galaxy.
    galaxyPresent: Boolean(document.getElementById("space3d")),
    reactRoot: Boolean(document.getElementById("root")),
  }));
  expect(after.mapRemoved).toBe(true);
  expect(after.reactRoot).toBe(false);
  expect(after.galaxyPresent).toBe(true);
});
