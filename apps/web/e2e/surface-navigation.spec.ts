import { expect, test, type BrowserContext, type Frame, type Page } from "@playwright/test";

/**
 * Navigation between the bridge-native surfaces, through the canonical top nav.
 *
 * This file exists because of a defect that every other spec missed: each surface
 * spec navigated with `page.goto`, which is a full load and calls
 * `applyCurrentRoute` during boot. Clicking the canonical nav does not do that —
 * it calls `pushRoute`, which calls `window.history.pushState`, and **`pushState`
 * does not fire `popstate`**. The bridge listened for `popstate` alone, so every
 * in-app navigation changed the URL and rendered nothing: clicking Map, Orbits or
 * Timeline landed on the right address with the canonical Systems page still on
 * screen.
 *
 * Fixing that surfaced a second one. The surface chain in `applyCurrentRoute`
 * early-returns as soon as one surface claims the route, and each surface removes
 * its own root only when it is *called* with a non-matching route — so going from
 * Map to Orbits left `#nur-map-root` mounted underneath, two surfaces at once.
 *
 * Both are asserted here, on the real controls a person actually clicks.
 */

const OWNER = { email: "owner@nur.app", password: "owner-demo-pass-123" };

const SURFACE_ROOTS = ["nur-orbit-root", "nur-map-root", "nur-timeline-root", "nur-insights-root"];

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

async function stageFrame(page: Page): Promise<Frame> {
  const handle = await page.waitForSelector("#nur-universe-stage");
  const frame = await handle.contentFrame();
  if (!frame) throw new Error("the universe stage frame is not attached");
  return frame;
}

/** Click a canonical world tab the way a person does. */
async function clickWorldTab(page: Page, label: string): Promise<void> {
  const frame = await stageFrame(page);
  const found = await frame.evaluate((want) => {
    const button = Array.from(document.querySelectorAll("[data-world-tab]"))
      .find((node) => (node.textContent || "").trim().toUpperCase().includes(want));
    if (!button) return false;
    (button as HTMLElement).click();
    return true;
  }, label);
  expect(found, `no canonical world tab labelled ${label}`).toBe(true);
}

/** Which surface roots are mounted, and whether the host is claimed. */
async function mountState(page: Page): Promise<{
  mounted: string[]; host: boolean; railVisible: string | null;
  topbarVisible: string | null; starBrain: boolean;
}> {
  const frame = await stageFrame(page);
  return frame.evaluate((rootIds) => {
    const rail = document.querySelector(".nur-rail");
    const topbar = document.querySelector(".nur-topbar");
    return {
      mounted: rootIds.filter((id) => Boolean(document.getElementById(id))),
      host: Boolean(document.getElementById("nur-surface-host")),
      railVisible: rail ? getComputedStyle(rail).visibility : null,
      topbarVisible: topbar ? getComputedStyle(topbar).visibility : null,
      starBrain: (() => {
        const brain = document.getElementById("nur-brain-canvas");
        if (!brain) return false;
        const rect = brain.getBoundingClientRect();
        const style = getComputedStyle(brain);
        return rect.width > 1 && rect.height > 1
          && style.display !== "none" && style.visibility !== "hidden";
      })(),
    };
  }, SURFACE_ROOTS);
}

test("the canonical top nav carries a tab for every world", async () => {
  await sharedPage.goto("/systems", { waitUntil: "networkidle" });
  await sharedPage.waitForTimeout(2500);
  const frame = await stageFrame(sharedPage);
  const tabs = await frame.evaluate(
    () => Array.from(document.querySelectorAll("[data-world-tab]"))
      .map((node) => (node as HTMLElement).dataset.worldTab),
  );
  expect(tabs).toEqual(["universe", "map", "orbits", "timeline", "insights"]);
});

