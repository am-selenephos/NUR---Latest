import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

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
  await expect(brain).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");
  await expect(brain).toHaveAttribute("data-nur-rig-depth", "projected-3d");
  await expect(brain).toHaveAttribute("data-nur-entry-systems-visual-contract", "exact-shared-crisp-v1");
  await expect(brain).toHaveAttribute("data-nur-opacity-profile", "crisp-opaque-v1");
  await expect(brain).toHaveAttribute(
    "data-nur-render-profile",
    "bounded-prism-cache-direct-pinpoints-v1",
  );
  await expect(brain).toHaveAttribute("data-nur-prism-wheel", "32");
  await expect(brain).toHaveAttribute("data-nur-halo-contract", "entry-f4-ring-exact");
  const entryCoreSize = await entry.locator("#f4-core").evaluate(element => {
    const rect = element.getBoundingClientRect();
    return { width: rect.width, height: rect.height };
  });
  expect(entryCoreSize.width).toBeGreaterThanOrEqual(450);
  expect(Math.abs(entryCoreSize.width - entryCoreSize.height)).toBeLessThanOrEqual(1);
  const entryGalaxy = entry.locator("#space3d");
  await expect(entryGalaxy).toHaveAttribute("data-nur-galaxy-rig", "canonical-v197-true-3d");
  await expect(entryGalaxy).toHaveAttribute("data-nur-galaxy-layers", "far-dust-galaxy-super");

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
  await expect.poll(() => entry.locator("html").evaluate(element => (
    getComputedStyle(element).animationName
  ))).toContain("nurHoloGlobalPhase");
  const entryPrimaryFilm = entry.locator(".f4-primary > .nur-holo-film").first();
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
  await expect(systemsBrain).toHaveAttribute("data-nur-rig-depth", "projected-3d");
  await expect(systemsBrain).toHaveAttribute("data-nur-entry-systems-visual-contract", "exact-shared-crisp-v1");
  await expect(systemsBrain).toHaveAttribute("data-nur-opacity-profile", "crisp-opaque-v1");
  await expect(systemsBrain).toHaveAttribute(
    "data-nur-render-profile",
    "bounded-prism-cache-direct-pinpoints-v1",
  );
  await expect(systemsBrain).toHaveAttribute("data-nur-prism-wheel", "32");
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
        .map(control => `${control.tagName.toLowerCase()}.${control.className}`),
    };
  }, HOLOGRAPHIC_CONTROLS);
  expect(controlCoverage.total).toBeGreaterThanOrEqual(60);
  expect(controlCoverage.missing).toEqual([]);
  expect(controlCoverage.incompleteSpectrum).toEqual([]);
  expect(controlCoverage.badGlass).toEqual([]);
  expect(controlCoverage.badGoldRim).toEqual([]);
  expect(controlCoverage.opaqueFilm).toEqual([]);

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
  expect(quietHover.shadow).not.toBe(quietDefault.shadow);
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

  await expect.poll(() => universe.locator("html").evaluate(element => (
    getComputedStyle(element).animationName
  ))).toContain("nurHoloGlobalPhase");
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
  expect(selectedTransformAfter).not.toBe(selectedTransformBefore);

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
      ".universe-state-strip",
      ".universe-composer-shell",
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
          sheenImage: getComputedStyle(element, "::before").backgroundImage,
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
    expect(panel.sheenImage, `${panel.identity} must carry full-spectrum optical light`)
      .toContain("33, 232, 255");
  }

  const galaxy = universe.locator("#space3d");
  await expect(galaxy).toBeVisible();
  await expect(galaxy).toHaveAttribute("data-nur-galaxy-rig", "canonical-v197-true-3d");
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
  expect(particleDiagnostics.total - particleDiagnostics.transient).toBe(1_698);
  expect(particleDiagnostics.byKind).toMatchObject({
    galaxy: 900,
    far: 585,
    dust: 165,
    super: 48,
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
