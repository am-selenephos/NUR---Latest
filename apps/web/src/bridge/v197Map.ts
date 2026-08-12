/**
 * Map — systems, paths and possible futures, rendered V197-native.
 *
 * Plain DOM and SVG through the bridge, not React. §38's component tree is
 * preserved as the function decomposition below (`mapHeader`, `mapNavigator`,
 * `mapCanvas`, `mapPathsView`, `mapDecisionsView`, `mapDetailPanel` and the tab
 * renderers), because the architecture law is that the canonical V197 document
 * owns the visible product and `#root` never appears on a product page.
 *
 * Everything displayed comes from `/api/v1/map*`. There is no sample goal, no
 * placeholder route and no invented blocker anywhere in this file: an owner with
 * an empty Map sees Systems and an empty state, because a map that shows
 * imaginary territory is worse than no map.
 *
 * Three rules shape the rendering, and each is asserted by a test:
 *
 *   A candidate never looks like structure. Anything NUR proposed renders dashed,
 *   dimmer, marked "NUR suggests", and carries Accept / Reject / Why. Confirmed
 *   structure is solid. Nothing crosses that line without the owner.
 *
 *   A prediction never looks settled. Translucent, dotted perimeter, confidence
 *   and assumptions on the card. An outcome is crystallised and solid.
 *
 *   An unmeasured dimension says "Not assessed" rather than showing a number.
 *   The path lanes are mostly honest absences at first, and that is correct.
 *
 * Layout is presentation only. Dragging writes x/y through
 * `PUT /map/views/{id}/layout` and the server refuses to let position change
 * meaning, so a goal moved next to Money is still a Creation goal.
 */

import MAP_CSS from "../styles/v197-map.css?raw";
import { markV197HolographicWordmark } from "./v197Brand";
import { createV197StarSeal } from "./v197StarSeal";
import { claimV197SurfaceHost, releaseV197SurfaceHost } from "./v197SurfaceHost";
import type { V197ApiClient } from "./v197ApiClient";

const ROOT_ID = "nur-map-root";
const STYLE_ID = "nur-map-style";

export const MAP_ROUTE = "/universe/map";

export type MapMode = "universe" | "focus" | "paths" | "decisions";

type DetailTab = "overview" | "path" | "evidence" | "activity" | "nur";

interface GraphNode {
  id: string;
  kind: string;
  label: string;
  parent_id: string | null;
  status: string;
  data: Record<string, unknown>;
}

interface GraphEdge {
  id: string;
  source: string;
  target: string;
  kind: string;
  semantic?: boolean;
  user_confirmed?: boolean;
  inference_source?: string | null;
  confidence?: number | null;
  note?: string | null;
  resolvable?: boolean;
  direction?: string;
}

interface SystemRegion {
  slug: string;
  title: string;
  node_id: string;
  state: string;
  state_reason: string;
  progress_percent: number;
  active_goal_count: number;
  blocker_count: number;
  next_move: unknown;
  layout: { x: number; y: number; radius: number };
}

interface Suggestion {
  id: string;
  suggestion_type: string;
  explanation: string;
  may_be_wrong_about: string;
  confidence: number | null;
  source_refs: { type?: string; id?: string }[];
}

interface MapGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
  system_regions: SystemRegion[];
  counts: Record<string, number>;
  suggested_changes: { candidate_edges: GraphEdge[]; suggestions: Suggestion[] };
  staleness: Record<string, unknown>;
  permissions: Record<string, boolean>;
  future_paths: {
    system_slug: string;
    current_progress: number;
    if_continued: string;
    if_ignored: string;
    basis: string;
  }[];
}

const EMPTY_GRAPH: MapGraph = {
  nodes: [],
  edges: [],
  system_regions: [],
  counts: {},
  suggested_changes: { candidate_edges: [], suggestions: [] },
  staleness: {},
  permissions: {},
  future_paths: [],
};

/** §10's state language. Each pairs a word with a glyph, never a score. */
const STATE_WORD: Record<string, string> = {
  STABLE: "Stable",
  BUILDING: "Building",
  ACTIVE: "Active",
  STALLED: "Stalled",
  RECOVERING: "Recovering",
  AT_RISK: "At risk",
  UNCLEAR: "Unclear",
  DORMANT: "Dormant",
};

const STATE_GLYPH: Record<string, string> = {
  STABLE: "◈",
  BUILDING: "◇",
  ACTIVE: "◆",
  STALLED: "◌",
  RECOVERING: "◐",
  AT_RISK: "△",
  UNCLEAR: "○",
  DORMANT: "·",
};

/** Edge meaning → CSS class. Hue and dash both come from this one mapping. */
const EDGE_CLASS: Record<string, string> = {
  MASTER_TO_SYSTEM: "nur-map-edge-contains",
  SYSTEM_TO_GOAL: "nur-map-edge-contains",
  GOAL_TO_OBJECTIVE: "nur-map-edge-contains",
  PLAN_TO_STEP: "nur-map-edge-contains",
  SYSTEM_TO_PLAN: "nur-map-edge-contains",
  MASTER_TO_PLAN: "nur-map-edge-contains",
  PROJECT_TO_TASK: "nur-map-edge-contains",
  SYSTEM_TO_DECISION: "nur-map-edge-contains",
  MASTER_TO_DECISION: "nur-map-edge-contains",
  SYSTEM_TO_ACTION: "nur-map-edge-contains",
  SYSTEM_TO_OUTCOME: "nur-map-edge-contains",
  SCHEDULED_ON_TIMELINE: "nur-map-edge-contains",
  PART_OF: "nur-map-edge-contains",
  DEPENDS_ON: "nur-map-edge-depends",
  SUPPORTS: "nur-map-edge-supports",
  ENABLES: "nur-map-edge-enables",
  BLOCKS: "nur-map-edge-blocks",
  SYSTEM_TO_BLOCKER: "nur-map-edge-blocks",
  CONTRADICTS: "nur-map-edge-contradicts",
  LEADS_TO: "nur-map-edge-leads",
  LEADS_TO_OPTION: "nur-map-edge-leads",
  EVIDENCE_FOR: "nur-map-edge-evidence",
  CAME_FROM_RESEARCH: "nur-map-edge-evidence",
  WEB_SIGNAL_SAVED: "nur-map-edge-evidence",
  INVOLVES: "nur-map-edge-involves",
  INVOLVES_PERSON: "nur-map-edge-involves",
  ORBIT_MEMBER: "nur-map-edge-involves",
  SYSTEM_TO_ORBIT: "nur-map-edge-involves",
  PREDICTED_TO_PRODUCE: "nur-map-edge-predicted",
  PATH_PREDICTION: "nur-map-edge-predicted",
};

/** Why two things are connected, in words. Hovering a line must answer this. */
const EDGE_MEANING: Record<string, string> = {
  DEPENDS_ON: "cannot move until the other does",
  SUPPORTS: "helps the other along",
  ENABLES: "makes the other possible",
  BLOCKS: "is stopping the other",
  CONTRADICTS: "argues against the other",
  LEADS_TO: "leads to the other",
  EVIDENCE_FOR: "is evidence for the other",
  INVOLVES: "involves the other",
  PART_OF: "is part of the other",
  PREDICTED_TO_PRODUCE: "is predicted to produce the other",
  MASTER_TO_SYSTEM: "is one of your Systems",
  SYSTEM_TO_GOAL: "is a goal inside this System",
  GOAL_TO_OBJECTIVE: "is a milestone of this goal",
  LEADS_TO_OPTION: "is one option for this decision",
};

/** Node radius per kind. Fixed, so no score can inflate a node. */
const NODE_RADIUS: Record<string, number> = {
  MASTER_STAR: 34,
  SYSTEM: 20,
  GOAL: 13,
  OBJECTIVE: 8,
  PLAN: 10,
  PLAN_STEP: 6,
  ACTION: 6,
  DECISION: 12,
  DECISION_OPTION: 7,
  BLOCKER: 11,
  OUTCOME: 9,
  PREDICTION: 11,
  INSIGHT: 8,
  PERSON: 9,
  PROJECT: 10,
  PROJECT_TASK: 6,
  TIMELINE_EVENT: 6,
  RESEARCH_SOURCE: 6,
  WEB_SIGNAL: 6,
  GLOW_MILESTONE: 6,
};

const KIND_WORD: Record<string, string> = {
  MASTER_STAR: "You",
  SYSTEM: "System",
  GOAL: "Goal",
  OBJECTIVE: "Objective",
  PLAN: "Plan",
  PLAN_STEP: "Plan step",
  ACTION: "Action",
  DECISION: "Decision",
  DECISION_OPTION: "Option",
  BLOCKER: "Blocker",
  OUTCOME: "Outcome",
  PREDICTION: "Prediction",
  INSIGHT: "Insight",
  PERSON: "Person",
  PROJECT: "Project",
  PROJECT_TASK: "Project task",
  TIMELINE_EVENT: "Scheduled",
  RESEARCH_SOURCE: "Research source",
  WEB_SIGNAL: "Web signal",
  GLOW_MILESTONE: "Glow milestone",
};

/** §23's evidence classes → the word and hue shown on the card. */
const BASIS_PRESENTATION: Record<string, { word: string; cls: string; glyph: string }> = {
  DIRECT_FACT: { word: "Recorded fact", cls: "nur-map-basis-fact", glyph: "◆" },
  USER_INTERPRETATION: { word: "You said", cls: "nur-map-basis-user", glyph: "✎" },
  MODEL_INFERENCE: { word: "NUR inferred", cls: "nur-map-basis-inference", glyph: "◈" },
  EXTERNAL_SOURCE: { word: "External source", cls: "nur-map-basis-external", glyph: "⌖" },
  PREDICTION: { word: "Prediction", cls: "nur-map-basis-prediction", glyph: "◇" },
  UNRESOLVED_CLAIM: { word: "Unresolved", cls: "nur-map-basis-inference", glyph: "?" },
};

