import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  auditV197Viewport,
  overlappingV197Pairs,
  settleV197Layout,
  visibleV197Rects,
  v197CenterDelta,
} from "./helpers/v197Geometry";
import { installNurMocks } from "./helpers/nurMocks";

type WebkitProject = "webkit-mobile" | "webkit-tablet" | "webkit-desktop";
type RequiredViewport = { width: number; height: number };

const WEBKIT_VIEWPORTS: Record<WebkitProject, readonly RequiredViewport[]> = {
  "webkit-mobile": [
    { width: 360, height: 800 },
    { width: 390, height: 844 },
    { width: 430, height: 932 },
    { width: 844, height: 390 },
  ],
  "webkit-tablet": [
    { width: 768, height: 1024 },
    { width: 1024, height: 768 },
  ],
  "webkit-desktop": [
    { width: 1280, height: 720 },
    { width: 1366, height: 768 },
    { width: 1440, height: 900 },
    { width: 1920, height: 1080 },
    { width: 2560, height: 1080 },
    { width: 2560, height: 1440 },
  ],
};

async function authenticate(page: Page): Promise<void> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "responsive-webkit-isolated-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "responsive-webkit-isolated-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
}

async function canvasSignal(canvas: Locator): Promise<{ lit: number; checksum: number }> {
  return canvas.evaluate((element: HTMLCanvasElement) => {
    const context = element.getContext("2d");
    if (!context || element.width < 2 || element.height < 2) return { lit: 0, checksum: 0 };
    const pixels = context.getImageData(0, 0, element.width, element.height).data;
    const stride = Math.max(4, Math.floor(pixels.length / 28_000 / 4) * 4);
    let lit = 0;
    let checksum = 0;
    for (let index = 0; index < pixels.length; index += stride) {
      const r = pixels[index] ?? 0;
      const g = pixels[index + 1] ?? 0;
      const b = pixels[index + 2] ?? 0;
      const a = pixels[index + 3] ?? 0;
      if (r + g + b > 120 && a > 20) lit += 1;
      checksum = (checksum + r * 3 + g * 5 + b * 7 + a * 11) % 2_147_483_647;
    }
    return { lit, checksum };
  });
}

async function assertIsolatedViewport(
  page: Page,
  viewport: RequiredViewport,
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

async function assertReducedMotionGalaxy(page: Page): Promise<void> {
  await authenticate(page);
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/today", { waitUntil: "load" });
  const frame = page.frameLocator("#nur-universe-stage");
  await expect(frame.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  const galaxy = frame.locator("#space3d");
  const galaxyPresentation = await galaxy.evaluate(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      display: style.display,
      visibility: style.visibility,
      opacity: style.opacity,
      width: rect.width,
      height: rect.height,
    };
  });
  expect(galaxyPresentation, JSON.stringify(galaxyPresentation)).toMatchObject({
    display: "block",
    visibility: "visible",
  });
  expect(galaxyPresentation.width).toBeGreaterThan(0);
  expect(galaxyPresentation.height).toBeGreaterThan(0);
  await expect.poll(async () => (await canvasSignal(galaxy)).lit).toBeGreaterThan(110);
  const firstGalaxyFrame = await canvasSignal(galaxy);
  await page.waitForTimeout(420);
  const secondGalaxyFrame = await canvasSignal(galaxy);
  expect(secondGalaxyFrame.lit).toBeGreaterThan(110);
  expect(secondGalaxyFrame.checksum).toBe(firstGalaxyFrame.checksum);

  const result = await frame.locator("body").evaluate(() => {
    const control = document.querySelector<HTMLElement>(".clean-nav-button");
    const brain = document.querySelector<HTMLElement>("#front-nur-star");
    const style = control ? getComputedStyle(control) : null;
    return {
      points: Number(brain?.dataset.nurPointCount),
      animationDuration: style?.animationDuration,
      transitionDuration: style?.transitionDuration,
      sparkfield: document.querySelectorAll("#v197-sparkfield").length,
    };
  });
  expect([1640, 2540]).toContain(result.points);
  expect(Number.parseFloat(result.animationDuration ?? "1")).toBeLessThanOrEqual(.00001);
  expect(Number.parseFloat(result.transitionDuration ?? "1")).toBeLessThanOrEqual(.00001);
  expect(result.sparkfield).toBe(0);
}

for (const project of Object.keys(WEBKIT_VIEWPORTS) as WebkitProject[]) {
  for (const viewport of WEBKIT_VIEWPORTS[project]) {
    test(`${project} isolated viewport ${viewport.width}x${viewport.height} preserves geometry contracts`, async ({ page }, testInfo) => {
      test.skip(testInfo.project.name !== project, `Runs only in the ${project} Safari/WebKit context.`);
      test.setTimeout(45_000);
      await assertIsolatedViewport(page, viewport, testInfo);
    });
  }
}

test("webkit-desktop reduced motion preserves the exact galaxy contract", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "webkit-desktop", "Runs only in the Desktop Safari/WebKit context.");
  test.setTimeout(45_000);
  await assertReducedMotionGalaxy(page);
});
