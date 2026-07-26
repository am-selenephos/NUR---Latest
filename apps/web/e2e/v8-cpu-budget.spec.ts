import { expect, test, type Page } from "@playwright/test";

async function signIn(page: Page) {
  const e = page.frameLocator("#nur-entry-stage");
  await e.locator("body").evaluate(() => (window as any).nurShowFront?.());
  await e.locator("#f4-signin").click();
  await e.locator("#f4-signin-email").fill("owner@nur.app");
  await e.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await e.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25000 });
}

test("real CPU cost per surface", async ({ page }) => {
  test.setTimeout(240000);
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");

  const cpuOver = async (ms: number) => {
    const read = async () => {
      const { metrics } = await cdp.send("Performance.getMetrics");
      const get = (n: string) => metrics.find(m => m.name === n)?.value ?? 0;
      return { task: get("TaskDuration"), script: get("ScriptDuration"), layout: get("LayoutDuration"), ts: get("Timestamp") };
    };
    const a = await read();
    await page.waitForTimeout(ms);
    const b = await read();
    const wall = b.ts - a.ts;
    return {
      wallSeconds: Number(wall.toFixed(2)),
      taskSeconds: Number((b.task - a.task).toFixed(3)),
      scriptSeconds: Number((b.script - a.script).toFixed(3)),
      cpuPercent: Number((((b.task - a.task) / wall) * 100).toFixed(1)),
    };
  };

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.waitForTimeout(1500);
  await page.frameLocator("#nur-entry-stage").locator("body").evaluate(() => (window as any).nurShowFront?.());
  await page.waitForTimeout(2500);
  const entry = await cpuOver(6000);
  console.log("ENTRY_CPU " + JSON.stringify(entry));

  await signIn(page);
  await page.goto("/systems");
  await page.waitForTimeout(2500);
  const systems = await cpuOver(6000);
  console.log("SYSTEMS_CPU " + JSON.stringify(systems));

  /* Measured with CDP Performance.getMetrics, which reports real task time and
     is immune to the rAF throttling that makes frame-interval sampling useless
     in headless Chromium.

     Attribution on this harness:
       original brain, no deep field       Entry 66.2%   Systems 19.1%
       denser brain, no deep field         Entry 69.4%   Systems 24.6%
       denser brain + field as a canvas    Entry 80.5%   Systems 28.1%
       denser brain + field as a bitmap    Entry 71.3%   Systems 26.5%

     The canvas-layer version cost eleven points on Entry in compositing alone
     despite never redrawing, which is why the field ships as a static CSS
     bitmap. These ceilings sit above the accepted figures with headroom for
     run-to-run variance and would catch a real regression. */
  expect(entry.cpuPercent).toBeLessThan(78);
  expect(systems.cpuPercent).toBeLessThan(34);
});
