import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const proofRoot = process.env.NUR_TRACK_A_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/track-a" : "proof/track-a");

async function shot(page: Page, project: string, name: string): Promise<void> {
  await mkdir(proofRoot, { recursive: true });
  await page.screenshot({ path: join(proofRoot, `${project}-${name}.png`), fullPage: false, animations: "disabled" });
}

async function waitForUniverseStage(page: Page): Promise<void> {
  const stage = page.locator("#nur-universe-stage");
  await expect(stage).toHaveClass(/is-visible/, { timeout: 20_000 });
  await expect(stage).toBeVisible();
  await page.waitForTimeout(450);
}

async function openCanonicalUniverse(page: Page): Promise<void> {
  await page.goto("/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html", { waitUntil: "load" });
  await page.evaluate(() => {
    (window as unknown as { NURConsolidated: { enterUniverse: () => void } }).NURConsolidated.enterUniverse();
  });
  await waitForUniverseStage(page);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  await universe.locator("body").evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
}

async function mapGeometry(page: Page): Promise<Record<string, number>> {
  return page.frameLocator("#nur-universe-stage").locator(".universe-map-panel").evaluate(node => {
    const rect = node.getBoundingClientRect();
    return { x: rect.x, y: rect.y, width: rect.width, height: rect.height };
  });
}

test("Track A runs hydrated canonical V197 on real mobile engines", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name === "chromium-desktop", "Desktop mutation proof is in track-a-sellable.spec.ts.");
  test.setTimeout(90_000);

  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();

  await waitForUniverseStage(page);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 25_000 });
  await expect(page.locator("#root")).toHaveCount(0);
  await expect(universe.locator(".universe-system-node:visible")).toHaveCount(6);
  await expect(universe.locator(".universe-system-node b")).toHaveText([
    "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection",
  ]);
  await expect(universe.locator(".universe-nav-tabs button > span:not(.nur-exact-mini-host)")).toHaveText([
    "Universe", "Map", "Orbits", "Timeline", "Insights",
  ]);
  await expect(universe.locator(".mobile-tabs button")).toHaveText([
    "Today", "Talk", "Journal", "Plan", "Systems",
  ]);
  const mobileChrome = await universe.locator(".nur-topbar").evaluate(node => {
    const boundary = node.getBoundingClientRect();
    const deep = node.querySelector<HTMLElement>(".universe-deep")?.getBoundingClientRect();
    const nav = node.querySelector<HTMLElement>(".universe-nav-tabs");
    return {
      deepInside: Boolean(deep && deep.left >= boundary.left && deep.right <= boundary.right),
      navOverflow: nav ? getComputedStyle(nav).overflowX === "auto" : false,
      navCanScroll: nav ? nav.scrollWidth > nav.clientWidth : false,
    };
  });
  expect(mobileChrome).toEqual({ deepInside: true, navOverflow: true, navCanScroll: false });
  expect(await universe.locator(".universe-system-lane").textContent()).not.toContain("1,284");
  expect(await universe.locator("body").evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
  await expect(universe.locator("#toast")).not.toHaveClass(/show/, { timeout: 7_000 });
  await shot(page, testInfo.project.name, "hydrated-systems");

  await universe.locator('[data-world-tab="map"]').click();
  await expect(page).toHaveURL(/\/universe\/map$/);
  await expect(universe.locator(".universe-insight-panel")).toContainText("persisted Map nodes");
  await expect(universe.locator("#toast")).not.toHaveClass(/show/, { timeout: 7_000 });
  await universe.locator(".universe-map-panel").scrollIntoViewIfNeeded();
  await shot(page, testInfo.project.name, "real-map-lens");
});

test("Track A direct host preserves canonical V197 geometry on mobile engines", async ({ context, page }, testInfo) => {
  test.skip(testInfo.project.name === "chromium-desktop", "Desktop parity is already covered by the canonical parity suite.");
  test.setTimeout(90_000);

  const baseline = await context.newPage();
  await openCanonicalUniverse(baseline);
  const expected = await mapGeometry(baseline);

  await page.route("**/api/v1/auth/me", route => route.fulfill({ status: 401, contentType: "application/json", body: '{"detail":"Not authenticated"}' }));
  await page.goto("/systems", { waitUntil: "load" });
  await page.evaluate(() => {
    (window as unknown as { NURConsolidated: { enterUniverse: () => void } }).NURConsolidated.enterUniverse();
  });
  await waitForUniverseStage(page);
  const routed = page.frameLocator("#nur-universe-stage");
  await expect(routed.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  await routed.locator("body").evaluate(async () => {
    await document.fonts.ready;
    await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
  });
  const observed = await mapGeometry(page);
  for (const key of ["x", "y", "width", "height"] as const) {
    expect(Math.abs(observed[key] - expected[key]), `${key}: canonical=${expected[key]} routed=${observed[key]}`).toBeLessThanOrEqual(1.1);
  }
  await expect(page.locator("#root")).toHaveCount(0);
  await expect(routed.locator("link[href*='global.css']")).toHaveCount(0);
  await shot(page, testInfo.project.name, "canonical-geometry");
  await baseline.close();
});
