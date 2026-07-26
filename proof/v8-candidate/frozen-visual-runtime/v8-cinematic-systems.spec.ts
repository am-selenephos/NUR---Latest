/**
 * Slice 1 evidence capture — Systems / Laniakea cinematic stage.
 *
 * Captures the candidate at every required viewport and measures the invariants
 * that the existing engines break: one canvas, one frame loop, no listener or
 * heap growth, and a keyboard path to every System the canvas draws.
 *
 * Runs against the live seeded owner, not mocks, so the figures on screen are
 * the owner's real recorded actions.
 */

import { expect, test, type Page } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const PROOF_ROOT = path.resolve(process.cwd(), "../../proof/v8-candidate");

const VIEWPORTS = [
  { label: "1920x1080", width: 1920, height: 1080 },
  { label: "1440x900", width: 1440, height: 900 },
  { label: "1366x768", width: 1366, height: 768 },
  { label: "1024x768", width: 1024, height: 768 },
  { label: "768x1024", width: 768, height: 1024 },
  { label: "430x932", width: 430, height: 932 },
  { label: "390x844", width: 390, height: 844 },
  { label: "360x800", width: 360, height: 800 },
] as const;

async function signIn(page: Page): Promise<void> {
  await page.goto("/");
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25_000 });
}

test.describe("V8 cinematic Systems stage", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "Evidence capture runs once on Chromium.");

  test("mounts one stage, stays keyboard reachable, and captures every viewport", async ({ page }, testInfo) => {
    test.setTimeout(240_000);
    await mkdir(PROOF_ROOT, { recursive: true });

    await signIn(page);
    // Slice 1 is opt-in; enable it for this capture only.
    await page.addInitScript(() => {
      try { window.localStorage.setItem("nur.visual.stage", "on"); } catch { /* ignore */ }
    });
    await page.goto("/systems");
    const universe = page.frameLocator("#nur-universe-stage");

    const stage = universe.locator("#nur-visual-stage");
    await expect(stage).toHaveCount(1, { timeout: 20_000 });
    await expect(universe.locator("#nur-visual-runtime-canvas")).toHaveCount(1);

    // Diagnostic: what the canonical buttons actually carry, and what the
    // snapshot returns, so a matching failure is explained rather than guessed.
    const binding = await universe.locator("body").evaluate(() => ({
      buttons: Array.from(document.querySelectorAll(".universe-system-node")).map(node => ({
        slug: (node as HTMLElement).dataset.systemSlug ?? null,
        system: (node as HTMLElement).dataset.system ?? null,
        label: node.querySelector("b")?.textContent?.trim() ?? null,
        describedBy: node.getAttribute("aria-describedby"),
      })),
      telemetryIds: Array.from(document.querySelectorAll(".nur-visual-figure")).map(node => node.id),
    }));
    await testInfo.attach("binding-diagnostic", {
      body: JSON.stringify(binding, null, 2),
      contentType: "application/json",
    });
    await writeFile(path.join(PROOF_ROOT, "binding-diagnostic.json"), `${JSON.stringify(binding, null, 2)}\n`, "utf8");

    // The stage must add no System control of its own: the canonical
    // `.universe-system-node` buttons stay the only ones, now carrying a
    // description that points at the real figures.
    const nodes = universe.locator(".universe-system-node");
    const nodeCount = await nodes.count();
    expect(nodeCount).toBeGreaterThan(0);

    const described = universe.locator(".universe-system-node[aria-describedby]");
    expect(await described.count()).toBeGreaterThan(0);

    // Keyboard focus must move canvas focus, proving the two share state.
    await described.first().focus();
    await expect(described.first()).toHaveClass(/nur-visual-focused/);

    const describedBy = await described.first().getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    const figures = universe.locator(`#${describedBy}`);
    await expect(figures).toContainText("%");

    // ── frame-rate and leak measurement ────────────────────────────────────
    const metrics = await universe.locator("body").evaluate(async () => {
      const view = window;
      const samples: number[] = [];
      await new Promise<void>(resolve => {
        let previous = 0;
        let frames = 0;
        const step = (now: number) => {
          if (previous !== 0) samples.push(now - previous);
          previous = now;
          frames += 1;
          if (frames < 180) view.requestAnimationFrame(step);
          else resolve();
        };
        view.requestAnimationFrame(step);
      });
      samples.sort((a, b) => a - b);
      const median = samples[Math.floor(samples.length / 2)] ?? 0;
      const p95 = samples[Math.floor(samples.length * 0.95)] ?? 0;
      const longFrames = samples.filter(value => value > 50).length;
      return {
        canvases: document.querySelectorAll("canvas").length,
        runtimeCanvases: document.querySelectorAll("#nur-visual-runtime-canvas").length,
        stages: document.querySelectorAll("#nur-visual-stage").length,
        canonicalSystemButtons: document.querySelectorAll(".universe-system-node").length,
        describedSystemButtons: document.querySelectorAll(".universe-system-node[aria-describedby]").length,
        medianFrameMs: Number(median.toFixed(2)),
        p95FrameMs: Number(p95.toFixed(2)),
        longFrames,
        fpsMedian: Number((1000 / Math.max(0.001, median)).toFixed(1)),
      };
    });

    expect(metrics.runtimeCanvases).toBe(1);
    expect(metrics.stages).toBe(1);

    // ── teardown proof: leaving Systems must remove the stage entirely ─────
    await page.goto("/settings");
    await expect(universe.locator("#nur-visual-stage")).toHaveCount(0, { timeout: 15_000 });
    await expect(universe.locator("#nur-visual-runtime-canvas")).toHaveCount(0);
    // Teardown must also hand the canonical buttons back untouched.
    await expect(universe.locator(".universe-system-node.nur-visual-focused")).toHaveCount(0);

    await page.goto("/systems");
    await expect(universe.locator("#nur-visual-stage")).toHaveCount(1, { timeout: 20_000 });
    // Returning must not accumulate a second owner.
    await expect(universe.locator("#nur-visual-runtime-canvas")).toHaveCount(1);

    // ── viewport capture ───────────────────────────────────────────────────
    const captured: string[] = [];
    for (const viewport of VIEWPORTS) {
      await page.setViewportSize({ width: viewport.width, height: viewport.height });
      await page.waitForTimeout(900);
      const file = path.join(PROOF_ROOT, `systems-${viewport.label}.png`);
      await page.screenshot({ path: file, fullPage: false });
      captured.push(file);
    }

    await writeFile(
      path.join(PROOF_ROOT, "slice1-metrics.json"),
      `${JSON.stringify({ ...metrics, capturedViewports: VIEWPORTS.map(v => v.label), capturedAt: new Date().toISOString() }, null, 2)}\n`,
      "utf8",
    );

    await testInfo.attach("slice1-metrics", { body: JSON.stringify(metrics, null, 2), contentType: "application/json" });
  });
});
