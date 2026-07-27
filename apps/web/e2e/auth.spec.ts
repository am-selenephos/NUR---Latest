import { expect, test, type Page } from "@playwright/test";

async function revealEntry(page: Page) {
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });
  return entry;
}

test("registration creates a secure owner session and logout guards canonical routes", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The live auth mutation runs once on desktop.");
  test.setTimeout(90_000);
  const email = `auth-${Date.now()}-${Math.floor(Math.random() * 1e6)}@nurapp.dev`;
  const entry = await revealEntry(page);

  await entry.locator("#f4-begin").click();
  await entry.locator("#f4-name").fill("Selene");
  await entry.locator("#f4-email").fill(email);
  await entry.locator("#f4-password").fill("orbit-pass-2026");
  await entry.locator("#f4-consent-check").check();
  const registered = page.waitForResponse(response =>
    response.url().includes("/api/v1/auth/register") && response.request().method() === "POST");
  await entry.locator("#f4-signup-form button[type='submit']").click();
  expect((await registered).status()).toBe(201);

  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 30_000 });
  await expect(page).toHaveURL(/\/today$/);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  const me = await page.evaluate(async () => {
    const response = await fetch("/api/v1/auth/me", { credentials: "include" });
    const body = response.ok ? await response.json() as { email: string } : null;
    return { status: response.status, email: body?.email ?? null };
  });
  expect(me).toEqual({ status: 200, email });

  await universe.locator(".nur-user").click();
  await expect(universe.locator("#nur-v197-owner-auth-menu")).toBeVisible();
  const loggedOut = page.waitForResponse(response =>
    response.url().includes("/api/v1/auth/logout") && response.request().method() === "POST");
  await universe.locator('[data-action="auth-logout"]').click();
  expect((await loggedOut).status()).toBe(204);
  await expect(page).toHaveURL(/\/$/);
  await expect(page.locator("#nur-universe-stage")).toBeHidden();
  await expect(page.frameLocator("#nur-entry-stage").locator("#f4-signin")).toBeVisible();

  await page.goto("/today", { waitUntil: "load" });
  await expect(page.locator("#nur-universe-stage")).not.toHaveClass(/is-visible/);
  await expect(page.frameLocator("#nur-entry-stage").locator("#f4-signin")).toBeVisible();
  const guarded = await page.evaluate(async () =>
    (await fetch("/api/v1/auth/me", { credentials: "include" })).status);
  expect(guarded).toBe(401);
});
