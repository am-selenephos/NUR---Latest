import { expect, test } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

test("removes the disabled Plan direction placeholder", async ({ page }) => {
  await installNurMocks(page);
  await page.goto("/plan", { waitUntil: "networkidle" });
  const plan = page.frameLocator("#nur-universe-stage").locator("#page-plan");

  await expect(plan).toBeVisible();
  await expect(plan.locator(".panel-top .tiny-link:not([data-page])")).toHaveCount(0);
  await expect(plan).not.toContainText("Direction editing opens in Track B");
});

test("retired Community utility routes return to bounded rooms", async ({ page }) => {
  await installNurMocks(page);
  const adjunct = page.frameLocator("#nur-universe-stage").locator("#nur-v197-adjunct-root");

  for (const route of [
    "/community/people",
    "/community/saved",
    "/community/notifications",
    "/community/moderation",
  ]) {
    await page.goto(route, { waitUntil: "networkidle" });
    await expect(page).toHaveURL(/\/universe\/community$/);
    await expect(adjunct.getByRole("heading", { name: "Shared signal without private spill." })).toBeVisible();
    await expect(adjunct).not.toContainText("Not connected in this build");
  }
});
