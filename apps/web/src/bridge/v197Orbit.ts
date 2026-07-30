/**
 * Orbit — the relational world, rendered V197-native.
 *
 * Plain DOM and SVG through the bridge, not React. The §29 component tree is
 * preserved as the function decomposition below (`orbitHeader`, `orbitLeftRail`,
 * `orbitCanvas`, `orbitListView`, `orbitThreadsView`, `orbitDetailPanel` and the
 * tab renderers), because the architecture law is that the canonical V197
 * document owns the visible product and `#root` never appears on a product page.
 *
 * Everything displayed here comes from `/api/v1/orbit-*`. There is no seeded
 * person, no sample edge and no placeholder activity anywhere in this file: an
 * owner with an empty Orbit sees the empty state, because inventing relational
 * gravity would be the worst possible lie for this particular surface.
 *
 * The one rule that shapes the detail panel: a reading's *basis* is always
 * visible. A signal the owner stated and a signal NUR inferred are rendered with
 * different marks and different words, an inferred one always shows the evidence
 * it rests on and the evidence against it, and no card ever presents a guess as
 * a fact.
 */

import ORBIT_CSS from "../styles/v197-orbit.css?raw";
import { markV197HolographicWordmark } from "./v197Brand";
import { createV197StarSeal } from "./v197StarSeal";
import type { V197ApiClient } from "./v197ApiClient";

const ROOT_ID = "nur-orbit-root";
const STYLE_ID = "nur-orbit-style";

export const ORBIT_ROUTE = "/universe/orbits";

export type OrbitBand = "INNER" | "NEAR" | "OUTER" | "PERIPHERAL" | "DORMANT";

const BANDS: OrbitBand[] = ["INNER", "NEAR", "OUTER", "PERIPHERAL", "DORMANT"];

/** Ring radius as a fraction of the field's half-height, inner band nearest. */
const BAND_RADIUS: Record<OrbitBand, number> = {
  INNER: 0.22,
  NEAR: 0.4,
  OUTER: 0.58,
  PERIPHERAL: 0.76,
  DORMANT: 0.92,
};

/** Node radius per band. Controlled, so a score can never inflate a planet. */
const BAND_NODE_RADIUS: Record<OrbitBand, number> = {
  INNER: 15,
  NEAR: 12.5,
  OUTER: 10,
  PERIPHERAL: 8,
  DORMANT: 8,
};

const BAND_LABEL: Record<OrbitBand, string> = {
  INNER: "Inner",
  NEAR: "Near",
  OUTER: "Outer",
  PERIPHERAL: "Peripheral",
  DORMANT: "Dormant",
};

const SIGNAL_KINDS = ["CONNECTION", "TRUST", "MOMENTUM", "TENSION"] as const;

const BASIS_WORD: Record<string, string> = {
  USER_STATED: "You said this",
  OBSERVED: "Measured from activity",
  NUR_INFERRED: "NUR inferred this",
};

const THREAD_GROUPS: { status: string; label: string }[] = [
  { status: "ACTIVE", label: "Active" },
  { status: "WAITING_ON_YOU", label: "Waiting on you" },
  { status: "WAITING_ON_OTHERS", label: "Waiting on others" },
  { status: "CONSULTATION", label: "Consultation" },
  { status: "RESOLVED", label: "Resolved" },
  { status: "DORMANT", label: "Dormant" },
];

export interface OrbitPerson {
  id: string;
  display_name: string;
  handle: string | null;
  relationship_type: string | null;
  orbit_level: OrbitBand | null;
  orbit_level_suggestion: OrbitBand | null;
  orbit_level_suggestion_reason: string | null;
  relational_state: string | null;
  tags: string[];
  user_summary: string | null;
  nur_summary: string | null;
  avatar_ref: string | null;
  memory_allowed: boolean;
  inference_allowed: boolean;
  sharing_allowed: boolean;
  capsule_eligible: boolean;
  archived_at: string | null;
  last_interaction_at: string | null;
  privacy_scope: string;
}

export interface OrbitGroupRow {
  id: string;
  name: string;
  purpose: string | null;
  group_type: string;
  privacy_mode: string;
  shared_memory_enabled: boolean;
  group_nur_enabled: boolean;
  system_slug: string | null;
  archived_at: string | null;
  member_count: number;
}

export interface OrbitEdge {
  id: string;
  source_person_id: string;
  target_person_id: string | null;
  target_group_id: string | null;
  relationship_type: string | null;
  strength_user: number | null;
  activity_score: number;
  reciprocity_score: number;
  momentum_score: number;
  tension_score: number;
  confidence: number | null;
}

export interface OrbitLayoutRow {
  entity_type: "PERSON" | "GROUP";
  entity_id: string;
  x: number;
  y: number;
  pinned: boolean;
  collapsed: boolean;
}

export interface OrbitSignal {
  id: string;
  person_id: string;
  signal_kind: string;
  basis: string;
  value: number | null;
  confidence: number | null;
  evidence: unknown[];
  contradictory_evidence: unknown[];
}

export interface OrbitField {
  people: OrbitPerson[];
  groups: OrbitGroupRow[];
  relationships: OrbitEdge[];
  layout: OrbitLayoutRow[];
  thread_counts: Record<string, number>;
}

export interface OrbitThreadRow {
  id: string;
  person_id: string | null;
  group_id: string | null;
  topic: string;
  participants: unknown[];
  status: string;
  last_event_at: string | null;
  last_event_summary: string | null;
  open_decision: string | null;
  next_action: string | null;
  plan_id: string | null;
  system_slug: string | null;
}

type OrbitView = "orbit" | "list" | "threads";
type DetailTab = "overview" | "context" | "threads" | "plans" | "insights";

interface OrbitState {
  view: OrbitView;
  field: OrbitField;
  threads: OrbitThreadRow[];
  query: string;
  bandFilter: OrbitBand | "ALL" | "GROUPS";
  selected: { type: "PERSON" | "GROUP"; id: string } | null;
  tab: DetailTab;
  sort: "name" | "band" | "recent";
  signals: OrbitSignal[];
  context: Record<string, unknown>[];
  insights: Record<string, unknown>[];
  personThreads: OrbitThreadRow[];
  expandedWhy: string | null;
  error: string | null;
}

// ── small DOM helpers, matching the adjunct idiom ────────────────────────────

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

