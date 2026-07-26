/**
 * The deep star field must exist behind the canonical rig on both surfaces,
 * carry no frame loop, and add no canvas layer.
 */
import { expect, test, type Page } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import path from "node:path";
const OUT = path.resolve(process.cwd(), "../../proof/v8-stars");

async function signIn(page: Page) {
  const e = page.frameLocator("#nur-entry-stage");
  await e.locator("body").evaluate(() => (window as any).nurShowFront?.());
  await e.locator("#f4-signin").click();
  await e.locator("#f4-signin-email").fill("owner@nur.app");
  await e.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await e.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25000 });
}

const probe = () => {
  const field = document.getElementById("nur-deep-starfield");
  const rig = document.getElementById("space3d");
  const host = document.getElementById("front-nur-star");
  // The bitmaps live on the plane children, not the container: each `<i>` is one
  // parallax plane carrying its own rasterised sky.
  const planes = field ? Array.from(field.querySelectorAll("i")) : [];
  const bg = planes.length ? getComputedStyle(planes[0] as Element).backgroundImage : "";
  return {
    fieldPresent: Boolean(field),
    fieldIsBitmap: bg.startsWith("url(") && bg.includes("data:image"),
    planeCount: planes.length,
    planesAnimated: planes.every(pl => getComputedStyle(pl as Element).animationName.includes("nurField")),
    fieldTag: field?.tagName ?? null,
    fieldZ: field ? Number(getComputedStyle(field).zIndex) : null,
    rigZ: rig ? Number(getComputedStyle(rig).zIndex) : null,
    brainPoints: Number(host?.dataset.nurPointCount ?? 0),
    dust: Number(host?.dataset.nurDustCount ?? 0),
    canvases: document.querySelectorAll("canvas").length,
  };
};

test("deep field sits behind the rig on Entry and Universe", async ({ page }) => {
  test.setTimeout(240000);
  await mkdir(OUT, { recursive: true });
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.waitForTimeout(1500);
  await page.frameLocator("#nur-entry-stage").locator("body").evaluate(() => (window as any).nurShowFront?.());
  await page.waitForTimeout(3000);
  const entry = await page.frameLocator("#nur-entry-stage").locator("body").evaluate(probe);
  console.log("ENTRY " + JSON.stringify(entry));
  await page.screenshot({ path: path.join(OUT, "entry-final.png") });

  await signIn(page);
  await page.goto("/systems");
  await page.waitForTimeout(3000);
  const systems = await page.frameLocator("#nur-universe-stage").locator("body").evaluate(probe);
  console.log("SYSTEMS " + JSON.stringify(systems));
  await page.screenshot({ path: path.join(OUT, "systems-final.png") });

  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, "systems-mobile.png") });

  for (const surface of [entry, systems]) {
    expect(surface.fieldPresent).toBe(true);
    // A div carrying a bitmap, never an extra canvas layer.
    expect(surface.fieldTag).toBe("DIV");
    expect(surface.fieldIsBitmap).toBe(true);
    expect(surface.fieldZ).toBeLessThan(surface.rigZ ?? 0);
    // Entry brain enlarged 40%: 1490 -> 2086 points, dust 430 -> 602.
    expect(surface.brainPoints).toBeGreaterThan(2000);
    expect(surface.dust).toBe(602);
    // Three parallax planes, each drifting and sparkling on the compositor.
    expect(surface.planeCount).toBe(3);
    expect(surface.planesAnimated).toBe(true);
  }
  expect(errors).toEqual([]);
});
