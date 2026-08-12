import { expect, test } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

test("Settings downloads the real owner export and revokes a selected session", async ({ page }) => {
  const state = await installNurMocks(page);
  await page.goto("/settings", { waitUntil: "networkidle" });
  const frame = page.frameLocator("#nur-universe-stage");
  const adjunct = frame.locator("#nur-v197-adjunct-root");
  await expect(adjunct.locator("h1")).toHaveText("Your NUR, held on your terms.");
  await expect(adjunct.getByText("2 owner-scoped sessions.")).toBeVisible();

  const downloadPromise = page.waitForEvent("download");
  await adjunct.locator('[data-adjunct-action="settings-export"]').click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe("nur-owner-export-v1.json");
  await expect(adjunct.getByText(/SHA-256 mock-owner-export-checksum/)).toBeVisible();

  await adjunct.locator('[data-adjunct-action="settings-revoke-session-bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"]').click();
  await expect(adjunct.getByText("Session revoked.")).toBeVisible();
  expect(state.ownerSessions.find(row => row.id === "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb")?.state).toBe("revoked");
  expect(state.accountWrites.map(row => row.path)).toEqual([
    "/api/v1/account/export",
    "/api/v1/auth/sessions/bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",
  ]);
});

test("Settings deletion requires reauthentication and exact owner confirmation", async ({ page }) => {
  const state = await installNurMocks(page);
  await page.goto("/settings", { waitUntil: "networkidle" });
  const frame = page.frameLocator("#nur-universe-stage");
  const adjunct = frame.locator("#nur-v197-adjunct-root");

  await adjunct.locator('[data-adjunct-control="delete-password"]').fill("owner-password");
  await adjunct.locator('[data-adjunct-control="delete-confirmation"]').fill("DELETE MY NUR ACCOUNT");
  page.once("dialog", dialog => dialog.accept());
  await adjunct.locator('[data-adjunct-action="settings-delete"]').click();

  await expect(page).toHaveURL(/\/auth$/);
  await expect(page.frameLocator("#nur-entry-stage").locator("#f4-signin")).toBeVisible();
  expect(state.accountDeleted).toBe(true);
  expect(state.accountWrites.at(-1)).toEqual({
    path: "/api/v1/account",
    body: { password: "owner-password", confirmation: "DELETE MY NUR ACCOUNT" },
  });
});
