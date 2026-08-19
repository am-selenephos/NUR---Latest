import { expect, test } from "@playwright/test";

import { installNurMocks, mockClaim } from "./helpers/nurMocks";

test.use({ serviceWorkers: "block" });

test("seeded Insights renders persisted review state inside the canonical iframe", async ({ page }) => {
  await installNurMocks(page);
  await page.goto("/universe/insights");

  const universe = page.frameLocator("#nur-universe-stage");
  const insights = universe.locator("#nur-insights-root");
  await expect(insights).toBeVisible();
  await expect(insights).toContainText("OWNER INTERPRETATION FIELD");
  await expect(insights).toContainText("omega_owner_ledger");
  await expect(insights).toContainText(mockClaim.claim_text);
  await expect(insights.locator(".nur-insights-count").filter({ hasText: "Candidate claims" })).toContainText("1");
  await expect(insights.locator(".nur-insights-count").filter({ hasText: "Open tensions" })).toContainText("1");
  await expect(insights.locator(".nur-insights-count").filter({ hasText: "Predictions" })).toContainText("1");
  await expect(insights.locator(".nur-insights-count").filter({ hasText: "Awaiting review" })).toContainText("1");
  await expect(insights.locator(".nur-insights-review")).toContainText("Open tensions");
  await expect(insights.locator(".nur-insights-review")).toContainText("Possible futures");
  await expect(insights.locator(".nur-insights-review")).toContainText("Owner review");
  await expect(insights.locator(".nur-insights-review")).toContainText("The owner may prefer evidence-gated learning.");

  const navItem = insights.locator(".nur-insights-nav-item").first();
  await navItem.click();
  await expect(insights.locator(".nur-insights-detail")).toContainText("82% confidence");
  await expect(insights.locator(".nur-insights-detail")).toContainText("Source domains not recorded");

  await page.reload();
  await expect(universe.locator("#nur-insights-root")).toContainText(mockClaim.claim_text);
});
