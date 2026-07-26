import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

type Material = {
  background: string;
  border: string;
  shadow: string;
};

async function material(locator: Locator): Promise<Material> {
  return locator.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      background: style.background,
      border: style.borderColor,
      shadow: style.boxShadow,
    };
  });
}

async function canvasSignal(canvas: Locator): Promise<{ lit: number; alpha: number; checksum: number }> {
  return canvas.evaluate((element: HTMLCanvasElement) => {
    const context = element.getContext("2d");
    if (!context || element.width < 2 || element.height < 2) return { lit: 0, alpha: 0, checksum: 0 };
    const pixels = context.getImageData(0, 0, element.width, element.height).data;
    const stride = Math.max(4, Math.floor(pixels.length / 28_000 / 4) * 4);
    let lit = 0;
    let alpha = 0;
    let checksum = 0;
    for (let index = 0; index < pixels.length; index += stride) {
      const r = pixels[index] ?? 0;
      const g = pixels[index + 1] ?? 0;
      const b = pixels[index + 2] ?? 0;
      const a = pixels[index + 3] ?? 0;
      if (a > 8) alpha += 1;
      if (r + g + b > 120 && a > 20) lit += 1;
      checksum = (checksum + r * 3 + g * 5 + b * 7 + a * 11) % 2_147_483_647;
    }
    return { lit, alpha, checksum };
  });
}

async function authenticatedUniverse(page: Page, path: string): Promise<FrameLocator> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "cool-black-mandate", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "cool-black-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto(path, { waitUntil: "load" });
  return page.frameLocator("#nur-universe-stage");
}

test("Entry keeps its copy while mind, sky, and star brain use the cool galaxy contract", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Visual mandate capture runs once in desktop Chromium.");
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });

  const root = entry.locator("#nur-front-v61");
  const brain = entry.locator("#front-nur-star");
  const canvas = brain.locator("#nur-brain-canvas");
  await expect(canvas).toBeVisible();
  await expect(brain).toHaveAttribute("data-nur-surface", "entry");
  await expect(brain).toHaveAttribute("data-nur-scale-profile", "entry-exact");
  await expect(brain).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");

  const presentation = await root.evaluate((element, mindSelector) => {
    const rootStyle = getComputedStyle(element);
    const mindStyle = getComputedStyle(element.querySelector<HTMLElement>(mindSelector)!);
    return {
      rootBackground: rootStyle.backgroundImage,
      mindBackground: mindStyle.backgroundImage,
      mindClip: mindStyle.backgroundClip,
      mindFill: mindStyle.webkitTextFillColor,
      mindAnimation: mindStyle.animationName,
      mindFilter: mindStyle.filter,
    };
  }, ".f4-title em");
  expect(presentation.rootBackground).toContain("rgba(0, 1, 4");
  expect(presentation.mindBackground).toContain("linear-gradient");
  expect(presentation.mindClip).toBe("text");
  expect(presentation.mindFill).toBe("rgba(0, 0, 0, 0)");
  expect(presentation.mindAnimation).toContain("nurMindGold");
  expect(presentation.mindFilter).toContain("drop-shadow");

  await expect.poll(async () => (await canvasSignal(canvas)).lit).toBeGreaterThan(70);
  const first = await canvasSignal(canvas);
  await page.waitForTimeout(420);
  const second = await canvasSignal(canvas);
  expect(second.checksum).not.toBe(first.checksum);
  await page.screenshot({ path: testInfo.outputPath("entry-cool-black-galaxy.png") });
});

