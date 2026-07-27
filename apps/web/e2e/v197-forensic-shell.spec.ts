import { expect, test, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const targetViewports = [
  { width: 360, height: 800 },
  { width: 390, height: 844 },
  { width: 430, height: 932 },
  { width: 844, height: 390 },
  { width: 768, height: 1024 },
  { width: 1024, height: 768 },
  { width: 1280, height: 720 },
  { width: 1366, height: 768 },
  { width: 1440, height: 900 },
  { width: 1920, height: 1080 },
  { width: 2560, height: 1080 },
  { width: 2560, height: 1440 },
] as const;

async function installAuthenticatedMocks(page: Page): Promise<void> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "forensic-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "forensic-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
}

test("shared shell stays inside every required viewport", async ({ page }) => {
  test.setTimeout(120_000);
  await installAuthenticatedMocks(page);

  for (const viewport of targetViewports) {
    await page.setViewportSize(viewport);
    await page.goto("/systems", { waitUntil: "load" });
    const frame = page.frameLocator("#nur-universe-stage");
    await expect(frame.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
    await expect(
      frame.locator("#front-nur-star"),
      `exact V197 brain host did not settle at ${viewport.width}x${viewport.height}`,
    ).toHaveCount(1, { timeout: 5_000 });
    await expect(
      frame.locator("#nur-brain-canvas"),
      `exact V43 brain canvas did not settle at ${viewport.width}x${viewport.height}`,
    ).toHaveCount(1, { timeout: 5_000 });

    const geometry = await frame.locator("body").evaluate(async () => {
      await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
      const visible = (element: HTMLElement) => {
        const style = getComputedStyle(element);
        const bounds = element.getBoundingClientRect();
        return style.display !== "none"
          && style.visibility !== "hidden"
          && Number(style.opacity) > 0
          && bounds.width > 0
          && bounds.height > 0;
      };
      const rect = (selector: string) => {
        const element = document.querySelector<HTMLElement>(selector);
        if (!element || !visible(element)) return null;
        const bounds = element.getBoundingClientRect();
        return {
          left: bounds.left,
          right: bounds.right,
          top: bounds.top,
          bottom: bounds.bottom,
          width: bounds.width,
          height: bounds.height,
        };
      };
      const escapedControls = Array.from(document.querySelectorAll<HTMLElement>("button, a, input, textarea, select"))
        .filter(element => {
          const style = getComputedStyle(element);
          if (
            style.display === "none"
            || style.visibility === "hidden"
            || style.opacity === "0"
            || element.closest("[hidden], [aria-hidden='true']")
          ) return false;
          const bounds = element.getBoundingClientRect();
          return bounds.width > 0
            && bounds.height > 0
            && (bounds.left < -1 || bounds.right > innerWidth + 1);
        })
        .map(element => `${element.tagName.toLowerCase()}.${element.className}`);

      return {
        shell: rect(".nur-shell"),
        leftRail: rect(".clean-left-rail"),
        rightRail: rect(".clean-right-rail"),
        topbar: rect(".nur-topbar"),
        viewport: rect(".nur-viewport"),
        composer: rect(".global-composer"),
        mobileTabs: rect(".mobile-tabs"),
        toast: rect(".toast, #toast.toast"),
        bodyBackground: getComputedStyle(document.body).backgroundColor,
        mapBackground: getComputedStyle(document.querySelector<HTMLElement>(".universe-map-panel")!).background,
        nodeLabels: Array.from(document.querySelectorAll<HTMLElement>(".universe-system-node"))
          .filter(visible)
          .map(node => {
            const element = node.querySelector<HTMLElement>(":scope > span")!;
            const style = getComputedStyle(element);
            return {
              width: element.getBoundingClientRect().width,
              display: style.display,
              overflowWrap: style.overflowWrap,
              wordBreak: style.wordBreak,
            };
          }),
        commands: Array.from(document.querySelectorAll<HTMLElement>(".universe-command-row .world-command")).map(element => ({
          clientWidth: element.clientWidth,
          scrollWidth: element.scrollWidth,
          overflowWrap: getComputedStyle(element).overflowWrap,
          wordBreak: getComputedStyle(element).wordBreak,
        })),
        navControls: Array.from(document.querySelectorAll<HTMLButtonElement>(".universe-nav-tabs button")).map(element => ({
          aria: element.getAttribute("aria-label"),
          title: element.title,
          fontSize: Number.parseFloat(getComputedStyle(element).fontSize),
          text: element.innerText.trim(),
        })),
        railTitles: Array.from(document.querySelectorAll<HTMLElement>(".clean-nav-title"))
          .filter(visible)
          .map(element => ({ clientWidth: element.clientWidth, scrollWidth: element.scrollWidth })),
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        escapedControls,
        brainHosts: document.querySelectorAll("#front-nur-star").length,
        brainCanvases: document.querySelectorAll("#nur-brain-canvas").length,
      };
    });

    expect(geometry.shell).not.toBeNull();
    expect(Math.abs((geometry.shell?.width ?? 0) - viewport.width)).toBeLessThanOrEqual(1);
    expect(Math.abs((geometry.shell?.height ?? 0) - viewport.height)).toBeLessThanOrEqual(1);
    expect(geometry.documentWidth).toBeLessThanOrEqual(geometry.viewportWidth + 1);
    expect(geometry.escapedControls).toEqual([]);
    expect(geometry.bodyBackground).toBe("rgb(0, 0, 0)");
    expect(geometry.mapBackground).not.toContain("31, 16, 58");
    expect(geometry.mapBackground).not.toContain("5, 3, 13");
    expect(geometry.nodeLabels).toHaveLength(6);
    geometry.nodeLabels.forEach(label => {
      expect(label.width).toBeGreaterThan(0);
      expect(label.display).not.toBe("none");
      expect(label.overflowWrap).toBe("normal");
      expect(label.wordBreak).toBe("normal");
    });
    geometry.commands.forEach(command => {
      expect(command.scrollWidth).toBeLessThanOrEqual(command.clientWidth + 1);
      expect(command.overflowWrap).toBe("normal");
      expect(command.wordBreak).toBe("normal");
    });
    geometry.navControls.forEach(control => {
      expect(control.aria).toBeTruthy();
      expect(control.title).toBe(control.aria);
      expect(control.fontSize).toBeGreaterThan(0);
      expect(control.text).not.toBe("");
    });
    expect(geometry.brainHosts).toBe(1);
    expect(geometry.brainCanvases).toBe(1);

    if (viewport.width <= 900) {
      expect(geometry.leftRail).toBeNull();
      expect(geometry.rightRail).toBeNull();
      expect(geometry.composer).not.toBeNull();
      expect(geometry.mobileTabs).not.toBeNull();
      expect(Math.abs((geometry.mobileTabs?.bottom ?? 0) - viewport.height)).toBeLessThanOrEqual(1);
      expect(Math.abs((geometry.composer?.bottom ?? 0) - (geometry.mobileTabs?.top ?? 0))).toBeLessThanOrEqual(1);
      if (geometry.toast) {
        expect(geometry.toast.bottom).toBeLessThanOrEqual((geometry.composer?.top ?? 0) - 8);
      }
    } else {
      expect(geometry.leftRail).not.toBeNull();
      expect(geometry.composer).toBeNull();
      expect(geometry.mobileTabs).toBeNull();
      expect(geometry.rightRail === null).toBe(viewport.width < 1600);
      geometry.railTitles.forEach(title => {
        expect(title.scrollWidth).toBeLessThanOrEqual(title.clientWidth + 1);
      });
    }

    expect(Math.abs((geometry.topbar?.bottom ?? 0) - (geometry.viewport?.top ?? 0))).toBeLessThanOrEqual(1);
  }
});

test("Today owns one visible exact V43 brain renderer", async ({ page }) => {
  test.setTimeout(60_000);
  await installAuthenticatedMocks(page);

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }] as const) {
    await page.setViewportSize(viewport);
    await page.goto("/today", { waitUntil: "load" });
    const frame = page.frameLocator("#nur-universe-stage");
    await expect(frame.locator("#page-today")).toBeVisible({ timeout: 20_000 });
    await expect(frame.locator("#page-today .orbit-star-zone > .f4-core > #front-nur-star")).toBeVisible();
    await expect(frame.locator("#nur-brain-canvas")).toBeVisible();

    const readBrain = () => frame.locator("body").evaluate(() => {
      const canvas = document.querySelector<HTMLCanvasElement>("#nur-brain-canvas");
      const context = canvas?.getContext("2d");
      const host = document.querySelector<HTMLElement>("#front-nur-star");
      let paintedSamples = 0;
      if (canvas && context) {
        const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
        const stride = Math.max(4, Math.floor(pixels.length / 6000 / 4) * 4);
        for (let index = 3; index < pixels.length; index += stride) {
          if (pixels[index] > 8) paintedSamples += 1;
        }
      }
      return {
        hosts: document.querySelectorAll("#front-nur-star").length,
        canvases: document.querySelectorAll("#nur-brain-canvas").length,
        surface: document.querySelector<HTMLElement>("#front-nur-star")?.dataset.nurSurface,
        paintedSamples,
        model: host?.dataset.nurModel,
        pointCount: host?.dataset.nurPointCount,
        dispersal: host?.dataset.nurDispersal,
      };
    });
    await expect.poll(async () => (await readBrain()).paintedSamples, { timeout: 5_000 }).toBeGreaterThan(100);
    const brain = await readBrain();

    const expectedPoints = viewport.width < 700 ? "1355" : "2086";
    expect(brain.hosts).toBe(1);
    expect(brain.canvases).toBe(1);
    expect(brain.surface).toBe("today");
    expect(brain.paintedSamples).toBeGreaterThan(100);
    expect(brain.model).toBe("v43-v7-spark-stem");
    expect(brain.pointCount).toBe(expectedPoints);
    expect(brain.dispersal).toBe("radial-circle");
  }
});
