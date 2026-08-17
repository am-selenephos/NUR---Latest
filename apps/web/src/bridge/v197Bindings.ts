import {
  V197ApiClient,
  V197ApiError,
  type V197BridgeSnapshot,
  type V197JournalEntry,
  type V197Plan,
  type V197PlanStep,
  type V197Session,
} from "./v197ApiClient";
import { ensureV197LanguageControls, type WritingPreference } from "./v197I18n";
import { hydrateTrackAV197 } from "./v197Hydration";
import { announcePersistedGlow } from "./v197Rewards";
import { createV197StartupStar } from "./v197StarSeal";
import {
  V197StreamClient,
  type V197StreamEvent,
  type V197TalkStreamHooks,
  type V197TalkStreamPayload,
} from "./v197StreamClient";

export type V197ActionApi = Pick<
  V197ApiClient,
  | "event"
  | "talk"
  | "createJournal"
  | "createPlan"
  | "patchPlanStep"
  | "createOutcome"
  | "rewardGlow"
  | "patchPreferences"
  | "createOrbit"
  | "acceptInsight"
  | "rejectInsight"
  | "correctInsight"
  | "convertInsightToPlan"
  | "addInsightToTimeline"
  | "saveTodayCheckIn"
  | "completeTodayAction"
  | "missTodayAction"
  | "makeTodayActionEasier"
  | "logout"
>;

type RefreshSnapshot = () => Promise<V197BridgeSnapshot>;
type LoggedOut = () => Promise<void> | void;
type AfterHydrate = () => Promise<void> | void;
export interface V197TalkTransport {
  readonly active: boolean;
  talk(payload: V197TalkStreamPayload, hooks?: V197TalkStreamHooks, signal?: AbortSignal): Promise<import("./v197ApiClient").V197TalkResult>;
  cancel(): Promise<boolean>;
}
type V197UniverseWindow = Window & {
  nurToast?: (message: string) => void;
  nurOpenPage?: (page: string, options?: Record<string, unknown>) => void;
};

function closest(target: EventTarget | null, selector: string): HTMLElement | null {
  const node = target as Element | null;
  return node && typeof node.closest === "function" ? node.closest<HTMLElement>(selector) : null;
}

function inputValue(document: Document, selector: string): string {
  return document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector)?.value.trim() ?? "";
}

function setInputValue(document: Document, selector: string, value: string): void {
  const input = document.querySelector<HTMLInputElement | HTMLTextAreaElement>(selector);
  if (input) input.value = value;
}

function errorMessage(error: unknown): string {
  return error instanceof Error ? error.message : "The action could not be persisted.";
}

// The honest, in-thread failure line. NUR never invents an assistant answer:
// the disabled provider and any real provider/API failure are surfaced with the
// server's own reason, so a failed turn can never read as a real response.
function talkFailureMessage(error: unknown): string {
  if (error instanceof V197ApiError && error.code === "provider_disabled") {
    return "Live AI is not connected on this server, so NUR did not answer this turn. Your message was kept; nothing was invented.";
  }
  const reason = errorMessage(error);
  return `NUR could not answer this turn: ${reason} Your message was kept; nothing was invented.`;
}

export class V197ActionBindings {
  private snapshot: V197BridgeSnapshot;
  private composerMode = "talk";
  private lastSubmittedTalk = "";
  private readonly clickHandler = (event: Event) => this.onClick(event);
  private readonly keyHandler = (event: Event) => this.onKeyDown(event as KeyboardEvent);
  private readonly scopeHandler = (event: Event) => this.onScopeChoice(event);

  constructor(
    private readonly document: Document,
    private readonly api: V197ActionApi,
    initialSnapshot: V197BridgeSnapshot,
    private readonly refreshSnapshot: RefreshSnapshot,
    private readonly onLoggedOut: LoggedOut,
    private readonly talkTransport: V197TalkTransport,
    private readonly afterHydrate: AfterHydrate,
  ) {
    this.snapshot = initialSnapshot;
  }

  bind(): () => void {
    this.document.addEventListener("click", this.clickHandler, true);
    this.document.addEventListener("keydown", this.keyHandler, true);
    this.document.addEventListener("click", this.scopeHandler);
    this.installLanguageControls();
    this.installOwnerAuthMenu();
    this.installSystemCreateDialog();
    return () => {
      this.document.removeEventListener("click", this.clickHandler, true);
      this.document.removeEventListener("keydown", this.keyHandler, true);
      this.document.removeEventListener("click", this.scopeHandler);
      this.document.getElementById("nur-v197-owner-auth-menu")?.remove();
      this.document.getElementById("nur-v197-system-create")?.remove();
    };
  }