/** Every control in Orbit is a capsule. There is no boxed-button helper. */
function capsule(
  doc: Document, label: string, variant: "primary" | "default" | "quiet" | "destructive" = "default",
): HTMLButtonElement {
  const node = el(doc, "button", "nur-orbit-capsule", label);
  node.type = "button";
  if (variant === "primary") node.classList.add("is-primary");
  if (variant === "quiet") node.classList.add("is-quiet");
  if (variant === "destructive") node.classList.add("is-destructive");
  return node;
}

function chip(doc: Document, label: string, pressed: boolean, count?: number): HTMLButtonElement {
  const node = el(doc, "button", "nur-orbit-chip");
  node.type = "button";
  node.setAttribute("aria-pressed", pressed ? "true" : "false");
  node.append(doc.createTextNode(label));
  if (typeof count === "number") {
    node.append(el(doc, "span", "nur-orbit-count", String(count)));
  }
  return node;
}

function ensureStyle(doc: Document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = ORBIT_CSS;
  doc.head.append(style);
}

function bandOf(person: OrbitPerson): OrbitBand | "UNPLACED" {
  return person.orbit_level ?? "UNPLACED";
}

function activityOf(person: OrbitPerson): "active" | "stable" | "dormant" {
  if (person.archived_at || person.orbit_level === "DORMANT") return "dormant";
  if (!person.last_interaction_at) return "stable";
  const days = (Date.now() - new Date(person.last_interaction_at).getTime()) / 86_400_000;
  return days <= 14 ? "active" : days > 90 ? "dormant" : "stable";
}

/** Edge meaning from stored scores. Drives both hue and dash pattern. */
function edgeMeaning(edge: OrbitEdge): string {
  if (edge.tension_score >= 40) return "tense";
  if (edge.target_group_id) return "collaborative";
  if (edge.momentum_score >= 50) return "collaborative";
  if ((edge.strength_user ?? 0) >= 75) return "intense";
  if (edge.confidence !== null && edge.confidence < 0.4) return "uncertain";
  if (edge.activity_score <= 5) return "dormant";
  return "active";
}

function relativeDate(value: string | null): string {
  if (!value) return "No recorded activity";
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  const days = Math.floor((Date.now() - parsed.getTime()) / 86_400_000);
  if (days <= 0) return "Today";
  if (days === 1) return "Yesterday";
  if (days < 30) return `${days} days ago`;
  return parsed.toLocaleDateString();
}

// ── header ───────────────────────────────────────────────────────────────────

function orbitHeader(doc: Document, state: OrbitState, actions: Actions): HTMLElement {
  const header = el(doc, "header", "nur-orbit-header");

  const titleBlock = el(doc, "div");
  const title = el(doc, "h1", "nur-orbit-title", "Orbit");
  markV197HolographicWordmark(title);
  titleBlock.append(title);
  titleBlock.append(
    el(doc, "p", "nur-orbit-subtitle", "People, circles and relational gravity"),
  );
  header.append(titleBlock);

  const switcher = el(doc, "div", "nur-orbit-segmented");
  switcher.setAttribute("role", "tablist");
  switcher.setAttribute("aria-label", "Orbit view");
  for (const [view, label] of [
    ["orbit", "Orbit"], ["list", "List"], ["threads", "Threads"],
  ] as [OrbitView, string][]) {
    const tab = capsule(doc, label);
    tab.setAttribute("role", "tab");
    tab.setAttribute("aria-selected", state.view === view ? "true" : "false");
    tab.dataset.orbitView = view;
    tab.addEventListener("click", () => actions.setView(view));
    switcher.append(tab);
  }
  header.append(switcher);

  header.append(el(doc, "div", "nur-orbit-header-spacer"));

  const search = el(doc, "input", "nur-orbit-search");
  search.type = "search";
  search.placeholder = "Search people, groups, plans or threads";
  search.setAttribute("aria-label", "Search people, groups, plans or threads");
  search.value = state.query;
  search.addEventListener("input", () => actions.setQuery(search.value));
  header.append(search);

  const addPerson = capsule(doc, "✦ Add a person", "primary");
  addPerson.dataset.orbitAction = "add-person";
  addPerson.addEventListener("click", () => actions.addPerson());
  header.append(addPerson);

  const createGroup = capsule(doc, "Create Group");
  createGroup.dataset.orbitAction = "create-group";
  createGroup.addEventListener("click", () => actions.createGroup());
  header.append(createGroup);

  return header;
}

// ── left rail ────────────────────────────────────────────────────────────────

function orbitLeftRail(doc: Document, state: OrbitState, actions: Actions): HTMLElement {
  const rail = el(doc, "aside", "nur-orbit-rail");
  rail.setAttribute("aria-label", "Orbit filters");

  const people = state.field.people;
  const countIn = (band: OrbitBand) => people.filter((p) => p.orbit_level === band).length;

  const scopes = el(doc, "section", "nur-orbit-rail-section");
  scopes.append(el(doc, "h2", "nur-orbit-rail-heading", "Scopes"));
  const scopeChips = el(doc, "div", "nur-orbit-chips");
  const scopeDefs: [OrbitBand | "ALL" | "GROUPS", string, number][] = [
    ["ALL", "All", people.length],
    ["INNER", "Inner", countIn("INNER")],
    ["NEAR", "Near", countIn("NEAR")],
    ["OUTER", "Outer", countIn("OUTER")],
    ["PERIPHERAL", "Peripheral", countIn("PERIPHERAL")],
    ["DORMANT", "Dormant", countIn("DORMANT")],
    ["GROUPS", "Groups", state.field.groups.length],
  ];
  for (const [key, label, count] of scopeDefs) {
    const node = chip(doc, label, state.bandFilter === key, count);
    node.dataset.orbitScope = String(key);
    node.addEventListener("click", () => actions.setBandFilter(key));
    scopeChips.append(node);
  }
  scopes.append(scopeChips);
  rail.append(scopes);

  // Smart segments, each computed from real rows. A segment with nothing in it
  // shows zero rather than being hidden, so the owner can see it is empty.
  const segments = el(doc, "section", "nur-orbit-rail-section");
  segments.append(el(doc, "h2", "nur-orbit-rail-heading", "Segments"));
  const segChips = el(doc, "div", "nur-orbit-chips");
  const active = people.filter((p) => activityOf(p) === "active").length;
  const dormant = people.filter((p) => activityOf(p) === "dormant").length;
  const emerging = people.filter((p) => !p.orbit_level && !p.archived_at).length;
  const needsAttention = people.filter(
    (p) => p.relational_state === "TENSE" || p.relational_state === "DRIFTING"
      || p.orbit_level_suggestion !== null,
  ).length;
  for (const [label, count] of [
    ["Active now", active], ["Needs attention", needsAttention],
    ["Emerging", emerging], ["Dormant", dormant],
  ] as [string, number][]) {
    const node = chip(doc, label, false, count);
    node.disabled = count === 0;
    segChips.append(node);
  }
  segments.append(segChips);
  rail.append(segments);

  const create = el(doc, "section", "nur-orbit-rail-section");
  create.append(el(doc, "h2", "nur-orbit-rail-heading", "Build your Orbit"));
  const addBtn = capsule(doc, "✦ Add a person", "primary");
  addBtn.style.width = "100%";
  addBtn.addEventListener("click", () => actions.addPerson());
  const groupBtn = capsule(doc, "Create Group Orbit", "quiet");
  groupBtn.style.width = "100%";
  groupBtn.style.marginTop = "6px";
  groupBtn.addEventListener("click", () => actions.createGroup());
  // Import is declared and honestly disabled: suggesting people from Talk and
  // Journal requires an approval step that does not exist yet, and adding
  // inferred people without it is exactly what the spec forbids.
  const importBtn = capsule(doc, "Import from NUR context", "quiet");
  importBtn.style.width = "100%";
  importBtn.style.marginTop = "6px";
  importBtn.disabled = true;
  importBtn.title =
    "Not connected yet. Importing would add people NUR inferred from Talk and Journal, "
    + "and that needs an explicit approval step before anything is stored.";
  create.append(addBtn, groupBtn, importBtn);
  rail.append(create);

  return rail;
}

