import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks, json } from "./helpers/nurMocks";

const HOLOGRAPHIC_CONTROLS = [
  "button:not(.f4-brand)",
  "a.soft-button",
  "a.tiny-link",
  "a.universe-lens-tab",
  "a.nur-adjunct-button",
  ".scope-option",
  ".scope-chip",
  ".nur-chip",
].join(",");

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
  await expect(brain).toHaveAttribute("data-nur-galaxy-paint", "three-coordinated-celestial-rig-v1");
  await expect(brain).toHaveAttribute("data-nur-rig-depth", "webgl-threejs-perspective");
  await expect(brain).toHaveAttribute("data-nur-entry-systems-visual-contract", "shared-seven-spectrum-3d-v1");
  await expect(brain).toHaveAttribute("data-nur-opacity-profile", "crisp-dimensional-v2");
  await expect(brain).toHaveAttribute(
    "data-nur-render-profile",
    "one-raf-two-canonical-canvases-v1",
  );
  await expect(brain).toHaveAttribute("data-nur-spectrum-band-count", "7");
  await expect(brain).toHaveAttribute("data-nur-halo-contract", "entry-f4-ring-exact");
  const entryCoreSize = await entry.locator("#f4-core").evaluate(element => {
    const rect = element.getBoundingClientRect();
    return { width: rect.width, height: rect.height };
  });
  expect(entryCoreSize.width).toBeGreaterThanOrEqual(450);
  expect(Math.abs(entryCoreSize.width - entryCoreSize.height)).toBeLessThanOrEqual(1);
  const entryGalaxy = entry.locator("#space3d");
  await expect(entryGalaxy).toHaveAttribute("data-nur-galaxy-rig", "three-v197-seven-spectrum-3d");
  await expect(entryGalaxy).toHaveAttribute("data-nur-galaxy-layers", "far-dust-galaxy-super");

  const presentation = await root.evaluate((element, mindSelector) => {
    const rootStyle = getComputedStyle(element);
    const mindStyle = getComputedStyle(element.querySelector<HTMLElement>(mindSelector)!);
    return {
      rootBackground: rootStyle.backgroundImage,
      rootBackgroundColor: rootStyle.backgroundColor,
      mindBackground: mindStyle.backgroundImage,
      mindClip: mindStyle.backgroundClip,
      mindFill: mindStyle.webkitTextFillColor,
      mindAnimation: mindStyle.animationName,
      mindFilter: mindStyle.filter,
    };
  }, ".f4-title em");
  expect(presentation.rootBackground).toBe("none");
  expect(presentation.rootBackgroundColor).toBe("rgb(0, 0, 0)");
  expect(presentation.mindBackground).toContain("linear-gradient");
  expect(presentation.mindClip).toBe("text");
  expect(presentation.mindFill).toBe("rgba(0, 0, 0, 0)");
  expect(presentation.mindAnimation).toContain("nurMindGold");
  expect(presentation.mindFilter).toContain("drop-shadow");

  const entryControlCoverage = await entry.locator("body").evaluate((_body, controlSelector) => {
    const controls = Array.from(document.querySelectorAll<HTMLElement>(controlSelector))
      .filter(element => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
      });
    return {
      total: controls.length,
      missing: controls
        .filter(control => !control.querySelector(":scope > .nur-holo-film"))
        .map(control => control.className),
      incompleteSpectrum: controls
        .filter(control => {
          const film = control.querySelector(".nur-holo-film");
          const background = film ? getComputedStyle(film, "::before").backgroundImage : "";
          return !background.includes("255, 82, 111")
            || !background.includes("255, 142, 53")
            || !background.includes("255, 211, 90")
            || !background.includes("102, 240, 145")
            || !background.includes("60, 211, 255")
            || !background.includes("103, 126, 255")
            || !background.includes("193, 96, 255")
            || !background.includes("255, 88, 190");
        })
        .map(control => control.className),
      badGlass: controls
        .filter(control => {
          const style = getComputedStyle(control);
          const base = style.backgroundColor.match(/[\d.]+/g)?.map(Number) ?? [];
          const alpha = base[3] ?? 1;
          return base.slice(0, 3).some(channel => channel !== 0)
            || alpha > 0.28
            || !style.backdropFilter.includes("blur(12px)");
        })
        .map(control => {
          const style = getComputedStyle(control);
          return `${control.className}|background=${style.backgroundColor}|backdrop=${style.backdropFilter}`;
        }),
      badGoldRim: controls
        .filter(control => {
          const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
          return !film || !getComputedStyle(film).boxShadow.includes("rgba(255, 222, 153, 0.24)");
        })
        .map(control => {
          const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
          return `${control.className}|film-shadow=${film ? getComputedStyle(film).boxShadow : "missing"}`;
        }),
      opaqueFilm: controls
        .filter(control => {
          const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
          const selected = control.matches(
            ".active, .selected, .f4-primary, [aria-current='page'], [aria-selected='true'], [aria-checked='true']",
          );
          const filmOpacity = film ? parseFloat(getComputedStyle(film).opacity) : 1;
          const fillOpacity = film ? parseFloat(getComputedStyle(film, "::before").opacity) : 1;
          const rimOpacity = film ? parseFloat(getComputedStyle(film, "::after").opacity) : 1;
          return !film
            || filmOpacity > .09
            || filmOpacity * fillOpacity > .09
            || filmOpacity * rimOpacity > .09
            || (selected && filmOpacity < .09);
        })
        .map(control => control.className),
    };
  }, HOLOGRAPHIC_CONTROLS);
  expect(entryControlCoverage.total).toBeGreaterThanOrEqual(3);
  expect(entryControlCoverage.missing).toEqual([]);
  expect(entryControlCoverage.incompleteSpectrum).toEqual([]);
  expect(entryControlCoverage.badGlass).toEqual([]);
  expect(entryControlCoverage.badGoldRim).toEqual([]);
  expect(entryControlCoverage.opaqueFilm).toEqual([]);
  await expect(entry.locator("html")).toHaveCSS("animation-name", "none");
  const entryPrimaryFilm = entry.locator(".f4-primary > .nur-holo-film").first();
  await expect.poll(() => entryPrimaryFilm.evaluate(element => (
    getComputedStyle(element, "::before").animationName
  ))).toContain("nurHoloEntryPhase");
  await expect(entry.locator(".f4-primary").first())
    .toHaveCSS("box-shadow", /rgba\(255, 211, 90, 0\.19\)/);
  const primaryTransformBefore = await entryPrimaryFilm.evaluate(element => (
    getComputedStyle(element, "::before").transform
  ));
  await page.waitForTimeout(360);
  const primaryTransformAfter = await entryPrimaryFilm.evaluate(element => (
    getComputedStyle(element, "::before").transform
  ));
  expect(primaryTransformAfter).not.toBe(primaryTransformBefore);
  const entrySecondary = entry.locator(".f4-link").first();
  const entrySecondaryFilm = entrySecondary.locator(":scope > .nur-holo-film");
  const secondaryTransformBefore = await entrySecondaryFilm.evaluate(element => (
    getComputedStyle(element, "::before").transform
  ));
  await page.waitForTimeout(360);
  const secondaryTransformAfter = await entrySecondaryFilm.evaluate(element => (
    getComputedStyle(element, "::before").transform
  ));
  expect(secondaryTransformAfter).not.toBe(secondaryTransformBefore);
  await entrySecondary.hover();
  await expect(entrySecondaryFilm).toHaveCSS("filter", /brightness/);

  await expect.poll(async () => (await canvasSignal(canvas)).lit).toBeGreaterThan(70);
  const first = await canvasSignal(canvas);
  await page.waitForTimeout(420);
  const second = await canvasSignal(canvas);
  expect(second.checksum).not.toBe(first.checksum);
  await page.screenshot({ path: testInfo.outputPath("entry-cool-black-galaxy.png") });

  await entry.locator("#f4-signin").click();
  const beginSwitch = entry.locator('.f4-mode[data-mode="signin"].active .f4-switch button[data-switch="signup"]');
  await expect(beginSwitch).toBeVisible();
  const beginSwitchMaterial = await beginSwitch.evaluate(element => {
    const rect = element.getBoundingClientRect();
    const style = getComputedStyle(element);
    return {
      width: rect.width,
      height: rect.height,
      background: style.backgroundColor,
      backdrop: style.backdropFilter,
      radius: style.borderRadius,
    };
  });
  expect(beginSwitchMaterial.width).toBeGreaterThanOrEqual(132);
  expect(beginSwitchMaterial.height).toBeGreaterThanOrEqual(35);
  const beginSwitchBackground = beginSwitchMaterial.background.match(/[\d.]+/g)?.map(Number) ?? [];
  expect(beginSwitchBackground.slice(0, 3)).toEqual([0, 0, 0]);
  expect(beginSwitchBackground[3]).toBeLessThanOrEqual(.03);
  expect(beginSwitchMaterial.backdrop).toContain("blur(10px)");
  expect(beginSwitchMaterial.radius).toBe("999px");
  await page.screenshot({ path: testInfo.outputPath("entry-signin-begin-switch.png") });
});