const OBJECT_FILTERS: { key: string; label: string; kinds: string[] }[] = [
  { key: "all", label: "All", kinds: [] },
  { key: "goals", label: "Goals", kinds: ["GOAL", "OBJECTIVE"] },
  { key: "plans", label: "Plans", kinds: ["PLAN", "PLAN_STEP", "ACTION"] },
  { key: "decisions", label: "Decisions", kinds: ["DECISION", "DECISION_OPTION"] },
  { key: "blockers", label: "Blockers", kinds: ["BLOCKER"] },
  { key: "signals", label: "Signals", kinds: ["WEB_SIGNAL", "RESEARCH_SOURCE"] },
  { key: "predictions", label: "Predictions", kinds: ["PREDICTION"] },
  { key: "outcomes", label: "Outcomes", kinds: ["OUTCOME"] },
];

const HORIZONS: { key: string; label: string; days: number | null }[] = [
  { key: "now", label: "Now", days: 0 },
  { key: "30", label: "30 days", days: 30 },
  { key: "90", label: "90 days", days: 90 },
  { key: "365", label: "1 year", days: 365 },
  { key: "all", label: "All", days: null },
];

interface MapState {
  mode: MapMode;
  graph: MapGraph;
  viewId: string | null;
  query: string;
  systemFilter: string;
  objectFilter: string;
  horizon: string;
  selected: string | null;
  tab: DetailTab;
  evidence: Record<string, unknown> | null;
  activity: Record<string, unknown> | null;
  predictions: Record<string, unknown> | null;
  comparison: Record<string, unknown> | null;
  analysis: Record<string, unknown> | null;
  smart: Record<string, unknown> | null;
  showOutline: boolean;
  showLabels: boolean;
  showEdges: boolean;
  error: string | null;
  notice: string | null;
  busy: boolean;
  /** False until the first graph load settles.
   *
   * Without this the first paint showed the empty state — "your Map begins with
   * where you are" — to an owner whose Map is merely still loading, which is a
   * lie about their own records and reads as data loss. §32 asks for a loading
   * state; this is what distinguishes "nothing recorded" from "not arrived yet".
   */
  loaded: boolean;
}

// ── small DOM helpers ────────────────────────────────────────────────────────

