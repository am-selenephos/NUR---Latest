import { mkdir, writeFile } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Frame, type Page } from "@playwright/test";

type Cadence = {
  durationMs: number;
  frames: number;
  fps: number;
  p50DeltaMs: number;
  p95DeltaMs: number;
  maxDeltaMs: number;
};

type RuntimeSnapshot = {
  elementCount: number;
  canvasCount: number;
  canvasOwners: string[];
  runningAnimations: number;
  runningAnimationDetails: Array<{ name: string; target: string }>;
  particleCount: number | null;
  miniStarHosts: number;
  compactedMiniStars: number;
  rayCount: number;
  styleCount: number;
  usedJSHeapSize: number | null;
  listenerAdds: number;
  listenerRemoves: number;
  mutationObservers: number;
  resizeObservers: number;
  longTasks: Array<{ startTime: number; duration: number }>;
};

type RouteState = {
  label: string;
  path: string;
  activeWorld: string | null;
  scrollY: number;
  mapTop: number | null;
};

const proofRoot = join(process.cwd(), "../../proof/v5/performance/g04-acceptance");
const ownerEmail = "owner@nur.app";
const ownerPassword = "owner-demo-pass-123";

async function installRuntimeCounters(page: Page): Promise<void> {
  await page.addInitScript(() => {
    type RuntimeCounters = {
      listenerAdds: number;
      listenerRemoves: number;
      mutationObservers: number;
      resizeObservers: number;
      longTasks: Array<{ startTime: number; duration: number }>;
    };
    type RouteDiagnostic = {
      at: number;
      frame: string;
      kind: string;
      path: string;
      world?: string;
      trusted?: boolean;
      stack?: string;
    };
    type RouteDiagnosticWindow = typeof window & {
      __nurG04?: RuntimeCounters;
      __nurG04Routes?: RouteDiagnostic[];
    };
    const global = window as RouteDiagnosticWindow;
    if (global.__nurG04) return;
    const counters: RuntimeCounters = {
      listenerAdds: 0,
      listenerRemoves: 0,
      mutationObservers: 0,
      resizeObservers: 0,
      longTasks: [],
    };
    global.__nurG04 = counters;

    const recordRoute = (entry: Omit<RouteDiagnostic, "at" | "frame" | "path">) => {
      try {
        const root = window.top as RouteDiagnosticWindow;
        const ledger = root.__nurG04Routes ??= [];
        ledger.push({
          at: Number(performance.now().toFixed(2)),
          frame: window.name || "top",
          path: window.top?.location.pathname ?? location.pathname,
          ...entry,
        });
      } catch {
        // Canonical stages are same-origin in this host. If that ever changes,
        // the missing ledger itself is useful boundary evidence.
      }
    };

    if (window === window.top) {
      global.__nurG04Routes = [];
      const nativePushState = history.pushState.bind(history);
      history.pushState = (data: unknown, unused: string, url?: string | URL | null) => {
        nativePushState(data, unused, url);
        recordRoute({ kind: "history.pushState", stack: new Error().stack });
      };
      const nativeReplaceState = history.replaceState.bind(history);
      history.replaceState = (data: unknown, unused: string, url?: string | URL | null) => {
        nativeReplaceState(data, unused, url);
        recordRoute({ kind: "history.replaceState", stack: new Error().stack });
      };
      window.addEventListener("popstate", () => recordRoute({ kind: "popstate", stack: new Error().stack }));
    }

    document.addEventListener("click", event => {
      const target = event.target as Element | null;
      const control = target?.closest<HTMLElement>("[data-world-focus], [data-world-tab]");
      if (!control) return;
      recordRoute({
        kind: "dom.click",
        world: control.dataset.worldFocus ?? control.dataset.worldTab,
        trusted: event.isTrusted,
      });
    }, true);
    window.addEventListener("nur:world-focus", event => {
      recordRoute({
        kind: "nur:world-focus",
        world: (event as CustomEvent<{ focus?: string }>).detail?.focus,
      });
    });

    const nativeElementClick = HTMLElement.prototype.click;
    HTMLElement.prototype.click = function () {
      const world = this.dataset.worldFocus ?? this.dataset.worldTab;
      if (world) recordRoute({ kind: "programmatic.click", world, stack: new Error().stack });
      nativeElementClick.call(this);
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

    try {
      const observer = new PerformanceObserver(list => {
        for (const entry of list.getEntries()) {
          counters.longTasks.push({ startTime: entry.startTime, duration: entry.duration });
        }
      });
      observer.observe({ type: "longtask", buffered: true });
    } catch {
      // Long-task entries are Chromium-only; the browser matrix still records
      // every other runtime and geometry invariant.
    }
  });
}

async function routeState(frame: Frame, label: string): Promise<RouteState> {
  return frame.evaluate(stateLabel => {
    const active = document.querySelector<HTMLElement>("[data-world-tab].active, [data-world-focus].active");
    const panel = document.querySelector<HTMLElement>(".universe-map-panel");
    return {
      label: stateLabel,
      path: parent.location.pathname,
      activeWorld: active?.dataset.worldTab ?? active?.dataset.worldFocus ?? null,
      scrollY,
      mapTop: panel ? Number(panel.getBoundingClientRect().top.toFixed(2)) : null,
    };
  }, label);
}

async function showEntry(page: Page): Promise<void> {
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() =>
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront === "function"),
  ).toBe(true);
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });
  await expect(entry.locator("#nur-front-v61")).toBeVisible();
}