test("Today, Talk, and Systems share one brain paint and one calm composer proportion", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Visual mandate capture runs once in desktop Chromium.");
  await page.setViewportSize({ width: 1440, height: 900 });
  const universe = await authenticatedUniverse(page, "/today");
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 15_000 });

  const todayBrain = universe.locator("#page-today #front-nur-star");
  await expect(todayBrain).toHaveAttribute("data-nur-surface", "today");
  await expect(todayBrain).toHaveAttribute("data-nur-scale-profile", "entry-exact");
  await expect(todayBrain).toHaveAttribute("data-nur-galaxy-paint", "three-coordinated-celestial-rig-v1");
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
  await expect(systemsBrain).toHaveAttribute("data-nur-galaxy-paint", "three-coordinated-celestial-rig-v1");
  await expect(systemsBrain).toHaveAttribute("data-nur-rig-depth", "webgl-threejs-perspective");
  await expect(systemsBrain).toHaveAttribute("data-nur-entry-systems-visual-contract", "shared-seven-spectrum-3d-v1");
  await expect(systemsBrain).toHaveAttribute("data-nur-opacity-profile", "crisp-dimensional-v2");
  await expect(systemsBrain).toHaveAttribute(
    "data-nur-render-profile",
    "one-raf-two-canonical-canvases-v1",
  );
  await expect(systemsBrain).toHaveAttribute("data-nur-spectrum-band-count", "7");
  await expect(systemsBrain).toHaveAttribute("data-nur-halo-contract", "entry-f4-ring-exact");
  const systemsHalos = universe.locator(
    "#page-systems .universe-master-star > .nur-v197-brain-orbit-halo",
  );
  await expect(systemsHalos).toHaveCount(3);
  await expect(systemsHalos.first()).toHaveAttribute("data-nur-halo-source", "entry-f4-ring");
  const haloGeometry = await systemsHalos.evaluateAll(elements => {
    const host = elements[0]?.parentElement?.getBoundingClientRect();
    if (!host) return [];
    const hostCenter = { x: host.left + host.width / 2, y: host.top + host.height / 2 };
    return elements.map(element => {
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        variant: element.classList.contains("three")
          ? "three"
          : element.classList.contains("two") ? "two" : "one",
        centerDeltaX: Math.abs(rect.left + rect.width / 2 - hostCenter.x),
        centerDeltaY: Math.abs(rect.top + rect.height / 2 - hostCenter.y),
        width: parseFloat(style.width),
        ratio: parseFloat(style.width) / parseFloat(style.height),
        border: style.borderTopStyle,
        borderColor: style.borderTopColor,
        shadow: style.boxShadow,
      };
    });
  });
  expect(haloGeometry).toHaveLength(3);
  const exactEntryHaloColors: Record<string, string> = {
    one: "rgba(248, 217, 138, 0.16)",
    two: "rgba(255, 222, 150, 0.12)",
    three: "rgba(255, 190, 122, 0.11)",
  };
  for (const halo of haloGeometry) {
    expect(halo.centerDeltaX).toBeLessThanOrEqual(1);
    expect(halo.centerDeltaY).toBeLessThanOrEqual(1);
    expect(halo.width).toBeGreaterThan(200);
    expect(halo.ratio).toBeCloseTo(2.15, 1);
    expect(halo.border).toBe("solid");
    expect(halo.borderColor).toBe(exactEntryHaloColors[halo.variant]);
    expect(halo.shadow).toContain("rgba(255, 173, 50, 0.024)");
  }
  await expect.poll(async () => (
    await canvasSignal(systemsBrain.locator("#nur-brain-canvas"))
  ).lit).toBeGreaterThan(70);

  const controlCoverage = await universe.locator("body").evaluate((_body, controlSelector) => {
    const controls = Array.from(document.querySelectorAll<HTMLElement>(controlSelector))
      .filter(element => {
        const rect = element.getBoundingClientRect();
        const style = getComputedStyle(element);
        return rect.width > 0 && rect.height > 0 && style.display !== "none" && style.visibility !== "hidden";
      });
    return {
      total: controls.length,
      missing: controls
        .filter(control => !control.querySelector(":scope > .nur-holo-film"))
        .map(control => `${control.tagName.toLowerCase()}.${control.className}`),
      incompleteSpectrum: controls
        .filter(control => {
          if (control.matches(
            ".clean-nav-button[data-page='today'],"
            + ".clean-nav-button[data-page='talk'],"
            + ".clean-nav-button[data-page='journal'],"
            + ".clean-nav-button[data-page='plan']",
          )) return false;
          const film = control.querySelector(".nur-holo-film");
          const background = film ? getComputedStyle(film, "::before").backgroundImage : "";
          return !background.includes("255, 82, 111")
            || !background.includes("255, 142, 53")
            || !background.includes("255, 211, 90")
            || !background.includes("102, 240, 145")
            || !background.includes("60, 211, 255")
            || !background.includes("103, 126, 255")
            || !background.includes("193, 96, 255")
            || !background.includes("255, 88, 190");
        })
        .map(control => `${control.tagName.toLowerCase()}.${control.className}`),
      badGlass: controls
        .filter(control => {
          const style = getComputedStyle(control);
          const base = style.backgroundColor.match(/[\d.]+/g)?.map(Number) ?? [];
          const alpha = base[3] ?? 1;
          const expectedBlur = control.matches(".universe-system-node") ? "blur(14px)" : "blur(12px)";
          return base.slice(0, 3).some(channel => channel !== 0)
            || alpha > 0.28
            || !style.backdropFilter.includes(expectedBlur);
        })
        .map(control => {
          const style = getComputedStyle(control);
          return `${control.tagName.toLowerCase()}.${control.className}|background=${style.backgroundColor}|backdrop=${style.backdropFilter}`;
        }),
      badGoldRim: controls
        .filter(control => {
          const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
          const expectedRim = control.matches(".universe-system-node")
            ? "rgba(255, 222, 153, 0.14)"
            : "rgba(255, 222, 153, 0.24)";
          return !film || !getComputedStyle(film).boxShadow.includes(expectedRim);
        })
        .map(control => {
          const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
          return `${control.tagName.toLowerCase()}.${control.className}|film-shadow=${film ? getComputedStyle(film).boxShadow : "missing"}`;
        }),
      glowingControls: controls
        .filter(control => getComputedStyle(control).boxShadow !== "none")
        .map(control => (
          `${control.tagName.toLowerCase()}.${control.className}`
          + `|shadow=${getComputedStyle(control).boxShadow}`
        )),
      opaqueFilm: controls
        .filter(control => {
          const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
          const selected = control.matches(
            ".active, .selected, .f4-primary, [aria-current='page'], [aria-selected='true'], [aria-checked='true']",
          );
          const quietPersonalOrbit = control.matches(
            ".clean-nav-button[data-page='today'],"
            + ".clean-nav-button[data-page='talk'],"
            + ".clean-nav-button[data-page='journal'],"
            + ".clean-nav-button[data-page='plan']",
          );
          const filmOpacity = film ? parseFloat(getComputedStyle(film).opacity) : 1;
          const fillOpacity = film ? parseFloat(getComputedStyle(film, "::before").opacity) : 1;
          const rimOpacity = film ? parseFloat(getComputedStyle(film, "::after").opacity) : 1;
          return !film
            || filmOpacity > .09
            || filmOpacity * fillOpacity > .09
            || filmOpacity * rimOpacity > .09
            || (selected && !quietPersonalOrbit && filmOpacity < .09);
        })
        .map(control => `${control.tagName.toLowerCase()}.${control.className}`),
    };
  }, HOLOGRAPHIC_CONTROLS);
  // The retired research/community/consultation/expert/composer controls are
  // physically absent; every remaining visible control still carries the
  // complete material contract.
  expect(controlCoverage.total).toBe(28);
  expect(controlCoverage.missing).toEqual([]);
  expect(controlCoverage.incompleteSpectrum).toEqual([]);
  expect(controlCoverage.badGlass).toEqual([]);
  expect(controlCoverage.badGoldRim).toEqual([]);
  expect(controlCoverage.glowingControls).toEqual([]);
  expect(controlCoverage.opaqueFilm).toEqual([]);

  const personalOrbitMaterials = await universe.locator(
    ".clean-nav-button[data-page='today'],"
    + ".clean-nav-button[data-page='talk'],"
    + ".clean-nav-button[data-page='journal'],"
    + ".clean-nav-button[data-page='plan']",
  ).evaluateAll(controls => controls.map(control => {
    const style = getComputedStyle(control);
    const film = control.querySelector<HTMLElement>(":scope > .nur-holo-film");
    return {
      background: style.backgroundImage,
      backgroundColor: style.backgroundColor,
      shadow: style.boxShadow,
      filmOpacity: film ? parseFloat(getComputedStyle(film).opacity) : 1,
      filmSpectrum: film ? getComputedStyle(film, "::before").backgroundImage : "",
    };
  }));
  expect(personalOrbitMaterials).toHaveLength(4);
  for (const control of personalOrbitMaterials) {
    for (const color of [
      "255, 155, 168",
      "255, 195, 157",
      "255, 232, 163",
      "159, 240, 206",
      "155, 220, 255",
      "173, 184, 255",
      "223, 173, 255",
    ]) expect(control.background).toContain(color);
    expect(control.backgroundColor).toBe("rgba(0, 0, 0, 0.08)");
    expect(control.shadow).toBe("none");
    expect(control.filmOpacity).toBeGreaterThanOrEqual(.04);
    expect(control.filmOpacity).toBeLessThanOrEqual(.06);
    for (const color of [
      "255, 82, 111",
      "255, 158, 74",
      "255, 222, 92",
      "126, 237, 130",
      "99, 224, 255",
      "121, 143, 255",
      "194, 138, 255",
    ]) expect(control.filmSpectrum).toContain(color);
  }

  const italicGold = await universe.locator("#page-systems .nur-systems-epigraph").evaluate(element => {
    const style = getComputedStyle(element);
    return {
      background: style.backgroundImage,
      clip: style.backgroundClip,
      fill: style.webkitTextFillColor,
      animation: style.animationName,
    };
  });
  expect(italicGold.background).toContain("linear-gradient");
  expect(italicGold.clip).toBe("text");
  expect(italicGold.fill).toBe("rgba(0, 0, 0, 0)");
  expect(italicGold.animation).toContain("nurSystemsItalicGold");

  const nodeMaterials = await universe.locator(
    "#page-systems .universe-system-node:not(.neural)",
  ).evaluateAll(nodes => nodes
    .filter(node => {
      const rect = node.getBoundingClientRect();
      return rect.width > 0 && rect.height > 0;
    })
    .map(node => {
      const style = getComputedStyle(node);
      const film = node.querySelector<HTMLElement>(":scope > .nur-holo-film");
      const title = node.querySelector<HTMLElement>(":scope > span > b");
      const note = node.querySelector<HTMLElement>(":scope > span > small");
      return {
        label: title?.textContent?.trim() ?? "",
        backgroundColor: style.backgroundColor,
        backgroundImage: style.backgroundImage,
        backdropFilter: style.backdropFilter,
        borderWidth: style.borderTopWidth,
        borderRadius: style.borderRadius,
        nodeBefore: getComputedStyle(node, "::before").content,
        nodeAfter: getComputedStyle(node, "::after").content,
        filmTag: film?.tagName ?? "",
        filmShadow: film ? getComputedStyle(film).boxShadow : "",
        filmOpacity: film ? parseFloat(getComputedStyle(film).opacity) : 0,
        prismOpacity: film ? parseFloat(getComputedStyle(film, "::before").opacity) : 0,
        prismImage: film ? getComputedStyle(film, "::before").backgroundImage : "",
        titleColor: title ? getComputedStyle(title).color : "",
        noteColor: note ? getComputedStyle(note).color : "",
      };
    }));
  expect(nodeMaterials).toHaveLength(6);
  expect(nodeMaterials.map(node => node.label)).toEqual(
    expect.arrayContaining(["Ambition", "Creation", "Rebuild", "Growth", "Connection", "Introspection"]),
  );
  for (const node of nodeMaterials) {
    const background = node.backgroundColor.match(/[\d.]+/g)?.map(Number) ?? [];
    expect(background.slice(0, 3), `${node.label} must use neutral black glass`).toEqual([0, 0, 0]);
    expect(background[3], `${node.label} glass must stay translucent`).toBeLessThanOrEqual(.28);
    expect(node.backdropFilter, `${node.label} must retain frosted depth`).toContain("blur(14px)");
    expect(node.borderWidth, `${node.label} must keep a hairline rim`).toBe("1px");
    expect(parseFloat(node.borderRadius), `${node.label} must stay refined, not pill-like`).toBeLessThanOrEqual(8);
    expect(node.filmTag, `${node.label} film must not collapse into the icon slot`).toBe("NUR-HOLO-FILM");
    expect(node.filmShadow, `${node.label} must carry the soft gold edge light`)
      .toContain("rgba(255, 222, 153, 0.14)");
    expect(node.filmOpacity, `${node.label} film must stay at or below nine percent`)
      .toBeLessThanOrEqual(.09);
    expect(node.filmOpacity * node.prismOpacity, `${node.label} prism must remain below ten percent effective opacity`)
      .toBeLessThanOrEqual(.09);
    expect(node.prismImage).toContain("255, 211, 90");
    expect(node.prismImage).toContain("255, 82, 111");
    expect(node.prismImage).toContain("60, 211, 255");
    expect(node.prismImage).toContain("102, 240, 145");
    expect(node.nodeBefore).toBe("none");
    expect(node.nodeAfter).toBe("none");
    expect(node.titleColor).toBe("rgba(255, 248, 230, 0.96)");
    expect(node.noteColor).toBe("rgba(242, 208, 134, 0.7)");
  }

  const quietNode = universe.locator(
    "#page-systems .universe-system-node:not(.active):not(.neural)",
  ).first();
  const quietDefault = await quietNode.evaluate(node => {
    const rect = node.getBoundingClientRect();
    const film = node.querySelector<HTMLElement>(":scope > .nur-holo-film")!;
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      shadow: getComputedStyle(node).boxShadow,
      filmOpacity: parseFloat(getComputedStyle(film).opacity),
    };
  });
  await quietNode.hover();
  await expect.poll(async () => quietNode.evaluate(node => {
    const film = node.querySelector<HTMLElement>(":scope > .nur-holo-film")!;
    return parseFloat(getComputedStyle(film).opacity);
  })).toBeGreaterThan(quietDefault.filmOpacity);
  const quietHover = await quietNode.evaluate(node => {
    const rect = node.getBoundingClientRect();
    const film = node.querySelector<HTMLElement>(":scope > .nur-holo-film")!;
    return {
      left: rect.left,
      top: rect.top,
      width: rect.width,
      height: rect.height,
      shadow: getComputedStyle(node).boxShadow,
      filmOpacity: parseFloat(getComputedStyle(film).opacity),
    };
  });
  expect(quietHover.left).toBeCloseTo(quietDefault.left, 1);
  expect(quietHover.top).toBeCloseTo(quietDefault.top, 1);
  expect(quietHover.width).toBeCloseTo(quietDefault.width, 1);
  expect(quietHover.height).toBeCloseTo(quietDefault.height, 1);
  expect(quietDefault.shadow).toBe("none");
  expect(quietHover.shadow).toBe("none");
  expect(quietHover.filmOpacity).toBeGreaterThan(quietDefault.filmOpacity);

  await page.mouse.move(1400, 8);
  await universe.locator("#page-systems .universe-system-node.active").focus();
  await page.keyboard.press("Tab");
  await expect(quietNode).toBeFocused();
  await expect.poll(() => quietNode.evaluate(node => node.matches(":focus-visible"))).toBe(true);
  await expect(quietNode).toHaveCSS("outline-style", "solid");
  const activeFilmOpacity = await universe.locator(
    "#page-systems .universe-system-node.active > .nur-holo-film",
  ).evaluate(element => parseFloat(getComputedStyle(element).opacity));
  expect(activeFilmOpacity).toBeGreaterThan(quietDefault.filmOpacity);
  await quietNode.evaluate(node => node.blur());

  // Authenticated controls retain a complete translucent spectrum, but their
  // film is deliberately still. Animating an inherited root custom property
  // restyled the entire V197 tree every frame.
  await expect(universe.locator("html")).toHaveCSS("animation-name", "none");
  const selectedControlFilm = universe.locator(
    "#page-systems .universe-system-node.active > .nur-holo-film",
  );
  const selectedTransformBefore = await selectedControlFilm.evaluate(element => (
    getComputedStyle(element, "::before").transform
  ));
  await page.waitForTimeout(360);
  const selectedTransformAfter = await selectedControlFilm.evaluate(element => (
    getComputedStyle(element, "::before").transform
  ));
  expect(selectedTransformAfter).toBe(selectedTransformBefore);
  await expect.poll(() => selectedControlFilm.evaluate(element => (
    getComputedStyle(element, "::before").backgroundImage
  ))).toContain("linear-gradient");

  const mapGeometry = await universe.locator("#page-systems .universe-map-panel").evaluate(panel => {
    const panelRect = panel.getBoundingClientRect();
    const inspect = (element: Element) => {
      const rect = element.getBoundingClientRect();
      return {
        position: getComputedStyle(element).position,
        left: rect.left - panelRect.left,
        top: rect.top - panelRect.top,
        right: panelRect.right - rect.right,
        bottom: panelRect.bottom - rect.bottom,
      };
    };
    const addSystem = panel.querySelector(".universe-add-system");
    return {
      addSystem: addSystem ? inspect(addSystem) : null,
      nodes: Array.from(panel.querySelectorAll(".universe-system-node:not(.neural)")).map(inspect),
    };
  });
  expect(mapGeometry.addSystem).not.toBeNull();
  expect(mapGeometry.addSystem?.position).toBe("absolute");
  expect(mapGeometry.addSystem?.left).toBeGreaterThanOrEqual(0);
  expect(mapGeometry.addSystem?.top).toBeGreaterThanOrEqual(0);
  expect(mapGeometry.addSystem?.right).toBeGreaterThanOrEqual(0);
  for (const node of mapGeometry.nodes) {
    expect(node.position).toBe("absolute");
    expect(node.left).toBeGreaterThanOrEqual(0);
    expect(node.right).toBeGreaterThanOrEqual(0);
  }

  const systemsBody = universe.locator("body");
  await expect(systemsBody).toHaveClass(/nur-v197-systems-active/);
  await expect(universe.locator(".nur-v178-warmth-film")).toHaveCSS("display", "none");

  const surfaceMaterials = await universe.locator("#page-systems").evaluate(root => {
    const selectors = [
      ":scope",
      ".universe-map-panel",
      ".universe-insight-panel",
    ];
    return selectors.map(selector => {
      const element = selector === ":scope" ? root : root.querySelector<HTMLElement>(selector);
      if (!element) return {
        selector,
        missing: true,
        backgroundColor: "",
        backgroundImage: "",
        sheenImage: "",
      };
      const style = getComputedStyle(element);
      return {
        selector,
        missing: false,
        backgroundColor: style.backgroundColor,
        backgroundImage: style.backgroundImage,
        sheenImage: selector === ":scope" ? "" : getComputedStyle(element, "::before").backgroundImage,
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
  const systemsPanelSheens = surfaceMaterials
    .filter(surface => surface.selector !== ":scope")
    .map(surface => surface.sheenImage)
    .join(" ");
  expect(systemsPanelSheens).toContain("255, 211, 90");
  expect(systemsPanelSheens).toContain("255, 82, 111");
  expect(systemsPanelSheens).toContain("193, 107, 255");
  expect(systemsPanelSheens).toContain("33, 232, 255");
  expect(systemsPanelSheens).toContain("105, 240, 180");

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
          shadow: style.boxShadow,
          sheenImage: getComputedStyle(element, "::before").backgroundImage,
        };
      });
  });
  expect(allPanelMaterials).toHaveLength(2);
  for (const panel of allPanelMaterials) {
    const channels = panel.backgroundColor.match(/[\d.]+/g)?.slice(0, 3).map(Number) ?? [];
    expect(channels, `${panel.identity} must expose an RGB black base`).toHaveLength(3);
    expect(
      Math.max(...channels) - Math.min(...channels),
      `${panel.identity} must remain neutral black, not blue-tinted: ${panel.backgroundColor}`,
    ).toBeLessThanOrEqual(1);
    expect(panel.shadow, `${panel.identity} must not cast an authenticated panel glow`).toBe("none");
    expect(panel.sheenImage, `${panel.identity} must carry full-spectrum optical light`)
      .toContain("33, 232, 255");
  }

  const galaxy = universe.locator("#space3d");
  await expect(galaxy).toBeVisible();
  await expect(galaxy).toHaveAttribute("data-nur-galaxy-rig", "three-v197-seven-spectrum-3d");
  await expect(galaxy).toHaveAttribute("data-nur-galaxy-layers", "far-dust-galaxy-super");
  const particleDiagnostics = await galaxy.evaluate(() => (
    (window as unknown as {
      nurGalaxy?: {
        getParticleDiagnostics?: () => {
          total: number;
          transient: number;
          byKind: Record<string, number>;
        };
      };
    }).nurGalaxy?.getParticleDiagnostics?.() ?? { total: 0, transient: 0, byKind: {} }
  ));
  expect(particleDiagnostics.total - particleDiagnostics.transient).toBe(2_400);
  expect(particleDiagnostics.byKind).toMatchObject({
    galaxy: 1_100,
    far: 900,
    dust: 340,
    super: 60,
  });
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

  await expect(universe.locator(".universe-composer--v173")).toHaveCount(0);
  await expect(universe.locator(".universe-search")).toHaveCount(0);
  expect(
    Math.abs(todayHeight - talkHeight),
    JSON.stringify({ todayHeight, talkHeight }),
  )
    .toBeLessThanOrEqual(1);
  await universe.locator(".nur-viewport").evaluate(element => { element.scrollTop = 0; });
  await page.waitForTimeout(150);
  await page.screenshot({ path: testInfo.outputPath("systems-cool-black-expanded-brain.png") });
  await universe.locator("#page-systems .universe-map-panel").screenshot({
    path: testInfo.outputPath("systems-expanded-star-brain-map.png"),
  });
});

