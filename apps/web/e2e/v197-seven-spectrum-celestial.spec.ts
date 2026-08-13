import { expect, test, type Locator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const SPECTRUM = ["red", "orange", "yellow", "green", "blue", "indigo", "violet"] as const;

async function canvasSignal(canvas: Locator): Promise<{ lit: number; alpha: number; checksum: number }> {
  return canvas.evaluate((element: HTMLCanvasElement) => {
    const context = element.getContext("2d");
    if (!context || element.width < 2 || element.height < 2) return { lit: 0, alpha: 0, checksum: 0 };
    const pixels = context.getImageData(0, 0, element.width, element.height).data;
    const stride = Math.max(4, Math.floor(pixels.length / 32_000 / 4) * 4);
    let lit = 0;
    let alpha = 0;
    let checksum = 0;
    for (let index = 0; index < pixels.length; index += stride) {
      const red = pixels[index] ?? 0;
      const green = pixels[index + 1] ?? 0;
      const blue = pixels[index + 2] ?? 0;
      const opacity = pixels[index + 3] ?? 0;
      if (opacity > 8) alpha += 1;
      if (red + green + blue > 120 && opacity > 20) lit += 1;
      checksum = (checksum + red * 3 + green * 5 + blue * 7 + opacity * 11) % 2_147_483_647;
    }
    return { lit, alpha, checksum };
  });
}

async function proveMovingCanvas(canvas: Locator, minimumLit: number): Promise<void> {
  await expect.poll(async () => (await canvasSignal(canvas)).lit, { timeout: 10_000 })
    .toBeGreaterThan(minimumLit);
  const first = await canvasSignal(canvas);
  await expect.poll(async () => (await canvasSignal(canvas)).checksum, { timeout: 5_000 })
    .not.toBe(first.checksum);
}

async function proveSevenSpectrum(canvas: Locator): Promise<void> {
  const diagnostics = await canvas.evaluate(() => (
    (window as unknown as {
      nurStarBrain?: { getDiagnostics?: () => {
        frameCount: number;
        brainstemPointCount: number;
        spectrumBands: string[];
        spectrumCounts: Record<string, number>;
      } };
    }).nurStarBrain?.getDiagnostics?.()
  ));
  expect(diagnostics).toBeTruthy();
  expect(diagnostics?.frameCount).toBeGreaterThan(1);
  expect(diagnostics?.brainstemPointCount).toBeGreaterThan(100);
  expect(diagnostics?.spectrumBands).toEqual(SPECTRUM);
  for (const band of SPECTRUM) expect(diagnostics?.spectrumCounts[band]).toBeGreaterThan(100);
}

async function proveDragRotation(page: Page, canvas: Locator): Promise<void> {
  const before = await canvas.evaluate(() => (
    (window as unknown as { nurStarBrain?: { getDiagnostics?: () => { yaw: number } } })
      .nurStarBrain?.getDiagnostics?.().yaw ?? 0
  ));
  const box = await canvas.boundingBox();
  expect(box).toBeTruthy();
  await page.mouse.move(box!.x + box!.width * .42, box!.y + box!.height * .5);
  await page.mouse.down();
  await page.mouse.move(box!.x + box!.width * .63, box!.y + box!.height * .42, { steps: 6 });
  await page.mouse.up();
  await expect.poll(async () => canvas.evaluate(() => (
    (window as unknown as { nurStarBrain?: { getDiagnostics?: () => { yaw: number } } })
      .nurStarBrain?.getDiagnostics?.().yaw ?? 0
  ))).not.toBeCloseTo(before, 2);
}

test("Entry is true black with a moving seven-spectrum Three.js sky and star brain", async ({ page }, testInfo) => {
  await page.route("https://fonts.googleapis.com/**", route => route.fulfill({ status: 204, body: "" }));
  await page.route("https://fonts.gstatic.com/**", route => route.fulfill({ status: 204, body: "" }));
  await page.route("**/api/v1/auth/me", route => route.fulfill({
    status: 401,
    contentType: "application/json",
    body: JSON.stringify({ detail: "Not authenticated" }),
  }));
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });

  await expect(entry.locator("#nur-front-v61")).toHaveCSS("background-color", "rgb(0, 0, 0)");
  const brainHost = entry.locator("#front-nur-star");
  const brainCanvas = brainHost.locator("#nur-brain-canvas");
  const galaxyCanvas = entry.locator("#space3d");
  await expect(brainHost).toHaveAttribute("data-nur-engine", "three-webgl-coordinated-v1");
  await expect(brainHost).toHaveAttribute("data-nur-spectrum-bands", SPECTRUM.join(","));
  await expect(brainCanvas).toBeVisible();
  await expect(galaxyCanvas).toBeVisible();
  await proveMovingCanvas(brainCanvas, testInfo.project.name.includes("mobile") ? 20 : 55);
  await proveMovingCanvas(galaxyCanvas, testInfo.project.name.includes("mobile") ? 35 : 90);
  await proveSevenSpectrum(brainCanvas);
  await proveDragRotation(page, brainCanvas);
  if (testInfo.project.name.includes("mobile")) await brainHost.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath(`entry-seven-spectrum-${testInfo.project.name}.png`),
    fullPage: false,
    animations: "allow",
  });
});

test("Systems is true black with the same moving seven-spectrum rig", async ({ page }, testInfo) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "seven-spectrum-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "seven-spectrum-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 15_000 });
  await expect(universe.locator("#nur-front-v61")).toHaveCSS("background-color", "rgb(0, 0, 0)");

  const brainHost = universe.locator("#front-nur-star");
  const brainCanvas = brainHost.locator("#nur-brain-canvas");
  const galaxyCanvas = universe.locator("#space3d");
  await expect(brainHost).toHaveAttribute("data-nur-surface", "universe");
  await expect(brainHost).toHaveAttribute("data-nur-spectrum-band-count", "7");
  await expect(brainCanvas).toBeVisible();
  await expect(galaxyCanvas).toBeVisible();
  await proveMovingCanvas(brainCanvas, testInfo.project.name.includes("mobile") ? 20 : 55);
  await proveMovingCanvas(galaxyCanvas, testInfo.project.name.includes("mobile") ? 35 : 90);
  await proveSevenSpectrum(brainCanvas);
  await proveDragRotation(page, brainCanvas);
  await brainHost.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath(`systems-seven-spectrum-${testInfo.project.name}.png`),
    fullPage: false,
    animations: "allow",
  });
});