  private installSystemCreateDialog(): void {
    if (this.document.getElementById("nur-v197-system-create")) return;
    const dialog = this.document.createElement("dialog");
    dialog.id = "nur-v197-system-create";
    dialog.className = "nur-v197-system-dialog";
    dialog.setAttribute("aria-labelledby", "nur-v197-system-create-title");

    const chamber = this.document.createElement("section");
    chamber.className = "nur-v197-system-dialog__chamber";
    const kicker = this.document.createElement("p");
    kicker.className = "nur-v197-system-dialog__kicker";
    kicker.textContent = "Private system";
    const title = this.document.createElement("h2");
    title.id = "nur-v197-system-create-title";
    title.textContent = "Name the field.";
    const note = this.document.createElement("p");
    note.className = "nur-v197-system-dialog__note";
    note.textContent = "One life area with its own evidence, actions, and return path.";
    const input = this.document.createElement("input");
    input.id = "nur-v197-system-title";
    input.autocomplete = "off";
    input.maxLength = 80;
    input.placeholder = "e.g. Quiet Ambition";
    input.setAttribute("aria-label", "System name");
    const actions = this.document.createElement("div");
    actions.className = "nur-v197-system-dialog__actions";
    const cancel = this.document.createElement("button");
    cancel.type = "button";
    cancel.dataset.action = "system-create-cancel";
    cancel.textContent = "Cancel";
    const create = this.document.createElement("button");
    create.type = "button";
    create.dataset.action = "system-create-submit";
    create.textContent = "Create system";
    actions.append(cancel, create);
    chamber.append(kicker, title, note, input, actions);
    dialog.append(chamber);
    dialog.addEventListener("cancel", event => {
      event.preventDefault();
      dialog.close();
    });
    this.document.body.append(dialog);
  }

  private openSystemCreateDialog(): void {
    const dialog = this.document.querySelector<HTMLDialogElement>("#nur-v197-system-create");
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    this.document.querySelector<HTMLInputElement>("#nur-v197-system-title")?.focus({ preventScroll: true });
  }

  private closeSystemCreateDialog(): void {
    const dialog = this.document.querySelector<HTMLDialogElement>("#nur-v197-system-create");
    if (!dialog) return;
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
  }

  private installOwnerAuthMenu(): void {
    if (this.document.getElementById("nur-v197-owner-auth-menu")) return;
    const menu = this.document.createElement("aside");
    menu.id = "nur-v197-owner-auth-menu";
    menu.hidden = true;
    menu.setAttribute("aria-label", "Owner session");
    const note = this.document.createElement("p");
    note.textContent = "Your private session is active on this device.";
    const navigation = this.document.createElement("nav");
    navigation.className = "nur-owner-menu-routes";
    navigation.setAttribute("aria-label", "Owner spaces");
    for (const [label, route] of [
      ["Settings", "/settings"],
      ["Memory", "/memory"],
      ["Teach NUR", "/teach-nur"],
      ["Billing", "/billing"],
      ["Capsules", "/capsules"],
      ["Agents", "/agents"],
      ["Projects", "/projects"],
      ["Notifications", "/notifications"],
      ["Glow", "/glow"],
      ["Omega", "/universe/omega"],
    ] as const) {
      const routeButton = this.document.createElement("button");
      routeButton.type = "button";
      routeButton.dataset.ownerRoute = route;
      routeButton.textContent = label;
      navigation.append(routeButton);
    }
    const logout = this.document.createElement("button");
    logout.type = "button";
    logout.dataset.action = "auth-logout";
    logout.textContent = "Sign out of NUR";
    menu.append(note, navigation, logout);
    this.document.body.append(menu);
  }

  private placeOwnerAuthMenu(trigger: HTMLElement, menu: HTMLElement): void {
    const view = this.universeWindow();
    const rect = trigger.getBoundingClientRect();
    const viewportWidth = view?.innerWidth ?? this.document.documentElement.clientWidth;
    const menuWidth = Math.min(260, Math.max(220, viewportWidth - 24));
    const left = Math.max(12, Math.min(viewportWidth - menuWidth - 12, rect.right - menuWidth));
    menu.style.setProperty("--nur-owner-menu-top", `${Math.round(rect.bottom + 8)}px`);
    menu.style.setProperty("--nur-owner-menu-left", `${Math.round(left)}px`);
  }

  private universeWindow(): V197UniverseWindow | null {
    return this.document.defaultView as V197UniverseWindow | null;
  }

  private toast(message: string): void {
    this.universeWindow()?.nurToast?.(message);
  }

  private activeOrbitId(): string | null {
    return this.snapshot.preferences?.active_orbit_id
      ?? this.snapshot.map?.nodes.find(node => node.kind !== "PERSONAL_BRIDGE")?.id
      ?? this.snapshot.session.orbit.id
      ?? null;
  }

  private locale(): string {
    return this.snapshot.preferences?.locale ?? this.snapshot.session.profile.locale ?? "en";
  }

  private writingPreference(): WritingPreference {
    return this.snapshot.preferences?.writing_preference
      ?? this.snapshot.session.profile.writing_preference
      ?? "default";
  }

  private async refresh(): Promise<void> {
    this.snapshot = await this.refreshSnapshot();
    hydrateTrackAV197(this.document, this.snapshot);
    this.installLanguageControls();
    await this.afterHydrate();
  }

  private async perform(control: HTMLElement, task: () => Promise<void>): Promise<void> {
    if (control.dataset.nurBusy === "true") return;
    control.dataset.nurBusy = "true";
    control.setAttribute("aria-busy", "true");
    try {
      await task();
    } catch (error) {
      this.toast(errorMessage(error));
    } finally {
      delete control.dataset.nurBusy;
      control.removeAttribute("aria-busy");
    }
  }

  private blockNative(event: Event): void {
    event.preventDefault();
    event.stopImmediatePropagation();
  }

  private async award(
    eventType: string,
    sourceKind: string,
    sourceId: string,
    idempotencyKey: string,
  ): Promise<void> {
    try {
      const award = await this.api.rewardGlow({
        event_type: eventType,
        source_kind: sourceKind,
        source_id: sourceId,
        orbit_id: this.activeOrbitId(),
        idempotency_key: idempotencyKey,
      });
      announcePersistedGlow(this.document, award);
    } catch (error) {
      // Persistence is the primary action. A verified anti-spam/daily/weekly
      // Glow gate must never suppress the persisted result or its hydration.
      if (error instanceof V197ApiError && error.status === 409) return;
      throw error;
    }
  }

