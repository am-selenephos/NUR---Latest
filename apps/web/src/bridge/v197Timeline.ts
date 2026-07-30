/**
 * Timeline — past, present and possible futures, rendered V197-native.
 *
 * Plain DOM through the bridge, not React. §58's component tree is preserved as
 * the function decomposition below (`timelineHeader`, `timelineNavigator`,
 * `timelineFlowView`, `timelineCalendarView`, `timelineHorizonsView`,
 * `timelineReviewView`, `timelineDetailPanel` and the tab renderers), because
 * the architecture law is that the canonical V197 document owns the visible
 * product and `#root` never appears on a product page.
 *
 * Everything comes from `/api/v1/timeline*`. Timeline owns no life entity of its
 * own: entries are `timeline_events` and `scheduled_actions`, both read from the
 * canonical endpoints those tables already have — an owner with an empty
 * Timeline sees Now and nothing else, never an invented event.
 *
 * The rule this file exists to protect: a drag never reschedules silently.
 * Moving a future entry always opens the ripple dialog — current time, proposed
 * time, and everything downstream that depends on it — and nothing is written
 * until the owner picks a mode. The keyboard path (the Time tab's Reschedule
 * control) goes through the exact same dialog, so neither path can drift from
 * the other's guarantee.
 */

import TIMELINE_CSS from "../styles/v197-timeline.css?raw";
import { markV197HolographicWordmark } from "./v197Brand";
import { createV197StarSeal } from "./v197StarSeal";
import { setV197SurfaceBackdrop } from "./v197SurfaceBackdrop";
import type { V197ApiClient } from "./v197ApiClient";

const ROOT_ID = "nur-timeline-root";
const STYLE_ID = "nur-timeline-style";

export const TIMELINE_ROUTE = "/universe/timeline";

export type TimelineMode = "flow" | "calendar" | "horizons" | "review";

type DetailTab = "overview" | "time" | "links" | "activity" | "nur";

interface Entry {
  ref: string;
  id: string;
  kind: string;
  event_type: string;
  title: string;
  description: string | null;
  status: string;
  time_kind: string;
  date_precision: string;
  scheduled_for: string | null;
  ends_at: string | null;
  all_day: boolean;
  actual_start_at: string | null;
  actual_end_at: string | null;
  completion_state: string | null;
  occurred_at: string | null;
  system_slug: string | null;
  goal_id: string | null;
  plan_id: string | null;
  orbit_id: string | null;
  phase_id: string | null;
  visibility_scope: string;
  energy_type: string | null;
  importance: number;
  source_type: string;
  lane?: string;
}

interface Phase {
  id: string;
  name: string;
  starts_at: string | null;
  ends_at: string | null;
  status: string;
}

interface Dependency {
  id: string;
  predecessor_ref: string;
  successor_ref: string;
  dependency_kind: string;
  lag_minutes: number;
  user_confirmed: boolean;
}

const EMPTY_FLOW = {
  now: new Date().toISOString(),
  entries: [] as Entry[],
  unscheduled: [] as Entry[],
  phases: [] as Phase[],
  dependencies: [] as Dependency[],
  counts: { total: 0, past: 0, present: 0, future: 0, unscheduled: 0 },
};

/** §5's truth states, each with a word and a glyph — never colour alone. */
const STATUS_PRESENTATION: Record<string, { word: string; glyph: string }> = {
  PLANNED: { word: "Planned", glyph: "○" },
  SCHEDULED: { word: "Scheduled", glyph: "◔" },
  IN_PROGRESS: { word: "In progress", glyph: "◐" },
  DUE: { word: "Due", glyph: "◑" },
  COMPLETED: { word: "Completed", glyph: "◆" },
  PARTIALLY_COMPLETED: { word: "Partially completed", glyph: "◒" },
  MISSED: { word: "Missed", glyph: "△" },
  RESCHEDULED: { word: "Rescheduled", glyph: "↻" },
  CANCELLED: { word: "Cancelled", glyph: "×" },
  OBSERVED: { word: "Observed", glyph: "◆" },
  PREDICTED: { word: "Predicted", glyph: "◇" },
  INFERRED: { word: "Inferred", glyph: "◈" },
  IMPORTED: { word: "Imported", glyph: "⇩" },
  ARCHIVED: { word: "Archived", glyph: "·" },
};

const HORIZON_LABEL: Record<string, string> = {
  NOW: "Now",
  THIS_WEEK: "This Week",
  THIRTY_DAYS: "30 Days",
  NINETY_DAYS: "90 Days",
  SIX_MONTHS: "6 Months",
  ONE_YEAR: "1 Year",
  SOMEDAY: "Someday",
};

const OBJECT_FILTERS: { key: string; label: string; types: string[] }[] = [
  { key: "all", label: "All", types: [] },
  { key: "actions", label: "Actions", types: ["ACTION"] },
  { key: "events", label: "Events", types: ["EVENT"] },
  { key: "milestones", label: "Milestones", types: ["GOAL_MILESTONE", "MILESTONE"] },
  { key: "decisions", label: "Decisions", types: ["DECISION"] },
  { key: "time_blocks", label: "Time Blocks", types: ["TIME_BLOCK"] },
];

const STATUS_FILTERS: { key: string; label: string; statuses: string[] }[] = [
  { key: "all", label: "All", statuses: [] },
  { key: "active", label: "Active", statuses: ["IN_PROGRESS", "DUE", "SCHEDULED"] },
  { key: "upcoming", label: "Upcoming", statuses: ["PLANNED", "PREDICTED"] },
  { key: "overdue", label: "Overdue", statuses: [] },
  { key: "completed", label: "Completed", statuses: ["COMPLETED", "OBSERVED"] },
  { key: "rescheduled", label: "Rescheduled", statuses: ["RESCHEDULED", "MISSED"] },
];

