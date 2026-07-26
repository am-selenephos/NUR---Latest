/**
 * Route-aware owner of the visual runtime.
 *
 * Holds at most one runtime and one scene for the whole application. When the
 * route leaves the scenes it knows about, it destroys the runtime rather than
 * hiding it — a hidden canvas that keeps animating is the exact defect this
 * system exists to remove.
 *
 * Accessibility deliberately does **not** introduce a parallel list of System
 * buttons. Canonical V197 already ships seven `.universe-system-node` controls,
 * and adding a second set would be a duplicate control surface. Instead the
 * scene binds to those existing buttons for focus and keyboard, and this module
 * contributes only the telemetry the canonical markup does not carry — the
 * progress figures and the verbatim formula behind them — wired to each button
 * through `aria-describedby`.
 */

import { NURVisualRuntime } from "./NURVisualRuntime";
import { SystemsScene } from "./scenes/SystemsScene";
import { buildSystemsModel, type SystemNodeModel, type SystemsSceneModel } from "./DataBinding";
import type { V197SystemsSnapshot } from "../bridge/v197ApiClient";
import { disposeV197StarBrain, ensureV197StarBrain } from "../bridge/v197StarBrain";

export const VISUAL_HOST_ID = "nur-visual-stage";
export const VISUAL_TELEMETRY_ID = "nur-visual-telemetry";
export const CANONICAL_NODE_SELECTOR = ".universe-system-node";

const SYSTEMS_ROUTES = new Set(["/systems", "/universe", "/universe/map", "/universe/orbits"]);

export function isVisualRoute(route: string): boolean {
  return SYSTEMS_ROUTES.has(route);
}

/**
 * Slice 1 ships **off by default**.
 *
 * The first capture proved the stage is not yet correct on the real Systems
 * surface: the canonical page already renders the same progress figures and
 * formula this module contributes, and the legacy V43 star-brain canvas is still
 * running, so mounting here produces a third canvas and duplicated telemetry.
 * Until the legacy engine is replaced rather than layered over, the stage is
 * opt-in so the founder can compare candidate against baseline without the
 * product carrying a known-duplicated surface.
 *
 * Enable for a session with:
 *   document.documentElement.dataset.nurVisualStage = "on"
 * or persistently with localStorage `nur.visual.stage = "on"`.
 */
export function visualStageEnabled(document: Document): boolean {
  if (document.documentElement.dataset.nurVisualStage === "on") return true;
  if (document.documentElement.dataset.nurVisualStage === "off") return false;

  // The stage lives inside the canonical iframe, so read the *host* location:
  // ?nur-visual=on turns it on for a visit, ?nur-visual=off turns it off again
  // and clears the stored preference. This exists so the candidate can be
  // compared against the baseline by URL alone, with no console step.
  try {
    const host = document.defaultView?.parent ?? document.defaultView;
    const flag = new URLSearchParams(host?.location?.search ?? "").get("nur-visual");
    if (flag === "on") {
      host?.localStorage?.setItem("nur.visual.stage", "on");
      return true;
    }
    if (flag === "off") {
      host?.localStorage?.setItem("nur.visual.stage", "off");
      return false;
    }
  } catch {
    // Cross-origin or storage-denied: fall through to the stored preference.
  }

  // OFF by default again. The founder's judgement was that the full-bleed
  // cinematic stage looked worse than the V43 star brain it replaced, so the
  // brain returns to its original surface and this experiment stays behind
  // ?nur-visual=on for comparison only.
  try {
    return document.defaultView?.localStorage?.getItem("nur.visual.stage") === "on";
  } catch {
    return false;
  }
}

interface BoundNode {
  button: HTMLElement;
  index: number;
}

interface OrchestratorState {
  runtime: NURVisualRuntime;
  scene: SystemsScene;
  host: HTMLElement;
  telemetry: HTMLElement;
  document: Document;
  bound: BoundNode[];
  model: SystemsSceneModel;
  /** True when this mount stopped the legacy engine and must restore it. */
  legacyStopped: boolean;
  /** Watches the Systems panel so late-hydrated nodes still get bound. */
  hydrationObserver: MutationObserver | null;
}

export class SceneOrchestrator {
  private state: OrchestratorState | null = null;
  private currentRoute = "";

  activeSceneId(): string | null {
    return this.state?.runtime.activeSceneId() ?? null;
  }

  pendingFrames(): number {
    return this.state?.runtime.pendingFrames() ?? 0;
  }

  /** Canonical controls this stage has attached behaviour to; 0 when unmounted. */
  boundControlCount(): number {
    return this.state?.bound.length ?? 0;
  }

