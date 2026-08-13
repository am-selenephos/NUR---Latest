import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const SPECTRUM = ["red", "orange", "yellow", "green", "blue", "indigo", "violet"] as const;

type GalaxyDiagnostics = {
  yaw: number;
  pitch: number;
  angularVelocityYaw: number;
  angularVelocityPitch: number;
  dragging: boolean;
  parallaxX: number;
  parallaxY: number;
};

type BrainDiagnostics = {
  yaw: number;
  pitch: number;
  angularVelocityYaw: number;
  angularVelocityPitch: number;
  dragging: boolean;
  frameCount: number;
};

async function galaxyDiagnostics(canvas: Locator): Promise<GalaxyDiagnostics> {
  return canvas.evaluate(() => {
    const diagnostics = (window as unknown as {
      nurGalaxy: { getParticleDiagnostics: () => GalaxyDiagnostics };
    }).nurGalaxy.getParticleDiagnostics();
    return diagnostics;
  });
}

async function brainDiagnostics(canvas: Locator): Promise<BrainDiagnostics> {
  return canvas.evaluate(() => {
    const diagnostics = (window as unknown as {
      nurStarBrain: { getDiagnostics: () => BrainDiagnostics };
    }).nurStarBrain.getDiagnostics();
    return diagnostics;
  });
}

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

async function provePointerParallax(galaxyCanvas: Locator): Promise<void> {
  const before = await galaxyDiagnostics(galaxyCanvas);
  await galaxyCanvas.evaluate(() => {
    window.dispatchEvent(new PointerEvent("pointermove", {
      bubbles: true,
      pointerId: 71,
      pointerType: "mouse",
      isPrimary: true,
      clientX: innerWidth * .9,
      clientY: innerHeight * .16,
    }));
  });
  await expect.poll(async () => {
    const current = await galaxyDiagnostics(galaxyCanvas);
    return Math.hypot(current.parallaxX - before.parallaxX, current.parallaxY - before.parallaxY);
  }).toBeGreaterThan(.015);
  expect((await galaxyDiagnostics(galaxyCanvas)).dragging).toBe(false);
}

async function emptyGalaxyPoint(frame: FrameLocator): Promise<{ x: number; y: number }> {
  return frame.locator("body").evaluate(() => {
    const blockers = [
      "button", "a", "input", "textarea", "select", "label", "summary",
      "[contenteditable='true']", "[role='button']", "[role='tab']", "[role='slider']",
      "[data-action]", "[data-system]", "[data-system-slug]", ".nur-rail", ".nur-topbar",
      ".talk-chamber", ".journal-pad", ".universe-insight-panel", ".nur-insights-pane",
      "#nur-map-root", "#nur-orbit-root", "#nur-timeline-root",
    ].join(",");
    const fractions = [
      [.72, .82], [.52, .9], [.82, .68], [.34, .84], [.62, .72], [.18, .76],
    ];
    for (const [xFraction, yFraction] of fractions) {
      const x = innerWidth * xFraction;
      const y = innerHeight * yFraction;
      const target = document.elementFromPoint(x, y) as HTMLElement | null;
      if (!target || target.closest("#front-nur-star") || target.closest(blockers)) continue;
      let current: HTMLElement | null = target;
      let interactive = false;
      while (current && current !== document.body) {
        if (current.onclick || getComputedStyle(current).cursor === "pointer") {
          interactive = true;
          break;
        }
        current = current.parentElement;
      }
      if (!interactive) return { x, y };
    }
    throw new Error("No empty galaxy interaction point was available");
  });
}

