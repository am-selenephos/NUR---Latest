import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type CDPSession, type Frame, type Page } from "@playwright/test";

type BrowserCounters = {
  longTasks: Array<{ startTime: number; duration: number }>;
  longAnimationFrames: Array<{ startTime: number; duration: number }>;
  eventTimings: Array<{ name: string; startTime: number; duration: number; interactionId: number }>;
  layoutShift: number;
  rafRequested: number;
  rafCompleted: number;
  rafCancelled: number;
  activeRaf: number;
  listenerAdds: number;
  listenerRemoves: number;
  mutationObservers: number;
  resizeObservers: number;
  canvasContexts: number;
};

type FrameCadence = {
  durationMs: number;
  frames: number;
  fps: number;
  p50DeltaMs: number;
  p95DeltaMs: number;
  maxDeltaMs: number;
  droppedFrameIntervals: number;
};

type FrameSnapshot = Partial<BrowserCounters> & Record<string, unknown>;

const label = process.env.NUR_PERF_LABEL ?? "baseline";
const soakMs = Number(process.env.NUR_PERF_SOAK_MS ?? "60000");
const proofRoot = process.env.NUR_PERF_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? `../../proof/v5/performance/${label}` : `proof/v5/performance/${label}`);

async function revealEntry(page: Page): Promise<ReturnType<Page["frameLocator"]>> {
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() =>
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront === "function"),
  ).toBe(true);
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });
  return entry;
}

async function installInstrumentation(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const global = window as typeof window & { __nurPerf?: BrowserCounters };
    if (global.__nurPerf) return;

    const counters: BrowserCounters = {
      longTasks: [],
      longAnimationFrames: [],
      eventTimings: [],
      layoutShift: 0,
      rafRequested: 0,
      rafCompleted: 0,
      rafCancelled: 0,
      activeRaf: 0,
      listenerAdds: 0,
      listenerRemoves: 0,
      mutationObservers: 0,
      resizeObservers: 0,
      canvasContexts: 0,
    };
    global.__nurPerf = counters;

    const observe = (type: string, callback: (entry: PerformanceEntry) => void, options: PerformanceObserverInit = {}) => {
      try {
        const observer = new PerformanceObserver(list => list.getEntries().forEach(callback));
        observer.observe({ type, buffered: true, ...options });
      } catch {
        // Unsupported entry types remain represented by an empty collection.
      }
    };
    observe("longtask", entry => counters.longTasks.push({ startTime: entry.startTime, duration: entry.duration }));
    observe("long-animation-frame", entry => counters.longAnimationFrames.push({ startTime: entry.startTime, duration: entry.duration }));
    observe("event", entry => {
      const timed = entry as PerformanceEventTiming & { interactionId?: number };
      counters.eventTimings.push({
        name: timed.name,
        startTime: timed.startTime,
        duration: timed.duration,
        interactionId: timed.interactionId ?? 0,
      });
    }, { durationThreshold: 16 } as PerformanceObserverInit);
    observe("layout-shift", entry => {
      const shift = entry as PerformanceEntry & { value?: number; hadRecentInput?: boolean };
      if (!shift.hadRecentInput) counters.layoutShift += shift.value ?? 0;
    });

    const nativeRaf = window.requestAnimationFrame.bind(window);
    const nativeCancelRaf = window.cancelAnimationFrame.bind(window);
    const pending = new Set<number>();
    window.requestAnimationFrame = callback => {
      counters.rafRequested += 1;
      counters.activeRaf += 1;
      const id = nativeRaf(timestamp => {
        if (pending.delete(id)) counters.activeRaf -= 1;
        counters.rafCompleted += 1;
        callback(timestamp);
      });
      pending.add(id);
      return id;
    };
    window.cancelAnimationFrame = id => {
      if (pending.delete(id)) counters.activeRaf -= 1;
      counters.rafCancelled += 1;
      nativeCancelRaf(id);
    };

    const nativeAdd = EventTarget.prototype.addEventListener;
    const nativeRemove = EventTarget.prototype.removeEventListener;
    EventTarget.prototype.addEventListener = function (...args) {
      counters.listenerAdds += 1;
      return nativeAdd.apply(this, args as Parameters<typeof nativeAdd>);
    };
    EventTarget.prototype.removeEventListener = function (...args) {
      counters.listenerRemoves += 1;
      return nativeRemove.apply(this, args as Parameters<typeof nativeRemove>);
    };

    const NativeMutationObserver = window.MutationObserver;
    window.MutationObserver = class extends NativeMutationObserver {
      constructor(callback: MutationCallback) {
        counters.mutationObservers += 1;
        super(callback);
      }
    };
    const NativeResizeObserver = window.ResizeObserver;
    if (NativeResizeObserver) {
      window.ResizeObserver = class extends NativeResizeObserver {
        constructor(callback: ResizeObserverCallback) {
          counters.resizeObservers += 1;
          super(callback);
        }
      };
    }

    const nativeGetContext = HTMLCanvasElement.prototype.getContext;
    HTMLCanvasElement.prototype.getContext = function (this: HTMLCanvasElement, ...args: unknown[]) {
      counters.canvasContexts += 1;
      return (nativeGetContext as (...values: unknown[]) => RenderingContext | null).apply(this, args);
    } as typeof HTMLCanvasElement.prototype.getContext;
  });
}

