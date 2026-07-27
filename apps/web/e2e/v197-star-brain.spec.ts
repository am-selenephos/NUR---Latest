import { expect, test, type Locator } from "@playwright/test";

import { installNurMocks, json, mockUser } from "./helpers/nurMocks";

type LockupGeometry = {
  word: { element: number; text: number; tracking: number; translateX: number; fontSize: number };
  subtitle: { element: number; text: number; tracking: number; translateX: number; fontSize: number };
};

async function lockupGeometry(
  root: Locator,
  wordSelector: string,
  subtitleSelector: string,
): Promise<LockupGeometry> {
  return root.evaluate((element, selectors) => {
    const center = (selector: string) => {
      const target = element.querySelector<HTMLElement>(selector);
      if (!target) throw new Error(`Missing lockup element: ${selector}`);
      const rect = target.getBoundingClientRect();
      const range = document.createRange();
      range.selectNodeContents(target);
      const textRect = range.getBoundingClientRect();
      const style = getComputedStyle(target);
      const transform = style.transform === "none" ? new DOMMatrix() : new DOMMatrix(style.transform);
      return {
        element: rect.left + rect.width / 2,
        text: textRect.left + textRect.width / 2,
        tracking: Number.parseFloat(style.letterSpacing) || 0,
        translateX: transform.m41,
        fontSize: Number.parseFloat(style.fontSize),
      };
    };
    return {
      word: center(selectors.wordSelector),
      subtitle: center(selectors.subtitleSelector),
    };
  }, { wordSelector, subtitleSelector });
}

function expectSameUntranslatedCenter(geometry: LockupGeometry): void {
  const wordElement = geometry.word.element - geometry.word.translateX;
  const subtitleElement = geometry.subtitle.element - geometry.subtitle.translateX;
  const wordText = geometry.word.text - geometry.word.translateX;
  const subtitleText = geometry.subtitle.text - geometry.subtitle.translateX;
  expect(Math.abs(wordElement - subtitleElement)).toBeLessThanOrEqual(.25);
  expect(Math.abs(wordText - subtitleText)).toBeLessThanOrEqual(.25);
}

function expectEntryInkCompensation(geometry: LockupGeometry): void {
  expectSameUntranslatedCenter(geometry);
  const expectedNudge = geometry.word.fontSize <= 58 ? 2.3 : 2;
  expect(geometry.word.translateX - geometry.word.tracking / 2).toBeCloseTo(expectedNudge, 1);
  expect(geometry.subtitle.translateX - geometry.subtitle.tracking / 2).toBeCloseTo(2, 1);
}

function expectSystemsInkCompensation(geometry: LockupGeometry): void {
  expectSameUntranslatedCenter(geometry);
  const expectedNudge = geometry.word.fontSize <= 50
    ? .055
    : geometry.word.fontSize <= 62
      ? .0595
      : .058;
  expect(geometry.word.translateX / geometry.word.fontSize).toBeCloseTo(expectedNudge, 2);
  expect(geometry.subtitle.translateX).toBeCloseTo(2, 1);
}

