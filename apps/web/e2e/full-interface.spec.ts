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
  { path: "/universe/map", lens: "map", root: "#nur-map-root" },
  { path: "/universe/orbits", lens: "orbits", root: "#nur-orbit-root" },
  { path: "/universe/timeline", lens: "timeline", root: "#nur-timeline-root" },
  { path: "/universe/insights", lens: "insights", root: "#nur-insights-root" },
  { path: "/universe/research", lens: "system", root: "#page-systems" },
  { path: "/universe/web-signals", lens: "system", root: "#page-systems" },
] as const;

const adjunctRoutes = [
  { path: "/settings", marker: "Your NUR, held on your terms." },
  { path: "/capsule/cap-active", marker: "shared context" },
  { path: "/universe/omega", marker: "Evidence changes the model, deliberately." },
  { path: "/universe/omega/review", marker: "Nothing sensitive becomes truth by accident." },
  { path: `/universe/omega/why-changed/${mockClaim.id}`, marker: "Why NUR changed its mind." },
  { path: "/universe/consultation", marker: "A question moves when context returns." },
  { path: "/universe/community", marker: "Shared signal without private spill." },
] as const;

test("every primary product route resolves inside canonical V197 without staged replacement UI", async ({ browser }) => {
  test.slow();
  async function withFreshRoute(routePath: string, assertion: (page: Page, universe: ReturnType<Page["frameLocator"]>) => Promise<void>) {
    const context = await browser.newContext();
    const page = await context.newPage();
    try {
      await authenticate(page);
      const universe = page.frameLocator("#nur-universe-stage");
      await page.goto(routePath);
      await assertion(page, universe);
    } finally {
      await context.close();
    }
  }

  for (const route of canonicalPages) {
    await withFreshRoute(route.path, async (page, universe) => {
      await expect(universe.locator(route.selector), route.path).toBeVisible();
      await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);
      await expect(page.locator("#root")).toHaveCount(0);
    });
  }

  for (const route of worldLenses) {
    await withFreshRoute(route.path, async (page, universe) => {
      await expect(universe.locator(route.root), route.path).toBeVisible();
      if (route.root === "#page-systems") {
        await expect(universe.locator(".universe-insight-panel"), route.path)
          .toHaveAttribute("data-nur-lens", route.lens);
      } else {
        await expect(universe.locator(route.root), route.path)
          .toHaveAttribute("data-v197-native-adjunct", "true");
      }
      await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);
      await expect(page.locator("#root")).toHaveCount(0);
    });
  }

  for (const route of adjunctRoutes) {
    await withFreshRoute(route.path, async (page, universe) => {
      const adjunct = universe.locator("#nur-v197-adjunct-root");
      await expect(adjunct, route.path).toBeVisible();
      await expect(adjunct, route.path).toContainText(route.marker);
      await expect(adjunct).toHaveAttribute("data-v197-native-adjunct", "true");
      await expect(page.locator("#root")).toHaveCount(0);
    });
  }
});

test("Research remains Systems-hosted local staging while settings persist through bridge bindings", async ({ page }) => {
  const state = await authenticate(page);
  const universe = page.frameLocator("#nur-universe-stage");

  await page.goto("/universe/research");
  await expect(universe.locator("#page-systems")).toBeVisible();
  await expect(universe.locator("#research-staging")).toBeVisible();
  const researchQuestion = `Which local evidence should NUR hold? ${Date.now()}`;
  await universe.locator("#research-query").fill(researchQuestion);
  await universe.locator("[data-research-submit]").click();
  await expect.poll(() => state.researchBriefs.some(row => row.question === researchQuestion)).toBe(true);
  await page.reload({ waitUntil: "load" });
  await expect(universe.locator(".research-results")).toContainText(researchQuestion);
  await expect(universe.locator("#universe-community")).toBeVisible();
  await expect(universe.locator("#universe-community [data-adjunct-action]")).toHaveCount(0);

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
