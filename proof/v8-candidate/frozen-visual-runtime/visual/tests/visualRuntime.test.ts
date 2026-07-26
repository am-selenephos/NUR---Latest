/**
 * Guards for the invariants that the current interface violates.
 *
 * These are regression tests, not aspirational ones: the shipped V43 runtime
 * never cancels its frame loop, and the V199 prototype leaves three superseded
 * engines running with no-op draw calls. If this suite ever passes while those
 * defects return, the guard is wrong.
 */

import { beforeEach, describe, expect, it, vi } from "vitest";
import { NURVisualRuntime, CANVAS_ID } from "../NURVisualRuntime";
import { SceneOrchestrator, VISUAL_HOST_ID, VISUAL_TELEMETRY_ID, isVisualRoute } from "../SceneOrchestrator";
import { SpriteAtlas } from "../materials/SpriteAtlas";
import { buildSystemsModel, orbitRelationships } from "../DataBinding";
import { NeuralCloud } from "../objects/NeuralCloud";
import { DepthField } from "../objects/DepthField";
import type { V197SystemsSnapshot } from "../../bridge/v197ApiClient";

function systemsSnapshot(): V197SystemsSnapshot {
  const make = (slug: string, title: string, orbit: string, percent: number, goals: number, actions: number) => ({
    slug,
    title,
    definition: `${title} definition`,
    orbit_id: orbit,
    questions: [],
    checklist: [],
    progress_percent: percent,
    progress_sources: {
      completed_actions: Math.round((percent / 100) * actions),
      total_actions: actions,
      action_completion_percent: percent,
      goal_progress_percent: percent,
      latest_diagnostic_score: 0,
      glow_points: 0,
      formula: "0.5*actions + 0.3*goals + 0.2*diagnostic",
    },
    active_goal_count: goals,
    goals: [],
    blockers: [],
    next_move: { kind: "action", id: null, title: "Write the next page" },
    prediction: {
      if_ignored: "",
      if_followed: "",
      basis: {},
      provenance_label: "derived",
    },
  });

  return {
    provenance_label: "Derived from your recorded actions",
    systems: [
      make("study", "Study", "orbit-mind", 60, 3, 10),
      make("body", "Body", "orbit-body", 20, 1, 5),
      make("money", "Money", "orbit-mind", 0, 0, 0),
    ],
  } as unknown as V197SystemsSnapshot;
}

function stubCanvas(): void {
  // jsdom has no 2D context; the runtime must still mount and tear down safely.
  HTMLCanvasElement.prototype.getContext = vi.fn(() => ({
    clearRect: vi.fn(),
    setTransform: vi.fn(),
    save: vi.fn(),
    restore: vi.fn(),
    beginPath: vi.fn(),
    closePath: vi.fn(),
    moveTo: vi.fn(),
    lineTo: vi.fn(),
    arc: vi.fn(),
    ellipse: vi.fn(),
    fill: vi.fn(),
    stroke: vi.fn(),
    fillRect: vi.fn(),
    drawImage: vi.fn(),
    quadraticCurveTo: vi.fn(),
    setLineDash: vi.fn(),
    createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
    globalAlpha: 1,
    globalCompositeOperation: "source-over",
    lineWidth: 1,
    strokeStyle: "",
    fillStyle: "",
    lineDashOffset: 0,
  })) as unknown as typeof HTMLCanvasElement.prototype.getContext;
}