async function proveGalaxyInteraction(
  page: Page,
  frame: FrameLocator,
  stageSelector: string,
  galaxyCanvas: Locator,
  brainCanvas: Locator,
  touch: boolean,
): Promise<void> {
  await provePointerParallax(galaxyCanvas);
  const before = await galaxyDiagnostics(galaxyCanvas);
  const brainBefore = await brainDiagnostics(brainCanvas);

  if (touch) {
    await frame.locator("body").evaluate((target) => {
      const interactionPoint = { x: innerWidth * .72, y: innerHeight * .82 };
      const init = {
        bubbles: true,
        cancelable: true,
        pointerId: 81,
        pointerType: "touch",
        isPrimary: true,
        button: 0,
        buttons: 1,
      };
      target.dispatchEvent(new PointerEvent("pointerdown", {
        ...init,
        clientX: interactionPoint.x,
        clientY: interactionPoint.y,
      }));
      window.dispatchEvent(new PointerEvent("pointermove", {
        ...init,
        clientX: interactionPoint.x - innerWidth * .24,
        clientY: interactionPoint.y - innerHeight * .14,
      }));
      window.dispatchEvent(new PointerEvent("pointerup", {
        ...init,
        buttons: 0,
        clientX: interactionPoint.x - innerWidth * .24,
        clientY: interactionPoint.y - innerHeight * .14,
      }));
    });
  } else {
    const point = await emptyGalaxyPoint(frame);
    const stage = await page.locator(stageSelector).boundingBox();
    expect(stage).toBeTruthy();
    await page.mouse.move(stage!.x + point.x, stage!.y + point.y);
    await page.mouse.down();
    await expect.poll(async () => (await galaxyDiagnostics(galaxyCanvas)).dragging).toBe(true);
    await page.mouse.move(stage!.x + point.x - 150, stage!.y + point.y - 78, { steps: 7 });
    await page.mouse.up();
  }

  const released = await galaxyDiagnostics(galaxyCanvas);
  expect(Math.abs(released.yaw - before.yaw)).toBeGreaterThan(.12);
  expect(Math.abs(released.pitch - before.pitch)).toBeGreaterThan(.05);
  expect(Math.hypot(released.angularVelocityYaw, released.angularVelocityPitch)).toBeGreaterThan(.001);
  expect(released.dragging).toBe(false);
  const brainAfter = await brainDiagnostics(brainCanvas);
  expect(Math.hypot(brainAfter.yaw - brainBefore.yaw, brainAfter.pitch - brainBefore.pitch))
    .toBeLessThan(.09);

  await page.waitForTimeout(140);
  const inertial = await galaxyDiagnostics(galaxyCanvas);
  expect(Math.hypot(inertial.yaw - released.yaw, inertial.pitch - released.pitch)).toBeGreaterThan(.003);
  expect(Math.hypot(inertial.angularVelocityYaw, inertial.angularVelocityPitch))
    .toBeLessThan(Math.hypot(released.angularVelocityYaw, released.angularVelocityPitch));
}