// ── the field ────────────────────────────────────────────────────────────────

function orbitCanvas(doc: Document, state: OrbitState, actions: Actions): HTMLElement {
  const surface = el(doc, "section", "nur-orbit-field-surface");

  const visible = visiblePeople(state);
  if (visible.length === 0 && state.field.groups.length === 0) {
    surface.append(orbitEmptyState(doc, state, actions));
    return surface;
  }

  const width = 900;
  const height = 620;
  const cx = width / 2;
  const cy = height / 2;
  const canvas = svg(doc, "svg", {
    class: "nur-orbit-canvas",
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: "xMidYMid meet",
    role: "img",
  });
  canvas.setAttribute(
    "aria-label",
    `Relational field: ${visible.length} people, ${state.field.groups.length} groups. `
    + "A parallel list of every node is available in List view.",
  );
  if (state.selected) canvas.dataset.hasSelection = "true";

  // Layer 1 — deep space. A fixed, deterministic scatter: a random field would
  // shift on every re-render and read as flicker.
  const stars = svg(doc, "g", {});
  for (let i = 0; i < 90; i += 1) {
    const t = (i * 2654435761) % 100000;
    stars.append(svg(doc, "circle", {
      cx: (t % width), cy: ((t * 7) % height),
      r: i % 9 === 0 ? 1.1 : 0.6,
      fill: "rgba(255,248,223,0.22)",
    }));
  }
  canvas.append(stars);

  // Layer 2 — orbit geometry.
  const rings = svg(doc, "g", {});
  for (const band of BANDS) {
    const rx = BAND_RADIUS[band] * (width / 2) * 0.92;
    const ry = BAND_RADIUS[band] * (height / 2) * 0.92;
    const ring = svg(doc, "ellipse", { cx, cy, rx, ry, class: "nur-orbit-ring" });
    ring.setAttribute("data-band", band);
    rings.append(ring);
    const label = svg(doc, "text", {
      x: cx, y: cy - ry - 5, class: "nur-orbit-ring-label", "text-anchor": "middle",
    });
    label.textContent = BAND_LABEL[band];
    rings.append(label);
  }
  canvas.append(rings);

  // Position every node, honouring a saved layout where one exists.
  const layoutBy = new Map(state.field.layout.map((l) => [`${l.entity_type}:${l.entity_id}`, l]));
  const positions = new Map<string, { x: number; y: number }>();
  const byBand = new Map<OrbitBand, OrbitPerson[]>();
  for (const person of visible) {
    const band = (person.orbit_level ?? "PERIPHERAL") as OrbitBand;
    byBand.set(band, [...(byBand.get(band) ?? []), person]);
  }
  for (const band of BANDS) {
    const members = byBand.get(band) ?? [];
    members.forEach((person, index) => {
      const saved = layoutBy.get(`PERSON:${person.id}`);
      if (saved) {
        positions.set(person.id, { x: cx + saved.x, y: cy + saved.y });
        return;
      }
      const angle = (index / Math.max(members.length, 1)) * Math.PI * 2 - Math.PI / 2;
      positions.set(person.id, {
        x: cx + Math.cos(angle) * BAND_RADIUS[band] * (width / 2) * 0.92,
        y: cy + Math.sin(angle) * BAND_RADIUS[band] * (height / 2) * 0.92,
      });
    });
  }
  state.field.groups.forEach((group, index) => {
    const saved = layoutBy.get(`GROUP:${group.id}`);
    const angle = (index / Math.max(state.field.groups.length, 1)) * Math.PI * 2 + Math.PI / 4;
    positions.set(group.id, saved
      ? { x: cx + saved.x, y: cy + saved.y }
      : {
          x: cx + Math.cos(angle) * 0.66 * (width / 2),
          y: cy + Math.sin(angle) * 0.66 * (height / 2),
        });
  });

  // Layer 3 — relationships.
  const edges = svg(doc, "g", {});
  const connected = new Set<string>();
  for (const edge of state.field.relationships) {
    const from = positions.get(edge.source_person_id);
    const targetId = edge.target_person_id ?? edge.target_group_id ?? "";
    const to = positions.get(targetId);
    if (!from || !to) continue;
    const line = svg(doc, "line", {
      x1: from.x, y1: from.y, x2: to.x, y2: to.y, class: "nur-orbit-edge",
    });
    line.setAttribute("data-meaning", edgeMeaning(edge));
    const touchesSelection = state.selected
      && (edge.source_person_id === state.selected.id || targetId === state.selected.id);
    if (touchesSelection) {
      line.setAttribute("data-connected", "true");
      connected.add(edge.source_person_id);
      connected.add(targetId);
    }
    edges.append(line);
  }
  canvas.append(edges);

  // Layer 4 — the You anchor. Restrained: a small NUR seal, not a giant avatar.
  const anchor = svg(doc, "g", {});
  anchor.append(svg(doc, "circle", {
    cx, cy, r: 30, fill: "rgba(255,211,90,0.05)",
    stroke: "rgba(255,211,90,0.28)", "stroke-width": 1,
  }));
  anchor.append(svg(doc, "circle", {
    cx, cy, r: 15, fill: "rgba(255,248,223,0.9)",
  }));
  anchor.append(svg(doc, "circle", {
    cx, cy, r: 22, fill: "none",
    stroke: "rgba(33,232,255,0.24)", "stroke-width": 1, "stroke-dasharray": "2 8",
  }));
  const anchorLabel = svg(doc, "text", {
    x: cx, y: cy + 48, class: "nur-orbit-anchor-label", "text-anchor": "middle",
  });
  anchorLabel.textContent = "You";
  anchor.append(anchorLabel);
  const anchorTitle = svg(doc, "title", {});
  anchorTitle.textContent = "Your relational center";
  anchor.append(anchorTitle);
  canvas.append(anchor);

  // Person and group nodes.
  const nodes = svg(doc, "g", {});
  for (const person of visible) {
    const at = positions.get(person.id);
    if (!at) continue;
    const band = (person.orbit_level ?? "PERIPHERAL") as OrbitBand;
    const radius = BAND_NODE_RADIUS[band];
    const group = svg(doc, "g", { class: "nur-orbit-node" });
    group.dataset.orbitNode = person.id;
    group.dataset.activity = activityOf(person);
    if (state.selected?.id === person.id) group.dataset.selected = "true";
    if (connected.has(person.id)) group.dataset.connected = "true";

    group.append(svg(doc, "circle", {
      cx: at.x, cy: at.y, r: radius + 7, class: "nur-orbit-node-halo",
      fill: "rgba(255,211,90,0.09)",
    }));
    group.append(svg(doc, "circle", {
      cx: at.x, cy: at.y, r: radius, class: "nur-orbit-node-core",
      fill: "rgba(3,3,7,0.9)",
      stroke: person.relational_state === "TENSE"
        ? "rgba(255,82,111,0.7)"
        : person.inference_allowed ? "rgba(193,107,255,0.6)" : "rgba(255,211,90,0.6)",
      "stroke-width": band === "INNER" ? 2 : 1.2,
    }));
    const initials = person.display_name.trim().slice(0, 2).toUpperCase();
    const text = svg(doc, "text", {
      x: at.x, y: at.y + 3.5, "text-anchor": "middle",
      class: "nur-orbit-node-label",
    });
    text.textContent = initials;
    group.append(text);
    const label = svg(doc, "text", {
      x: at.x, y: at.y + radius + 14, "text-anchor": "middle",
      class: "nur-orbit-node-label",
    });
    label.textContent = person.display_name;
    group.append(label);
    const tip = svg(doc, "title", {});
    tip.textContent =
      `${person.display_name} · ${person.relationship_type ?? "Relationship not set"} · `
      + `${person.orbit_level ? BAND_LABEL[person.orbit_level] + " Orbit" : "Not yet placed"}`;
    group.append(tip);
    group.addEventListener("click", () => actions.select("PERSON", person.id));
    nodes.append(group);
  }

  // Groups render as small constellations, never as large person nodes.
  for (const groupRow of state.field.groups) {
    const at = positions.get(groupRow.id);
    if (!at) continue;
    const node = svg(doc, "g", { class: "nur-orbit-node" });
    node.dataset.orbitNode = groupRow.id;
    node.dataset.orbitGroup = "true";
    if (state.selected?.id === groupRow.id) node.dataset.selected = "true";
    node.append(svg(doc, "circle", {
      cx: at.x, cy: at.y, r: 26, class: "nur-orbit-node-halo",
      fill: "rgba(33,232,255,0.05)",
    }));
    const particles = Math.min(Math.max(groupRow.member_count, 3), 7);
    for (let i = 0; i < particles; i += 1) {
      const angle = (i / particles) * Math.PI * 2;
      node.append(svg(doc, "circle", {
        cx: at.x + Math.cos(angle) * 15, cy: at.y + Math.sin(angle) * 15, r: 2.4,
        fill: "rgba(255,248,223,0.7)",
      }));
    }
    node.append(svg(doc, "circle", {
      cx: at.x, cy: at.y, r: 5, fill: "rgba(255,211,90,0.85)",
    }));
    const label = svg(doc, "text", {
      x: at.x, y: at.y + 40, "text-anchor": "middle", class: "nur-orbit-node-label",
    });
    label.textContent = `${groupRow.name} · ${groupRow.member_count}`;
    node.append(label);
    const tip = svg(doc, "title", {});
    tip.textContent =
      `${groupRow.name} · ${groupRow.member_count} members · ${groupRow.purpose ?? "No purpose set"} · `
      + `Group NUR ${groupRow.group_nur_enabled ? "active" : "off"}`;
    node.append(tip);
    node.addEventListener("click", () => actions.select("GROUP", groupRow.id));
    nodes.append(node);
  }
  canvas.append(nodes);
  surface.append(canvas);
  return surface;
}