  apply(document: Document, route: string, systems: V197SystemsSnapshot | null | undefined): void {
    if (!isVisualRoute(route) || !visualStageEnabled(document)) {
      this.teardown();
      this.currentRoute = route;
      return;
    }

    const model = buildSystemsModel(systems);
    if (this.state && this.state.document === document && document.contains(this.state.host)) {
      this.state.model = model;
      this.state.scene.updateModel(model);
      this.bindCanonicalNodes(this.state);
      this.renderTelemetry(this.state, null);
      this.currentRoute = route;
      return;
    }

    this.teardown();
    const anchor = resolveAnchor(document);
    if (!anchor) return;

    // Take the surface from the legacy engine before creating a second owner.
    // Layering over it was the P0 defect in the first Slice 1 capture.
    const legacyStopped = disposeV197StarBrain(document);

    const host = ensureHost(document, anchor);
    const telemetry = ensureTelemetry(document, host);
    const runtime = new NURVisualRuntime(document, host);
    const scene = new SystemsScene(model);

    const state: OrchestratorState = {
      runtime,
      scene,
      host,
      telemetry,
      document,
      bound: [],
      model,
      legacyStopped,
      hydrationObserver: null,
    };
    this.state = state;

    scene.setFocusListener(node => this.reflectFocus(state, node));
    runtime.setScene(scene);
    this.bindCanonicalNodes(state);
    this.renderTelemetry(state, null);
    this.bindPointer(state);
    this.observeHydration(state, anchor);
    this.currentRoute = route;
  }

  /**
   * Attaches focus behaviour to the canonical System buttons. The scene's node
   * order is the snapshot order, so a button is matched by slug where hydration
   * supplied one and by visible title otherwise.
   */
  private bindCanonicalNodes(state: OrchestratorState): void {
    const { document, scene, runtime, model } = state;
    state.bound = [];

    const buttons = Array.from(document.querySelectorAll<HTMLElement>(CANONICAL_NODE_SELECTOR));
    for (const button of buttons) {
      const index = matchNodeIndex(button, model.nodes);
      if (index < 0) continue;

      const node = model.nodes[index];
      if (node) {
        const describedBy = `${VISUAL_TELEMETRY_ID}-${node.slug}`;
        button.setAttribute("aria-describedby", describedBy);
      }

      runtime.bindListener(button, "pointerenter", () => scene.setFocus(index));
      runtime.bindListener(button, "focus", () => scene.setFocus(index));
      runtime.bindListener(button, "blur", () => {
        if (scene.focusedIndex() === index) scene.setFocus(-1);
      });
      state.bound.push({ button, index });
    }
  }

  /**
   * The bridge hydrates the Systems panel after the stage mounts: the raw
   * canonical markup carries one active System button and hydration supplies the
   * rest with their real slugs. Binding once at mount therefore caught a single
   * node. Re-binding on mutation is what makes all seven reachable.
   */
  private observeHydration(state: OrchestratorState, anchor: HTMLElement): void {
    const view = state.document.defaultView;
    const ObserverCtor = (view as (Window & { MutationObserver?: typeof MutationObserver }) | null)?.MutationObserver;
    if (typeof ObserverCtor !== "function") return;

    let queued = false;
    const observer = new ObserverCtor(() => {
      if (queued || this.state !== state) return;
      queued = true;
      view?.requestAnimationFrame(() => {
        queued = false;
        if (this.state !== state) return;
        const before = state.bound.length;
        this.bindCanonicalNodes(state);
        if (state.bound.length !== before) this.renderTelemetry(state, null);
      });
    });
    observer.observe(anchor, {
      subtree: true,
      childList: true,
      attributes: true,
      attributeFilter: ["data-system-slug", "data-system"],
    });
    state.hydrationObserver = observer;
  }

  private bindPointer(state: OrchestratorState): void {
    const { runtime, scene, host } = state;
    runtime.bindListener(host, "pointermove", event => {
      const rect = host.getBoundingClientRect();
      const pointerEvent = event as PointerEvent;
      const index = scene.nodeAt(pointerEvent.clientX - rect.left, pointerEvent.clientY - rect.top);
      if (index >= 0) scene.setFocus(index);
    }, { passive: true });
    runtime.bindListener(host, "pointerleave", () => scene.setFocus(-1), { passive: true });

    // A click anywhere sends a shockwave through the mass. It costs nothing,
    // requires no target, and makes the world feel like it is made of matter
    // that answers you.
    runtime.bindListener(state.document, "pointerdown", event => {
      const pointerEvent = event as PointerEvent;
      const rect = host.getBoundingClientRect();
      scene.strike(pointerEvent.clientX - rect.left, pointerEvent.clientY - rect.top, 1);
    }, { passive: true });
  }