async function proveBrainInteraction(
  page: Page,
  canvas: Locator,
  galaxyCanvas: Locator,
  touch: boolean,
): Promise<void> {
  const before = await brainDiagnostics(canvas);
  const galaxyBefore = await galaxyDiagnostics(galaxyCanvas);
  const interactionBefore = await canvas.evaluate(element => element.parentElement?.dataset.nurLastInteraction ?? null);
  const box = await canvas.boundingBox();
  expect(box).toBeTruthy();
  if (touch) {
    await canvas.evaluate((element: HTMLCanvasElement) => {
      const rect = element.getBoundingClientRect();
      const init = {
        bubbles: true,
        cancelable: true,
        pointerId: 91,
        pointerType: "touch",
        isPrimary: true,
        button: 0,
        buttons: 1,
      };
      element.dispatchEvent(new PointerEvent("pointerdown", {
        ...init,
        clientX: rect.left + rect.width * .38,
        clientY: rect.top + rect.height * .55,
      }));
      element.dispatchEvent(new PointerEvent("pointermove", {
        ...init,
        clientX: rect.left + rect.width * .69,
        clientY: rect.top + rect.height * .34,
      }));
      element.dispatchEvent(new PointerEvent("pointerup", {
        ...init,
        buttons: 0,
        clientX: rect.left + rect.width * .69,
        clientY: rect.top + rect.height * .34,
      }));
    });
  } else {
    await page.mouse.move(box!.x + box!.width * .38, box!.y + box!.height * .55);
    await page.mouse.down();
    await expect.poll(async () => (await brainDiagnostics(canvas)).dragging).toBe(true);
    await page.mouse.move(box!.x + box!.width * .69, box!.y + box!.height * .34, { steps: 7 });
    await page.mouse.up();
  }

  await expect.poll(async () => {
    const current = await brainDiagnostics(canvas);
    return Math.hypot(current.yaw - before.yaw, current.pitch - before.pitch);
  }).toBeGreaterThan(.035);
  const released = await brainDiagnostics(canvas);
  expect(Math.abs(released.yaw - before.yaw)).toBeGreaterThan(.02);
  expect(Math.abs(released.pitch - before.pitch)).toBeGreaterThan(.015);
  expect(Math.hypot(released.angularVelocityYaw, released.angularVelocityPitch)).toBeGreaterThan(.001);
  expect(released.dragging).toBe(false);
  const galaxyAfter = await galaxyDiagnostics(galaxyCanvas);
  expect(Math.hypot(galaxyAfter.yaw - galaxyBefore.yaw, galaxyAfter.pitch - galaxyBefore.pitch))
    .toBeLessThan(.09);
  expect(await canvas.evaluate(element => element.parentElement?.dataset.nurLastInteraction ?? null))
    .toBe(interactionBefore);

  await page.waitForTimeout(140);
  const inertial = await brainDiagnostics(canvas);
  expect(Math.hypot(inertial.yaw - released.yaw, inertial.pitch - released.pitch)).toBeGreaterThan(.003);
  expect(Math.hypot(inertial.angularVelocityYaw, inertial.angularVelocityPitch))
    .toBeLessThan(Math.hypot(released.angularVelocityYaw, released.angularVelocityPitch));
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
  if (testInfo.project.name.includes("mobile")) await brainHost.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath(`entry-seven-spectrum-${testInfo.project.name}.png`),
    fullPage: false,
    animations: "allow",
  });
  const touch = testInfo.project.name.includes("mobile");
  await proveGalaxyInteraction(page, entry, "#nur-entry-stage", galaxyCanvas, brainCanvas, touch);
  await proveBrainInteraction(page, brainCanvas, galaxyCanvas, touch);
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
  await brainHost.scrollIntoViewIfNeeded();
  await page.screenshot({
    path: testInfo.outputPath(`systems-seven-spectrum-${testInfo.project.name}.png`),
    fullPage: false,
    animations: "allow",
  });
  const touch = testInfo.project.name.includes("mobile");
  await proveGalaxyInteraction(page, universe, "#nur-universe-stage", galaxyCanvas, brainCanvas, touch);
  await proveBrainInteraction(page, brainCanvas, galaxyCanvas, touch);

  await galaxyCanvas.evaluate(() => {
    (window as unknown as { __e2eGalaxyOwner?: unknown; nurGalaxy?: unknown }).__e2eGalaxyOwner =
      (window as unknown as { nurGalaxy?: unknown }).nurGalaxy;
  });
  for (let cycle = 0; cycle < 2; cycle += 1) {
    await universe.getByRole("tab", { name: "Insights", exact: true }).click();
    await expect(universe.locator("#nur-insights-root")).toBeVisible();
    await expect(universe.locator("#nur-brain-canvas")).toBeHidden();
    await universe.getByRole("tab", { name: "Universe", exact: true }).click();
    await expect(universe.locator("#page-systems")).toBeVisible();
    await expect(universe.locator("#nur-brain-canvas")).toHaveCount(1);
  }
  expect(await galaxyCanvas.evaluate(() => (
    (window as unknown as { __e2eGalaxyOwner?: unknown; nurGalaxy?: unknown }).__e2eGalaxyOwner ===
      (window as unknown as { nurGalaxy?: unknown }).nurGalaxy
  ))).toBe(true);
});

test("Journal stays visually clean and Insights mounts its dedicated owner surface", async ({ page }, testInfo) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "insights-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "insights-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  const universe = page.frameLocator("#nur-universe-stage");

  await page.goto("/journal", { waitUntil: "load" });
  await expect(universe.locator("#page-journal")).toBeVisible({ timeout: 15_000 });
  await expect(universe.locator("#page-journal .journal-prompt")).toBeHidden();
  await page.screenshot({
    path: testInfo.outputPath(`journal-clean-${testInfo.project.name}.png`),
    fullPage: false,
    animations: "allow",
  });

  await page.goto("/universe/insights", { waitUntil: "load" });
  const insights = universe.locator("#nur-insights-root");
  await expect(insights).toBeVisible({ timeout: 15_000 });
  await expect(insights).toHaveAttribute("data-insights-loaded", "true");
  await expect(insights).toContainText(
    "Outcome evidence should strengthen planning patterns only after persisted results.",
  );
  await expect(universe.locator("#nur-brain-canvas:visible")).toHaveCount(0);
  await expect(universe.locator(".global-composer")).toBeHidden();
  const geometry = await insights.evaluate(element => ({
    rootRight: element.getBoundingClientRect().right,
    viewport: innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    clientWidth: document.documentElement.clientWidth,
  }));
  expect(geometry.rootRight).toBeLessThanOrEqual(geometry.viewport + 1);
  expect(geometry.scrollWidth).toBeLessThanOrEqual(geometry.clientWidth + 2);
  await page.screenshot({
    path: testInfo.outputPath(`insights-owner-field-${testInfo.project.name}.png`),
    fullPage: false,
    animations: "allow",
  });
});
