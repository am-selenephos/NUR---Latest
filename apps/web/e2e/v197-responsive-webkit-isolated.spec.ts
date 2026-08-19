import { expect, test, type Page } from "@playwright/test";

import {
  auditV197Viewport,
  overlappingV197Pairs,
  settleV197Layout,
  V197_REQUIRED_VIEWPORTS,
  visibleV197Rects,
  v197CenterDelta,
} from "./helpers/v197Geometry";
import { installNurMocks } from "./helpers/nurMocks";

async function authenticate(page: Page): Promise<void> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "responsive-webkit-isolated-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "responsive-webkit-isolated-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
}

async function assertIsolatedViewport(
  page: Page,
  viewport: (typeof V197_REQUIRED_VIEWPORTS)[number],
  testInfo: { outputPath: (path: string) => string },
): Promise<void> {
  await authenticate(page);
  await page.setViewportSize(viewport);
  await page.goto("/systems", { waitUntil: "load" });
  const frame = page.frameLocator("#nur-universe-stage");
  const body = frame.locator("body");
  await expect(frame.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  await settleV197Layout(body);

  const audit = await auditV197Viewport(body);
  expect(audit.documentWidth).toBeLessThanOrEqual(audit.viewportWidth + 1);
  expect(audit.escapedControls).toEqual([]);
  expect(audit.undersizedTouchTargets).toEqual([]);

  const nodeRects = await visibleV197Rects(body, ".universe-system-node");
  const topbarGroups = await visibleV197Rects(
    body,
    ".nur-topbar > .universe-top-left, .nur-topbar > .universe-top-tools",
  );
  const mapStacking = await body.evaluate(() => {
    const brain = document.querySelector<HTMLElement>(".universe-master-star");
    const nodes = Array.from(document.querySelectorAll<HTMLElement>(".universe-system-node"));
    return {
      brain: Number.parseInt(getComputedStyle(brain!).zIndex, 10),
      nodes: nodes.map(node => Number.parseInt(getComputedStyle(node).zIndex, 10)),
    };
  });
  expect(overlappingV197Pairs(nodeRects)).toEqual([]);
  expect(overlappingV197Pairs(topbarGroups)).toEqual([]);
  mapStacking.nodes.forEach(zIndex => expect(zIndex).toBeGreaterThan(mapStacking.brain));

  const centerDelta = await v197CenterDelta(
    body,
    ".universe-map-title",
    ".universe-master-star",
  );
  expect(centerDelta).toBeLessThanOrEqual(1);

  if (viewport.width === 390 && viewport.height === 844) {
    await frame.locator("#page-systems .universe-map-panel").screenshot({
      path: testInfo.outputPath("systems-node-crystal-390x844.png"),
    });
  }
}

for (const viewport of V197_REQUIRED_VIEWPORTS) {
  test(`isolated WebKit viewport ${viewport.width}x${viewport.height} preserves geometry contracts`, async ({ page }, testInfo) => {
    test.setTimeout(45_000);
    await assertIsolatedViewport(page, viewport, testInfo);
  });
}
