import { expect, test, type FrameLocator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const lenses = [
  { route: "/universe/map", focus: "map", root: "#nur-map-root", title: "Map", laneLabel: null },
  { route: "/universe/orbits", focus: "orbits", root: "#nur-orbit-root", title: "Orbit", laneLabel: null },
  { route: "/universe/timeline", focus: "timeline", root: "#nur-timeline-root", title: "Timeline", laneLabel: null },
  { route: "/universe/insights", focus: "insights", root: "#page-systems", title: null, laneLabel: "Owner insight summary" },
  { route: "/universe/research", focus: "research", root: "#page-systems", title: null, laneLabel: "Owner research summary" },
  { route: "/universe/community", focus: "community", root: "#page-systems", title: null, laneLabel: "Persisted community rooms" },
  { route: "/universe/web-signals", focus: "web", root: "#page-systems", title: null, laneLabel: "Owner web-signal staging summary" },
] as const;

async function authenticate(page: Page): Promise<void> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "forensic-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "forensic-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
}

async function expectExactV197Sigils(frame: FrameLocator): Promise<void> {
  const sigils = frame.locator(".nur-star-seal[data-nur-v197-sigil-source='#iSpark']");
  await expect.poll(() => sigils.count()).toBeGreaterThan(0);
  await expect(frame.locator(".nur-star-seal svg, .nur-star-seal use")).toHaveCount(0);

  const contract = await sigils.evaluateAll(elements => elements.map(element => {
    const star = element.querySelector<HTMLElement>(":scope > .spark");
    return {
      hasExactRoot: Boolean(star?.classList.contains("nur-v197-sigil-star")),
      rays: star?.querySelectorAll(".ray").length ?? 0,
      orbitSparks: star?.querySelectorAll(".ob").length ?? 0,
      coreLayers: star?.querySelectorAll(".spark-glow, .spark-halo, .spark-h2, .spark-core").length ?? 0,
    };
  }));
  contract.forEach(sigil => {
    expect(sigil.hasExactRoot).toBe(true);
    expect(sigil.rays).toBe(12);
    expect(sigil.orbitSparks).toBe(3);
    expect(sigil.coreLayers).toBe(4);
  });
}

test("all seven Universe routes retain one bounded canonical V197 surface", async ({ page }) => {
  test.setTimeout(120_000);
  await authenticate(page);

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }] as const) {
    await page.setViewportSize(viewport);
    for (const lens of lenses) {
      await page.goto(lens.route, { waitUntil: "load" });
      const frame = page.frameLocator("#nur-universe-stage");
      const root = frame.locator(lens.root);
      await expect(root).toBeVisible({ timeout: 20_000 });
      await expect.poll(() => frame.locator("body").getAttribute("data-nur-world-focus"))
        .toBe(lens.focus);
      await expect.poll(() => frame.locator(
        `[data-world-focus="${lens.focus}"].active, [data-world-tab="${lens.focus}"].active`,
      ).count()).toBeGreaterThan(0);
      if (lens.laneLabel) {
        await expect(frame.locator(".universe-system-lane")).toHaveAttribute("aria-label", lens.laneLabel);
      } else {
        await expect(root).toHaveAttribute("data-v197-native-adjunct", "true");
        await expect(frame.locator("#page-systems")).toBeHidden();
      }

      const result = await root.evaluate(async (element, dedicatedTitle) => {
        await document.fonts.ready;
        await new Promise<void>(resolve => requestAnimationFrame(() => requestAnimationFrame(() => resolve())));
        const visible = (node: HTMLElement) => {
          let current: HTMLElement | null = node;
          while (current) {
            const style = getComputedStyle(current);
            if (style.display === "none" || style.visibility === "hidden" || Number(style.opacity) <= 0) {
              return false;
            }
            current = current.parentElement;
          }
          const rect = node.getBoundingClientRect();
          return rect.width > 0 && rect.height > 0;
        };
        const viewportControls = Array.from(
          element.querySelectorAll<HTMLElement>("button, input, textarea, select, [role='button']"),
        ).filter(node => {
          if (!visible(node)) return false;
          const rect = node.getBoundingClientRect();
          return rect.bottom >= 0 && rect.top <= innerHeight;
        });
        const escapedControls = viewportControls.flatMap(control => {
          const rect = control.getBoundingClientRect();
          return rect.left < -1 || rect.right > innerWidth + 1
            ? [{ name: `${control.tagName.toLowerCase()}.${control.className}`, left: rect.left, right: rect.right }]
            : [];
        });
        const title = element.querySelector<HTMLElement>(".universe-map-title");
        const wordmark = title?.querySelector<HTMLElement>(".nur-v197-stable-wordmark") ?? null;
        const subtitle = title?.querySelector<HTMLElement>(".nur-master-subtitle") ?? null;
        const visualCenter = (node: HTMLElement) => {
          const rect = node.getBoundingClientRect();
          const style = getComputedStyle(node);
          const matrix = style.transform === "none" ? new DOMMatrix() : new DOMMatrix(style.transform);
          return rect.left + rect.width / 2 - matrix.m41;
        };
        const wordmarkStyle = wordmark ? getComputedStyle(wordmark) : null;
        const bounds = element.getBoundingClientRect();
        const surfaceHeading = dedicatedTitle
          ? element.querySelector<HTMLElement>("h1")?.textContent?.trim() ?? null
          : null;
        return {
          left: bounds.left,
          right: bounds.right,
          scrollWidth: document.documentElement.scrollWidth,
          viewportWidth: innerWidth,
          escapedControls,
          nativeAdjunct: element.dataset.v197NativeAdjunct ?? null,
          surfaceHeading,
          lockupDelta: wordmark && subtitle ? visualCenter(wordmark) - visualCenter(subtitle) : null,
          lockupAxis: title?.dataset.nurLockupAxis ?? null,
          holographic: wordmark?.dataset.nurHolographicWordmark ?? null,
          animation: wordmarkStyle?.animationName ?? null,
          backgroundClip: wordmarkStyle?.backgroundClip ?? null,
          textFill: wordmarkStyle?.webkitTextFillColor ?? null,
        };
      }, lens.title);

      expect(result.left).toBeGreaterThanOrEqual(-1);
      expect(result.right).toBeLessThanOrEqual(viewport.width + 1);
      expect(result.scrollWidth).toBeLessThanOrEqual(result.viewportWidth + 1);
      expect(result.escapedControls).toEqual([]);
      if (lens.title) {
        expect(result.nativeAdjunct).toBe("true");
        expect(result.surfaceHeading).toBe(lens.title);
      } else {
        expect(Math.abs(result.lockupDelta ?? Number.POSITIVE_INFINITY)).toBeLessThanOrEqual(.25);
        expect(result.lockupAxis).toBe("center");
        expect(result.holographic).toBe("animated");
        expect(result.animation).toContain("univPrism");
        expect(result.backgroundClip).toBe("text");
        expect(result.textFill).toBe("rgba(0, 0, 0, 0)");
      }
      await expectExactV197Sigils(frame);
    }
  }
});