async function mountEntry(page: Page): Promise<Frame> {
  await page.goto("/", { waitUntil: "load" });
  await showEntry(page);
  const entryFrame = page.frames().find(candidate => candidate.name() === "nur-entry-stage")
    ?? page.frames().find(candidate => candidate.url() === "about:srcdoc");
  if (!entryFrame) throw new Error("V197 Entry frame was not mounted.");
  return entryFrame;
}

async function signIn(page: Page, mountedEntry?: Frame): Promise<Frame> {
  const entry = mountedEntry ?? await mountEntry(page);
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill(ownerEmail);
  await entry.locator("#f4-signin-password").fill(ownerPassword);
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(page).toHaveURL(/\/today$/, { timeout: 30_000 });
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/);
  const frame = page.frames().find(candidate => candidate.name() === "nur-universe-stage");
  if (!frame) throw new Error("V197 Universe frame was not mounted.");
  await expect(page.frameLocator("#nur-universe-stage").locator("#page-today")).toBeVisible({ timeout: 20_000 });
  return frame;
}

async function warmFramePipeline(frame: Frame, frameCount = 120, maximumWarmupMs = 4_000): Promise<void> {
  await frame.evaluate(async ({ count, maximumMs }) => {
    await new Promise<void>(resolve => {
      let frames = 0;
      let settled = false;
      const started = performance.now();
      const finish = () => {
        if (settled) return;
        settled = true;
        window.clearTimeout(fallback);
        resolve();
      };
      const fallback = window.setTimeout(finish, maximumMs);
      const tick = (timestamp: number) => {
        if (settled) return;
        frames += 1;
        if (frames >= count || timestamp - started >= maximumMs) finish();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
  }, { count: frameCount, maximumMs: maximumWarmupMs });
}

async function measureCadence(frame: Frame, durationMs = 5000): Promise<Cadence> {
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
      durationMs: Number(elapsed.toFixed(2)),
      frames: marks.length,
      fps: elapsed > 0 ? Number((((marks.length - 1) * 1000) / elapsed).toFixed(2)) : 0,
      p50DeltaMs: Number(percentile(.5).toFixed(2)),
      p95DeltaMs: Number(percentile(.95).toFixed(2)),
      maxDeltaMs: Number((deltas.at(-1) ?? 0).toFixed(2)),
    };
  }, durationMs);
}

