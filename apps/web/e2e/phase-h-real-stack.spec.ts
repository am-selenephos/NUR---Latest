import { expect, test, type FrameLocator, type Page } from "@playwright/test";

type Surface = {
  name: string;
  route: string;
  selector: string;
};

const SURFACES: Surface[] = [
  { name: "today", route: "/today", selector: "#page-today" },
  { name: "talk", route: "/talk", selector: "#page-talk" },
  { name: "journal", route: "/journal", selector: "#page-journal" },
  { name: "plan", route: "/plan", selector: "#page-plan" },
  { name: "systems", route: "/systems", selector: "#page-systems" },
  { name: "orbit", route: "/universe/orbits", selector: "#nur-orbit-root" },
  { name: "map", route: "/universe/map", selector: "#nur-map-root" },
  { name: "timeline", route: "/universe/timeline", selector: "#nur-timeline-root" },
  { name: "insights", route: "/universe/insights", selector: "#nur-insights-root" },
  { name: "agents", route: "/agents", selector: "#nur-v197-adjunct-root" },
  { name: "memory", route: "/memory", selector: "#nur-v197-adjunct-root" },
  { name: "projects", route: "/projects", selector: "#nur-v197-adjunct-root" },
  { name: "capsules", route: "/capsules", selector: "#nur-v197-adjunct-root" },
  { name: "research", route: "/systems", selector: "#universe-research" },
  { name: "community", route: "/universe/community", selector: "#nur-v197-adjunct-root" },
  { name: "billing", route: "/billing", selector: "#nur-v197-adjunct-root" },
  { name: "notifications", route: "/notifications", selector: "#nur-v197-adjunct-root" },
];

async function revealEntry(page: Page): Promise<FrameLocator> {
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

async function registerOwner(page: Page): Promise<void> {
  const entry = await revealEntry(page);
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  await entry.locator("#f4-begin").click();
  await entry.locator("#f4-name").fill("Phase H Owner");
  await entry.locator("#f4-email").fill(`phase-h-${suffix}@nurapp.dev`);
  await entry.locator("#f4-password").fill("orbit-pass-2026");
  await entry.locator("#f4-consent-check").check();
  const registered = page.waitForResponse(response => (
    response.url().includes("/api/v1/auth/register") && response.request().method() === "POST"
  ));
  await entry.locator("#f4-signup-form button[type='submit']").click();
  expect((await registered).status()).toBe(201);
  await expect(page).toHaveURL(/\/today$/);
}

test("Phase H mounts every canonical product surface on the real stack", async ({ page }, testInfo) => {
  test.setTimeout(240_000);
  const serverErrors: string[] = [];
  const pageErrors: string[] = [];

  page.on("response", response => {
    if (response.status() >= 500) serverErrors.push(`${response.status()} ${response.request().method()} ${response.url()}`);
  });
  page.on("pageerror", error => pageErrors.push(error.message));

  await registerOwner(page);
  const universe = page.frameLocator("#nur-universe-stage");

  for (const surface of SURFACES) {
    await page.goto(surface.route, { waitUntil: "load" });
    const root = universe.locator(surface.selector);
    await expect(root, `${surface.name} must mount its canonical V197 root`).toBeVisible({ timeout: 30_000 });
    await testInfo.attach(`${surface.name}-${testInfo.project.name}`, {
      body: await page.screenshot({ fullPage: false }),
      contentType: "image/png",
    });
  }

  expect(serverErrors, `Unexpected 5xx responses:\n${serverErrors.join("\n")}`).toEqual([]);
  expect(pageErrors, `Uncaught page errors:\n${pageErrors.join("\n")}`).toEqual([]);
});