describe("NURVisualRuntime", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    stubCanvas();
  });

  it("owns exactly one canvas even when mounted repeatedly", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);

    const first = new NURVisualRuntime(document, host);
    const second = new NURVisualRuntime(document, host);

    expect(document.querySelectorAll(`#${CANVAS_ID}`)).toHaveLength(1);
    first.destroy();
    second.destroy();
  });

  it("holds no more than one outstanding frame and none after destroy", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const runtime = new NURVisualRuntime(document, host);

    expect(runtime.pendingFrames()).toBeLessThanOrEqual(1);
    runtime.destroy();
    expect(runtime.pendingFrames()).toBe(0);
  });

  it("removes every bound listener and its canvas on destroy", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const runtime = new NURVisualRuntime(document, host);

    const target = document.createElement("div");
    const remove = vi.spyOn(target, "removeEventListener");
    runtime.bindListener(target, "click", () => undefined);

    runtime.destroy();

    expect(remove).toHaveBeenCalledWith("click", expect.any(Function), undefined);
    expect(document.getElementById(CANVAS_ID)).toBeNull();
  });
});

describe("SpriteAtlas", () => {
  beforeEach(() => stubCanvas());

  it("rasterises each colour and radius bucket once", () => {
    const atlas = new SpriteAtlas({ pixelRatio: 1 });
    for (let index = 0; index < 400; index += 1) {
      atlas.sprite("glow", "#8fc5ff", 12 + (index % 3));
    }
    // 400 draws of the same bucket must not produce 400 sprites — this is the
    // allocation defect the current star engine has.
    expect(atlas.size()).toBe(1);
  });

  it("keeps distinct buckets separate", () => {
    const atlas = new SpriteAtlas({ pixelRatio: 1 });
    atlas.sprite("glow", "#8fc5ff", 4);
    atlas.sprite("glow", "#8fc5ff", 60);
    atlas.sprite("core", "#8fc5ff", 4);
    expect(atlas.size()).toBe(3);
  });
});

describe("DataBinding", () => {
  it("maps real snapshot figures without inventing any", () => {
    const model = buildSystemsModel(systemsSnapshot());
    expect(model.nodes).toHaveLength(3);

    const study = model.nodes[0];
    expect(study?.progress).toBeCloseTo(0.6);
    expect(study?.completedActions).toBe(6);
    expect(study?.totalActions).toBe(10);
    expect(study?.goalCount).toBe(3);
    expect(study?.progressFormula).toContain("0.5*actions");
  });

  it("marks a System with no recorded activity as having no data", () => {
    const model = buildSystemsModel(systemsSnapshot());
    const money = model.nodes.find(node => node.slug === "money");
    expect(money?.hasData).toBe(false);
    expect(money?.progress).toBe(0);
  });

  it("draws an arc only between Systems that genuinely share an orbit", () => {
    const model = buildSystemsModel(systemsSnapshot());
    const pairs = orbitRelationships(model.nodes);
    // study + money share orbit-mind; body is alone in orbit-body.
    expect(pairs).toEqual([[0, 2]]);
  });

  it("treats an absent snapshot as empty rather than fabricating Systems", () => {
    const model = buildSystemsModel(null);
    expect(model.empty).toBe(true);
    expect(model.nodes).toHaveLength(0);
  });
});