test("login replays the exact V197 startup star before the Universe is revealed", async ({ page }, testInfo) => {
  await installNurMocks(page);
  let authenticated = false;
  await page.route("**/api/v1/auth/me", route => (
    authenticated
      ? json(route, mockUser)
      : json(route, { detail: "Not authenticated" }, 401)
  ));
  await page.route("**/api/v1/auth/login", async route => {
    authenticated = true;
    await new Promise(resolve => setTimeout(resolve, 1_200));
    await json(route, { ok: true });
  });
  await page.context().addCookies([{
    name: "nur_csrf",
    value: "login-transition-csrf",
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

  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("selene@nurapp.dev");
  await entry.locator("#f4-signin-password").fill("private-orbit-password");
  await entry.locator("#f4-signin-form button[type='submit']").click();

  const wait = entry.locator("#nur-v197-auth-wait");
  const startup = wait.locator(".nur-star-seal--startup[data-nur-v197-sigil-source='#iSpark']");
  await expect(wait).toBeVisible();
  await expect(startup.locator(":scope > .i-spark.spark.nur-v197-sigil-star")).toHaveCount(1);
  await expect(startup.locator(".ray")).toHaveCount(12);
  await expect(startup.locator(".ob")).toHaveCount(3);
  await expect(startup.locator(".spark-glow, .spark-halo, .spark-h2, .spark-core")).toHaveCount(4);
  await expect(startup.locator("svg, use")).toHaveCount(0);

  const exactClone = await entry.locator("body").evaluate(() => {
    const source = document.querySelector<HTMLElement>("#iSpark")!;
    const clone = document.querySelector<HTMLElement>(
      "#nur-v197-auth-wait .nur-star-seal--startup > .i-spark.spark",
    )!;
    return {
      sameInnerMarkup: source.innerHTML === clone.innerHTML,
      animation: getComputedStyle(clone).animationName,
    };
  });
  expect(exactClone.sameInnerMarkup).toBe(true);
  expect(exactClone.animation).toContain("sparkAppear");
  const waitPresentation = await wait.evaluate(element => {
    const style = getComputedStyle(element);
    return { background: style.backgroundColor, zIndex: Number(style.zIndex) };
  });
  expect(waitPresentation.background).toBe("rgb(0, 0, 0)");
  expect(waitPresentation.zIndex).toBeGreaterThan(999);
  await page.screenshot({ path: testInfo.outputPath("exact-v197-login-star.png") });

  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 20_000 });
  await expect(wait).toBeHidden();
  await expect(page).toHaveURL(/\/today$/);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator(".nur-star-seal > .spark").first()).toBeAttached();
  await expect(universe.locator(".nur-star-seal svg, .nur-star-seal use")).toHaveCount(0);
});