function orbitEmptyState(doc: Document, _state: OrbitState, actions: Actions): HTMLElement {
  const empty = el(doc, "div", "nur-orbit-empty");
  const seal = createV197StarSeal(doc, 32, true);
  empty.append(seal);
  empty.append(el(doc, "p", undefined,
    "Your Orbit begins with one person, one signal, one shared field."));
  const row = el(doc, "div", "nur-orbit-empty-actions");
  const add = capsule(doc, "✦ Add first person", "primary");
  add.addEventListener("click", () => actions.addPerson());
  const group = capsule(doc, "Create a group");
  group.addEventListener("click", () => actions.createGroup());
  row.append(add, group);
  empty.append(row);
  return empty;
}

// ── list view ────────────────────────────────────────────────────────────────

function visiblePeople(state: OrbitState): OrbitPerson[] {
  const query = state.query.trim().toLowerCase();
  let rows = state.field.people;
  if (state.bandFilter !== "ALL" && state.bandFilter !== "GROUPS") {
    rows = rows.filter((p) => p.orbit_level === state.bandFilter);
  }
  if (state.bandFilter === "GROUPS") rows = [];
  if (query) {
    rows = rows.filter((p) =>
      p.display_name.toLowerCase().includes(query)
      || (p.relationship_type ?? "").toLowerCase().includes(query)
      || p.tags.some((tag) => String(tag).toLowerCase().includes(query)));
  }
  const order = (p: OrbitPerson) => (p.orbit_level ? BANDS.indexOf(p.orbit_level) : BANDS.length);
  return [...rows].sort((a, b) => {
    if (state.sort === "band") return order(a) - order(b);
    if (state.sort === "recent") {
      return (b.last_interaction_at ?? "").localeCompare(a.last_interaction_at ?? "");
    }
    return a.display_name.localeCompare(b.display_name);
  });
}