describe("SceneOrchestrator", () => {
  beforeEach(() => {
    document.body.innerHTML = "";
    // Slice 1 is opt-in until the legacy engine is replaced; the guards below
    // exercise the enabled path deliberately.
    document.documentElement.dataset.nurVisualStage = "on";
    stubCanvas();
  });

  /**
   * Reproduces the canonical Systems surface: the map panel plus the seven
   * `.universe-system-node` buttons V197 already ships. The stage must attach to
   * these, never replace or duplicate them.
   */
  function anchor(slugs: string[] = ["study", "body", "money"]): HTMLElement {
    const page = document.createElement("div");
    page.id = "page-systems";
    page.className = "active";
    const panel = document.createElement("div");
    panel.className = "universe-map-panel";
    for (const slug of slugs) {
      const button = document.createElement("button");
      button.className = "universe-system-node";
      button.dataset.systemSlug = slug;
      panel.appendChild(button);
    }
    page.appendChild(panel);
    document.body.appendChild(page);
    return panel;
  }

  function canonicalButtons(): NodeListOf<HTMLElement> {
    return document.querySelectorAll<HTMLElement>(".universe-system-node");
  }

  it("mounts on a Systems route and tears down when the route leaves", () => {
    anchor();
    const orchestrator = new SceneOrchestrator();

    orchestrator.apply(document, "/systems", systemsSnapshot());
    expect(document.getElementById(VISUAL_HOST_ID)).not.toBeNull();
    expect(orchestrator.activeSceneId()).toBe("systems");

    orchestrator.apply(document, "/settings", systemsSnapshot());
    expect(document.getElementById(VISUAL_HOST_ID)).toBeNull();
    expect(orchestrator.pendingFrames()).toBe(0);
  });

  it("never leaves a second stage behind when the route is re-applied", () => {
    anchor();
    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", systemsSnapshot());
    orchestrator.apply(document, "/systems", systemsSnapshot());
    orchestrator.apply(document, "/universe", systemsSnapshot());

    expect(document.querySelectorAll(`#${VISUAL_HOST_ID}`)).toHaveLength(1);
    expect(document.querySelectorAll(`#${CANVAS_ID}`)).toHaveLength(1);
    orchestrator.teardown();
  });

  it("adds no System control of its own — the canonical buttons stay the only ones", () => {
    anchor();
    const before = canonicalButtons().length;
    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", systemsSnapshot());

    // Duplicating the canonical control surface is the failure this guards.
    expect(canonicalButtons()).toHaveLength(before);
    expect(document.querySelectorAll("button").length).toBe(before);
    orchestrator.teardown();
  });

  it("binds every canonical System button and describes it with real figures", () => {
    anchor();
    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", systemsSnapshot());

    expect(orchestrator.boundControlCount()).toBe(3);

    const study = document.querySelector<HTMLElement>('[data-system-slug="study"]');
    expect(study?.getAttribute("aria-describedby")).toBe(`${VISUAL_TELEMETRY_ID}-study`);

    const description = document.getElementById(`${VISUAL_TELEMETRY_ID}-study`);
    expect(description?.textContent).toContain("Study");
    expect(description?.textContent).toContain("6 of 10 actions complete");
    expect(description?.textContent).toContain("3 active goals");
    expect(description?.textContent).toContain("0.5*actions");
    orchestrator.teardown();
  });

  it("returns the canonical buttons to their original state on teardown", () => {
    anchor();
    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", systemsSnapshot());
    orchestrator.teardown();

    const study = document.querySelector<HTMLElement>('[data-system-slug="study"]');
    expect(study?.hasAttribute("aria-describedby")).toBe(false);
    expect(study?.classList.contains("nur-visual-focused")).toBe(false);
    expect(orchestrator.boundControlCount()).toBe(0);
  });

  it("matches canonical buttons by title when hydration has not added a slug", () => {
    const page = document.createElement("div");
    page.id = "page-systems";
    page.className = "active";
    const panel = document.createElement("div");
    panel.className = "universe-map-panel";
    const button = document.createElement("button");
    button.className = "universe-system-node";
    button.dataset.system = "Study";
    panel.appendChild(button);
    page.appendChild(panel);
    document.body.appendChild(page);

    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", systemsSnapshot());
    expect(orchestrator.boundControlCount()).toBe(1);
    orchestrator.teardown();
  });

  it("states the empty case instead of drawing Systems that do not exist", () => {
    anchor([]);
    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", null);
    expect(orchestrator.boundControlCount()).toBe(0);
    expect(document.querySelector(".nur-visual-empty")?.textContent).toContain("No Systems are active yet");
    orchestrator.teardown();
  });

  it("stays unmounted unless explicitly enabled", () => {
    anchor();
    delete document.documentElement.dataset.nurVisualStage;
    const orchestrator = new SceneOrchestrator();
    orchestrator.apply(document, "/systems", systemsSnapshot());
    expect(document.getElementById(VISUAL_HOST_ID)).toBeNull();
    expect(orchestrator.pendingFrames()).toBe(0);
  });

  it("recognises only the Systems surfaces as visual routes", () => {
    expect(isVisualRoute("/systems")).toBe(true);
    expect(isVisualRoute("/universe")).toBe(true);
    expect(isVisualRoute("/talk")).toBe(false);
    expect(isVisualRoute("/settings")).toBe(false);
  });
});

