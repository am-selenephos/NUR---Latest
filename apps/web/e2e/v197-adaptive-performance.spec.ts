import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks, json, mockUser } from "./helpers/nurMocks";

type V197Frames = {
  entry: FrameLocator;
  universe: FrameLocator;
};

async function universeFrame(
  page: Page,
  inspectEntry?: (entry: FrameLocator) => Promise<void>,
): Promise<V197Frames> {
  await installNurMocks(page);
  let authenticated = false;
  await page.route("**/api/v1/auth/me", route => (
    authenticated
      ? json(route, mockUser)
      : json(route, { detail: "Not authenticated" }, 401)
  ));
  await page.route("**/api/v1/auth/login", route => {
    authenticated = true;
    return json(route, { ok: true });
  });
  await page.context().addCookies([{
    name: "nur_csrf",
    value: "adaptive-performance-csrf",
    url: "http://localhost:4173",
    httpOnly: false,
    sameSite: "Lax",
  }]);
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });
  await expect(entry.locator("#nur-front-v61")).toBeVisible();
  await inspectEntry?.(entry);

  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 20_000 });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("body.universe-edition")).toBeVisible();
  return { entry, universe };
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

const ACTIONABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled]):not([type='hidden'])",
  "textarea:not([disabled])",
  "select:not([disabled])",
  "summary",
  "[role='button']:not([aria-disabled='true'])",
  "[tabindex]:not([tabindex='-1']):not([aria-disabled='true'])",
].join(",");

