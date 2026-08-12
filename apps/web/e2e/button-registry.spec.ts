import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type FrameLocator, type Page } from "@playwright/test";

type RegistryControl = {
  id: string;
  selector?: string;
  route?: string;
  status: "WIRED" | "SOURCE_NATIVE" | "HONEST_DISABLED" | "DEFERRED";
  endpoint?: string;
  proof?: string;
};

type Registry = {
  architecture: string;
  source_sha256: string;
  statuses: string[];
  controls: RegistryControl[];
};

const here = dirname(fileURLToPath(import.meta.url));
const registry = JSON.parse(
  readFileSync(resolve(here, "../../../docs/interaction-registry.json"), "utf8"),
) as Registry;
const visibleSelectors = registry.controls.flatMap(control => control.selector ? [control.selector] : []);

async function showEntry(page: Page): Promise<FrameLocator> {
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await expect(entry.locator("#f4-begin")).toBeVisible();
  return entry;
}

async function signIn(page: Page): Promise<FrameLocator> {
  const entry = await showEntry(page);
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 20_000 });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(page).toHaveURL(/\/today$/);
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  return universe;
}

async function uncovered(frame: FrameLocator): Promise<string[]> {
  return frame.locator("body").evaluate((_, selectors: string[]) => {
    const candidates = [...document.querySelectorAll<HTMLElement>(
      "button, input:not([type='hidden']), select, textarea, a[href], [role='button'], [role='tab']",
    )].filter(node => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return style.display !== "none" && style.visibility !== "hidden" && rect.width > 0 && rect.height > 0;
    });
    return candidates.filter(node => !selectors.some(selector => {
      try {
        return node.matches(selector);
      } catch {
        return false;
      }
    })).map(node => {
      const id = node.id ? `#${node.id}` : "";
      const classes = [...node.classList].slice(0, 3).map(value => `.${value}`).join("");
      const data = node.dataset.action
        ? `[data-action=${node.dataset.action}]`
        : node.dataset.worldFocus
          ? `[data-world-focus=${node.dataset.worldFocus}]`
          : node.dataset.contextAction
            ? `[data-context-action=${node.dataset.contextAction}]`
            : "";
      const label = (node.getAttribute("aria-label") || node.textContent || "").trim().replace(/\s+/g, " ").slice(0, 60);
      return `${node.tagName.toLowerCase()}${id}${classes}${data} :: ${label}`;
    });
  }, visibleSelectors);
}

test("machine-readable Track A registry is internally complete", () => {
  expect(registry.architecture).toBe("track-a-v197-native-host");
  expect(registry.source_sha256).toBe("c4699091db9f1ebc3a6e2076d483a3d41303d3e261ace0111c9411322f7ea3a5");
  expect(new Set(registry.controls.map(control => control.id)).size).toBe(registry.controls.length);
  for (const control of registry.controls) {
    expect(registry.statuses).toContain(control.status);
    if (control.status === "DEFERRED") expect(control.route).toBeTruthy();
    else {
      expect(control.selector).toBeTruthy();
      expect(control.proof).toBeTruthy();
      if (control.status === "WIRED") expect(control.proof).toMatch(/\.spec\.ts(?:\s|$)/);
    }
  }
});

test("entry, signup, and signin chambers expose no unregistered visible controls", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Registry coverage runs once in desktop Chromium.");
  const entry = await showEntry(page);
  expect(await uncovered(entry)).toEqual([]);

  await entry.locator("#f4-begin").click();
  expect(await uncovered(entry)).toEqual([]);
  await entry.locator("#f4-close").click();

  await entry.locator("#f4-signin").click();
  expect(await uncovered(entry)).toEqual([]);
});

test("authenticated V197 pages and hidden scope chamber expose no unregistered controls", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Registry coverage runs once in desktop Chromium.");
  test.setTimeout(90_000);
  const universe = await signIn(page);

  for (const pageName of ["today", "talk", "journal", "plan", "systems"]) {
    await universe.locator(`[data-page="${pageName}"]:visible`).first().click();
    expect(await uncovered(universe), `unregistered control on ${pageName}`).toEqual([]);
  }

  await universe.locator("#scope-open").click();
  await expect(universe.locator("#scope-modal")).toHaveClass(/open/);
  expect(await uncovered(universe), "unregistered control in scope/language chamber").toEqual([]);
  await universe.locator(".scope-modal-close").click();

  await universe.locator(".nur-user").click();
  await expect(universe.locator("#nur-v197-owner-auth-menu")).toBeVisible();
  expect(await uncovered(universe), "unregistered control in owner session chamber").toEqual([]);
  await universe.locator(".nur-user").click();

  for (const focus of ["map", "orbits", "timeline", "insights"]) {
    const control = universe.locator(`[data-world-tab="${focus}"], [data-world-focus="${focus}"]`).first();
    await control.click();
    expect(await uncovered(universe), `unregistered control in ${focus} focus`).toEqual([]);
  }

  let releaseStream!: () => void;
  const streamGate = new Promise<void>(resolve => { releaseStream = resolve; });
  let cancelRequests = 0;
  await page.route("**/api/v1/cognition/talk/stream", async route => {
    await streamGate;
    await route.abort("aborted").catch(() => undefined);
  });
  await page.route("**/api/v1/cognition/talk-runs/*/cancel", async route => {
    cancelRequests += 1;
    await route.fulfill({ status: 202, contentType: "application/json", body: JSON.stringify({ cancel_requested: true }) });
  });
  await universe.locator('[data-page="talk"]:visible').first().click();
  await universe.locator("#talk-input").fill("Registry cancellation boundary");
  await universe.locator('[data-send="talk"]').click();
  const cancel = universe.locator('[data-action="talk-cancel"]');
  await expect(cancel).toBeVisible();
  expect(await uncovered(universe), "unregistered control during live Talk").toEqual([]);
  await cancel.click();
  await expect.poll(() => cancelRequests).toBe(1);
  releaseStream();
  await page.unroute("**/api/v1/cognition/talk/stream");
  await page.unroute("**/api/v1/cognition/talk-runs/*/cancel");

  for (const control of registry.controls.filter(row => row.status === "HONEST_DISABLED" && row.selector)) {
    const matches = universe.locator(control.selector!);
    const count = await matches.count();
    for (let index = 0; index < count; index += 1) {
      const node = matches.nth(index);
      if (!await node.isVisible()) continue;
      await expect(node, `${control.id} must be honestly disabled`).toBeDisabled();
    }
  }
});

test("mobile-only V197 controls are named, usable, and registered", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Coverage controls its own mobile viewport.");
  await page.setViewportSize({ width: 393, height: 852 });
  const universe = await signIn(page);
  const mobileLabels = await universe.locator(".mobile-tabs button").allTextContents();
  const lensLabels = await universe.locator(".universe-nav-tabs button > span:not(.nur-exact-mini-host)").allTextContents();
  expect(mobileLabels).toHaveLength(5);
  expect(lensLabels).toHaveLength(5);
  expect(mobileLabels.every(label => label.trim().length > 0)).toBe(true);
  expect(lensLabels.every(label => label.trim().length > 0)).toBe(true);
  expect(await uncovered(universe)).toEqual([]);
});

test("V197-native adjunct routes are served by the canonical non-React host", async ({ request }) => {
  for (const route of ["/settings", "/capsule/example", "/universe/omega", "/universe/omega/review", "/universe/omega/why-changed/example"]) {
    const response = await request.get(route);
    expect(response.status(), route).toBe(200);
    const body = await response.text();
    expect(body, route).toContain("nur-universe-stage");
    expect(body, route).not.toContain('id="root"');
  }
});