test("clicking a world tab actually renders its surface, not just its URL", async () => {
  test.slow();
  const page = sharedPage;
  await page.goto("/systems", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  for (const [label, route, root] of [
    ["MAP", "/universe/map", "nur-map-root"],
    ["ORBITS", "/universe/orbits", "nur-orbit-root"],
    ["TIMELINE", "/universe/timeline", "nur-timeline-root"],
    ["INSIGHTS", "/universe/insights", "nur-insights-root"],
  ] as [string, string, string][]) {
    await clickWorldTab(page, label);

    // The URL must change *and* the surface must mount. Before the fix only the
    // first of those happened.
    await expect.poll(
      async () => new URL(page.url()).pathname,
      { timeout: 15_000, message: `${label} did not navigate` },
    ).toBe(route);

    await expect.poll(
      async () => (await mountState(page)).mounted,
      { timeout: 20_000, message: `${label} navigated but rendered nothing` },
    ).toEqual([root]);

    // And the checkpoint shell survives the transition every time.
    const state = await mountState(page);
    expect(state.host).toBe(true);
    expect(state.railVisible).toBe("visible");
    expect(state.topbarVisible).toBe("visible");
  }
});

test("bouncing between surfaces never leaves two mounted at once", async () => {
  test.slow();
  const page = sharedPage;
  await page.goto("/systems", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  // Map → Orbits is the exact order that left `#nur-map-root` behind, because the
  // chain early-returns on Orbit and Map never runs its own cleanup branch.
  for (const [label, root] of [
    ["MAP", "nur-map-root"],
    ["ORBITS", "nur-orbit-root"],
    ["MAP", "nur-map-root"],
    ["TIMELINE", "nur-timeline-root"],
    ["ORBITS", "nur-orbit-root"],
  ] as [string, string][]) {
    await clickWorldTab(page, label);
    await expect.poll(
      async () => (await mountState(page)).mounted,
      { timeout: 20_000, message: `${label} left another surface mounted` },
    ).toEqual([root]);
  }
});

test("a pending search repaint cannot remount the surface after navigation", async () => {
  const page = sharedPage;
  await page.goto("/universe/map", { waitUntil: "networkidle" });
  await expect.poll(
    async () => (await mountState(page)).mounted,
    { timeout: 20_000 },
  ).toEqual(["nur-map-root"]);

  const frame = await stageFrame(page);
  const navigated = await frame.evaluate(() => {
    const search = document.querySelector<HTMLInputElement>(".nur-map-search");
    const orbit = Array.from(document.querySelectorAll<HTMLElement>("[data-world-tab]"))
      .find(node => (node.textContent || "").trim().toUpperCase().includes("ORBITS"));
    if (!search || !orbit) return false;
    search.value = "pending map query";
    search.dispatchEvent(new Event("input", { bubbles: true }));
    orbit.click();
    return true;
  });
  expect(navigated).toBe(true);

  await expect.poll(
    async () => (await mountState(page)).mounted,
    { timeout: 20_000 },
  ).toEqual(["nur-orbit-root"]);
  await page.waitForTimeout(300);
  expect((await mountState(page)).mounted).toEqual(["nur-orbit-root"]);
});

test("dedicated surfaces keep neutral-black glass instead of a blue panel wash", async () => {
  test.slow();
  const page = sharedPage;
  for (const [route, rootId, selectors] of [
    ["/universe/map", "nur-map-root", ["#nur-map-root", ".nur-map-pane", ".nur-map-canvas-wrap"]],
    ["/universe/orbits", "nur-orbit-root", ["#nur-orbit-root", ".nur-orbit-rail", ".nur-orbit-field-surface", ".nur-orbit-detail"]],
    ["/universe/timeline", "nur-timeline-root", ["#nur-timeline-root", ".nur-timeline-pane", ".nur-timeline-flow-wrap"]],
  ] as const) {
    await page.goto(route, { waitUntil: "networkidle" });
    await expect.poll(
      async () => (await mountState(page)).mounted,
      { timeout: 20_000, message: `${route} did not mount its dedicated surface` },
    ).toEqual([rootId]);
    const frame = await stageFrame(page);
    const materials = await frame.evaluate((panelSelectors) => panelSelectors.map(selector => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element) return { selector, missing: true, base: [] as number[], blueAlpha: 1 };
      const style = getComputedStyle(element);
      const base = style.backgroundColor.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
      const blueAlpha = Array.from(
        style.backgroundImage.matchAll(/rgba\(\s*([\d.]+),\s*([\d.]+),\s*([\d.]+),\s*([\d.]+)\s*\)/g),
        match => ({ r: Number(match[1]), g: Number(match[2]), b: Number(match[3]), a: Number(match[4]) }),
      ).filter(color => color.b > color.r + 20 && color.b > color.g)
        .reduce((maximum, color) => Math.max(maximum, color.a), 0);
      return { selector, missing: false, base, blueAlpha };
    }), selectors);

    for (const material of materials) {
      expect(material.missing, `${route} is missing ${material.selector}`).toBe(false);
      expect(material.base, `${route} ${material.selector} needs a neutral RGB base`).toHaveLength(3);
      expect(
        Math.max(...material.base) - Math.min(...material.base),
        `${route} ${material.selector} has a blue-tinted base`,
      ).toBeLessThanOrEqual(1);
      expect(
        material.blueAlpha,
        `${route} ${material.selector} has more than a subtle holographic blue film`,
      ).toBeLessThanOrEqual(0.02);
    }
  }
});

