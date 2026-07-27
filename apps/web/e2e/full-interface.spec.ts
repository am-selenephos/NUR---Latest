import { expect, test, type Page } from "@playwright/test";

import { installNurMocks, mockClaim } from "./helpers/nurMocks";

test.use({ serviceWorkers: "block" });

async function authenticate(page: Page) {
  const state = await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "full-interface-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "full-interface-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  return state;
}

const canonicalPages = [
  { path: "/today", selector: "#page-today" },
  { path: "/talk", selector: "#page-talk" },
  { path: "/journal", selector: "#page-journal" },
  { path: "/plan", selector: "#page-plan" },
  { path: "/systems", selector: "#page-systems" },
  { path: "/universe", selector: "#page-systems" },
] as const;

const worldLenses = [
  { path: "/universe/map", lens: "map" },
  { path: "/universe/orbits", lens: "orbits" },
  { path: "/universe/timeline", lens: "timeline" },
  { path: "/universe/insights", lens: "insights" },
  { path: "/universe/research", lens: "research" },
  { path: "/universe/community", lens: "community" },
  { path: "/universe/web-signals", lens: "web" },
] as const;

const adjunctRoutes = [
  { path: "/settings", marker: "Your NUR, held on your terms." },
  { path: "/capsule/cap-active", marker: "shared context" },
  { path: "/universe/omega", marker: "Evidence changes the model, deliberately." },
  { path: "/universe/omega/review", marker: "Nothing sensitive becomes truth by accident." },
  { path: `/universe/omega/why-changed/${mockClaim.id}`, marker: "Why NUR changed its mind." },
] as const;

test("every primary product route resolves inside canonical V197 without staged replacement UI", async ({ page }) => {
  await authenticate(page);
  const universe = page.frameLocator("#nur-universe-stage");

  for (const route of canonicalPages) {
    await page.goto(route.path);
    await expect(universe.locator(route.selector), route.path).toBeVisible();
    await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);
    await expect(page.locator("#root")).toHaveCount(0);
  }

  for (const route of worldLenses) {
    await page.goto(route.path);
    await expect(universe.locator("#page-systems"), route.path).toBeVisible();
    await expect(universe.locator(".universe-insight-panel"), route.path)
      .toHaveAttribute("data-nur-lens", route.lens);
    await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);
    await expect(page.locator("#root")).toHaveCount(0);
  }

  for (const route of adjunctRoutes) {
    await page.goto(route.path);
    const adjunct = universe.locator("#nur-v197-adjunct-root");
    await expect(adjunct, route.path).toBeVisible();
    await expect(adjunct, route.path).toContainText(route.marker);
    await expect(adjunct).toHaveAttribute("data-v197-native-adjunct", "true");
    await expect(page.locator("#root")).toHaveCount(0);
  }

  await expect(universe.locator("body")).not.toContainText(
    /This lens is staged|full view arrives with its data|Phase 3 shared-system|Mark a Personal Glow/i,
  );
});

test("primary research and settings controls persist through current bridge bindings", async ({ page }) => {
  const state = await authenticate(page);
  const universe = page.frameLocator("#nur-universe-stage");

  await page.goto("/universe/research");
  await universe.locator("#research-query").fill("Which source verifies the current route?");
  await universe.locator("[data-research-submit]").click();
  await expect.poll(() => state.researchBriefs.some(
    row => row.question === "Which source verifies the current route?",
  )).toBe(true);
  await expect(universe.locator("#universe-research .research-results"))
    .toContainText("Which source verifies the current route?");

  await page.goto("/settings");
  const locale = universe.locator('[data-adjunct-control="locale"]');
  await locale.selectOption("ur");
  await universe.locator('[data-adjunct-control="writing-preference"]').selectOption("roman");
  await universe.locator('[data-adjunct-action="settings-save"]').click();
  await expect.poll(() => state.preferences.locale).toBe("ur");
  await expect.poll(() => state.preferences.writing_preference).toBe("roman");
  await expect(universe.locator("html")).toHaveAttribute("lang", "ur");
  await expect(universe.locator("html")).toHaveAttribute("dir", "ltr");
});
