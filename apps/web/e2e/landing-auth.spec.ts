import { expect, test, type Route } from "@playwright/test";

import { installNurMocks, json, mockUser } from "./helpers/nurMocks";

test.use({ serviceWorkers: "block" });

test("V197 landing preserves its hero and the mocked auth lifecycle", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The complete mocked auth lifecycle runs once in Chromium.");
  let authenticated = false;
  let registerCalls = 0;
  let loginCalls = 0;
  let logoutCalls = 0;
  const establishMockSession = () => page.context().addCookies([
    { name: "nur_session", value: "mock-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "mock-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);

  await installNurMocks(page);
  // Registered last so this stateful auth handler takes precedence over the
  // broader deterministic data mocks used to hydrate the authenticated shell.
  await page.route("**/api/v1/auth/**", async (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/me") {
      return authenticated ? json(route, mockUser) : json(route, { detail: "Not authenticated" }, 401);
    }
    if (path === "/api/v1/auth/register" || path === "/api/v1/auth/login") {
      if (path.endsWith("/register")) registerCalls += 1;
      else loginCalls += 1;
      authenticated = true;
      await establishMockSession();
      return json(route, path.endsWith("/login") ? { ok: true } : mockUser, path.endsWith("/login") ? 200 : 201);
    }
    if (path === "/api/v1/auth/logout") {
      logoutCalls += 1;
      authenticated = false;
      await page.context().clearCookies();
      return json(route, undefined, 204);
    }
    return json(route, { detail: "unhandled" }, 404);
  });

  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  const hero = entry.getByRole("heading", { name: "There is a universe inside your mind.", exact: true });
  await expect(hero).toBeVisible();
  const visibleHeroText = await entry.locator(".f4-title").evaluate(element =>
    (element as HTMLElement).innerText.replace(/\s+/g, " ").trim());
  expect(visibleHeroText).toBe("There is a universe inside your mind.");
  await expect(entry.locator(".f4-title em")).toHaveText("mind.");
  const mindStyle = await entry.locator(".f4-title em").evaluate(element => ({
    text: element.textContent,
    display: getComputedStyle(element).display,
    backgroundClip: getComputedStyle(element).backgroundClip,
    webkitTextFillColor: getComputedStyle(element).webkitTextFillColor,
  }));
  expect(mindStyle.text).toBe("mind.");
  expect(mindStyle.display).not.toBe("block");
  expect(mindStyle.backgroundClip).toContain("text");
  expect(mindStyle.webkitTextFillColor).toBe("rgba(0, 0, 0, 0)");
  await expect(entry.locator(".f4-brand-word")).toHaveText("NUR");

  await entry.locator("#f4-begin").click();
  await expect(entry.locator('[data-mode="signup"]')).toHaveClass(/active/);
  await entry.locator("#f4-name").fill("Selene");
  await entry.locator("#f4-email").fill("selene@nurapp.dev");
  await entry.locator("#f4-password").fill("orbit-pass-2026");
  const consent = entry.locator("#f4-consent-check");
  if (await consent.count()) await consent.check();
  await entry.locator('#f4-signup-form button[type="submit"]').click();
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  await expect(page).toHaveURL(/\/today$/);

  for (let cycle = 1; cycle <= 3; cycle += 1) {
    const activeUniverse = page.frameLocator("#nur-universe-stage");
    await expect(activeUniverse.locator("#nur-v197-owner-auth-menu")).toBeAttached({ timeout: 20_000 });
    await activeUniverse.locator(".nur-user").click();
    await expect(activeUniverse.locator("#nur-v197-owner-auth-menu")).toBeVisible();
    await activeUniverse.locator('[data-action="auth-logout"]').click();
    await expect(page).toHaveURL(/\/$/);
    await expect(page.locator("#nur-entry-stage")).toBeVisible();
    await expect(page.locator("#nur-entry-stage")).not.toHaveAttribute("aria-hidden", "true");
    await expect(page.locator("#nur-entry-stage")).not.toHaveAttribute("inert", "");
    await expect(page.locator("#nur-universe-stage")).toBeHidden();

    const returnedEntry = page.frameLocator("#nur-entry-stage");
    await expect(returnedEntry.locator("#f4-signin")).toBeVisible();
    await expect(returnedEntry.locator("#intro")).toBeHidden();
    expect(await page.evaluate(() => sessionStorage.getItem("nur:v197:logout-entry"))).toBeNull();
    await returnedEntry.locator("#f4-signin").click();
    await returnedEntry.locator("#f4-signin-email").fill("selene@nurapp.dev");
    await returnedEntry.locator("#f4-signin-password").fill("orbit-pass-2026");
    await returnedEntry.locator('#f4-signin-form button[type="submit"]').click();
    await expect(page.frameLocator("#nur-universe-stage").locator("#page-today")).toBeVisible({ timeout: 20_000 });
    await expect(page).toHaveURL(/\/today$/);
  }
  expect({ registerCalls, loginCalls, logoutCalls }).toEqual({ registerCalls: 1, loginCalls: 3, logoutCalls: 3 });
});
