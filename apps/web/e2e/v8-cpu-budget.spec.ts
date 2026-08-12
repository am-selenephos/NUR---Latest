import { expect, test, type Page } from "@playwright/test";

type CpuSample = {
  wallSeconds: number;
  taskSeconds: number;
  scriptSeconds: number;
  cpuPercent: number;
};

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
  const pageErrors: string[] = [];
  page.on("pageerror", error => pageErrors.push(error.stack ?? error.message));
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable");

  const cpuOver = async (ms: number): Promise<CpuSample> => {
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
  const cpuSeries = async (label: string, count = 5, sampleMs = 4_000) => {
    const samples: CpuSample[] = [];
    for (let index = 0; index < count; index += 1) {
      samples.push(await cpuOver(sampleMs));
    }
    const sorted = samples.map(sample => sample.cpuPercent).sort((a, b) => a - b);
    const totalWall = samples.reduce((sum, sample) => sum + sample.wallSeconds, 0);
    const totalTask = samples.reduce((sum, sample) => sum + sample.taskSeconds, 0);
    const summary = {
      samples,
      aggregateCpuPercent: Number(((totalTask / totalWall) * 100).toFixed(1)),
      medianCpuPercent: sorted[Math.floor(sorted.length / 2)] ?? 0,
      p95CpuPercent: sorted[Math.ceil(sorted.length * .95) - 1] ?? 0,
      maximumCpuPercent: sorted.at(-1) ?? 0,
    };
    console.log(`${label}_CPU ${JSON.stringify(summary)}`);
    return summary;
  };

  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/");
  await page.waitForTimeout(1500);
  await page.frameLocator("#nur-entry-stage").locator("body").evaluate(() => (window as any).nurShowFront?.());
  await page.waitForTimeout(2500);
  const entry = await cpuSeries("ENTRY");

  await signIn(page);
  const hiddenEntryMotion = await page.frameLocator("#nur-entry-stage").locator("body").evaluate(async () => {
    const checksum = (canvas: HTMLCanvasElement | null) => {
      if (!canvas || canvas.width < 2 || canvas.height < 2) return 0;
      const context = canvas.getContext("2d");
      if (!context) return 0;
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const stride = Math.max(4, Math.floor(data.length / 20_000 / 4) * 4);
      let value = 0;
      for (let index = 0; index < data.length; index += stride) {
        value = (value + (data[index] ?? 0) * 3 + (data[index + 1] ?? 0) * 5
          + (data[index + 2] ?? 0) * 7 + (data[index + 3] ?? 0) * 11) % 2_147_483_647;
      }
      return value;
    };
    const canvases = ["#space3d", "#nur-brain-canvas"]
      .map(selector => document.querySelector<HTMLCanvasElement>(selector));
    const before = canvases.map(checksum);
    await new Promise(resolve => setTimeout(resolve, 700));
    return { before, after: canvases.map(checksum) };
  });
  expect(hiddenEntryMotion.after).toEqual(hiddenEntryMotion.before);

  await page.goto("/systems");
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25_000 });
  const universeStage = page.frameLocator("#nur-universe-stage");
  await expect(universeStage.locator("#page-systems")).toBeVisible();
  let previousTransient: number | null = null;
  await expect.poll(
    async () => {
      const diagnostics = await universeStage.locator("body").evaluate(() => (
        (window as unknown as {
          nurGalaxy?: {
            getParticleDiagnostics?: () => {
              transient: number;
              [key: string]: unknown;
            };
          };
        }).nurGalaxy?.getParticleDiagnostics?.() ?? { transient: Number.POSITIVE_INFINITY }
      ));
      if (diagnostics.transient !== previousTransient) {
        console.log(`GALAXY_SETTLE ${JSON.stringify(diagnostics)}`);
        previousTransient = diagnostics.transient;
      }
      return diagnostics.transient;
    },
    {
      message: "Transient route/login burst particles must retire before steady-state CPU measurement",
      timeout: 15_000,
      intervals: [250],
    },
  ).toBe(0);
  const visibleUniverseMoves = await page.frameLocator("#nur-universe-stage").locator("body").evaluate(async () => {
    const canvas = document.querySelector<HTMLCanvasElement>("#space3d");
    if (!canvas) return false;
    const context = canvas.getContext("2d");
    if (!context) return false;
    const checksum = () => {
      const data = context.getImageData(0, 0, canvas.width, canvas.height).data;
      const stride = Math.max(4, Math.floor(data.length / 20_000 / 4) * 4);
      let value = 0;
      for (let index = 0; index < data.length; index += stride) {
        value = (value + (data[index] ?? 0) * 3 + (data[index + 1] ?? 0) * 5
          + (data[index + 2] ?? 0) * 7 + (data[index + 3] ?? 0) * 11) % 2_147_483_647;
      }
      return value;
    };
    const before = checksum();
    await new Promise(resolve => setTimeout(resolve, 700));
    return checksum() !== before;
  });
  expect(visibleUniverseMoves).toBe(true);
  const systems = await cpuSeries("SYSTEMS");

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
  expect(entry.aggregateCpuPercent).toBeLessThan(78);
  expect(entry.p95CpuPercent).toBeLessThan(78);
  expect(systems.aggregateCpuPercent).toBeLessThan(34);
  expect(systems.p95CpuPercent).toBeLessThan(34);
  expect(pageErrors).toEqual([]);
});
