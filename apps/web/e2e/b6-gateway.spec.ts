import { expect, test, type FrameLocator, type Page } from "@playwright/test";

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

test("B6 proves browser → FastAPI → durable owner state → V197 rehydrate", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The real gateway mutation runs once on desktop.");
  test.setTimeout(120_000);

  const email = `b6-${Date.now()}-${Math.floor(Math.random() * 1e6)}@nurapp.dev`;
  const journalLine = `B6 durable journal trace ${Date.now()}`;
  const entry = await revealEntry(page);

  await entry.locator("#f4-begin").click();
  await entry.locator("#f4-name").fill("B6 Owner");
  await entry.locator("#f4-email").fill(email);
  await entry.locator("#f4-password").fill("orbit-pass-2026");
  await entry.locator("#f4-consent-check").check();
  const registered = page.waitForResponse(response => (
    response.url().includes("/api/v1/auth/register") && response.request().method() === "POST"
  ));
  await entry.locator("#f4-signup-form button[type='submit']").click();
  expect((await registered).status()).toBe(201);

  await expect(page).toHaveURL(/\/today$/);
  await page.goto("/journal", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-journal")).toBeVisible({ timeout: 30_000 });

  const journalWrite = page.waitForResponse(response => (
    response.url().includes("/api/v1/journal") && response.request().method() === "POST"
  ));
  await universe.locator("#journal-input").fill(journalLine);
  await universe.locator("#journal-save").click();
  expect((await journalWrite).status()).toBe(201);
  await expect(universe.locator("#journal-input")).toHaveValue("");

  const read = await page.evaluate(async () => {
    const response = await fetch("/api/v1/journal", { credentials: "include" });
    return { status: response.status, body: await response.json() } as {
      status: number;
      body: Array<{ body?: string }>;
    };
  });
  expect(read.status).toBe(200);
  expect(read.body.some(row => row.body === journalLine)).toBe(true);

  await page.reload({ waitUntil: "load" });
  const rehydrated = page.frameLocator("#nur-universe-stage");
  await expect(rehydrated.locator("#page-journal")).toBeVisible({ timeout: 30_000 });
  await expect(rehydrated.locator("#page-journal .journal-prompt")).toContainText(journalLine);
});