function el<K extends keyof HTMLElementTagNameMap>(
  doc: Document, tag: K, className?: string, content?: string,
): HTMLElementTagNameMap[K] {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function svg<K extends keyof SVGElementTagNameMap>(
  doc: Document, tag: K, attrs: Record<string, string | number> = {},
): SVGElementTagNameMap[K] {
  const node = doc.createElementNS("http://www.w3.org/2000/svg", tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, String(value));
  return node;
}

/** Every control in Map is a capsule. There is no boxed-button helper. */
function capsule(doc: Document, label: string, disabledReason?: string): HTMLButtonElement {
  const node = el(doc, "button", "nur-map-capsule", label);
  node.type = "button";
  if (disabledReason) {
    node.disabled = true;
    node.setAttribute("aria-disabled", "true");
    // An honestly disabled control always says why, in the tooltip and to a
    // screen reader. A dead button with no explanation is the thing to avoid.
    node.title = disabledReason;
    node.setAttribute("aria-description", disabledReason);
  }
  return node;
}

function chip(doc: Document, label: string, pressed: boolean, count?: number): HTMLButtonElement {
  const node = el(doc, "button", "nur-map-capsule nur-map-capsule-sm");
  node.type = "button";
  node.setAttribute("aria-pressed", pressed ? "true" : "false");
  node.append(doc.createTextNode(label));
  if (typeof count === "number") {
    node.append(el(doc, "span", "nur-map-row-meta", ` ${count}`));
  }
  return node;
}

function field(doc: Document, label: string, value: string, unmeasured = false): HTMLElement {
  const wrap = el(doc, "div", "nur-map-field");
  wrap.append(el(doc, "p", "nur-map-field-label", label));
  const body = el(doc, "p", "nur-map-field-value", value);
  if (unmeasured) body.classList.add("is-unmeasured");
  wrap.append(body);
  return wrap;
}

function ensureStyle(doc: Document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = MAP_CSS;
  doc.head.append(style);
}

function text(value: unknown, fallback = "Not recorded"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

function nodeRefOf(nodeId: string): { type: string; id: string } {
  const at = nodeId.indexOf(":");
  if (at < 0) return { type: "nur", id: nodeId };
  return { type: nodeId.slice(0, at).replace(/-/g, "_"), id: nodeId.slice(at + 1) };
}

function edgeClassOf(edge: GraphEdge): string {
  return EDGE_CLASS[edge.kind] ?? "nur-map-edge-contains";
}

/** The sentence a hovered line must be able to produce. */
function edgeWhy(edge: GraphEdge, labelOf: (id: string) => string): string {
  const meaning = EDGE_MEANING[edge.kind] ?? "is connected to";
  const base = `${labelOf(edge.source)} ${meaning} ${labelOf(edge.target)}`;
  if (edge.semantic && !edge.user_confirmed) {
    return `${base}. NUR proposed this from ${text(edge.inference_source, "an unnamed source")} — it is not part of your Map until you accept it.`;
  }
  if (edge.note) return `${base}. You noted: ${edge.note}`;
  return `${base}.`;
}

export async function renderV197Map(
  doc: Document, route: string, api: V197ApiClient,
): Promise<boolean> {
  if (route !== MAP_ROUTE) {
    doc.getElementById(ROOT_ID)?.remove();
    // Give the canonical content region back, or leaving this route would leave
    // the canonical page hidden behind a removed surface.
    releaseV197SurfaceHost(doc);
    return false;
  }

  ensureStyle(doc);
  // Mount inside the canonical shell: the rail, the top nav and the starfield all
  // stay, and this surface takes only the content region. See v197SurfaceHost.
  const claimed = claimV197SurfaceHost(doc);
  if (claimed === null) {
    // No canonical viewport means no honest place to render. Falling back to a
    // full-screen overlay is exactly the behaviour this replaced.
    releaseV197SurfaceHost(doc);
    return false;
  }
  const host: HTMLElement = claimed;

  const view = doc.defaultView;
  const isMobile = Boolean(view && view.innerWidth <= 900);

  const state: MapState = {
    // §33: a phone opens in Focus, not a shrunken galaxy.
    mode: isMobile ? "focus" : "universe",
    graph: EMPTY_GRAPH,
    viewId: null,
    query: "",
    systemFilter: "ALL",
    objectFilter: "all",
    horizon: "all",
    selected: null,
    tab: "overview",
    evidence: null,
    activity: null,
    predictions: null,
    comparison: null,
    analysis: null,
    smart: null,
    showOutline: false,
    showLabels: true,
    showEdges: true,
    error: null,
    notice: null,
    busy: false,
    loaded: false,
  };

  // ── data ───────────────────────────────────────────────────────────────────

  async function loadGraph(): Promise<void> {
    try {
      const views = await api.get<{ default_view_id: string }>("/map/views");
      state.viewId = views?.default_view_id ?? null;
      const graph = state.viewId
        ? await api.get<MapGraph>(`/map/views/${state.viewId}/graph`)
        : await api.get<MapGraph>("/map");
      state.graph = graph ?? EMPTY_GRAPH;
      state.error = null;
    } catch (error) {
      // §32: a failure must not replace the whole Map with an error card. The
      // last graph stays on screen and the notice is restrained.
      state.error = error instanceof Error ? error.message : "Part of the Map could not update.";
    }
    try {
      state.smart = await api.get<Record<string, unknown>>("/map/smart-sections");
    } catch {
      state.smart = null;
    }
    state.loaded = true;
    paint();
  }

  async function loadSelection(nodeId: string): Promise<void> {
    const ref = nodeRefOf(nodeId);
    try {
      const [evidence, activity, predictions] = await Promise.all([
        api.get<Record<string, unknown>>(`/map/entities/${ref.type}/${ref.id}/evidence`),
        api.get<Record<string, unknown>>(`/map/entities/${ref.type}/${ref.id}/activity`),
        api.get<Record<string, unknown>>(`/map/entities/${ref.type}/${ref.id}/predictions`),
      ]);
      state.evidence = evidence ?? null;
      state.activity = activity ?? null;
      state.predictions = predictions ?? null;
    } catch {
      // Detail is supplementary; a failure here must not blank the canvas.
      state.evidence = null;
    }
    paint();
  }

  async function mutate(run: () => Promise<unknown>, notice?: string): Promise<void> {
    state.busy = true;
    try {
      await run();
      state.error = null;
      state.notice = notice ?? null;
      await loadGraph();
    } catch (error) {
      // The server's own refusal is shown: "Confirm it is real before it is
      // treated as a blocker" is the useful sentence, not "request failed".
      state.error = error instanceof Error ? error.message : "That did not work.";
      paint();
    } finally {
      state.busy = false;
    }
  }

  const actions = {
    setMode(mode: MapMode) {
      state.mode = mode;
      paint();
      if (mode === "paths") void loadComparison();
      if (mode === "decisions") void loadDecisions();
    },
    setQuery(query: string) { state.query = query; paint(); },
    setSystemFilter(slug: string) { state.systemFilter = slug; paint(); },
    setObjectFilter(key: string) { state.objectFilter = key; paint(); },
    setHorizon(key: string) { state.horizon = key; paint(); },
    setTab(tab: DetailTab) { state.tab = tab; paint(); },
    toggleOutline() { state.showOutline = !state.showOutline; paint(); },
    toggleLabels() { state.showLabels = !state.showLabels; paint(); },
    toggleEdges() { state.showEdges = !state.showEdges; paint(); },
    select(nodeId: string) {
      state.selected = nodeId;
      state.tab = "overview";
      state.evidence = null;
      state.activity = null;
      state.predictions = null;
      state.analysis = null;
      paint();
      void loadSelection(nodeId);
    },
    focus(nodeId: string) {
      state.selected = nodeId;
      state.mode = "focus";
      paint();
      void loadSelection(nodeId);
    },
    accept(id: string) {
      void mutate(
        () => api.post(`/map/suggestions/${id}/accept`, {}),
        "Accepted. It is part of your Map now.",
      );
    },
    reject(id: string, suppress: boolean) {
      void mutate(
        () => api.post(`/map/suggestions/${id}/reject`, { suppress_kind: suppress }),
        suppress ? "This kind will not be raised again." : "Rejected.",
      );
    },
    generate() {
      void mutate(
        () => api.post("/map/suggestions/generate", {}),
        "Checked your own records for patterns. Nothing was changed.",
      );
    },
    resetLayout() {
      if (!state.viewId) return;
      void mutate(
        () => api.put(`/map/views/${state.viewId}/layout`, { nodes: [] }),
        "Layout left as it was; positions are cleared per node.",
      );
    },
    /** Non-drag alternative for every drag action (§34). */
    nudge(nodeId: string, dx: number, dy: number) {
      const node = state.graph.nodes.find((row) => row.id === nodeId);
      const layout = node?.data.layout as { x: number; y: number } | undefined;
      if (!layout) return;
      actions.moveTo(nodeId, layout.x + dx, layout.y + dy);
    },
    /** Where a drag or a nudge lands. Writes position and nothing else. */
    moveTo(nodeId: string, x: number, y: number) {
      if (!state.viewId) return;
      const ref = nodeRefOf(nodeId);
      void mutate(() => api.put(`/map/views/${state.viewId}/layout`, {
        nodes: [{
          node_ref_type: ref.type,
          node_ref_id: ref.id,
          x: Math.round(x * 100) / 100,
          y: Math.round(y * 100) / 100,
        }],
      }));
    },
  };

  async function loadComparison(): Promise<void> {
    const goal = state.graph.nodes.find(
      (row) => row.kind === "GOAL" && (state.selected === row.id || state.selected === null),
    );
    if (!goal) { state.comparison = null; paint(); return; }
    try {
      state.comparison = await api.post<Record<string, unknown>>(
        "/map/path-comparison", { goal_id: nodeRefOf(goal.id).id },
      );
    } catch (error) {
      state.comparison = null;
      state.error = error instanceof Error ? error.message : null;
    }
    paint();
  }

  async function loadDecisions(): Promise<void> {
    const decision = state.graph.nodes.find(
      (row) => row.kind === "DECISION" && row.status === "UNRESOLVED",
    );
    if (!decision) { state.analysis = null; paint(); return; }
    try {
      state.analysis = await api.post<Record<string, unknown>>(
        "/map/decision-analysis", { decision_id: nodeRefOf(decision.id).id },
      );
    } catch {
      state.analysis = null;
    }
    paint();
  }

  // ── derived ────────────────────────────────────────────────────────────────

  function labelOf(nodeId: string): string {
    return state.graph.nodes.find((row) => row.id === nodeId)?.label ?? nodeId;
  }

  function visibleNodes(): GraphNode[] {
    const filter = OBJECT_FILTERS.find((row) => row.key === state.objectFilter);
    const query = state.query.trim().toLowerCase();
    return state.graph.nodes.filter((node) => {
      if (node.kind === "MASTER_STAR" || node.kind === "SYSTEM") return true;
      if (filter && filter.kinds.length && !filter.kinds.includes(node.kind)) return false;
      if (state.systemFilter !== "ALL" && node.parent_id !== `system:${state.systemFilter}`) {
        return false;
      }
      if (query && !node.label.toLowerCase().includes(query)) return false;
      return true;
    });
  }

  /** Direct neighbours of the selection: what illuminates on click. */
  function neighbourhood(): Set<string> {
    if (!state.selected) return new Set();
    const near = new Set<string>([state.selected]);
    for (const edge of state.graph.edges) {
      if (edge.source === state.selected) near.add(edge.target);
      if (edge.target === state.selected) near.add(edge.source);
    }
    return near;
  }

  // ── §38 components ─────────────────────────────────────────────────────────

  function mapHeader(): HTMLElement {
    const header = el(doc, "header", "nur-map-header");

    const title = el(doc, "div", "nur-map-title");
    const heading = el(doc, "h1", undefined, "Map");
    markV197HolographicWordmark(heading);
    title.append(heading);
    title.append(el(doc, "p", "nur-map-subtitle", "Systems, paths and possible futures"));
    header.append(title);

    const modes = el(doc, "div", "nur-map-header-actions");
    modes.setAttribute("role", "tablist");
    modes.setAttribute("aria-label", "Map view mode");
    ([
      ["universe", "Universe"], ["focus", "Focus"],
      ["paths", "Paths"], ["decisions", "Decisions"],
    ] as [MapMode, string][]).forEach(([mode, label]) => {
      const button = chip(doc, label, state.mode === mode);
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", state.mode === mode ? "true" : "false");
      button.dataset.mapMode = mode;
      button.addEventListener("click", () => actions.setMode(mode));
      modes.append(button);
    });
    header.append(modes);

    const tools = el(doc, "div", "nur-map-header-actions");
    const search = el(doc, "input", "nur-map-search");
    search.type = "search";
    search.placeholder = "Search Systems, goals, plans, decisions or signals";
    search.value = state.query;
    search.setAttribute("aria-label", "Search the Map");
    search.addEventListener("input", () => actions.setQuery(search.value));
    tools.append(search);

    // Add Goal is a canonical write and lives at POST /goals; the Map does not
    // shadow it. Until the multi-field drawer exists this is honestly disabled
    // rather than pretending to work.
    tools.append(capsule(
      doc, "Add Goal",
      "Not built yet. Goals are created on the Systems page, which owns the full goal form.",
    ));
    tools.append(capsule(
      doc, "Add Signal",
      "Not built yet. Signals arrive from Talk, Journal, Today, Research and Web Signals.",
    ));
    const ask = capsule(doc, "Ask NUR to Map");
    ask.addEventListener("click", () => actions.generate());
    ask.title =
      "Checks your own records for patterns — duplicate plans, competing deadlines, "
      + "unreviewed assumptions. Deterministic, and nothing is applied without you.";
    tools.append(ask);
    header.append(tools);

    return header;
  }

  function mapNavigator(): HTMLElement {
    const pane = el(doc, "aside", "nur-map-pane nur-map-nav");
    pane.setAttribute("aria-label", "Map navigator");
    const scroll = el(doc, "div", "nur-map-pane-scroll");

    // Systems, driven from what the server returned — never a hardcoded list.
    const systems = el(doc, "div", "nur-map-nav-group");
    systems.append(el(doc, "p", "nur-map-nav-label", "Systems"));
    const systemChips = el(doc, "div", "nur-map-chips");
    const all = chip(doc, "All Systems", state.systemFilter === "ALL");
    all.addEventListener("click", () => actions.setSystemFilter("ALL"));
    systemChips.append(all);
    for (const region of state.graph.system_regions) {
      const button = chip(doc, region.title, state.systemFilter === region.slug);
      button.title = `${STATE_WORD[region.state] ?? region.state} — ${region.state_reason}`;
      button.dataset.mapSystem = region.slug;
      button.addEventListener("click", () => actions.setSystemFilter(region.slug));
      systemChips.append(button);
    }
    systems.append(systemChips);
    scroll.append(systems);

    const objects = el(doc, "div", "nur-map-nav-group");
    objects.append(el(doc, "p", "nur-map-nav-label", "Objects"));
    const objectChips = el(doc, "div", "nur-map-chips");
    for (const row of OBJECT_FILTERS) {
      const button = chip(doc, row.label, state.objectFilter === row.key);
      button.dataset.mapObjectFilter = row.key;
      button.addEventListener("click", () => actions.setObjectFilter(row.key));
      objectChips.append(button);
    }
    objects.append(objectChips);
    scroll.append(objects);

    const horizon = el(doc, "div", "nur-map-nav-group");
    horizon.append(el(doc, "p", "nur-map-nav-label", "Time horizon"));
    const horizonChips = el(doc, "div", "nur-map-chips");
    for (const row of HORIZONS) {
      const button = chip(doc, row.label, state.horizon === row.key);
      button.addEventListener("click", () => actions.setHorizon(row.key));
      horizonChips.append(button);
    }
    horizon.append(horizonChips);
    // This filters the Map; it is not the Timeline, and says so.
    horizon.append(el(
      doc, "p", "nur-map-empty",
      "Filters what the Map shows. The full chronology lives on Timeline.",
    ));
    scroll.append(horizon);

    // §13.7 smart sections, each from real rows or an honest empty line.
    const sections: [string, string][] = [
      ["current_focus", "Current focus"],
      ["needs_decision", "Needs decision"],
      ["blocked", "Blocked"],
      ["momentum", "Momentum"],
      ["fragile_paths", "Fragile paths"],
      ["recently_changed", "Recently changed"],
    ];
    for (const [key, label] of sections) {
      const rows = (state.smart?.[key] as { ref: string; label: string; reason?: string }[] | undefined) ?? [];
      const group = el(doc, "div", "nur-map-nav-group");
      group.dataset.mapSection = key;
      group.append(el(doc, "p", "nur-map-nav-label", label));
      if (!rows.length) {
        group.append(el(doc, "p", "nur-map-empty", "Nothing here yet."));
      } else {
        const list = el(doc, "ul", "nur-map-nav-list");
        for (const row of rows.slice(0, 6)) {
          const item = el(doc, "li");
          const button = el(doc, "button", "nur-map-row");
          button.type = "button";
          if (state.selected === row.ref) button.classList.add("is-selected");
          button.append(el(doc, "span", undefined, "◦"));
          button.append(el(doc, "span", "nur-map-row-label", row.label));
          button.append(el(doc, "span", "nur-map-row-meta", row.reason ? "why" : ""));
          if (row.reason) button.title = row.reason;
          button.addEventListener("click", () => actions.select(row.ref));
          item.append(button);
          list.append(item);
        }
        group.append(list);
      }
      scroll.append(group);
    }

    const create = el(doc, "div", "nur-map-nav-group");
    create.append(el(doc, "p", "nur-map-nav-label", "Create"));
    const createChips = el(doc, "div", "nur-map-chips");
    createChips.append(capsule(
      doc, "Map a Problem",
      "Not built yet as a guided flow. POST /api/v1/map/problem is live and tested, "
      + "but the six-step drawer that drives it is not.",
    ));
    createChips.append(capsule(
      doc, "Add Decision",
      "Not built yet. Decisions are created against an Orbit; the Map adds their options.",
    ));
    const suggest = capsule(doc, "Suggest a Path");
    suggest.addEventListener("click", () => actions.generate());
    createChips.append(suggest);
    create.append(createChips);
    scroll.append(create);

    pane.append(scroll);
    return pane;
  }

  function mapCanvas(): HTMLElement {
    const pane = el(doc, "section", "nur-map-pane nur-map-workspace");
    pane.setAttribute("aria-label", "Living Map");
    const wrap = el(doc, "div", "nur-map-canvas-wrap");

    const nodes = visibleNodes();
    const near = neighbourhood();

    if (!state.loaded) {
      // §32: loading is its own state. Saying "your Map begins with where you
      // are" to someone whose map has simply not arrived is a claim about their
      // records that happens to be false.
      const loading = el(doc, "div", "nur-map-pane-scroll");
      loading.dataset.mapLoading = "true";
      loading.append(el(doc, "p", "nur-map-detail-kind", "Map"));
      loading.append(el(doc, "p", "nur-map-empty", "Assembling your Systems and routes…"));
      wrap.append(loading);
      pane.append(wrap);
      return pane;
    }

    if (!nodes.some((row) => row.kind !== "MASTER_STAR" && row.kind !== "SYSTEM")) {
      // §31: the empty Map is beautiful and useful, never "no data available".
      const empty = el(doc, "div", "nur-map-pane-scroll");
      empty.append(el(doc, "p", "nur-map-detail-kind", "Your Map"));
      empty.append(el(
        doc, "h2", "nur-map-detail-title",
        "Your Map begins with where you are and where you want to move.",
      ));
      empty.append(el(
        doc, "p", "nur-map-field-value",
        `Your ${state.graph.system_regions.length} Systems are here and waiting. `
        + "Nothing else has been drawn, because nothing else has been recorded yet.",
      ));
      const regionList = el(doc, "ul", "nur-map-nav-list");
      for (const region of state.graph.system_regions) {
        const item = el(doc, "li");
        const button = el(doc, "button", "nur-map-row");
        button.type = "button";
        button.append(el(doc, "span", undefined, STATE_GLYPH[region.state] ?? "○"));
        button.append(el(doc, "span", "nur-map-row-label", region.title));
        button.append(el(doc, "span", "nur-map-row-meta", STATE_WORD[region.state] ?? region.state));
        button.title = region.state_reason;
        button.addEventListener("click", () => actions.select(region.node_id));
        item.append(button);
        regionList.append(button.parentElement === item ? button : item);
        if (!item.parentElement) regionList.append(item);
      }
      empty.append(regionList);
      wrap.append(empty);
      pane.append(wrap);
      return pane;
    }

    // Fit the real owner-ledger geometry instead of looking through a permanent
    // 1560x1120 window. Sparse maps used to occupy a small patch in the middle
    // of the workspace even though their coordinates were valid. This changes
    // only the camera; server-owned positions and drag writes stay untouched.
    const positioned = nodes.flatMap(node => {
      const layout = node.data.layout as { x: number; y: number } | undefined;
      return layout ? [{ x: layout.x, y: layout.y }] : [];
    });
    const regionExtents = state.graph.system_regions.flatMap(region => [
      { x: region.layout.x - 148, y: region.layout.y - 148 },
      { x: region.layout.x + 148, y: region.layout.y + 148 },
    ]);
    const extents = [...positioned, ...regionExtents];
    if (extents.length === 0) {
      extents.push({ x: -310, y: -230 }, { x: 310, y: 230 });
    }
    const minX = Math.min(...extents.map(point => point.x));
    const maxX = Math.max(...extents.map(point => point.x));
    const minY = Math.min(...extents.map(point => point.y));
    const maxY = Math.max(...extents.map(point => point.y));
    const mapWidth = Math.max(620, maxX - minX + 160);
    const mapHeight = Math.max(460, maxY - minY + 150);
    const mapCenterX = (minX + maxX) / 2;
    const mapCenterY = (minY + maxY) / 2;

    const canvas = svg(doc, "svg", {
      class: "nur-map-canvas",
      viewBox:
        `${mapCenterX - mapWidth / 2} ${mapCenterY - mapHeight / 2} ${mapWidth} ${mapHeight}`,
      preserveAspectRatio: "xMidYMid meet",
      role: "img",
      "aria-label":
        `Map with ${nodes.length} objects across ${state.graph.system_regions.length} Systems. `
        + "A full outline is available through the Outline control.",
    });
    canvas.dataset.mapCamera = "owner-ledger-fit";

    const defs = svg(doc, "defs");
    const regionPrism = svg(doc, "linearGradient", {
      id: "nur-map-region-prism",
      x1: "0%", y1: "0%", x2: "100%", y2: "100%",
    });
    for (const [offset, color] of [
      ["0%", "rgba(255,211,90,0.05)"],
      ["22%", "rgba(255,122,69,0.035)"],
      ["42%", "rgba(255,82,171,0.032)"],
      ["61%", "rgba(79,204,255,0.03)"],
      ["80%", "rgba(72,235,175,0.032)"],
      ["100%", "rgba(193,107,255,0.026)"],
    ]) {
      regionPrism.append(svg(doc, "stop", { offset, "stop-color": color }));
    }
    defs.append(regionPrism);
    canvas.append(defs);

    // System regions first: soft gravity behind everything.
    const regions = svg(doc, "g", { class: "nur-map-region-halo" });
    for (const region of state.graph.system_regions) {
      const dim = state.systemFilter !== "ALL" && state.systemFilter !== region.slug;
      regions.append(svg(doc, "circle", {
        cx: region.layout.x, cy: region.layout.y, r: 132,
        fill: "url(#nur-map-region-prism)",
        stroke: "rgba(248,217,138,0.1)",
        "stroke-width": 1,
        opacity: dim ? 0.25 : 1,
      }));
      const label = svg(doc, "text", {
        x: region.layout.x, y: region.layout.y - 108,
        "text-anchor": "middle", class: "nur-map-region-label",
        opacity: dim ? 0.3 : 1,
      });
      label.textContent = region.title;
      regions.append(label);
      const stateLabel = svg(doc, "text", {
        x: region.layout.x, y: region.layout.y - 94,
        "text-anchor": "middle", class: "nur-map-region-state",
        opacity: dim ? 0.3 : 1,
      });
      // State word and glyph together: never colour alone.
      stateLabel.textContent =
        `${STATE_GLYPH[region.state] ?? "○"} ${STATE_WORD[region.state] ?? region.state}`;
      regions.append(stateLabel);
    }
    canvas.append(regions);

    const positionOf = (nodeId: string): { x: number; y: number } | null => {
      const node = state.graph.nodes.find((row) => row.id === nodeId);
      const layout = node?.data.layout as { x: number; y: number } | undefined;
      return layout ? { x: layout.x, y: layout.y } : null;
    };

    const visibleIds = new Set(nodes.map((row) => row.id));

    if (state.showEdges) {
      const edgeLayer = svg(doc, "g", { class: "nur-map-edge-layer" });
      const draw = (edge: GraphEdge, candidate: boolean) => {
        const from = positionOf(edge.source);
        const to = positionOf(edge.target);
        if (!from || !to) return;
        if (!visibleIds.has(edge.source) || !visibleIds.has(edge.target)) return;
        const line = svg(doc, "path", {
          class: `nur-map-edge ${edgeClassOf(edge)}`,
          d: `M ${from.x} ${from.y} Q ${(from.x + to.x) / 2} ${(from.y + to.y) / 2 - 34} ${to.x} ${to.y}`,
        });
        if (candidate) line.classList.add("is-candidate");
        if (state.selected && !(near.has(edge.source) && near.has(edge.target))) {
          line.classList.add("is-dimmed");
        } else if (state.selected) {
          line.classList.add("is-active");
        }
        // Hovering a line answers "why are these connected?"
        const why = edgeWhy(edge, labelOf);
        const tip = svg(doc, "title");
        tip.textContent = why;
        line.append(tip);
        line.dataset.mapEdgeWhy = why;
        if (candidate) line.dataset.mapEdgeCandidate = "true";
        edgeLayer.append(line);
      };
      for (const edge of state.graph.edges) draw(edge, false);
      for (const edge of state.graph.suggested_changes.candidate_edges) draw(edge, true);
      canvas.append(edgeLayer);
    }

    // ── which nodes get a drawn label ─────────────────────────────────────────
    // The anchor and the Systems are the frame and are always named. Beyond that
    // only the selection's neighbourhood is named, capped, and only for nodes big
    // enough to carry text.
    //
    // Both halves of that are needed. Labelling by size alone produced dozens of
    // overlapping strings in the outer ring. Labelling the whole neighbourhood
    // reproduced it the moment the *anchor* was selected, because almost
    // everything hangs off the anchor — so the cap is what actually holds.
    const LABEL_BUDGET = 14;
    const labelled = new Set<string>();
    const focusCandidates: GraphNode[] = [];
    for (const node of nodes) {
      if (node.kind === "MASTER_STAR" || node.kind === "SYSTEM") {
        labelled.add(node.id);
        continue;
      }
      if (state.selected && near.has(node.id) && (NODE_RADIUS[node.kind] ?? 8) >= 9) {
        focusCandidates.push(node);
      }
    }
    focusCandidates.sort(
      (a, b) => (NODE_RADIUS[b.kind] ?? 8) - (NODE_RADIUS[a.kind] ?? 8),
    );
    for (const node of focusCandidates.slice(0, LABEL_BUDGET)) labelled.add(node.id);

    const nodeLayer = svg(doc, "g", { class: "nur-map-node-layer" });
    for (const node of nodes) {
      const layout = node.data.layout as { x: number; y: number } | undefined;
      if (!layout) continue;
      const radius = NODE_RADIUS[node.kind] ?? 8;
      const group = svg(doc, "g", { class: "nur-map-node", tabindex: 0 });
      group.dataset.mapNode = node.id;
      group.dataset.mapKind = node.kind;
      group.setAttribute("role", "button");

      if (state.selected === node.id) group.classList.add("is-selected");
      else if (state.selected && !near.has(node.id)) group.classList.add("is-dimmed");
      if (node.kind === "PREDICTION") group.classList.add("is-prediction");
      if (node.kind === "OUTCOME") group.classList.add("is-outcome");
      if (node.kind === "BLOCKER") {
        group.classList.add("is-blocker");
        if (node.status === "PROPOSED") group.classList.add("is-proposed");
      }
      if (node.kind === "DECISION" && node.status === "UNRESOLVED") {
        group.classList.add("is-unresolved");
      }

      // Geometry per kind, so meaning survives greyscale: a decision is a prism,
      // a blocker is a fracture, everything else is a luminous point.
      let body: SVGElement;
      if (node.kind === "DECISION") {
        body = svg(doc, "polygon", {
          class: "nur-map-node-body",
          points: [
            `${layout.x},${layout.y - radius}`,
            `${layout.x + radius},${layout.y}`,
            `${layout.x},${layout.y + radius}`,
            `${layout.x - radius},${layout.y}`,
          ].join(" "),
          fill: "rgba(132,61,255,0.2)",
          stroke: "rgba(193,107,255,0.8)",
          "stroke-width": 1.4,
        });
      } else if (node.kind === "BLOCKER") {
        body = svg(doc, "polygon", {
          class: "nur-map-node-body",
          points: [
            `${layout.x},${layout.y - radius}`,
            `${layout.x + radius},${layout.y + radius * 0.7}`,
            `${layout.x - radius},${layout.y + radius * 0.7}`,
          ].join(" "),
          "stroke-width": 1.4,
        });
      } else {
        body = svg(doc, "circle", {
          class: "nur-map-node-body",
          cx: layout.x, cy: layout.y, r: radius,
          fill: node.kind === "MASTER_STAR"
            ? "rgba(255,211,90,0.22)"
            : node.kind === "SYSTEM"
              ? "rgba(255,248,223,0.14)"
              : "rgba(33,232,255,0.13)",
          stroke: node.kind === "MASTER_STAR"
            ? "rgba(255,248,223,0.9)"
            : "rgba(248,217,138,0.55)",
          "stroke-width": node.kind === "MASTER_STAR" ? 2 : 1.1,
        });
      }
      group.append(body);

      const tip = svg(doc, "title");
      const kindWord = KIND_WORD[node.kind] ?? node.kind;
      tip.textContent = `${node.label} — ${kindWord}, ${node.status.toLowerCase()}`;
      group.append(tip);

      // §39: reduce labels while zoomed out. Every node keeps its name in the
      // hover tooltip and in the outline, so nothing is hidden — only undrawn.
      if (state.showLabels && labelled.has(node.id)) {
        const label = svg(doc, "text", {
          x: layout.x, y: layout.y + radius + 13,
          "text-anchor": "middle", class: "nur-map-node-label",
        });
        label.textContent =
          node.label.length > 26 ? `${node.label.slice(0, 25)}…` : node.label;
        group.append(label);
      }

      // ── drag to reposition ────────────────────────────────────────────────
      // Position is presentation. This moves the group's transform while the
      // pointer is down and persists x/y on release; the server refuses to let a
      // position change System membership or any relationship, so a goal dragged
      // next to Money is still a Creation goal. A movement threshold keeps a
      // click from becoming a one-pixel drag, and vice versa.
      let dragging = false;
      let moved = false;
      let originX = 0;
      let originY = 0;
      const toCanvas = (event: PointerEvent): { x: number; y: number } | null => {
        const matrix = canvas.getScreenCTM();
        if (!matrix) return null;
        const point = canvas.createSVGPoint();
        point.x = event.clientX;
        point.y = event.clientY;
        const mapped = point.matrixTransform(matrix.inverse());
        return { x: mapped.x, y: mapped.y };
      };

      group.addEventListener("pointerdown", (event) => {
        const pointer = event as PointerEvent;
        if (pointer.button !== 0) return;
        const at = toCanvas(pointer);
        if (!at) return;
        dragging = true;
        moved = false;
        originX = at.x;
        originY = at.y;
        group.setPointerCapture(pointer.pointerId);
      });

      group.addEventListener("pointermove", (event) => {
        if (!dragging) return;
        const at = toCanvas(event as PointerEvent);
        if (!at) return;
        const dx = at.x - originX;
        const dy = at.y - originY;
        if (!moved && Math.hypot(dx, dy) < 4) return;
        moved = true;
        group.classList.add("is-dragging");
        group.setAttribute("transform", `translate(${dx} ${dy})`);
      });

      const endDrag = (event: Event) => {
        if (!dragging) return;
        const pointer = event as PointerEvent;
        dragging = false;
        if (group.hasPointerCapture?.(pointer.pointerId)) {
          group.releasePointerCapture(pointer.pointerId);
        }
        group.classList.remove("is-dragging");
        if (!moved) return;
        const at = toCanvas(pointer);
        group.removeAttribute("transform");
        if (!at) return;
        // One write per gesture, on release — not per pointermove.
        actions.moveTo(node.id, layout.x + (at.x - originX), layout.y + (at.y - originY));
      };
      group.addEventListener("pointerup", endDrag);
      group.addEventListener("pointercancel", endDrag);

      group.addEventListener("click", () => {
        // A completed drag is not a selection.
        if (moved) { moved = false; return; }
        actions.select(node.id);
      });
      group.addEventListener("dblclick", () => actions.focus(node.id));
      group.addEventListener("keydown", (event) => {
        const key = (event as KeyboardEvent).key;
        if (key === "Enter" || key === " ") {
          event.preventDefault();
          actions.select(node.id);
          return;
        }
        // Arrow keys are the non-drag alternative to repositioning.
        const step = 28;
        const moves: Record<string, [number, number]> = {
          ArrowLeft: [-step, 0], ArrowRight: [step, 0],
          ArrowUp: [0, -step], ArrowDown: [0, step],
        };
        if (moves[key]) {
          event.preventDefault();
          actions.nudge(node.id, moves[key][0], moves[key][1]);
        }
      });
      nodeLayer.append(group);
    }
    canvas.append(nodeLayer);
    wrap.append(canvas);

    const controls = el(doc, "div", "nur-map-canvas-controls");
    const labels = chip(doc, state.showLabels ? "Labels on" : "Labels off", state.showLabels);
    labels.addEventListener("click", () => actions.toggleLabels());
    controls.append(labels);
    const edges = chip(doc, state.showEdges ? "Edges on" : "Edges off", state.showEdges);
    edges.addEventListener("click", () => actions.toggleEdges());
    controls.append(edges);
    const outline = chip(doc, "Outline", state.showOutline);
    outline.dataset.mapOutlineToggle = "true";
    outline.addEventListener("click", () => actions.toggleOutline());
    controls.append(outline);
    const centre = capsule(doc, "Center on You");
    centre.classList.add("nur-map-capsule-sm");
    centre.addEventListener("click", () => actions.select("nur"));
    controls.append(centre);
    controls.append(capsule(
      doc, "Fit all",
      "Not built yet. The canvas has no pan or zoom transform to fit to; the view is fixed.",
    ));
    const reset = capsule(doc, "Reset layout");
    reset.classList.add("nur-map-capsule-sm");
    reset.addEventListener("click", () => actions.resetLayout());
    controls.append(reset);
    wrap.append(controls);

    const legend = el(doc, "div", "nur-map-canvas-legend");
    ([
      ["Depends on", "nur-map-edge-depends"],
      ["Blocks", "nur-map-edge-blocks"],
      ["Contradicts", "nur-map-edge-contradicts"],
      ["NUR suggests", "is-candidate"],
    ] as [string, string][]).forEach(([label, cls]) => {
      const row = el(doc, "div", "nur-map-legend-row");
      const swatch = el(doc, "span", `nur-map-legend-swatch ${cls}`);
      row.append(swatch, el(doc, "span", undefined, label));
      legend.append(row);
    });
    wrap.append(legend);

    if (state.showOutline) wrap.append(mapAccessibilityOutline());

    pane.append(wrap);
    return pane;
  }

  /** A real parallel representation of the graph — §34's hard requirement. */
  function mapAccessibilityOutline(): HTMLElement {
    const wrap = el(doc, "div", "nur-map-pane-scroll");
    wrap.dataset.mapOutline = "true";
    wrap.style.position = "absolute";
    wrap.style.inset = "0";
    wrap.style.background = "rgba(0,0,0,0.94)";
    wrap.append(el(doc, "p", "nur-map-nav-label", "Map outline"));
    const root = el(doc, "ul", "nur-map-outline");
    const childrenOf = (parentId: string | null): GraphNode[] =>
      visibleNodes().filter((row) => row.parent_id === parentId);

    const render = (node: GraphNode, into: HTMLElement): void => {
      const item = el(doc, "li");
      const button = el(doc, "button", "nur-map-row");
      button.type = "button";
      const kindWord = KIND_WORD[node.kind] ?? node.kind;
      // The screen-reader sentence §34 asks for, built from real counts.
      const summary = `${node.label}. ${kindWord}. ${node.status.toLowerCase()}.`;
      button.append(el(doc, "span", undefined, "·"));
      button.append(el(doc, "span", "nur-map-row-label", node.label));
      button.append(el(doc, "span", "nur-map-row-meta", kindWord));
      button.setAttribute("aria-label", summary);
      button.addEventListener("click", () => actions.select(node.id));
      item.append(button);
      const kids = childrenOf(node.id);
      if (kids.length) {
        const list = el(doc, "ul");
        for (const kid of kids) render(kid, list);
        item.append(list);
      }
      into.append(item);
    };

    const anchor = visibleNodes().find((row) => row.kind === "MASTER_STAR");
    if (anchor) render(anchor, root);
    wrap.append(root);
    const close = capsule(doc, "Close outline");
    close.addEventListener("click", () => actions.toggleOutline());
    wrap.append(close);
    return wrap;
  }

  /**
   * §33's mobile default: a Focus list, not a shrunken galaxy.
   *
   * This exists because of a real defect found running the spec on WebKit mobile:
   * the rail and detail panel are `display: none` at phone widths, and the
   * candidate strip lived only in the detail panel — so on a phone NUR's
   * suggestions rendered into a hidden panel and were unreachable. Everything
   * waiting on the owner has to be reachable on the surface they actually open.
   */
  function mapMobileFocusList(): HTMLElement {
    const pane = el(doc, "section", "nur-map-pane nur-map-workspace");
    pane.setAttribute("aria-label", "Focus list");
    const scroll = el(doc, "div", "nur-map-pane-scroll");
    scroll.dataset.mapFocusList = "true";

    const section = (label: string, rows: { ref: string; label: string; reason?: string }[]): void => {
      const group = el(doc, "div", "nur-map-nav-group");
      group.append(el(doc, "p", "nur-map-nav-label", label));
      if (!rows.length) {
        group.append(el(doc, "p", "nur-map-empty", "Nothing here yet."));
      } else {
        const list = el(doc, "ul", "nur-map-nav-list");
        for (const row of rows) {
          const item = el(doc, "li");
          const button = el(doc, "button", "nur-map-row");
          button.type = "button";
          if (state.selected === row.ref) button.classList.add("is-selected");
          button.append(el(doc, "span", undefined, "◦"));
          button.append(el(doc, "span", "nur-map-row-label", row.label));
          button.append(el(doc, "span", "nur-map-row-meta", row.reason ? "why" : ""));
          if (row.reason) button.title = row.reason;
          button.addEventListener("click", () => actions.select(row.ref));
          item.append(button);
          list.append(item);
        }
        group.append(list);
      }
      scroll.append(group);
    };

    const read = (key: string): { ref: string; label: string; reason?: string }[] =>
      (state.smart?.[key] as { ref: string; label: string; reason?: string }[] | undefined) ?? [];

    section("Current focus", read("current_focus"));
    section("Needs decision", read("needs_decision"));
    section("Blocked", read("blocked"));
    section("Momentum", read("momentum"));
    section("Fragile paths", read("fragile_paths"));

    // Systems stay reachable on a phone, with their state and its reason.
    const systems = el(doc, "div", "nur-map-nav-group");
    systems.append(el(doc, "p", "nur-map-nav-label", "Systems"));
    const list = el(doc, "ul", "nur-map-nav-list");
    for (const region of state.graph.system_regions) {
      const item = el(doc, "li");
      const button = el(doc, "button", "nur-map-row");
      button.type = "button";
      button.append(el(doc, "span", undefined, STATE_GLYPH[region.state] ?? "○"));
      button.append(el(doc, "span", "nur-map-row-label", region.title));
      button.append(el(
        doc, "span", "nur-map-row-meta", STATE_WORD[region.state] ?? region.state,
      ));
      button.title = region.state_reason;
      button.addEventListener("click", () => actions.select(region.node_id));
      item.append(button);
      list.append(item);
    }
    systems.append(list);
    scroll.append(systems);

    // The candidate strip, on the surface rather than behind a hidden panel.
    const pending = state.graph.suggested_changes.suggestions;
    if (pending.length) {
      scroll.append(el(doc, "p", "nur-map-nav-label", "NUR suggests"));
      for (const suggestion of pending) scroll.append(candidateCard(suggestion));
    }

    pane.append(scroll);
    return pane;
  }

  function mapPathsView(): HTMLElement {
    const pane = el(doc, "section", "nur-map-pane nur-map-workspace");
    const scroll = el(doc, "div", "nur-map-pane-scroll");
    scroll.dataset.mapPaths = "true";
    scroll.append(el(doc, "p", "nur-map-detail-kind", "Paths"));

    const comparison = state.comparison;
    if (!comparison) {
      scroll.append(el(doc, "h2", "nur-map-detail-title", "Nothing to compare yet"));
      scroll.append(el(
        doc, "p", "nur-map-empty",
        "Select a goal, then Paths compares the routes that actually exist toward it.",
      ));
      pane.append(scroll);
      return pane;
    }

    const goal = comparison.goal as { title: string } | undefined;
    scroll.append(el(doc, "h2", "nur-map-detail-title", text(goal?.title, "This goal")));
    scroll.append(el(doc, "p", "nur-map-lane-strategy", text(comparison.association_basis, "")));

    const lanes = (comparison.paths as Record<string, unknown>[] | undefined) ?? [];
    if (!lanes.length) {
      scroll.append(el(doc, "p", "nur-map-empty", text(comparison.note, "")));
      pane.append(scroll);
      return pane;
    }

    const holder = el(doc, "div", "nur-map-lanes");
    for (const lane of lanes) {
      const card = el(doc, "article", "nur-map-lane");
      card.append(el(doc, "h3", "nur-map-lane-name", text(lane.name, "Route")));
      card.append(el(doc, "p", "nur-map-lane-strategy", text(lane.strategy, "")));

      const dims = el(doc, "div", "nur-map-lane-dims");
      const add = (label: string, value: unknown) => {
        const cell = el(doc, "div");
        cell.append(el(doc, "div", "nur-map-dim-label", label));
        const shown = text(value, "Not assessed");
        const body = el(doc, "div", "nur-map-dim-value", shown);
        // §19: an unmeasured dimension is styled as absent, not as a value.
        if (shown === "Not assessed" || shown === "Not recorded") {
          body.classList.add("is-unmeasured");
        }
        cell.append(body);
        dims.append(cell);
      };
      add("First step", lane.first_step);
      add("Effort", lane.effort);
      add("Time horizon", lane.time_horizon);
      add("Reversibility", lane.reversibility);
      add("Evidence", lane.evidence_strength);
      add("Expected outcome", lane.expected_outcome);
      add("Fallback", lane.fallback);
      card.append(dims);

      card.append(field(doc, "Uncertainty", text(lane.uncertainty, "")));

      const milestones = (lane.milestones as { title: string; done: boolean }[] | undefined) ?? [];
      if (milestones.length) {
        const list = el(doc, "ul", "nur-map-milestones");
        for (const milestone of milestones) {
          const item = el(doc, "li", "nur-map-milestone");
          if (milestone.done) item.classList.add("is-done");
          item.append(doc.createTextNode(`${milestone.done ? "✓" : "○"} ${milestone.title}`));
          list.append(item);
        }
        card.append(list);
      }

      const blockers = (lane.blockers as { title: string; status: string }[] | undefined) ?? [];
      if (blockers.length) {
        card.append(field(
          doc, "Blockers",
          blockers.map((row) => `${row.title} (${row.status.toLowerCase()})`).join(" · "),
        ));
      }
      holder.append(card);
    }
    scroll.append(holder);
    scroll.append(el(doc, "p", "nur-map-empty", text(comparison.note, "")));
    pane.append(scroll);
    return pane;
  }

  function mapDecisionsView(): HTMLElement {
    const pane = el(doc, "section", "nur-map-pane nur-map-workspace");
    const scroll = el(doc, "div", "nur-map-pane-scroll");
    scroll.dataset.mapDecisions = "true";
    scroll.append(el(doc, "p", "nur-map-detail-kind", "Decisions"));

    const analysis = state.analysis;
    if (!analysis) {
      scroll.append(el(doc, "h2", "nur-map-detail-title", "No open decision"));
      scroll.append(el(
        doc, "p", "nur-map-empty",
        "Unresolved forks appear here with their options, trade-offs and what each "
        + "would cost to walk back.",
      ));
      pane.append(scroll);
      return pane;
    }

    const decision = analysis.decision as { statement: string } | undefined;
    scroll.append(el(doc, "h2", "nur-map-detail-title", text(decision?.statement, "Decision")));

    const options = (analysis.options as Record<string, unknown>[] | undefined) ?? [];
    const matrix = (analysis.comparison_matrix as {
      dimension: string; values: Record<string, string>;
    }[] | undefined) ?? [];

    if (matrix.length && options.length) {
      const scrollBox = el(doc, "div", "nur-map-matrix-scroll");
      const table = el(doc, "table", "nur-map-matrix");
      const head = el(doc, "thead");
      const headRow = el(doc, "tr");
      headRow.append(el(doc, "th", undefined, "Dimension"));
      for (const option of options) {
        headRow.append(el(doc, "th", undefined, text(option.label, "Option")));
      }
      head.append(headRow);
      table.append(head);
      const body = el(doc, "tbody");
      for (const row of matrix) {
        const line = el(doc, "tr");
        line.append(el(doc, "th", undefined, row.dimension));
        for (const option of options) {
          line.append(el(doc, "td", undefined, text(row.values[String(option.id)], "—")));
        }
        body.append(line);
      }
      table.append(body);
      scrollBox.append(table);
      scroll.append(scrollBox);
    }

    const recommendation = analysis.recommendation as {
      label: string; because: string; changes_if: string;
    } | null;
    if (recommendation) {
      const card = el(doc, "div", "nur-map-doubt");
      card.append(el(doc, "p", "nur-map-doubt-label", "NUR's reading"));
      card.append(el(doc, "p", "nur-map-field-value", recommendation.because));
      // The assumption is always visible next to the recommendation.
      card.append(el(doc, "p", "nur-map-field-value", recommendation.changes_if));
      scroll.append(card);
    } else {
      scroll.append(el(doc, "p", "nur-map-empty", text(analysis.note, "")));
    }

    const actionsRow = el(doc, "div", "nur-map-candidate-actions");
    actionsRow.append(capsule(
      doc, "Choose an option",
      "Not built yet as a drawer. POST /map/decisions/{id}/choose/{option} is live and "
      + "tested; only the owner can call it.",
    ));
    actionsRow.append(capsule(
      doc, "Run an experiment first",
      "Not built yet. Experiments exist in the backend but are not wired to decisions.",
    ));
    actionsRow.append(capsule(
      doc, "Ask a consultation",
      "Not built yet. Consultations are a separate surface.",
    ));
    scroll.append(actionsRow);

    pane.append(scroll);
    return pane;
  }

  function mapDetailPanel(): HTMLElement {
    const pane = el(doc, "aside", "nur-map-pane nur-map-detail");
    pane.setAttribute("aria-label", "Selection detail");
    const scroll = el(doc, "div", "nur-map-pane-scroll");

    const node = state.graph.nodes.find((row) => row.id === state.selected);
    if (!node) {
      scroll.append(el(doc, "p", "nur-map-detail-kind", "Nothing selected"));
      scroll.append(el(
        doc, "p", "nur-map-empty",
        "Select something on the Map to understand its role, evidence and possible movement.",
      ));
      // Candidates remain reachable with nothing selected: they are the one thing
      // waiting on the owner rather than on work.
      const pending = state.graph.suggested_changes.suggestions;
      if (pending.length) {
        scroll.append(el(doc, "p", "nur-map-nav-label", "NUR suggests"));
        for (const suggestion of pending) scroll.append(candidateCard(suggestion));
      }
      pane.append(scroll);
      return pane;
    }

    const header = el(doc, "div", "nur-map-detail-header");
    header.append(el(
      doc, "p", "nur-map-detail-kind",
      `${KIND_WORD[node.kind] ?? node.kind} · ${node.status.toLowerCase()}`,
    ));
    header.append(el(doc, "h2", "nur-map-detail-title", node.label));
    scroll.append(header);

    const tabs = el(doc, "div", "nur-map-tabs");
    tabs.setAttribute("role", "tablist");
    ([
      ["overview", "Overview"], ["path", "Path"], ["evidence", "Evidence"],
      ["activity", "Activity"], ["nur", "NUR View"],
    ] as [DetailTab, string][]).forEach(([tab, label]) => {
      const button = el(doc, "button", "nur-map-tab", label);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", state.tab === tab ? "true" : "false");
      button.dataset.mapTab = tab;
      button.addEventListener("click", () => actions.setTab(tab));
      tabs.append(button);
    });
    scroll.append(tabs);

    const body = el(doc, "div");
    body.dataset.mapTabPanel = state.tab;
    body.setAttribute("role", "tabpanel");
    if (state.tab === "overview") overviewTab(body, node);
    if (state.tab === "path") pathTab(body, node);
    if (state.tab === "evidence") evidenceTab(body);
    if (state.tab === "activity") activityTab(body);
    if (state.tab === "nur") nurViewTab(body, node);
    scroll.append(body);

    pane.append(scroll);
    return pane;
  }

  function overviewTab(into: HTMLElement, node: GraphNode): void {
    const data = node.data;
    if (node.kind === "MASTER_STAR") {
      // §8: the centre is the owner's current operating state, not NUR as a
      // separate being. Every line below is a count or a row from their ledger.
      const counts = state.graph.counts;
      const read = (key: string): { ref: string; label: string }[] =>
        (state.smart?.[key] as { ref: string; label: string }[] | undefined) ?? [];
      const focus = read("current_focus");
      const decisions = read("needs_decision");
      const blocked = read("blocked");
      const momentum = read("momentum");
      const fragile = read("fragile_paths");

      into.dataset.mapCurrentPosition = "true";
      into.append(field(
        doc, "Active priorities",
        focus.length ? focus.map((row) => row.label).join(" · ") : "None recorded",
        focus.length === 0,
      ));
      into.append(field(
        doc, "Open decisions",
        decisions.length
          ? `${decisions.length} waiting on you — ${decisions[0].label}`
          : "None waiting on you",
        decisions.length === 0,
      ));
      into.append(field(
        doc, "Current constraints",
        blocked.length
          ? `${blocked.length} goal${blocked.length === 1 ? "" : "s"} blocked`
          : "Nothing is blocked",
        blocked.length === 0,
      ));
      into.append(field(
        doc, "Recent movement",
        momentum.length
          ? `${momentum.length} outcome${momentum.length === 1 ? "" : "s"} in the last 14 days`
          : "No outcome recorded in the last 14 days",
        momentum.length === 0,
      ));
      into.append(field(
        doc, "Major risks",
        fragile.length
          ? `${fragile.length} assumption${fragile.length === 1 ? "" : "s"} past review`
          : "No assumption is past its review date",
        fragile.length === 0,
      ));
      const states = state.graph.system_regions
        .map((row) => `${row.title}: ${STATE_WORD[row.state] ?? row.state}`)
        .join(" · ");
      into.append(field(doc, "Systems", states || "No Systems"));
      // Confidence in words, and only from what is actually observable. A number
      // here would be the fake precision §10 forbids.
      const recorded = (counts.goals ?? 0) + (counts.decisions ?? 0)
        + (counts.blockers ?? 0) + (counts.semantic_edges ?? 0);
      into.append(field(
        doc, "How much of this NUR can see",
        recorded === 0
          ? "Almost nothing is recorded yet, so NUR's model of your position is "
            + "close to empty. Anything it says now rests on very little."
          : `${recorded} recorded objects and connections. Anything you have not `
            + "written down is invisible here.",
        recorded === 0,
      ));
      return;
    }
    if (node.kind === "SYSTEM") {
      const region = state.graph.system_regions.find((row) => row.node_id === node.id);
      if (region) {
        into.append(field(
          doc, "State",
          `${STATE_GLYPH[region.state] ?? ""} ${STATE_WORD[region.state] ?? region.state}`,
        ));
        into.append(field(doc, "Why", region.state_reason));
        into.append(field(doc, "Active goals", String(region.active_goal_count)));
        into.append(field(doc, "Unresolved blockers", String(region.blocker_count)));
      }
    }
    if (node.kind === "BLOCKER") {
      into.append(field(doc, "Category", text(data.category)));
      into.append(field(
        doc, "Basis",
        BASIS_PRESENTATION[
          data.basis === "NUR_INFERRED" ? "MODEL_INFERENCE"
            : data.basis === "OBSERVED" ? "DIRECT_FACT" : "USER_INTERPRETATION"
        ]?.word ?? text(data.basis),
      ));
      // A blocker NUR only proposed is never presented as established.
      if (data.confirmed_by_owner === false) {
        const notice = el(doc, "div", "nur-map-doubt");
        notice.append(el(doc, "p", "nur-map-doubt-label", "Not confirmed"));
        notice.append(el(
          doc, "p", "nur-map-field-value",
          "NUR proposed this. It is not treated as a real blocker until you say it is.",
        ));
        into.append(notice);
      }
      const affects = (data.affects as { type?: string; id?: string }[] | undefined) ?? [];
      into.append(field(
        doc, "What it affects",
        affects.length
          ? affects.map((ref) => labelOf(`${ref.type}:${ref.id}`)).join(" · ")
          : "Nothing linked yet",
        affects.length === 0,
      ));
      into.append(field(doc, "Evidence items", String(data.evidence_count ?? 0)));
    }
    if (node.kind === "DECISION") {
      into.append(field(doc, "Options recorded", String(data.option_count ?? 0)));
      into.append(field(
        doc, "Resolved",
        data.chosen_option_id ? labelOf(`decision-option:${data.chosen_option_id}`) : "Not yet",
        !data.chosen_option_id,
      ));
      into.append(field(doc, "Rationale", text(data.rationale, "None recorded")));
    }
    if (node.kind === "GOAL") {
      into.append(field(doc, "Progress", `${text(data.progress_percent, "0")}% verified`));
      into.append(field(doc, "Target date", text(data.target_date, "No target date")));
      into.append(field(doc, "Why it matters", text(data.why, "Not recorded")));
    }
    if (node.kind === "DECISION_OPTION") {
      into.append(field(doc, "Reversibility", text(data.reversibility)));
      into.append(field(doc, "Time horizon", text(data.time_horizon, "Not stated"), !data.time_horizon));
      into.append(field(doc, "Risks recorded", String(data.risk_count ?? 0)));
    }
    if (typeof data.annotation_count === "number") {
      into.append(field(doc, "Your notes", String(data.annotation_count)));
    }
    if (!into.childElementCount) {
      into.append(el(
        doc, "p", "nur-map-empty",
        "This object carries no recorded detail beyond its name and place.",
      ));
    }
  }

  function pathTab(into: HTMLElement, node: GraphNode): void {
    const dependencies = state.graph.edges.filter(
      (edge) => edge.target === node.id && edge.kind === "DEPENDS_ON",
    );
    const blocks = state.graph.edges.filter(
      (edge) => edge.target === node.id && edge.kind === "BLOCKS",
    );
    const children = state.graph.nodes.filter((row) => row.parent_id === node.id);

    into.append(field(
      doc, "Depends on",
      dependencies.length
        ? dependencies.map((edge) => labelOf(edge.source)).join(" · ")
        : "Nothing recorded",
      dependencies.length === 0,
    ));
    into.append(field(
      doc, "Blocked by",
      blocks.length ? blocks.map((edge) => labelOf(edge.source)).join(" · ") : "Nothing",
      blocks.length === 0,
    ));
    into.append(field(
      doc, "Contains",
      children.length ? children.map((row) => row.label).join(" · ") : "Nothing yet",
      children.length === 0,
    ));

    const row = el(doc, "div", "nur-map-candidate-actions");
    if (node.kind === "GOAL") {
      const compare = capsule(doc, "Compare paths");
      compare.addEventListener("click", () => {
        state.selected = node.id;
        actions.setMode("paths");
      });
      row.append(compare);
    }
    row.append(capsule(
      doc, "Continue Plan",
      "Not built yet. Plan execution lives on the Plan page, which owns the step flow.",
    ));
    row.append(capsule(
      doc, "Add to Timeline",
      "Not built yet from Map. Timeline owns scheduling; POST /timeline/from-goal exists.",
    ));
    into.append(row);
  }

  function evidenceTab(into: HTMLElement): void {
    const evidence = state.evidence;
    if (!evidence) {
      into.append(el(doc, "p", "nur-map-empty", "Loading the evidence for this object…"));
      return;
    }
    const supporting = (evidence.supporting as Record<string, unknown>[] | undefined) ?? [];
    const contradicting = (evidence.contradicting as Record<string, unknown>[] | undefined) ?? [];
    const missing = (evidence.missing_information as string[] | undefined) ?? [];

    const render = (rows: Record<string, unknown>[], against: boolean): void => {
      for (const row of rows) {
        const card = el(doc, "div", "nur-map-card");
        if (against) card.classList.add("is-contradicting");
        const cls = String(row.evidence_class ?? "USER_INTERPRETATION");
        const presentation = BASIS_PRESENTATION[cls] ?? BASIS_PRESENTATION.USER_INTERPRETATION;
        // Basis is always visible, in words and with a glyph — never hue alone.
        const badge = el(doc, "p", `nur-map-card-basis ${presentation.cls}`);
        badge.textContent = `${presentation.glyph} ${presentation.word}`;
        card.append(badge);
        card.append(el(doc, "p", "nur-map-field-value", text(row.body, "")));
        card.append(el(doc, "p", "nur-map-row-meta", `Source: ${text(row.source, "unknown")}`));
        into.append(card);
      }
    };

    into.append(el(doc, "p", "nur-map-nav-label", "Supporting"));
    if (supporting.length) render(supporting, false);
    else into.append(el(doc, "p", "nur-map-empty", "Nothing supports this yet."));

    into.append(el(doc, "p", "nur-map-nav-label", "Contradicting"));
    if (contradicting.length) render(contradicting, true);
    else into.append(el(doc, "p", "nur-map-empty", "Nothing argues against this yet."));

    // Naming what is absent is part of the evidence picture.
    if (missing.length) {
      into.append(el(doc, "p", "nur-map-nav-label", "Missing information"));
      for (const line of missing) {
        into.append(el(doc, "p", "nur-map-empty", line));
      }
    }
  }

  function activityTab(into: HTMLElement): void {
    const activity = state.activity;
    const items = (activity?.items as Record<string, unknown>[] | undefined) ?? [];
    if (!items.length) {
      into.append(el(doc, "p", "nur-map-empty", "Nothing has happened to this object yet."));
      return;
    }
    const list = el(doc, "ul", "nur-map-nav-list");
    for (const row of items) {
      const item = el(doc, "li", "nur-map-card");
      item.append(el(doc, "p", "nur-map-card-basis", text(row.kind, "event")));
      item.append(el(doc, "p", "nur-map-field-value", text(row.title, "")));
      item.append(el(doc, "p", "nur-map-row-meta", text(row.at, "")));
      list.append(item);
    }
    into.append(list);
  }

  function nurViewTab(into: HTMLElement, node: GraphNode): void {
    const predictions = (state.predictions?.items as Record<string, unknown>[] | undefined) ?? [];
    if (predictions.length) {
      into.append(el(doc, "p", "nur-map-nav-label", "Predictions"));
      for (const row of predictions) {
        const card = el(doc, "div", "nur-map-card");
        const badge = el(doc, "p", "nur-map-card-basis nur-map-basis-prediction");
        badge.textContent = "◇ Prediction";
        card.append(badge);
        card.append(el(doc, "p", "nur-map-field-value", text(row.statement, "")));
        // Confidence is shown as a range word, and certainty is impossible.
        card.append(el(
          doc, "p", "nur-map-row-meta",
          row.confidence === null || row.confidence === undefined
            ? "No confidence recorded · never certain"
            : `Confidence ${row.confidence} · never certain`,
        ));
        const assumptions = (row.assumptions as string[] | undefined) ?? [];
        if (assumptions.length) {
          card.append(el(doc, "p", "nur-map-row-meta", `Rests on: ${assumptions.join("; ")}`));
        }
        if (row.overdue_for_review) {
          card.append(el(
            doc, "p", "nur-map-row-meta",
            "Past its review date — anything resting on this rests on an unchecked assumption.",
          ));
        }
        if (row.resolution) {
          card.append(el(doc, "p", "nur-map-row-meta", `Outcome: ${String(row.resolution)}`));
        }
        into.append(card);
      }
    } else {
      into.append(el(doc, "p", "nur-map-empty", "NUR has made no prediction about this."));
    }

    // §17: this section is required and is never omitted.
    const doubt = el(doc, "div", "nur-map-doubt");
    doubt.dataset.mapDoubt = "true";
    doubt.append(el(doc, "p", "nur-map-doubt-label", "What NUR may be wrong about"));
    const kindWord = (KIND_WORD[node.kind] ?? node.kind).toLowerCase();
    doubt.append(el(
      doc, "p", "nur-map-field-value",
      node.kind === "BLOCKER" && node.data.basis === "NUR_INFERRED"
        ? "This blocker was inferred, not stated. NUR may have read a delay as an "
          + "obstacle when it was a choice."
        : `NUR sees this ${kindWord} only through what has been recorded. Anything you `
          + "have not written down is invisible here, so its place on the Map may be "
          + "more confident than the evidence deserves.",
    ));
    into.append(doubt);
  }

  function candidateCard(suggestion: Suggestion): HTMLElement {
    const card = el(doc, "div", "nur-map-candidate");
    card.dataset.mapCandidate = suggestion.id;
    const mark = el(doc, "p", "nur-map-candidate-mark");
    // A candidate is marked as a candidate, in words as well as by its dashes.
    mark.textContent = `◈ NUR suggests · ${suggestion.suggestion_type.replace(/_/g, " ").toLowerCase()}`;
    card.append(mark);
    card.append(el(doc, "p", "nur-map-field-value", suggestion.explanation));

    const doubt = el(doc, "div", "nur-map-doubt");
    doubt.append(el(doc, "p", "nur-map-doubt-label", "May be wrong about"));
    doubt.append(el(doc, "p", "nur-map-field-value", suggestion.may_be_wrong_about));
    card.append(doubt);

    const row = el(doc, "div", "nur-map-candidate-actions");
    const accept = capsule(doc, "Accept");
    accept.classList.add("nur-map-capsule-sm");
    accept.dataset.mapAccept = suggestion.id;
    accept.addEventListener("click", () => actions.accept(suggestion.id));
    const reject = capsule(doc, "Reject");
    reject.classList.add("nur-map-capsule-sm");
    reject.dataset.mapReject = suggestion.id;
    reject.addEventListener("click", () => actions.reject(suggestion.id, false));
    const never = capsule(doc, "Never suggest this kind");
    never.classList.add("nur-map-capsule-sm");
    never.addEventListener("click", () => actions.reject(suggestion.id, true));
    row.append(accept, reject, never);
    card.append(row);
    return card;
  }

  // ── paint ──────────────────────────────────────────────────────────────────

  function paint(): void {
    doc.getElementById(ROOT_ID)?.remove();
    const root = el(doc, "div");
    root.id = ROOT_ID;
    root.dataset.v197NativeAdjunct = "true";

    const shell = el(doc, "div", "nur-map-shell");
    // Exposed so a caller can wait for the graph rather than racing the first
    // paint, and so the loading state is observable rather than inferred.
    root.dataset.mapLoaded = state.loaded ? "true" : "false";
    if (isMobile && state.selected) shell.classList.add("is-mobile-detail");
    shell.append(mapHeader());

    if (state.error) {
      const banner = el(doc, "div", "nur-map-banner");
      banner.dataset.mapError = "true";
      banner.textContent = state.error;
      const retry = capsule(doc, "Retry");
      retry.classList.add("nur-map-capsule-sm");
      retry.addEventListener("click", () => { void loadGraph(); });
      banner.append(doc.createTextNode(" "));
      banner.append(retry);
      shell.append(banner);
    } else if (state.notice) {
      const banner = el(doc, "div", "nur-map-banner is-notice");
      banner.textContent = state.notice;
      shell.append(banner);
    }

    const zones = el(doc, "div", "nur-map-zones");
    zones.append(mapNavigator());
    if (state.mode === "paths") zones.append(mapPathsView());
    else if (state.mode === "decisions") zones.append(mapDecisionsView());
    // On a phone, Focus is a list. The galaxy is Visual mode, reached explicitly.
    else if (isMobile && state.mode === "focus") zones.append(mapMobileFocusList());
    else zones.append(mapCanvas());
    zones.append(mapDetailPanel());
    shell.append(zones);

    root.append(shell);
    root.append(createV197StarSeal(doc));
    host.append(root);
  }

  paint();
  await loadGraph();
  return true;
}