  private async saveJournal(): Promise<void> {
    const body = inputValue(this.document, "#journal-input");
    if (!body) {
      this.toast("Write one honest line first.");
      return;
    }
    const row: V197JournalEntry = await this.api.createJournal(body, this.activeOrbitId());
    await this.award("journal_saved", "JOURNAL_ENTRY", row.id, `journal:${row.id}:saved`);
    setInputValue(this.document, "#journal-input", "");
    await this.refresh();
    this.toast("Journal persisted privately.");
  }

  private async sendTalk(source: "talk" | "today" | "mobile"): Promise<void> {
    const inputSelector = source === "today"
      ? "#today-input"
      : source === "mobile"
        ? "#mobile-composer"
        : "#talk-input";
    const message = inputValue(this.document, inputSelector);
    if (!message) {
      this.toast("Give NUR one real sentence.");
      return;
    }

    const requestId = crypto.randomUUID();
    this.lastSubmittedTalk = message;
    this.universeWindow()?.nurOpenPage?.("talk");
    const transient = this.beginTalkStream(message, requestId);
    try {
      const result = await this.talkTransport.talk(
        {
          request_id: requestId,
          message,
          orbit_id: this.activeOrbitId(),
          locale: this.locale(),
          writing_preference: this.writingPreference(),
          mode: this.composerMode,
          capability_id: null,
          memory_mode: "EPHEMERAL",
        },
        {
          onEvent: (event: V197StreamEvent) => {
            transient.event(event);
            // Clear the composer only once the server has accepted the turn.
            if (event.event === "talk.accepted") setInputValue(this.document, inputSelector, "");
          },
          onDelta: transient.delta,
        },
      );
      await this.award("talk_meaningful", "COGNITIVE_EVENT", result.turn_event_id, `talk:${result.turn_event_id}:meaningful`);
      setInputValue(this.document, inputSelector, "");
      await this.refresh();
      transient.remove();
      this.toast(result.provider_available ? "NUR answered and persisted this turn." : result.provider_reason || "AI is not connected; the honest disabled response was persisted.");
    } catch (error) {
      // Never leave a silent user-only bubble. Convert the pending NUR bubble
      // into a visible, honest failure in place (the user turn stays; no
      // assistant text is invented; the provider's own reason is shown). The
      // next successful send or a reload reconciles from the persisted ledger.
      transient.fail(talkFailureMessage(error));
      this.toast(errorMessage(error));
    }
  }

  private beginTalkStream(message: string, requestId: string): {
    delta: (value: string) => void;
    event: (value: V197StreamEvent) => void;
    fail: (honest: string) => void;
    remove: () => void;
  } {
    const stream = this.document.querySelector<HTMLElement>("#talk-stream");
    if (!stream) return { delta: () => undefined, event: () => undefined, fail: () => undefined, remove: () => undefined };
    // A turn is now in flight, so the "no persisted Talk turns yet" placeholder
    // must not linger (it is otherwise only cleared by a successful refresh).
    stream.querySelector("[data-nur-talk-empty]")?.remove();
    const user = this.document.createElement("div");
    user.className = "talk-message user";
    user.dataset.nurTransient = requestId;
    user.textContent = message;
    const response = this.document.createElement("div");
    response.className = "talk-message nur";
    response.dataset.nurTransient = requestId;
    response.setAttribute("aria-busy", "true");
    const meta = this.document.createElement("div");
    meta.className = "talk-meta";
    meta.textContent = "NUR · opening live model stream ";
    const cancel = this.document.createElement("button");
    cancel.type = "button";
    cancel.className = "tiny-link";
    cancel.dataset.action = "talk-cancel";
    cancel.textContent = "cancel";
    const body = this.document.createElement("span");
    body.dataset.nurStreamText = requestId;
    body.textContent = "Holding your context…";
    meta.append(cancel);
    response.append(meta, body);
    stream.append(user, response);
    stream.scrollTop = stream.scrollHeight;
    let hasDelta = false;
    return {
      delta: value => {
        if (!hasDelta) {
          body.textContent = "";
          hasDelta = true;
        }
        body.append(this.document.createTextNode(value));
        meta.firstChild!.textContent = "NUR · live model stream ";
        stream.scrollTop = stream.scrollHeight;
      },
      event: value => {
        if (value.event === "talk.accepted") meta.firstChild!.textContent = "NUR · private turn accepted ";
        if (value.event === "provider.created") meta.firstChild!.textContent = "NUR · model is responding ";
        if (value.event === "talk.validated") {
          meta.firstChild!.textContent = "NUR · validating and persisting ";
          response.setAttribute("aria-busy", "false");
        }
      },
      // Turn the pending NUR bubble into a visible, honest failure in place — the
      // user turn stays, no assistant text is invented, and the composer never
      // leaves a silent user-only bubble on a provider/API failure.
      fail: honest => {
        response.setAttribute("aria-busy", "false");
        response.classList.add("is-error");
        response.dataset.nurTalkError = "true";
        cancel.remove();
        meta.textContent = "NUR · could not answer";
        body.textContent = honest;
        stream.scrollTop = stream.scrollHeight;
      },
      remove: () => {
        user.remove();
        response.remove();
      },
    };
  }