function orbitListView(doc: Document, state: OrbitState, actions: Actions): HTMLElement {
  const surface = el(doc, "section", "nur-orbit-field-surface");
  const rows = visiblePeople(state);

  if (rows.length === 0 && state.field.groups.length === 0) {
    surface.append(orbitEmptyState(doc, state, actions));
    return surface;
  }

  const list = el(doc, "div", "nur-orbit-list");
  list.setAttribute("role", "table");
  list.setAttribute("aria-label", "Orbit people");

  const head = el(doc, "div", "nur-orbit-list-head");
  head.setAttribute("role", "row");
  for (const [label, sort] of [
    ["Person", "name"], ["Orbit", "band"], ["Relationship", null],
    ["Activity", "recent"], ["Next move", null], ["Privacy", null],
  ] as [string, OrbitState["sort"] | null][]) {
    const cell = el(doc, "div");
    cell.setAttribute("role", "columnheader");
    if (sort) {
      const button = el(doc, "button", undefined, label);
      button.type = "button";
      button.addEventListener("click", () => actions.setSort(sort));
      cell.append(button);
    } else {
      cell.textContent = label;
    }
    head.append(cell);
  }
  list.append(head);

  for (const person of rows) {
    const row = el(doc, "button", "nur-orbit-row");
    row.type = "button";
    row.setAttribute("role", "row");
    row.dataset.orbitRow = person.id;
    if (state.selected?.id === person.id) row.setAttribute("aria-selected", "true");

    const name = el(doc, "div", "nur-orbit-row-name");
    name.append(el(doc, "strong", undefined, person.display_name));
    if (person.orbit_level_suggestion) {
      const flag = el(doc, "span", "nur-orbit-privacy", "· suggestion");
      flag.title = person.orbit_level_suggestion_reason ?? "";
      name.append(flag);
    }
    row.append(name);

    const band = el(doc, "div");
    const pill = el(doc, "span", "nur-orbit-band",
      person.orbit_level ? BAND_LABEL[person.orbit_level] : "Unplaced");
    pill.dataset.band = bandOf(person);
    band.append(pill);
    row.append(band);

    row.append(el(doc, "div", undefined, person.relationship_type ?? "Not set"));
    row.append(el(doc, "div", undefined, relativeDate(person.last_interaction_at)));
    row.append(el(doc, "div", undefined,
      person.relational_state ? person.relational_state.toLowerCase() : "No move recorded"));

    const privacy = el(doc, "div");
    const mark = el(doc, "span", "nur-orbit-privacy",
      person.sharing_allowed ? "Shareable" : "Private only");
    mark.dataset.shared = person.sharing_allowed ? "true" : "false";
    privacy.append(mark);
    row.append(privacy);

    row.addEventListener("click", () => actions.select("PERSON", person.id));
    list.append(row);
  }

  for (const group of state.field.groups) {
    const row = el(doc, "button", "nur-orbit-row");
    row.type = "button";
    row.setAttribute("role", "row");
    row.dataset.orbitRow = group.id;
    if (state.selected?.id === group.id) row.setAttribute("aria-selected", "true");
    const name = el(doc, "div", "nur-orbit-row-name");
    name.append(el(doc, "strong", undefined, group.name));
    name.append(el(doc, "span", "nur-orbit-privacy", `· ${group.member_count} members`));
    row.append(name);
    const band = el(doc, "div");
    const pill = el(doc, "span", "nur-orbit-band", "Group");
    pill.dataset.band = "UNPLACED";
    band.append(pill);
    row.append(band);
    row.append(el(doc, "div", undefined, group.group_type.toLowerCase()));
    row.append(el(doc, "div", undefined, group.purpose ?? "No purpose set"));
    row.append(el(doc, "div", undefined,
      group.group_nur_enabled ? "Group NUR active" : "Group NUR off"));
    const privacy = el(doc, "div");
    const mark = el(doc, "span", "nur-orbit-privacy", group.privacy_mode.replace(/_/g, " ").toLowerCase());
    mark.dataset.shared = group.privacy_mode === "PRIVATE_ORGANIZER" ? "false" : "true";
    privacy.append(mark);
    row.append(privacy);
    row.addEventListener("click", () => actions.select("GROUP", group.id));
    list.append(row);
  }

  surface.append(list);
  return surface;
}

// ── threads view ─────────────────────────────────────────────────────────────

function orbitThreadsView(doc: Document, state: OrbitState, actions: Actions): HTMLElement {
  const surface = el(doc, "section", "nur-orbit-field-surface");
  const list = el(doc, "div", "nur-orbit-list");

  if (state.threads.length === 0) {
    const empty = el(doc, "div", "nur-orbit-empty");
    empty.append(el(doc, "p", undefined,
      "No relational threads yet. A thread appears when a conversation, decision "
      + "or shared plan is left open with someone."));
    const add = capsule(doc, "✦ Add a person", "primary");
    add.addEventListener("click", () => actions.addPerson());
    const row = el(doc, "div", "nur-orbit-empty-actions");
    row.append(add);
    empty.append(row);
    surface.append(empty);
    return surface;
  }

  const nameFor = (thread: OrbitThreadRow): string => {
    if (thread.person_id) {
      return state.field.people.find((p) => p.id === thread.person_id)?.display_name
        ?? "Unknown person";
    }
    if (thread.group_id) {
      return state.field.groups.find((g) => g.id === thread.group_id)?.name ?? "Unknown group";
    }
    return "Unattributed";
  };

  for (const bucket of THREAD_GROUPS) {
    const inBucket = state.threads.filter((t) => t.status === bucket.status);
    if (inBucket.length === 0) continue;
    const section = el(doc, "section", "nur-orbit-rail-section");
    section.append(el(doc, "h2", "nur-orbit-rail-heading",
      `${bucket.label} · ${inBucket.length}`));
    for (const thread of inBucket) {
      const card = el(doc, "div", "nur-orbit-item");
      card.append(el(doc, "strong", undefined, thread.topic));
      card.append(el(doc, "div", "nur-orbit-item-meta",
        `${nameFor(thread)} · ${relativeDate(thread.last_event_at)}`));
      if (thread.open_decision) {
        card.append(el(doc, "div", "nur-orbit-item-meta",
          `Open decision: ${thread.open_decision}`));
      }
      if (thread.next_action) {
        card.append(el(doc, "div", "nur-orbit-item-meta", `Next: ${thread.next_action}`));
      }
      section.append(card);
    }
    list.append(section);
  }
  surface.append(list);
  return surface;
}