async function routeWithBrowserTiming(
  frame: Frame,
  selector: string,
  expectedPath: string,
): Promise<number> {
  await frame.evaluate(({ controlSelector, path }) => {
    const global = window as typeof window & { __nurRouteTiming?: { started: number; settled: number } };
    const control = [...document.querySelectorAll<HTMLElement>(controlSelector)]
      .find(element => element.offsetParent !== null);
    if (!control) throw new Error(`Visible route control not found: ${controlSelector}`);
    global.__nurRouteTiming = { started: 0, settled: 0 };
    control.addEventListener("pointerup", () => {
      global.__nurRouteTiming = { started: performance.now(), settled: 0 };
      const observe = () => {
        if (parent.location.pathname === path) {
          global.__nurRouteTiming!.settled = performance.now();
          return;
        }
        requestAnimationFrame(observe);
      };
      requestAnimationFrame(observe);
    }, { once: true });
  }, { controlSelector: selector, path: expectedPath });

  const control = frame.locator(selector).filter({ visible: true }).first();
  await control.click();
  await expect.poll(() => frame.evaluate(() => {
    const timing = (window as typeof window & { __nurRouteTiming?: { settled: number } }).__nurRouteTiming;
    return timing?.settled ?? 0;
  })).toBeGreaterThan(0);
  return frame.evaluate(() => {
    const timing = (window as typeof window & { __nurRouteTiming: { started: number; settled: number } }).__nurRouteTiming;
    return Number((timing.settled - timing.started).toFixed(2));
  });
}

async function snapshot(frame: Frame): Promise<RuntimeSnapshot> {
  return frame.evaluate(() => {
    type RuntimeCounters = {
      listenerAdds: number;
      listenerRemoves: number;
      mutationObservers: number;
      resizeObservers: number;
      longTasks: Array<{ startTime: number; duration: number }>;
    };
    const global = window as typeof window & {
      __nurG04?: RuntimeCounters;
      nurGalaxy?: { getParticleCount?: () => number };
    };
    const memory = performance as Performance & { memory?: { usedJSHeapSize: number } };
    const runningAnimationDetails = document.getAnimations()
      .filter(animation => animation.playState === "running")
      .map(animation => {
        const target = animation.effect instanceof KeyframeEffect
          ? animation.effect.target
          : null;
        const element = target instanceof Element ? target : null;
        const named = animation as Animation & { animationName?: string };
        return {
          name: named.animationName ?? getComputedStyle(element ?? document.documentElement).animationName,
          target: element
            ? `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}${[...element.classList].map(name => `.${name}`).join("")}`
            : "unknown",
        };
      });
    return {
      elementCount: document.querySelectorAll("*").length,
      canvasCount: document.querySelectorAll("canvas").length,
      canvasOwners: [...document.querySelectorAll<HTMLCanvasElement>("canvas")]
        .map(canvas => canvas.id || canvas.className || "anonymous-canvas"),
      runningAnimations: runningAnimationDetails.length,
      runningAnimationDetails,
      particleCount: global.nurGalaxy?.getParticleCount?.() ?? null,
      miniStarHosts: document.querySelectorAll(".nur-exact-mini-host").length,
      compactedMiniStars: document.querySelectorAll('.nur-exact-mini-host[data-nur-mini-compacted="true"]').length,
      rayCount: document.querySelectorAll(".nur-exact-mini-host .ray").length,
      styleCount: document.querySelectorAll("style").length,
      usedJSHeapSize: memory.memory?.usedJSHeapSize ?? null,
      listenerAdds: global.__nurG04?.listenerAdds ?? 0,
      listenerRemoves: global.__nurG04?.listenerRemoves ?? 0,
      mutationObservers: global.__nurG04?.mutationObservers ?? 0,
      resizeObservers: global.__nurG04?.resizeObservers ?? 0,
      longTasks: global.__nurG04?.longTasks ?? [],
    };
  });
}