test("Today, Talk, and Systems share one brain paint and one calm composer proportion", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Visual mandate capture runs once in desktop Chromium.");
  await page.setViewportSize({ width: 1440, height: 900 });
  const universe = await authenticatedUniverse(page, "/today");
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 15_000 });

  const todayBrain = universe.locator("#page-today #front-nur-star");
  await expect(todayBrain).toHaveAttribute("data-nur-surface", "today");
  await expect(todayBrain).toHaveAttribute("data-nur-scale-profile", "entry-exact");
  await expect(todayBrain).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");
  await expect(universe.locator("#page-today .orbit-annotation")).toHaveCount(0);
  await expect.poll(async () => (
    await canvasSignal(todayBrain.locator("#nur-brain-canvas"))
  ).lit).toBeGreaterThan(70);

  const todayComposer = universe.locator("#page-today .thought-composer").first();
  await expect(todayComposer).toBeVisible();
  const todayHeight = await todayComposer.evaluate(element => element.getBoundingClientRect().height);
  const todayInput = todayComposer.locator("input");
  const todayRest = await material(todayComposer);
  await todayInput.focus();
  expect(await material(todayComposer)).toEqual(todayRest);
  await expect(todayInput).toBeFocused();
  await universe.locator(".nur-viewport").evaluate(element => { element.scrollTop = 0; });
  await page.waitForTimeout(150);
  await page.screenshot({ path: testInfo.outputPath("today-clean-brain-and-composer.png") });
  await universe.locator("#page-today .orbit-hero").screenshot({
    path: testInfo.outputPath("today-exact-entry-brain.png"),
  });

  await universe.locator('.clean-nav-button[data-page="talk"]').click();
  await expect(universe.locator("#page-talk")).toBeVisible();
  const talkComposer = universe.locator("#page-talk .thought-composer").first();
  const talkHeight = await talkComposer.evaluate(element => element.getBoundingClientRect().height);
  const talkRest = await material(talkComposer);
  await talkComposer.locator("input").focus();
  expect(await material(talkComposer)).toEqual(talkRest);

  await universe.locator('.clean-nav-button[data-page="systems"]').click();
  await expect(universe.locator("#page-systems")).toBeVisible();
  const systemsBrain = universe.locator("#page-systems #front-nur-star");
  await expect(systemsBrain).toHaveAttribute("data-nur-surface", "universe");
  await expect(systemsBrain).toHaveAttribute("data-nur-scale-profile", "systems-expanded");
  await expect(systemsBrain).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");
  await expect.poll(async () => (
    await canvasSignal(systemsBrain.locator("#nur-brain-canvas"))
  ).lit).toBeGreaterThan(70);

  const systemsBody = universe.locator("body");
  await expect(systemsBody).toHaveClass(/nur-v197-systems-active/);
  await expect(universe.locator(".nur-v178-warmth-film")).toHaveCSS("display", "none");

  const surfaceMaterials = await universe.locator("#page-systems").evaluate(root => {
    const selectors = [
      ":scope",
      ".universe-map-panel",
      ".universe-insight-panel",
      ".universe-state-strip",
      ".universe-composer-shell",
    ];
    return selectors.map(selector => {
      const element = selector === ":scope" ? root : root.querySelector<HTMLElement>(selector);
      if (!element) return { selector, missing: true, backgroundColor: "", backgroundImage: "" };
      const style = getComputedStyle(element);
      return {
        selector,
        missing: false,
        backgroundColor: style.backgroundColor,
        backgroundImage: style.backgroundImage,
      };
    });
  });
  for (const surface of surfaceMaterials) {
    expect(surface.missing, `${surface.selector} must be present`).toBe(false);
    const channels = surface.backgroundColor.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    expect(channels, `${surface.selector} must expose an RGB black base`).toHaveLength(3);
    expect(
      Math.max(...channels) - Math.min(...channels),
      `${surface.selector} must remain neutral black, not blue-tinted: ${surface.backgroundColor}`,
    ).toBeLessThanOrEqual(1);
  }
  const systemsPanelImages = surfaceMaterials
    .filter(surface => surface.selector !== ":scope")
    .map(surface => surface.backgroundImage)
    .join(" ");
  expect(systemsPanelImages).toContain("255, 211, 90");
  expect(systemsPanelImages).toContain("255, 58, 158");
  expect(systemsPanelImages).toContain("105, 240, 180");
  expect(systemsPanelImages).not.toContain("33, 232, 255");

  const allPanelMaterials = await universe.locator("#page-systems").evaluate(root => {
    const selector = [
      ".universe-map-panel",
      ".universe-insight-panel",
      ".universe-card",
      ".candidate-insight",
      ".context-rail-card",
      ".v172-context-card",
      ".clean-audit-card",
      ".nur-panel",
      ".universe-state-strip",
      ".universe-composer-shell",
    ].join(",");
    return Array.from(root.querySelectorAll<HTMLElement>(selector))
      .filter(element => {
        const rect = element.getBoundingClientRect();
        return rect.width > 0 && rect.height > 0;
      })
      .map((element, index) => {
        const style = getComputedStyle(element);
        return {
          identity: `${element.tagName.toLowerCase()}.${Array.from(element.classList).join(".")}#${index}`,
          backgroundColor: style.backgroundColor,
          backgroundImage: style.backgroundImage,
        };
      });
  });
  expect(allPanelMaterials.length).toBeGreaterThanOrEqual(8);
  for (const panel of allPanelMaterials) {
    const channels = panel.backgroundColor.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    expect(channels, `${panel.identity} must expose an RGB black base`).toHaveLength(3);
    expect(
      Math.max(...channels) - Math.min(...channels),
      `${panel.identity} must remain neutral black, not blue-tinted: ${panel.backgroundColor}`,
    ).toBeLessThanOrEqual(1);
    expect(panel.backgroundImage, `${panel.identity} must not restore the cyan band`)
      .not.toContain("33, 232, 255");
  }

  const galaxy = universe.locator("#space3d");
  await expect(galaxy).toBeVisible();
  const particleCount = await galaxy.evaluate(() => (
    (window as unknown as { nurGalaxy?: { getParticleCount?: () => number } }).nurGalaxy?.getParticleCount?.() ?? 0
  ));
  expect(particleCount).toBeGreaterThanOrEqual(1_160);
  expect(particleCount).toBeLessThanOrEqual(1_200);
  const galaxyFirst = await canvasSignal(galaxy);
  await page.waitForTimeout(420);
  const galaxySecond = await canvasSignal(galaxy);
  expect(galaxySecond.lit).toBeGreaterThan(110);
  expect(galaxySecond.checksum).not.toBe(galaxyFirst.checksum);

  const topbarWidths = await universe.locator(".universe-top-tools").evaluate(element => {
    const width = (selector: string) => element.querySelector<HTMLElement>(selector)!.getBoundingClientRect().width;
    return { english: width(".nur-v197-language-open"), privacy: width("#scope-open") };
  });
  expect(topbarWidths.english).toBeCloseTo(76, 1);
  expect(topbarWidths.privacy).toBeCloseTo(topbarWidths.english, 1);

  const systemsComposer = universe.locator(".universe-composer--v173");
  const systemsHeight = await systemsComposer.evaluate(element => element.getBoundingClientRect().height);
  const systemsMetrics = await systemsComposer.evaluate(element => {
    const style = getComputedStyle(element);
    return {
      cssHeight: style.height,
      minHeight: style.minHeight,
      maxHeight: style.maxHeight,
      padding: style.padding,
      border: style.borderWidth,
      boxSizing: style.boxSizing,
      transform: style.transform,
    };
  });
  const systemsRest = await material(systemsComposer);
  await systemsComposer.locator("input").focus();
  expect(await material(systemsComposer)).toEqual(systemsRest);
  expect(
    Math.max(todayHeight, talkHeight, systemsHeight) - Math.min(todayHeight, talkHeight, systemsHeight),
    JSON.stringify({ todayHeight, talkHeight, systemsHeight, systemsMetrics }),
  )
    .toBeLessThanOrEqual(1);
  expect(systemsHeight).toBeGreaterThanOrEqual(64);

  const search = universe.locator(".universe-search");
  const searchRest = await material(search);
  await search.locator("input").focus();
  expect(await material(search)).toEqual(searchRest);
  await universe.locator(".nur-viewport").evaluate(element => { element.scrollTop = 0; });
  await page.waitForTimeout(150);
  await page.screenshot({ path: testInfo.outputPath("systems-cool-black-expanded-brain.png") });
  await universe.locator("#page-systems .universe-map-panel").screenshot({
    path: testInfo.outputPath("systems-expanded-star-brain-map.png"),
  });
});