interface TimelineState {
  mode: TimelineMode;
  flow: typeof EMPTY_FLOW;
  horizons: Record<string, unknown> | null;
  review: Record<string, unknown> | null;
  calendar: Record<string, unknown> | null;
  smart: Record<string, unknown> | null;
  query: string;
  systemFilter: string;
  objectFilter: string;
  statusFilter: string;
  selected: string | null;
  tab: DetailTab;
  evidence: Record<string, unknown> | null;
  dependencies: { predecessors: Dependency[]; successors: Dependency[] } | null;
  rescheduleHistory: Record<string, unknown>[] | null;
  ripple: {
    entryId: string;
    entryTitle: string;
    currentStartAt: string | null;
    proposedStartAt: string;
    affected: { ref: string; title: string; proposed_start_at: string }[];
    note: string;
  } | null;
  showOutline: boolean;
  error: string | null;
  notice: string | null;
  loaded: boolean;
}

function el<K extends keyof HTMLElementTagNameMap>(
  doc: Document, tag: K, className?: string, content?: string,
): HTMLElementTagNameMap[K] {
  const node = doc.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function capsule(doc: Document, label: string, disabledReason?: string): HTMLButtonElement {
  const node = el(doc, "button", "nur-timeline-capsule", label);
  node.type = "button";
  if (disabledReason) {
    node.disabled = true;
    node.setAttribute("aria-disabled", "true");
    node.title = disabledReason;
    node.setAttribute("aria-description", disabledReason);
  }
  return node;
}

function chip(doc: Document, label: string, pressed: boolean): HTMLButtonElement {
  const node = el(doc, "button", "nur-timeline-capsule nur-timeline-capsule-sm", label);
  node.type = "button";
  node.setAttribute("aria-pressed", pressed ? "true" : "false");
  return node;
}

function field(doc: Document, label: string, value: string, unmeasured = false): HTMLElement {
  const wrap = el(doc, "div", "nur-timeline-field");
  wrap.append(el(doc, "p", "nur-timeline-field-label", label));
  const body = el(doc, "p", "nur-timeline-field-value", value);
  if (unmeasured) body.classList.add("is-unmeasured");
  wrap.append(body);
  return wrap;
}

function ensureStyle(doc: Document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = TIMELINE_CSS;
  doc.head.append(style);
}

function text(value: unknown, fallback = "Not recorded"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number") return String(value);
  return fallback;
}

function fmt(iso: string | null): string {
  if (!iso) return "No time set";
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return iso;
  return parsed.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
  });
}

function dayKey(iso: string | null): string {
  if (!iso) return "unscheduled";
  return new Date(iso).toISOString().slice(0, 10);
}

/** Past / present / future / overdue, decided from the real timestamp.
 *
 * The server sends a `lane` already, but it groups an overdue commitment with
 * ordinary history — and §60 gives overdue its own restrained Coral Flame
 * treatment, because something still owed is not the same as something finished.
 */
function laneOf(entry: Entry, nowMs: number): string {
  const settled = ["COMPLETED", "OBSERVED", "CANCELLED", "ARCHIVED"];
  if (settled.includes(entry.status)) return "past";
  if (["IN_PROGRESS", "DUE"].includes(entry.status)) return "present";
  if (!entry.scheduled_for) return "future";
  const when = new Date(entry.scheduled_for).getTime();
  if (when < nowMs) return "overdue";
  if (when <= nowMs + 86_400_000) return "present";
  return "future";
}