// ── detail panel ─────────────────────────────────────────────────────────────

function orbitDetailPanel(doc: Document, state: OrbitState, actions: Actions): HTMLElement {
  const panel = el(doc, "aside", "nur-orbit-detail");
  panel.setAttribute("aria-label", "Orbit detail");
  panel.setAttribute("role", "region");

  if (!state.selected) {
    panel.append(el(doc, "p", "nur-orbit-detail-empty",
      "Select a person or group to explore its Orbit."));
    return panel;
  }

  if (state.selected.type === "GROUP") {
    const group = state.field.groups.find((g) => g.id === state.selected?.id);
    if (!group) {
      panel.append(el(doc, "p", "nur-orbit-detail-empty", "That group is no longer here."));
      return panel;
    }
    panel.append(el(doc, "h2", "nur-orbit-detail-name", group.name));
    panel.append(el(doc, "p", "nur-orbit-detail-meta",
      `${group.member_count} members · ${group.privacy_mode.replace(/_/g, " ").toLowerCase()}`));
    if (group.purpose) panel.append(el(doc, "p", "nur-orbit-note", group.purpose));

    const actionsRow = el(doc, "div", "nur-orbit-actions");
    const openNur = capsule(doc, "Open Group NUR", "primary");
    if (!group.group_nur_enabled) {
      // Honestly disabled with the reason, rather than a button that misleads.
      openNur.disabled = true;
      openNur.title =
        "Group NUR is off for this circle. It needs a shared-context privacy mode, "
        + "because a shared assistant must not read context no member agreed to share.";
    } else {
      openNur.title = "Group NUR workspace is not built yet.";
      openNur.disabled = true;
    }
    actionsRow.append(openNur);
    panel.append(actionsRow);
    panel.append(el(doc, "p", "nur-orbit-note",
      group.group_nur_enabled
        ? "Group NUR is enabled for this circle. The shared workspace itself is not built yet."
        : "Enable a shared-context privacy mode to allow Group NUR."));
    return panel;
  }

  const person = state.field.people.find((p) => p.id === state.selected?.id);
  if (!person) {
    panel.append(el(doc, "p", "nur-orbit-detail-empty", "That person is no longer here."));
    return panel;
  }

  panel.append(el(doc, "h2", "nur-orbit-detail-name", person.display_name));
  panel.append(el(doc, "p", "nur-orbit-detail-meta",
    [
      person.relationship_type ?? "Relationship not set",
      person.orbit_level ? `${BAND_LABEL[person.orbit_level]} Orbit` : "Not yet placed",
      person.sharing_allowed ? "Shareable" : "Private context",
    ].join(" · ")));

  // A pending suggestion is shown with its reason and both answers, never applied.
  if (person.orbit_level_suggestion) {
    const box = el(doc, "div", "nur-orbit-why");
    box.append(el(doc, "div", undefined,
      `Suggested move to ${BAND_LABEL[person.orbit_level_suggestion]} Orbit.`));
    box.append(el(doc, "div", "nur-orbit-item-meta",
      person.orbit_level_suggestion_reason ?? ""));
    const row = el(doc, "div", "nur-orbit-actions");
    const accept = capsule(doc, "Accept", "quiet");
    accept.addEventListener(
      "click", () => actions.setBand(person.id, person.orbit_level_suggestion as OrbitBand),
    );
    const keep = capsule(doc, "Keep as is", "quiet");
    keep.addEventListener(
      "click", () => actions.setBand(person.id, person.orbit_level ?? "PERIPHERAL"),
    );
    row.append(accept, keep);
    box.append(row);
    panel.append(box);
  }

  const primary = el(doc, "div", "nur-orbit-actions");
  for (const [label, hint] of [
    ["Open Talk", "Talk does not yet accept a person as context."],
    ["Add Context", "Linking existing context from this panel is not built yet."],
    ["Start Plan", "Creating a shared plan from Orbit is not built yet."],
  ]) {
    const button = capsule(doc, label, label === "Open Talk" ? "primary" : "default");
    button.disabled = true;
    button.title = hint;
    primary.append(button);
  }
  const archive = capsule(doc, "Archive", "destructive");
  archive.addEventListener("click", () => actions.archive(person.id));
  primary.append(archive);
  panel.append(primary);

  const tabs = el(doc, "div", "nur-orbit-tabs");
  tabs.setAttribute("role", "tablist");
  for (const [tab, label] of [
    ["overview", "Overview"], ["context", "Shared Context"], ["threads", "Threads"],
    ["plans", "Plans"], ["insights", "Insights"],
  ] as [DetailTab, string][]) {
    const node = el(doc, "button", "nur-orbit-tab", label);
    node.type = "button";
    node.setAttribute("role", "tab");
    node.setAttribute("aria-selected", state.tab === tab ? "true" : "false");
    node.dataset.orbitTab = tab;
    node.addEventListener("click", () => actions.setTab(tab));
    tabs.append(node);
  }
  panel.append(tabs);

  if (state.tab === "overview") panel.append(overviewTab(doc, state, person, actions));
  if (state.tab === "context") panel.append(contextTab(doc, state));
  if (state.tab === "threads") panel.append(threadsTab(doc, state));
  if (state.tab === "plans") panel.append(plansTab(doc));
  if (state.tab === "insights") panel.append(insightsTab(doc, state));

  return panel;
}

