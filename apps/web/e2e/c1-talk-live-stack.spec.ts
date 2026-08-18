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

test("C1 proves the live Talk SSE boundary and honest disabled-provider reload path", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The real Talk mutation runs once on desktop.");
  test.setTimeout(120_000);

  const email = `c1-${Date.now()}-${Math.floor(Math.random() * 1e6)}@nurapp.dev`;
  const message = `C1 durable Talk trace ${Date.now()}`;
  const entry = await revealEntry(page);

  await entry.locator("#f4-begin").click();
  await entry.locator("#f4-name").fill("C1 Owner");
  await entry.locator("#f4-email").fill(email);
  await entry.locator("#f4-password").fill("orbit-pass-2026");
  await entry.locator("#f4-consent-check").check();
  const registered = page.waitForResponse(response => (
    response.url().includes("/api/v1/auth/register") && response.request().method() === "POST"
  ));
  await entry.locator("#f4-signup-form button[type='submit']").click();
  expect((await registered).status()).toBe(201);

  await page.goto("/talk", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-talk")).toBeVisible({ timeout: 30_000 });

  const stream = page.waitForResponse(response => (
    response.url().includes("/api/v1/cognition/talk/stream") && response.request().method() === "POST"
  ));
  await universe.locator("#talk-input").fill(message);
  await universe.getByRole("button", { name: "Send to NUR" }).click();
  expect((await stream).status()).toBe(200);

  await expect(universe.locator("#talk-stream .talk-message.user")).toContainText(message, { timeout: 30_000 });
  await expect(universe.locator("#talk-stream [data-nur-talk-error='true']")).toContainText("Live AI is not connected", { timeout: 30_000 });
  await expect(universe.locator("#talk-stream .talk-message.nur:not([data-nur-talk-error='true'])")).toHaveCount(0);

  await page.reload({ waitUntil: "load" });
  const rehydrated = page.frameLocator("#nur-universe-stage");
  await expect(rehydrated.locator("#page-talk")).toBeVisible({ timeout: 30_000 });
  await expect(rehydrated.locator("#talk-stream .talk-message.user")).toContainText(message, { timeout: 30_000 });
  await expect(rehydrated.locator("#talk-stream")).not.toContainText("I saved this turn, but live AI is disabled on this server.");
});