describe("NeuralCloud hero object", () => {
  it("builds the NUR anatomy, not a primitive", () => {
    const cloud = new NeuralCloud({ density: 1, mobile: false });
    const groups = new Set(cloud.points.map(point => point.group));
    // Three distinct structures are what give the object a silhouette.
    expect(groups).toEqual(new Set(["cortex", "cereb", "stem"]));
    expect(cloud.points.length).toBeGreaterThan(900);

    const cortex = cloud.points.filter(point => point.group === "cortex");
    const cereb = cloud.points.filter(point => point.group === "cereb");
    const stem = cloud.points.filter(point => point.group === "stem");
    expect(cortex.length).toBe(794);
    expect(cereb.length).toBe(161);
    expect(stem.length).toBe(105);

    // The longitudinal fissure must actually separate the hemispheres: no cortex
    // point may sit on the midline above the underside.
    const onMidline = cortex.filter(point => Math.abs(point.x) < 0.1 && point.y > -0.12);
    expect(onMidline).toHaveLength(0);

    // The cerebellum sits low and to the back; the stem descends below it.
    expect(Math.max(...cereb.map(point => point.y))).toBeLessThan(0);
    expect(Math.max(...cereb.map(point => point.z))).toBeLessThan(0);
    expect(Math.min(...stem.map(point => point.y))).toBeLessThan(-0.9);
  });

  it("scales its population with the quality tier", () => {
    const high = new NeuralCloud({ density: 1, mobile: false });
    const low = new NeuralCloud({ density: 0.38, mobile: true });
    expect(low.points.length).toBeLessThan(high.points.length / 2);
    expect(low.points.length).toBeGreaterThan(100);
  });

  it("assigns cortex points to Systems and leaves shared structure unassigned", () => {
    const cloud = new NeuralCloud({ density: 1, mobile: false });
    cloud.assignSystems(7);

    const assigned = new Set(
      cloud.points.filter(point => point.group === "cortex").map(point => point.system),
    );
    // Every System must own a contiguous region, so all seven indices appear.
    expect(assigned).toEqual(new Set([0, 1, 2, 3, 4, 5, 6]));

    for (const point of cloud.points) {
      if (point.group !== "cortex") expect(point.system).toBe(-1);
    }
  });

  it("releases its points on dispose", () => {
    const cloud = new NeuralCloud({ density: 1, mobile: false });
    cloud.dispose();
    expect(cloud.points).toHaveLength(0);
  });
});

describe("DepthField", () => {
  it("separates planes by parallax, size and count", () => {
    const far = new DepthField("far", 1);
    const near = new DepthField("near", 1);
    expect(far.plane).toBe("far");
    expect(near.plane).toBe("near");
    // Depth reads through correlated differences, so the planes must not be
    // interchangeable scatters of the same particles.
    far.dispose();
    near.dispose();
  });
});