async function cadence(frame: Frame, durationMs = 5000): Promise<FrameCadence> {
  return frame.evaluate(async measurementMs => {
    const marks: number[] = [];
    const started = performance.now();
    await new Promise<void>(resolve => {
      const tick = (timestamp: number) => {
        marks.push(timestamp);
        if (timestamp - started >= measurementMs) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    const deltas = marks.slice(1).map((value, index) => value - marks[index]).sort((a, b) => a - b);
    const percentile = (fraction: number) => deltas[Math.min(deltas.length - 1, Math.floor(deltas.length * fraction))] ?? 0;
    const elapsed = (marks.at(-1) ?? started) - (marks[0] ?? started);
    return {
      durationMs: elapsed,
      frames: marks.length,
      fps: elapsed > 0 ? Number((((marks.length - 1) * 1000) / elapsed).toFixed(2)) : 0,
      p50DeltaMs: Number(percentile(.5).toFixed(2)),
      p95DeltaMs: Number(percentile(.95).toFixed(2)),
      maxDeltaMs: Number((deltas.at(-1) ?? 0).toFixed(2)),
      droppedFrameIntervals: deltas.filter(delta => delta > 25).length,
    };
  }, durationMs);
}

async function counters(frame: Frame): Promise<FrameSnapshot> {
  return frame.evaluate(() => {
    const global = window as typeof window & {
      __nurPerf?: BrowserCounters;
      nurGalaxy?: { getParticleCount?: () => number };
    };
    const memory = (performance as Performance & { memory?: { usedJSHeapSize: number; totalJSHeapSize: number } }).memory;
    const animations = document.getAnimations().filter(animation => animation.playState === "running");
    const animationTargets = new Map<string, number>();
    for (const animation of animations) {
      const rawTarget = (animation.effect as KeyframeEffect | null)?.target as Element | { element?: Element } | null;
      const target = rawTarget instanceof Element ? rawTarget : rawTarget?.element;
      const key = target
        ? `${target.tagName.toLowerCase()}${target.id ? `#${target.id}` : ""}${target.classList.length ? `.${[...target.classList].join(".")}` : ""}`
        : "unknown";
      animationTargets.set(key, (animationTargets.get(key) ?? 0) + 1);
    }
    const classCounts = new Map<string, number>();
    document.querySelectorAll<HTMLElement>("[class]").forEach(element => {
      for (const name of element.classList) classCounts.set(name, (classCounts.get(name) ?? 0) + 1);
    });
    const top = (values: Map<string, number>) => [...values.entries()]
      .sort((left, right) => right[1] - left[1])
      .slice(0, 30)
      .map(([name, count]) => ({ name, count }));
    return {
      ...(global.__nurPerf ?? {}),
      canvasElements: document.querySelectorAll("canvas").length,
      canvasOwners: [...document.querySelectorAll<HTMLCanvasElement>("canvas")]
        .map(canvas => canvas.id || canvas.className || "anonymous-canvas"),
      runningAnimations: animations.length,
      animationTargets: top(animationTargets),
      topClasses: top(classCounts),
      elementCount: document.querySelectorAll("*").length,
      miniStarHosts: document.querySelectorAll(".nur-exact-mini-host").length,
      miniStarModules: document.querySelectorAll(".nur-exact-mini-host .nur-star-module").length,
      starRays: document.querySelectorAll(".nur-exact-mini-host .ray").length,
      adjunctRoots: document.querySelectorAll("[data-nur-v197-adjunct]").length,
      bridgeStyleNodes: document.querySelectorAll('style[id^="nur-v197"], style[id^="nur-track-a"]').length,
      particleCount: global.nurGalaxy?.getParticleCount?.() ?? null,
      usedJSHeapSize: memory?.usedJSHeapSize ?? null,
      totalJSHeapSize: memory?.totalJSHeapSize ?? null,
      visibilityState: document.visibilityState,
    };
  });
}

async function centreMeasurements(frame: Frame): Promise<Record<string, unknown>> {
  return frame.evaluate(() => {
    const viewport = { width: innerWidth, height: innerHeight };
    const measure = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      return {
        selector,
        rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
        deltaFromViewportCenter: {
          x: Number((rect.left + rect.width / 2 - viewport.width / 2).toFixed(2)),
          y: Number((rect.top + rect.height / 2 - viewport.height / 2).toFixed(2)),
        },
      };
    };
    return {
      viewport,
      wordmark: measure("#nur-v197-system-wordmark"),
      masterStar: measure(".universe-master-star, .master-star, .f4-master-star--hero"),
      systemField: measure(".system-field-card, .universe-system-field"),
    };
  });
}

async function collectCdpTrace(cdp: CDPSession, outputPath: string): Promise<void> {
  const completed = new Promise<{ stream: string }>(resolve => {
    cdp.once("Tracing.tracingComplete", event => resolve(event as { stream: string }));
  });
  await cdp.send("Tracing.end");
  const { stream } = await completed;
  const chunks: string[] = [];
  for (;;) {
    const part = await cdp.send("IO.read", { handle: stream }) as { data: string; eof?: boolean; base64Encoded?: boolean };
    chunks.push(part.base64Encoded ? Buffer.from(part.data, "base64").toString("utf8") : part.data);
    if (part.eof) break;
  }
  await cdp.send("IO.close", { handle: stream });
  await writeFile(outputPath, chunks.join(""), "utf8");
}

test("measures canonical V197 runtime without changing presentation", async ({ page, context }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Baseline trace is captured once on desktop Chromium.");
  test.setTimeout(Math.max(180_000, soakMs + 120_000));
  await mkdir(proofRoot, { recursive: true });
  await installInstrumentation(page);

  const cdp = await context.newCDPSession(page);
  await cdp.send("Performance.enable");
  await cdp.send("Tracing.start", {
    categories: "devtools.timeline,blink.user_timing,v8,disabled-by-default-v8.cpu_profiler",
    transferMode: "ReturnAsStream",
  });
  await page.goto("/", { waitUntil: "load" });
  const entryLocator = await revealEntry(page);
  const entryHandle = page.frames().find(frame => frame.name() === "nur-entry-stage")
    ?? page.frames().find(frame => frame.url() === "about:srcdoc");
  if (!entryHandle) throw new Error("V197 Entry frame did not load.");

  const entryCadence = await cadence(entryHandle);
  const entryCounters = await counters(entryHandle);
  const navigationMetrics = await cdp.send("Performance.getMetrics");

  await entryLocator.locator("#f4-signin").click();
  await entryLocator.locator("#f4-signin-email").fill("owner@nur.app");
  await entryLocator.locator("#f4-signin-password").fill("owner-demo-pass-123");
  const loginStarted = performance.now();
  await entryLocator.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 30_000 });
  await expect(page).toHaveURL(/\/today$/);
  const loginToUniverseMs = performance.now() - loginStarted;

  const universeHandle = page.frames().find(frame => frame.name() === "nur-universe-stage");
  if (!universeHandle) throw new Error("V197 Universe frame did not load.");
  await expect(page.frameLocator("#nur-universe-stage").locator("#page-today")).toBeVisible({ timeout: 20_000 });

  const universeCadence = await cadence(universeHandle);
  const universeStart = await counters(universeHandle);
  const centres = await centreMeasurements(universeHandle);
  const heapAtStart = await cdp.send("Performance.getMetrics");

  const systemsStarted = performance.now();
  await page.frameLocator("#nur-universe-stage").locator('[data-route="systems"], [data-page="systems"]').first().click();
  await expect(page).toHaveURL(/\/systems$/);
  await expect(page.frameLocator("#nur-universe-stage").locator("#page-systems")).toBeVisible();
  const systemsNavigationMs = performance.now() - systemsStarted;

  const mapStarted = performance.now();
  await page.frameLocator("#nur-universe-stage").locator('[data-world-tab="map"]').click();
  await expect(page).toHaveURL(/\/universe\/map$/);
  const mapNavigationMs = performance.now() - mapStarted;
  const universeAfterMap = await counters(universeHandle);
  const heapAfterMap = await cdp.send("Performance.getMetrics");

  const soakStarted = performance.now();
  await universeHandle.evaluate(async durationMs => {
    await new Promise<void>(resolve => {
      const started = performance.now();
      const tick = (timestamp: number) => {
        if (timestamp - started >= durationMs) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }, soakMs);
  const actualSoakMs = performance.now() - soakStarted;

  const universeEnd = await counters(universeHandle);
  const heapAtEnd = await cdp.send("Performance.getMetrics");
  const finalCdpMetrics = await cdp.send("Performance.getMetrics");
  const metricObject = (rows: Array<{ name: string; value: number }>) =>
    Object.fromEntries(rows.map(row => [row.name, row.value]));

  const report = {
    label,
    generatedAt: new Date().toISOString(),
    browser: testInfo.project.name,
    canonicalV197Sha256: "c4699091db9f1ebc3a6e2076d483a3d41303d3e261ace0111c9411322f7ea3a5",
    requestedSoakMs: soakMs,
    actualSoakMs,
    routeTimingsMs: { loginToUniverseMs, systemsNavigationMs, mapNavigationMs },
    entry: { cadence: entryCadence, counters: entryCounters },
    universe: { cadence: universeCadence, start: universeStart, afterMap: universeAfterMap, end: universeEnd, centres },
    cdp: {
      navigation: metricObject(navigationMetrics.metrics),
      heapAtStart: metricObject(heapAtStart.metrics),
      heapAfterMap: metricObject(heapAfterMap.metrics),
      heapAtEnd: metricObject(heapAtEnd.metrics),
      final: metricObject(finalCdpMetrics.metrics),
    },
  };

  await writeFile(join(proofRoot, "performance-report.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await page.screenshot({ path: join(proofRoot, "systems-map.png"), fullPage: false, animations: "allow" });
  await collectCdpTrace(cdp, join(proofRoot, "chromium-performance-trace.json"));

  expect(universeStart.canvasElements).toBe(2);
  expect((universeStart.canvasOwners as string[]).sort()).toEqual(["nur-brain-canvas", "space3d"]);
  expect(universeEnd.canvasElements).toBe(2);
  expect((universeEnd.canvasOwners as string[]).sort()).toEqual(["nur-brain-canvas", "space3d"]);
  expect(Number(universeEnd.activeRaf ?? 0)).toBeLessThanOrEqual(4);
});