test("Entry replaces the center MasterStar with the exact interactive V43 brain", async ({ page }, testInfo) => {
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
    return document.fonts.ready;
  });

  const brain = entry.locator("#f4-core > #front-nur-star");
  await expect(brain).toBeVisible();
  await expect(entry.locator("#f4-core > .spark, #f4-core > .f4-master-star")).toHaveCount(0);
  await expect(entry.locator("#f4-core")).toHaveAttribute("data-nur-legacy-master-star", "removed");
  await expect(brain).toHaveAttribute("data-nur-source", "exact-v43-front-page-signup-v7-star-brain");
  await expect(brain).toHaveAttribute("data-nur-dispersal", "radial-circle");
  await expect(brain).toHaveAttribute("title", /drag to spin the mind.+double-click: neural storm.+scroll to zoom/);
  await expect(entry.locator("#nur-v43-exact-star-brain-runtime"))
    .toHaveAttribute("data-nur-runtime-hash", "8e249a704734e0d60bedff389883e90460338d14ac806c00ca6e5019b5834192");
  await expect(brain.locator("#nur-brain-canvas")).toBeVisible();

  const expectedPoints = testInfo.project.name.includes("mobile") ? "1355" : "2086";
  const expectedStemPoints = testInfo.project.name.includes("mobile") ? "97" : "147";
  await expect(brain).toHaveAttribute("data-nur-point-count", expectedPoints);
  await expect(brain).toHaveAttribute("data-nur-stem-point-count", expectedStemPoints);
  await expect(brain).toHaveAttribute("data-nur-sparkle-profile", "exact-galaxy-rig-star");
  await expect(brain).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");
  await expect(brain).toHaveAttribute("data-nur-anatomy", "cortex-cerebellum-brainstem");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurStarBrain?: { shatter?: unknown } }).nurStarBrain?.shatter
  ))).toBe("function");
  const circularDispersal = await brain.evaluate(element => {
    const style = getComputedStyle(element);
    return style.maskImage || style.webkitMaskImage;
  });
  expect(circularDispersal).toContain("radial-gradient");

  const geometry = await lockupGeometry(
    entry.locator(".f4-brand-copy"),
    ".f4-brand-word",
    ".f4-brand-sub",
  );

  await expect(entry.locator(".f4-brand-copy"))
    .toHaveAttribute("data-nur-lockup-axis", "center");
  await expect(entry.locator(".f4-brand-word"))
    .toHaveAttribute("data-nur-holographic-wordmark", "animated");

  const typography = await entry.locator(".f4-brand-copy").evaluate(element => {
    const word = getComputedStyle(element.querySelector<HTMLElement>(".f4-brand-word")!);
    const subtitle = getComputedStyle(element.querySelector<HTMLElement>(".f4-brand-sub")!);
    return {
      word: {
        family: word.fontFamily,
        weight: word.fontWeight,
        clip: word.backgroundClip,
        fill: word.webkitTextFillColor,
        animation: word.animationName,
        background: word.backgroundImage,
        position: word.backgroundPosition,
      },
      subtitle: {
        family: subtitle.fontFamily,
        style: subtitle.fontStyle,
        weight: subtitle.fontWeight,
        transform: subtitle.textTransform,
        tracking: Number.parseFloat(subtitle.letterSpacing),
      },
    };
  });
  expectEntryInkCompensation(geometry);
  expect(typography.word.family).toContain("Bodoni Moda");
  expect(typography.word.weight).toBe("500");
  expect(typography.word.clip).toBe("text");
  expect(typography.word.fill).toBe("rgba(0, 0, 0, 0)");
  expect(typography.word.animation).toContain("univPrism");
  expect(typography.word.background).toContain("linear-gradient");
  expect(typography.subtitle.family).toContain("Crimson Pro");
  expect(typography.subtitle.style).toBe("normal");
  expect(typography.subtitle.weight).toBe("400");
  expect(typography.subtitle.transform).toBe("uppercase");
  expect(typography.subtitle.tracking).toBeGreaterThan(0);
  await page.waitForTimeout(800);
  await expect.poll(() => entry.locator(".f4-brand-word").evaluate(element => (
    getComputedStyle(element).backgroundPosition
  ))).not.toBe(typography.word.position);

  const loadedFonts = await entry.locator("body").evaluate(async () => {
    await document.fonts.ready;
    return Array.from(document.fonts)
      .filter(face => face.family === "Crimson Pro" || face.family === "Bodoni Moda")
      .map(face => `${face.family}:${face.weight}:${face.style}:${face.status}`);
  });
  expect(loadedFonts).toContain("Crimson Pro:400:normal:loaded");
  expect(loadedFonts).toContain("Bodoni Moda:500:normal:loaded");

  const heroControls = await entry.locator("body").evaluate(() => {
    const rect = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element) throw new Error(`Missing Entry control: ${selector}`);
      const bounds = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        left: bounds.left,
        right: bounds.right,
        top: bounds.top,
        bottom: bounds.bottom,
        height: bounds.height,
        radius: Number.parseFloat(style.borderRadius),
        backdrop: style.backdropFilter,
        background: style.backgroundImage,
      };
    };
    const primary = rect("#f4-begin");
    const secondary = rect("#f4-what");
    const signIn = rect("#f4-signin");
    const stack = document.querySelector<HTMLElement>(".f4-brand-copy")!.getBoundingClientRect();
    const overlaps = (a: ReturnType<typeof rect>, b: ReturnType<typeof rect>) => (
      a.left < b.right && a.right > b.left && a.top < b.bottom && a.bottom > b.top
    );
    return {
      primary,
      secondary,
      signIn,
      stackBottom: stack.bottom,
      overlaps: [
        overlaps(primary, secondary),
        overlaps(primary, signIn),
        overlaps(secondary, signIn),
      ],
    };
  });
  expect(heroControls.overlaps).toEqual([false, false, false]);
  expect(heroControls.primary.height).toBeGreaterThanOrEqual(48);
  expect(heroControls.secondary.height).toBeGreaterThanOrEqual(48);
  expect(heroControls.signIn.height).toBeGreaterThanOrEqual(38);
  [heroControls.primary, heroControls.secondary, heroControls.signIn].forEach(control => {
    expect(control.radius).toBeGreaterThan(100);
    expect(control.backdrop).toContain("blur");
    expect(control.background).toContain("linear-gradient");
  });
  if (testInfo.project.name.includes("mobile")) {
    expect(heroControls.signIn.top).toBeGreaterThanOrEqual(heroControls.stackBottom + 7);
  }

  await brain.locator("#nur-brain-canvas").click();
  await expect(brain).toHaveAttribute("data-nur-last-interaction", "shatter");
});