function overviewTab(
  doc: Document, state: OrbitState, person: OrbitPerson, actions: Actions,
): HTMLElement {
  const wrap = el(doc, "div");

  if (person.user_summary) {
    const box = el(doc, "div", "nur-orbit-item");
    box.append(el(doc, "div", undefined, person.user_summary));
    box.append(el(doc, "div", "nur-orbit-item-meta", "Written by you"));
    wrap.append(box);
  }
  if (person.nur_summary) {
    const box = el(doc, "div", "nur-orbit-item");
    box.append(el(doc, "div", undefined, person.nur_summary));
    box.append(el(doc, "div", "nur-orbit-item-meta", "NUR observation, not your words"));
    wrap.append(box);
  }

  for (const kind of SIGNAL_KINDS) {
    const matching = state.signals.filter((s) => s.signal_kind === kind);
    const card = el(doc, "div", "nur-orbit-signal");
    const top = el(doc, "div", "nur-orbit-signal-top");
    top.append(el(doc, "span", "nur-orbit-signal-name", kind.toLowerCase()));
    const best = matching.find((s) => s.basis === "USER_STATED") ?? matching[0];
    top.append(el(doc, "span", "nur-orbit-signal-value",
      best?.value !== null && best?.value !== undefined ? String(best.value) : "—"));
    card.append(top);

    if (!best) {
      card.append(el(doc, "div", "nur-orbit-item-meta", "Nothing recorded"));
      wrap.append(card);
      continue;
    }

    // Every basis present is shown. A stated reading and an inferred one are
    // different claims and neither is allowed to stand in for the other.
    for (const signal of matching) {
      const badge = el(doc, "span", "nur-orbit-basis", BASIS_WORD[signal.basis] ?? signal.basis);
      badge.dataset.basis = signal.basis;
      card.append(badge);
    }

    const why = capsule(doc, "Why is NUR showing this?", "quiet");
    why.dataset.orbitWhy = kind;
    why.setAttribute("aria-expanded", state.expandedWhy === kind ? "true" : "false");
    why.addEventListener("click", () => actions.toggleWhy(kind));
    card.append(why);

    if (state.expandedWhy === kind) {
      const box = el(doc, "div", "nur-orbit-why");
      for (const signal of matching) {
        box.append(el(doc, "div", "nur-orbit-item-meta",
          `${BASIS_WORD[signal.basis] ?? signal.basis}`
          + (signal.confidence !== null ? ` · confidence ${signal.confidence}` : "")));
        const evidence = signal.evidence ?? [];
        if (evidence.length) {
          const list = el(doc, "ul");
          for (const item of evidence) {
            list.append(el(doc, "li", undefined, JSON.stringify(item)));
          }
          box.append(list);
        } else if (signal.basis === "USER_STATED") {
          box.append(el(doc, "div", undefined, "You stated this directly."));
        }
        const against = signal.contradictory_evidence ?? [];
        if (against.length) {
          const doubt = el(doc, "div", "nur-orbit-why-doubt");
          doubt.append(el(doc, "div", undefined, "Evidence against this reading:"));
          const list = el(doc, "ul");
          for (const item of against) list.append(el(doc, "li", undefined, JSON.stringify(item)));
          doubt.append(list);
          box.append(doubt);
        }
      }
      if (matching.some((s) => s.basis === "NUR_INFERRED")) {
        box.append(el(doc, "div", "nur-orbit-why-doubt",
          "NUR may be overgeneralizing from a small number of interactions. "
          + "Review the evidence before treating this as settled."));
      }
      card.append(box);
    }
    wrap.append(card);
  }

  if (!person.inference_allowed) {
    wrap.append(el(doc, "p", "nur-orbit-note",
      "Inference is off for this person, so NUR records only what you state or what "
      + "activity measures. Nothing here is a guess."));
  }
  return wrap;
}

function contextTab(doc: Document, state: OrbitState): HTMLElement {
  const wrap = el(doc, "div");
  if (state.context.length === 0) {
    wrap.append(el(doc, "p", "nur-orbit-note",
      "No context is linked to this person yet."));
    return wrap;
  }
  for (const link of state.context) {
    const card = el(doc, "div", "nur-orbit-item");
    card.append(el(doc, "strong", undefined, String(link.source_type ?? "Context")));
    if (link.link_reason) {
      card.append(el(doc, "div", undefined, String(link.link_reason)));
    }
    card.append(el(doc, "div", "nur-orbit-item-meta",
      `${String(link.visibility_scope ?? "PRIVATE").replace(/_/g, " ").toLowerCase()} · `
      + relativeDate(String(link.created_at ?? ""))));
    wrap.append(card);
  }
  return wrap;
}

function threadsTab(doc: Document, state: OrbitState): HTMLElement {
  const wrap = el(doc, "div");
  if (state.personThreads.length === 0) {
    wrap.append(el(doc, "p", "nur-orbit-note", "No open threads with this person."));
    return wrap;
  }
  for (const thread of state.personThreads) {
    const card = el(doc, "div", "nur-orbit-item");
    card.append(el(doc, "strong", undefined, thread.topic));
    card.append(el(doc, "div", "nur-orbit-item-meta",
      `${thread.status.replace(/_/g, " ").toLowerCase()} · ${relativeDate(thread.last_event_at)}`));
    if (thread.next_action) {
      card.append(el(doc, "div", "nur-orbit-item-meta", `Next: ${thread.next_action}`));
    }
    wrap.append(card);
  }
  return wrap;
}

function plansTab(doc: Document): HTMLElement {
  const wrap = el(doc, "div");
  // Declared and honest: shared plans are a real object elsewhere in NUR, but
  // nothing links a plan to a person yet, so this shows no invented progress.
  wrap.append(el(doc, "p", "nur-orbit-note",
    "Shared plans are not linked to people yet. When a plan names a participant it "
    + "will appear here with its owner, milestones and Timeline connection."));
  return wrap;
}

function insightsTab(doc: Document, state: OrbitState): HTMLElement {
  const wrap = el(doc, "div");
  if (state.insights.length === 0) {
    wrap.append(el(doc, "p", "nur-orbit-note",
      "No relational insights yet. NUR records one only when it can show the evidence "
      + "behind it and say where it might be wrong."));
    return wrap;
  }
  for (const insight of state.insights) {
    const card = el(doc, "div", "nur-orbit-item");
    card.append(el(doc, "strong", undefined, String(insight.observation ?? "")));
    const evidence = (insight.evidence_refs as unknown[]) ?? [];
    if (evidence.length) {
      const list = el(doc, "ul");
      for (const item of evidence) list.append(el(doc, "li", undefined, JSON.stringify(item)));
      card.append(list);
    }
    if (insight.confidence !== null && insight.confidence !== undefined) {
      card.append(el(doc, "div", "nur-orbit-item-meta", `Confidence ${insight.confidence}`));
    }
    if (insight.alternative_interpretation) {
      card.append(el(doc, "div", "nur-orbit-item-meta",
        `Alternative reading: ${insight.alternative_interpretation}`));
    }
    if (insight.recommended_move) {
      card.append(el(doc, "div", "nur-orbit-item-meta",
        `Suggested move: ${insight.recommended_move}`));
    }
    // Always last and always present — the schema will not store an insight
    // without it, so it can be rendered unconditionally.
    card.append(el(doc, "div", "nur-orbit-why-doubt",
      `What NUR may be wrong about: ${String(insight.may_be_wrong_about ?? "")}`));
    wrap.append(card);
  }
  return wrap;
}