async function visibleActionableTargetSizes(root: Locator) {
  return root.locator(ACTIONABLE_SELECTOR).evaluateAll(elements => {
    const visible = (element: Element) => {
      const target = element as HTMLElement;
      if (target.closest("[hidden], [inert], [aria-hidden='true']")) return false;
      for (let ancestor: HTMLElement | null = target; ancestor; ancestor = ancestor.parentElement) {
        const style = getComputedStyle(ancestor);
        if (
          style.display === "none"
          || style.visibility === "hidden"
          || Number.parseFloat(style.opacity || "1") < .02
        ) return false;
      }
      const rect = target.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    return elements.filter(visible).map(element => {
      const rect = element.getBoundingClientRect();
      return {
        label: (element.getAttribute("aria-label") || element.textContent || element.className).trim(),
        tag: element.tagName.toLowerCase(),
        width: Number(rect.width.toFixed(2)),
        height: Number(rect.height.toFixed(2)),
      };
    });
  });
}

async function paintBudget(frame: FrameLocator) {
  return frame.locator("body").evaluate(() => {
    const visible = (element: Element) => {
      const target = element as HTMLElement;
      for (let ancestor: HTMLElement | null = target; ancestor; ancestor = ancestor.parentElement) {
        const style = getComputedStyle(ancestor);
        if (
          style.display === "none"
          || style.visibility === "hidden"
          || Number.parseFloat(style.opacity || "1") < .02
        ) return false;
      }
      const rect = target.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    };
    const animations = document.getAnimations().filter(animation => animation.playState === "running");
    const repeatedAnimations = animations.filter(animation => animation.effect?.getTiming().iterations === Infinity);
    const targets = repeatedAnimations.flatMap(animation => {
      const target = animation.effect instanceof KeyframeEffect ? animation.effect.target : null;
      return target instanceof Element && visible(target) ? [target] : [];
    });
    const viewportArea = Math.max(1, innerWidth * innerHeight);
    const backdropHosts = [...document.querySelectorAll<HTMLElement>("*")].filter(element => (
      visible(element)
      && !element.matches(".nur-holo-control")
      && getComputedStyle(element).backdropFilter !== "none"
    ));
    return {
      backdropHosts: backdropHosts.map(element => element.className || element.id),
      inactiveRouteAnimations: targets.filter(element => element.closest(".nur-page:not(.active)")).length,
      largeSurfaceAnimations: targets.filter(element => {
        const rect = element.getBoundingClientRect();
        return rect.width * rect.height > viewportArea * .08
          && !element.closest(".nur-holo-control, #front-nur-star");
      }).length,
      repeatedAnimations: repeatedAnimations.length,
      visibleRepeatedAnimations: targets.length,
      visibleControlEffects: targets.filter(element => element.closest(".nur-holo-control")).length,
      repeatedTargets: repeatedAnimations.map(animation => {
        const target = animation.effect instanceof KeyframeEffect ? animation.effect.target : null;
        const element = target instanceof Element ? target : null;
        const rect = element?.getBoundingClientRect();
        return {
          name: animation instanceof CSSAnimation ? animation.animationName : "script",
          target: element?.id || element?.className || element?.tagName || "unknown",
          area: rect ? Math.round(rect.width * rect.height) : 0,
        };
      }),
    };
  });
}

test("Systems owns nonblank rigs, an honest paint budget, and no hidden Entry timelines", async ({ page }, testInfo) => {
  const failures: string[] = [];
  page.on("pageerror", error => failures.push(error.message));
  page.on("console", message => {
    if (message.text().includes("NUR offline shell registration failed")) failures.push(message.text());
  });
  const { universe } = await universeFrame(page);
  const systemsSelector = testInfo.project.name.includes("mobile")
    ? ".mobile-tabs [data-page='systems']"
    : ".clean-nav-button[data-page='systems']";

  await universe.locator(systemsSelector).click();
  await expect(universe.locator("#page-systems.active")).toBeVisible();
  const galaxy = universe.locator("#space3d");
  const brain = universe.locator("#nur-brain-canvas");
  await expect(galaxy).toBeVisible();
  await expect(brain).toBeVisible();
  await brain.scrollIntoViewIfNeeded();
  await expect.poll(async () => (await canvasSignal(galaxy)).lit).toBeGreaterThan(110);
  await expect.poll(async () => (await canvasSignal(brain)).lit).toBeGreaterThan(110);

  const firstGalaxy = await canvasSignal(galaxy);
  const firstBrain = await canvasSignal(brain);
  expect(firstGalaxy.checksum).toBeGreaterThan(0);
  expect(firstBrain.checksum).toBeGreaterThan(0);
  await expect.poll(async () => (await canvasSignal(galaxy)).checksum).not.toBe(firstGalaxy.checksum);
  await expect.poll(async () => (await canvasSignal(brain)).checksum).not.toBe(firstBrain.checksum);

  const canvases = await universe.locator("canvas").evaluateAll(elements => elements.map(element => {
    const canvas = element as HTMLCanvasElement;
    const rect = canvas.getBoundingClientRect();
    return { id: canvas.id, width: rect.width, height: rect.height, pixels: canvas.width * canvas.height };
  }));
  expect(canvases.map(canvas => canvas.id).sort()).toEqual(["nur-brain-canvas", "space3d"]);
  expect(canvases.every(canvas => canvas.width > 0 && canvas.height > 0 && canvas.pixels > 0)).toBe(true);

  const systemsBudget = await paintBudget(universe);
  expect(systemsBudget.backdropHosts.length, JSON.stringify(systemsBudget, null, 2)).toBeLessThanOrEqual(8);
  expect(systemsBudget.inactiveRouteAnimations, JSON.stringify(systemsBudget, null, 2)).toBe(0);
  expect(systemsBudget.largeSurfaceAnimations, JSON.stringify(systemsBudget, null, 2)).toBeLessThanOrEqual(2);
  expect(systemsBudget.visibleRepeatedAnimations, JSON.stringify(systemsBudget, null, 2))
    .toBeLessThanOrEqual(testInfo.project.name.includes("mobile") ? 28 : 32);
  expect(systemsBudget.visibleControlEffects, JSON.stringify(systemsBudget, null, 2)).toBeGreaterThan(0);

  // Authenticated Universe retires the Entry iframe entirely; absence is stronger
  // than keeping a hidden frame around and trying to police its animations.
  await expect(page.locator("#nur-entry-stage")).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute("data-nur-entry-retired", "true");
  expect(failures).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("adaptive-systems.png"), fullPage: false });
});