async function geometry(frame: Frame): Promise<Record<string, unknown>> {
  return frame.evaluate(() => {
    const rect = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element) return null;
      const value = element.getBoundingClientRect();
      return {
        left: Number(value.left.toFixed(2)),
        top: Number(value.top.toFixed(2)),
        right: Number(value.right.toFixed(2)),
        bottom: Number(value.bottom.toFixed(2)),
        width: Number(value.width.toFixed(2)),
        height: Number(value.height.toFixed(2)),
        centerX: Number((value.left + value.width / 2).toFixed(2)),
        centerY: Number((value.top + value.height / 2).toFixed(2)),
      };
    };
    const panel = rect(".universe-map-panel");
    const wordmark = rect(".nur-v197-stable-wordmark");
    const subtitle = rect(".nur-master-subtitle");
    const star = rect(".universe-master-star");
    const fieldReadout = rect(".universe-field-readout");
    const addSystem = rect(".universe-add-system");
    const panelCenter = panel?.centerX ?? 0;
    const transformX = (selector: string) => {
      const element = document.querySelector<HTMLElement>(selector);
      if (!element) return 0;
      const style = getComputedStyle(element);
      return style.transform === "none" ? 0 : new DOMMatrix(style.transform).m41;
    };
    const wordmarkTransformX = transformX(".nur-v197-stable-wordmark");
    const subtitleTransformX = transformX(".nur-master-subtitle");
    const nodeRects = [...document.querySelectorAll<HTMLElement>(".universe-system-node")]
      .filter(node => node.offsetParent !== null)
      .map(node => ({
        label: node.querySelector("b")?.textContent?.trim() || node.dataset.system || node.className,
        className: node.className,
        rect: (() => {
          const value = node.getBoundingClientRect();
          return {
            left: Number(value.left.toFixed(2)),
            top: Number(value.top.toFixed(2)),
            right: Number(value.right.toFixed(2)),
            bottom: Number(value.bottom.toFixed(2)),
            width: Number(value.width.toFixed(2)),
            height: Number(value.height.toFixed(2)),
            centerX: Number((value.left + value.width / 2).toFixed(2)),
            centerY: Number((value.top + value.height / 2).toFixed(2)),
          };
        })(),
      }));
    const intersects = (
      left: { left: number; top: number; right: number; bottom: number } | null,
      right: { left: number; top: number; right: number; bottom: number } | null,
      padding = 4,
    ) => Boolean(left && right
      && left.right + padding > right.left
      && right.right + padding > left.left
      && left.bottom + padding > right.top
      && right.bottom + padding > left.top);
    const titleNodeCollisions = nodeRects.flatMap(node => [
      ...(intersects(wordmark, node.rect) ? [`wordmark / ${node.label}`] : []),
      ...(intersects(subtitle, node.rect) ? [`subtitle / ${node.label}`] : []),
    ]);
    const titleControlCollisions = [
      ...(intersects(wordmark, fieldReadout) ? ["wordmark / field readout"] : []),
      ...(intersects(wordmark, addSystem) ? ["wordmark / add system"] : []),
      ...(intersects(subtitle, fieldReadout) ? ["subtitle / field readout"] : []),
      ...(intersects(subtitle, addSystem) ? ["subtitle / add system"] : []),
    ];
    const nodeCollisions: string[] = [];
    for (let left = 0; left < nodeRects.length; left += 1) {
      for (let right = left + 1; right < nodeRects.length; right += 1) {
        if (intersects(nodeRects[left].rect, nodeRects[right].rect)) {
          nodeCollisions.push(`${nodeRects[left].label} / ${nodeRects[right].label}`);
        }
      }
    }
    const style = getComputedStyle(document.querySelector<HTMLElement>(".nur-v197-stable-wordmark")!);
    return {
      viewport: { width: innerWidth, height: innerHeight },
      panel,
      wordmark,
      subtitle,
      star,
      fieldReadout,
      addSystem,
      nodes: nodeRects,
      collisions: { titleNodeCollisions, titleControlCollisions, nodeCollisions },
      deltas: {
        wordmarkBaseToPanelX: Number(Math.abs((wordmark?.centerX ?? 0) - wordmarkTransformX - panelCenter).toFixed(2)),
        subtitleBaseToPanelX: Number(Math.abs((subtitle?.centerX ?? 0) - subtitleTransformX - panelCenter).toFixed(2)),
        starToPanelX: Number(Math.abs((star?.centerX ?? 0) - panelCenter).toFixed(2)),
        wordmarkToSubtitleBaseX: Number(Math.abs(
          (wordmark?.centerX ?? 0) - wordmarkTransformX
          - ((subtitle?.centerX ?? 0) - subtitleTransformX),
        ).toFixed(2)),
      },
      wordmarkStyle: {
        fontFamily: style.fontFamily,
        animationName: style.animationName,
        backgroundClip: style.backgroundClip,
        webkitTextFillColor: style.getPropertyValue("-webkit-text-fill-color"),
      },
      horizontalOverflow: Math.max(0, document.documentElement.scrollWidth - document.documentElement.clientWidth),
    };
  });
}

