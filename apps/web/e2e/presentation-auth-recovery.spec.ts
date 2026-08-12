import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const proofRoot = process.env.NUR_AUTH_RECOVERY_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/presentation-auth-recovery" : "proof/presentation-auth-recovery");

async function shot(page: Page, name: string): Promise<void> {
  await mkdir(proofRoot, { recursive: true });
  await page.screenshot({ path: join(proofRoot, name), fullPage: false, animations: "disabled" });
}

async function revealEntry(page: Page): Promise<ReturnType<Page["frameLocator"]>> {
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() =>
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront === "function"),
  ).toBe(true);
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });
  return entry;
}

test("initial non-401 session failure stays on usable V197 Entry with a diagnostic", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "One deterministic startup-failure proof is sufficient.");
  await page.route("**/api/v1/auth/me", route => route.fulfill({
    status: 503,
    contentType: "application/json",
    body: JSON.stringify({ detail: "database not ready" }),
  }));
  await page.goto("/", { waitUntil: "load" });
  const entry = await revealEntry(page);
  await entry.locator("#f4-signin").click();

  await expect(entry.locator("#f4-status")).toContainText("NUR could not verify the local session");
  await expect(entry.locator("#f4-status")).toContainText("database not ready");
  await expect(entry.locator("#f4-status")).toHaveAttribute("role", "alert");
  await expect(entry.locator("#f4-status")).toBeVisible();
  await expect(entry.locator("#f4-signin-form")).toBeVisible();
  await expect(page.locator("#nur-universe-stage")).not.toHaveClass(/is-visible/);
  await shot(page, "startup-session-failure-visible.png");
});

test("real demo signin verifies identity, survives refresh, and logs out", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "One live browser-session proof is sufficient.");
  test.setTimeout(90_000);
  await page.goto("/", { waitUntil: "load" });
  const entry = await revealEntry(page);
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();

  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 30_000 });
  await expect(page.locator("#nur-entry-stage")).toHaveCSS("display", "none");
  await expect(page.locator("#nur-entry-stage")).toHaveAttribute("data-nur-stage-suspended", "true");
  await expect(entry.locator("#nur-v197-auth-wait")).toBeHidden();
  await expect(page).toHaveURL(/\/today$/);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  const me = await page.evaluate(async () => {
    const response = await fetch("/api/v1/auth/me", { credentials: "include" });
    const body = response.ok ? await response.json() as { email: string } : null;
    return { status: response.status, email: body?.email ?? null };
  });
  expect(me).toEqual({ status: 200, email: "owner@nur.app" });
  await shot(page, "demo-signin-authenticated.png");

  await page.reload({ waitUntil: "load" });
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 30_000 });
  await expect(page.locator("#nur-entry-stage")).toHaveCSS("display", "none");
  const afterRefresh = await page.evaluate(async () =>
    (await fetch("/api/v1/auth/me", { credentials: "include" })).status);
  expect(afterRefresh).toBe(200);
  await expect(page).toHaveURL(/\/today$/);
  await expect(page.frameLocator("#nur-universe-stage").locator("#page-today")).toBeVisible({ timeout: 20_000 });
  await shot(page, "demo-session-after-refresh.png");

  const refreshedUniverse = page.frameLocator("#nur-universe-stage");
  await refreshedUniverse.locator(".nur-user").click();
  await expect(refreshedUniverse.locator("#nur-v197-owner-auth-menu")).toBeVisible();
  const loggedOut = page.waitForResponse(response =>
    response.url().includes("/api/v1/auth/logout") && response.request().method() === "POST");
  await refreshedUniverse.locator('[data-action="auth-logout"]').click();
  expect((await loggedOut).status()).toBe(204);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("#nur-entry-stage")).toBeVisible();
  await expect(page.locator("#nur-entry-stage")).not.toHaveAttribute("data-nur-stage-suspended", "true");
  await expect(page.locator("#nur-entry-stage")).not.toHaveAttribute("aria-hidden", "true");
  await expect(page.locator("#nur-entry-stage")).not.toHaveAttribute("inert", "");
  await expect(page.locator("#nur-universe-stage")).toBeHidden();
  await expect(page.frameLocator("#nur-entry-stage").locator("#f4-signin")).toBeVisible();
  const loggedOutMe = await page.evaluate(async () =>
    (await fetch("/api/v1/auth/me", { credentials: "include" })).status);
  expect(loggedOutMe).toBe(401);
  await shot(page, "demo-logout-returned-to-landing.png");
});