function dayLabel(key: string, now: Date): string {
  if (key === "unscheduled") return "";
  const date = new Date(`${key}T00:00:00Z`);
  const days = Math.round((date.getTime() - new Date(now.toDateString()).getTime()) / 86_400_000);
  if (days === 0) return "Today";
  if (days === 1) return "Tomorrow";
  if (days === -1) return "Yesterday";
  return date.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export async function renderV197Timeline(
  doc: Document, route: string, api: V197ApiClient,
): Promise<boolean> {
  if (route !== TIMELINE_ROUTE) {
    doc.getElementById(ROOT_ID)?.remove();
    // Always restore the canonical content layer on the way out, or leaving this
    // route would leave the canonical page invisible.
    setV197SurfaceBackdrop(doc, false);
    return false;
  }

  ensureStyle(doc);
  // Keep the canonical galaxy visible behind this surface and step the
  // competing canonical content layer aside. See v197SurfaceBackdrop.
  setV197SurfaceBackdrop(doc, true);
  const view = doc.defaultView;
  const isMobile = Boolean(view && view.innerWidth <= 900);

  const state: TimelineState = {
    mode: "flow",
    flow: EMPTY_FLOW,
    horizons: null,
    review: null,
    calendar: null,
    smart: null,
    query: "",
    systemFilter: "ALL",
    objectFilter: "all",
    statusFilter: "all",
    selected: null,
    tab: "overview",
    evidence: null,
    dependencies: null,
    rescheduleHistory: null,
    ripple: null,
    showOutline: false,
    error: null,
    notice: null,
    loaded: false,
  };

  // ── data ───────────────────────────────────────────────────────────────────

  async function loadFlow(): Promise<void> {
    try {
      state.flow = (await api.get<typeof EMPTY_FLOW>("/timeline/flow")) ?? EMPTY_FLOW;
      state.error = null;
    } catch (error) {
      // §52: a failure must not remove the whole Timeline. The last-known state
      // stays on screen and the notice is restrained.
      state.error = error instanceof Error ? error.message : "Part of the Timeline could not update.";
    }
    try {
      state.smart = await api.get<Record<string, unknown>>("/timeline/smart-sections");
    } catch {
      state.smart = null;
    }
    state.loaded = true;
    paint();
  }

  async function loadHorizons(): Promise<void> {
    try {
      state.horizons = await api.get<Record<string, unknown>>("/timeline/horizons");
    } catch {
      state.horizons = null;
    }
    paint();
  }

  async function loadReview(): Promise<void> {
    try {
      state.review = await api.get<Record<string, unknown>>("/timeline/review");
    } catch {
      state.review = null;
    }
    paint();
  }

  async function loadCalendar(): Promise<void> {
    try {
      state.calendar = await api.get<Record<string, unknown>>("/timeline/calendar?view=week");
    } catch {
      state.calendar = null;
    }
    paint();
  }

  async function loadSelection(ref: string): Promise<void> {
    const [, id] = ref.split(":");
    try {
      if (ref.startsWith("timeline_event:")) {
        const [deps, history] = await Promise.all([
          api.get<{ predecessors: Dependency[]; successors: Dependency[] }>(
            `/timeline/entries/${id}/dependencies`,
          ),
          api.get<{ items: Record<string, unknown>[] }>(
            `/timeline/entries/${id}/reschedule-history`,
          ),
        ]);
        state.dependencies = deps ?? null;
        state.rescheduleHistory = history?.items ?? [];
      } else {
        state.dependencies = null;
        state.rescheduleHistory = [];
      }
    } catch {
      state.dependencies = null;
      state.rescheduleHistory = [];
    }
    paint();
  }

  async function mutate(run: () => Promise<unknown>, notice?: string): Promise<void> {
    try {
      await run();
      state.error = null;
      state.notice = notice ?? null;
      await loadFlow();
    } catch (error) {
      state.error = error instanceof Error ? error.message : "That did not work.";
      paint();
    }
  }

  const actions = {
    setMode(mode: TimelineMode) {
      state.mode = mode;
      paint();
      if (mode === "horizons" && !state.horizons) void loadHorizons();
      if (mode === "review" && !state.review) void loadReview();
      if (mode === "calendar" && !state.calendar) void loadCalendar();
    },
    setQuery(query: string) { state.query = query; paint(); },
    setSystemFilter(slug: string) { state.systemFilter = slug; paint(); },
    setObjectFilter(key: string) { state.objectFilter = key; paint(); },
    setStatusFilter(key: string) { state.statusFilter = key; paint(); },
    setTab(tab: DetailTab) { state.tab = tab; paint(); },
    toggleOutline() { state.showOutline = !state.showOutline; paint(); },
    select(ref: string) {
      state.selected = ref;
      state.tab = "overview";
      state.dependencies = null;
      state.rescheduleHistory = null;
      paint();
      void loadSelection(ref);
    },
    jumpToToday() {
      state.mode = "flow";
      paint();
      const target = doc.getElementById("nur-timeline-now-anchor");
      target?.scrollIntoView({ block: "center" });
    },
    start(entryId: string) {
      void mutate(
        () => api.post(`/timeline/entries/${entryId}/start`, {}),
        "Marked in progress.",
      );
    },
    complete(entryId: string) {
      void mutate(
        () => api.post(`/timeline/entries/${entryId}/complete`, {}),
        "Completed.",
      );
    },
    miss(entryId: string) {
      void mutate(
        () => api.post(`/timeline/entries/${entryId}/miss`, {}),
        "Marked missed.",
      );
    },
    archive(entryId: string) {
      void mutate(
        () => api.post(`/timeline/entries/${entryId}/archive`, {}),
        "Archived.",
      );
    },
    confirmObserved(entryId: string) {
      void mutate(
        () => api.post(`/timeline/entries/${entryId}/confirm-observed`, {}),
        "Confirmed as observed.",
      );
    },
    /** Opens the ripple dialog. Never writes anything by itself. */
    async openReschedule(entryId: string, entryTitle: string, currentStartAt: string | null, newStartAt: string): Promise<void> {
      try {
        const preview = await api.post<{
          affected: { ref: string; title: string; proposed_start_at: string }[];
          note: string;
        }>("/timeline/ripple-preview", { entry_id: entryId, new_start_at: newStartAt });
        state.ripple = {
          entryId, entryTitle, currentStartAt, proposedStartAt: newStartAt,
          affected: preview.affected, note: preview.note,
        };
        paint();
      } catch (error) {
        state.error = error instanceof Error ? error.message : "Could not preview that move.";
        paint();
      }
    },
    cancelRipple() { state.ripple = null; paint(); },
    async applyRipple(mode: string): Promise<void> {
      if (!state.ripple) return;
      const { entryId, proposedStartAt } = state.ripple;
      state.ripple = null;
      await mutate(
        () => api.post("/timeline/ripple-apply", {
          entry_id: entryId, new_start_at: proposedStartAt, mode,
        }),
        mode === "MOVE_ONLY"
          ? "Moved. Nothing downstream was touched."
          : "Moved, and downstream items were updated with a recorded reason.",
      );
    },
    /** The non-drag alternative: nudge by whole days, keyboard-reachable. */
    nudgeEntry(entry: Entry, days: number) {
      const base = entry.scheduled_for ? new Date(entry.scheduled_for) : new Date();
      base.setUTCDate(base.getUTCDate() + days);
      void actions.openReschedule(entry.id, entry.title, entry.scheduled_for, base.toISOString());
    },
  };

  // ── derived ────────────────────────────────────────────────────────────────

  function visibleEntries(): Entry[] {
    const objectFilter = OBJECT_FILTERS.find((row) => row.key === state.objectFilter);
    const statusFilter = STATUS_FILTERS.find((row) => row.key === state.statusFilter);
    const query = state.query.trim().toLowerCase();
    const now = new Date(state.flow.now).getTime();
    return state.flow.entries.filter((entry) => {
      if (objectFilter && objectFilter.types.length && !objectFilter.types.includes(entry.event_type)) {
        return false;
      }
      if (state.systemFilter !== "ALL" && entry.system_slug !== state.systemFilter) return false;
      if (statusFilter?.key === "overdue") {
        const when = entry.scheduled_for ? new Date(entry.scheduled_for).getTime() : null;
        if (!(when !== null && when < now && !["COMPLETED", "CANCELLED", "MISSED", "ARCHIVED"].includes(entry.status))) {
          return false;
        }
      } else if (statusFilter && statusFilter.statuses.length && !statusFilter.statuses.includes(entry.status)) {
        return false;
      }
      if (query && !entry.title.toLowerCase().includes(query)) return false;
      return true;
    });
  }

  function entryByRef(ref: string): Entry | undefined {
    return state.flow.entries.find((row) => row.ref === ref)
      ?? state.flow.unscheduled.find((row) => row.ref === ref);
  }

  // ── §58 components ─────────────────────────────────────────────────────────

  function timelineHeader(): HTMLElement {
    const header = el(doc, "header", "nur-timeline-header");

    const title = el(doc, "div", "nur-timeline-title");
    const heading = el(doc, "h1", undefined, "Timeline");
    markV197HolographicWordmark(heading);
    title.append(heading);
    title.append(el(doc, "p", "nur-timeline-subtitle", "Past, present and possible futures"));
    header.append(title);

    const modes = el(doc, "div", "nur-timeline-header-actions");
    modes.setAttribute("role", "tablist");
    modes.setAttribute("aria-label", "Timeline view mode");
    ([
      ["flow", "Flow"], ["calendar", "Calendar"],
      ["horizons", "Horizons"], ["review", "Review"],
    ] as [TimelineMode, string][]).forEach(([mode, label]) => {
      const button = chip(doc, label, state.mode === mode);
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", state.mode === mode ? "true" : "false");
      button.dataset.timelineMode = mode;
      button.addEventListener("click", () => actions.setMode(mode));
      modes.append(button);
    });
    header.append(modes);

    const tools = el(doc, "div", "nur-timeline-header-actions");
    const jump = capsule(doc, "Jump to Today");
    jump.dataset.timelineJumpToday = "true";
    jump.addEventListener("click", () => actions.jumpToToday());
    tools.append(jump);
    const search = el(doc, "input", "nur-timeline-search");
    search.type = "search";
    search.placeholder = "Search events, actions, milestones or memories";
    search.value = state.query;
    search.setAttribute("aria-label", "Search the Timeline");
    search.style.width = "220px";
    search.addEventListener("input", () => actions.setQuery(search.value));
    tools.append(search);
    tools.append(capsule(
      doc, "Add",
      "Not built yet as a guided flow. The creation endpoint (POST /timeline/events) "
      + "is live and tested; the celestial action menu is not.",
    ));
    tools.append(capsule(
      doc, "Ask NUR to Schedule",
      "Not built. There is no model provider connected in this deployment, so "
      + "Timeline never proposes a schedule it did not read from your own rows.",
    ));
    header.append(tools);
    return header;
  }

  function timelineNavigator(): HTMLElement {
    const pane = el(doc, "aside", "nur-timeline-pane nur-timeline-nav");
    pane.setAttribute("aria-label", "Time navigator");
    const scroll = el(doc, "div", "nur-timeline-pane-scroll");

    const modeGroup = el(doc, "div", "nur-timeline-nav-group");
    modeGroup.append(el(doc, "p", "nur-timeline-nav-label", "Objects"));
    const objectChips = el(doc, "div", "nur-timeline-chips");
    for (const row of OBJECT_FILTERS) {
      const button = chip(doc, row.label, state.objectFilter === row.key);
      button.addEventListener("click", () => actions.setObjectFilter(row.key));
      objectChips.append(button);
    }
    modeGroup.append(objectChips);
    scroll.append(modeGroup);

    const statusGroup = el(doc, "div", "nur-timeline-nav-group");
    statusGroup.append(el(doc, "p", "nur-timeline-nav-label", "Status"));
    const statusChips = el(doc, "div", "nur-timeline-chips");
    for (const row of STATUS_FILTERS) {
      const button = chip(doc, row.label, state.statusFilter === row.key);
      button.addEventListener("click", () => actions.setStatusFilter(row.key));
      statusChips.append(button);
    }
    statusGroup.append(statusChips);
    scroll.append(statusGroup);

    const sections: [string, string][] = [
      ["now", "Now"], ["next", "Next"], ["overdue", "Overdue"],
      ["awaiting_dependency", "Awaiting Dependency"], ["needs_review", "Needs Review"],
      ["unscheduled", "Unscheduled"], ["repeating", "Repeating"],
    ];
    for (const [key, label] of sections) {
      const rows = (state.smart?.[key] as { ref: string; label: string }[] | undefined) ?? [];
      const group = el(doc, "div", "nur-timeline-nav-group");
      group.dataset.timelineSection = key;
      group.append(el(doc, "p", "nur-timeline-nav-label", label));
      if (!rows.length) {
        group.append(el(doc, "p", "nur-timeline-empty", "Nothing here yet."));
      } else {
        const list = el(doc, "ul", "nur-timeline-nav-list");
        for (const row of rows.slice(0, 6)) {
          const item = el(doc, "li");
          const button = el(doc, "button", "nur-timeline-row");
          button.type = "button";
          if (state.selected === row.ref) button.classList.add("is-selected");
          button.append(el(doc, "span", undefined, "◦"));
          button.append(el(doc, "span", "nur-timeline-row-label", row.label));
          button.append(el(doc, "span", "nur-timeline-row-meta", ""));
          button.addEventListener("click", () => actions.select(row.ref));
          item.append(button);
          list.append(item);
        }
        group.append(list);
      }
      scroll.append(group);
    }

    pane.append(scroll);
    return pane;
  }

  function truthBadge(entry: Entry): string {
    const presentation = STATUS_PRESENTATION[entry.status] ?? { word: entry.status, glyph: "○" };
    return `${presentation.glyph} ${presentation.word}`;
  }

  function entryRow(entry: Entry, lane: string): HTMLElement {
    const row = el(doc, "div", `nur-timeline-entry is-${lane}`);
    row.dataset.timelineEntry = entry.ref;
    row.dataset.timelineLane = lane;
    row.setAttribute("tabindex", "0");
    row.setAttribute("role", "button");
    if (state.selected === entry.ref) row.classList.add("is-selected");

    row.append(el(doc, "span", "nur-timeline-entry-glyph", truthBadge(entry).split(" ")[0]));
    const body = el(doc, "div", "nur-timeline-entry-body");
    body.append(el(doc, "p", "nur-timeline-entry-title", entry.title));
    body.append(el(
      doc, "p", "nur-timeline-entry-meta",
      `${fmt(entry.scheduled_for)} · ${STATUS_PRESENTATION[entry.status]?.word ?? entry.status}`,
    ));
    row.append(body);

    row.addEventListener("click", () => actions.select(entry.ref));
    row.addEventListener("keydown", (event) => {
      const key = (event as KeyboardEvent).key;
      if (key === "Enter" || key === " ") {
        event.preventDefault();
        actions.select(entry.ref);
      } else if (lane === "future" && (key === "ArrowUp" || key === "ArrowDown")) {
        event.preventDefault();
        actions.nudgeEntry(entry, key === "ArrowDown" ? 1 : -1);
      }
    });

    // Drag to reschedule: only future entries are draggable, and the gesture
    // always ends at the ripple dialog — never a silent write.
    if (lane === "future") {
      let dragging = false;
      let moved = false;
      let originY = 0;
      row.addEventListener("pointerdown", (event) => {
        const pointer = event as PointerEvent;
        if (pointer.button !== 0) return;
        dragging = true;
        moved = false;
        originY = pointer.clientY;
        row.setPointerCapture(pointer.pointerId);
      });
      row.addEventListener("pointermove", (event) => {
        if (!dragging) return;
        const dy = (event as PointerEvent).clientY - originY;
        if (!moved && Math.abs(dy) < 6) return;
        moved = true;
        row.classList.add("is-dragging");
      });
      row.addEventListener("pointerup", (event) => {
        if (!dragging) return;
        dragging = false;
        row.classList.remove("is-dragging");
        const pointer = event as PointerEvent;
        if (row.hasPointerCapture?.(pointer.pointerId)) {
          row.releasePointerCapture(pointer.pointerId);
        }
        if (!moved) return;
        // Each ~28px of vertical drag proposes one day of movement — a coarse,
        // legible mapping rather than sub-minute pixel physics.
        const dy = pointer.clientY - originY;
        const proposedDays = Math.round(dy / 28);
        if (proposedDays === 0) return;
        actions.nudgeEntry(entry, proposedDays);
      });
    }

    return row;
  }

  function timelineFlowView(): HTMLElement {
    const pane = el(doc, "section", "nur-timeline-pane nur-timeline-workspace");
    pane.setAttribute("aria-label", "Living Timeline");
    const wrap = el(doc, "div", "nur-timeline-flow-wrap");

    if (!state.loaded) {
      const loading = el(doc, "div", "nur-timeline-pane-scroll");
      loading.dataset.timelineLoading = "true";
      loading.append(el(doc, "p", "nur-timeline-empty", "Assembling your history and horizon…"));
      wrap.append(loading);
      pane.append(wrap);
      return pane;
    }

    const entries = visibleEntries();
    if (!entries.length && !state.flow.unscheduled.length) {
      const empty = el(doc, "div", "nur-timeline-pane-scroll");
      empty.dataset.timelineEmpty = "true";
      empty.append(el(doc, "h2", "nur-timeline-detail-title", "Your Timeline begins where memory meets intention."));
      empty.append(el(
        doc, "p", "nur-timeline-empty",
        "Nothing has been recorded yet. Once something is scheduled or logged, it "
        + "appears here in its place in time.",
      ));
      wrap.append(empty);
      pane.append(wrap);
      return pane;
    }

    const scroll = el(doc, "div", "nur-timeline-flow-scroll");
    const spine = el(doc, "div", "nur-timeline-spine");
    const now = new Date(state.flow.now);

    const nowMs = now.getTime();
    const nowHorizon = (): HTMLElement => {
      const horizon = el(doc, "div", "nur-timeline-now-horizon");
      horizon.id = "nur-timeline-now-anchor";
      horizon.dataset.timelineNow = "true";
      horizon.append(el(doc, "span", "nur-timeline-now-sigil"));
      horizon.append(el(
        doc, "span", "nur-timeline-now-label",
        now.toLocaleString(undefined, {
          month: "short", day: "numeric", hour: "numeric", minute: "2-digit",
        }),
      ));
      return horizon;
    };

    // The horizon goes exactly where the present is, by timestamp — not before
    // whichever day contains it. Placing it at day granularity put a line
    // labelled "2:49 PM" above an entry timed 12:49 PM, so the page contradicted
    // its own label.
    const sorted = entries.slice().sort((a, b) => {
      const left = a.scheduled_for ? new Date(a.scheduled_for).getTime() : nowMs;
      const right = b.scheduled_for ? new Date(b.scheduled_for).getTime() : nowMs;
      return left - right;
    });
    let insertedNow = false;
    let currentKey: string | null = null;
    let group: HTMLElement | null = null;

    for (const entry of sorted) {
      const when = entry.scheduled_for ? new Date(entry.scheduled_for).getTime() : nowMs;
      if (!insertedNow && when > nowMs) {
        spine.append(nowHorizon());
        insertedNow = true;
        // Force a fresh day group so the horizon is not visually trapped inside
        // the previous group's box.
        currentKey = null;
      }
      const key = dayKey(entry.scheduled_for);
      if (key !== currentKey || group === null) {
        group = el(doc, "div", "nur-timeline-day-group");
        group.append(el(doc, "p", "nur-timeline-day-label", dayLabel(key, now)));
        spine.append(group);
        currentKey = key;
      }
      group.append(entryRow(entry, laneOf(entry, nowMs)));
    }
    if (!insertedNow) spine.append(nowHorizon());

    scroll.append(spine);

    if (state.flow.unscheduled.length) {
      const holding = el(doc, "div", "nur-timeline-unscheduled");
      holding.dataset.timelineUnscheduled = "true";
      holding.append(el(doc, "p", "nur-timeline-nav-label", "Unscheduled"));
      for (const entry of state.flow.unscheduled) {
        holding.append(entryRow(entry, "future"));
      }
      scroll.append(holding);
    }

    wrap.append(scroll);

    const controls = el(doc, "div", "nur-timeline-canvas-controls");
    const outline = chip(doc, "Outline", state.showOutline);
    outline.dataset.timelineOutlineToggle = "true";
    outline.addEventListener("click", () => actions.toggleOutline());
    controls.append(outline);
    wrap.append(controls);

    if (state.showOutline) wrap.append(timelineAccessibilityOutline(entries));
    if (state.ripple) wrap.append(rippleDialog());

    pane.append(wrap);
    return pane;
  }

  function timelineAccessibilityOutline(entries: Entry[]): HTMLElement {
    const box = el(doc, "div", "nur-timeline-pane-scroll");
    box.dataset.timelineOutline = "true";
    box.style.position = "absolute";
    box.style.inset = "0";
    box.style.background = "rgba(0,0,0,0.94)";
    box.append(el(doc, "p", "nur-timeline-nav-label", "Timeline outline"));
    const list = el(doc, "ul", "nur-timeline-outline");
    for (const entry of entries) {
      const item = el(doc, "li");
      const button = el(doc, "button", "nur-timeline-row");
      button.type = "button";
      const presentation = STATUS_PRESENTATION[entry.status] ?? { word: entry.status };
      const summary = `${entry.title}. ${text(entry.event_type)}. Due ${fmt(entry.scheduled_for)}. ${presentation.word}.`;
      button.setAttribute("aria-label", summary);
      button.append(el(doc, "span", undefined, "·"));
      button.append(el(doc, "span", "nur-timeline-row-label", entry.title));
      button.append(el(doc, "span", "nur-timeline-row-meta", presentation.word));
      button.addEventListener("click", () => actions.select(entry.ref));
      item.append(button);
      list.append(item);
    }
    box.append(list);
    const close = capsule(doc, "Close outline");
    close.addEventListener("click", () => actions.toggleOutline());
    box.append(close);
    return box;
  }

  function rippleDialog(): HTMLElement {
    const dialog = el(doc, "div", "nur-timeline-ripple-dialog");
    dialog.dataset.timelineRippleDialog = "true";
    dialog.setAttribute("role", "dialog");
    dialog.setAttribute("aria-modal", "true");
    const card = el(doc, "div", "nur-timeline-ripple-card");
    card.append(el(doc, "h2", "nur-timeline-ripple-title", `Move "${state.ripple!.entryTitle}"?`));
    card.append(el(
      doc, "p", "nur-timeline-ripple-move",
      `From ${fmt(state.ripple!.currentStartAt)} to ${fmt(state.ripple!.proposedStartAt)}.`,
    ));
    card.append(el(doc, "p", "nur-timeline-ripple-move", state.ripple!.note));

    if (state.ripple!.affected.length) {
      const list = el(doc, "ul", "nur-timeline-ripple-affected");
      for (const item of state.ripple!.affected) {
        list.append(el(doc, "li", undefined, `${item.title} → ${fmt(item.proposed_start_at)}`));
      }
      card.append(list);
    }

    const actionsBox = el(doc, "div", "nur-timeline-ripple-actions");
    const moveOnly = capsule(doc, "Move this only");
    moveOnly.dataset.timelineRippleMode = "MOVE_ONLY";
    moveOnly.addEventListener("click", () => void actions.applyRipple("MOVE_ONLY"));
    actionsBox.append(moveOnly);
    if (state.ripple!.affected.length) {
      const shift = capsule(doc, "Shift dependent actions");
      shift.dataset.timelineRippleMode = "SHIFT_DEPENDENTS";
      shift.addEventListener("click", () => void actions.applyRipple("SHIFT_DEPENDENTS"));
      actionsBox.append(shift);
      const compress = capsule(doc, "Compress later work");
      compress.dataset.timelineRippleMode = "COMPRESS_LATER";
      compress.addEventListener("click", () => void actions.applyRipple("COMPRESS_LATER"));
      actionsBox.append(compress);
      const flag = capsule(doc, "Keep dates and flag risk");
      flag.dataset.timelineRippleMode = "KEEP_AND_FLAG";
      flag.addEventListener("click", () => void actions.applyRipple("KEEP_AND_FLAG"));
      actionsBox.append(flag);
    }
    const cancel = capsule(doc, "Cancel");
    cancel.dataset.timelineRippleCancel = "true";
    cancel.addEventListener("click", () => actions.cancelRipple());
    actionsBox.append(cancel);
    card.append(actionsBox);
    dialog.append(card);
    return dialog;
  }

  function timelineCalendarView(): HTMLElement {
    const pane = el(doc, "section", "nur-timeline-pane nur-timeline-workspace");
    const scroll = el(doc, "div", "nur-timeline-pane-scroll");
    scroll.dataset.timelineCalendar = "true";
    scroll.append(el(doc, "p", "nur-timeline-detail-kind", "Calendar · This week"));

    const entries = (state.calendar?.entries as Entry[] | undefined) ?? [];
    if (!entries.length) {
      scroll.append(el(doc, "p", "nur-timeline-empty", "Nothing exact-timed this week."));
      pane.append(scroll);
      return pane;
    }
    const groups = new Map<string, Entry[]>();
    for (const entry of entries) {
      const key = dayKey(entry.scheduled_for);
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key)!.push(entry);
    }
    for (const [key, rows] of Array.from(groups.entries()).sort()) {
      const day = el(doc, "div", "nur-timeline-calendar-day");
      day.append(el(doc, "p", "nur-timeline-calendar-date", dayLabel(key, new Date())));
      for (const entry of rows) day.append(entryRow(entry, entry.lane ?? "future"));
      scroll.append(day);
    }
    scroll.append(el(
      doc, "p", "nur-timeline-empty",
      "A grouped agenda, not a pixel-grid calendar — the exact-time scheduling "
      + "surface, simplified deliberately.",
    ));
    pane.append(scroll);
    return pane;
  }

  function timelineHorizonsView(): HTMLElement {
    const pane = el(doc, "section", "nur-timeline-pane nur-timeline-workspace");
    const scroll = el(doc, "div", "nur-timeline-pane-scroll");
    scroll.dataset.timelineHorizons = "true";
    scroll.append(el(doc, "p", "nur-timeline-detail-kind", "Horizons"));

    if (!state.horizons) {
      scroll.append(el(doc, "p", "nur-timeline-empty", "Loading horizons…"));
      pane.append(scroll);
      return pane;
    }

    const buckets = state.horizons.buckets as Record<string, { ref: string; label: string }[]>;
    const grid = el(doc, "div", "nur-timeline-horizons");
    for (const key of ["NOW", "THIS_WEEK", "THIRTY_DAYS", "NINETY_DAYS", "SIX_MONTHS", "ONE_YEAR", "SOMEDAY"]) {
      const col = el(doc, "div", "nur-timeline-horizon-col");
      col.dataset.timelineHorizonBucket = key;
      col.append(el(doc, "p", "nur-timeline-horizon-label", HORIZON_LABEL[key]));
      const rows = buckets[key] ?? [];
      if (!rows.length) {
        col.append(el(doc, "p", "nur-timeline-empty", "Nothing here."));
      } else {
        for (const row of rows) {
          const item = el(doc, "div", "nur-timeline-horizon-item", row.label);
          item.addEventListener("click", () => actions.select(row.ref));
          col.append(item);
        }
      }
      grid.append(col);
    }
    scroll.append(grid);

    const drift = (state.horizons.drift as { ref: string; reschedule_count: number }[] | undefined) ?? [];
    if (drift.length) {
      const banner = el(doc, "div", "nur-timeline-drift");
      banner.dataset.timelineDrift = "true";
      banner.textContent = `${drift.length} item${drift.length === 1 ? "" : "s"} moved outward more than once — worth a look, not a judgement.`;
      scroll.append(banner);
    }
    pane.append(scroll);
    return pane;
  }

  function timelineReviewView(): HTMLElement {
    const pane = el(doc, "section", "nur-timeline-pane nur-timeline-workspace");
    const scroll = el(doc, "div", "nur-timeline-pane-scroll");
    scroll.dataset.timelineReview = "true";
    scroll.append(el(doc, "p", "nur-timeline-detail-kind", "Review"));

    if (!state.review) {
      scroll.append(el(doc, "p", "nur-timeline-empty", "Loading this week's comparison…"));
      pane.append(scroll);
      return pane;
    }

    const findings = state.review.live_findings as Record<string, unknown>;
    scroll.append(el(doc, "h2", "nur-timeline-detail-title", "This week: planned versus actual"));

    const grid = el(doc, "div", "nur-timeline-review-grid");
    const stat = (label: string, value: string) => {
      const box = el(doc, "div", "nur-timeline-stat");
      box.append(el(doc, "p", "nur-timeline-stat-label", label));
      box.append(el(doc, "p", "nur-timeline-stat-value", value));
      grid.append(box);
    };
    stat("Entries", String(findings.period_entry_count ?? 0));
    stat("Completed", String(findings.completed_count ?? 0));
    stat("Missed", String(findings.missed_count ?? 0));
    stat("Rescheduled", String(findings.reschedule_count ?? 0));
    scroll.append(grid);

    const distribution = findings.system_time_distribution as Record<string, string> | undefined;
    if (distribution && Object.keys(distribution).length) {
      scroll.append(field(
        doc, "System time distribution",
        Object.entries(distribution).map(([slug, pct]) => `${slug}: ${pct}`).join(" · "),
      ));
    }

    const generate = capsule(doc, "Generate this week's review");
    generate.dataset.timelineGenerateReview = "true";
    generate.addEventListener("click", () => {
      const now = new Date();
      const start = new Date(now.getTime() - 7 * 86_400_000);
      void mutate(() => api.post("/timeline/reviews/generate", {
        review_type: "WEEKLY", period_start: start.toISOString(), period_end: now.toISOString(),
      }), "Review generated from your own recorded rows.");
      void loadReview();
    });
    scroll.append(generate);

    const recent = (state.review.recent_reviews as Record<string, unknown>[] | undefined) ?? [];
    if (recent.length) {
      scroll.append(el(doc, "p", "nur-timeline-nav-label", "Recent reviews"));
      for (const row of recent) {
        const card = el(doc, "div", "nur-timeline-card");
        card.append(el(doc, "p", "nur-timeline-field-value", text(row.review_type)));
        card.append(el(doc, "p", "nur-timeline-row-meta", text(row.summary, "Computed, not written")));
        scroll.append(card);
      }
    }

    scroll.append(el(
      doc, "p", "nur-timeline-empty",
      "Deterministic — computed from your own recorded timestamps, no model consulted.",
    ));
    pane.append(scroll);
    return pane;
  }

  function timelineDetailPanel(): HTMLElement {
    const pane = el(doc, "aside", "nur-timeline-pane nur-timeline-detail");
    pane.setAttribute("aria-label", "Selection detail");
    const scroll = el(doc, "div", "nur-timeline-pane-scroll");

    const entry = state.selected ? entryByRef(state.selected) : undefined;
    if (!entry) {
      scroll.append(el(doc, "p", "nur-timeline-detail-kind", "Nothing selected"));
      scroll.append(el(
        doc, "p", "nur-timeline-empty",
        "Select something in time to explore its meaning, dependencies and outcome.",
      ));
      pane.append(scroll);
      return pane;
    }

    const header = el(doc, "div", "nur-timeline-detail-header");
    header.append(el(doc, "p", "nur-timeline-detail-kind", `${text(entry.event_type)} · ${truthBadge(entry)}`));
    header.append(el(doc, "h2", "nur-timeline-detail-title", entry.title));
    scroll.append(header);

    const tabs = el(doc, "div", "nur-timeline-tabs");
    tabs.setAttribute("role", "tablist");
    ([
      ["overview", "Overview"], ["time", "Time"], ["links", "Links"],
      ["activity", "Activity"], ["nur", "NUR View"],
    ] as [DetailTab, string][]).forEach(([tab, label]) => {
      const button = el(doc, "button", "nur-timeline-tab", label);
      button.type = "button";
      button.setAttribute("role", "tab");
      button.setAttribute("aria-selected", state.tab === tab ? "true" : "false");
      button.dataset.timelineTab = tab;
      button.addEventListener("click", () => actions.setTab(tab));
      tabs.append(button);
    });
    scroll.append(tabs);

    const body = el(doc, "div");
    body.dataset.timelineTabPanel = state.tab;
    body.setAttribute("role", "tabpanel");
    if (state.tab === "overview") overviewTab(body, entry);
    if (state.tab === "time") timeTab(body, entry);
    if (state.tab === "links") linksTab(body, entry);
    if (state.tab === "activity") activityTab(body);
    if (state.tab === "nur") nurViewTab(body, entry);
    scroll.append(body);

    pane.append(scroll);
    return pane;
  }

  function overviewTab(into: HTMLElement, entry: Entry): void {
    into.append(field(doc, "Description", text(entry.description, "None recorded"), !entry.description));
    into.append(field(doc, "System", text(entry.system_slug, "Not linked"), !entry.system_slug));
    into.append(field(doc, "Priority", `${entry.importance}/100`));
    into.append(field(doc, "Source", text(entry.source_type)));

    const row = el(doc, "div", "nur-timeline-nav-group");
    const controls = el(doc, "div", "nur-timeline-chips");
    if (entry.kind === "timeline_event") {
      if (["PLANNED", "SCHEDULED"].includes(entry.status)) {
        const start = capsule(doc, "Start");
        start.addEventListener("click", () => actions.start(entry.id));
        controls.append(start);
      }
      if (!["COMPLETED", "CANCELLED", "ARCHIVED"].includes(entry.status)) {
        const complete = capsule(doc, "Complete");
        complete.addEventListener("click", () => actions.complete(entry.id));
        controls.append(complete);
        const miss = capsule(doc, "Mark missed");
        miss.addEventListener("click", () => actions.miss(entry.id));
        controls.append(miss);
      }
      if (["PREDICTED", "INFERRED", "IMPORTED"].includes(entry.status)) {
        const confirm = capsule(doc, "Confirm observed");
        confirm.addEventListener("click", () => actions.confirmObserved(entry.id));
        controls.append(confirm);
      }
      const archive = capsule(doc, "Archive");
      archive.addEventListener("click", () => actions.archive(entry.id));
      controls.append(archive);
    }
    row.append(controls);
    into.append(row);
  }

  function timeTab(into: HTMLElement, entry: Entry): void {
    into.append(field(doc, "Precision", entry.date_precision.replace(/_/g, " ").toLowerCase()));
    into.append(field(doc, "Planned", fmt(entry.scheduled_for)));
    into.append(field(doc, "Ends", fmt(entry.ends_at), !entry.ends_at));
    into.append(field(doc, "Actual start", fmt(entry.actual_start_at), !entry.actual_start_at));
    into.append(field(doc, "Actual end", fmt(entry.actual_end_at), !entry.actual_end_at));
    into.append(field(
      doc, "Completion quality",
      text(entry.completion_state, "Not assessed"), !entry.completion_state,
    ));

    if (entry.kind === "timeline_event" && entry.scheduled_for) {
      const reschedule = capsule(doc, "Reschedule");
      reschedule.dataset.timelineReschedule = "true";
      reschedule.addEventListener("click", () => {
        // The keyboard/pointer-free path: proposes one day forward, opening the
        // exact same ripple dialog a drag would.
        void actions.openReschedule(
          entry.id, entry.title, entry.scheduled_for,
          new Date(new Date(entry.scheduled_for!).getTime() + 86_400_000).toISOString(),
        );
      });
      into.append(reschedule);
    }

    const history = state.rescheduleHistory ?? [];
    if (history.length) {
      into.append(el(doc, "p", "nur-timeline-nav-label", "Reschedule history"));
      for (const row of history) {
        const card = el(doc, "div", "nur-timeline-card");
        card.append(el(
          doc, "p", "nur-timeline-field-value",
          `${fmt(row.previous_start_at as string | null)} → ${fmt(row.new_start_at as string | null)}`,
        ));
        card.append(el(doc, "p", "nur-timeline-row-meta", text(row.reason, "No reason given")));
        into.append(card);
      }
    }
  }

  function linksTab(into: HTMLElement, entry: Entry): void {
    into.append(field(doc, "Goal", entry.goal_id ? entry.goal_id : "None", !entry.goal_id));
    into.append(field(doc, "Plan", entry.plan_id ? entry.plan_id : "None", !entry.plan_id));
    into.append(field(doc, "Orbit", entry.orbit_id ? entry.orbit_id : "None", !entry.orbit_id));

    const deps = state.dependencies;
    into.append(field(
      doc, "Depends on",
      deps?.predecessors.length
        ? deps.predecessors.map((row) => row.predecessor_ref).join(" · ")
        : "Nothing recorded",
      !deps?.predecessors.length,
    ));
    into.append(field(
      doc, "Blocks",
      deps?.successors.length
        ? deps.successors.map((row) => row.successor_ref).join(" · ")
        : "Nothing recorded",
      !deps?.successors.length,
    ));

    const row = el(doc, "div", "nur-timeline-chips");
    row.append(capsule(
      doc, "Open on Map",
      "Not built yet as an in-panel jump. The object exists on Map through the "
      + "same dependency edges shown here.",
    ));
    into.append(row);
  }

  function activityTab(into: HTMLElement): void {
    into.append(el(
      doc, "p", "nur-timeline-empty",
      "Activity for this entry is not yet composed into one feed here; its "
      + "reschedule history is on the Time tab.",
    ));
  }

  function nurViewTab(into: HTMLElement, entry: Entry): void {
    const doubt = el(doc, "div", "nur-timeline-doubt");
    doubt.dataset.timelineDoubt = "true";
    doubt.append(el(doc, "p", "nur-timeline-doubt-label", "What NUR may be wrong about"));
    doubt.append(el(
      doc, "p", "nur-timeline-field-value",
      entry.status === "PREDICTED"
        ? "This is a prediction, not a confirmed fact. NUR only sees what you have "
          + "recorded, and a horizon passing quietly is not the same as it happening."
        : `NUR reads this ${text(entry.event_type).toLowerCase()} only from what has been `
          + "recorded. Anything you have not written down is invisible here, so its "
          + "urgency or importance may be more confident than the evidence deserves.",
    ));
    into.append(doubt);
  }

  // ── paint ──────────────────────────────────────────────────────────────────

  function paint(): void {
    doc.getElementById(ROOT_ID)?.remove();
    const root = el(doc, "div");
    root.id = ROOT_ID;
    root.dataset.v197NativeAdjunct = "true";
    root.dataset.timelineLoaded = state.loaded ? "true" : "false";

    const shell = el(doc, "div", "nur-timeline-shell");
    if (isMobile && state.selected) shell.classList.add("is-mobile-detail");
    shell.append(timelineHeader());

    if (state.error) {
      const banner = el(doc, "div", "nur-timeline-banner");
      banner.dataset.timelineError = "true";
      banner.textContent = state.error;
      const retry = capsule(doc, "Retry");
      retry.classList.add("nur-timeline-capsule-sm");
      retry.addEventListener("click", () => { void loadFlow(); });
      banner.append(doc.createTextNode(" "));
      banner.append(retry);
      shell.append(banner);
    } else if (state.notice) {
      const banner = el(doc, "div", "nur-timeline-banner is-notice");
      banner.textContent = state.notice;
      shell.append(banner);
    }

    const zones = el(doc, "div", "nur-timeline-zones");
    zones.append(timelineNavigator());
    if (state.mode === "calendar") zones.append(timelineCalendarView());
    else if (state.mode === "horizons") zones.append(timelineHorizonsView());
    else if (state.mode === "review") zones.append(timelineReviewView());
    else zones.append(timelineFlowView());
    zones.append(timelineDetailPanel());
    shell.append(zones);

    root.append(shell);
    root.append(createV197StarSeal(doc));
    doc.body.append(root);
  }

  paint();
  await loadFlow();
  return true;
}