  private async createPlan(titleOverride?: string): Promise<void> {
    const title = titleOverride?.trim() || this.lastUserTalk();
    if (!title) {
      this.toast("Name one honest direction before creating a Plan.");
      return;
    }
    const plan: V197Plan = await this.api.createPlan(title, this.activeOrbitId());
    await this.award("plan_created", "PLAN", plan.id, `plan:${plan.id}:created`);
    await this.refresh();
    this.universeWindow()?.nurOpenPage?.("plan");
    this.toast("Plan persisted with its first move.");
  }

  private async togglePlanStep(control: HTMLElement): Promise<void> {
    const stepId = control.dataset.planStepId;
    if (!stepId) return;
    const done = control.getAttribute("aria-pressed") !== "true";
    const step: V197PlanStep = await this.api.patchPlanStep(stepId, { done });
    if (done) await this.award("plan_step_completed", "PLAN_STEP", step.id, `plan-step:${step.id}:completed`);
    await this.refresh();
    this.toast(done ? "Step completed and persisted." : "Step reopened.");
  }

  private async makeEasier(): Promise<void> {
    const step = this.snapshot.plans[0]?.steps.find(row => !row.done);
    if (!step) {
      this.toast("There is no open persisted step to make smaller.");
      return;
    }
    const title = step.title.startsWith("Make it smaller:") ? step.title : `Make it smaller: ${step.title}`;
    const updated = await this.api.patchPlanStep(step.id, { title });
    await this.award("task_made_smaller", "PLAN_STEP", updated.id, `plan-step:${updated.id}:made-smaller`);
    await this.refresh();
    this.toast("The move is smaller and persisted.");
  }

  private async returnOutcome(): Promise<void> {
    const composer = this.document.querySelector<HTMLElement>("#nur-outcome-composer");
    const stepId = composer?.dataset.planStepId;
    const result = inputValue(this.document, "#nur-outcome-input");
    if (!stepId || !result) {
      this.toast("Complete one Plan step, then name what changed.");
      return;
    }
    const outcome = await this.api.createOutcome(result, stepId);
    await this.award("outcome_returned", "OUTCOME", outcome.id, `outcome:${outcome.id}:returned`);
    setInputValue(this.document, "#nur-outcome-input", "");
    await this.refresh();
    this.toast("Outcome returned. The ledger and Glow balance moved together.");
  }

  private async createSystem(): Promise<void> {
    const title = inputValue(this.document, "#nur-v197-system-title");
    if (!title) {
      this.toast("Name the System first.");
      this.document.querySelector<HTMLInputElement>("#nur-v197-system-title")?.focus();
      return;
    }
    await this.api.createOrbit(title);
    setInputValue(this.document, "#nur-v197-system-title", "");
    this.closeSystemCreateDialog();
    await this.refresh();
    this.toast("System persisted in your private universe.");
  }

  private lastUserTalk(): string {
    return this.lastSubmittedTalk
      || [...this.snapshot.talkThread].reverse().find(row => row.who === "user" && row.text)?.text?.trim()
      || "";
  }

  private setComposerMode(control: HTMLElement, mode: string): void {
    this.composerMode = mode === "ask" ? "talk" : mode;
    this.document.querySelectorAll<HTMLElement>(".universe-prompt-row [data-action]").forEach(button => {
      button.classList.toggle("active", button === control);
      button.setAttribute("aria-pressed", String(button === control));
    });
    this.toast(mode === "plan" ? "Plan mode selected. Send one direction." : `${mode} mode selected.`);
  }

  private selectSystem(control: HTMLElement): void {
    const orbitId = control.dataset.orbitId;
    const system = control.dataset.system;
    if (!orbitId || !system) return;
    this.document.querySelectorAll<HTMLElement>("[data-system]").forEach(node => {
      const active = node.dataset.orbitId === orbitId;
      node.classList.toggle("active", active);
      node.setAttribute("aria-pressed", String(active));
    });
    this.document.body.dataset.nurSystem = system;
    void this.perform(control, async () => {
      await this.api.patchPreferences({ active_orbit_id: orbitId });
      this.snapshot.preferences = { ...(this.snapshot.preferences ?? {}), active_orbit_id: orbitId };
      hydrateTrackAV197(this.document, this.snapshot);
      this.toast(`${system} is now the active persisted System.`);
    });
  }

  private toggleTodayCheckIn(): void {
    const chamber = this.document.querySelector<HTMLElement>("#nur-v197-today-checkin");
    if (!chamber) return;
    chamber.hidden = !chamber.hidden;
    if (!chamber.hidden) chamber.querySelector<HTMLInputElement>("input")?.focus();
  }

  private async saveTodayCheckIn(): Promise<void> {
    const value = (name: string): number => Number(
      this.document.querySelector<HTMLInputElement>(`#nur-checkin-${name}`)?.value ?? "5",
    );
    await this.api.saveTodayCheckIn({
      energy: value("energy"),
      pain: value("pain"),
      sleep_quality: value("sleep"),
      nourishment: value("nourishment"),
      movement: value("movement"),
      emotional_load: value("load"),
      clarity: value("clarity"),
      note: inputValue(this.document, "#nur-checkin-note") || null,
    });
    const chamber = this.document.querySelector<HTMLElement>("#nur-v197-today-checkin");
    if (chamber) chamber.hidden = true;
    await this.refresh();
    this.toast("Today's reading persisted. Body, Mind, Life, Glow, and Timeline recalculated.");
  }

  private todayActionId(control: HTMLElement): string | null {
    return control.dataset.todayActionId ?? this.snapshot.today?.next_move?.id ?? null;
  }

