import type {
  V197BridgeSnapshot,
  V197CommunityRoom,
  V197InsightDetail,
  V197InsightEvidenceResponse,
  V197InsightWhyChanged,
  V197MapNode,
  V197Plan,
  V197PlanStep,
  V197SystemSnapshot,
  V197TalkThreadRow,
} from "./v197ApiClient";
import { applyV197Locale } from "./v197I18n";
import { hydrateReadOnlyV197 } from "./v197Mutations";
import { renderPersistedGlow } from "./v197Rewards";

/**
 * The six Star Systems, in canonical order. This must match
 * `apps/api/app/living/catalog.py`; a mismatch silently drops or duplicates
 * System slots because the mapping is by title.
 */
const CORE_SYSTEMS = [
  "Ambition",
  "Rebuild",
  "Creation",
  "Growth",
  "Introspection",
  "Connection",
] as const;
const NO_RELIABLE_INSIGHT = "NUR doesn't have enough evidence for a reliable pattern yet.";

function empty(node: Element): void {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function text(node: Element | null, value: string): void {
  if (node) node.textContent = value;
}

function ownText(node: Element | null, value: string): void {
  if (!node) return;
  const textNodes = [...node.childNodes].filter(child => child.nodeType === 3);
  const rendered = node.firstElementChild ? ` ${value}` : value;
  if (textNodes.length === 0) {
    node.append(node.ownerDocument.createTextNode(rendered));
    return;
  }
  textNodes[0].nodeValue = rendered;
  textNodes.slice(1).forEach(child => child.remove());
}

function shorten(value: string, max = 110): string {
  const normalized = value.trim().replace(/\s+/g, " ");
  return normalized.length > max ? `${normalized.slice(0, max - 1)}…` : normalized;
}

function number(value: unknown): string {
  return typeof value === "number" && Number.isFinite(value) ? String(value) : "0";
}

function renderTalk(document: Document, rows: V197TalkThreadRow[]): void {
  const stream = document.querySelector<HTMLElement>("#talk-stream");
  if (!stream) return;

  // Every refresh rebuilds the transcript, which destroys the scroll position.
  // Two rules keep that from throwing the reader around:
  //   - if they were at the bottom, stay pinned to the bottom;
  //   - if they had scrolled up to read, restore exactly where they were.
  const distanceFromBottom = stream.scrollHeight - stream.scrollTop - stream.clientHeight;
  const wasPinned = stream.scrollHeight === 0 || distanceFromBottom < 48;
  const previousTop = stream.scrollTop;

  empty(stream);

  if (rows.length === 0) {
    const message = document.createElement("div");
    message.className = "talk-message nur";
    message.dataset.nurTalkEmpty = "true";
    const meta = document.createElement("div");
    meta.className = "talk-meta";
    meta.textContent = "NUR · private ledger";
    message.append(meta, document.createTextNode("No persisted Talk turns yet. Say one true line to begin."));
    stream.append(message);
    return;
  }

  rows.forEach(row => {
    const message = document.createElement("div");
    message.className = `talk-message ${row.who === "nur" ? "nur" : "user"}`;
    message.dataset.eventId = row.id;
    if (row.who === "nur") {
      const meta = document.createElement("div");
      meta.className = "talk-meta";
      meta.textContent = "NUR · model-generated";
      message.append(meta);
    }
    const body = document.createElement("span");
    body.className = "talk-message-body";
    body.textContent = row.text || "Persisted response without display text.";
    message.append(body);
    stream.append(message);
  });
  // Deferred to the next frame: immediately after appending, `scrollHeight` is
  // still the pre-layout value, so assigning it here landed the view near the
  // top — which is why the transcript jumped back to the first message on every
  // turn.
  const view = document.defaultView;
  const settle = (): void => {
    if (wasPinned) stream.scrollTop = stream.scrollHeight;
    else stream.scrollTop = Math.min(previousTop, stream.scrollHeight);
  };
  if (view) view.requestAnimationFrame(settle);
  else settle();
}

function renderJournal(document: Document, snapshot: V197BridgeSnapshot): void {
  const count = snapshot.journal.length;
  const latest = snapshot.journal[0];
  text(
    document.querySelector("#page-journal .page-sub"),
    count === 0
      ? "Private by default. No persisted entries yet."
      : `${count} private ${count === 1 ? "entry" : "entries"} persisted in your owner ledger.`,
  );
  text(
    document.querySelector("#page-journal .journal-prompt"),
    latest ? `Last held: “${shorten(latest.body, 150)}”` : "What are you trying not to lose?",
  );
}

function renderToday(document: Document, snapshot: V197BridgeSnapshot): void {
  const today = snapshot.today;
  if (!today) {
    text(document.querySelector("#page-today .page-kicker"), "Today in NUR · owner ledger unavailable");
    return;
  }
  const parsed = new Date(`${today.date}T12:00:00`);
  const dateLabel = Number.isNaN(parsed.getTime())
    ? today.date
    : parsed.toLocaleDateString(undefined, { month: "long", day: "numeric", year: "numeric" });
  text(document.querySelector("#page-today .page-kicker"), `Today in NUR · ${today.day_label}, ${dateLabel} · ${today.daypart}`);
  text(
    document.querySelector("#page-today .page-sub"),
    `${today.timezone} · ${today.active_goals.length} active goals · ${today.completed_today.length} completed · ${today.missed_today.length} missed · ${today.glow_today} Glow today.`,
  );

  const dimensions = [today.body, today.mind, today.life];
  const labels = ["Body", "Mind", "Life"];
  document.querySelectorAll<HTMLElement>("#page-today .reading-line").forEach((line, index) => {
    const dimension = dimensions[index];
    if (!dimension) return;
    text(line.querySelector(":scope > span:first-child"), labels[index]);
    const bar = line.querySelector<HTMLElement>(".reading-bar > i");
    if (bar) bar.style.width = `${Math.max(0, Math.min(100, dimension.score))}%`;
    text(line.querySelector("strong"), `${dimension.score}% · persisted evidence`);
    line.title = `${dimension.calculation}. Sources: ${JSON.stringify(dimension.sources)}`;
  });

  const nextMove = today.next_move;
  text(document.querySelector("#page-today .next-move .move-kicker"), nextMove ? "One real next move" : "No move is due");
  text(document.querySelector("#page-today .next-move h3"), nextMove?.title ?? "Choose one capacity-matched move.");
  text(
    document.querySelector("#page-today .next-move p:last-of-type"),
    nextMove
      ? `${nextMove.kind.replaceAll("_", " ").toLowerCase()} · persisted owner ledger`
      : "Create a System action or schedule; NUR will not invent one.",
  );
  ensureTodayOperatingControls(document, snapshot);
}

function checkInRange(
  document: Document,
  id: string,
  labelText: string,
  value: number,
): HTMLLabelElement {
  const label = document.createElement("label");
  label.className = "nur-v197-checkin-field";
  label.htmlFor = id;
  const name = document.createElement("span");
  name.textContent = labelText;
  const output = document.createElement("output");
  output.textContent = String(value);
  const input = document.createElement("input");
  input.id = id;
  input.type = "range";
  input.min = "0";
  input.max = "10";
  input.step = "1";
  input.value = String(value);
  input.addEventListener("input", () => { output.textContent = input.value; });
  label.append(name, output, input);
  return label;
}

function ensureTodayOperatingControls(document: Document, snapshot: V197BridgeSnapshot): void {
  const readingLines = document.querySelector<HTMLElement>("#page-today .reading-lines");
  if (readingLines && !document.querySelector("#nur-v197-today-checkin")) {
    const chamber = document.createElement("section");
    chamber.id = "nur-v197-today-checkin";
    chamber.className = "nur-v197-checkin";
    chamber.hidden = true;
    const title = document.createElement("h3");
    title.textContent = "Adjust today's real reading";
    const note = document.createElement("p");
    note.textContent = "0 is low, 10 is high. Pain and emotional load are inverse capacity signals.";
    const fields = document.createElement("div");
    fields.className = "nur-v197-checkin-grid";
    fields.append(
      checkInRange(document, "nur-checkin-energy", "Energy", 5),
      checkInRange(document, "nur-checkin-pain", "Pain / load", 5),
      checkInRange(document, "nur-checkin-sleep", "Sleep", 5),
      checkInRange(document, "nur-checkin-nourishment", "Food / water", 5),
      checkInRange(document, "nur-checkin-movement", "Movement", 5),
      checkInRange(document, "nur-checkin-load", "Emotional load", 5),
      checkInRange(document, "nur-checkin-clarity", "Clarity", 5),
    );
    const noteInput = document.createElement("input");
    noteInput.id = "nur-checkin-note";
    noteInput.placeholder = "One private note, optional";
    noteInput.autocomplete = "off";
    const save = document.createElement("button");
    save.type = "button";
    save.className = "f4-primary compact";
    save.dataset.action = "save-today-checkin";
    save.textContent = "Hold this reading →";
    chamber.append(title, note, fields, noteInput, save);
    readingLines.after(chamber);
  }

  const nextMove = document.querySelector<HTMLElement>("#page-today .next-move");
  let actions = document.querySelector<HTMLElement>("#nur-v197-today-actions");
  if (nextMove && !actions) {
    actions = document.createElement("div");
    actions.id = "nur-v197-today-actions";
    actions.className = "nur-v197-today-actions";
    ([
      ["today-did-it", "I did it"],
      ["today-missed-it", "I missed it"],
      ["today-make-easier", "Make today easier"],
    ] as const).forEach(([action, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "soft-button";
      button.dataset.action = action;
      button.textContent = label;
      actions?.append(button);
    });
    nextMove.append(actions);
  }
  const actionable = snapshot.today?.next_move?.kind === "SYSTEM_ACTION";
  actions?.querySelectorAll<HTMLButtonElement>("button").forEach(button => {
    button.dataset.todayActionId = actionable ? snapshot.today?.next_move?.id ?? "" : "";
    button.disabled = !actionable;
    button.setAttribute("aria-disabled", String(!actionable));
    button.title = actionable ? "Persist this owner action." : "A persisted System action is required.";
  });
}

function makeStep(document: Document, plan: V197Plan, step: V197PlanStep): HTMLElement {
  const row = document.createElement("div");
  row.className = `plan-step${step.done ? " done" : ""}`;
  row.dataset.planId = plan.id;

  const button = document.createElement("button");
  button.type = "button";
  button.className = "plan-check nur-v136-v89-mini-host";
  button.dataset.planStepId = step.id;
  button.setAttribute("aria-label", step.done ? "Reopen step" : "Complete step");
  button.setAttribute("aria-pressed", String(step.done));

  const copy = document.createElement("div");
  const title = document.createElement("h3");
  title.textContent = step.title;
  const body = document.createElement("p");
  body.textContent = step.body || "One persisted movement inside this Plan.";
  copy.append(title, body);

  const state = document.createElement("time");
  state.textContent = step.done ? "returned" : "open";
  row.append(button, copy, state);
  return row;
}

function ensureOutcomeComposer(document: Document): void {
  if (document.querySelector("#nur-outcome-composer")) return;
  const page = document.querySelector<HTMLElement>("#page-plan article.nur-panel, #page-plan .nur-panel");
  if (!page) return;
  const shell = document.createElement("div");
  shell.id = "nur-outcome-composer";
  shell.className = "thought-composer";
  shell.hidden = true;

  const input = document.createElement("input");
  input.id = "nur-outcome-input";
  input.autocomplete = "off";
  input.placeholder = "What changed in the real world?";
  const button = document.createElement("button");
  button.type = "button";
  button.className = "thought-send-button send-holo-pill";
  button.dataset.action = "return-outcome";
  button.textContent = "Return outcome →";
  shell.append(input, button);
  page.append(shell);
}

function renderPlans(document: Document, plans: V197Plan[]): void {
  const current = plans[0];
  const list = document.querySelector<HTMLElement>("#page-plan .plan-list");
  text(document.querySelector("#page-plan .panel-title"), current?.title ?? "No persisted Plan yet");
  text(
    document.querySelector("#page-plan .panel-sub"),
    current ? `${current.steps.length} persisted ${current.steps.length === 1 ? "step" : "steps"} · ${current.status.toLowerCase()}` : "Use the composer below to name one honest direction.",
  );
  if (list) {
    empty(list);
    if (current?.steps.length) current.steps.forEach(step => list.append(makeStep(document, current, step)));
    else {
      const state = document.createElement("div");
      state.className = "plan-step";
      const copy = document.createElement("div");
      const title = document.createElement("h3");
      title.textContent = "A Plan begins after one direction is persisted.";
      copy.append(title);
      state.append(copy);
      list.append(state);
    }
  }
  ensureOutcomeComposer(document);
  const completedStep = current?.steps.find(step => step.done);
  const outcomeComposer = document.querySelector<HTMLElement>("#nur-outcome-composer");
  if (outcomeComposer) {
    outcomeComposer.hidden = !completedStep;
    if (completedStep) outcomeComposer.dataset.planStepId = completedStep.id;
    else delete outcomeComposer.dataset.planStepId;
  }
}

function systemNodes(snapshot: V197BridgeSnapshot): V197MapNode[] {
  const available = (snapshot.map?.nodes ?? []).filter(node => node.kind !== "PERSONAL_BRIDGE");
  return CORE_SYSTEMS.map(title => available.find(node => node.title === title)).filter((node): node is V197MapNode => Boolean(node));
}

function livingSystems(snapshot: V197BridgeSnapshot): V197SystemSnapshot[] {
  return CORE_SYSTEMS.map(title => snapshot.systems?.systems.find(row => row.title === title))
    .filter((row): row is V197SystemSnapshot => Boolean(row));
}

function renderSystemRail(document: Document, nodes: V197MapNode[], activeOrbitId: string | null): void {
  const list = document.querySelector<HTMLElement>(".clean-system-list");
  if (!list) return;
  const existing = [...list.querySelectorAll<HTMLButtonElement>(".clean-system-row")];
  while (existing.length < nodes.length) {
    const row = document.createElement("button");
    row.type = "button";
    row.className = "clean-system-row";
    const glyph = document.createElement("i");
    glyph.textContent = "✦";
    const label = document.createElement("span");
    row.append(glyph, label);
    list.append(row);
    existing.push(row);
  }
  existing.forEach((row, index) => {
    const node = nodes[index];
    if (!node) {
      row.hidden = true;
      return;
    }
    row.hidden = false;
    row.dataset.system = node.title;
    row.dataset.orbitId = node.id;
    row.dataset.page = "systems";
    text(row.querySelector(":scope > span:not(.nur-exact-mini-host)"), node.title);
    const active = node.id === activeOrbitId || (!activeOrbitId && index === 0);
    row.classList.toggle("active", active);
    row.setAttribute("aria-pressed", String(active));
  });
}

function renderSystems(document: Document, snapshot: V197BridgeSnapshot): void {
  const living = livingSystems(snapshot);
  const nodes = systemNodes(snapshot);
  const activeOrbitId = snapshot.preferences?.active_orbit_id ?? living[0]?.orbit_id ?? nodes[0]?.id ?? null;
  const slots = [...document.querySelectorAll<HTMLButtonElement>(".universe-system-node")];
  slots.forEach((slot, index) => {
    const system = living[index];
    const node = nodes[index];
    // The canonical markup ships a fixed number of System slots. The Systems row
    // must show Systems, so a slot with no living System is hidden rather than
    // falling back to an arbitrary orbit — that fallback kept rendering retired
    // Systems (Money, Body) as though they still existed.
    if (!system) {
      // Both signals: the attribute for semantics and assistive technology, and
      // an inline style because canonical CSS sets `display` on this class and
      // would otherwise keep the slot painted.
      slot.hidden = true;
      // Canonical CSS declares `display` on this class with `!important`, which
      // beats both the `hidden` attribute and a plain inline style. Only an
      // important inline declaration wins.
      slot.style.setProperty("display", "none", "important");
      slot.dataset.nurSystemSlot = "retired";
      slot.removeAttribute("data-system-slug");
      slot.setAttribute("aria-hidden", "true");
      slot.tabIndex = -1;
      return;
    }
    slot.style.removeProperty("display");
    delete slot.dataset.nurSystemSlot;
    slot.removeAttribute("aria-hidden");
    slot.removeAttribute("tabindex");
    if (!node && !system) {
      slot.hidden = true;
      return;
    }
    const title = system?.title ?? node?.title ?? "System";
    const orbitId = system?.orbit_id ?? node?.id ?? "";
    slot.hidden = false;
    slot.dataset.system = title;
    slot.dataset.systemSlug = system?.slug ?? "";
    slot.dataset.orbitId = orbitId;
    text(slot.querySelector(":scope > span:not(.nur-exact-mini-host) > b"), title);
    const held = node ? Object.values(node.counts).reduce((sum, value) => sum + value, 0) : 0;
    text(
      slot.querySelector(":scope > span:not(.nur-exact-mini-host) > small"),
      system ? `${system.progress_percent}% · ${system.progress_sources.glow_points} Glow` : `${held} held`,
    );
    const active = orbitId === activeOrbitId || (!activeOrbitId && index === 0);
    slot.classList.toggle("active", active);
    slot.setAttribute("aria-pressed", String(active));
  });
  const railNodes = living.length
    ? living.map(system => ({
        id: system.orbit_id,
        title: system.title,
        kind: "SYSTEM",
        orbit_id: system.orbit_id,
        active: true,
        counts: { progress: system.progress_percent, glow: system.progress_sources.glow_points },
      }))
    : nodes;
  renderSystemRail(document, railNodes, activeOrbitId);

  const stateCards = [...document.querySelectorAll<HTMLElement>(".universe-state-strip > article")];
  const state = snapshot.ownerState;
  const facts: Array<[string, string, string]> = [
    ["Systems", number(state?.active_systems), "owner-owned"],
    ["Plans", number(state?.plans_active), "persisted"],
    ["Outcomes", number(state?.outcomes_returned), "returned"],
    ["Questions", number(state?.open_questions), "open"],
    ["Research", number(state?.research_staged), "saved locally"],
    ["Insights", number(state?.insights_evolving), "owner review"],
  ];
  stateCards.forEach((card, index) => {
    const fact = facts[index];
    if (!fact) return;
    text(card.querySelector("small"), fact[0]);
    text(card.querySelector("b"), fact[1]);
    text(card.querySelector("em, span"), fact[2]);
  });
}

function recordTitle(row: Record<string, unknown> | undefined, fallback: string): string {
  if (!row) return fallback;
  for (const key of ["title", "claim", "question", "summary"]) {
    const value = row[key];
    if (typeof value === "string" && value.trim()) return value;
  }
  return fallback;
}

function renderLiveUniverse(document: Document, snapshot: V197BridgeSnapshot): void {
  const live = snapshot.live;
  if (!live) return;

  const coverage = Math.round(Math.max(0, Math.min(1, live.state.confidence)) * 100);
  text(
    document.querySelector("#page-systems .universe-hero-copy .page-sub"),
    `${live.state.summary} ${live.state.source_count} owner-ledger sources · ${coverage}% source coverage, not truth probability.`,
  );
  text(
    document.querySelector(".universe-field-readout > span"),
    `${live.active_systems.length} active Systems · ${live.open_loops.length} open loops · ${live.glow.today_points ?? 0} Glow today`,
  );

  const cards = [...document.querySelectorAll<HTMLElement>(".universe-state-strip > article")];
  const nextMove = live.next_moves[0];
  const firstGoal = live.active_goals[0];
  const firstProject = live.projects[0];
  const firstSignal = live.signals[0];
  const firstChange = live.what_changed[0];
  const orbitCount = live.people_orbits.length + live.group_orbits.length;
  const facts: Array<[string, string, string, string, string]> = [
    [
      "What NUR sees now",
      shorten(live.state.summary, 48),
      `${live.state.source_count} persisted sources · ${coverage}% coverage`,
      "systems",
      "universe",
    ],
    [
      "Future path",
      recordTitle(firstGoal, `${live.active_goals.length} active goals`),
      `${live.active_objectives.length} objectives · ${live.active_plans.length} plans`,
      "",
      "map",
    ],
    [
      "People in your Orbit",
      orbitCount ? `${orbitCount} active people / groups` : "No people or group Orbit yet",
      orbitCount ? "Open the owner-scoped Orbit ledger" : "NUR will not invent social activity",
      "",
      "orbits",
    ],
    [
      "Projects & open loops",
      recordTitle(firstProject, `${live.open_loops.length} open loops`),
      `${live.projects.length} projects · ${live.open_loops.length} unresolved`,
      "",
      "orbits",
    ],
    [
      "Next move",
      recordTitle(nextMove, "No persisted next move"),
      typeof nextMove?.why === "string" ? shorten(nextMove.why, 62) : "NUR will not invent one",
      "plan",
      "",
    ],
    [
      "Signals & change",
      recordTitle(firstSignal, recordTitle(firstChange, "No recent persisted signal")),
      `${live.signals.length} signals · ${live.what_changed.length} recent changes`,
      "",
      "research",
    ],
  ];
  cards.forEach((card, index) => {
    const fact = facts[index];
    if (!fact) return;
    setLaneCard(card, fact[0], fact[1], fact[2]);
    if (fact[3]) card.dataset.page = fact[3];
    else delete card.dataset.page;
    if (fact[4]) card.dataset.worldFocus = fact[4];
    else delete card.dataset.worldFocus;
    card.setAttribute("role", "link");
    card.tabIndex = 0;
  });

  const lane = document.querySelector<HTMLElement>(".universe-system-lane");
  const laneCards = [...(lane?.querySelectorAll<HTMLElement>("article") ?? [])];
  const insight = live.latest_insights[0];
  const timeline = live.timeline_highlights[0];
  setLaneCard(
    laneCards[0],
    "Latest insight",
    recordTitle(insight, "No candidate insight yet"),
    insight ? "Evidence-linked owner insight" : "NUR will not invent one",
  );
  setLaneCard(
    laneCards[1],
    "Latest timeline",
    recordTitle(timeline, "No Timeline event yet"),
    timeline ? "Persisted owner event" : "Nothing has been persisted in this slot",
  );
  setLaneCard(
    laneCards[2],
    "What changed",
    recordTitle(firstChange, "No recent persisted change"),
    firstChange ? "Recent owner ledger, not a verified last-visit diff" : "No invented change state",
  );
  lane?.setAttribute("aria-label", "Live Universe owner-ledger highlights");
  document.body.dataset.nurLiveProvenance = live.provenance_label;
}

function renderSelectedSystem(document: Document, snapshot: V197BridgeSnapshot): void {
  const systems = livingSystems(snapshot);
  if (systems.length === 0) return;
  const activeOrbitId = snapshot.preferences?.active_orbit_id;
  const selectedTitle = document.body.dataset.nurSystem;
  const system = systems.find(row => row.orbit_id === activeOrbitId)
    ?? systems.find(row => row.title === selectedTitle)
    ?? systems[0];
  document.body.dataset.nurSystem = system.title;

  const panel = document.querySelector<HTMLElement>(".universe-insight-panel");
  if (panel) panel.dataset.nurLens = "system";
  ownText(document.querySelector(".system-badge"), `${system.title} System`);
  text(document.querySelector(".live-label"), "OWNER LEDGER");
  text(document.querySelector(".universe-insight-title small"), "Definition");
  text(document.querySelector(".universe-insight-title h2"), system.title);
  text(document.querySelector(".universe-insight-copy"), system.definition);
  document.querySelectorAll<HTMLElement>(".signal-list span").forEach((slot, index) => {
    slot.textContent = system.questions[index] ?? "No additional diagnostic question.";
  });
  text(document.querySelector(".insight-opportunity small"), "Suggested next move");
  text(document.querySelector(".insight-opportunity b"), system.next_move.title);
  text(document.querySelector(".insight-uncertainty span"), "If ignored");
  text(document.querySelector(".insight-uncertainty p"), system.prediction.if_ignored);
  text(document.querySelector(".insight-strength span"), "Persisted progress");
  text(document.querySelector(".insight-strength b"), `${system.progress_percent}%`);
  const decorativeStrengthBar = document.querySelector<HTMLElement>(".insight-strength i");
  if (decorativeStrengthBar) decorativeStrengthBar.hidden = true;
  text(document.querySelector(".insight-evidence small"), "Evidence");
  text(
    document.querySelector(".insight-evidence b"),
    `${system.progress_sources.completed_actions}/${system.progress_sources.total_actions} actions · ${system.progress_sources.glow_points} Glow`,
  );
  text(document.querySelector(".insight-evidence span"), system.progress_sources.formula);
  text(document.querySelector(".insight-revision span"), system.prediction.if_followed);

  const cards = [...document.querySelectorAll<HTMLElement>(".universe-state-strip > article")];
  setLaneCard(cards[0], "System progress", `${system.progress_percent}%`, "calculated from owner evidence");
  setLaneCard(
    cards[1],
    "Actions",
    `${system.progress_sources.completed_actions}/${system.progress_sources.total_actions}`,
    "completed / persisted",
  );
  setLaneCard(cards[2], "Active goals", String(system.active_goal_count), `${system.progress_sources.goal_progress_percent}% goal progress`);
  setLaneCard(cards[3], "Glow", String(system.progress_sources.glow_points), "source-linked in this System");
  setLaneCard(cards[4], "Next move", system.next_move.title, "capacity-matched owner action");
  setLaneCard(cards[5], "Future path", system.prediction.if_followed, system.prediction.provenance_label.replaceAll("_", " ").toLowerCase());
  cards.forEach(card => card.querySelectorAll<HTMLElement>(".sparkline").forEach(line => { line.hidden = true; }));

  // A selected System also owns the signal lane: its Glow scoreboard replaces
  // the Live Universe highlights (the universe lens restores them on focus).
  const laneCards = [...document.querySelectorAll<HTMLElement>(".universe-system-lane article")];
  const scoreboard = snapshot.scoreboard?.rows ?? [];
  laneCards.forEach((card, index) => {
    const score = scoreboard[index];
    setLaneCard(
      card,
      score ? `System rank ${score.rank}` : "System Glow",
      score?.system_title ?? system.title,
      `${score?.score ?? system.progress_sources.glow_points} persisted Glow`,
    );
  });
}

function setLaneCard(card: Element | undefined, eyebrow: string, title: string, detail: string): void {
  if (!card) return;
  text(card.querySelector(":scope > small"), eyebrow);
  text(card.querySelector(":scope > b"), title);
  const detailSlot = card.querySelector(":scope > em")
    ?? card.querySelector(":scope > span:not(.state-mark):not(.nur-exact-mini-host)");
  text(detailSlot, detail);
}

function primaryInsight(snapshot: V197BridgeSnapshot): Record<string, unknown> | undefined {
  const summary = snapshot.insights;
  const typed = summary?.dedicated_insights?.[0];
  if (typed) return typed;
  const compatible = summary?.claims.find(row =>
    row.record_kind === "DEDICATED_INSIGHT"
    || (typeof row.insight_type === "string" && Array.isArray(row.evidence)),
  );
  return compatible ?? summary?.omega_claims?.[0] ?? summary?.claims[0];
}

function ensureInsightControls(document: Document, claim: Record<string, unknown> | undefined): void {
  const panel = document.querySelector<HTMLElement>(".universe-insight-panel");
  if (!panel) return;
  let controls = document.querySelector<HTMLElement>("#nur-v197-insight-controls");
  if (!controls) {
    controls = document.createElement("section");
    controls.id = "nur-v197-insight-controls";
    controls.className = "nur-v197-insight-controls";
    controls.setAttribute("aria-label", "Insight owner review controls");
    const correction = document.createElement("input");
    correction.id = "nur-v197-insight-correction";
    correction.placeholder = "Correct what NUR got wrong";
    correction.autocomplete = "off";
    const actions = document.createElement("div");
    actions.className = "nur-v197-insight-actions";
    ([
      ["insight-accept", "Accept"],
      ["insight-reject", "Reject"],
      ["insight-correct", "Correct"],
      ["insight-plan", "Make a Plan"],
      ["insight-timeline", "Add to Timeline"],
    ] as const).forEach(([action, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "soft-button";
      button.dataset.action = action;
      button.textContent = label;
      actions.append(button);
    });
    const status = document.createElement("small");
    status.className = "nur-v197-insight-review-state";
    controls.append(correction, actions, status);
    panel.append(controls);
  }
  const insightId = typeof claim?.id === "string" ? claim.id : "";
  const dedicated = Boolean(
    insightId
    && (claim?.record_kind === "DEDICATED_INSIGHT"
      || (typeof claim?.insight_type === "string" && Array.isArray(claim?.evidence))),
  );
  const ownerConfirmed = claim?.lifecycle_status === "OWNER_CONFIRMED"
    || claim?.truth_status === "ACCEPTED";
  controls.dataset.insightId = dedicated ? insightId : "";
  controls.hidden = false;
  controls.querySelectorAll<HTMLButtonElement>("button").forEach(button => {
    const requiresConfirmation = button.dataset.action === "insight-plan";
    const disabled = !dedicated || (requiresConfirmation && !ownerConfirmed);
    button.disabled = disabled;
    button.setAttribute("aria-disabled", String(disabled));
    button.title = !dedicated
      ? "Generate a dedicated evidence-linked Insight before reviewing it here."
      : requiresConfirmation && !ownerConfirmed
        ? "Accept this Insight before converting it into a Plan."
        : "Persist this owner review action.";
  });
  const correction = controls.querySelector<HTMLInputElement>("#nur-v197-insight-correction");
  if (correction) correction.disabled = !dedicated;
  text(
    controls.querySelector(".nur-v197-insight-review-state"),
    dedicated
      ? `${String(claim?.lifecycle_status ?? claim?.truth_status ?? "candidate").toLowerCase()} · owner-governed Insight`
      : "Omega claim shown read-only · generate a dedicated Insight to act on it",
  );
}

export function renderInsightInspection(
  document: Document,
  detail: V197InsightDetail | null,
  evidence: V197InsightEvidenceResponse | null,
  history: V197InsightWhyChanged | null,
  failure: string | null = null,
): void {
  const panel = document.querySelector<HTMLElement>(".universe-insight-panel");
  if (!panel) return;
  let host = panel.querySelector<HTMLElement>("#nur-v197-insight-inspection");
  if (!host) {
    host = document.createElement("section");
    host.id = "nur-v197-insight-inspection";
    host.className = "nur-v197-insight-inspection";
    host.setAttribute("aria-label", "Insight evidence and change history");
    panel.append(host);
  }
  host.hidden = false;
  empty(host);
  if (failure || !detail || !evidence || !history) {
    const state = document.createElement("small");
    state.textContent = failure ?? "No dedicated Insight is available for evidence inspection.";
    host.append(state);
    return;
  }
  ensureInsightControls(document, {
    ...detail,
    record_kind: "DEDICATED_INSIGHT",
    claim_text: detail.claim,
  });

  const heading = document.createElement("strong");
  heading.textContent = `${detail.epistemic_state} · ${detail.time_scale} · version ${detail.insight_version}`;
  const sourceState = document.createElement("p");
  const support = evidence.relations.filter(row => row.relation === "SUPPORTS");
  const counter = evidence.relations.filter(row => row.relation === "CONTRADICTS");
  sourceState.textContent = `${support.length} supporting · ${counter.length} counter · ${detail.source_diversity} source domains`;
  const uncertainty = document.createElement("p");
  uncertainty.textContent = `What NUR may be wrong about: ${detail.what_nur_may_be_wrong_about}`;
  host.append(heading, sourceState, uncertainty);

  const evidenceList = document.createElement("ul");
  evidenceList.setAttribute("aria-label", "Canonical Insight evidence");
  evidence.relations.slice(0, 8).forEach(row => {
    const item = document.createElement("li");
    item.textContent = `${row.relation} · ${row.source_domain} · ${row.provenance_label} · ${row.source_exists ? "source present" : "source invalidated"}${row.evidence_summary ? ` · ${row.evidence_summary}` : ""}`;
    evidenceList.append(item);
  });
  host.append(evidenceList);

  if (detail.alternative_explanations.length) {
    const alternatives = document.createElement("p");
    alternatives.textContent = `Alternatives: ${detail.alternative_explanations.join(" · ")}`;
    host.append(alternatives);
  }
  const changes = document.createElement("p");
  changes.textContent = history.changes.length
    ? `Why changed: ${history.changes.slice(-4).map(row => `${row.change_class}: ${row.trigger}`).join(" · ")}`
    : "Why changed: no state transition has been recorded yet.";
  host.append(changes);

  const routes = document.createElement("nav");
  routes.setAttribute("aria-label", "Canonical Insight links");
  Object.entries(detail.canonical_links).forEach(([label, route]) => {
    if (!route) return;
    const button = document.createElement("button");
    button.type = "button";
    button.className = "soft-button";
    button.dataset.ownerRoute = route;
    button.textContent = label.replace(/_/g, " ");
    routes.append(button);
  });
  host.append(routes);
}

function renderVisibleLens(
  document: Document,
  snapshot: V197BridgeSnapshot,
  focus: string,
): void {
  if (!["map", "orbits", "timeline", "insights", "community", "research", "web"].includes(focus)) return;
  const panel = document.querySelector<HTMLElement>(".universe-insight-panel");
  if (!panel) return;
  panel.dataset.nurLens = focus;
  ownText(panel.querySelector(".system-badge"), `${focus[0].toUpperCase()}${focus.slice(1)} lens`);
  text(panel.querySelector(".live-label"), "OWNER LEDGER");

  let title = "No persisted data yet";
  let copy = "This lens will not invent content before owner-scoped records exist.";
  let uncertainty = "Only persisted owner records are shown.";
  let count = 0;
  const signals: string[] = [];

  if (focus === "map") {
    const graphNodes = snapshot.mapGraph?.nodes ?? [];
    const nodes = graphNodes.length
      ? graphNodes.filter(node => node.kind !== "MASTER_STAR")
      : snapshot.map?.nodes.filter(node => node.kind !== "PERSONAL_BRIDGE") ?? [];
    count = nodes.length;
    title = `${count} persisted Map nodes`;
    copy = snapshot.mapGraph
      ? `${snapshot.mapGraph.counts.systems} Systems · ${snapshot.mapGraph.counts.goals} goals · ${snapshot.mapGraph.counts.people ?? 0} people · ${snapshot.mapGraph.counts.social_orbits ?? 0} social Orbits · ${snapshot.mapGraph.counts.open_predictions} open predictions.`
      : (snapshot.map?.counts ?? []).map(row => `${row.count} ${row.label}`).join(" · ") || "No owner map counts yet.";
    uncertainty = "Map geometry is canonical V197; graph labels, edges, and paths come from the owner ledger.";
    signals.push(...nodes.slice(0, 3).map(node => "label" in node ? node.label : node.title));
  }

  if (focus === "orbits") {
    const socialKinds = new Set(["PERSON", "GROUP", "COUNCIL", "COMMUNITY"]);
    const orbits = (snapshot.orbits?.orbits ?? []).filter(
      row => row.kind !== "PERSONAL_BRIDGE" && !socialKinds.has(row.kind),
    );
    const projects = snapshot.projects?.projects ?? [];
    const people = snapshot.live?.people_orbits ?? [];
    const groups = snapshot.live?.group_orbits ?? [];
    const social = [...people, ...groups];
    count = orbits.length + projects.length + social.length;
    title = social.length
      ? `${recordTitle(social[0], "Social Orbit")} · ${String(social[0].kind ?? "orbit").toLowerCase()}`
      : projects.length
        ? `${projects[0].title} · AM Project`
        : orbits.length ? `${orbits[0].title} + ${Math.max(0, orbits.length - 1)} Systems` : "No persisted Orbits yet";
    copy = social.length
      ? `${people.length} Person Orbits · ${groups.length} Group/Council Orbits · ${social.reduce((sum, row) => sum + Number(row.unresolved_count ?? 0), 0)} unresolved threads · group memory remains separate.`
      : projects.length
        ? `${projects.length} owner AM ${projects.length === 1 ? "Project" : "Projects"} · ${projects.reduce((sum, row) => sum + Object.values(row.task_counts).reduce((inner, value) => inner + value, 0), 0)} persisted tasks · ${projects.reduce((sum, row) => sum + row.verified_evidence, 0)} verified evidence.`
      : orbits.length
        ? `${orbits.length} owner-owned Orbits · ${orbits.reduce((sum, row) => sum + Object.values(row.counts).reduce((inner, value) => inner + value, 0), 0)} held objects.`
      : "Create one System to open this lens.";
    uncertainty = social.length
      ? "No private Talk, Journal, Timeline, or Omega record is copied into a social Orbit."
      : projects.length
      ? `Runs remain proposal/approval records; NUR performs no external action from this lens · ${snapshot.projects?.counts.blocked_tasks ?? 0} blocked tasks.`
      : "Only the signed-in owner's Orbits are queried.";
    signals.push(...social.slice(0, 3).map(row => `${recordTitle(row, "Orbit")} · ${Number(row.unresolved_count ?? 0)} unresolved`));
    signals.push(...projects.slice(0, 3).map(row => `${row.title} · ${row.status.toLowerCase()}`));
    if (signals.length < 3) signals.push(...orbits.slice(0, 3 - signals.length).map(row => row.title));
  }

  if (focus === "timeline") {
    const items = snapshot.timeline?.items ?? [];
    const past = items.filter(row => !row.lane || row.lane === "past");
    const present = items.filter(row => row.lane === "present");
    const future = items.filter(row => row.lane === "future" || row.lane === "prediction");
    const latest = present[0] ?? future[0] ?? past[0];
    const latestOutcome = items.find(row => ["OUTCOME_REPORTED", "OUTCOME_RETURNED"].includes(row.kind));
    count = items.length;
    title = latest?.title ?? "No persisted Timeline event yet";
    copy = latest
      ? `${past.length} past · ${present.length} present · ${future.length} future/prediction. ${latest.body}${latestOutcome && latestOutcome.id !== latest.id ? ` Latest returned outcome: ${latestOutcome.body}` : ""}`
      : "Create or schedule one real action to open the future lane.";
    uncertainty = latest ? `${latest.provenance_label} · ${latest.kind.replaceAll("_", " ")}` : "No event provenance exists yet.";
    if (latestOutcome) signals.push(`Returned: ${shorten(latestOutcome.body, 72)}`);
    signals.push(...items.filter(item => item.id !== latestOutcome?.id).slice(0, 3 - signals.length).map(item => item.title));
  }

  if (focus === "community") {
    const rooms = (snapshot.communityRooms ?? []).filter(room => room.status === "ACTIVE");
    const councils = rooms.filter(room => room.room_kind === "COUNCIL");
    count = rooms.length;
    title = rooms.length
      ? `${rooms[0].title} · ${rooms[0].room_kind.toLowerCase()} room`
      : "No bounded rooms yet";
    copy = rooms.length
      ? `${rooms.length} persisted ${rooms.length === 1 ? "room" : "rooms"} · ${councils.length} ${councils.length === 1 ? "Council" : "Councils"} · members see room content only.`
      : "Create one bounded room to open Group NUR; no public feed is faked.";
    uncertainty = "Private Talk, Journal, Timeline, and Omega never enter a room automatically.";
    signals.push(...rooms.slice(0, 3).map(room => `${room.title} · ${room.current_user_role.toLowerCase()}${room.is_demo ? " · DEMO" : ""}`));
  }

  if (focus === "research") {
    const briefs = snapshot.researchBriefs;
    const latest = briefs[0];
    count = briefs.length;
    title = latest?.question ?? "No persisted research question yet";
    copy = latest
      ? `${briefs.length} owner-staged ${briefs.length === 1 ? "brief" : "briefs"} · latest status ${latest.status.toLowerCase()}.`
      : "Stage one question; NUR will hold it without inventing a source.";
    uncertainty = latest
      ? `Provider status: ${latest.provider_status.toLowerCase()} · summaries remain empty until evidence is returned.`
      : "No external research provider has returned evidence.";
    signals.push(...briefs.slice(0, 3).map(row => `${row.question} · ${row.provider_status.toLowerCase()}`));
  }

  if (focus === "web") {
    const briefs = snapshot.researchBriefs;
    const connected = briefs.filter(row => row.provider_status === "CONNECTED");
    count = connected.length;
    title = connected.length ? `${connected.length} provider-returned web signals` : "No fetched web signal yet";
    copy = connected.length
      ? `${briefs.length} staged questions · ${connected.length} connected provider results.`
      : `${briefs.length} owner-staged ${briefs.length === 1 ? "question" : "questions"} · no external result is presented as fetched.`;
    uncertainty = "Web Signals remains provider-neutral and labels disconnected evidence honestly.";
    signals.push(...briefs.slice(0, 3).map(row => `${row.question} · ${row.provider_status.toLowerCase()}`));
  }

  if (focus === "insights") {
    const insight = snapshot.insights;
    const claim = primaryInsight(snapshot);
    const claimText = typeof claim?.claim_text === "string" ? claim.claim_text : null;
    const claimTitle = typeof claim?.title === "string" ? claim.title : claimText;
    count = insight?.counts.claims ?? 0;
    title = claimTitle ?? NO_RELIABLE_INSIGHT;
    copy = claimText
      ? `${claimText} · ${Array.isArray(claim?.evidence) ? claim.evidence.length : 0} attached evidence records.`
      : "More owner evidence across time or domains is required before NUR surfaces one.";
    uncertainty = typeof claim?.what_nur_may_be_wrong_about === "string"
      ? claim.what_nur_may_be_wrong_about
      : `${insight?.counts.open_contradictions ?? 0} open contradictions · ${insight?.counts.review_queue ?? 0} awaiting review.`;
    signals.push(
      `${insight?.counts.claims ?? 0} candidate claims`,
      `${insight?.counts.predictions ?? 0} predictions`,
      `${insight?.counts.open_contradictions ?? 0} contradictions`,
      `${insight?.counts.feasibility_assessments ?? 0} feasibility checks`,
    );
  }

  text(panel.querySelector(".universe-insight-title small"), "Persisted view");
  text(panel.querySelector(".universe-insight-title h2"), title);
  text(panel.querySelector(".universe-insight-copy"), copy);
  text(panel.querySelector(".insight-uncertainty p"), uncertainty);
  const signalSlots = [...panel.querySelectorAll<HTMLElement>(".signal-list span")];
  signalSlots.forEach((slot, index) => {
    slot.textContent = signals[index] ?? "No additional persisted signal";
  });
  text(panel.querySelector(".insight-strength span"), "Persisted records");
  text(panel.querySelector(".insight-strength b"), String(count));
  text(panel.querySelector(".insight-evidence small"), "Provenance");
  text(panel.querySelector(".insight-evidence b"), snapshot.timeline?.provenance_label ?? snapshot.map?.provenance_label ?? "owner_ledger");
  text(panel.querySelector(".insight-evidence span"), "No fake live metrics");
  text(panel.querySelector(".insight-revision span"), "Updated from the latest persisted snapshot.");
  const controls = document.querySelector<HTMLElement>("#nur-v197-insight-controls");
  const inspection = document.querySelector<HTMLElement>("#nur-v197-insight-inspection");
  if (focus === "insights") ensureInsightControls(document, primaryInsight(snapshot));
  else {
    if (controls) controls.hidden = true;
    if (inspection) inspection.hidden = true;
  }
}

export function renderWorldLens(
  document: Document,
  snapshot: V197BridgeSnapshot,
  focus: string,
): void {
  const mapPanel = document.querySelector<HTMLElement>("#page-systems .universe-map-panel");
  if (mapPanel) {
    mapPanel.scrollLeft = 0;
    mapPanel.scrollTop = 0;
  }
  if (focus === "universe") {
    renderLiveUniverse(document, snapshot);
    return;
  }
  renderVisibleLens(document, snapshot, focus);
  const lane = document.querySelector<HTMLElement>(".universe-system-lane");
  if (!lane) return;
  const cards = [...lane.querySelectorAll<HTMLElement>("article")];

  if (focus === "timeline") {
    const items = snapshot.timeline?.items ?? [];
    const latestOutcome = items.find(row => ["OUTCOME_REPORTED", "OUTCOME_RETURNED"].includes(row.kind));
    const rows = latestOutcome
      ? [latestOutcome, ...items.filter(row => row.id !== latestOutcome.id)].slice(0, 3)
      : items.slice(0, 3);
    cards.forEach((card, index) => {
      const row = rows[index];
      setLaneCard(card, row?.kind.replaceAll("_", " ") ?? "owner timeline", row?.title ?? "No event", row ? shorten(row.body, 80) : "No persisted event in this slot.");
    });
    lane.setAttribute("aria-label", "Owner timeline summary");
    return;
  }

  if (focus === "orbits") {
    const social = [
      ...(snapshot.live?.people_orbits ?? []),
      ...(snapshot.live?.group_orbits ?? []),
    ].slice(0, 3);
    const projects = snapshot.projects?.projects.slice(0, 3) ?? [];
    const occupied = social.length + projects.length;
    const rows = (snapshot.orbits?.orbits ?? []).filter(
      row => row.kind !== "PERSONAL_BRIDGE" && !["PERSON", "GROUP", "COUNCIL", "COMMUNITY"].includes(row.kind),
    ).slice(0, Math.max(0, 3 - occupied));
    cards.forEach((card, index) => {
      const socialOrbit = social[index];
      if (socialOrbit) {
        setLaneCard(
          card,
          `${String(socialOrbit.kind ?? "orbit").toLowerCase()} · owner social ledger`,
          recordTitle(socialOrbit, "Social Orbit"),
          `${Number(socialOrbit.unresolved_count ?? 0)} unresolved · ${Number(socialOrbit.shared_goal_count ?? 0)} shared goals`,
        );
        return;
      }
      const project = projects[index - social.length];
      if (project) {
        const taskCount = Object.values(project.task_counts).reduce((sum, value) => sum + value, 0);
        setLaneCard(card, `AM Project · ${project.status.toLowerCase()}`, project.title, `${taskCount} tasks · ${project.verified_evidence} verified evidence`);
        return;
      }
      const row = rows[index - occupied];
      const held = row ? Object.values(row.counts).reduce((sum, value) => sum + value, 0) : 0;
      setLaneCard(card, row?.kind ?? "project orbit", row?.title ?? "No Orbit", row ? `${held} held objects · ${row.status.toLowerCase()}` : "No persisted Orbit in this slot.");
    });
    lane.setAttribute("aria-label", "Owner Orbits summary");
    return;
  }

  if (focus === "insights") {
    const insight = snapshot.insights;
    setLaneCard(cards[0], "candidate claims", number(insight?.counts.claims), "owner-only Omega ledger");
    setLaneCard(cards[1], "open contradictions", number(insight?.counts.open_contradictions), "needs review");
    setLaneCard(cards[2], "review queue", number(insight?.counts.review_queue), "no automatic promotion");
    lane.setAttribute("aria-label", "Owner insight summary");
    return;
  }

  if (focus === "community") {
    const rooms = (snapshot.communityRooms ?? []).filter(room => room.status === "ACTIVE");
    cards.forEach((card, index) => {
      const room = rooms[index];
      setLaneCard(
        card,
        room ? `${room.room_kind.toLowerCase()} room` : "bounded rooms",
        room ? `${room.title}${room.is_demo ? " · DEMO" : ""}` : "No room",
        room ? `your role ${room.current_user_role.toLowerCase()} · member content only` : "No persisted room in this slot.",
      );
    });
    lane.setAttribute("aria-label", "Persisted community rooms");
    return;
  }

  if (focus === "research" || focus === "web") {
    const briefs = snapshot.researchBriefs.slice(0, 3);
    cards.forEach((card, index) => {
      const row = briefs[index];
      setLaneCard(
        card,
        focus === "research" ? row?.status ?? "owner research" : row?.provider_status ?? "web provider",
        row?.question ?? (focus === "research" ? "No staged question" : "No fetched signal"),
        row
          ? (row.summary || (focus === "research" ? "Held without invented sources." : "No external result is presented as fetched."))
          : "No persisted record in this slot.",
      );
    });
    lane.setAttribute(
      "aria-label",
      focus === "research" ? "Owner research summary" : "Owner web-signal staging summary",
    );
    return;
  }

  const counts = snapshot.map?.counts ?? [];
  const scoreboard = snapshot.scoreboard?.rows.slice(0, 3) ?? [];
  cards.forEach((card, index) => {
    const score = scoreboard[index];
    const row = counts[index];
    setLaneCard(
      card,
      score ? `System rank ${score.rank}` : row?.label ?? "owner ledger",
      score?.system_title ?? number(row?.count),
      score ? `${score.score} persisted Glow` : row ? "persisted private data" : "No persisted count in this slot.",
    );
  });
  lane.setAttribute("aria-label", "Owner map summary");
}

function renderInsight(document: Document, snapshot: V197BridgeSnapshot): void {
  const insights = snapshot.insights;
  const claim = primaryInsight(snapshot);
  const contradiction = insights?.contradictions[0];
  const claimText = typeof claim?.claim_text === "string" ? claim.claim_text : null;
  const confidence = typeof claim?.confidence === "number" ? `${Math.round(claim.confidence * 100)}% confidence` : "awaiting owner evidence";
  const claimCount = typeof insights?.counts.claims === "number" ? insights.counts.claims : insights?.claims.length ?? 0;
  const contradictionCount = typeof insights?.counts.open_contradictions === "number"
    ? insights.counts.open_contradictions
    : insights?.contradictions.length ?? 0;
  const predictionCount = typeof insights?.counts.predictions === "number"
    ? insights.counts.predictions
    : insights?.predictions.length ?? 0;
  const reviewCount = typeof insights?.counts.review_queue === "number"
    ? insights.counts.review_queue
    : insights?.review_queue.length ?? 0;
  const openStep = snapshot.plans.flatMap(plan => plan.steps).find(step => !step.done);
  const latestEvent = snapshot.timeline?.items[0];

  ownText(document.querySelector(".system-badge"), "Candidate insight");
  text(document.querySelector(".universe-insight-title small"), claimText ? "Candidate claim" : "Evidence state");
  text(document.querySelector(".universe-insight-title h2"), claimText ?? NO_RELIABLE_INSIGHT);
  text(
    document.querySelector(".universe-insight-copy"),
    claimText
      ? `Inferred from the owner ledger · ${confidence}.`
      : "More owner evidence across time or domains is required before NUR surfaces one.",
  );
  const contradictionText = typeof contradiction?.description === "string" ? contradiction.description : "No open contradiction is persisted.";
  text(document.querySelector(".insight-uncertainty span"), "Open contradiction");
  text(document.querySelector(".insight-uncertainty p"), contradictionText);
  const signals = [
    `${claimCount} candidate ${claimCount === 1 ? "claim" : "claims"}`,
    `${contradictionCount} open ${contradictionCount === 1 ? "contradiction" : "contradictions"}`,
    `${predictionCount} unresolved ${predictionCount === 1 ? "prediction" : "predictions"}`,
  ];
  document.querySelectorAll<HTMLElement>(".signal-list span").forEach((slot, index) => {
    slot.textContent = signals[index] ?? "No additional persisted signal";
  });
  text(document.querySelector(".insight-opportunity small"), "Next persisted move");
  text(document.querySelector(".insight-opportunity b"), openStep?.title ?? "No persisted next move yet.");
  text(document.querySelector(".insight-strength span"), "Persisted claims");
  text(document.querySelector(".insight-strength b"), String(claimCount));
  const decorativeStrengthBar = document.querySelector<HTMLElement>(".insight-strength i");
  if (decorativeStrengthBar) {
    decorativeStrengthBar.hidden = true;
    decorativeStrengthBar.style.display = "none";
  }
  text(document.querySelector(".insight-evidence small"), "Owner evidence");
  text(document.querySelector(".insight-evidence b"), `${snapshot.timeline?.items.length ?? 0} persisted events`);
  text(document.querySelector(".insight-evidence span"), insights?.provenance_label ?? "owner_ledger");
  text(
    document.querySelector(".insight-revision span"),
    latestEvent ? `Latest persisted change: ${latestEvent.title}.` : `No persisted revision yet · ${reviewCount} awaiting review.`,
  );
  text(document.querySelector(".live-label"), "OWNER LEDGER");
}

function makeHonestResult(document: Document, mark: string, title: string, detail: string): HTMLElement {
  const article = document.createElement("article");
  const icon = document.createElement("i");
  icon.textContent = mark;
  const copy = document.createElement("div");
  const heading = document.createElement("b");
  heading.textContent = title;
  const body = document.createElement("span");
  body.textContent = detail;
  const status = document.createElement("small");
  status.textContent = "Local owner ledger · no invented external data";
  copy.append(heading, body, status);
  article.append(icon, copy);
  return article;
}

function renderResearch(document: Document, snapshot: V197BridgeSnapshot): void {
  text(document.querySelector("#universe-research .universe-card-head h2"), "Saved research questions, held honestly.");
  const results = document.querySelector<HTMLElement>("#universe-research .research-results");
  if (!results) return;
  empty(results);
  if (snapshot.researchBriefs.length === 0) {
    results.append(makeHonestResult(document, "⌕", "Research engine is not connected yet.", "Stage a question here; NUR saves it locally without inventing sources."));
    return;
  }
  snapshot.researchBriefs.slice(0, 4).forEach(row => {
    results.append(makeHonestResult(document, "R", row.question, row.summary || `Status: ${row.status.toLowerCase()} · provider ${row.provider_status.toLowerCase()}`));
  });
}

function ensureCommunityControls(document: Document, rooms: V197CommunityRoom[]): void {
  const host = document.querySelector<HTMLElement>("#universe-community");
  if (!host) return;
  let controls = document.querySelector<HTMLElement>("#nur-v197-community-controls");
  if (!controls) {
    controls = document.createElement("div");
    controls.id = "nur-v197-community-controls";
    controls.className = "nur-v197-community-controls";
    const title = document.createElement("input");
    title.id = "nur-v197-room-title";
    title.placeholder = "Name a bounded room";
    title.maxLength = 240;
    const actions = document.createElement("div");
    actions.className = "nur-v197-community-actions";
    const createRoom = document.createElement("button");
    createRoom.dataset.action = "community-create-room";
    createRoom.textContent = "Create Group room";
    const createCouncil = document.createElement("button");
    createCouncil.dataset.action = "community-create-council";
    createCouncil.textContent = "Start Council";
    actions.append(createRoom, createCouncil);
    const message = document.createElement("input");
    message.id = "nur-v197-room-message";
    message.placeholder = "Write one honest line to your latest room";
    message.maxLength = 12000;
    const post = document.createElement("button");
    post.dataset.action = "community-post-message";
    post.textContent = "Post to room";
    const memberEmail = document.createElement("input");
    memberEmail.id = "nur-v197-member-email";
    memberEmail.type = "email";
    memberEmail.placeholder = "Invite by exact NUR account email";
    memberEmail.maxLength = 320;
    const addMember = document.createElement("button");
    addMember.dataset.action = "community-add-member";
    addMember.textContent = "Add member";
    const councilPosition = document.createElement("input");
    councilPosition.id = "nur-v197-council-position";
    councilPosition.placeholder = "State a Council position";
    councilPosition.maxLength = 12000;
    const addPosition = document.createElement("button");
    addPosition.dataset.action = "council-add-position";
    addPosition.textContent = "Add position";
    const councilDecision = document.createElement("input");
    councilDecision.id = "nur-v197-council-decision";
    councilDecision.placeholder = "Record the Council decision (room owner)";
    councilDecision.maxLength = 12000;
    const recordDecision = document.createElement("button");
    recordDecision.dataset.action = "council-record-decision";
    recordDecision.textContent = "Record decision";
    const state = document.createElement("small");
    state.className = "nur-v197-community-state";
    controls.append(
      title, actions, message, post, memberEmail, addMember,
      councilPosition, addPosition, councilDecision, recordDecision, state,
    );
    host.append(controls);
  }
  const hasRoom = rooms.length > 0;
  const council = rooms.find(room => room.room_kind === "COUNCIL");
  const gate = (
    selector: string,
    enabled: boolean,
    enabledTitle: string,
    disabledTitle: string,
  ): void => {
    const node = controls?.querySelector<HTMLInputElement | HTMLButtonElement>(selector);
    if (!node) return;
    node.disabled = !enabled;
    node.setAttribute("aria-disabled", String(!enabled));
    node.title = enabled ? enabledTitle : disabledTitle;
  };
  gate("#nur-v197-room-message", hasRoom, "", "Create a room before posting a message.");
  gate('[data-action="community-post-message"]', hasRoom,
    hasRoom ? `Persist a message in ${rooms[0].title}.` : "",
    "Create a room before posting a message.");
  gate("#nur-v197-member-email", hasRoom, "", "Create a room before inviting a member.");
  gate('[data-action="community-add-member"]', hasRoom,
    hasRoom ? `Grant membership in ${rooms[0].title}; members see room content only.` : "",
    "Create a room before inviting a member.");
  gate("#nur-v197-council-position", Boolean(council), "", "Start a Council to add positions.");
  gate('[data-action="council-add-position"]', Boolean(council),
    council ? `Persist a position in ${council.title}; minority opinions stay on the ledger.` : "",
    "Start a Council to add positions.");
  gate("#nur-v197-council-decision", Boolean(council), "", "Start a Council to record a decision.");
  gate('[data-action="council-record-decision"]', Boolean(council),
    council ? `Only the owner of ${council.title} can record the decision.` : "",
    "Start a Council to record a decision.");
  text(
    controls.querySelector(".nur-v197-community-state"),
    hasRoom
      ? `Messages and invitations act on “${rooms[0].title}” · Glow is server-verified and never invented.`
      : "Rooms persist through your owner-scoped ledger; nothing here is public.",
  );
}

function renderCommunity(document: Document, snapshot: V197BridgeSnapshot): void {
  const rooms = (snapshot.communityRooms ?? []).filter(room => room.status === "ACTIVE");
  text(
    document.querySelector("#universe-community .universe-card-head h2"),
    rooms.length
      ? `${rooms.length} bounded ${rooms.length === 1 ? "room" : "rooms"} · persisted Group NUR.`
      : "No rooms yet. Create one bounded room to open Group NUR.",
  );
  const community = document.querySelector<HTMLElement>("#universe-community .community-items");
  if (community) {
    empty(community);
    if (rooms.length === 0) {
      community.append(makeHonestResult(
        document,
        "◎",
        "No fake people, replies, or rooms.",
        "Rooms hold only explicitly shared content; private Talk, Journal, Timeline, and Omega stay sealed.",
      ));
    }
    rooms.slice(0, 4).forEach(room => {
      community.append(makeHonestResult(
        document,
        room.room_kind === "COUNCIL" ? "⚖" : "◉",
        `${room.title}${room.is_demo ? " · DEMO" : ""}`,
        `${room.room_kind.toLowerCase()} room · your role ${room.current_user_role.toLowerCase()} · member content only`,
      ));
    });
    // The latest room's persisted conversation, newest last — never invented.
    (snapshot.communityMessages ?? []).slice(-3).forEach(message => {
      community.append(makeHonestResult(
        document,
        "✎",
        shorten(message.body, 90),
        `${message.provenance_label.replaceAll("_", " ").toLowerCase()}${message.is_demo ? " · DEMO" : ""} · ${message.language_tag}`,
      ));
    });
  }
  ensureCommunityControls(document, rooms);
  document.querySelectorAll<HTMLElement>("[data-community-tab]").forEach(control => {
    control.setAttribute("aria-disabled", "true");
    if (control.tagName === "BUTTON") (control as HTMLButtonElement).disabled = true;
    control.setAttribute("title", "Public community feeds stay disconnected; only your persisted rooms are shown.");
  });

  const council = (snapshot.communityRooms ?? []).find(room => room.room_kind === "COUNCIL" && room.status === "ACTIVE");
  const councilCounts = snapshot.councilSummary?.counts;
  text(
    document.querySelector("#universe-consult .universe-card-head h2"),
    council ? `Council: ${council.title}` : "No Council is open yet.",
  );
  text(
    document.querySelector("#universe-consult .consultation-question p"),
    council
      ? councilCounts
        ? `${councilCounts.positions} persisted ${councilCounts.positions === 1 ? "position" : "positions"} · ${councilCounts.decisions} recorded ${councilCounts.decisions === 1 ? "decision" : "decisions"} · minority opinions stay on the ledger.`
        : "This Council persists positions and decisions through the owner-scoped room ledger."
      : "Create a Council room to gather positions, evidence, and one owned decision — nothing is invented.",
  );
}

function renderHonestDisabledSurfaces(document: Document): void {
  document.querySelectorAll<HTMLElement>("[data-stage], .consultation-question button").forEach(control => {
    control.setAttribute("aria-disabled", "true");
    if (control.tagName === "BUTTON") (control as HTMLButtonElement).disabled = true;
  });
  const ritual = document.querySelector<HTMLButtonElement>('[data-action="ritual"]');
  if (ritual) {
    ritual.textContent = "Rituals open in Track B";
    ritual.disabled = true;
    ritual.setAttribute("aria-disabled", "true");
    ritual.setAttribute("title", "Ritual scheduling is not connected in this Track A build.");
  }
  const editDirection = document.querySelector<HTMLButtonElement>("#page-plan .panel-top .tiny-link:not([data-page])");
  if (editDirection) {
    editDirection.dataset.trackAAction = "edit-direction";
    editDirection.textContent = "Direction editing opens in Track B";
    editDirection.disabled = true;
    editDirection.setAttribute("aria-disabled", "true");
    editDirection.setAttribute("title", "Plan direction editing is not connected in this Track A build.");
  }
}

export function hydrateTrackAV197(document: Document, snapshot: V197BridgeSnapshot): void {
  hydrateReadOnlyV197(document, snapshot);
  const locale = snapshot.preferences?.locale ?? snapshot.session.profile.locale ?? "en";
  const writingPreference = snapshot.preferences?.writing_preference ?? snapshot.session.profile.writing_preference ?? "default";
  applyV197Locale(document, locale, writingPreference);
  renderTalk(document, snapshot.talkThread);
  renderToday(document, snapshot);
  renderJournal(document, snapshot);
  renderPlans(document, snapshot.plans);
  renderSystems(document, snapshot);
  renderInsight(document, snapshot);
  // The Live Universe aggregate paints the state strip first; an explicitly
  // selected System then owns it, so System evidence is never hidden behind
  // the aggregate view (the universe lens re-renders it on focus).
  renderLiveUniverse(document, snapshot);
  renderSelectedSystem(document, snapshot);
  renderResearch(document, snapshot);
  renderCommunity(document, snapshot);
  renderHonestDisabledSurfaces(document);
  renderPersistedGlow(document, snapshot.glow);
  text(document.querySelector('[data-thread-action="glow"]'), "Glow this persisted Talk");
  document.querySelectorAll<HTMLElement>(".quiet-chip").forEach(chip => {
    if (chip.textContent?.toLowerCase().includes("live feed")) ownText(chip, "local owner ledger");
  });
  const voice = document.querySelector<HTMLElement>(".composer-action--voice");
  if (voice) {
    voice.setAttribute("aria-disabled", "true");
    voice.setAttribute("title", "Voice is not connected in this Track A build.");
  }

  const latestUserTalk = [...snapshot.talkThread].reverse().find(row => row.who === "user" && row.text);
  text(document.querySelector("#page-today .mini-thread"), latestUserTalk?.text ? `“${shorten(latestUserTalk.text, 170)}”` : "No persisted Talk signal yet.");
}
