/**
 * Baseline frame cadence with the cinematic stage OFF.
 *
 * Slice 1 measured 29.9 FPS. Before attributing that to the new scene, the same
 * measurement has to exist for the product as it ships today — otherwise a
 * harness-imposed cap would be misreported as a regression.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const PROOF_ROOT = path.resolve(process.cwd(), "../../proof/v8-baseline");

async function signIn(page: Page): Promise<void> {
  await page.goto("/");
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type=\'submit\']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25_000 });
}

test.describe("V8 baseline", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "Baseline captured once on Chromium.");

  test("measures the shipping Systems surface with the stage disabled", async ({ page }, testInfo) => {
    test.setTimeout(180_000);
    await mkdir(PROOF_ROOT, { recursive: true });

    await signIn(page);
    await page.goto("/systems");
    const universe = page.frameLocator("#nur-universe-stage");

    // The stage must be absent: this is the product as it ships.
    await expect(universe.locator("#nur-visual-stage")).toHaveCount(0);
    // Let hydration finish; measuring during it destroys the execution context.
    await expect(universe.locator(".universe-system-node")).toHaveCount(7, { timeout: 20_000 });
    await page.waitForTimeout(2500);

    const metrics = await universe.locator("body").evaluate(async () => {
      const samples: number[] = [];
      await new Promise<void>(resolve => {
        let previous = 0;
        let frames = 0;
        const step = (now: number) => {
          if (previous !== 0) samples.push(now - previous);
          previous = now;
          frames += 1;
          if (frames < 180) window.requestAnimationFrame(step);
          else resolve();
        };
        window.requestAnimationFrame(step);
      });
      samples.sort((a, b) => a - b);
      const median = samples[Math.floor(samples.length / 2)] ?? 0;
      const p95 = samples[Math.floor(samples.length * 0.95)] ?? 0;
      return {
        canvases: document.querySelectorAll("canvas").length,
        medianFrameMs: Number(median.toFixed(2)),
        p95FrameMs: Number(p95.toFixed(2)),
        longFrames: samples.filter(value => value > 50).length,
        fpsMedian: Number((1000 / Math.max(0.001, median)).toFixed(1)),
      };
    });

    for (const viewport of [
      { label: "1920x1080", width: 1920, height: 1080 },
      { label: "390x844", width: 390, height: 844 },
    ]) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.waitForTimeout(700);
      await page.screenshot({ path: path.join(PROOF_ROOT, `systems-${viewport.label}.png`) });
    }

    await writeFile(
      path.join(PROOF_ROOT, "baseline-metrics.json"),
      `${JSON.stringify({ ...metrics, capturedAt: new Date().toISOString() }, null, 2)}\n`,
      "utf8",
    );
    await testInfo.attach("baseline-metrics", { body: JSON.stringify(metrics, null, 2), contentType: "application/json" });
  });
});