  private async completeTodayAction(control: HTMLElement): Promise<void> {
    const actionId = this.todayActionId(control);
    if (!actionId || this.snapshot.today?.next_move?.kind !== "SYSTEM_ACTION") {
      this.toast("Create or select a persisted System action first.");
      return;
    }
    await this.api.completeTodayAction(actionId);
    await this.refresh();
    this.toast("Action completed. Today, Timeline, System progress, and Glow moved together.");
  }

  private async missTodayAction(control: HTMLElement): Promise<void> {
    const actionId = this.todayActionId(control);
    if (!actionId || this.snapshot.today?.next_move?.kind !== "SYSTEM_ACTION") {
      this.toast("Create or select a persisted System action first.");
      return;
    }
    await this.api.missTodayAction(actionId);
    await this.refresh();
    this.toast("Miss recorded without erasure. The action can still be returned.");
  }

  private async makeTodayActionEasier(control: HTMLElement): Promise<void> {
    const actionId = this.todayActionId(control);
    const current = this.snapshot.today?.next_move;
    if (!actionId || current?.kind !== "SYSTEM_ACTION") {
      this.toast("Create or select a persisted System action first.");
      return;
    }
    await this.api.makeTodayActionEasier(actionId, `Five-minute version: ${current.title}`, 5);
    await this.refresh();
    this.toast("A five-minute replacement now carries the same lineage.");
  }

  private insightId(control: HTMLElement): string | null {
    return control.closest<HTMLElement>("#nur-v197-insight-controls")?.dataset.insightId ?? null;
  }

  private async actOnInsight(control: HTMLElement, action: string): Promise<void> {
    const insightId = this.insightId(control);
    if (!insightId) {
      this.toast("This candidate is not a persisted dedicated Insight yet.");
      return;
    }
    if (action === "insight-accept") await this.api.acceptInsight(insightId);
    if (action === "insight-reject") await this.api.rejectInsight(insightId);
    if (action === "insight-correct") {
      const correction = inputValue(this.document, "#nur-v197-insight-correction");
      if (!correction) {
        this.toast("Write the correction first.");
        return;
      }
      await this.api.correctInsight(insightId, correction);
    }
    if (action === "insight-plan") await this.api.convertInsightToPlan(insightId);
    if (action === "insight-timeline") await this.api.addInsightToTimeline(insightId);
    await this.refresh();
    this.toast(
      action === "insight-plan"
        ? "Insight converted to a persisted Plan."
        : action === "insight-timeline"
          ? "Insight review added to Timeline."
          : "Insight review persisted to the owner ledger.",
    );
  }

  private installLanguageControls(): void {
    ensureV197LanguageControls(
      this.document,
      this.locale(),
      this.writingPreference(),
      async (locale, writingPreference) => {
        await this.api.patchPreferences({ locale, writing_preference: writingPreference });
        this.snapshot.preferences = { ...(this.snapshot.preferences ?? {}), locale, writing_preference: writingPreference };
        this.toast("Language preference persisted privately.");
      },
      this.snapshot.health?.ai_provider ?? "disabled",
    );
  }

  private onScopeChoice(event: Event): void {
    const option = closest(event.target, ".scope-option[data-scope], .v172-scope-option[data-scope]");
    if (!option) return;
    const map: Record<string, string> = {
      Ephemeral: "EPHEMERAL",
      Private: "PRIVATE_ORBIT",
      "System Shared": "SYSTEM_SHARED",
      "Learning Candidate": "LEARNING_CANDIDATE",
    };
    const boundary = map[option.dataset.scope ?? ""];
    if (!boundary) return;
    void this.perform(option, async () => {
      await this.api.patchPreferences({ default_boundary: boundary });
      this.snapshot.preferences = { ...(this.snapshot.preferences ?? {}), default_boundary: boundary };
      this.toast("Boundary persisted privately.");
    });
  }

