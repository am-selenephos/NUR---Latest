import { expect, test, type Page, type Route } from "@playwright/test";

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function signedOutEntry(page: Page, path: string): Promise<ReturnType<Page["frameLocator"]>> {
  await page.route("**/api/v1/auth/me", route => json(route, { detail: "Not authenticated" }, 401));
  await page.goto(path, { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect(entry.locator("#f4-signin")).toBeVisible();
  return entry;
}

test("Entry requests password recovery without revealing whether an account exists", async ({ page }) => {
  let submittedEmail = "";
  await page.route("**/api/v1/auth/password/forgot", async route => {
    submittedEmail = String((route.request().postDataJSON() as { email?: string }).email ?? "");
    await json(route, {
      accepted: true,
      message: "If an account matches that email, reset instructions will be sent.",
    }, 202);
  });

  const entry = await signedOutEntry(page, "/auth");
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator('[data-password-recovery-open="true"]').click();

  const dialog = entry.locator("#nur-v197-password-recovery");
  await expect(dialog).toBeVisible();
  await expect(dialog.locator("#nur-v197-forgot-email")).toHaveValue("owner@nur.app");
  await dialog.locator("#nur-v197-forgot-form button[type='submit']").click();
  await expect(dialog.locator('[data-password-recovery-status="true"]')).toHaveText(
    "If an account matches that email, reset instructions will be sent.",
  );
  expect(submittedEmail).toBe("owner@nur.app");
});

test("one-time reset link changes the password and removes the token from the URL", async ({ page }) => {
  let submitted: Record<string, unknown> | null = null;
  await page.route("**/api/v1/auth/password/reset", async route => {
    submitted = route.request().postDataJSON() as Record<string, unknown>;
    await route.fulfill({ status: 204, body: "" });
  });

  const entry = await signedOutEntry(page, "/reset-password?token=opaque-one-time-token");
  const dialog = entry.locator("#nur-v197-password-recovery");
  await expect(dialog).toBeVisible();
  await dialog.locator("#nur-v197-reset-password").fill("new-private-password-2026");
  await dialog.locator("#nur-v197-reset-confirmation").fill("new-private-password-2026");
  await dialog.locator("#nur-v197-reset-form button[type='submit']").click();

  await expect(dialog.locator('[data-password-recovery-status="true"]')).toHaveText(
    "Password changed. Sign in to return to your Orbit.",
  );
  await expect(page).toHaveURL(/\/auth$/);
  expect(submitted).toEqual({
    token: "opaque-one-time-token",
    new_password: "new-private-password-2026",
  });
});
