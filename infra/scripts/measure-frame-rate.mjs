#!/usr/bin/env node
/**
 * Frame rate from a real Chrome trace.
 *
 * Use this, not CDP screencast. Screencast JPEG-encodes every frame, and at
 * 1920x1080 and above the encoder saturates well below the true rate — it read
 * 8 FPS where the trace reads 25, and it read 16 FPS under a 6x CPU throttle
 * against 8 unthrottled, which is impossible for an application and was the
 * clue that the harness was the thing being measured.
 *
 * `commits/s` is the number to read: one Commit is one composited frame.
 * DrawFrame and PipelineReporter fire several times per frame across pipeline
 * stages, so a DrawFrame count reads in the hundreds and means nothing on its
 * own. rasterTasks/s shows how much content is being re-rasterised rather than
 * reused, which is the useful signal when commits are low.
 *
 *   node infra/scripts/measure-frame-rate.mjs
 */
import { chromium } from "@playwright/test";

const WEB = process.env.WEB_ORIGIN ?? "http://localhost:4173";
const EMAIL = process.env.NUR_DEMO_OWNER_EMAIL ?? "owner@nur.app";
const PASSWORD = process.env.NUR_DEMO_OWNER_PASSWORD ?? "owner-demo-pass-123";

const browser = await chromium.launch({
  headless: false,
  args: ["--enable-gpu", "--ignore-gpu-blocklist"],
});

async function frames(page, seconds, label) {
  const cdp = await page.context().newCDPSession(page);
  const events = [];
  cdp.on("Tracing.dataCollected", ({ value }) => events.push(...value));
  await cdp.send("Tracing.start", {
    traceConfig: {
      includedCategories: [
        "disabled-by-default-devtools.timeline.frame",
        "disabled-by-default-devtools.timeline",
        "benchmark",
        "viz",
      ],
    },
  });
  const started = Date.now();
  await page.waitForTimeout(seconds * 1000);
  const complete = new Promise(resolve => cdp.once("Tracing.tracingComplete", resolve));
  await cdp.send("Tracing.end");
  await complete;
  const elapsed = (Date.now() - started) / 1000;
  await cdp.detach();

  const commits = events.filter(event => event.name === "Commit").length;
  const raster = events.filter(event => event.name === "RasterTask").length;
  console.log(
    `${label.padEnd(22)} commits/s=${(commits / elapsed).toFixed(1)}` +
    `  rasterTasks/s=${(raster / elapsed).toFixed(0)}`,
  );
}

async function signIn(page) {
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill(EMAIL);
  await entry.locator("#f4-signin-password").fill(PASSWORD);
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await page.waitForTimeout(9000);
}

for (const [width, height, tag] of [[1920, 1080, "FHD"], [2560, 1440, "QHD"]]) {
  const context = await browser.newContext({ viewport: { width, height }, deviceScaleFactor: 1 });
  const page = await context.newPage();

  await page.goto(WEB);
  await page.waitForTimeout(4000);
  await page.frameLocator("#nur-entry-stage").locator("body")
    .evaluate(() => window.nurShowFront?.());
  await page.waitForTimeout(5000);
  await frames(page, 5, `ENTRY ${tag}`);

  await signIn(page);
  await page.goto(`${WEB}/systems`);
  await page.waitForTimeout(6000);
  await frames(page, 5, `SYSTEMS ${tag}`);

  await context.close();
}

await browser.close();