test("G04 warm V197 runtime preserves identity, centring, and natural interaction", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  await installRuntimeCounters(page);
  const entryFrame = await mountEntry(page);
  await warmFramePipeline(entryFrame);
  const entryCadence = await measureCadence(entryFrame);
  const frame = await signIn(page, entryFrame);
  const projectDir = join(proofRoot, testInfo.project.name);
  await mkdir(projectDir, { recursive: true });

  await warmFramePipeline(frame);
  const todayCadence = await measureCadence(frame);
  const systemsSelector = testInfo.project.name.includes("mobile")
    ? ".mobile-tabs [data-page='systems']"
    : ".clean-nav-button[data-page='systems']";
  const systemsInteractionMs = await routeWithBrowserTiming(frame, systemsSelector, "/systems");
  await expect(page).toHaveURL(/\/systems$/);
  await expect(frame.locator("#page-systems")).toBeVisible();
  const routeStates: RouteState[] = [await routeState(frame, "before-map")];
  const mapInteractionMs = await routeWithBrowserTiming(frame, "[data-world-tab='map']", "/universe/map");
  await expect(page).toHaveURL(/\/universe\/map$/);
  routeStates.push(await routeState(frame, "after-map-route"));
  await warmFramePipeline(frame);
  routeStates.push(await routeState(frame, "after-map-warmup"));
  const mapCadence = await measureCadence(frame);
  routeStates.push(await routeState(frame, "after-map-cadence"));
  const runtime = await snapshot(frame);
  const measuredGeometry = await geometry(frame);
  const hostProfile = await page.locator("html").getAttribute("data-nur-runtime-profile");
  const routeDiagnostics = await page.evaluate(() => (
    window as typeof window & { __nurG04Routes?: unknown[] }
  ).__nurG04Routes ?? []);

  const report = {
    project: testInfo.project.name,
    generatedAt: new Date().toISOString(),
    canonicalV197Sha256: "d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6",
    hostProfile,
    entryCadence,
    todayCadence,
    mapCadence,
    interactionsMs: { systems: systemsInteractionMs, map: mapInteractionMs },
    routeStates,
    routeDiagnostics,
    runtime,
    geometry: measuredGeometry,
  };
  await writeFile(join(projectDir, "acceptance.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");
  await page.screenshot({ path: join(projectDir, "systems-map.png"), fullPage: false, animations: "allow" });

  expect(hostProfile).toBe("balanced");
  expect(routeStates.slice(1).every(state => state.path === "/universe/map")).toBe(true);
  expect(routeStates.slice(1).every(state => state.activeWorld === "map")).toBe(true);
  expect(runtime.canvasCount).toBe(2);
  expect(runtime.canvasOwners.sort()).toEqual(["nur-brain-canvas", "space3d"]);
  expect(runtime.runningAnimations).toBeLessThanOrEqual(testInfo.project.name.includes("mobile") ? 16 : 24);
  expect(runtime.particleCount ?? 0).toBeGreaterThanOrEqual(1_160);
  expect(runtime.particleCount ?? 0).toBeLessThanOrEqual(1_200);
  expect(runtime.compactedMiniStars).toBe(runtime.miniStarHosts);
  expect(runtime.rayCount).toBe(0);
  // Headed Chromium is the reference timing environment. Headless Firefox and
  // WebKit can throttle compositor/rAF cadence heavily, so their matrix role is
  // engine parity, geometry, routing, and reduced-work correctness.
  if (testInfo.project.name.startsWith("chromium")) {
    expect(systemsInteractionMs).toBeLessThanOrEqual(200);
    expect(mapInteractionMs).toBeLessThanOrEqual(200);
  }

  const deltas = (measuredGeometry.deltas ?? {}) as Record<string, number>;
  expect(deltas.wordmarkBaseToPanelX).toBeLessThanOrEqual(.5);
  expect(deltas.subtitleBaseToPanelX).toBeLessThanOrEqual(.5);
  expect(deltas.starToPanelX).toBeLessThanOrEqual(2);
  expect(deltas.wordmarkToSubtitleBaseX).toBeLessThanOrEqual(.5);
  expect(measuredGeometry.horizontalOverflow).toBe(0);

  const wordmarkStyle = measuredGeometry.wordmarkStyle as Record<string, string>;
  expect(wordmarkStyle.fontFamily).toContain("Bodoni Moda");
  expect(wordmarkStyle.animationName).toContain("univPrism");
  expect(wordmarkStyle.backgroundClip).toBe("text");
  expect(wordmarkStyle.webkitTextFillColor).toBe("rgba(0, 0, 0, 0)");
  const collisions = measuredGeometry.collisions as {
    titleNodeCollisions: string[];
    titleControlCollisions: string[];
    nodeCollisions: string[];
  };
  expect(collisions.titleNodeCollisions).toEqual([]);
  expect(collisions.titleControlCollisions).toEqual([]);
  expect(collisions.nodeCollisions).toEqual([]);

  if (process.env.NUR_G04_ENFORCE_FPS === "1" && testInfo.project.name.startsWith("chromium")) {
    const minimumFps = testInfo.project.name.includes("mobile") ? 45 : 55;
    expect(entryCadence?.fps ?? 0, `Entry must sustain at least ${minimumFps} FPS after warm-up`).toBeGreaterThanOrEqual(minimumFps);
    expect(todayCadence.fps, `Today must sustain at least ${minimumFps} FPS after warm-up`).toBeGreaterThanOrEqual(minimumFps);
    expect(mapCadence.fps, `Map must sustain at least ${minimumFps} FPS after warm-up`).toBeGreaterThanOrEqual(minimumFps);
  }
});