test("Insights owns its dedicated host and Universe restores the canonical page", async () => {
  test.slow();
  const page = sharedPage;
  await page.goto("/systems", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  await clickWorldTab(page, "MAP");
  await expect.poll(
    async () => (await mountState(page)).mounted,
    { timeout: 20_000 },
  ).toEqual(["nur-map-root"]);

  // Insights now owns a bounded interpretation surface rather than falling
  // through to the Systems summary lens or retaining Map underneath it.
  await clickWorldTab(page, "INSIGHTS");
  await expect.poll(
    async () => new URL(page.url()).pathname,
    { timeout: 15_000 },
  ).toBe("/universe/insights");
  await expect.poll(
    async () => {
      const state = await mountState(page);
      return { mounted: state.mounted, host: state.host };
    },
    { timeout: 20_000, message: "Insights did not claim exactly one surface" },
  ).toEqual({ mounted: ["nur-insights-root"], host: true });
  expect((await mountState(page)).starBrain).toBe(false);

  // Back to the universe: the canonical page and its star-brain return.
  await clickWorldTab(page, "UNIVERSE");
  await expect.poll(
    async () => {
      const state = await mountState(page);
      return {
        mounted: state.mounted,
        host: state.host,
        starBrain: state.starBrain,
        rail: state.railVisible,
      };
    },
    { timeout: 25_000, message: "the canonical universe did not come back" },
  ).toEqual({ mounted: [], host: false, starBrain: true, rail: "visible" });
});

test("browser back and forward still route correctly", async () => {
  test.slow();
  const page = sharedPage;
  await page.goto("/systems", { waitUntil: "networkidle" });
  await page.waitForTimeout(2500);

  await clickWorldTab(page, "MAP");
  await expect.poll(async () => (await mountState(page)).mounted, { timeout: 20_000 })
    .toEqual(["nur-map-root"]);
  await clickWorldTab(page, "TIMELINE");
  await expect.poll(async () => (await mountState(page)).mounted, { timeout: 20_000 })
    .toEqual(["nur-timeline-root"]);

  // `popstate` was always wired; this guards it while `pushState` gained its own
  // explicit apply, so the two paths cannot drift.
  await page.goBack({ waitUntil: "networkidle" });
  await expect.poll(
    async () => new URL(page.url()).pathname,
    { timeout: 15_000 },
  ).toBe("/universe/map");
  await expect.poll(
    async () => (await mountState(page)).mounted,
    { timeout: 20_000, message: "back did not re-render Map" },
  ).toEqual(["nur-map-root"]);

  await page.goForward({ waitUntil: "networkidle" });
  await expect.poll(
    async () => new URL(page.url()).pathname,
    { timeout: 15_000 },
  ).toBe("/universe/timeline");
  await expect.poll(
    async () => (await mountState(page)).mounted,
    { timeout: 20_000, message: "forward did not re-render Timeline" },
  ).toEqual(["nur-timeline-root"]);
});
