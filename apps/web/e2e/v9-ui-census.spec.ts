/**
 * V9 — current-UI visual census.
 *
 * Visits every reachable NUR route as the live seeded owner and records what is
 * actually on screen: control counts, heading structure, text density, empty and
 * error surfaces, touch-target violations and console failures. Screenshots are
 * captured at a desktop and a mobile viewport for each route.
 *
 * This is measurement, not judgement. The flaw ledger is derived from these
 * numbers afterwards so that every finding has a screenshot and a metric behind
 * it rather than an opinion.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const PROOF_ROOT = path.resolve(process.cwd(), "../../proof/v9-current-ui");

const ROUTES = [
  { route: "/today", surface: "Today", tier: "A" },
  { route: "/talk", surface: "Talk", tier: "B" },
  { route: "/journal", surface: "Journal", tier: "B" },
  { route: "/plan", surface: "Plan", tier: "B" },
  { route: "/systems", surface: "Systems", tier: "A" },
  { route: "/universe", surface: "Universe", tier: "A" },
  { route: "/universe/map", surface: "Map", tier: "A" },
  { route: "/universe/orbits", surface: "Orbits", tier: "A" },
  { route: "/universe/timeline", surface: "Timeline", tier: "B" },
  { route: "/universe/insights", surface: "Insights", tier: "B" },
  { route: "/universe/research", surface: "Research", tier: "A" },
  { route: "/universe/web-signals", surface: "Web Signals", tier: "B" },
  { route: "/universe/community", surface: "Community lens", tier: "B" },
  { route: "/community", surface: "Community", tier: "B" },
  { route: "/consultations", surface: "Consultations", tier: "B" },
  { route: "/projects", surface: "Projects", tier: "A" },
  { route: "/glow", surface: "Glow", tier: "B" },
  { route: "/notifications", surface: "Notifications", tier: "C" },
  { route: "/settings", surface: "Settings", tier: "C" },
  { route: "/universe/omega", surface: "Omega", tier: "B" },
  { route: "/universe/omega/review", surface: "Omega review", tier: "B" },
] as const;

const VIEWPORTS = [
  { label: "desktop-1920x1080", width: 1920, height: 1080 },
  { label: "mobile-390x844", width: 390, height: 844 },
] as const;

async function signIn(page: Page): Promise<void> {
  await page.goto("/");
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25_000 });
}

interface RouteRecord {
  route: string;
  surface: string;
  tier: string;
  viewport: string;
  controls: number;
  disabledControls: number;
  links: number;
  headings: string;
  h1: number;
  textCharacters: number;
  cards: number;
  canvases: number;
  images: number;
  smallText: number;
  tinyTouchTargets: number;
  emptyStates: number;
  errorMarkers: number;
  loadingMarkers: number;
  scrollHeight: number;
  consoleErrors: number;
  screenshot: string;
}

test.describe("V9 current-UI census", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "Census captured once on Chromium.");

  test("captures every route at desktop and mobile with real metrics", async ({ page }, testInfo) => {
    test.setTimeout(900_000);
    await mkdir(PROOF_ROOT, { recursive: true });

    const consoleErrors: string[] = [];
    page.on("pageerror", error => consoleErrors.push(`pageerror: ${error.message}`));
    page.on("console", message => {
      if (message.type() === "error") consoleErrors.push(`console: ${message.text().slice(0, 200)}`);
    });

    await signIn(page);
    const universe = page.frameLocator("#nur-universe-stage");
    const records: RouteRecord[] = [];

    // Signed-out entry, before anything else is recorded.
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.waitForTimeout(400);
      const file = `entry-${viewport.label}.png`;
      await page.screenshot({ path: path.join(PROOF_ROOT, file) });
    }

    for (const target of ROUTES) {
      for (const viewport of VIEWPORTS) {
        const errorsBefore = consoleErrors.length;
        await page.setViewportSize({ width: viewport.width, height: viewport.height });
        await page.goto(target.route);
        await page.waitForTimeout(1400);

        const metrics = await universe.locator("body").evaluate(() => {
          const visible = (node: Element): boolean => {
            const rect = node.getBoundingClientRect();
            if (rect.width === 0 || rect.height === 0) return false;
            const style = getComputedStyle(node);
            return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0.05;
          };

          const controls = Array.from(document.querySelectorAll("button, [role='button'], input, select, textarea"))
            .filter(visible);
          const links = Array.from(document.querySelectorAll("a[href]")).filter(visible);
          const headingNodes = Array.from(document.querySelectorAll("h1,h2,h3,h4,h5,h6")).filter(visible);

          // Touch-target and legibility checks against WCAG-oriented thresholds.
          let tiny = 0;
          for (const control of controls) {
            const rect = control.getBoundingClientRect();
            if (rect.width < 44 || rect.height < 44) tiny += 1;
          }
          let smallText = 0;
          for (const node of Array.from(document.querySelectorAll("p, span, small, li, td")).filter(visible)) {
            const size = Number.parseFloat(getComputedStyle(node).fontSize);
            if (size > 0 && size < 12 && (node.textContent ?? "").trim().length > 3) smallText += 1;
          }

          const body = document.body;
          const text = (body.innerText ?? "").replace(/\s+/g, " ").trim();
          const lowered = text.toLowerCase();
          const countMatches = (words: string[]): number =>
            words.reduce((total, word) => total + (lowered.includes(word) ? 1 : 0), 0);

          return {
            controls: controls.length,
            disabledControls: controls.filter(node => node.hasAttribute("disabled")
              || node.getAttribute("aria-disabled") === "true").length,
            links: links.length,
            headings: headingNodes.map(node => node.tagName).join(">"),
            h1: headingNodes.filter(node => node.tagName === "H1").length,
            textCharacters: text.length,
            cards: Array.from(document.querySelectorAll("[class*='card'], [class*='panel'], [class*='tile']"))
              .filter(visible).length,
            canvases: document.querySelectorAll("canvas").length,
            images: Array.from(document.querySelectorAll("img, svg")).filter(visible).length,
            smallText,
            tinyTouchTargets: tiny,
            emptyStates: countMatches(["nothing yet", "no results", "not yet", "empty", "none yet"]),
            errorMarkers: countMatches(["error", "failed", "went wrong", "unavailable", "try again"]),
            loadingMarkers: countMatches(["loading", "please wait", "working"]),
            scrollHeight: document.documentElement.scrollHeight,
          };
        });

        const file = `${target.surface.replace(/\W+/g, "-").toLowerCase()}-${viewport.label}.png`;
        await page.screenshot({ path: path.join(PROOF_ROOT, file) });

        records.push({
          route: target.route,
          surface: target.surface,
          tier: target.tier,
          viewport: viewport.label,
          ...metrics,
          consoleErrors: consoleErrors.length - errorsBefore,
          screenshot: `proof/v9-current-ui/${file}`,
        });
      }
    }

    await writeFile(
      path.join(PROOF_ROOT, "census.json"),
      `${JSON.stringify({ capturedAt: new Date().toISOString(), records, consoleErrors: consoleErrors.slice(0, 40) }, null, 2)}\n`,
      "utf8",
    );

    const header = Object.keys(records[0] ?? {}).join(",");
    const rows = records.map(record => Object.values(record)
      .map(value => (typeof value === "string" && value.includes(",") ? `"${value}"` : String(value)))
      .join(","));
    await writeFile(path.join(PROOF_ROOT, "census.csv"), `${[header, ...rows].join("\n")}\n`, "utf8");

    await testInfo.attach("census-summary", {
      body: JSON.stringify({ routes: ROUTES.length, records: records.length }, null, 2),
      contentType: "application/json",
    });

    expect(records.length).toBe(ROUTES.length * VIEWPORTS.length);
  });
});
