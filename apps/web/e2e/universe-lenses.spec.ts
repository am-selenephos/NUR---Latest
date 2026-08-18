import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const proofDir = process.env.NUR_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/screenshots" : "proof/screenshots");

test.use({ serviceWorkers: "block" });

function proofPath(name: string) {
  const path = join(proofDir, name);
  mkdirSync(dirname(path), { recursive: true });
  return path;
}

async function authenticate(page: Page): Promise<FrameLocator> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "lens-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "lens-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  return page.frameLocator("#nur-universe-stage");
}

async function visibleBox(label: string, locator: Locator) {
  await expect(locator, label).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} has a DOM box`).not.toBeNull();
  return box!;
}

async function assertNoHorizontalOverflow(frame: FrameLocator) {
  const widths = await frame.locator("html").evaluate(element => ({
    scroll: element.scrollWidth,
    client: element.clientWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
}

test("Universe topbar routes to each dedicated canonical surface", async ({ page }) => {
  const frame = await authenticate(page);
  await page.goto("/universe");
  await expect(frame.locator("#page-systems")).toBeVisible();

  for (const lens of [
    { label: "Map", route: "/universe/map", focus: "map", root: "#nur-map-root" },
    { label: "Orbits", route: "/universe/orbits", focus: "orbits", root: "#nur-orbit-root" },
    { label: "Timeline", route: "/universe/timeline", focus: "timeline", root: "#nur-timeline-root" },
    { label: "Insights", route: "/universe/insights", focus: "insights", root: "#nur-insights-root" },
  ] as const) {
    await frame.getByRole("tab", { name: lens.label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${lens.route}$`));
    await expect(frame.locator("body")).toHaveAttribute("data-nur-world-focus", lens.focus);
    await expect(frame.locator(lens.root)).toBeVisible({ timeout: 20_000 });
    await expect(frame.locator(lens.root)).toHaveAttribute("data-v197-native-adjunct", "true");
  }

});

test("dedicated Map controls breathe at 1280 without escaping the canonical host", async ({ page }) => {
  const frame = await authenticate(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/universe/map");

  const root = frame.locator("#nur-map-root");
  await expect(root).toBeVisible({ timeout: 20_000 });
  await expect(root).toHaveAttribute("data-map-loaded", "true");
  const rootBox = await visibleBox("Map root", root);
  const title = await visibleBox("Map title", root.locator(".nur-map-title"));
  const search = await visibleBox("Map search", root.locator(".nur-map-search"));
  const workspace = await visibleBox("Map workspace", root.locator(".nur-map-workspace"));
  for (const [label, box] of [["title", title], ["search", search], ["workspace", workspace]] as const) {
    expect(box.x, `${label} left edge`).toBeGreaterThanOrEqual(rootBox.x - 1);
    expect(box.x + box.width, `${label} right edge`).toBeLessThanOrEqual(rootBox.x + rootBox.width + 1);
  }
  await expect(root.getByRole("tab", { name: "Universe", exact: true })).toHaveAttribute("aria-selected", "true");
  await assertNoHorizontalOverflow(frame);

  await page.screenshot({ path: proofPath("map-1280-control-breathing.png"), fullPage: false });
  await root.getByRole("tab", { name: "Focus", exact: true }).click();
  await expect(root.getByRole("tab", { name: "Focus", exact: true })).toHaveAttribute("aria-selected", "true");
});

test("timeline and insights expose persisted truth while retired world routes return to Systems", async ({ page }) => {
  const frame = await authenticate(page);

  await page.goto("/universe/timeline");
  const timeline = frame.locator("#nur-timeline-root");
  await expect(timeline).toBeVisible({ timeout: 20_000 });
  await expect(timeline).toHaveAttribute("data-timeline-loaded", "true");
  await expect(timeline).toContainText("The owner returned a visible outcome.");

  await page.goto("/universe/research");
  await expect(frame.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", "system");

  await page.goto("/universe/web-signals");
  await expect(frame.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", "system");

  await page.goto("/universe/insights");
  const insights = frame.locator("#nur-insights-root");
  await expect(insights).toContainText(
    "Outcome evidence should strengthen planning patterns only after persisted results.",
  );
  await expect(insights).toHaveAttribute("data-insights-loaded", "true");
  await expect(insights).toHaveAttribute("data-nur-brain-surface", "none");
  await expect(frame.locator("#nur-brain-canvas")).toBeHidden();
});

test("mobile map first viewport is usable, not clipped", async ({ page }) => {
  const frame = await authenticate(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await page.goto("/universe/map");

  const root = frame.locator("#nur-map-root");
  await expect(root).toBeVisible({ timeout: 20_000 });
  await expect(root).toHaveAttribute("data-map-loaded", "true");
  await expect(root.locator(".nur-map-title")).toBeVisible();
  await expect(root.locator(".nur-map-workspace")).toBeVisible();
  await expect(root.locator(".nur-map-nav")).toBeHidden();
  await expect(root.locator(".nur-map-detail")).toBeHidden();
  await expect(root.getByRole("tab", { name: "Focus", exact: true })).toHaveAttribute("aria-selected", "true");
  await assertNoHorizontalOverflow(frame);
  await page.screenshot({ path: proofPath("map-mobile-393-clean.png"), fullPage: false });
});