  private onClick(event: Event): void {
    const disabled = closest(event.target, "[aria-disabled=\"true\"], button:disabled");
    if (disabled) {
      this.blockNative(event);
      this.toast(disabled.getAttribute("title") || "This control is honestly unavailable in Track A.");
      return;
    }

    const ownerButton = closest(event.target, ".nur-user");
    if (ownerButton) {
      this.blockNative(event);
      const menu = this.document.getElementById("nur-v197-owner-auth-menu");
      if (menu) {
        const opening = menu.hidden;
        if (opening) this.placeOwnerAuthMenu(ownerButton, menu);
        menu.hidden = !opening;
        ownerButton.setAttribute("aria-expanded", String(opening));
      }
      return;
    }

    const logout = closest(event.target, '[data-action="auth-logout"]');
    if (logout) {
      this.blockNative(event);
      void this.perform(logout, async () => {
        await this.api.logout();
        await this.onLoggedOut();
      });
      return;
    }

    const ownerRoute = closest(event.target, "[data-owner-route]");
    if (ownerRoute?.dataset.ownerRoute) {
      this.blockNative(event);
      this.document.getElementById("nur-v197-owner-auth-menu")?.setAttribute("hidden", "");
      this.universeWindow()?.dispatchEvent(new CustomEvent("nur:owner-route", {
        detail: { route: ownerRoute.dataset.ownerRoute },
      }));
      return;
    }

    const cancelTalk = closest(event.target, '[data-action="talk-cancel"]');
    if (cancelTalk) {
      this.blockNative(event);
      void this.perform(cancelTalk, async () => {
        const requested = await this.talkTransport.cancel();
        this.toast(requested ? "Cancelling this Talk turn." : "No live Talk turn is running.");
      });
      return;
    }

    const system = closest(event.target, ".universe-system-node[data-orbit-id], .clean-system-row[data-orbit-id]");
    if (system) {
      this.blockNative(event);
      this.selectSystem(system);
      return;
    }

    const journal = closest(event.target, "#journal-save");
    if (journal) {
      this.blockNative(event);
      void this.perform(journal, () => this.saveJournal());
      return;
    }

    const send = closest(event.target, "[data-send], .universe-send");
    if (send) {
      this.blockNative(event);
      const source = send.dataset.send as "talk" | "today" | "mobile";
      void this.perform(send, () => this.sendTalk(source));
      return;
    }

    const step = closest(event.target, ".plan-check[data-plan-step-id]");
    if (step) {
      this.blockNative(event);
      void this.perform(step, () => this.togglePlanStep(step));
      return;
    }

    const thread = closest(event.target, "[data-thread-action]");
    if (thread) {
      this.blockNative(event);
      const action = thread.dataset.threadAction;
      if (action === "journal") {
        setInputValue(this.document, "#journal-input", this.lastUserTalk());
        this.universeWindow()?.nurOpenPage?.("journal");
        this.toast("Latest persisted Talk moved into a Journal draft.");
      } else if (action === "plan") {
        void this.perform(thread, () => this.createPlan(this.lastUserTalk()));
      } else if (action === "glow") {
        const row = [...this.snapshot.talkThread].reverse().find(item => item.who === "user");
        if (!row) this.toast("There is no persisted Talk turn to Glow yet.");
        else void this.perform(thread, async () => {
          await this.award("talk_meaningful", "COGNITIVE_EVENT", row.id, `talk:${row.id}:meaningful`);
          await this.refresh();
        });
      } else {
        this.toast("This persisted thread remains private.");
      }
      return;
    }

    const action = closest(event.target, "[data-action]");
    if (!action) return;
    const name = action.dataset.action ?? "";
    if (["reflect", "ask", "challenge", "explore", "summarize", "plan"].includes(name)) {
      this.blockNative(event);
      this.setComposerMode(action, name);
      return;
    }
    if (name === "checkin") {
      this.blockNative(event);
      this.toggleTodayCheckIn();
      return;
    }
    if (name === "save-today-checkin") {
      this.blockNative(event);
      void this.perform(action, () => this.saveTodayCheckIn());
      return;
    }
    if (name === "today-did-it") {
      this.blockNative(event);
      void this.perform(action, () => this.completeTodayAction(action));
      return;
    }
    if (name === "today-missed-it") {
      this.blockNative(event);
      void this.perform(action, () => this.missTodayAction(action));
      return;
    }
    if (name === "today-make-easier") {
      this.blockNative(event);
      void this.perform(action, () => this.makeTodayActionEasier(action));
      return;
    }
    if (name === "show-glows") {
      this.blockNative(event);
      this.document.querySelector<HTMLElement>('[data-context-tab="glows"]')?.click();
      return;
    }
    if (name === "make-easier") {
      this.blockNative(event);
      void this.perform(action, () => this.makeEasier());
      return;
    }
    if (name === "return-outcome") {
      this.blockNative(event);
      void this.perform(action, () => this.returnOutcome());
      return;
    }
    if (name === "add-system") {
      this.blockNative(event);
      this.openSystemCreateDialog();
      return;
    }
    if (name === "system-create-cancel") {
      this.blockNative(event);
      this.closeSystemCreateDialog();
      return;
    }
    if (name === "system-create-submit") {
      this.blockNative(event);
      void this.perform(action, () => this.createSystem());
      return;
    }
    if (["insight-accept", "insight-reject", "insight-correct", "insight-plan", "insight-timeline"].includes(name)) {
      this.blockNative(event);
      void this.perform(action, () => this.actOnInsight(action, name));
      return;
    }
    this.blockNative(event);
    this.toast("This control is honestly unavailable in the Track A vertical slice.");
  }

  private onKeyDown(event: KeyboardEvent): void {
    if (event.key !== "Enter" || event.shiftKey) return;
    const target = event.target as Element | null;
    if (!target || typeof target.matches !== "function") return;
    if (target.matches("#talk-input, #today-input, #mobile-composer")) {
      this.blockNative(event);
      const source = target.matches("#today-input") ? "today" : target.matches("#mobile-composer") ? "mobile" : "talk";
      void this.perform(target as HTMLElement, () => this.sendTalk(source));
      return;
    }
    if (target.matches("#nur-v197-system-title")) {
      this.blockNative(event);
      void this.perform(target as HTMLElement, () => this.createSystem());
      return;
    }
    if (target.matches("#nur-outcome-input")) {
      this.blockNative(event);
      void this.perform(target as HTMLElement, () => this.returnOutcome());
    }
  }
}

export function bindV197Actions(
  document: Document,
  api: V197ActionApi,
  snapshot: V197BridgeSnapshot,
  refresh: RefreshSnapshot,
  onLoggedOut: LoggedOut = () => undefined,
  talkTransport: V197TalkTransport = new V197StreamClient(),
  afterHydrate: AfterHydrate = () => undefined,
): () => void {
  return new V197ActionBindings(
    document,
    api,
    snapshot,
    refresh,
    onLoggedOut,
    talkTransport,
    afterHydrate,
  ).bind();
}

type V197EntryAuthApi = Pick<
  V197ApiClient,
  "register" | "login" | "forgotPassword" | "resetPassword"
>;

const V197_RECOVERY_DIALOG_ID = "nur-v197-password-recovery";