test("coarse mobile audits every visible Entry and Universe action at its final 44px box", async ({ page }, testInfo) => {
  test.skip(!testInfo.project.name.includes("mobile"), "Coarse target sizing is exercised by the mobile project.");
  let entrySizes: Awaited<ReturnType<typeof visibleActionableTargetSizes>> = [];
  const { universe } = await universeFrame(page, async entry => {
    entrySizes = await visibleActionableTargetSizes(entry.locator("body"));
  });
  await universe.locator(".mobile-tabs [data-page='systems']").click();
  await expect(universe.locator("#page-systems.active")).toBeVisible();
  const universeSizes = await visibleActionableTargetSizes(universe.locator("body"));
  const undersized = [...entrySizes, ...universeSizes]
    .filter(target => target.width < 43.5 || target.height < 43.5);
  expect(entrySizes.length).toBeGreaterThan(0);
  expect(universeSizes.length).toBeGreaterThan(0);
  expect(undersized, JSON.stringify(undersized, null, 2)).toEqual([]);
  await page.screenshot({ path: testInfo.outputPath("adaptive-mobile-targets.png"), fullPage: false });
});

test("reduced motion paints one deterministic brain frame and owns no continuing animation", async ({ page }, testInfo) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const { universe } = await universeFrame(page);
  const systemsSelector = testInfo.project.name.includes("mobile")
    ? ".mobile-tabs [data-page='systems']"
    : ".clean-nav-button[data-page='systems']";
  await universe.locator(systemsSelector).click();
  await expect(universe.locator("#page-systems.active")).toBeVisible();
  const galaxy = universe.locator("#space3d");
  const brain = universe.locator("#nur-brain-canvas");
  await brain.scrollIntoViewIfNeeded();
  await expect.poll(async () => (await canvasSignal(galaxy)).lit).toBeGreaterThan(110);
  await expect.poll(async () => (await canvasSignal(brain)).lit).toBeGreaterThan(110);
  const firstGalaxy = await canvasSignal(galaxy);
  const firstBrain = await canvasSignal(brain);

  await page.waitForTimeout(450);
  expect(await canvasSignal(galaxy)).toEqual(firstGalaxy);
  expect(await canvasSignal(brain)).toEqual(firstBrain);

  const runtime = await universe.locator("body").evaluate(() => {
    const brainDiagnostics = (window as unknown as {
      nurStarBrain?: { getDiagnostics?: () => Record<string, unknown> };
      nurGalaxy?: { getParticleDiagnostics?: () => Record<string, unknown> };
    }).nurStarBrain?.getDiagnostics?.();
    const galaxyDiagnostics = (window as unknown as {
      nurGalaxy?: { getParticleDiagnostics?: () => Record<string, unknown> };
    }).nurGalaxy?.getParticleDiagnostics?.();
    return {
      brainDiagnostics,
      galaxyDiagnostics,
      runningInfinite: document.getAnimations().filter(animation => (
        animation.playState === "running" && animation.effect?.getTiming().iterations === Infinity
      )).length,
    };
  });
  expect(runtime.brainDiagnostics).toMatchObject({
    reducedMotion: true,
    frameScheduled: false,
    staticFramePainted: true,
    stageVisible: true,
  });
  expect(runtime.galaxyDiagnostics).toMatchObject({ frameScheduled: false, shouldRender: true });
  expect(runtime.runningInfinite).toBe(0);
  await expect(page.locator("#nur-entry-stage")).toHaveCount(0);
  await expect(page.locator("html")).toHaveAttribute("data-nur-entry-retired", "true");
});