test("Systems owns the exact V43 brain while Map owns a dedicated causal surface", async ({ page }) => {
  test.setTimeout(60_000);
  await authenticate(page);

  for (const viewport of [{ width: 390, height: 844 }, { width: 1440, height: 900 }] as const) {
    await page.setViewportSize(viewport);
    await page.goto("/systems", { waitUntil: "load" });
    const frame = page.frameLocator("#nur-universe-stage");
    const panel = frame.locator("#page-systems .universe-map-panel");
    await expect(panel).toBeVisible({ timeout: 20_000 });

    const brain = panel.locator(".universe-master-star > #front-nur-star");
    await expect(brain).toBeVisible();
    await expect(brain).toHaveAttribute("data-nur-source", "v43-anatomy-three-celestial-runtime");
    await expect(brain).toHaveAttribute("data-nur-dispersal", "radial-circle");
    await expect(brain.locator("#nur-brain-canvas")).toBeVisible();
    await expect(panel.locator(".universe-master-star > .f4-core, .universe-master-star > .f4-master-star"))
      .toHaveCount(0);
    await expect(panel.locator(".universe-rings:visible")).toHaveCount(0);
    const visibleNodes = panel.locator(".universe-system-node:not([hidden])");
    await expect(visibleNodes).toHaveCount(6);
    await expect(visibleNodes.locator(":scope > i[data-nur-native-glyph='true']")).toHaveCount(6);
    await expect(panel.locator(
      ".universe-system-node svg, .universe-system-node [data-nur-star-seal='authentic']",
    )).toHaveCount(0);

    const geometry = await panel.evaluate(element => {
      const panelRect = element.getBoundingClientRect();
      return Array.from(element.querySelectorAll<HTMLElement>(".universe-system-node:not([hidden])")).map(node => {
        const rect = node.getBoundingClientRect();
        const copy = node.querySelector<HTMLElement>(":scope > span")!.getBoundingClientRect();
        const style = getComputedStyle(node);
        return {
          name: node.className,
          left: rect.left - panelRect.left,
          right: rect.right - panelRect.left,
          top: rect.top - panelRect.top,
          bottom: rect.bottom - panelRect.top,
          computed: {
            left: style.left,
            right: style.right,
            top: style.top,
            width: style.width,
            transform: style.transform,
          },
          copyFits: copy.left >= rect.left - 1
            && copy.right <= rect.right + 1
            && copy.top >= rect.top - 1
            && copy.bottom <= rect.bottom + 1,
          scrollFits: node.scrollWidth <= node.clientWidth + 1 && node.scrollHeight <= node.clientHeight + 1,
        };
      });
    });
    const panelSize = await panel.evaluate(element => ({ width: element.clientWidth, height: element.clientHeight }));
    geometry.forEach(node => {
      const detail = `${node.name} ${JSON.stringify(node.computed)}`;
      expect(node.left, detail).toBeGreaterThanOrEqual(-1);
      expect(node.right, detail).toBeLessThanOrEqual(panelSize.width + 1);
      expect(node.top, detail).toBeGreaterThanOrEqual(-1);
      expect(node.bottom, detail).toBeLessThanOrEqual(panelSize.height + 1);
      expect(node.copyFits, detail).toBe(true);
      expect(node.scrollFits, detail).toBe(true);
    });

    await page.goto("/universe/map", { waitUntil: "load" });
    const map = frame.locator("#nur-map-root");
    await expect(map).toBeVisible({ timeout: 20_000 });
    await expect(map).toHaveAttribute("data-v197-native-adjunct", "true");
    await expect(map).toHaveAttribute("data-map-loaded", "true");
    await expect(map.locator("h1")).toHaveText("Map");
    await expect(frame.locator("#page-systems")).toBeHidden();
    await expect(frame.locator("#root")).toHaveCount(0);
  }
});