test("G04 reduced motion materially removes galaxy and decorative animation work", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  await page.emulateMedia({ reducedMotion: "reduce" });
  const frame = await signIn(page);
  const systemsSelector = testInfo.project.name.includes("mobile")
    ? ".mobile-tabs [data-page='systems']"
    : ".clean-nav-button[data-page='systems']";
  await frame.locator(systemsSelector).click();
  await expect(frame.locator("#page-systems")).toBeVisible();
  await frame.locator("[data-world-tab='map']").click();
  await expect(page).toHaveURL(/\/universe\/map$/);

  const reduced = await frame.evaluate(() => {
    const canvas = document.querySelector<HTMLElement>("#space3d");
    const animations = document.getAnimations()
      .filter(animation => animation.playState === "running")
      .map(animation => {
        const timing = animation.effect?.getComputedTiming();
        const named = animation as Animation & { animationName?: string };
        const effectTarget = animation.effect instanceof KeyframeEffect
          ? animation.effect.target
          : null;
        const effectStyle = effectTarget instanceof Element ? getComputedStyle(effectTarget) : null;
        const effectiveDurationMs = effectStyle
          ? Math.max(...effectStyle.animationDuration.split(",").map(value => {
            const duration = Number.parseFloat(value);
            return value.trim().endsWith("ms") ? duration : duration * 1_000;
          }))
          : 0;
        const duration = typeof timing?.duration === "number" ? timing.duration : 0;
        const activeDuration = typeof timing?.activeDuration === "number" ? timing.activeDuration : 0;
        return {
          name: named.animationName ?? "unnamed",
          target: effectTarget instanceof Element
            ? `${effectTarget.tagName.toLowerCase()}${effectTarget.id ? `#${effectTarget.id}` : ""}${[...effectTarget.classList].map(name => `.${name}`).join("")}`
            : "unknown",
          inNurFront: effectTarget instanceof Element && Boolean(effectTarget.closest("#nur-front-v61")),
          computedAnimation: effectStyle?.animation ?? "",
          effectiveDurationMs,
          duration,
          activeDuration,
          endTime: timing?.endTime ?? 0,
        };
      });
    return {
      canvasDisplay: canvas ? getComputedStyle(canvas).display : "missing",
      runningAnimations: animations.length,
      // WebKit can retain the source keyframe duration in getComputedTiming()
      // after a reduced-motion !important override. Computed CSS is the value
      // that actually drives compositor work across engines.
      meaningfulAnimations: animations.filter(animation => animation.effectiveDurationMs > 16).length,
      animations,
    };
  });
  const projectDir = join(proofRoot, testInfo.project.name);
  await mkdir(projectDir, { recursive: true });
  await writeFile(join(projectDir, "reduced-motion.json"), `${JSON.stringify(reduced, null, 2)}\n`, "utf8");
  await page.screenshot({ path: join(projectDir, "reduced-motion-map.png"), fullPage: false, animations: "allow" });

  expect(reduced.canvasDisplay).toBe("none");
  expect(reduced.meaningfulAnimations).toBeLessThanOrEqual(2);
});