function bindV197PasswordRecovery(
  document: Document,
  api: V197EntryAuthApi,
): () => void {
  const signInForm = document.querySelector<HTMLFormElement>("#f4-signin-form");
  if (!signInForm) return () => undefined;

  const switchRow = document.createElement("p");
  switchRow.className = "f4-switch nur-v197-recovery-switch";
  const openButton = document.createElement("button");
  openButton.type = "button";
  openButton.dataset.passwordRecoveryOpen = "true";
  openButton.textContent = "Reset your password";
  switchRow.append("Cannot enter? ", openButton);
  signInForm.insertAdjacentElement("afterend", switchRow);

  const dialog = document.createElement("dialog");
  dialog.id = V197_RECOVERY_DIALOG_ID;
  dialog.className = "nur-v197-recovery-dialog";
  dialog.setAttribute("aria-labelledby", "nur-v197-recovery-title");
  const chamber = document.createElement("section");
  chamber.className = "nur-v197-recovery-chamber";
  dialog.append(chamber);
  document.body.append(dialog);

  let activeToken: string | null = null;

  const close = () => {
    if (typeof dialog.close === "function" && dialog.open) dialog.close();
    else dialog.removeAttribute("open");
    openButton.focus({ preventScroll: true });
  };
  const show = () => {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
    dialog.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
  };

  const render = (token: string | null) => {
    activeToken = token;
    chamber.replaceChildren();
    const closeButton = document.createElement("button");
    closeButton.type = "button";
    closeButton.className = "nur-v197-recovery-close";
    closeButton.dataset.passwordRecoveryClose = "true";
    closeButton.setAttribute("aria-label", "Close password recovery");
    closeButton.textContent = "Close";
    const title = document.createElement("h2");
    title.id = "nur-v197-recovery-title";
    title.textContent = token ? "Choose a new password." : "Return to your Orbit.";
    const copy = document.createElement("p");
    copy.textContent = token
      ? "Set a new password for this one-time recovery link."
      : "Enter your account email. NUR will send instructions if an Orbit matches it.";
    const form = document.createElement("form");
    form.id = token ? "nur-v197-reset-form" : "nur-v197-forgot-form";
    const field = document.createElement("label");
    field.className = "nur-v197-recovery-field";
    const fieldName = document.createElement("span");
    fieldName.textContent = token ? "new password" : "email";
    const input = document.createElement("input");
    input.required = true;
    if (token) {
      input.id = "nur-v197-reset-password";
      input.type = "password";
      input.autocomplete = "new-password";
      input.minLength = 8;
      input.maxLength = 256;
    } else {
      input.id = "nur-v197-forgot-email";
      input.type = "email";
      input.autocomplete = "email";
      input.value = inputValue(document, "#f4-signin-email");
    }
    field.append(fieldName, input);
    form.append(field);
    if (token) {
      const confirmationField = document.createElement("label");
      confirmationField.className = "nur-v197-recovery-field";
      const confirmationName = document.createElement("span");
      confirmationName.textContent = "confirm password";
      const confirmation = document.createElement("input");
      confirmation.id = "nur-v197-reset-confirmation";
      confirmation.type = "password";
      confirmation.autocomplete = "new-password";
      confirmation.required = true;
      confirmation.minLength = 8;
      confirmation.maxLength = 256;
      form.append(confirmationField);
      confirmationField.append(confirmationName, confirmation);
    }
    const submit = document.createElement("button");
    submit.type = "submit";
    submit.className = "f4-primary";
    submit.textContent = token ? "Set new password" : "Send reset instructions";
    const status = document.createElement("p");
    status.className = "nur-v197-recovery-status";
    status.dataset.passwordRecoveryStatus = "true";
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    form.append(submit);
    chamber.append(closeButton, title, copy, form, status);
  };

  const url = new URL(window.location.href);
  const resetToken = url.pathname === "/reset-password" ? url.searchParams.get("token") : null;
  render(resetToken);

  const clickHandler = (event: Event) => {
    const target = event.target as Element | null;
    if (target?.closest('[data-password-recovery-open="true"]')) {
      render(null);
      show();
    } else if (target?.closest('[data-password-recovery-close="true"]')) {
      close();
    }
  };
  const submitHandler = (event: SubmitEvent) => {
    const form = event.target as HTMLFormElement | null;
    if (!form || !["nur-v197-forgot-form", "nur-v197-reset-form"].includes(form.id)) return;
    event.preventDefault();
    if (!form.reportValidity()) return;
    const status = dialog.querySelector<HTMLElement>('[data-password-recovery-status="true"]');
    const submit = form.querySelector<HTMLButtonElement>('button[type="submit"]');
    submit?.setAttribute("aria-busy", "true");
    if (submit) submit.disabled = true;
    if (status) {
      status.textContent = "Working…";
      status.className = "nur-v197-recovery-status";
      status.setAttribute("role", "status");
    }

    const task = form.id === "nur-v197-forgot-form"
      ? api.forgotPassword(inputValue(document, "#nur-v197-forgot-email")).then(result => result.message)
      : (() => {
          const password = inputValue(document, "#nur-v197-reset-password");
          const confirmation = inputValue(document, "#nur-v197-reset-confirmation");
          if (password !== confirmation) return Promise.reject(new Error("The two passwords do not match."));
          if (!activeToken) return Promise.reject(new Error("This recovery link is missing its one-time token."));
          return api.resetPassword(activeToken, password).then(() => {
            window.history.replaceState({}, "", "/auth");
            activeToken = null;
            return "Password changed. Sign in to return to your Orbit.";
          });
        })();

    void task.then(message => {
      if (status) {
        status.textContent = message;
        status.classList.add("is-good");
      }
    }).catch(error => {
      if (status) {
        status.textContent = errorMessage(error);
        status.classList.add("is-warn");
        status.setAttribute("role", "alert");
      }
    }).finally(() => {
      submit?.removeAttribute("aria-busy");
      if (submit) submit.disabled = false;
    });
  };

  document.addEventListener("click", clickHandler, true);
  document.addEventListener("submit", submitHandler, true);
  if (resetToken) window.setTimeout(show, 0);
  return () => {
    document.removeEventListener("click", clickHandler, true);
    document.removeEventListener("submit", submitHandler, true);
    switchRow.remove();
    dialog.remove();
  };
}