  /** Canvas focus → canonical button state, so the two can never drift apart. */
  private reflectFocus(state: OrchestratorState, node: SystemNodeModel | null): void {
    for (const entry of state.bound) {
      const active = node !== null && state.model.nodes[entry.index]?.slug === node.slug;
      entry.button.classList.toggle("nur-visual-focused", active);
    }
    this.renderTelemetry(state, node);
  }

  /**
   * Telemetry, not controls. Every figure is the same value the scene encodes,
   * and the progress formula is printed verbatim so the number is auditable.
   * Each System's block keeps a stable id so the canonical button can reference
   * it with aria-describedby whether or not it is currently focused.
   */
  private renderTelemetry(state: OrchestratorState, _focused: SystemNodeModel | null): void {
    const { telemetry, document, model } = state;
    telemetry.textContent = "";

    if (model.empty) {
      const empty = document.createElement("p");
      empty.className = "nur-visual-empty";
      empty.textContent = "No Systems are active yet. Start one to see it enter the orbit.";
      telemetry.appendChild(empty);
      return;
    }

    // Descriptions for every System, so assistive technology can read a figure
    // for any button at any time. Only the focused one is visually presented.
    for (const node of model.nodes) {
      const block = document.createElement("p");
      block.id = `${VISUAL_TELEMETRY_ID}-${node.slug}`;
      block.className = "nur-visual-figure";

      const percent = Math.round(node.progress * 100);
      const detail = node.totalActions > 0
        ? `${node.completedActions} of ${node.totalActions} actions complete`
        : "no recorded actions yet";
      const goals = node.goalCount === 1 ? "1 active goal" : `${node.goalCount} active goals`;

      const title = document.createElement("span");
      title.className = "nur-visual-figure__title";
      title.textContent = node.title;

      const figures = document.createElement("span");
      figures.className = "nur-visual-figure__values";
      figures.textContent = `${percent}% · ${detail} · ${goals}`;

      block.append(title, figures);

      if (node.progressFormula) {
        const formula = document.createElement("span");
        formula.className = "nur-visual-figure__formula";
        formula.textContent = node.progressFormula;
        block.appendChild(formula);
      }

      telemetry.appendChild(block);
    }

    if (model.provenanceLabel) {
      const provenance = document.createElement("p");
      provenance.className = "nur-visual-provenance";
      provenance.textContent = model.provenanceLabel;
      telemetry.appendChild(provenance);
    }
  }

  teardown(): void {
    if (!this.state) return;
    for (const entry of this.state.bound) {
      entry.button.classList.remove("nur-visual-focused");
      entry.button.removeAttribute("aria-describedby");
    }
    this.state.hydrationObserver?.disconnect();
    this.state.hydrationObserver = null;
    const restoreLegacy = this.state.legacyStopped;
    const document = this.state.document;
    this.state.runtime.destroy();
    this.state.host.remove();
    this.state = null;

    // Give the surface back exactly as it was found, so leaving the stage does
    // not silently remove the founder-approved star brain from the product.
    if (restoreLegacy) {
      try {
        ensureV197StarBrain(document);
      } catch {
        // A failed restore must not throw out of a route change.
      }
    }
  }

  route(): string {
    return this.currentRoute;
  }
}

/**
 * Matches a canonical button to a snapshot System. Hydration supplies
 * `data-system-slug`; the raw canonical markup carries only the display title,
 * so both are accepted.
 */
function matchNodeIndex(button: HTMLElement, nodes: SystemNodeModel[]): number {
  const slug = button.dataset.systemSlug;
  if (slug) {
    const bySlug = nodes.findIndex(node => node.slug === slug);
    if (bySlug >= 0) return bySlug;
  }
  const title = (button.dataset.system ?? button.querySelector("b")?.textContent ?? "").trim().toLowerCase();
  if (!title) return -1;
  return nodes.findIndex(node => node.title.trim().toLowerCase() === title);
}

/**
 * The world sits behind the entire document, not inside a panel.
 *
 * Confining the scene to `.universe-map-panel` capped it at roughly 747x468 —
 * a cinematic object cannot exist in a box that size while the rest of the page
 * floats above it on flat black. Anchoring to the body lets the hero occupy the
 * full viewport and the interface float within the same world.
 */
function resolveAnchor(document: Document): HTMLElement | null {
  return document.body ?? null;
}

function ensureHost(document: Document, anchor: HTMLElement): HTMLElement {
  document.getElementById(VISUAL_HOST_ID)?.remove();
  const host = document.createElement("div");
  host.id = VISUAL_HOST_ID;
  host.className = "nur-visual-stage";
  anchor.prepend(host);
  return host;
}

function ensureTelemetry(document: Document, host: HTMLElement): HTMLElement {
  const telemetry = document.createElement("div");
  telemetry.id = VISUAL_TELEMETRY_ID;
  telemetry.className = "nur-visual-mirror";
  host.appendChild(telemetry);
  return telemetry;
}