test("G04 ten-minute runtime soak has bounded heap, listeners, observers, canvas, and DOM", async ({ page }, testInfo) => {
  test.skip(process.env.NUR_G04_SOAK !== "1", "Run explicitly with NUR_G04_SOAK=1 for the release performance gate.");
  test.skip(testInfo.project.name !== "chromium-desktop-g04", "The ten-minute memory soak runs on the reference browser only.");
  const soakMs = 600_000;
  test.setTimeout(soakMs + 180_000);
  await installRuntimeCounters(page);
  const frame = await signIn(page);
  await frame.locator(".clean-nav-button[data-page='systems']").click();
  await expect(frame.locator("#page-systems")).toBeVisible();
  await frame.locator("[data-world-tab='map']").click();
  await expect(page).toHaveURL(/\/universe\/map$/);
  await warmFramePipeline(frame);

  const requestGc = (page as Page & { requestGC?: () => Promise<void> }).requestGC;
  if (requestGc) await requestGc.call(page);
  const start = await snapshot(frame);
  const samples = await frame.evaluate(async durationMs => {
    const points: Array<{ elapsedMs: number; elements: number; canvases: number; styles: number; animations: number; heap: number | null }> = [];
    const started = performance.now();
    let nextSample = 0;
    await new Promise<void>(resolve => {
      const tick = (timestamp: number) => {
        const elapsed = timestamp - started;
        if (elapsed >= nextSample) {
          const memory = performance as Performance & { memory?: { usedJSHeapSize: number } };
          points.push({
            elapsedMs: Number(elapsed.toFixed(2)),
            elements: document.querySelectorAll("*").length,
            canvases: document.querySelectorAll("canvas").length,
            styles: document.querySelectorAll("style").length,
            animations: document.getAnimations().filter(animation => animation.playState === "running").length,
            heap: memory.memory?.usedJSHeapSize ?? null,
          });
          nextSample += 30_000;
        }
        if (elapsed >= durationMs) resolve();
        else requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
    });
    return points;
  }, soakMs);
  if (requestGc) await requestGc.call(page);
  const end = await snapshot(frame);

  const report = { generatedAt: new Date().toISOString(), soakMs, start, end, samples };
  const projectDir = join(proofRoot, testInfo.project.name);
  await mkdir(projectDir, { recursive: true });
  await writeFile(join(projectDir, "ten-minute-soak.json"), `${JSON.stringify(report, null, 2)}\n`, "utf8");

  expect(end.canvasCount).toBe(start.canvasCount);
  expect(end.styleCount).toBe(start.styleCount);
  expect(Math.abs(end.elementCount - start.elementCount)).toBeLessThanOrEqual(8);
  expect(end.mutationObservers).toBe(start.mutationObservers);
  expect(end.resizeObservers).toBe(start.resizeObservers);
  const listenerGrowth = (end.listenerAdds - end.listenerRemoves) - (start.listenerAdds - start.listenerRemoves);
  expect(listenerGrowth).toBeLessThanOrEqual(2);
  if (start.usedJSHeapSize !== null && end.usedJSHeapSize !== null) {
    expect(end.usedJSHeapSize - start.usedJSHeapSize).toBeLessThanOrEqual(12 * 1024 * 1024);
  }
});