describe("photosensitivity safety (WCAG 2.3.1)", () => {
  /**
   * A regression guard for a real defect that shipped: hero points twinkled at
   * 1.59-5.09 Hz with a +/-39% luminance swing on a black field, which the
   * founder correctly described as looking like a seizure. WCAG 2.3.1 permits no
   * more than three general flashes per second, where a general flash is a pair
   * of opposing relative-luminance changes of 10% or more.
   *
   * The source is asserted directly because the frequencies are constants; a
   * rendering test could not distinguish 0.3 Hz from 5 Hz without running for
   * seconds.
   */
  const HZ = (radiansPerMs: number): number => (radiansPerMs * 1000) / (2 * Math.PI);
  const SAFE_HZ = 3;

  it("keeps every animated luminance term below the three-flash threshold", async () => {
    const cloud = await import("node:fs/promises")
      .then(fs => fs.readFile("src/visual/objects/NeuralCloud.ts", "utf8"));
    const field = await import("node:fs/promises")
      .then(fs => fs.readFile("src/visual/objects/DepthField.ts", "utf8"));

    const twinkle = cloud.match(/twinkleSpeed: random\(([\d.]+), ([\d.]+)\)/);
    expect(twinkle).not.toBeNull();
    expect(HZ(Number(twinkle?.[2]))).toBeLessThan(SAFE_HZ);

    // The hero's luminance is driven by one coherent field plus a shared breath.
    // Both must stay well under the flash threshold.
    const wave = cloud.match(/coherentNoise\(point\.x, point\.y, point\.z, now \* ([\d.]+)\)/);
    expect(wave).not.toBeNull();
    expect(HZ(Number(wave?.[1]))).toBeLessThan(SAFE_HZ);

    const breath = cloud.match(/Math\.sin\(now \* ([\d.]+)\) \* 0\.03/);
    expect(breath).not.toBeNull();
    expect(HZ(Number(breath?.[1]))).toBeLessThan(SAFE_HZ);

    // Per-point independent flicker must not return: luminance may only come
    // from the shared field, never from a per-point phase and speed.
    expect(cloud).not.toMatch(/Math\.sin\(now \* point\.twinkleSpeed/);

    const fieldSpeed = field.match(/speed: ([\d.]+) \+ Math\.random\(\) \* ([\d.]+)/);
    expect(fieldSpeed).not.toBeNull();
    expect(HZ(Number(fieldSpeed?.[1]) + Number(fieldSpeed?.[2]))).toBeLessThan(SAFE_HZ);
  });

  it("keeps the luminance swing well under a WCAG general flash", () => {
    // Hero: 0.9 +/- (0.05 swell + 0.05 shimmer) => at most 11% peak-to-mean.
    const heroSwing = (0.05 + 0.05) / 0.9;
    expect(heroSwing).toBeLessThan(0.15);
    // Field: 0.86 +/- 0.12 => 14%, slow enough that it never pairs into a flash.
    const fieldSwing = 0.12 / 0.86;
    expect(fieldSwing).toBeLessThan(0.2);
  });
});

describe("bloom feedback safety", () => {
  /**
   * A regression guard for a defect that reached the founder: bloom composited
   * additively onto the same surface the trails preserved, so each frame
   * re-amplified the previous frame's bloom and the screen saturated to solid
   * white within about a second.
   */
  it("never lets bloom read from the surface it writes into", async () => {
    const source = await import("node:fs/promises")
      .then(fs => fs.readFile("src/visual/NURVisualRuntime.ts", "utf8"));

    // Bloom must take an explicit source argument rather than reading the canvas
    // it is about to write to.
    expect(source).toMatch(/applyBloom\(strength: number, radius: number, source: HTMLCanvasElement \| null\)/);
    expect(source).toMatch(/bloom\.drawImage\(source, 0, 0, width, height\)/);
    expect(source).not.toMatch(/bloom\.drawImage\(this\.canvas/);

    // When trails are active the scene must render into its own buffer.
    expect(source).toMatch(/const target = trails \? this\.ensureSceneBuffer\(\) : this\.context/);
    expect(source).toMatch(/context: target,/);
  });

  it("keeps bloom strength below a level that could wash the frame", async () => {
    const scene = await import("node:fs/promises")
      .then(fs => fs.readFile("src/visual/scenes/SystemsScene.ts", "utf8"));
    const bloom = scene.match(/bloom: ([\d.]+)/);
    expect(bloom).not.toBeNull();
    expect(Number(bloom?.[1])).toBeLessThanOrEqual(0.35);
  });
});
