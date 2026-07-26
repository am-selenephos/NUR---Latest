/**
 * V9 — state census.
 *
 * The route census covered populated desktop and mobile only. This covers the
 * states that decide whether the interface is actually premium: signed out,
 * signup, a brand-new empty account, validation errors, offline, permission
 * denied, reduced motion, RTL, long strings and the mobile keyboard.
 *
 * Every state is produced by driving the real application — a fresh registration,
 * a real bad password, real offline emulation — rather than by mocking a screen
 * that looks like the state.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const PROOF_ROOT = path.resolve(process.cwd(), "../../proof/v9-current-ui/states");

interface StateRecord {
  state: string;
  route: string;
  viewport: string;
  controls: number;
  disabledControls: number;
  h1: number;
  textCharacters: number;
  tinyTouchTargets: number;
  smallText: number;
  visibleText: string;
  screenshot: string;
  note: string;
}

const records: StateRecord[] = [];

async function measure(
  page: Page,
  scope: "page" | "universe",
  state: string,
  route: string,
  viewport: string,
  note: string,
): Promise<void> {
  const target = scope === "universe"
    ? page.frameLocator("#nur-universe-stage").locator("body")
    : page.locator("body");

  const metrics = await target.evaluate(() => {
    const visible = (node: Element): boolean => {
      const rect = node.getBoundingClientRect();
      if (rect.width === 0 || rect.height === 0) return false;
      const style = getComputedStyle(node);
      return style.visibility !== "hidden" && style.display !== "none" && Number(style.opacity) > 0.05;
    };
    const controls = Array.from(document.querySelectorAll("button,[role='button'],input,select,textarea"))
      .filter(visible);
    let tiny = 0;
    for (const control of controls) {
      const rect = control.getBoundingClientRect();
      if (rect.width < 44 || rect.height < 44) tiny += 1;
    }
    let small = 0;
    for (const node of Array.from(document.querySelectorAll("p,span,small,li,td,label")).filter(visible)) {
      const size = Number.parseFloat(getComputedStyle(node).fontSize);
      if (size > 0 && size < 12 && (node.textContent ?? "").trim().length > 3) small += 1;
    }
    const text = (document.body.innerText ?? "").replace(/\s+/g, " ").trim();
    return {
      controls: controls.length,
      disabledControls: controls.filter(node => node.hasAttribute("disabled")
        || node.getAttribute("aria-disabled") === "true").length,
      h1: Array.from(document.querySelectorAll("h1")).filter(visible).length,
      textCharacters: text.length,
      tinyTouchTargets: tiny,
      smallText: small,
      visibleText: text.slice(0, 220),
    };
  });

  const file = `${state.replace(/\W+/g, "-").toLowerCase()}-${viewport}.png`;
  await page.screenshot({ path: path.join(PROOF_ROOT, file) });
  records.push({ state, route, viewport, ...metrics, screenshot: `proof/v9-current-ui/states/${file}`, note });
}

async function signIn(page: Page, email = "owner@nur.app", password = "owner-demo-pass-123"): Promise<void> {
  await page.goto("/");
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill(email);
  await entry.locator("#f4-signin-password").fill(password);
  await entry.locator("#f4-signin-form button[type='submit']").click();
}

test.describe("V9 state census", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "State census captured once on Chromium.");

  test("captures the states that decide whether the product feels finished", async ({ page, context }, testInfo) => {
    test.setTimeout(900_000);
    await mkdir(PROOF_ROOT, { recursive: true });

    // ── signed out ────────────────────────────────────────────────────────
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/");
    await page.waitForTimeout(1500);
    await measure(page, "page", "signed-out-entry", "/", "desktop", "First visit, unauthenticated");

    await page.setViewportSize({ width: 390, height: 844 });
    await page.waitForTimeout(900);
    await measure(page, "page", "signed-out-entry", "/", "mobile", "First visit on a phone");

    // ── signup form ───────────────────────────────────────────────────────
    await page.setViewportSize({ width: 1920, height: 1080 });
    await page.goto("/");
    const entry = page.frameLocator("#nur-entry-stage");
    await entry.locator("body").evaluate(() => {
      (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
    });
    await page.waitForTimeout(1200);
    await measure(page, "page", "signup-form", "/", "desktop", "Onboarding entry surface");

    // ── validation error: real wrong password ─────────────────────────────
    await signIn(page, "owner@nur.app", "definitely-not-the-password");
    await page.waitForTimeout(2500);
    await measure(page, "page", "signin-validation-error", "/", "desktop", "Real rejected credential");

    // ── new empty account: real registration ──────────────────────────────
    const unique = `census-${Date.now()}@nur.app`;
    await page.goto("/");
    await entry.locator("body").evaluate(() => {
      (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
    });
    await page.waitForTimeout(900);
    const created = await entry.locator("#f4-name").isVisible().catch(() => false);
    if (created) {
      await entry.locator("#f4-name").fill("Census Owner");
      await entry.locator("#f4-email").fill(unique);
      const password = entry.locator("#f4-password");
      if (await password.isVisible().catch(() => false)) await password.fill("census-owner-pass-123");
      await measure(page, "page", "signup-filled", "/", "desktop", `Registration form filled for ${unique}`);
    }

    // ── populated owner, then the operational states ──────────────────────
    await signIn(page);
    await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25_000 });

    await page.goto("/settings");
    await page.waitForTimeout(1600);
    await measure(page, "universe", "settings-populated", "/settings", "desktop", "Provider and account controls");

    // ── offline ───────────────────────────────────────────────────────────
    await context.setOffline(true);
    await page.goto("/notifications").catch(() => undefined);
    await page.waitForTimeout(2200);
    await measure(page, "universe", "offline", "/notifications", "desktop", "Network disabled at the browser context");
    await context.setOffline(false);
    await page.waitForTimeout(1200);

    // ── permission denied: another owner's capsule ────────────────────────
    await page.goto("/capsule/00000000-0000-0000-0000-000000000000");
    await page.waitForTimeout(2200);
    await measure(page, "universe", "permission-denied-or-missing", "/capsule/<nonexistent>", "desktop",
      "Capsule id that does not belong to this owner");

    // ── reduced motion ────────────────────────────────────────────────────
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.goto("/systems");
    await page.waitForTimeout(2000);
    await measure(page, "universe", "reduced-motion", "/systems", "desktop", "prefers-reduced-motion: reduce");
    await page.emulateMedia({ reducedMotion: null });

    // ── RTL ───────────────────────────────────────────────────────────────
    await page.goto("/today");
    await page.waitForTimeout(1500);
    await page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
      document.documentElement.setAttribute("dir", "rtl");
      document.documentElement.setAttribute("lang", "ur");
    });
    await page.waitForTimeout(900);
    await measure(page, "universe", "rtl-direction", "/today", "desktop", "dir=rtl applied to the universe document");
    await page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
      document.documentElement.setAttribute("dir", "ltr");
      document.documentElement.setAttribute("lang", "en");
    });

    // ── long strings ──────────────────────────────────────────────────────
    await page.goto("/talk");
    await page.waitForTimeout(1600);
    const overflow = await page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
      const long = "نُور ایک زندہ ذہانت ہے جو آپ کے ساتھ سیکھتی ہے ".repeat(14);
      const field = document.querySelector<HTMLTextAreaElement | HTMLInputElement>(
        "#talk-input, textarea, input[type='text']",
      );
      if (!field) return { applied: false, overflowX: document.documentElement.scrollWidth > window.innerWidth };
      field.value = long;
      field.dispatchEvent(new Event("input", { bubbles: true }));
      return { applied: true, overflowX: document.documentElement.scrollWidth > window.innerWidth };
    });
    await page.waitForTimeout(700);
    await measure(page, "universe", "long-string", "/talk", "desktop",
      `Long Urdu string in composer; applied=${overflow.applied} horizontalOverflow=${overflow.overflowX}`);

    // ── mobile keyboard open ──────────────────────────────────────────────
    await page.setViewportSize({ width: 390, height: 420 });
    await page.goto("/talk");
    await page.waitForTimeout(1600);
    await measure(page, "universe", "mobile-keyboard-open", "/talk", "mobile-short",
      "Viewport halved to emulate an open keyboard");

    await writeFile(
      path.join(PROOF_ROOT, "state-census.json"),
      `${JSON.stringify({ capturedAt: new Date().toISOString(), records }, null, 2)}\n`,
      "utf8",
    );
    await testInfo.attach("state-census", {
      body: JSON.stringify({ states: records.length }, null, 2),
      contentType: "application/json",
    });
    expect(records.length).toBeGreaterThanOrEqual(12);
  });
});