test("Orbit uses the exact loading sigil and keeps its empty actions below the star field", async ({ page }, testInfo) => {
  test.skip(
    !["chromium-desktop", "chromium-mobile"].includes(testInfo.project.name),
    "Orbit visual contract is owned by Chromium desktop and mobile.",
  );
  const mobile = testInfo.project.name === "chromium-mobile";
  await installNurMocks(page);
  await page.route("**/api/v1/orbit-field", route => json(route, {
    people: [],
    groups: [],
    relationships: [],
    layout: [],
    thread_counts: {},
  }));
  await page.route("**/api/v1/orbit-threads", route => json(route, []));
  await page.context().addCookies([
    { name: "nur_session", value: "orbit-empty-mandate", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "orbit-empty-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.setViewportSize(mobile ? { width: 393, height: 851 } : { width: 1440, height: 900 });
  await page.goto("/universe/orbits", { waitUntil: "load" });

  const universe = page.frameLocator("#nur-universe-stage");
  const root = universe.locator("#nur-orbit-root");
  await expect(root).toBeVisible({ timeout: 20_000 });
  if (mobile) {
    await root.locator('[data-orbit-view="orbit"]').click();
  }
  const anchor = root.locator(".nur-orbit-anchor-sigil");
  const startup = anchor.locator(
    ".nur-star-seal--startup[data-nur-v197-sigil-source='#iSpark']",
  );
  await expect(anchor).toHaveAttribute("data-nur-orbit-anchor", "v197-startup-sigil");
  await expect(startup).toHaveCount(1);
  const startupStar = startup.locator(":scope > .i-spark.spark.nur-v197-sigil-star");
  await expect(startupStar).toHaveCount(1);
  await expect(startupStar).not.toHaveClass(/f4-master-star|nur-v33-master|nur-v34-exact-symbol/);
  await expect(startup.locator(".ray")).toHaveCount(12);
  await expect(startup.locator(".ob")).toHaveCount(3);
  const satelliteMotion = await startup.locator(".ob").evaluateAll(elements => elements.map(element => ({
    classes: Array.from(element.classList),
    animations: getComputedStyle(element).animationName,
  })));
  expect(satelliteMotion).toEqual([
    { classes: ["ob", "ob1"], animations: expect.stringContaining("o1") },
    { classes: ["ob", "ob2"], animations: expect.stringContaining("o2") },
    { classes: ["ob", "ob3"], animations: expect.stringContaining("o3") },
  ]);
  await expect(startup.locator(".spark-glow, .spark-halo, .spark-h2, .spark-core")).toHaveCount(4);
  await expect(startup.locator("svg, use")).toHaveCount(0);

  const empty = root.locator(".nur-orbit-empty");
  await expect(empty).toHaveAttribute("data-nur-orbit-empty-layout", "bottom-footer");
  await expect(empty).toContainText(
    "Your Orbit begins with one person, one signal, one shared field.",
  );
  await expect(empty.locator(".nur-orbit-empty-actions > button")).toHaveCount(2);

  const layout = await root.evaluate(element => {
    const rect = (selector: string) => {
      const box = element.querySelector<HTMLElement>(selector)?.getBoundingClientRect();
      if (!box) return null;
      return {
        left: box.left,
        top: box.top,
        right: box.right,
        bottom: box.bottom,
        width: box.width,
        height: box.height,
      };
    };
    const canvas = rect(".nur-orbit-canvas");
    const sigil = rect(".nur-orbit-anchor-sigil");
    const footer = rect(".nur-orbit-empty");
    const footerMessage = rect(".nur-orbit-empty > p");
    const footerActions = rect(".nur-orbit-empty-actions");
    const actionButtons = Array.from(
      element.querySelectorAll<HTMLElement>(".nur-orbit-empty-actions > button"),
      button => button.getBoundingClientRect(),
    );
    const actionCluster = actionButtons.length > 0
      ? {
          left: Math.min(...actionButtons.map(button => button.left)),
          right: Math.max(...actionButtons.map(button => button.right)),
        }
      : null;
    const panelShadows = Array.from(element.querySelectorAll<HTMLElement>(
      ".nur-orbit-field-surface,.nur-orbit-rail,.nur-orbit-detail",
    )).map(panel => ({
      className: panel.className,
      shadow: getComputedStyle(panel).boxShadow,
    }));
    const controlShadows = Array.from(element.querySelectorAll<HTMLElement>("button"))
      .filter(button => button.getBoundingClientRect().height > 0)
      .map(button => ({
        label: button.textContent?.trim() ?? "",
        shadow: getComputedStyle(button).boxShadow,
      }));
    const ringLabel = element.querySelector<SVGTextElement>(".nur-orbit-ring-label");
    return {
      canvas,
      sigil,
      footer,
      footerMessage,
      footerActions,
      actionCluster,
      panelShadows,
      controlShadows,
      ringCount: element.querySelectorAll(".nur-orbit-ring").length,
      ringFont: ringLabel ? getComputedStyle(ringLabel).fontFamily : "",
      ringFontSize: ringLabel ? getComputedStyle(ringLabel).fontSize : "",
    };
  });
  expect(layout.canvas).not.toBeNull();
  expect(layout.sigil).not.toBeNull();
  expect(layout.footer).not.toBeNull();
  expect(layout.footerMessage).not.toBeNull();
  expect(layout.footerActions).not.toBeNull();
  expect(layout.actionCluster).not.toBeNull();
  expect(layout.canvas!.bottom).toBeLessThanOrEqual(layout.footer!.top + 1);
  expect(layout.footerMessage!.width).toBeGreaterThan(240);
  expect(layout.footerActions!.top).toBeGreaterThanOrEqual(layout.footerMessage!.bottom - 1);
  const footerCenter = layout.footer!.left + layout.footer!.width / 2;
  expect(Math.abs(
    layout.footerMessage!.left + layout.footerMessage!.width / 2 - footerCenter,
  )).toBeLessThanOrEqual(1);
  expect(Math.abs(
    (layout.actionCluster!.left + layout.actionCluster!.right) / 2 - footerCenter,
  )).toBeLessThanOrEqual(1);
  expect(Math.abs(
    layout.sigil!.left + layout.sigil!.width / 2
    - (layout.canvas!.left + layout.canvas!.width / 2),
  )).toBeLessThanOrEqual(1);
  expect(Math.abs(
    layout.sigil!.top + layout.sigil!.height / 2
    - (layout.canvas!.top + layout.canvas!.height / 2),
  )).toBeLessThanOrEqual(1);
  expect(layout.ringCount).toBe(5);
  expect(layout.ringFont).toContain("Crimson Pro");
  expect(parseFloat(layout.ringFontSize)).toBeGreaterThanOrEqual(14);
  expect(layout.panelShadows.filter(panel => panel.shadow !== "none")).toEqual([]);
  expect(layout.controlShadows.filter(control => control.shadow !== "none")).toEqual([]);

  if (mobile) {
    await empty.scrollIntoViewIfNeeded();
    await empty.evaluate(element => {
      const footer = element.getBoundingClientRect();
      const tabs = document.querySelector<HTMLElement>(".mobile-tabs")?.getBoundingClientRect();
      const viewport = element.closest<HTMLElement>(".nur-viewport");
      if (tabs && viewport && footer.bottom > tabs.top - 8) {
        viewport.scrollTop += footer.bottom - tabs.top + 10;
      }
    });
    const mobileClearance = await root.evaluate(element => {
      const footer = element.querySelector<HTMLElement>(".nur-orbit-empty")?.getBoundingClientRect();
      const tabs = document.querySelector<HTMLElement>(".mobile-tabs")?.getBoundingClientRect();
      const composer = document.querySelector<HTMLElement>(".global-composer");
      return {
        footerBottom: footer?.bottom ?? Number.POSITIVE_INFINITY,
        tabsTop: tabs?.top ?? Number.NEGATIVE_INFINITY,
        composerDisplay: composer ? getComputedStyle(composer).display : "missing",
      };
    });
    expect(mobileClearance.composerDisplay).toBe("none");
    expect(mobileClearance.footerBottom).toBeLessThanOrEqual(mobileClearance.tabsTop - 8);
  }

  await page.screenshot({
    path: testInfo.outputPath("orbit-loading-sigil-empty-footer.png"),
  });
});

test("Orbit keeps populated field creation actions centered below the star", async ({ page }, testInfo) => {
  test.skip(
    !["chromium-desktop", "chromium-mobile"].includes(testInfo.project.name),
    "Orbit visual contract is owned by Chromium desktop and mobile.",
  );
  const mobile = testInfo.project.name === "chromium-mobile";
  await installNurMocks(page);
  await page.route("**/api/v1/orbit-field", route => json(route, {
    people: [{
      id: "orbit-person-1",
      display_name: "Amina",
      handle: null,
      relationship_type: "Friend",
      orbit_level: "INNER",
      orbit_level_suggestion: null,
      orbit_level_suggestion_reason: null,
      relational_state: "STEADY",
      tags: [],
      user_summary: null,
      nur_summary: null,
      avatar_ref: null,
      memory_allowed: true,
      inference_allowed: false,
      sharing_allowed: false,
      capsule_eligible: false,
      archived_at: null,
      last_interaction_at: "2026-07-30T12:00:00Z",
      privacy_scope: "PRIVATE",
    }],
    groups: [],
    relationships: [],
    layout: [],
    thread_counts: {},
  }));
  await page.route("**/api/v1/orbit-threads", route => json(route, []));
  await page.context().addCookies([
    { name: "nur_session", value: "orbit-populated-mandate", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "orbit-populated-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.setViewportSize(mobile ? { width: 393, height: 851 } : { width: 1440, height: 900 });
  await page.goto("/universe/orbits", { waitUntil: "load" });

  const root = page.frameLocator("#nur-universe-stage").locator("#nur-orbit-root");
  await expect(root).toBeVisible({ timeout: 20_000 });
  if (mobile) await root.locator('[data-orbit-view="orbit"]').click();

  const actions = root.locator(".nur-orbit-field-actions");
  await expect(actions.locator(':scope > [data-orbit-action="add-person"]')).toHaveCount(1);
  await expect(actions.locator(':scope > [data-orbit-action="create-group"]')).toHaveCount(1);
  await expect(root.locator(".nur-orbit-header-actions")).toHaveCount(0);
  await expect(root.locator('.nur-orbit-rail [data-orbit-action="add-person"], .nur-orbit-rail [data-orbit-action="create-group"]')).toHaveCount(0);

  const layout = await root.evaluate(element => {
    const box = (selector: string) => element.querySelector<HTMLElement>(selector)!.getBoundingClientRect();
    const canvas = box(".nur-orbit-canvas");
    const footer = box(".nur-orbit-field-actions");
    const buttons = Array.from(
      element.querySelectorAll<HTMLElement>(".nur-orbit-field-actions > button"),
      button => button.getBoundingClientRect(),
    );
    return {
      canvasBottom: canvas.bottom,
      footerTop: footer.top,
      footerCenter: footer.left + footer.width / 2,
      actionsCenter: (
        Math.min(...buttons.map(button => button.left))
        + Math.max(...buttons.map(button => button.right))
      ) / 2,
    };
  });
  expect(layout.canvasBottom).toBeLessThanOrEqual(layout.footerTop + 1);
  expect(Math.abs(layout.actionsCenter - layout.footerCenter)).toBeLessThanOrEqual(1);
});