export function bindV197EntryAuth(
  document: Document,
  api: V197EntryAuthApi,
  onAuthenticated: (session: V197Session) => Promise<void>,
): () => void {
  const recoveryCleanup = bindV197PasswordRecovery(document, api);
  const waitLayer = ensureV197AuthWaitLayer(document);
  const handler = (event: Event) => {
    const form = event.target as HTMLFormElement | null;
    if (!form || !["f4-signup-form", "f4-signin-form"].includes(form.id)) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (!form.checkValidity()) {
      form.reportValidity();
      return;
    }
    const status = document.querySelector<HTMLElement>("#f4-status");
    const submit = form.querySelector<HTMLElement>('button[type="submit"]');
    const waitMessage = form.id === "f4-signup-form"
      ? "NUR is creating your private Orbit"
      : "NUR is opening your Orbit";
    form.setAttribute("aria-busy", "true");
    submit?.setAttribute("aria-busy", "true");
    waitLayer.querySelector<HTMLElement>("[data-nur-auth-wait-message]")!.textContent = waitMessage;
    waitLayer.querySelector<HTMLElement>("[data-nur-auth-wait-star]")
      ?.replaceChildren(createV197StartupStar(document));
    waitLayer.hidden = false;
    if (status) status.textContent = form.id === "f4-signup-form" ? "Creating your private Orbit…" : "Returning to your Orbit…";

    const task = form.id === "f4-signup-form"
      ? api.register({
          chosen_name: inputValue(document, "#f4-name"),
          email: inputValue(document, "#f4-email"),
          password: inputValue(document, "#f4-password"),
          consent: document.querySelector<HTMLInputElement>("#f4-consent-check")?.checked === true,
        })
      : api.login({
          email: inputValue(document, "#f4-signin-email"),
          password: inputValue(document, "#f4-signin-password"),
        });

    void task.then(onAuthenticated).catch(error => {
      const detail = errorMessage(error);
      const duplicateOrbit = form.id === "f4-signup-form" && /could not create/i.test(detail);
      const hint = duplicateOrbit
        ? " This email already has an Orbit. Your details are ready in Sign in."
        : /too many attempts/i.test(detail)
          ? " Wait a few minutes, then try once."
          : "";
      const showFailure = (message = `⚠ ${detail}${hint}`) => {
        if (!status) return;
        status.textContent = message;
        status.classList.add("nur-v197-auth-error");
        status.setAttribute("role", "alert");
        if (typeof status.scrollIntoView === "function") {
          status.scrollIntoView({ block: "nearest" });
        }
      };
      showFailure();
      if (duplicateOrbit) {
        const email = inputValue(document, "#f4-email");
        const password = inputValue(document, "#f4-password");
        document.querySelector<HTMLButtonElement>('[data-switch="signin"]')?.click();
        window.setTimeout(() => {
          const signInEmail = document.querySelector<HTMLInputElement>("#f4-signin-email");
          const signInPassword = document.querySelector<HTMLInputElement>("#f4-signin-password");
          if (signInEmail) signInEmail.value = email;
          if (signInPassword) signInPassword.value = password;
          showFailure("This email already has an Orbit. Enter it with the password below.");
          signInPassword?.focus();
        }, 0);
      } else if (status) {
        showFailure();
      }
    }).finally(() => {
      waitLayer.hidden = true;
      form.removeAttribute("aria-busy");
      submit?.removeAttribute("aria-busy");
    });
  };
  document.addEventListener("submit", handler, true);
  return () => {
    document.removeEventListener("submit", handler, true);
    recoveryCleanup();
  };
}

const V197_AUTH_WAIT_ID = "nur-v197-auth-wait";

function ensureV197AuthWaitLayer(document: Document): HTMLElement {
  const existing = document.getElementById(V197_AUTH_WAIT_ID);
  if (existing) return existing;

  const layer = document.createElement("div");
  layer.id = V197_AUTH_WAIT_ID;
  layer.hidden = true;
  layer.setAttribute("role", "status");
  layer.setAttribute("aria-live", "polite");

  const inner = document.createElement("div");
  inner.className = "nur-v197-auth-wait-inner";
  const starHost = document.createElement("div");
  starHost.className = "nur-v197-auth-wait-star";
  starHost.dataset.nurAuthWaitStar = "true";
  const word = document.createElement("div");
  word.className = "nur-v197-auth-wait-word";
  word.textContent = "NUR";
  const message = document.createElement("p");
  message.dataset.nurAuthWaitMessage = "true";
  const note = document.createElement("p");
  note.className = "nur-v197-auth-wait-note";
  note.textContent = "Your private context stays inside its boundary while the universe opens.";
  inner.append(starHost, word, message, note);
  layer.append(inner);
  document.body.append(layer);
  return layer;
}