test("NUR and Neural Upgrade Rewiring stay on one center axis at every responsive boundary", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The full breakpoint lock runs once in Chromium.");
  const widths = [390, 600, 720, 900, 1180, 1440] as const;

  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
    return document.fonts.ready;
  });

  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await entry.locator("body").evaluate(() => new Promise<void>(resolve => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    }));
    expectEntryInkCompensation(await lockupGeometry(
      entry.locator(".f4-brand-copy"),
      ".f4-brand-word",
      ".f4-brand-sub",
    ));
  }

  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "brand-lock-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "brand-lock-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 15_000 });
  await universe.locator("body").evaluate(() => document.fonts.ready);

  for (const width of widths) {
    await page.setViewportSize({ width, height: 900 });
    await universe.locator("body").evaluate(() => new Promise<void>(resolve => {
      requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
    }));
    expectSystemsInkCompensation(await lockupGeometry(
      universe.locator(".universe-map-title"),
      ".nur-v197-stable-wordmark",
      ".nur-master-subtitle",
    ));
  }
});

test("Systems map mounts only the exact brain and keeps the NUR lockup on one axis", async ({ page }, testInfo) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "star-brain-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "star-brain-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 15_000 });
  await universe.locator("body").evaluate(() => document.fonts.ready);

  const host = universe.locator(".universe-master-star");
  const brain = host.locator(":scope > #front-nur-star");
  await expect(brain).toBeVisible();
  await expect(host.locator(":scope > .f4-core")).toHaveCount(0);
  await expect(host).toHaveAttribute("data-nur-legacy-master-star", "removed");
  await expect(brain).toHaveAttribute("data-nur-source", "exact-v43-front-page-signup-v7-star-brain");
  await expect(brain).toHaveAttribute("data-nur-dispersal", "radial-circle");
  await expect(brain.locator("#nur-brain-canvas")).toBeVisible();
  await expect(universe.locator("#nur-v43-exact-star-brain-runtime"))
    .toHaveAttribute("data-nur-runtime-hash", "8e249a704734e0d60bedff389883e90460338d14ac806c00ca6e5019b5834192");

  const expectedPoints = testInfo.project.name.includes("mobile") ? "1355" : "2086";
  const expectedStemPoints = testInfo.project.name.includes("mobile") ? "97" : "147";
  await expect(brain).toHaveAttribute("data-nur-point-count", expectedPoints);
  await expect(brain).toHaveAttribute("data-nur-stem-point-count", expectedStemPoints);
  await expect(brain).toHaveAttribute("data-nur-sparkle-profile", "exact-galaxy-rig-star");
  await expect(brain).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");
  await expect(brain).toHaveAttribute("data-nur-anatomy", "cortex-cerebellum-brainstem");
  await expect.poll(() => universe.locator("body").evaluate(() => (
    typeof (window as unknown as { nurStarBrain?: { storm?: unknown } }).nurStarBrain?.storm
  ))).toBe("function");

  const geometry = await lockupGeometry(
    universe.locator(".universe-map-title"),
    ".nur-v197-stable-wordmark",
    ".nur-master-subtitle",
  );
  expectSystemsInkCompensation(geometry);
  await expect(universe.locator(".universe-map-title"))
    .toHaveAttribute("data-nur-lockup-axis", "center");
  await expect(universe.locator(".nur-v197-stable-wordmark"))
    .toHaveAttribute("data-nur-holographic-wordmark", "animated");

  const mapContract = await universe.locator(".universe-map-panel").evaluate(panel => {
    const visible = (element: HTMLElement) => {
      const style = getComputedStyle(element);
      const rect = element.getBoundingClientRect();
      return style.display !== "none"
        && style.visibility !== "hidden"
        && Number(style.opacity) > 0
        && rect.width > 0
        && rect.height > 0;
    };
    const nodes = Array.from(panel.querySelectorAll<HTMLElement>(".universe-system-node"))
      .filter(visible);
    const mantra = panel.ownerDocument.querySelector<HTMLElement>(".universe-map-mantra")!;
    const selected = panel.querySelector<HTMLElement>(".universe-system-node.active")!;
    const title = panel.querySelector<HTMLElement>(".universe-map-title")!;
    const wordmark = title.querySelector<HTMLElement>(":scope > .nur-v197-stable-wordmark")!;
    const subtitle = title.querySelector<HTMLElement>(":scope > .nur-master-subtitle")!;
    const wordmarkStyle = getComputedStyle(wordmark);
    const subtitleStyle = getComputedStyle(subtitle);
    const wordmarkTransform = wordmarkStyle.transform === "none"
      ? new DOMMatrix()
      : new DOMMatrix(wordmarkStyle.transform);
    const subtitleTransform = subtitleStyle.transform === "none"
      ? new DOMMatrix()
      : new DOMMatrix(subtitleStyle.transform);
    const wordmarkRect = wordmark.getBoundingClientRect();
    const subtitleRect = subtitle.getBoundingClientRect();
    const panelRect = panel.getBoundingClientRect();
    const mantraRect = mantra.getBoundingClientRect();
    const titleRect = title.getBoundingClientRect();
    const overlapWidth = Math.max(0, Math.min(panelRect.right, mantraRect.right) - Math.max(panelRect.left, mantraRect.left));
    const overlapHeight = Math.max(0, Math.min(panelRect.bottom, mantraRect.bottom) - Math.max(panelRect.top, mantraRect.top));
    return {
      visibleRings: Array.from(panel.querySelectorAll<HTMLElement>(".universe-rings"))
        .filter(visible).length,
      nodeCount: nodes.length,
      nativeGlyphs: nodes.filter(node => (
        node.querySelector<HTMLElement>(":scope > i")?.dataset.nurNativeGlyph === "true"
      )).length,
      generatedNodeArt: panel.querySelectorAll(
        ".universe-system-node svg, .universe-system-node [data-nur-star-seal='authentic']",
      ).length,
      widths: nodes.map(node => node.getBoundingClientRect().width),
      heights: nodes.map(node => node.getBoundingClientRect().height),
      headingSizes: nodes.map(node => Number.parseFloat(
        getComputedStyle(node.querySelector<HTMLElement>(":scope > span > b")!).fontSize,
      )),
      supportSizes: nodes.map(node => Number.parseFloat(
        getComputedStyle(node.querySelector<HTMLElement>(":scope > span > small")!).fontSize,
      )),
      titleOffset: titleRect.top - panelRect.top,
      wordmarkCount: title.querySelectorAll(":scope > b").length,
      wordmarkIsExactSource: wordmark.matches("b.nur-holo-word"),
      wordmarkTypography: {
        family: wordmarkStyle.fontFamily,
        size: Number.parseFloat(wordmarkStyle.fontSize),
        weight: wordmarkStyle.fontWeight,
        lineHeight: Number.parseFloat(wordmarkStyle.lineHeight),
        tracking: Number.parseFloat(wordmarkStyle.letterSpacing),
        animation: wordmarkStyle.animationName,
      },
      subtitleTypography: {
        family: subtitleStyle.fontFamily,
        size: Number.parseFloat(subtitleStyle.fontSize),
        weight: subtitleStyle.fontWeight,
        style: subtitleStyle.fontStyle,
        tracking: Number.parseFloat(subtitleStyle.letterSpacing),
      },
      lockupGeometry: {
        wordmarkWidth: wordmarkRect.width,
        subtitleWidth: subtitleRect.width,
        centerDelta: subtitleRect.left + subtitleRect.width / 2 - subtitleTransform.m41
          - (wordmarkRect.left + wordmarkRect.width / 2 - wordmarkTransform.m41),
      },
      mantraRelocated: !panel.contains(mantra)
        && Boolean(mantra.closest("#page-systems .universe-hero-copy")),
      mantraMapOverlap: overlapWidth * overlapHeight,
      selectedBackground: getComputedStyle(selected).backgroundImage,
    };
  });
  expect(mapContract.visibleRings).toBe(0);
  expect(mapContract.nodeCount).toBe(6);
  expect(mapContract.nativeGlyphs).toBe(6);
  expect(mapContract.generatedNodeArt).toBe(0);
  expect(Math.max(...mapContract.widths) - Math.min(...mapContract.widths)).toBeLessThanOrEqual(1);
  expect(Math.max(...mapContract.heights) - Math.min(...mapContract.heights)).toBeLessThanOrEqual(1);
  mapContract.headingSizes.forEach(size => expect(size).toBeGreaterThanOrEqual(14));
  mapContract.headingSizes.forEach(size => expect(size).toBeLessThanOrEqual(18));
  mapContract.supportSizes.forEach(size => expect(size).toBeGreaterThanOrEqual(12));
  expect(mapContract.titleOffset).toBeLessThanOrEqual(20);
  expect(mapContract.wordmarkCount).toBe(1);
  expect(mapContract.wordmarkIsExactSource).toBe(true);
  expect(mapContract.wordmarkTypography.family).toContain("Bodoni Moda");
  expect(mapContract.wordmarkTypography.weight).toBe("500");
  expect(mapContract.wordmarkTypography.animation).toContain("univPrism");
  expect(mapContract.subtitleTypography.family).toContain("Crimson Pro");
  expect(mapContract.subtitleTypography.weight).toBe("400");
  expect(mapContract.subtitleTypography.style).toBe("normal");
  expect(Math.abs(mapContract.lockupGeometry.centerDelta)).toBeLessThanOrEqual(.25);
  if (testInfo.project.name.includes("mobile")) {
    expect(mapContract.wordmarkTypography.size).toBe(50);
    expect(mapContract.wordmarkTypography.lineHeight).toBeCloseTo(42.5, 1);
    expect(mapContract.wordmarkTypography.tracking).toBeCloseTo(5.5, 1);
    expect(mapContract.subtitleTypography.size).toBe(12);
    expect(mapContract.subtitleTypography.tracking).toBeCloseTo(1.62, 1);
  } else {
    expect(mapContract.lockupGeometry.wordmarkWidth).toBeCloseTo(182, 1);
    expect(mapContract.lockupGeometry.subtitleWidth).toBeCloseTo(237.1875, 1);
    expect(mapContract.wordmarkTypography.size).toBe(72);
    expect(mapContract.wordmarkTypography.lineHeight).toBeCloseTo(56.88, 1);
    expect(mapContract.wordmarkTypography.tracking).toBe(9);
    expect(mapContract.subtitleTypography.size).toBe(14);
    expect(mapContract.subtitleTypography.tracking).toBeCloseTo(2.66, 1);
  }
  expect(mapContract.mantraRelocated).toBe(true);
  expect(mapContract.mantraMapOverlap).toBe(0);
  expect(mapContract.selectedBackground).toContain("33, 232, 255");
  expect(mapContract.selectedBackground).toContain("255, 58, 158");
  await page.screenshot({ path: testInfo.outputPath("systems-final.png") });

  await brain.locator("#nur-brain-canvas").click();
  await expect(brain).toHaveAttribute("data-nur-last-interaction", "shatter");
});