// ── controller ───────────────────────────────────────────────────────────────

interface Actions {
  setView(view: OrbitView): void;
  setQuery(query: string): void;
  setBandFilter(band: OrbitBand | "ALL" | "GROUPS"): void;
  setSort(sort: OrbitState["sort"]): void;
  select(type: "PERSON" | "GROUP", id: string): void;
  setTab(tab: DetailTab): void;
  toggleWhy(kind: string): void;
  setBand(personId: string, band: OrbitBand): void;
  archive(personId: string): void;
  addPerson(): void;
  createGroup(): void;
}

const EMPTY_FIELD: OrbitField = {
  people: [], groups: [], relationships: [], layout: [], thread_counts: {},
};

/**
 * Render the Orbit surface for `/universe/orbits`.
 *
 * Returns false for any other route, so the caller can fall through to the
 * canonical V197 document exactly as the other adjuncts do.
 */
export async function renderV197Orbit(
  doc: Document, route: string, api: V197ApiClient,
): Promise<boolean> {
  if (route !== ORBIT_ROUTE) {
    doc.getElementById(ROOT_ID)?.remove();
    return false;
  }

  ensureStyle(doc);

  const state: OrbitState = {
    view: doc.defaultView && doc.defaultView.innerWidth <= 900 ? "list" : "orbit",
    field: EMPTY_FIELD,
    threads: [],
    query: "",
    bandFilter: "ALL",
    selected: null,
    tab: "overview",
    sort: "band",
    signals: [],
    context: [],
    insights: [],
    personThreads: [],
    expandedWhy: null,
    error: null,
  };

  const actions: Actions = {
    setView(view) { state.view = view; paint(); },
    setQuery(query) { state.query = query; paint(); },
    setBandFilter(band) { state.bandFilter = band; paint(); },
    setSort(sort) { state.sort = sort; paint(); },
    setTab(tab) { state.tab = tab; paint(); },
    toggleWhy(kind) { state.expandedWhy = state.expandedWhy === kind ? null : kind; paint(); },
    select(type, id) {
      state.selected = { type, id };
      state.tab = "overview";
      state.expandedWhy = null;
      state.signals = [];
      state.context = [];
      state.insights = [];
      state.personThreads = [];
      paint();
      if (type === "PERSON") void loadPerson(id);
    },
    setBand(personId, band) {
      void mutate(() => api.patch(`/orbit-entities/${personId}`, { orbit_level: band }));
    },
    archive(personId) {
      void mutate(() => api.post(`/orbit-entities/${personId}/archive`, {}));
    },
    addPerson() {
      const view = doc.defaultView;
      const name = view ? view.prompt("Who should join your Orbit?")?.trim() : null;
      if (!name) return;
      void mutate(() => api.post("/orbits/people", { display_name: name }));
    },
    createGroup() {
      const view = doc.defaultView;
      const name = view ? view.prompt("Name this circle")?.trim() : null;
      if (!name) return;
      void mutate(() => api.post("/orbit-groups", { name }));
    },
  };

  async function mutate(run: () => Promise<unknown>): Promise<void> {
    try {
      await run();
      state.error = null;
      await loadField();
    } catch (error) {
      // The server's own refusal text is shown rather than a generic failure:
      // "this person is private-reference only" is the useful sentence.
      state.error = error instanceof Error ? error.message : "That did not work.";
      paint();
    }
  }

  async function loadField(): Promise<void> {
    try {
      const [field, threads] = await Promise.all([
        api.get<OrbitField>("/orbit-field"),
        api.get<OrbitThreadRow[]>("/orbit-threads"),
      ]);
      state.field = field ?? EMPTY_FIELD;
      state.threads = threads ?? [];
      state.error = null;
    } catch (error) {
      state.field = EMPTY_FIELD;
      state.error = error instanceof Error ? error.message : "Orbit could not load.";
    }
    paint();
  }

  async function loadPerson(personId: string): Promise<void> {
    try {
      const [signals, context, insights, threads] = await Promise.all([
        api.get<OrbitSignal[]>(`/orbit-entities/${personId}/signals`),
        api.get<Record<string, unknown>[]>(`/orbit-entities/${personId}/context`),
        api.get<Record<string, unknown>[]>(`/orbit-entities/${personId}/insights`),
        api.get<OrbitThreadRow[]>(`/orbit-entities/${personId}/threads`),
      ]);
      state.signals = signals ?? [];
      state.context = context ?? [];
      state.insights = insights ?? [];
      state.personThreads = threads ?? [];
    } catch {
      // Detail is supplementary. A failure here must not blank the field.
      state.signals = [];
    }
    paint();
  }

  function paint(): void {
    doc.getElementById(ROOT_ID)?.remove();
    const root = el(doc, "div");
    root.id = ROOT_ID;
    root.dataset.v197NativeAdjunct = "true";

    const shell = el(doc, "div", "nur-orbit-shell");
    shell.append(orbitHeader(doc, state, actions));

    const workspace = el(doc, "div", "nur-orbit-workspace");
    workspace.append(orbitLeftRail(doc, state, actions));
    if (state.view === "orbit") workspace.append(orbitCanvas(doc, state, actions));
    if (state.view === "list") workspace.append(orbitListView(doc, state, actions));
    if (state.view === "threads") workspace.append(orbitThreadsView(doc, state, actions));
    workspace.append(orbitDetailPanel(doc, state, actions));
    shell.append(workspace);

    if (state.error) {
      const notice = el(doc, "p", "nur-orbit-inline-error", state.error);
      notice.setAttribute("role", "status");
      shell.append(notice);
    }

    root.append(shell);
    doc.body.append(root);
  }

  paint();
  await loadField();
  return true;
}
