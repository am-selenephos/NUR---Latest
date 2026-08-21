import {
  V197ApiClient,
  V197ApiError,
  type V197BillingPlan,
  type V197BillingState,
  type V197BridgeSnapshot,
  type V197CapsuleAnswer,
  type V197CapsuleView,
  type V197CommunityPost,
  type V197ConsultationDetail,
  type V197Memory,
  type V197MemoryCandidate,
  type V197MemorySensitivity,
  type V197MemoryType,
  type V197OwnedCapsule,
  type V197Session,
  type V197TeachNURContribution,
  type V197TeachNURContributionKind,
} from "./v197ApiClient";
import { applyV197Locale, directionForPreference, V197_LOCALE_META, type WritingPreference } from "./v197I18n";
import V197_ADJUNCT_FORENSIC_CSS from "../styles/v197-adjunct-forensic.css?raw";
import { markV197HolographicWordmark } from "./v197Brand";
import { createV197StarSeal } from "./v197StarSeal";
import {
  DRAWER_SECTIONS,
  buildApprovalCard,
  describeRisk,
  groupWorkflows,
  resolveApprovalEditor,
  type AgenticRiskClass,
  type V197AgenticPolicy,
  type V197AgenticWorkflow,
} from "./v197Agentic";

const ROOT_ID = "nur-v197-adjunct-root";
const STYLE_ID = "nur-v197-adjunct-style";
const MEMORY_TYPES: readonly V197MemoryType[] = [
  "EPISODIC",
  "SEMANTIC",
  "PROCEDURAL",
  "SOCIAL",
  "EVIDENCE",
  "SELF",
  "GOAL",
  "META_COGNITIVE",
  "ADAPTIVE_INTERFACE",
];
const MEMORY_SENSITIVITIES: readonly V197MemorySensitivity[] = ["LOW", "PRIVATE", "SENSITIVE"];
const TEACH_NUR_KINDS: readonly V197TeachNURContributionKind[] = [
  "FACT",
  "LIVED_EXPERIENCE",
  "CORRECTION",
  "COUNTEREXAMPLE",
  "LANGUAGE",
  "RESEARCH",
  "EXPERTISE",
  "MISUNDERSTANDING",
  "OUTCOME_EVIDENCE",
];
type AdjunctBackgroundState = {
  previousFocus: HTMLElement | null;
  siblings: Map<HTMLElement, { inert: boolean; ariaHidden: string | null }>;
};
const adjunctBackgrounds = new WeakMap<Document, AdjunctBackgroundState>();
const UNIVERSE_CHAMBERS = [
  { route: "/universe", label: "Live Universe", glyph: "✦" },
  { route: "/universe/insights/candidates", label: "Candidates", glyph: "✧" },
  { route: "/universe/consultation", label: "Consultation", glyph: "◌" },
  { route: "/universe/community", label: "Community", glyph: "◎" },
] as const;

type RefreshSnapshot = () => Promise<V197BridgeSnapshot>;

function isDocumentHTMLElement(document: Document, node: Element | null): node is HTMLElement {
  const HTMLElementConstructor = document.defaultView?.HTMLElement;
  return Boolean(HTMLElementConstructor && node instanceof HTMLElementConstructor);
}

function text(value: unknown, fallback = "Not recorded"): string {
  if (typeof value === "string" && value.trim()) return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  return fallback;
}

function date(value: unknown): string {
  if (typeof value !== "string" || !value) return "No expiry";
  const parsed = new Date(value);
  return Number.isNaN(parsed.getTime()) ? value : parsed.toLocaleString();
}

function activeOrbitId(snapshot: V197BridgeSnapshot): string | null {
  return snapshot.preferences?.active_orbit_id
    ?? snapshot.map?.nodes.find(node => node.kind !== "PERSONAL_BRIDGE")?.id
    ?? snapshot.session.orbit.id
    ?? null;
}

function requestKey(scope: string): string {
  const suffix = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  return `v197-${scope}:${suffix}`;
}

function safeExternalUrl(value: string | null | undefined): URL | null {
  if (!value) return null;
  try {
    const url = new URL(value);
    return url.protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

function openExternalUrl(value: string | null | undefined): boolean {
  const url = safeExternalUrl(value);
  if (!url) return false;
  return window.open(url.toString(), "_blank", "noopener,noreferrer") !== null;
}

function selectOptions<T extends string>(document: Document, select: HTMLSelectElement, values: readonly T[]): void {
  for (const value of values) {
    const option = element(document, "option", undefined, value.replaceAll("_", " ")) as HTMLOptionElement;
    option.value = value;
    select.append(option);
  }
}

function element<K extends keyof HTMLElementTagNameMap>(
  document: Document,
  tag: K,
  className?: string,
  content?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (content !== undefined) node.textContent = content;
  return node;
}

function button(document: Document, label: string, action: string, primary = false): HTMLButtonElement {
  const node = element(document, "button", primary ? "nur-adjunct-button is-primary" : "nur-adjunct-button", label);
  node.type = "button";
  node.dataset.adjunctAction = action;
  return node;
}

function fact(document: Document, label: string, value: string): HTMLElement {
  const node = element(document, "div", "nur-adjunct-fact");
  node.append(element(document, "span", "nur-adjunct-label", label));
  node.append(element(document, "strong", undefined, value));
  return node;
}

function panel(document: Document, eyebrow: string, title: string): HTMLElement {
  const node = element(document, "section", "nur-adjunct-panel");
  node.append(element(document, "p", "nur-adjunct-eyebrow", eyebrow));
  node.append(element(document, "h2", undefined, title));
  return node;
}

function empty(document: Document, title: string, body: string): HTMLElement {
  const node = element(document, "div", "nur-adjunct-empty");
  const seal = createV197StarSeal(document, 20, false);
  seal.classList.add("nur-adjunct-empty-seal");
  node.append(seal, element(document, "strong", undefined, title));
  node.append(element(document, "p", undefined, body));
  return node;
}

function status(document: Document, message: string, tone: "quiet" | "good" | "warn" = "quiet"): HTMLElement {
  const node = element(document, "p", `nur-adjunct-status is-${tone}`, message);
  node.setAttribute("role", "status");
  return node;
}

function setStatus(node: HTMLElement, message: string, tone: "quiet" | "good" | "warn" = "quiet"): void {
  node.textContent = message;
  node.className = `nur-adjunct-status is-${tone}`;
}

function labeledControl(document: Document, label: string, control: HTMLElement): HTMLElement {
  const field = element(document, "label", "nur-adjunct-field");
  field.append(element(document, "span", undefined, label), control);
  return field;
}

function recordId(row: Record<string, unknown>): string {
  return text(row.id, "");
}

function ensureStyle(document: Document): void {
  if (document.getElementById(STYLE_ID)) return;
  const style = element(document, "style");
  style.id = STYLE_ID;
  style.textContent = V197_ADJUNCT_FORENSIC_CSS;
  document.head.append(style);
}

function isolateAdjunctBackground(document: Document, root: HTMLElement): void {
  let state = adjunctBackgrounds.get(document);
  if (!state) {
    state = {
      previousFocus: isDocumentHTMLElement(document, document.activeElement) ? document.activeElement : null,
      siblings: new Map(),
    };
    adjunctBackgrounds.set(document, state);
  }
  for (const child of Array.from(document.body.children)) {
    if (!isDocumentHTMLElement(document, child) || child === root) continue;
    if (!state.siblings.has(child)) {
      state.siblings.set(child, { inert: child.inert, ariaHidden: child.getAttribute("aria-hidden") });
    }
    child.inert = true;
    child.setAttribute("aria-hidden", "true");
  }
}

function restoreAdjunctBackground(document: Document): void {
  const state = adjunctBackgrounds.get(document);
  if (!state) return;
  for (const [sibling, previous] of state.siblings) {
    sibling.inert = previous.inert;
    if (previous.ariaHidden === null) sibling.removeAttribute("aria-hidden");
    else sibling.setAttribute("aria-hidden", previous.ariaHidden);
  }
  adjunctBackgrounds.delete(document);
  if (state.previousFocus?.isConnected) state.previousFocus.focus({ preventScroll: true });
}

function universeChamberNav(document: Document): HTMLElement {
  const current = window.location.pathname;
  const nav = element(document, "nav", "nur-adjunct-universe-nav");
  nav.setAttribute("aria-label", "Universe chambers");
  for (const chamber of UNIVERSE_CHAMBERS) {
    const control = button(document, `${chamber.glyph} ${chamber.label}`, `universe-chamber-${chamber.label.toLowerCase()}`);
    const selected = chamber.route === "/universe"
      ? current === chamber.route
      : current === chamber.route || current.startsWith(`${chamber.route}/`);
    if (selected) control.setAttribute("aria-current", "page");
    control.addEventListener("click", () => navigate(chamber.route));
    nav.append(control);
  }
  return nav;
}

function mount(document: Document, title: string, subtitle: string, backRoute = "/systems"): HTMLElement {
  document.getElementById(ROOT_ID)?.remove();
  ensureStyle(document);
  const root = element(document, "div");
  root.id = ROOT_ID;
  root.dataset.v197NativeAdjunct = "true";
  const shell = element(document, "main", "nur-adjunct-shell");
  const topbar = element(document, "header", "nur-adjunct-topbar");
  const back = element(
    document,
    "button",
    "nur-adjunct-back",
    backRoute.startsWith("/universe") ? "← Live Universe" : "← Return to NUR",
  );
  back.type = "button";
  back.dataset.adjunctRoute = backRoute;
  const brand = element(document, "div", "nur-adjunct-brand", "NUR");
  markV197HolographicWordmark(brand);
  const brandSeal = createV197StarSeal(document, 24, true);
  brandSeal.classList.add("nur-adjunct-brand-seal");
  brand.prepend(brandSeal);
  topbar.append(back, brand, element(document, "span", "nur-adjunct-privacy", "Private by default. Shared only by choice."));
  const hero = element(document, "section", "nur-adjunct-hero");
  hero.append(element(document, "p", "nur-adjunct-eyebrow", "Neural Upgrade Rewiring"));
  hero.append(element(document, "h1", undefined, title));
  hero.append(element(document, "p", "nur-adjunct-subtitle", subtitle));
  shell.append(topbar);
  if (window.location.pathname.startsWith("/universe/")) shell.append(universeChamberNav(document));
  shell.append(hero);
  root.append(shell);
  document.body.append(root);
  isolateAdjunctBackground(document, root);
  back.focus({ preventScroll: true });
  back.addEventListener("click", () => {
    window.history.pushState({}, "", backRoute);
    window.dispatchEvent(new PopStateEvent("popstate"));
  });
  return shell;
}

async function renderSettings(
  document: Document,
  api: V197ApiClient,
  snapshot: V197BridgeSnapshot,
  refreshSnapshot: RefreshSnapshot,
): Promise<void> {
  const shell = mount(document, "Your NUR, held on your terms.", "Language, model access, motion and learning preferences stay in your owner-scoped ledger.");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const provider = panel(document, "Provider boundary", "Intelligence connection");
  const providerState = snapshot.health?.ai_provider === "openai" ? "OPENAI_CONFIGURED" : "DISABLED";
  provider.append(element(document, "div", "nur-adjunct-facts"));
  provider.querySelector(".nur-adjunct-facts")?.append(
    fact(document, "Provider", providerState),
    fact(document, "Execution", "Server-side only"),
    fact(document, "Prompt logging", "Off by default"),
  );
  provider.append(status(document, providerState === "OPENAI_CONFIGURED"
    ? "The backend can answer Talk requests. No key is exposed to this document."
    : "AI is not connected. Run the local configuration script, then start NUR in OpenAI mode.", providerState === "OPENAI_CONFIGURED" ? "good" : "warn"));

  const language = panel(document, "Language and voice", "How NUR speaks with you");
  const localeLabel = element(document, "label", "nur-adjunct-field");
  localeLabel.append(element(document, "span", undefined, "Interface language"));
  const locale = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  locale.dataset.adjunctControl = "locale";
  for (const row of V197_LOCALE_META) {
    const option = element(document, "option", undefined, `${row.label} · ${row.status === "polished_beta" ? "polished beta" : "draft"}`) as HTMLOptionElement;
    option.value = row.locale;
    option.selected = row.locale === (snapshot.preferences?.locale ?? snapshot.session.profile.locale ?? "en");
    locale.append(option);
  }
  localeLabel.append(locale);
  const writingLabel = element(document, "label", "nur-adjunct-field");
  writingLabel.append(element(document, "span", undefined, "Writing preference"));
  const writing = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  writing.dataset.adjunctControl = "writing-preference";
  for (const [value, label] of [["default", "Language default"], ["roman", "Roman writing"], ["script", "Native script"]]) {
    const option = element(document, "option", undefined, label) as HTMLOptionElement;
    option.value = value;
    option.selected = value === (snapshot.preferences?.writing_preference ?? "default");
    writing.append(option);
  }
  writingLabel.append(writing);
  language.append(localeLabel, writingLabel);
  language.append(status(document, "Roman Urdu is stored as locale=ur with writing_preference=roman. Draft locales are labelled honestly."));

  const experience = panel(document, "Presence", "Motion, sound and Omega");
  const toggle = (label: string, key: string, checked: boolean) => {
    const row = element(document, "label", "nur-adjunct-toggle");
    row.append(element(document, "span", undefined, label));
    const input = element(document, "input") as HTMLInputElement;
    input.type = "checkbox";
    input.checked = checked;
    input.dataset.adjunctControl = key;
    row.append(input);
    return row;
  };
  experience.append(
    toggle("Quiet interface sound", "sound", snapshot.preferences?.sound_enabled ?? true),
    toggle("Reduce visual motion", "reduced-effects", snapshot.preferences?.reduced_effects ?? false),
    toggle("Omega research memory", "omega", snapshot.preferences?.omega_enabled ?? true),
  );

  const ownership = panel(document, "Owner data", "Export the complete owner-scoped ledger");
  ownership.append(element(document, "p", "nur-adjunct-boundary", "The download includes deterministic JSON, a SHA-256 manifest checksum, and explicit status for any unavailable stored object. Secret hashes are excluded."));
  const ownershipActions = element(document, "div", "nur-adjunct-actions");
  const exportButton = button(document, "Export my NUR", "settings-export");
  const exportState = status(document, "Nothing is marked exported until the API returns the real owner manifest.");
  ownershipActions.append(exportButton);
  ownership.append(ownershipActions, exportState);
  exportButton.addEventListener("click", async () => {
    exportButton.disabled = true;
    exportState.textContent = "Preparing the owner-scoped export…";
    try {
      const exported = await api.downloadOwnerExport();
      const href = URL.createObjectURL(exported.blob);
      const anchor = element(document, "a") as HTMLAnchorElement;
      anchor.href = href;
      anchor.download = exported.filename;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      window.setTimeout(() => URL.revokeObjectURL(href), 0);
      exportState.textContent = `Export downloaded. SHA-256 ${exported.checksum}.`;
      exportState.className = "nur-adjunct-status is-good";
    } catch (error) {
      exportState.textContent = error instanceof Error ? error.message : "Owner export could not be prepared.";
      exportState.className = "nur-adjunct-status is-warn";
    } finally {
      exportButton.disabled = false;
    }
  });

  const security = panel(document, "Password", "Change it and revoke every active session");
  const passwordField = (label: string, control: string) => {
    const field = element(document, "label", "nur-adjunct-field");
    field.append(element(document, "span", undefined, label));
    const input = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
    input.type = "password";
    input.autocomplete = control === "current-password" || control === "delete-password"
      ? "current-password"
      : "new-password";
    input.minLength = 8;
    input.maxLength = 256;
    input.dataset.adjunctControl = control;
    field.append(input);
    return field;
  };
  security.append(
    passwordField("Current password", "current-password"),
    passwordField("New password", "new-password"),
    passwordField("Confirm new password", "confirm-password"),
  );
  const securityActions = element(document, "div", "nur-adjunct-actions");
  const changePassword = button(document, "Change password", "settings-change-password", true);
  const securityState = status(document, "A successful change signs every device out, including this one.");
  securityActions.append(changePassword);
  security.append(securityActions, securityState);
  changePassword.addEventListener("click", async () => {
    const current = (security.querySelector('[data-adjunct-control="current-password"]') as HTMLInputElement).value;
    const next = (security.querySelector('[data-adjunct-control="new-password"]') as HTMLInputElement).value;
    const confirmation = (security.querySelector('[data-adjunct-control="confirm-password"]') as HTMLInputElement).value;
    if (current.length < 1 || next.length < 8) {
      securityState.textContent = "Enter the current password and a new password of at least 8 characters.";
      securityState.className = "nur-adjunct-status is-warn";
      return;
    }
    if (next !== confirmation) {
      securityState.textContent = "The two new passwords do not match.";
      securityState.className = "nur-adjunct-status is-warn";
      return;
    }
    changePassword.disabled = true;
    securityState.textContent = "Changing password and revoking sessions…";
    try {
      await api.changePassword(current, next);
      securityState.textContent = "Password changed. Returning to Sign in…";
      securityState.className = "nur-adjunct-status is-good";
      window.setTimeout(() => window.location.replace("/auth"), 400);
    } catch (error) {
      securityState.textContent = error instanceof Error ? error.message : "Password could not be changed.";
      securityState.className = "nur-adjunct-status is-warn";
      changePassword.disabled = false;
    }
  });

  const sessionsPanel = panel(document, "Sessions", "Devices with access to this Orbit");
  const sessionList = element(document, "div", "nur-adjunct-list");
  const sessionActions = element(document, "div", "nur-adjunct-actions");
  const revokeOthers = button(document, "Sign out other devices", "settings-revoke-other-sessions");
  const sessionState = status(document, "Loading the real session ledger…");
  sessionActions.append(revokeOthers);
  sessionsPanel.append(sessionList, sessionActions, sessionState);
  const loadSessions = async () => {
    sessionList.replaceChildren();
    try {
      const sessions = await api.ownerSessions();
      for (const ownerSession of sessions) {
        const row = element(document, "div", "nur-adjunct-row");
        const heading = element(document, "div", "nur-adjunct-row-head");
        heading.append(
          element(document, "strong", undefined, ownerSession.current ? "This device" : "Signed-in device"),
          element(document, "span", "nur-adjunct-chip", ownerSession.state),
        );
        row.append(heading, element(document, "p", undefined, `Started ${date(ownerSession.created_at)} · Expires ${date(ownerSession.expires_at)}`));
        if (!ownerSession.current && ownerSession.state === "active") {
          const revoke = button(document, "Revoke session", `settings-revoke-session-${ownerSession.id}`);
          revoke.addEventListener("click", async () => {
            revoke.disabled = true;
            try {
              await api.revokeSession(ownerSession.id);
              await loadSessions();
              sessionState.textContent = "Session revoked.";
              sessionState.className = "nur-adjunct-status is-good";
            } catch (error) {
              sessionState.textContent = error instanceof Error ? error.message : "Session could not be revoked.";
              sessionState.className = "nur-adjunct-status is-warn";
              revoke.disabled = false;
            }
          });
          row.append(element(document, "div", "nur-adjunct-actions"));
          row.querySelector(".nur-adjunct-actions")?.append(revoke);
        }
        sessionList.append(row);
      }
      if (!sessions.length) sessionList.append(empty(document, "No session row returned", "The API did not report an active browser session."));
      sessionState.textContent = `${sessions.length} owner-scoped session${sessions.length === 1 ? "" : "s"}.`;
    } catch (error) {
      sessionList.append(empty(document, "Session ledger unavailable", "No device is shown without an API response."));
      sessionState.textContent = error instanceof Error ? error.message : "Sessions could not be loaded.";
      sessionState.className = "nur-adjunct-status is-warn";
    }
  };
  revokeOthers.addEventListener("click", async () => {
    revokeOthers.disabled = true;
    try {
      const result = await api.revokeOtherSessions();
      await loadSessions();
      sessionState.textContent = `${result.revoked_session_count} other session${result.revoked_session_count === 1 ? "" : "s"} revoked.`;
      sessionState.className = "nur-adjunct-status is-good";
    } catch (error) {
      sessionState.textContent = error instanceof Error ? error.message : "Other sessions could not be revoked.";
      sessionState.className = "nur-adjunct-status is-warn";
    } finally {
      revokeOthers.disabled = false;
    }
  });
  await loadSessions();

  const deletion = panel(document, "Danger zone", "Permanently delete this NUR account");
  deletion.classList.add("is-danger");
  const deletionPassword = passwordField("Current password", "delete-password");
  const deletionConfirmationField = element(document, "label", "nur-adjunct-field");
  deletionConfirmationField.append(element(document, "span", undefined, "Type DELETE MY NUR ACCOUNT"));
  const deletionConfirmation = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  deletionConfirmation.autocomplete = "off";
  deletionConfirmation.dataset.adjunctControl = "delete-confirmation";
  deletionConfirmation.maxLength = 64;
  deletionConfirmationField.append(deletionConfirmation);
  const deletionActions = element(document, "div", "nur-adjunct-actions");
  const deleteButton = button(document, "Delete account permanently", "settings-delete");
  const deletionState = status(document, "Local files must be removed before the database account can be deleted. External provider erasure is never claimed unless a provider adapter performs it.");
  deletionActions.append(deleteButton);
  deletion.append(deletionPassword, deletionConfirmationField, deletionActions, deletionState);
  deleteButton.addEventListener("click", async () => {
    const password = (deletion.querySelector('[data-adjunct-control="delete-password"]') as HTMLInputElement).value;
    if (!password || deletionConfirmation.value !== "DELETE MY NUR ACCOUNT") {
      deletionState.textContent = 'Enter the current password and type "DELETE MY NUR ACCOUNT" exactly.';
      deletionState.className = "nur-adjunct-status is-warn";
      return;
    }
    if (!window.confirm("Permanently delete this NUR account and all owner-scoped data? This cannot be undone.")) return;
    deleteButton.disabled = true;
    deletionState.textContent = "Deleting owner data and revoking sessions…";
    try {
      const result = await api.deleteAccount(password, deletionConfirmation.value);
      deletionState.textContent = result.external_provider_deletion.detail;
      deletionState.className = "nur-adjunct-status is-good";
      window.setTimeout(() => window.location.replace("/auth"), 900);
    } catch (error) {
      deletionState.textContent = error instanceof Error ? error.message : "Account deletion did not complete.";
      deletionState.className = "nur-adjunct-status is-warn";
      deleteButton.disabled = false;
    }
  });

  const savePanel = panel(document, "Persisted owner preference", "Return with the same language");
  savePanel.classList.add("is-wide");
  const actions = element(document, "div", "nur-adjunct-actions");
  const save = button(document, "Save preferences", "settings-save", true);
  actions.append(save);
  const saveState = status(document, "Changes are stored only in your owner-scoped preference row.");
  savePanel.append(actions, saveState);
  save.addEventListener("click", async () => {
    save.disabled = true;
    saveState.textContent = "Saving…";
    try {
      const selectedLocale = locale.value;
      const selectedWriting = writing.value as WritingPreference;
      await api.patchPreferences({
        locale: selectedLocale,
        writing_preference: selectedWriting,
        sound_enabled: (experience.querySelector('[data-adjunct-control="sound"]') as HTMLInputElement).checked,
        reduced_effects: (experience.querySelector('[data-adjunct-control="reduced-effects"]') as HTMLInputElement).checked,
        omega_enabled: (experience.querySelector('[data-adjunct-control="omega"]') as HTMLInputElement).checked,
      });
      const next = await refreshSnapshot();
      applyV197Locale(document, selectedLocale, selectedWriting);
      document.documentElement.dir = directionForPreference(selectedLocale, selectedWriting);
      saveState.textContent = "Saved. NUR will return in this language and writing style.";
      saveState.className = "nur-adjunct-status is-good";
      if (next.preferences) snapshot.preferences = next.preferences;
    } catch (error) {
      saveState.textContent = error instanceof Error ? error.message : "Preferences could not be saved.";
      saveState.className = "nur-adjunct-status is-warn";
    } finally {
      save.disabled = false;
    }
  });

  grid.append(provider, language, experience, security, sessionsPanel, ownership, deletion, savePanel);
}

async function renderMemory(document: Document, api: V197ApiClient, snapshot: V197BridgeSnapshot): Promise<void> {
  const shell = mount(
    document,
    "Memory stays proposed until you choose it.",
    "Candidate inferences, accepted memories and owner-written context remain separate, editable and deletable inside your private ledger.",
  );
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const orbitId = activeOrbitId(snapshot);

  const create = panel(document, "Owner-written memory", "Hold one thing deliberately");
  create.classList.add("is-wide");
  const createText = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  createText.dataset.adjunctControl = "memory-create-text";
  createText.placeholder = "Write only what you want NUR to remember...";
  const createType = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  createType.dataset.adjunctControl = "memory-create-type";
  selectOptions(document, createType, MEMORY_TYPES);
  createType.value = "SEMANTIC";
  const createSensitivity = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  createSensitivity.dataset.adjunctControl = "memory-create-sensitivity";
  selectOptions(document, createSensitivity, MEMORY_SENSITIVITIES);
  createSensitivity.value = "PRIVATE";
  const createAction = button(document, "Remember by my choice", "memory-create", true);
  createAction.disabled = !orbitId;
  const createState = status(
    document,
    orbitId ? "Nothing is stored until you press this control." : "Choose an active Orbit before creating a memory.",
    orbitId ? "quiet" : "warn",
  );
  const createActions = element(document, "div", "nur-adjunct-actions");
  createActions.append(createAction);
  create.append(
    element(document, "p", "nur-adjunct-boundary", "Private means owner-scoped. Sensitive memory remains excluded from sharing unless you later select it through a separate boundary."),
    labeledControl(document, "Memory", createText),
    labeledControl(document, "Type", createType),
    labeledControl(document, "Sensitivity", createSensitivity),
    createActions,
    createState,
  );

  const candidates = panel(document, "Review queue", "Memory candidates");
  const candidateState = status(document, "Candidates are not memories until you approve them.");
  const candidateList = element(document, "div", "nur-adjunct-list");
  candidates.append(candidateState, candidateList);

  const accepted = panel(document, "Owner ledger", "Accepted memories");
  const memoryState = status(document, "Edits create a persisted version; deletion removes the owner memory.");
  const memoryList = element(document, "div", "nur-adjunct-list");
  accepted.append(memoryState, memoryList);

  const renderCandidates = (rows: V197MemoryCandidate[]) => {
    candidateList.replaceChildren();
    if (!rows.length) {
      candidateList.append(empty(document, "No memory candidate is waiting", "NUR has not proposed an owner memory, or every proposal has already been reviewed."));
      return;
    }
    for (const candidate of rows) {
      const row = element(document, "article", "nur-adjunct-row");
      const head = element(document, "div", "nur-adjunct-row-head");
      head.append(
        element(document, "strong", undefined, candidate.candidate_text),
        element(document, "span", "nur-adjunct-chip", candidate.status),
      );
      row.append(head, element(document, "p", undefined, `${candidate.memory_type} · ${candidate.sensitivity} · ${candidate.provenance_label}`));
      if (["PENDING", "PENDING_REVIEW", "CANDIDATE", "EDITED"].includes(candidate.status)) {
        const correctedText = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
        correctedText.value = candidate.candidate_text;
        correctedText.dataset.adjunctControl = `memory-candidate-text-${candidate.id}`;
        const reason = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
        reason.placeholder = "Why this correction is needed";
        reason.dataset.adjunctControl = `memory-candidate-reason-${candidate.id}`;
        const actions = element(document, "div", "nur-adjunct-actions");
        const approve = button(document, "Approve as memory", `memory-candidate-approve-${candidate.id}`, true);
        const correct = button(document, "Correct proposal", `memory-candidate-correct-${candidate.id}`);
        const reject = button(document, "Reject proposal", `memory-candidate-reject-${candidate.id}`);
        actions.append(approve, correct, reject);
        const controls = [approve, correct, reject];
        const act = async (action: "approve" | "correct" | "reject") => {
          controls.forEach(control => { control.disabled = true; });
          setStatus(candidateState, `${action === "approve" ? "Approving" : action === "correct" ? "Correcting" : "Rejecting"} owner candidate...`);
          try {
            if (action === "approve") await api.approveMemoryCandidate(candidate.id);
            else if (action === "reject") await api.rejectMemoryCandidate(candidate.id);
            else {
              const canonicalText = correctedText.value.trim();
              const correctionReason = reason.value.trim();
              if (!canonicalText || !correctionReason) throw new Error("A corrected memory and a reason are both required.");
              await api.correctMemoryCandidate(candidate.id, {
                canonical_text: canonicalText,
                correction_reason: correctionReason,
              });
            }
            setStatus(candidateState, "Owner candidate review persisted.", "good");
            await refreshLists();
          } catch (error) {
            setStatus(candidateState, error instanceof Error ? error.message : "The candidate action failed.", "warn");
            controls.forEach(control => { control.disabled = false; });
          }
        };
        approve.addEventListener("click", () => void act("approve"));
        correct.addEventListener("click", () => void act("correct"));
        reject.addEventListener("click", () => void act("reject"));
        row.append(
          labeledControl(document, "Corrected wording", correctedText),
          labeledControl(document, "Correction reason", reason),
          actions,
        );
      }
      candidateList.append(row);
    }
  };

  const renderMemories = (rows: V197Memory[]) => {
    memoryList.replaceChildren();
    if (!rows.length) {
      memoryList.append(empty(document, "No accepted memory", "Create one deliberately or approve a candidate. NUR does not backfill an invented memory."));
      return;
    }
    for (const memory of rows) {
      const row = element(document, "article", "nur-adjunct-row");
      const head = element(document, "div", "nur-adjunct-row-head");
      head.append(
        element(document, "strong", undefined, memory.canonical_text),
        element(document, "span", "nur-adjunct-chip", `${memory.status} · v${memory.version}`),
      );
      const canonicalText = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
      canonicalText.value = memory.canonical_text;
      canonicalText.dataset.adjunctControl = `memory-text-${memory.id}`;
      const memoryType = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
      selectOptions(document, memoryType, MEMORY_TYPES);
      if (MEMORY_TYPES.includes(memory.memory_type as V197MemoryType)) memoryType.value = memory.memory_type;
      const sensitivity = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
      selectOptions(document, sensitivity, MEMORY_SENSITIVITIES);
      if (MEMORY_SENSITIVITIES.includes(memory.sensitivity as V197MemorySensitivity)) sensitivity.value = memory.sensitivity;
      const actions = element(document, "div", "nur-adjunct-actions");
      const save = button(document, "Save owner edit", `memory-save-${memory.id}`, true);
      const remove = button(document, "Delete memory", `memory-delete-${memory.id}`);
      actions.append(save, remove);
      save.addEventListener("click", async () => {
        const value = canonicalText.value.trim();
        if (!value) {
          setStatus(memoryState, "A memory cannot be blank.", "warn");
          return;
        }
        save.disabled = true;
        remove.disabled = true;
        try {
          await api.patchMemory(memory.id, {
            canonical_text: value,
            memory_type: memoryType.value as V197MemoryType,
            sensitivity: sensitivity.value as V197MemorySensitivity,
          });
          setStatus(memoryState, "Owner edit persisted as the next memory version.", "good");
          await refreshLists();
        } catch (error) {
          setStatus(memoryState, error instanceof Error ? error.message : "The memory edit failed.", "warn");
          save.disabled = false;
          remove.disabled = false;
        }
      });
      remove.addEventListener("click", async () => {
        if (!window.confirm("Delete this owner memory? This removes it from active NUR use.")) return;
        save.disabled = true;
        remove.disabled = true;
        try {
          await api.deleteMemory(memory.id);
          setStatus(memoryState, "Memory deleted from the owner ledger.", "good");
          await refreshLists();
        } catch (error) {
          setStatus(memoryState, error instanceof Error ? error.message : "The memory could not be deleted.", "warn");
          save.disabled = false;
          remove.disabled = false;
        }
      });
      row.append(
        head,
        element(document, "p", undefined, `${memory.memory_type} · ${memory.sensitivity} · ${memory.provenance_label}`),
        labeledControl(document, "Canonical wording", canonicalText),
        labeledControl(document, "Type", memoryType),
        labeledControl(document, "Sensitivity", sensitivity),
        actions,
      );
      memoryList.append(row);
    }
  };

  const refreshLists = async () => {
    const [candidateRows, memoryRows] = await Promise.all([
      api.memoryCandidates(undefined, 100),
      api.memories({ includeRetired: false, limit: 100 }),
    ]);
    renderCandidates(candidateRows);
    renderMemories(memoryRows);
  };

  createAction.addEventListener("click", async () => {
    const canonicalText = createText.value.trim();
    if (!canonicalText || !orbitId) {
      setStatus(createState, orbitId ? "Write the memory you want NUR to hold." : "Choose an active Orbit first.", "warn");
      return;
    }
    createAction.disabled = true;
    setStatus(createState, "Writing only this owner-approved memory...");
    try {
      await api.createMemory({
        canonical_text: canonicalText,
        structured_value: {},
        orbit_id: orbitId,
        memory_type: createType.value as V197MemoryType,
        sensitivity: createSensitivity.value as V197MemorySensitivity,
        confidence: 1,
      });
      createText.value = "";
      setStatus(createState, "Memory persisted by your explicit choice.", "good");
      await refreshLists();
    } catch (error) {
      setStatus(createState, error instanceof Error ? error.message : "The memory could not be created.", "warn");
    } finally {
      createAction.disabled = false;
    }
  });

  grid.append(create, candidates, accepted);
  await refreshLists();
}

async function renderTeachNUR(document: Document, api: V197ApiClient, snapshot: V197BridgeSnapshot): Promise<void> {
  const shell = mount(
    document,
    "Teach NUR without surrendering authority.",
    "Your contribution enters an owner-scoped review ledger. Consent is explicit, reversible and never authorizes model training by implication.",
  );
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const orbitId = activeOrbitId(snapshot);

  const contribute = panel(document, "Explicit contribution", "Offer one bounded correction or insight");
  contribute.classList.add("is-wide");
  const kind = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  kind.dataset.adjunctControl = "teach-kind";
  selectOptions(document, kind, TEACH_NUR_KINDS);
  kind.value = "CORRECTION";
  const content = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  content.dataset.adjunctControl = "teach-content";
  content.placeholder = "What should NUR learn, question or correct?";
  const scope = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  scope.dataset.adjunctControl = "teach-consent-scope";
  for (const [value, label] of [
    ["PRIVATE_OWNER", "Private owner retrieval only"],
    ["DEIDENTIFIED_RESEARCH", "Deidentified research review"],
  ] as const) {
    const option = element(document, "option", undefined, label) as HTMLOptionElement;
    option.value = value;
    scope.append(option);
  }
  const sensitivity = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  sensitivity.dataset.adjunctControl = "teach-sensitivity";
  selectOptions(document, sensitivity, MEMORY_SENSITIVITIES);
  sensitivity.value = "PRIVATE";
  const consentRow = element(document, "label", "nur-adjunct-toggle");
  const consent = element(document, "input") as HTMLInputElement;
  consent.type = "checkbox";
  consent.dataset.adjunctControl = "teach-consent";
  consentRow.append(
    element(document, "span", undefined, "I explicitly consent to this selected contribution scope."),
    consent,
  );
  const scopeState = status(document, "Private owner scope keeps the contribution inside your own retrieval ledger.");
  const createAction = button(document, "Submit to review ledger", "teach-create", true);
  createAction.disabled = true;
  const createState = status(document, "No contribution is submitted without the checked consent control.");
  const actions = element(document, "div", "nur-adjunct-actions");
  actions.append(createAction);
  contribute.append(
    element(document, "p", "nur-adjunct-boundary", "Deidentified research consent permits governed review only. It does not authorize foundation-model training, institutional promotion or public attribution."),
    labeledControl(document, "Contribution kind", kind),
    labeledControl(document, "Contribution", content),
    labeledControl(document, "Consent scope", scope),
    labeledControl(document, "Sensitivity", sensitivity),
    scopeState,
    consentRow,
    actions,
    createState,
  );

  const ledger = panel(document, "Owner review ledger", "Your contributions");
  ledger.classList.add("is-wide");
  const ledgerState = status(document, "Withdrawal closes future use while preserving the required consent audit.");
  const list = element(document, "div", "nur-adjunct-list");
  ledger.append(ledgerState, list);

  const renderRows = (rows: V197TeachNURContribution[]) => {
    list.replaceChildren();
    if (!rows.length) {
      list.append(empty(document, "No contribution submitted", "NUR does not invent a teaching history. Your first explicit contribution will appear here."));
      return;
    }
    for (const contribution of rows) {
      const row = element(document, "article", "nur-adjunct-row");
      const head = element(document, "div", "nur-adjunct-row-head");
      head.append(
        element(document, "strong", undefined, contribution.content),
        element(document, "span", "nur-adjunct-chip", contribution.status),
      );
      row.append(
        head,
        element(document, "p", undefined, `${contribution.contribution_kind} · ${contribution.consent_scope} · ${contribution.sensitivity}`),
        element(document, "p", undefined, `Model training: ${contribution.model_training_status} · Promotion: ${contribution.institutional_promotion_status}`),
      );
      if (contribution.consent_granted && !["WITHDRAWN", "REJECTED", "ROLLED_BACK"].includes(contribution.status)) {
        const withdraw = button(document, "Withdraw consent", `teach-withdraw-${contribution.id}`);
        const rowActions = element(document, "div", "nur-adjunct-actions");
        rowActions.append(withdraw);
        withdraw.addEventListener("click", async () => {
          withdraw.disabled = true;
          try {
            await api.reviewTeachNURContribution(
              contribution.id,
              { action: "WITHDRAW_CONSENT", review_note: "Withdrawn by owner from the V197 contribution ledger." },
              requestKey(`teach-withdraw-${contribution.id}`),
            );
            setStatus(ledgerState, "Consent withdrawn. The audit remains, but future use is closed.", "good");
            await refreshLedger();
          } catch (error) {
            setStatus(ledgerState, error instanceof Error ? error.message : "Consent could not be withdrawn.", "warn");
            withdraw.disabled = false;
          }
        });
        row.append(rowActions);
      }
      list.append(row);
    }
  };

  const refreshLedger = async () => renderRows(await api.teachNURContributions(undefined, 100));

  const syncConsent = () => {
    createAction.disabled = !consent.checked;
    setStatus(
      createState,
      consent.checked
        ? "Consent is explicit for this submission and can later be withdrawn."
        : "No contribution is submitted without the checked consent control.",
      consent.checked ? "good" : "quiet",
    );
  };
  consent.addEventListener("change", syncConsent);
  scope.addEventListener("change", () => {
    setStatus(
      scopeState,
      scope.value === "DEIDENTIFIED_RESEARCH"
        ? "This permits governed deidentified research review, not model training or public promotion."
        : "Private owner scope keeps the contribution inside your own retrieval ledger.",
    );
    consent.checked = false;
    syncConsent();
  });

  createAction.addEventListener("click", async () => {
    const contribution = content.value.trim();
    if (!consent.checked || !contribution) {
      setStatus(createState, consent.checked ? "Write the contribution you want reviewed." : "Explicit consent is required.", "warn");
      return;
    }
    createAction.disabled = true;
    setStatus(createState, "Submitting only this bounded contribution...");
    try {
      await api.createTeachNURContribution({
        contribution_kind: kind.value as V197TeachNURContributionKind,
        content: contribution,
        orbit_id: orbitId,
        language_tag: snapshot.preferences?.locale ?? snapshot.session.profile.locale ?? "und",
        consent_scope: scope.value as "PRIVATE_OWNER" | "DEIDENTIFIED_RESEARCH",
        consent_granted: true,
        consent_policy_version: "teach-nur-v1",
        sensitivity: sensitivity.value as V197MemorySensitivity,
        confidence: 1,
        source_refs: [],
      }, requestKey("teach-create"));
      content.value = "";
      consent.checked = false;
      setStatus(createState, "Contribution entered your owner review ledger.", "good");
      await refreshLedger();
    } catch (error) {
      setStatus(createState, error instanceof Error ? error.message : "The contribution could not be submitted.", "warn");
    } finally {
      createAction.disabled = !consent.checked;
    }
  });

  grid.append(contribute, ledger);
  await refreshLedger();
}

function billingPrice(plan: V197BillingPlan): string {
  if (plan.is_free) return "Free";
  try {
    return new Intl.NumberFormat(undefined, {
      style: "currency",
      currency: plan.currency,
      maximumFractionDigits: 2,
    }).format(plan.price_minor / 100);
  } catch {
    return `${plan.currency} ${(plan.price_minor / 100).toFixed(2)}`;
  }
}

function billingLegalLinks(document: Document, state: V197BillingState): HTMLElement {
  const links = element(document, "div", "nur-adjunct-actions");
  for (const [label, value] of [
    ["Terms", state.terms_url],
    ["Privacy", state.privacy_url],
    ["Refund policy", state.refund_policy_url],
  ] as const) {
    const url = safeExternalUrl(value);
    if (!url) continue;
    const anchor = element(document, "a", "nur-adjunct-button", label) as HTMLAnchorElement;
    anchor.href = url.toString();
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    links.append(anchor);
  }
  if (!links.childElementCount) {
    links.append(status(document, "Provider legal links are not configured. Paid checkout remains unavailable until they are present.", "warn"));
  }
  return links;
}

function externalFallback(document: Document, container: HTMLElement, value: string, label: string): boolean {
  const url = safeExternalUrl(value);
  if (!url) return false;
  container.querySelector("[data-adjunct-external-fallback]")?.remove();
  const anchor = element(document, "a", "nur-adjunct-button", label) as HTMLAnchorElement;
  anchor.href = url.toString();
  anchor.target = "_blank";
  anchor.rel = "noopener noreferrer";
  anchor.dataset.adjunctExternalFallback = "true";
  container.append(anchor);
  return true;
}

async function renderBilling(document: Document, api: V197ApiClient): Promise<void> {
  const [plans, billing] = await Promise.all([api.billingPlans(), api.billingSubscription()]);
  const shell = mount(
    document,
    "Billing without hidden authority.",
    "Plans, entitlements, renewal state and provider handoff come from the billing ledger. NUR never fabricates a purchase or silently changes your subscription.",
  );
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const current = panel(document, "Owner subscription", billing.subscription ? billing.subscription.plan_code : "Orbit Scan Free");
  const currentFacts = element(document, "div", "nur-adjunct-facts");
  currentFacts.append(
    fact(document, "Provider", billing.subscription?.provider ?? (billing.provider_configured ? "Configured, no subscription" : "Disabled")),
    fact(document, "Status", billing.subscription?.status ?? "FREE"),
    fact(document, "Renews", billing.subscription ? (billing.subscription.cancel_at_period_end ? "No · cancellation scheduled" : "Provider managed") : "No paid renewal"),
    fact(document, "Paid through", date(billing.subscription?.current_period_end)),
  );
  const portal = button(document, "Manage subscription", "billing-portal");
  portal.disabled = !billing.portal_available;
  const portalState = status(document, billing.cancellation_note, billing.provider_configured ? "quiet" : "warn");
  const currentActions = element(document, "div", "nur-adjunct-actions");
  currentActions.append(portal);
  current.append(currentFacts, currentActions, portalState, billingLegalLinks(document, billing));
  portal.addEventListener("click", async () => {
    portal.disabled = true;
    setStatus(portalState, "Requesting a short-lived provider portal...");
    try {
      const response = await api.billingPortal();
      const url = safeExternalUrl(response.url);
      if (!url) {
        setStatus(portalState, "The API did not return a valid HTTPS portal URL. Nothing was opened.", "warn");
      } else if (!openExternalUrl(url.toString())) {
        externalFallback(document, currentActions, url.toString(), "Open secure billing portal");
        setStatus(portalState, "Your browser blocked the new tab. Use the secure provider link shown beside this control.", "warn");
      } else {
        setStatus(portalState, `Provider portal opened in a new tab. Link expires ${date(response.expires_at)}.`, "good");
      }
    } catch (error) {
      setStatus(portalState, error instanceof Error ? error.message : "The provider portal is unavailable.", "warn");
    } finally {
      portal.disabled = !billing.portal_available;
    }
  });

  const entitlements = panel(document, "Server projection", "Current entitlements");
  const entitlementList = element(document, "div", "nur-adjunct-list");
  if (!billing.entitlements.length) {
    entitlementList.append(empty(document, "No paid entitlement projection", "Free access remains governed by the server. No paid feature is implied."));
  }
  for (const entitlement of billing.entitlements) {
    const row = element(document, "div", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(
      element(document, "strong", undefined, entitlement.feature_key.replaceAll("_", " ")),
      element(document, "span", "nur-adjunct-chip", entitlement.allowed ? "ALLOWED" : "NOT INCLUDED"),
    );
    const usage = entitlement.usage_limit === null
      ? `${entitlement.usage_consumed} used · no fixed limit returned`
      : `${entitlement.usage_consumed} / ${entitlement.usage_limit} used`;
    row.append(head, element(document, "p", undefined, `${usage} · ${entitlement.reason}`));
    entitlementList.append(row);
  }
  entitlements.append(entitlementList);

  const available = panel(document, "Available plans", "Choose only through the real provider");
  available.classList.add("is-wide");
  const checkoutState = status(
    document,
    billing.provider_configured
      ? "Checkout opens only after the API returns a valid HTTPS provider URL."
      : "Billing provider is disabled. Plan information is visible, but purchase controls are unavailable.",
    billing.provider_configured ? "quiet" : "warn",
  );
  const planList = element(document, "div", "nur-adjunct-list");
  if (!plans.length) {
    planList.append(empty(document, "No active plan returned", "NUR will not invent price, entitlement or availability data."));
  }
  for (const plan of plans) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(
      element(document, "strong", undefined, `${plan.name} · ${billingPrice(plan)}`),
      element(document, "span", "nur-adjunct-chip", plan.billing_interval),
    );
    row.append(
      head,
      element(document, "p", undefined, plan.description),
      element(document, "p", "nur-adjunct-boundary", `${plan.features.filter(feature => feature.allowed).length} server-declared features · legal copy ${plan.legal_copy_version}`),
    );
    const planActions = element(document, "div", "nur-adjunct-actions");
    const checkout = button(document, plan.is_free ? "Included free" : `Choose ${plan.name}`, `billing-checkout-${plan.code}`, !plan.is_free);
    checkout.disabled = plan.is_free || !plan.active || !billing.provider_configured;
    planActions.append(checkout);
    checkout.addEventListener("click", async () => {
      checkout.disabled = true;
      setStatus(checkoutState, `Creating an idempotent ${plan.name} provider handoff...`);
      try {
        const response = await api.billingCheckout(plan.code, requestKey("billing-checkout"));
        const url = safeExternalUrl(response.checkout_url);
        if (!url) {
          setStatus(checkoutState, "The API did not return a valid HTTPS checkout URL. Nothing was opened and no purchase is claimed.", "warn");
        } else if (!openExternalUrl(url.toString())) {
          externalFallback(document, planActions, url.toString(), `Continue to ${plan.name}`);
          setStatus(checkoutState, "Your browser blocked the new tab. Use the secure provider link on this plan. No subscription is claimed yet.", "warn");
        } else {
          setStatus(checkoutState, `${plan.name} checkout opened through ${response.provider}. No subscription is claimed until the webhook ledger confirms it.`, "good");
        }
      } catch (error) {
        setStatus(checkoutState, error instanceof Error ? error.message : "Checkout is unavailable.", "warn");
      } finally {
        checkout.disabled = plan.is_free || !plan.active || !billing.provider_configured;
      }
    });
    row.append(planActions);
    planList.append(row);
  }
  available.append(checkoutState, planList);
  grid.append(current, entitlements, available);
}

async function renderOwnerCapsules(document: Document, api: V197ApiClient, snapshot: V197BridgeSnapshot): Promise<void> {
  const orbitId = activeOrbitId(snapshot);
  const [sources, initialCapsules] = await Promise.all([
    orbitId ? api.orbitSources(orbitId) : Promise.resolve([]),
    api.ownedCapsules(),
  ]);
  let capsules = initialCapsules;
  const shell = mount(
    document,
    "Share a room, never your whole mind.",
    "A Context Capsule copies only explicitly allowlisted Orbit sources. Recipient grants, expiry, audit and revocation remain separate owner-controlled boundaries.",
    "/universe/orbits",
  );
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const create = panel(document, "Source allowlist", "Create a bounded Context Capsule");
  create.classList.add("is-wide");
  const title = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  title.dataset.adjunctControl = "capsules-title";
  title.placeholder = "Capsule title";
  const purpose = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  purpose.dataset.adjunctControl = "capsules-purpose";
  purpose.placeholder = "What should this bounded room help the recipient do?";
  const capability = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  capability.dataset.adjunctControl = "capsules-capability";
  for (const [value, label] of [
    ["READ_ONLY", "Read approved sources only"],
    ["ASK_SCOPED_QUESTIONS", "Ask scoped questions"],
  ] as const) {
    const option = element(document, "option", undefined, label) as HTMLOptionElement;
    option.value = value;
    capability.append(option);
  }
  const instructions = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  instructions.dataset.adjunctControl = "capsules-instructions";
  instructions.placeholder = "Optional instructions shown inside the recipient room";
  const expires = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  expires.type = "datetime-local";
  expires.dataset.adjunctControl = "capsules-expires";
  const sourceList = element(document, "div", "nur-adjunct-list");
  if (!sources.length) {
    sourceList.append(empty(
      document,
      orbitId ? "No approved Orbit source" : "No active Orbit",
      orbitId
        ? "Attach an owned decision, reference or other supported source to this Orbit before creating a Capsule."
        : "Choose an active Orbit before creating a Context Capsule.",
    ));
  }
  for (const source of sources) {
    const row = element(document, "label", "nur-adjunct-toggle");
    const copy = element(document, "span", undefined, `${source.source_kind} · ${source.source_id} · ${source.inclusion_mode}`);
    const check = element(document, "input") as HTMLInputElement;
    check.type = "checkbox";
    check.dataset.capsuleSourceId = source.id;
    check.dataset.adjunctControl = `capsules-source-${source.id}`;
    row.append(copy, check);
    sourceList.append(row);
  }
  const createAction = button(document, "Create bounded capsule", "capsules-create", true);
  createAction.disabled = !orbitId || !sources.length;
  const createState = status(
    document,
    sources.length
      ? "Select at least one source. Nothing else in Memory, Talk, Journal, Timeline or Omega is traversable."
      : "Creation is disabled until an active Orbit has an explicit approved source.",
    sources.length ? "quiet" : "warn",
  );
  const createActions = element(document, "div", "nur-adjunct-actions");
  createActions.append(createAction);
  create.append(
    element(document, "p", "nur-adjunct-boundary", "Creating a Capsule does not share it. A recipient grant is a second explicit write, and revocation closes access immediately."),
    labeledControl(document, "Title", title),
    labeledControl(document, "Purpose", purpose),
    labeledControl(document, "Recipient capability", capability),
    labeledControl(document, "Recipient instructions", instructions),
    labeledControl(document, "Capsule expiry (optional)", expires),
    element(document, "h3", undefined, "Approved sources"),
    sourceList,
    createActions,
    createState,
  );

  const owned = panel(document, "Owner lifecycle", "Your Context Capsules");
  owned.classList.add("is-wide");
  const ownedState = status(document, "Email grants are hash-addressed by the server; this page never claims delivery or recipient acceptance.");
  const ownedList = element(document, "div", "nur-adjunct-list");
  owned.append(ownedState, ownedList);

  const renderOwned = () => {
    ownedList.replaceChildren();
    if (!capsules.length) {
      ownedList.append(empty(document, "No owner Capsule", "Create a source-bounded room above. It remains unshared until you add a recipient grant."));
      return;
    }
    for (const capsule of capsules) {
      const row = element(document, "article", "nur-adjunct-row");
      const capsuleState = capsule.revoked_at ? "REVOKED" : "ACTIVE";
      const head = element(document, "div", "nur-adjunct-row-head");
      head.append(
        element(document, "strong", undefined, capsule.title),
        element(document, "span", "nur-adjunct-chip", capsuleState),
      );
      row.append(
        head,
        element(document, "p", undefined, capsule.purpose),
        element(document, "p", "nur-adjunct-boundary", `${capsule.capability} · expires ${date(capsule.expires_at)}`),
      );
      const controls = element(document, "div", "nur-adjunct-actions");
      const open = button(document, "Open owner controls", `capsules-open-${capsule.id}`);
      open.addEventListener("click", () => navigate(`/capsule/${encodeURIComponent(capsule.id)}`));
      controls.append(open);
      row.append(controls);
      if (capsuleState === "ACTIVE") {
        const email = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
        email.type = "email";
        email.autocomplete = "email";
        email.placeholder = "Exact recipient account email";
        email.dataset.adjunctControl = `capsules-grant-email-${capsule.id}`;
        const grantCapability = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
        grantCapability.dataset.adjunctControl = `capsules-grant-capability-${capsule.id}`;
        for (const [value, label] of [
          ["READ_ONLY", "Read approved sources only"],
          ["ASK_SCOPED_QUESTIONS", "Ask scoped questions"],
        ] as const) {
          const option = element(document, "option", undefined, label) as HTMLOptionElement;
          option.value = value;
          grantCapability.append(option);
        }
        grantCapability.value = capsule.capability === "READ_ONLY" ? "READ_ONLY" : "ASK_SCOPED_QUESTIONS";
        const grant = button(document, "Grant this recipient", `capsules-grant-${capsule.id}`, true);
        const grantState = status(document, "Granting access does not send an email or prove the recipient opened the room.");
        const grantActions = element(document, "div", "nur-adjunct-actions");
        grantActions.append(grant);
        grant.addEventListener("click", async () => {
          const recipientEmail = email.value.trim();
          if (!recipientEmail || !email.checkValidity()) {
            setStatus(grantState, "Enter the exact valid email for the intended recipient.", "warn");
            return;
          }
          grant.disabled = true;
          setStatus(grantState, "Writing the recipient grant...");
          try {
            await api.grantCapsule(capsule.id, {
              recipient_email: recipientEmail,
              capability: grantCapability.value,
              expires_at: capsule.expires_at,
            });
            email.value = "";
            setStatus(grantState, "Recipient grant persisted. Delivery and opening remain unclaimed.", "good");
          } catch (error) {
            setStatus(grantState, error instanceof Error ? error.message : "The recipient grant failed.", "warn");
          } finally {
            grant.disabled = false;
          }
        });
        row.append(
          labeledControl(document, "Recipient email", email),
          labeledControl(document, "Granted capability", grantCapability),
          grantActions,
          grantState,
        );
      }
      ownedList.append(row);
    }
  };

  createAction.addEventListener("click", async () => {
    const selectedSourceIds = Array.from(sourceList.querySelectorAll<HTMLInputElement>("[data-capsule-source-id]:checked"))
      .map(control => control.dataset.capsuleSourceId)
      .filter((value): value is string => Boolean(value));
    const capsuleTitle = title.value.trim();
    const capsulePurpose = purpose.value.trim();
    if (!capsuleTitle || !capsulePurpose) {
      setStatus(createState, "A Capsule title and bounded purpose are required.", "warn");
      return;
    }
    if (!orbitId || !selectedSourceIds.length) {
      setStatus(createState, orbitId ? "Select at least one approved Orbit source." : "Choose an active Orbit first.", "warn");
      return;
    }
    let expiresAt: string | null = null;
    if (expires.value) {
      const parsed = new Date(expires.value);
      if (Number.isNaN(parsed.getTime())) {
        setStatus(createState, "Choose a valid Capsule expiry.", "warn");
        return;
      }
      expiresAt = parsed.toISOString();
    }
    createAction.disabled = true;
    setStatus(createState, "Copying only the selected source allowlist...");
    try {
      const capsule = await api.createCapsule(orbitId, {
        title: capsuleTitle,
        purpose: capsulePurpose,
        capability: capability.value,
        recipient_instructions: instructions.value.trim() || null,
        expires_at: expiresAt,
        orbit_source_ids: selectedSourceIds,
        representations: {},
      });
      capsules = [capsule, ...capsules];
      title.value = "";
      purpose.value = "";
      instructions.value = "";
      expires.value = "";
      sourceList.querySelectorAll<HTMLInputElement>("[data-capsule-source-id]").forEach(control => { control.checked = false; });
      renderOwned();
      setStatus(createState, "Capsule created from the selected allowlist. No recipient has access yet.", "good");
    } catch (error) {
      setStatus(createState, error instanceof Error ? error.message : "The Capsule could not be created.", "warn");
    } finally {
      createAction.disabled = !sources.length;
    }
  });

  renderOwned();
  grid.append(create, owned);
}

function capsuleStatePanel(document: Document, view: V197CapsuleView): HTMLElement {
  const overview = panel(document, "Approved Context Capsule", `${view.title} — shared context`);
  overview.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(
    fact(document, "State", view.state),
    fact(document, "Purpose", view.purpose),
    fact(document, "Access", view.capability),
    fact(document, "Expires", date(view.expires_at)),
  );
  overview.append(facts, element(document, "p", "nur-adjunct-boundary", view.safety_copy));
  return overview;
}

async function renderRecipientCapsule(document: Document, api: V197ApiClient, capsuleId: string, view: V197CapsuleView): Promise<void> {
  const shell = mount(document, `${view.owner_display}'s shared context`, view.state === "ACTIVE"
    ? "Held open deliberately. Only the sources approved for this room can be reached."
    : `This bounded room is ${view.state.toLowerCase()}. Nothing outside it becomes visible.`, "/today");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  grid.append(capsuleStatePanel(document, view));

  if (view.state !== "ACTIVE") {
    const terminal = panel(document, view.state, "The owner's boundary now closes this room.");
    terminal.classList.add("is-wide");
    terminal.append(empty(document, "Access is closed", "No cached answer is shown and no new question can be asked after revocation or expiry."));
    grid.append(terminal);
    return;
  }

  const included = panel(document, "Approved source ledger", "What is included");
  const includedList = element(document, "div", "nur-adjunct-list");
  if (!view.included.length) includedList.append(empty(document, "No source was included", "This room carries no answerable context."));
  for (const source of view.included) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, source.title), element(document, "span", "nur-adjunct-chip", `${source.source_kind} · ${source.representation}`));
    row.append(head, element(document, "p", undefined, source.body));
    includedList.append(row);
  }
  included.append(includedList);

  const excluded = panel(document, "Boundary proof", "What is excluded");
  const excludedList = element(document, "div", "nur-adjunct-list");
  if (!view.excluded_summary.length) excludedList.append(empty(document, "No withheld category is enumerated", "The recipient still cannot traverse the owner's general memory, Talk, Journal, Timeline, Settings or Omega."));
  for (const item of view.excluded_summary) {
    const row = element(document, "div", "nur-adjunct-row");
    row.append(element(document, "strong", undefined, `${text(item.source_kind)} · ${text(item.count, "0")} withheld`));
    row.append(element(document, "p", undefined, text(item.note, "Withheld by the owner")));
    excludedList.append(row);
  }
  excluded.append(excludedList);

  const ask = panel(document, "Scoped question", "Ask within this approved boundary");
  ask.classList.add("is-wide");
  const canAsk = view.capability === "ASK_SCOPED_QUESTIONS";
  const field = element(document, "label", "nur-adjunct-field");
  field.append(element(document, "span", undefined, "Question"));
  const input = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  input.placeholder = canAsk ? "Ask only about the approved sources…" : "This room is read-only.";
  input.disabled = !canAsk;
  input.dataset.adjunctControl = "capsule-question";
  field.append(input);
  const actions = element(document, "div", "nur-adjunct-actions");
  const askButton = button(document, "Ask from approved context", "capsule-ask", true);
  askButton.disabled = !canAsk;
  const copyButton = button(document, "Copy room address", "capsule-copy");
  actions.append(askButton, copyButton);
  const askState = status(document, canAsk ? "Answers cite only included source IDs." : "The owner granted read-only access.");
  const answerHost = element(document, "div");
  ask.append(field, actions, askState, answerHost);

  copyButton.addEventListener("click", async () => {
    await navigator.clipboard?.writeText(window.location.href);
    askState.textContent = "Room address copied.";
    askState.className = "nur-adjunct-status is-good";
  });
  askButton.addEventListener("click", async () => {
    const question = input.value.trim();
    if (!question) {
      askState.textContent = "Write one scoped question first.";
      askState.className = "nur-adjunct-status is-warn";
      return;
    }
    askButton.disabled = true;
    askState.textContent = "Reading only the approved sources…";
    try {
      const answer: V197CapsuleAnswer = await api.askCapsule(capsuleId, question);
      answerHost.replaceChildren();
      const answerNode = element(document, "article", "nur-adjunct-answer");
      answerNode.append(element(document, "p", "nur-adjunct-eyebrow", `${answer.answer_mode} · source-bound`));
      answerNode.append(element(document, "blockquote", undefined, answer.answer_text));
      answerNode.append(element(document, "p", undefined, answer.source_refs.length ? `Sources: ${answer.source_refs.join(", ")}` : "No approved source supported a direct answer."));
      if (answer.policy_explanation) answerNode.append(element(document, "p", "nur-adjunct-boundary", answer.policy_explanation));
      answerHost.append(answerNode);
      askState.textContent = "Answer persisted inside the capsule ledger.";
      askState.className = "nur-adjunct-status is-good";
    } catch (error) {
      askState.textContent = error instanceof Error ? error.message : "The bounded answer could not be created.";
      askState.className = "nur-adjunct-status is-warn";
    } finally {
      askButton.disabled = !canAsk;
    }
  });

  grid.append(included, excluded, ask);
}

async function renderOwnerCapsule(document: Document, api: V197ApiClient, capsule: V197OwnedCapsule): Promise<void> {
  const shell = mount(document, "A bounded room you control.", "Owner preview exposes lifecycle and audit controls, never the recipient's private question composer.", "/universe/orbits");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const lifecycle = panel(document, "Owner capsule", capsule.title);
  lifecycle.classList.add("is-wide");
  const state = capsule.revoked_at ? "REVOKED" : "ACTIVE";
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "State", state), fact(document, "Purpose", capsule.purpose), fact(document, "Capability", capsule.capability), fact(document, "Expires", date(capsule.expires_at)));
  lifecycle.append(facts);
  const actions = element(document, "div", "nur-adjunct-actions");
  const auditButton = button(document, "Open access audit", "capsule-audit");
  const revokeButton = button(document, "Revoke now", "capsule-revoke", true);
  revokeButton.disabled = state === "REVOKED";
  actions.append(auditButton, revokeButton);
  const lifecycleState = status(document, state === "ACTIVE" ? "Revocation takes effect immediately." : "This capsule is already revoked.", state === "ACTIVE" ? "quiet" : "warn");
  const auditHost = element(document, "div", "nur-adjunct-list");
  lifecycle.append(actions, lifecycleState, auditHost);
  auditButton.addEventListener("click", async () => {
    auditButton.disabled = true;
    try {
      const rows = await api.capsuleAudit(capsule.id);
      auditHost.replaceChildren();
      if (!rows.length) auditHost.append(empty(document, "No access event yet", "The room has not been opened by a recipient."));
      for (const row of rows) {
        const item = element(document, "div", "nur-adjunct-row");
        item.append(element(document, "strong", undefined, text(row.event_kind)), element(document, "p", undefined, date(row.created_at)));
        auditHost.append(item);
      }
      lifecycleState.textContent = `${rows.length} owner-scoped audit event${rows.length === 1 ? "" : "s"}.`;
    } catch (error) {
      lifecycleState.textContent = error instanceof Error ? error.message : "Audit could not be read.";
      lifecycleState.className = "nur-adjunct-status is-warn";
    } finally {
      auditButton.disabled = false;
    }
  });
  revokeButton.addEventListener("click", async () => {
    revokeButton.disabled = true;
    lifecycleState.textContent = "Closing the room…";
    try {
      await api.revokeCapsule(capsule.id);
      lifecycleState.textContent = "Revoked. Recipient reads and asks are blocked immediately.";
      lifecycleState.className = "nur-adjunct-status is-good";
    } catch (error) {
      lifecycleState.textContent = error instanceof Error ? error.message : "Revocation failed.";
      lifecycleState.className = "nur-adjunct-status is-warn";
      revokeButton.disabled = false;
    }
  });
  grid.append(lifecycle);
}

async function renderCapsule(document: Document, api: V197ApiClient, capsuleId: string): Promise<void> {
  try {
    const view = await api.capsuleView(capsuleId);
    await renderRecipientCapsule(document, api, capsuleId, view);
    return;
  } catch (error) {
    if (!(error instanceof V197ApiError) || error.status !== 404) throw error;
  }
  const owned = (await api.ownedCapsules()).find(row => row.id === capsuleId);
  if (owned) {
    await renderOwnerCapsule(document, api, owned);
    return;
  }
  const shell = mount(document, "This room is not available.", "No Context Capsule is shared with this session at this address.", "/today");
  const unavailable = panel(document, "Boundary held", "Nothing leaks through a missing grant");
  unavailable.classList.add("is-wide");
  unavailable.append(empty(document, "No active grant", "Sign in as the intended recipient or ask the owner for a current capsule address."));
  const grid = element(document, "div", "nur-adjunct-grid");
  grid.append(unavailable);
  shell.append(grid);
}

function omegaList(
  document: Document,
  rows: Array<Record<string, unknown>>,
  titleKey: string,
  bodyKey: string,
  chipKey: string,
  actions?: (row: Record<string, unknown>) => HTMLElement,
): HTMLElement {
  const list = element(document, "div", "nur-adjunct-list");
  if (!rows.length) return empty(document, "No persisted evidence yet", "Omega does not invent a result before the owner's evidence exists.");
  for (const row of rows) {
    const item = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, text(row[titleKey])), element(document, "span", "nur-adjunct-chip", text(row[chipKey], "UNRESOLVED")));
    item.append(head);
    const body = text(row[bodyKey], "");
    if (body) item.append(element(document, "p", undefined, body));
    if (actions) item.append(actions(row));
    list.append(item);
  }
  return list;
}

function navigate(route: string): void {
  window.history.pushState({}, "", route);
  window.dispatchEvent(new PopStateEvent("popstate"));
}

async function renderOmegaDashboard(document: Document, api: V197ApiClient): Promise<void> {
  const [dashboard, scheduler] = await Promise.all([api.omegaDashboard(), api.omegaScheduler()]);
  const shell = mount(document, "Evidence changes the model, deliberately.", "Omega is an owner-only cognition ledger: claims, contradictions, predictions and governed learning proposals. It is not sentience and exposes no chain-of-thought.");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const runtime = panel(document, "Omega substrate", "Consolidation status");
  runtime.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "Scheduler", scheduler.enabled && scheduler.scheduled_consolidation ? "ACTIVE" : "DISABLED"), fact(document, "Worker", scheduler.worker_mode), fact(document, "Last run", scheduler.last_consolidation_status), fact(document, "Interval", `${scheduler.interval_hours} hours`));
  runtime.append(facts);
  const runtimeActions = element(document, "div", "nur-adjunct-actions");
  const consolidate = button(document, "Consolidate owner evidence", "omega-consolidate", true);
  const review = button(document, `Open review queue (${dashboard.review_queue.length})`, "omega-review");
  const exportButton = button(document, "Export owner Omega", "omega-export");
  runtimeActions.append(consolidate, review, exportButton);
  const runtimeState = status(document, "Consolidation proposes changes; sensitive inferences still require owner review.");
  runtime.append(runtimeActions, runtimeState);
  review.addEventListener("click", () => navigate("/universe/omega/review"));
  consolidate.addEventListener("click", async () => {
    consolidate.disabled = true;
    runtimeState.textContent = "Consolidating the owner ledger…";
    try {
      const run = await api.consolidateOmega();
      runtimeState.textContent = `Run ${text(run.status)}: ${text(run.created_claims, "0")} claims created, ${text(run.contradictions_found, "0")} contradictions found.`;
      runtimeState.className = "nur-adjunct-status is-good";
    } catch (error) {
      runtimeState.textContent = error instanceof Error ? error.message : "Consolidation did not complete.";
      runtimeState.className = "nur-adjunct-status is-warn";
    } finally {
      consolidate.disabled = false;
    }
  });
  exportButton.addEventListener("click", async () => {
    exportButton.disabled = true;
    try {
      const data = await api.omegaExport();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      const anchor = element(document, "a") as HTMLAnchorElement;
      anchor.href = url;
      anchor.download = "nur-omega-owner-export.json";
      anchor.click();
      URL.revokeObjectURL(url);
      runtimeState.textContent = "Owner-scoped Omega export prepared locally.";
      runtimeState.className = "nur-adjunct-status is-good";
    } catch (error) {
      runtimeState.textContent = error instanceof Error ? error.message : "Export failed.";
      runtimeState.className = "nur-adjunct-status is-warn";
    } finally {
      exportButton.disabled = false;
    }
  });

  const claimPanel = panel(document, "Candidate understanding", `Claims · ${dashboard.claims.length}`);
  claimPanel.append(omegaList(document, dashboard.claims, "claim_text", "", "truth_status", row => {
    const actions = element(document, "div", "nur-adjunct-actions");
    const why = button(document, "Why changed?", "omega-why");
    why.addEventListener("click", () => navigate(`/universe/omega/why-changed/${recordId(row)}`));
    actions.append(why);
    return actions;
  }));

  const contradictionPanel = panel(document, "Open tension", `Contradictions · ${dashboard.contradictions.length}`);
  contradictionPanel.append(omegaList(document, dashboard.contradictions, "description", "proposed_resolution", "severity"));
  const predictionPanel = panel(document, "Unresolved future", `Predictions · ${dashboard.predictions.length}`);
  predictionPanel.append(omegaList(document, dashboard.predictions, "prediction_text", "expected_observation", "status"));
  const proposalPanel = panel(document, "Governed learning", `Proposals · ${dashboard.learning_proposals.length}`);
  proposalPanel.append(omegaList(document, dashboard.learning_proposals, "description", "evidence_summary", "status"));
  grid.append(runtime, claimPanel, contradictionPanel, predictionPanel, proposalPanel);
}

async function renderOmegaReview(document: Document, api: V197ApiClient): Promise<void> {
  const rows = await api.omegaReviewQueue();
  const shell = mount(document, "Nothing sensitive becomes truth by accident.", "Review model-generated claim candidates before they enter the owner evidence graph.", "/universe/omega");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const review = panel(document, "Owner confirmation gate", `Pending review · ${rows.length}`);
  review.classList.add("is-wide");
  const reviewState = status(document, "Approval and rejection are persisted and owner-scoped.");
  review.append(omegaList(document, rows, "candidate_claim_text", "reason", "sensitivity", row => {
    const actions = element(document, "div", "nur-adjunct-actions");
    const approve = button(document, "Approve as reviewed", `omega-review-approve-${recordId(row)}`, true);
    const reject = button(document, "Reject", `omega-review-reject-${recordId(row)}`);
    const act = async (action: "approve" | "reject") => {
      approve.disabled = true;
      reject.disabled = true;
      try {
        await api.reviewOmegaItem(recordId(row), action);
        row.status = action === "approve" ? "APPROVED" : "REJECTED";
        reviewState.textContent = `Candidate ${action === "approve" ? "approved" : "rejected"}. Refreshing owner queue…`;
        reviewState.className = "nur-adjunct-status is-good";
        await renderOmegaReview(document, api);
      } catch (error) {
        reviewState.textContent = error instanceof Error ? error.message : "Review action failed.";
        reviewState.className = "nur-adjunct-status is-warn";
        approve.disabled = false;
        reject.disabled = false;
      }
    };
    approve.addEventListener("click", () => void act("approve"));
    reject.addEventListener("click", () => void act("reject"));
    actions.append(approve, reject);
    return actions;
  }), reviewState);
  grid.append(review);
}

async function renderOmegaWhyChanged(document: Document, api: V197ApiClient, claimId: string): Promise<void> {
  const [why, evidence] = await Promise.all([api.omegaWhyChanged(claimId), api.omegaEvidence(claimId)]);
  const shell = mount(document, "Why NUR changed its mind.", "A provenance explanation assembled from the owner evidence graph, not hidden chain-of-thought.", "/universe/omega");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const claim = panel(document, "Current claim", text(why.claim_text));
  claim.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "Truth state", text(why.current_truth_status)), fact(document, "Confidence", text(why.current_confidence)));
  claim.append(facts);

  const changed = panel(document, "Change ledger", "What moved this claim");
  const reasons = Array.isArray(why.changed_because) ? why.changed_because : [];
  changed.append(omegaList(document, reasons.map((value, index) => ({ id: String(index), title: text(value), state: "EVIDENCE" })), "title", "", "state"));

  const evidencePanel = panel(document, "Evidence graph", `Edges · ${evidence.length}`);
  evidencePanel.append(omegaList(document, evidence, "relation", "note", "evidence_kind"));
  const actions = element(document, "div", "nur-adjunct-actions");
  const confirm = button(document, "Confirm claim", "omega-claim-confirm", true);
  const retire = button(document, "Retire claim", "omega-claim-retire");
  actions.append(confirm, retire);
  const actionState = status(document, text(why.unresolved_note, "Owner review remains the final authority."));
  claim.append(actions, actionState);
  const act = async (action: "confirm" | "retire") => {
    confirm.disabled = true;
    retire.disabled = true;
    try {
      if (action === "confirm") await api.confirmOmegaClaim(claimId);
      else await api.retireOmegaClaim(claimId);
      actionState.textContent = action === "confirm" ? "Claim confirmed by owner." : "Claim retired from active use.";
      actionState.className = "nur-adjunct-status is-good";
    } catch (error) {
      actionState.textContent = error instanceof Error ? error.message : "Claim action failed.";
      actionState.className = "nur-adjunct-status is-warn";
      confirm.disabled = false;
      retire.disabled = false;
    }
  };
  confirm.addEventListener("click", () => void act("confirm"));
  retire.addEventListener("click", () => void act("retire"));
  grid.append(claim, changed, evidencePanel);
}

function conciseRecord(value: unknown): string {
  if (typeof value === "string") return value;
  if (typeof value === "number" || typeof value === "boolean") return String(value);
  if (!value || typeof value !== "object") return "No detail recorded";
  const entries = Object.entries(value as Record<string, unknown>)
    .filter(([, item]) => typeof item === "string" || typeof item === "number" || typeof item === "boolean")
    .slice(0, 4)
    .map(([key, item]) => `${key.replaceAll("_", " ")}: ${String(item)}`);
  return entries.join(" · ") || "Structured owner evidence";
}

async function renderCandidateInsights(
  document: Document,
  api: V197ApiClient,
): Promise<void> {
  const insights = await api.candidateInsights();
  const shell = mount(
    document,
    "Candidate insight, never silent truth.",
    "Every inference keeps its evidence, counter-evidence, uncertainty, provenance and owner decision. Acceptance is explicit; correction preserves the original audit trail.",
    "/universe",
  );
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const overview = panel(document, "Owner review queue", `Candidates · ${insights.length}`);
  overview.classList.add("is-wide");
  const counts = insights.reduce<Record<string, number>>((result, insight) => {
    result[insight.status] = (result[insight.status] ?? 0) + 1;
    return result;
  }, {});
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(
    fact(document, "Candidate", String(counts.CANDIDATE ?? counts.PENDING ?? 0)),
    fact(document, "Accepted", String(counts.ACCEPTED ?? 0)),
    fact(document, "Corrected", String(counts.CORRECTED ?? 0)),
    fact(document, "Rejected", String(counts.REJECTED ?? 0)),
  );
  const generate = button(document, "Generate from owner ledger", "candidate-generate", true);
  const generateState = status(document, "Generation may honestly refuse when the owner ledger has insufficient evidence.");
  overview.append(facts, generate, generateState);
  generate.addEventListener("click", async () => {
    generate.disabled = true;
    try {
      await api.generateCandidateInsight();
      await renderCandidateInsights(document, api);
    } catch (error) {
      generateState.textContent = error instanceof Error ? error.message : "Candidate insight was not generated.";
      generateState.className = "nur-adjunct-status is-warn";
      generate.disabled = false;
    }
  });
  grid.append(overview);

  if (!insights.length) {
    const quiet = panel(document, "Honest state", "No candidate insight yet");
    quiet.classList.add("is-wide");
    quiet.append(empty(document, "The review queue is empty", "NUR will not invent a pattern merely to populate this page."));
    grid.append(quiet);
    return;
  }

  for (const insight of insights) {
    const card = panel(document, `${insight.insight_type} · ${insight.provenance_label}`, insight.title);
    card.classList.add("is-wide", "nur-candidate-card");
    const facts = element(document, "div", "nur-adjunct-facts");
    facts.append(
      fact(document, "Status", insight.status),
      fact(document, "Confidence", `${Math.round(insight.confidence * 100)}%`),
      fact(document, "System", insight.affected_system_slug ?? "Not linked"),
      fact(document, "Updated", date(insight.updated_at)),
    );
    const claim = element(document, "blockquote", "nur-adjunct-candidate-claim", insight.claim);
    const interpretations = element(document, "div", "nur-adjunct-grid nur-adjunct-evidence-grid");
    const evidence = element(document, "section", "nur-adjunct-evidence-block");
    evidence.append(
      element(document, "p", "nur-adjunct-eyebrow", "Evidence"),
      element(document, "h3", undefined, `${insight.evidence.length} linked`),
    );
    const evidenceList = element(document, "div", "nur-adjunct-list");
    for (const item of insight.evidence) evidenceList.append(element(document, "p", "nur-adjunct-evidence-line", conciseRecord(item)));
    if (!insight.evidence.length) evidenceList.append(status(document, "No evidence record was returned.", "warn"));
    evidence.append(evidenceList);
    const counter = element(document, "section", "nur-adjunct-evidence-block");
    counter.append(
      element(document, "p", "nur-adjunct-eyebrow", "Counter-evidence"),
      element(document, "h3", undefined, `${insight.counter_evidence.length} linked`),
    );
    const counterList = element(document, "div", "nur-adjunct-list");
    for (const item of insight.counter_evidence) counterList.append(element(document, "p", "nur-adjunct-evidence-line", conciseRecord(item)));
    if (!insight.counter_evidence.length) counterList.append(status(document, "No counter-evidence record was returned."));
    counter.append(counterList);
    interpretations.append(evidence, counter);

    const uncertainty = element(document, "p", "nur-adjunct-boundary", `What NUR may be wrong about: ${insight.what_nur_may_be_wrong_about}`);
    const reading = element(
      document,
      "p",
      undefined,
      [insight.positive_interpretation, insight.hard_interpretation, insight.suggested_action].filter(Boolean).join(" · "),
    );
    const correction = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
    correction.placeholder = "Correct the candidate without erasing its original record";
    correction.value = insight.correction ?? "";
    const actions = element(document, "div", "nur-adjunct-actions");
    const accept = button(document, "Accept", `candidate-accept-${insight.id}`, true);
    const reject = button(document, "Reject", `candidate-reject-${insight.id}`);
    const correct = button(document, "Persist correction", `candidate-correct-${insight.id}`);
    const plan = button(document, "Convert to plan", `candidate-plan-${insight.id}`);
    const timeline = button(document, "Add review to Timeline", `candidate-timeline-${insight.id}`);
    const memory = button(document, "Save as memory candidate", `candidate-memory-${insight.id}`);
    memory.disabled = insight.status !== "ACCEPTED";
    actions.append(accept, reject, correct, plan, timeline, memory);
    const actionState = status(document, "Every action writes through the owner-scoped API.");
    const act = async (control: HTMLButtonElement, task: () => Promise<unknown>) => {
      control.disabled = true;
      try {
        await task();
        await renderCandidateInsights(document, api);
      } catch (error) {
        actionState.textContent = error instanceof Error ? error.message : "Insight action failed.";
        actionState.className = "nur-adjunct-status is-warn";
        control.disabled = false;
      }
    };
    accept.addEventListener("click", () => void act(accept, () => api.acceptInsight(insight.id)));
    reject.addEventListener("click", () => void act(reject, () => api.rejectInsight(insight.id)));
    correct.addEventListener("click", () => {
      if (!correction.value.trim()) {
        actionState.textContent = "Write the correction first.";
        actionState.className = "nur-adjunct-status is-warn";
        return;
      }
      void act(correct, () => api.correctInsight(insight.id, correction.value.trim()));
    });
    plan.addEventListener("click", () => void act(plan, () => api.convertInsightToPlan(insight.id)));
    timeline.addEventListener("click", () => void act(timeline, () => api.addInsightToTimeline(insight.id)));
    memory.addEventListener("click", () => void act(memory, () => api.saveInsightToMemory(insight.id)));
    card.append(facts, claim, interpretations, uncertainty, reading, correction, actions, actionState);
    grid.append(card);
  }
}

function consultationStages(document: Document, detail: V197ConsultationDetail): HTMLElement {
  const rail = element(document, "div", "nur-adjunct-actions");
  const completed = new Set(detail.completed_stages.map(row => row.stage));
  for (const stage of detail.stage_order) {
    const chip = element(document, "span", "nur-adjunct-chip", `${completed.has(stage) ? "✓ " : stage === detail.next_stage ? "✦ " : ""}${stage}`);
    if (stage === detail.next_stage) chip.dataset.currentStage = "true";
    rail.append(chip);
  }
  return rail;
}

async function renderConsultationIndex(
  document: Document,
  api: V197ApiClient,
  orbitId: string,
): Promise<void> {
  const [rows, communityRooms] = await Promise.all([
    api.consultations(),
    api.communityRooms(),
  ]);
  const shell = mount(document, "A question moves when context returns.", "Consultation keeps lived experience, constraints, disagreement, evidence and the final outcome inside one bounded ORIENT → RETURN path.", "/universe");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const listPanel = panel(document, "Consultation ledger", `Open and returned · ${rows.length}`);
  const list = element(document, "div", "nur-adjunct-list");
  if (!rows.length) list.append(empty(document, "No Consultation yet", "Open one bounded question. Nothing is synthesized before contributions exist."));
  for (const row of rows) {
    const item = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, row.title), element(document, "span", "nur-adjunct-chip", `${row.current_stage} · ${row.status}`));
    item.append(head, element(document, "p", undefined, row.question));
    const actions = element(document, "div", "nur-adjunct-actions");
    const open = button(document, "Enter Consultation", `consultation-open-${row.id}`);
    open.addEventListener("click", () => navigate(`/universe/consultation/${row.id}`));
    actions.append(open);
    item.append(actions);
    list.append(item);
  }
  listPanel.append(list);

  const create = panel(document, "ORIENT", "Open a bounded Consultation");
  const field = (label: string, control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement) => {
    const wrapper = element(document, "label", "nur-adjunct-field");
    wrapper.append(element(document, "span", undefined, label), control);
    return wrapper;
  };
  const title = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  title.placeholder = "Consultation title";
  const question = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  question.placeholder = "What is the actual question?";
  const purpose = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  purpose.placeholder = "Why does this need a shared return?";
  const desired = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  desired.placeholder = "What useful outcome should exist?";
  const scope = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  scope.placeholder = "What is inside and outside this Consultation?";
  const room = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  room.append(element(document, "option", undefined, "Private owner Consultation"));
  room.options[0].value = "";
  for (const candidate of communityRooms) {
    const option = element(document, "option", undefined, `${candidate.title} · ${candidate.current_user_role}`) as HTMLOptionElement;
    option.value = candidate.id;
    room.append(option);
  }
  create.append(field("Title", title), field("Question", question), field("Purpose", purpose), field("Desired outcome", desired), field("Scope statement", scope), field("Bounded room", room));
  const actions = element(document, "div", "nur-adjunct-actions");
  const createButton = button(document, "Open Consultation", "consultation-create", true);
  actions.append(createButton);
  const createState = status(document, "Only explicit Consultation records are shared. Private Talk, Journal and Omega remain outside.");
  create.append(actions, createState);
  createButton.addEventListener("click", async () => {
    const values = [title.value, question.value, purpose.value, desired.value, scope.value].map(value => value.trim());
    if (values.some(value => !value)) {
      createState.textContent = "Title, question, purpose, desired outcome and scope are all required.";
      createState.className = "nur-adjunct-status is-warn";
      return;
    }
    createButton.disabled = true;
    try {
      const created = await api.createConsultation({
        title: values[0], question: values[1], purpose: values[2], desired_outcome: values[3],
        scope_statement: values[4], room_id: room.value || null,
        orbit_id: orbitId, system_slug: "quiet-ambition",
      });
      navigate(`/universe/consultation/${created.id}`);
    } catch (error) {
      createState.textContent = error instanceof Error ? error.message : "Consultation could not be opened.";
      createState.className = "nur-adjunct-status is-warn";
      createButton.disabled = false;
    }
  });
  grid.append(listPanel, create);
}

async function renderConsultationDetail(document: Document, api: V197ApiClient, consultationId: string): Promise<void> {
  const detail = await api.consultation(consultationId);
  const row = detail.consultation;
  const shell = mount(document, row.title, row.question, "/universe/consultation");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const orientation = panel(document, "Bounded Consultation", `${row.current_stage} · ${row.status}`);
  orientation.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "Purpose", row.purpose), fact(document, "Desired outcome", row.desired_outcome), fact(document, "Scope", row.scope_statement), fact(document, "Your role", row.current_user_role));
  orientation.append(facts, consultationStages(document, detail), element(document, "p", "nur-adjunct-boundary", detail.what_nur_may_be_wrong_about));

  const contributions = panel(document, "GATHER", `Contributions · ${detail.contributions.length}`);
  const contributionList = element(document, "div", "nur-adjunct-list");
  if (!detail.contributions.length) contributionList.append(empty(document, "No contribution yet", "Lived experience, constraints and disagreement stay visible instead of being smoothed away."));
  for (const contribution of detail.contributions) {
    const item = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, contribution.contribution_type.replaceAll("_", " ")), element(document, "span", "nur-adjunct-chip", contribution.provenance_label));
    item.append(head, element(document, "p", undefined, contribution.body));
    contributionList.append(item);
  }
  contributions.append(contributionList);
  if (row.status === "ACTIVE") {
    const type = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
    for (const value of ["LIVED_EXPERIENCE", "PRACTICAL_MOVE", "CONSTRAINT", "COUNTEREXAMPLE", "DISAGREEMENT", "WITNESS", "TRIED_THIS", "OUTCOME", "EXPERT_VOICE", "RESEARCH_EVIDENCE"]) {
      const option = element(document, "option", undefined, value.replaceAll("_", " ")) as HTMLOptionElement;
      option.value = value;
      type.append(option);
    }
    const body = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
    body.placeholder = "Add only what belongs inside this Consultation…";
    const send = button(document, "Add contribution", "consultation-contribute", true);
    const contributionState = status(document, "This contribution is shared only with members of the bounded room.");
    contributions.append(type, body, send, contributionState);
    send.addEventListener("click", async () => {
      if (!body.value.trim()) {
        contributionState.textContent = "Write one contribution first.";
        contributionState.className = "nur-adjunct-status is-warn";
        return;
      }
      send.disabled = true;
      try {
        await api.addConsultationContribution(consultationId, {
          contribution_type: type.value, body: body.value.trim(),
          language_tag: document.documentElement.lang || "en",
        });
        await renderConsultationDetail(document, api, consultationId);
      } catch (error) {
        contributionState.textContent = error instanceof Error ? error.message : "Contribution was not saved.";
        contributionState.className = "nur-adjunct-status is-warn";
        send.disabled = false;
      }
    });
  }

  const movement = panel(document, "Owner movement", row.status === "COMPLETED" ? "RETURN is held" : `Complete ${detail.next_stage}`);
  const stageList = element(document, "div", "nur-adjunct-list");
  for (const stage of detail.completed_stages) {
    const item = element(document, "article", "nur-adjunct-row");
    item.append(element(document, "strong", undefined, stage.stage), element(document, "p", undefined, JSON.stringify(stage.stage_payload)));
    stageList.append(item);
  }
  movement.append(stageList);
  if (row.status === "ACTIVE" && row.current_user_role === "OWNER" && detail.next_stage) {
    const note = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
    note.placeholder = detail.next_stage === "RETURN" ? "Record the outcome and prediction comparison…" : `Record the ${detail.next_stage} evidence…`;
    const advance = button(document, `Persist ${detail.next_stage}`, `consultation-stage-${detail.next_stage.toLowerCase()}`, true);
    const stageState = status(document, "Stage movement happens only after server persistence.");
    movement.append(note, advance, stageState);
    advance.addEventListener("click", async () => {
      if (!note.value.trim()) {
        stageState.textContent = "Record this stage before advancing.";
        stageState.className = "nur-adjunct-status is-warn";
        return;
      }
      advance.disabled = true;
      try {
        const result = await api.completeConsultationStage(consultationId, detail.next_stage!, { note: note.value.trim() });
        if (result.glow?.status === "AWARDED") stageState.textContent = `RETURN persisted · +${text(result.glow.awarded_points, "0")} Glow`;
        await renderConsultationDetail(document, api, consultationId);
      } catch (error) {
        stageState.textContent = error instanceof Error ? error.message : "Stage was not persisted.";
        stageState.className = "nur-adjunct-status is-warn";
        advance.disabled = false;
      }
    });
  } else if (row.status === "ACTIVE") {
    movement.append(empty(document, "Owner movement only", "Members contribute evidence and disagreement. The Consultation owner advances the stage."));
  } else {
    movement.append(status(document, "This Consultation completed its RETURN loop.", "good"));
  }
  grid.append(orientation, contributions, movement);
}

async function loadCommunityFeed(api: V197ApiClient): Promise<{
  rooms: Awaited<ReturnType<V197ApiClient["communityRooms"]>>;
  posts: V197CommunityPost[];
}> {
  const rooms = await api.communityRooms();
  const groups = await Promise.all(rooms.map(room => api.communityPosts(room.id).catch(() => [])));
  const posts = groups.flat().sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  return { rooms, posts };
}

async function renderCommunityIndex(document: Document, api: V197ApiClient): Promise<void> {
  const { rooms, posts } = await loadCommunityFeed(api);
  const shell = mount(document, "Shared signal without private spill.", "Community is built from real bounded rooms and persisted contributions. No fake people, replies, activity or live public count appears here.", "/universe");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const roomPanel = panel(document, "Group NUR boundaries", `Rooms · ${rooms.length}`);
  roomPanel.id = "nur-v197-community-controls";
  const roomList = element(document, "div", "nur-adjunct-list");
  if (!rooms.length) roomList.append(empty(document, "No bounded room yet", "Create one real room. NUR will not invent a community around you."));
  for (const room of rooms) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, room.title), element(document, "span", "nur-adjunct-chip", `${room.is_demo ? "DEMO · " : ""}${room.room_kind}`));
    row.append(head, element(document, "p", undefined, room.description ?? room.privacy));
    const actions = element(document, "div", "nur-adjunct-actions");
    const open = button(document, "Enter bounded room", `community-room-${room.id}`);
    open.addEventListener("click", () => navigate(`/universe/community/room/${room.id}`));
    actions.append(open);
    row.append(actions);
    roomList.append(row);
  }
  roomPanel.append(roomList);
  const roomTitle = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  roomTitle.id = "nur-v197-room-title";
  roomTitle.placeholder = "Name one bounded room";
  const createRoom = button(document, "Create Group NUR room", "community-room-create", true);
  const createCouncil = button(document, "Start a Council room", "community-council-create");
  const roomState = status(document, "The creator becomes owner. Membership is explicit and server-enforced.");
  const roomActions = element(document, "div", "nur-adjunct-actions");
  roomActions.append(createRoom, createCouncil);
  roomPanel.append(roomTitle, roomActions, roomState);
  const createBoundedRoom = async (
    control: HTMLButtonElement,
    roomKind: "GROUP" | "COUNCIL",
  ): Promise<void> => {
    if (!roomTitle.value.trim()) {
      roomState.textContent = "Name the room first.";
      roomState.className = "nur-adjunct-status is-warn";
      return;
    }
    createRoom.disabled = true;
    createCouncil.disabled = true;
    try {
      const created = await api.createCommunityRoom(roomTitle.value.trim(), roomKind);
      navigate(`/universe/community/room/${created.id}`);
    } catch (error) {
      roomState.textContent = error instanceof Error ? error.message : "Room was not created.";
      roomState.className = "nur-adjunct-status is-warn";
      control.focus();
      createRoom.disabled = false;
      createCouncil.disabled = false;
    }
  };
  createRoom.addEventListener("click", () => { void createBoundedRoom(createRoom, "GROUP"); });
  createCouncil.addEventListener("click", () => { void createBoundedRoom(createCouncil, "COUNCIL"); });

  const feed = panel(document, "Persisted signal feed", `Posts · ${posts.length}`);
  const postList = element(document, "div", "nur-adjunct-list");
  if (!posts.length) postList.append(empty(document, "No post yet", "Room members can write the first persisted contribution."));
  for (const post of posts) {
    const room = rooms.find(candidate => candidate.id === post.room_id);
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, post.title), element(document, "span", "nur-adjunct-chip", `${post.is_demo ? "DEMO · " : ""}${room?.title ?? "ROOM"}`));
    row.append(head, element(document, "p", undefined, post.body));
    const actions = element(document, "div", "nur-adjunct-actions");
    const open = button(document, "Open thread", `community-post-${post.id}`);
    open.addEventListener("click", () => navigate(`/universe/community/post/${post.id}?room=${post.room_id}`));
    actions.append(open);
    row.append(actions);
    postList.append(row);
  }
  feed.append(postList);
  grid.append(roomPanel, feed);
}

async function renderCommunityRoom(document: Document, api: V197ApiClient, roomId: string): Promise<void> {
  const [room, summary, messages, posts] = await Promise.all([
    api.get<Record<string, unknown>>(`/community/rooms/${encodeURIComponent(roomId)}`),
    api.communityRoomSummary(roomId), api.communityMessages(roomId), api.communityPosts(roomId),
  ]);
  const shell = mount(document, text(room.title), text(room.description, "A bounded Group NUR room."), "/universe/community");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const boundary = panel(document, "Room boundary", `${text(room.current_user_role)} · ${text(room.room_kind)}`);
  boundary.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "Messages", text(summary.counts.messages, "0")), fact(document, "Posts", text(summary.counts.posts, "0")), fact(document, "Contributions", text(summary.counts.comments, "0")), fact(document, "External public feed", summary.external_public_feed));
  boundary.append(facts, element(document, "p", "nur-adjunct-boundary", text(room.privacy)));
  const boundaryActions = element(document, "div", "nur-adjunct-actions");
  const consultation = button(document, "Start Consultation", "community-start-consultation", true);
  consultation.addEventListener("click", () => navigate("/universe/consultation"));
  boundaryActions.append(consultation);
  boundary.append(boundaryActions);
  if (text(room.current_user_role) === "OWNER") {
    const memberEmail = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
    memberEmail.id = "nur-v197-member-email";
    memberEmail.type = "email";
    memberEmail.autocomplete = "off";
    memberEmail.placeholder = "Exact NUR account email";
    const addMember = button(document, "Add member", "community-member-add");
    const memberState = status(document, "Only an existing NUR account can cross this room boundary.");
    boundary.append(memberEmail, addMember, memberState);
    addMember.addEventListener("click", async () => {
      if (!memberEmail.value.trim()) {
        memberState.textContent = "Enter the exact account email first.";
        memberState.className = "nur-adjunct-status is-warn";
        return;
      }
      addMember.disabled = true;
      try {
        await api.addCommunityMember(roomId, memberEmail.value.trim());
        memberState.textContent = "Member added to this boundary.";
        memberState.className = "nur-adjunct-status is-good";
      } catch (error) {
        memberState.textContent = error instanceof Error ? error.message : "Member was not added.";
        memberState.className = "nur-adjunct-status is-warn";
        addMember.disabled = false;
      }
    });
  }

  const conversation = panel(document, "Group NUR", `Conversation · ${messages.length}`);
  conversation.id = "universe-community";
  const messageList = element(document, "div", "nur-adjunct-list");
  if (!messages.length) messageList.append(empty(document, "No room message yet", "NUR stays quiet until a member contributes."));
  for (const message of messages) {
    const item = element(document, "article", "nur-adjunct-row");
    item.append(element(document, "span", "nur-adjunct-chip", `${message.is_demo ? "DEMO · " : ""}${message.provenance_label}`), element(document, "p", undefined, message.body));
    messageList.append(item);
  }
  const messageInput = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  messageInput.id = "nur-v197-room-message";
  messageInput.placeholder = "Write inside this room boundary…";
  const sendMessage = button(document, "Send to room", "community-message-send", true);
  const messageState = status(document, "A persisted real message may earn server-verified Glow. DEMO messages never do.");
  conversation.append(messageList, messageInput, sendMessage, messageState);
  sendMessage.addEventListener("click", async () => {
    if (!messageInput.value.trim()) return;
    sendMessage.disabled = true;
    try {
      const saved = await api.postCommunityMessage(roomId, messageInput.value.trim(), document.documentElement.lang || "en");
      messageState.textContent = saved.glow?.status === "AWARDED" ? `Persisted · +${saved.glow.awarded_points} Glow` : "Persisted in the bounded room.";
      messageState.className = "nur-adjunct-status is-good";
      await renderCommunityRoom(document, api, roomId);
    } catch (error) {
      messageState.textContent = error instanceof Error ? error.message : "Message was not saved.";
      messageState.className = "nur-adjunct-status is-warn";
      sendMessage.disabled = false;
    }
  });

  const threads = panel(document, "Room threads", `Posts · ${posts.length}`);
  const threadList = element(document, "div", "nur-adjunct-list");
  for (const post of posts) {
    const item = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, post.title), element(document, "span", "nur-adjunct-chip", post.is_demo ? "DEMO" : post.provenance_label));
    item.append(head, element(document, "p", undefined, post.body));
    const open = button(document, "Open thread", `community-post-${post.id}`);
    open.addEventListener("click", () => navigate(`/universe/community/post/${post.id}?room=${roomId}`));
    item.append(open);
    threadList.append(item);
  }
  const postTitle = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  postTitle.placeholder = "Thread title";
  const postBody = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  postBody.placeholder = "Question, lived experience, resource, outcome or Project log…";
  const publish = button(document, "Publish in room", "community-post-create", true);
  const postState = status(document, "Only room members can read this thread.");
  threads.append(threadList, postTitle, postBody, publish, postState);
  publish.addEventListener("click", async () => {
    if (!postTitle.value.trim() || !postBody.value.trim()) {
      postState.textContent = "A thread needs both title and body.";
      postState.className = "nur-adjunct-status is-warn";
      return;
    }
    publish.disabled = true;
    try {
      const saved = await api.createCommunityPost(roomId, postTitle.value.trim(), postBody.value.trim(), document.documentElement.lang || "en");
      navigate(`/universe/community/post/${saved.id}?room=${roomId}`);
    } catch (error) {
      postState.textContent = error instanceof Error ? error.message : "Thread was not published.";
      postState.className = "nur-adjunct-status is-warn";
      publish.disabled = false;
    }
  });
  grid.append(boundary, conversation, threads);

  if (text(room.room_kind) === "COUNCIL") {
    const positions = await api.communityPositions(roomId);
    const council = panel(document, "Council ledger", `Positions · ${positions.length} · Decisions · ${text(summary.counts.decisions, "0")}`);
    council.classList.add("is-wide");
    const positionList = element(document, "div", "nur-adjunct-list");
    if (!positions.length) {
      positionList.append(empty(document, "No position yet", "A Council preserves disagreement before it records a decision."));
    }
    for (const position of positions) {
      const row = element(document, "article", "nur-adjunct-row");
      row.append(element(document, "p", undefined, position.position));
      if (position.is_minority) row.append(element(document, "span", "nur-adjunct-chip", "MINORITY POSITION"));
      positionList.append(row);
    }
    const positionInput = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
    positionInput.id = "nur-v197-council-position";
    positionInput.placeholder = "State one position without erasing disagreement";
    const addPosition = button(document, "Add position", "council-position-add", true);
    const councilState = status(document, "Every position is persisted with its real owner.");
    council.append(positionList, positionInput, addPosition, councilState);
    addPosition.addEventListener("click", async () => {
      if (!positionInput.value.trim()) return;
      addPosition.disabled = true;
      try {
        await api.createCouncilPosition(roomId, positionInput.value.trim());
        await renderCommunityRoom(document, api, roomId);
      } catch (error) {
        councilState.textContent = error instanceof Error ? error.message : "Position was not saved.";
        councilState.className = "nur-adjunct-status is-warn";
        addPosition.disabled = false;
      }
    });
    if (text(room.current_user_role) === "OWNER") {
      const decisionInput = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
      decisionInput.id = "nur-v197-council-decision";
      decisionInput.placeholder = "Record the bounded Council decision";
      const recordDecision = button(document, "Record decision", "council-decision-record");
      council.append(decisionInput, recordDecision);
      recordDecision.addEventListener("click", async () => {
        if (!decisionInput.value.trim()) return;
        recordDecision.disabled = true;
        try {
          await api.createCouncilDecision(roomId, decisionInput.value.trim());
          await renderCommunityRoom(document, api, roomId);
        } catch (error) {
          councilState.textContent = error instanceof Error ? error.message : "Decision was not saved.";
          councilState.className = "nur-adjunct-status is-warn";
          recordDecision.disabled = false;
        }
      });
    }
    grid.append(council);
  }
}

async function renderCommunityPost(document: Document, api: V197ApiClient, postId: string): Promise<void> {
  const requestedRoom = new URL(window.location.href).searchParams.get("room");
  const rooms = await api.communityRooms();
  let roomId = requestedRoom;
  let post: V197CommunityPost | undefined;
  if (roomId) post = (await api.communityPosts(roomId)).find(row => row.id === postId);
  if (!post) {
    for (const room of rooms) {
      const found = (await api.communityPosts(room.id)).find(row => row.id === postId);
      if (found) { post = found; roomId = room.id; break; }
    }
  }
  if (!post || !roomId) throw new Error("This thread is not available inside your room memberships.");
  const comments = await api.communityComments(roomId, postId);
  const shell = mount(document, post.title, post.body, `/universe/community/room/${roomId}`);
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const thread = panel(document, "Bounded thread", `${post.is_demo ? "DEMO · " : ""}${post.provenance_label}`);
  thread.classList.add("is-wide");
  thread.append(element(document, "p", undefined, post.body));
  const reactions = element(document, "div", "nur-adjunct-actions");
  const useful = button(document, "✦ Useful", "community-react-useful");
  const witness = button(document, "Witness", "community-react-witness");
  const reactionState = status(document, "Reactions are unique persisted room records.");
  const react = async (reaction: string) => {
    useful.disabled = true; witness.disabled = true;
    try {
      await api.createCommunityReaction(roomId!, "POST", postId, reaction);
      reactionState.textContent = `${reaction} reaction persisted.`;
      reactionState.className = "nur-adjunct-status is-good";
    } catch (error) {
      reactionState.textContent = error instanceof Error ? error.message : "Reaction failed.";
      reactionState.className = "nur-adjunct-status is-warn";
    }
  };
  useful.addEventListener("click", () => void react("USEFUL"));
  witness.addEventListener("click", () => void react("WITNESS"));
  reactions.append(useful, witness);
  thread.append(reactions, reactionState);

  const discussion = panel(document, "Discussion", `Replies · ${comments.length}`);
  discussion.classList.add("is-wide");
  const list = element(document, "div", "nur-adjunct-list");
  if (!comments.length) list.append(empty(document, "No reply yet", "No fabricated person is waiting here."));
  for (const comment of comments) {
    const row = element(document, "article", "nur-adjunct-row");
    row.append(element(document, "span", "nur-adjunct-chip", comment.is_demo ? "DEMO" : "MEMBER_WRITTEN"), element(document, "p", undefined, comment.body));
    list.append(row);
  }
  const reply = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  reply.placeholder = "Reply with experience, evidence, constraint or disagreement…";
  const send = button(document, "Reply", "community-comment-create", true);
  const replyState = status(document, "The reply remains inside this room thread.");
  discussion.append(list, reply, send, replyState);
  send.addEventListener("click", async () => {
    if (!reply.value.trim()) return;
    send.disabled = true;
    try {
      const saved = await api.createCommunityComment(roomId!, postId, reply.value.trim(), document.documentElement.lang || "en");
      replyState.textContent = saved.glow?.status === "AWARDED" ? `Reply persisted · +${saved.glow.awarded_points} Glow` : "Reply persisted.";
      replyState.className = "nur-adjunct-status is-good";
      await renderCommunityPost(document, api, postId);
    } catch (error) {
      replyState.textContent = error instanceof Error ? error.message : "Reply was not saved.";
      replyState.className = "nur-adjunct-status is-warn";
      send.disabled = false;
    }
  });
  grid.append(thread, discussion);
}

async function renderProjectsIndex(document: Document, api: V197ApiClient): Promise<void> {
  const projects = await api.projects();
  const shell = mount(document, "Intent becomes evidence, then a shipped result.", "AM Projects keeps objective, tasks, bounded agent proposals, evidence, reviews and owner approval in one Project Orbit.");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const ledger = panel(document, "Owner Project ledger", `Projects · ${projects.length}`);
  const list = element(document, "div", "nur-adjunct-list");
  if (!projects.length) list.append(empty(document, "No Project yet", "Create one objective. No agent gets authority merely because a card exists."));
  for (const project of projects) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, text(project.title)), element(document, "span", "nur-adjunct-chip", text(project.status)));
    row.append(head, element(document, "p", undefined, text(project.objective)));
    const open = button(document, "Open Project Orbit", `project-open-${recordId(project)}`);
    open.addEventListener("click", () => navigate(`/projects/${recordId(project)}/overview`));
    row.append(open);
    list.append(row);
  }
  ledger.append(list);

  const create = panel(document, "New Project Orbit", "Define what done means");
  const title = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  title.placeholder = "Project title";
  const objective = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  objective.placeholder = "Objective and success definition…";
  const system = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  for (const value of ["quiet-ambition", "rebuild", "study", "money", "body", "connection", "creation"]) {
    const option = element(document, "option", undefined, value.replaceAll("-", " ")) as HTMLOptionElement;
    option.value = value;
    system.append(option);
  }
  const createButton = button(document, "Create Project Orbit", "project-create", true);
  const createState = status(document, "External actions remain denied until an owner explicitly approves a bounded run.");
  create.append(title, objective, system, createButton, createState);
  createButton.addEventListener("click", async () => {
    if (!title.value.trim() || !objective.value.trim()) {
      createState.textContent = "A Project needs a title and objective.";
      createState.className = "nur-adjunct-status is-warn";
      return;
    }
    createButton.disabled = true;
    try {
      const created = await api.createProject({ title: title.value.trim(), objective: objective.value.trim(), system_slug: system.value });
      navigate(`/projects/${recordId(created)}/overview`);
    } catch (error) {
      createState.textContent = error instanceof Error ? error.message : "Project was not created.";
      createState.className = "nur-adjunct-status is-warn";
      createButton.disabled = false;
    }
  });
  grid.append(ledger, create);
}

async function renderProjectDetail(document: Document, api: V197ApiClient, projectId: string, route: string): Promise<void> {
  const [project, tasks, runs, evidence, reviews, artifacts, files] = await Promise.all([
    api.project(projectId), api.projectTasks(projectId), api.projectRuns(projectId),
    api.projectEvidence(projectId), api.projectReviews(projectId), api.projectArtifacts(projectId),
    api.projectFiles(projectId),
  ]);
  const shell = mount(document, text(project.title), text(project.objective), "/projects");
  const tabs = element(document, "nav", "nur-adjunct-actions");
  const tabNames = ["overview", "tasks", "evidence", "agents", "runs", "deliverables"];
  for (const tab of tabNames) {
    const control = button(document, tab.replaceAll("-", " "), `project-tab-${tab}`, route.endsWith(`/${tab}`));
    control.addEventListener("click", () => navigate(`/projects/${projectId}/${tab}`));
    tabs.append(control);
  }
  shell.append(tabs);
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const state = panel(document, "Project Orbit", `${text(project.status)} · ${text(project.system_slug, "unassigned system")}`);
  state.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "Tasks", text(tasks.length)), fact(document, "Passed evidence", text(evidence.filter(row => row.verification_status === "PASSED").length)), fact(document, "Agent proposals", text(runs.length)), fact(document, "Owner reviews", text(reviews.length)));
  state.append(facts, element(document, "p", "nur-adjunct-boundary", "No run can pre-authorize spending, publishing, deployment, messaging, secret access or security changes."));

  const taskPanel = panel(document, "Execution", `Tasks · ${tasks.length}`);
  const taskList = element(document, "div", "nur-adjunct-list");
  for (const task of tasks) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, text(task.title)), element(document, "span", "nur-adjunct-chip", text(task.status)));
    row.append(head, element(document, "p", undefined, text(task.acceptance_criteria, "Acceptance criteria not set")));
    if (task.status !== "DONE") {
      const done = button(document, "Close with passed evidence", `project-task-done-${recordId(task)}`);
      done.addEventListener("click", async () => {
        try {
          await api.patchProjectTask(recordId(task), { status: "DONE" });
          await renderProjectDetail(document, api, projectId, route);
        } catch (error) {
          const note = status(document, error instanceof Error ? error.message : "Task completion was rejected.", "warn");
          row.append(note);
        }
      });
      row.append(done);
    }
    taskList.append(row);
  }
  const taskTitle = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  taskTitle.placeholder = "One concrete task";
  const criteria = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  criteria.placeholder = "Acceptance criteria";
  const addTask = button(document, "Add task", "project-task-create", true);
  const taskState = status(document, "A task cannot become DONE without PASSED evidence.");
  taskPanel.append(taskList, taskTitle, criteria, addTask, taskState);
  addTask.addEventListener("click", async () => {
    if (!taskTitle.value.trim() || !criteria.value.trim()) return;
    addTask.disabled = true;
    try {
      await api.createProjectTask(projectId, { title: taskTitle.value.trim(), acceptance_criteria: criteria.value.trim(), assigned_role: "implementer" });
      await renderProjectDetail(document, api, projectId, route);
    } catch (error) {
      taskState.textContent = error instanceof Error ? error.message : "Task was not created.";
      taskState.className = "nur-adjunct-status is-warn";
      addTask.disabled = false;
    }
  });

  const proof = panel(document, "Evidence gate", `Evidence · ${evidence.length}`);
  const proofList = element(document, "div", "nur-adjunct-list");
  for (const item of evidence) {
    const row = element(document, "article", "nur-adjunct-row");
    row.append(element(document, "span", "nur-adjunct-chip", text(item.verification_status)), element(document, "p", undefined, text(item.summary)));
    proofList.append(row);
  }
  const proofSummary = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  proofSummary.placeholder = "What was verified?";
  const proofLocator = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  proofLocator.placeholder = "Evidence locator/path/URL";
  const taskSelect = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  taskSelect.append(element(document, "option", undefined, "Project-level evidence"));
  taskSelect.options[0].value = "";
  for (const task of tasks) {
    const option = element(document, "option", undefined, text(task.title)) as HTMLOptionElement;
    option.value = recordId(task);
    taskSelect.append(option);
  }
  const addEvidence = button(document, "Record passed evidence", "project-evidence-create", true);
  const proofState = status(document, "PASSED evidence requires both a named verifier and a locator.");
  proof.append(proofList, taskSelect, proofSummary, proofLocator, addEvidence, proofState);
  addEvidence.addEventListener("click", async () => {
    if (!proofSummary.value.trim() || !proofLocator.value.trim()) return;
    addEvidence.disabled = true;
    try {
      const saved = await api.createProjectEvidence(projectId, {
        task_id: taskSelect.value || null, evidence_kind: "TEST_OUTPUT",
        summary: proofSummary.value.trim(), locator: proofLocator.value.trim(),
        verification_status: "PASSED", verifier: "OWNER",
      });
      const glow = saved.glow as Record<string, unknown> | undefined;
      proofState.textContent = glow?.status === "AWARDED" ? `Evidence persisted · +${text(glow.awarded_points, "0")} Glow` : "Evidence persisted.";
      await renderProjectDetail(document, api, projectId, route);
    } catch (error) {
      proofState.textContent = error instanceof Error ? error.message : "Evidence was not recorded.";
      proofState.className = "nur-adjunct-status is-warn";
      addEvidence.disabled = false;
    }
  });

  const agent = panel(document, "Bounded agent work", `Runs · ${runs.length}`);
  const runList = element(document, "div", "nur-adjunct-list");
  for (const run of runs) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, text(run.role)), element(document, "span", "nur-adjunct-chip", text(run.status)));
    row.append(head, element(document, "p", undefined, text(run.request_summary)));
    if (run.status === "PROPOSED") {
      const actions = element(document, "div", "nur-adjunct-actions");
      const approve = button(document, "Approve bounded run", `project-run-approve-${recordId(run)}`, true);
      const cancel = button(document, "Cancel", `project-run-cancel-${recordId(run)}`);
      approve.addEventListener("click", async () => { await api.projectRunAction(recordId(run), "approve"); await renderProjectDetail(document, api, projectId, route); });
      cancel.addEventListener("click", async () => { await api.projectRunAction(recordId(run), "cancel"); await renderProjectDetail(document, api, projectId, route); });
      actions.append(approve, cancel); row.append(actions);
    }
    runList.append(row);
  }
  const role = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  for (const value of ["architect", "implementer", "researcher", "visual reviewer", "QA", "security reviewer", "writer", "translator"]) {
    const option = element(document, "option", undefined, value) as HTMLOptionElement; option.value = value; role.append(option);
  }
  const request = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  request.placeholder = "Propose a scoped task. This records intent; it does not execute autonomously.";
  const propose = button(document, "Propose agent run", "project-run-propose", true);
  const runState = status(document, "Owner approval changes PROPOSED to APPROVED. It still does not grant external action authority.");
  agent.append(runList, role, request, propose, runState);
  propose.addEventListener("click", async () => {
    if (!request.value.trim()) return;
    propose.disabled = true;
    try {
      await api.proposeProjectRun(projectId, { role: role.value, request_summary: request.value.trim(), task_id: tasks.length ? recordId(tasks[0]) : null });
      await renderProjectDetail(document, api, projectId, route);
    } catch (error) {
      runState.textContent = error instanceof Error ? error.message : "Run proposal failed.";
      runState.className = "nur-adjunct-status is-warn";
      propose.disabled = false;
    }
  });

  const review = panel(document, "Owner review", `Reviews · ${reviews.length} · Artifacts · ${artifacts.length}`);
  const reviewList = element(document, "div", "nur-adjunct-list");
  for (const item of reviews) {
    const row = element(document, "article", "nur-adjunct-row");
    row.append(element(document, "span", "nur-adjunct-chip", text(item.decision)), element(document, "p", undefined, text(item.note, "No note")));
    reviewList.append(row);
  }
  const reviewNote = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  reviewNote.placeholder = "Why is this accepted, rejected or corrected?";
  const approveReview = button(document, "Record owner approval", "project-review-create", true);
  const reviewState = status(document, "Review records judgment; it does not rewrite evidence.");
  review.append(reviewList, reviewNote, approveReview, reviewState);
  approveReview.addEventListener("click", async () => {
    if (!reviewNote.value.trim()) return;
    approveReview.disabled = true;
    try {
      await api.createProjectReview(projectId, { decision: "APPROVE", note: reviewNote.value.trim() });
      await renderProjectDetail(document, api, projectId, route);
    } catch (error) {
      reviewState.textContent = error instanceof Error ? error.message : "Review was not saved.";
      reviewState.className = "nur-adjunct-status is-warn";
      approveReview.disabled = false;
    }
  });
  const deliverables = buildDeliverablesPanel(document, api, projectId, route, files, tasks);

  // Every visible tab owns an implemented surface. Retired deep links resolve
  // to overview without exposing an empty placeholder tab.
  const activeTab = tabNames.find(tab => route.endsWith(`/${tab}`)) ?? "overview";
  const panelsByTab: Record<string, HTMLElement[]> = {
    overview: [state, taskPanel, proof, agent, deliverables, review],
    tasks: [state, taskPanel],
    evidence: [state, proof],
    agents: [state, agent],
    runs: [state, agent],
    deliverables: [state, deliverables],
  };
  const visible = panelsByTab[activeTab] ?? panelsByTab.overview;
  grid.append(...visible);
}

function humanBytes(size: unknown): string {
  const n = typeof size === "number" ? size : Number(size);
  if (!Number.isFinite(n) || n < 0) return "—";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

async function triggerBrowserDownload(api: V197ApiClient, fileId: string, filename: string): Promise<void> {
  const blob = await api.downloadProjectFile(fileId);
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename || "download";
  anchor.dataset.adjunctDownload = fileId;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 10_000);
}

function buildDeliverablesPanel(
  document: Document,
  api: V197ApiClient,
  projectId: string,
  route: string,
  files: Array<Record<string, unknown>>,
  tasks: Array<Record<string, unknown>>,
): HTMLElement {
  const deliverables = panel(document, "Deliverables", `Files · ${files.length}`);
  deliverables.classList.add("is-wide");
  deliverables.dataset.adjunctPanel = "deliverables";
  const fileList = element(document, "div", "nur-adjunct-list");
  fileList.dataset.adjunctList = "project-files";
  if (!files.length) fileList.append(empty(document, "No stored bytes yet", "Upload a real file, or generate an evidence package. Nothing is invented."));
  for (const file of files) {
    const row = element(document, "article", "nur-adjunct-row");
    row.dataset.adjunctFile = recordId(file);
    const head = element(document, "div", "nur-adjunct-row-head");
    const stateLabel = `${text(file.provenance)} · ${text(file.storage_state)}`;
    head.append(
      element(document, "strong", undefined, text(file.original_filename, "file")),
      element(document, "span", "nur-adjunct-chip", stateLabel),
    );
    row.append(head, element(document, "p", undefined, `${humanBytes(file.byte_size)} · sha256 ${text(file.checksum_sha256, "—").slice(0, 12)}… · scan ${text(file.scan_state)}`));
    const actions = element(document, "div", "nur-adjunct-actions");
    if (file.storage_state === "STORED") {
      const download = button(document, "Download", `project-file-download-${recordId(file)}`);
      download.addEventListener("click", async () => {
        download.disabled = true;
        try {
          await triggerBrowserDownload(api, recordId(file), text(file.safe_filename, "download"));
        } catch (error) {
          row.append(status(document, error instanceof Error ? error.message : "Download failed.", "warn"));
        } finally {
          download.disabled = false;
        }
      });
      actions.append(download);
    } else if (file.storage_state === "QUARANTINED") {
      actions.append(status(document, text(file.quarantine_reason, "Quarantined; download blocked."), "warn"));
    }
    row.append(actions);
    fileList.append(row);
  }

  const upload = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  upload.type = "file";
  upload.dataset.adjunctControl = "project-file-input";
  const uploadButton = button(document, "Upload file", "project-file-upload", true);
  const generate = button(document, "Generate evidence package", "project-run-evidence-package");
  const deliverState = status(document, "Files are owner-scoped real bytes. Executable formats are quarantined; no run gains authority beyond its approved, deny-by-default capabilities.");
  deliverables.append(fileList, upload, uploadButton, generate, deliverState);

  uploadButton.addEventListener("click", async () => {
    const chosen = upload.files?.[0];
    if (!chosen) {
      deliverState.textContent = "Choose a file to upload.";
      deliverState.className = "nur-adjunct-status is-warn";
      return;
    }
    uploadButton.disabled = true;
    try {
      const saved = await api.uploadProjectFile(projectId, chosen);
      const quarantined = (saved as Record<string, unknown>).storage_state === "QUARANTINED";
      deliverState.textContent = quarantined
        ? "Stored but quarantined: executable/script formats cannot be downloaded (no scanner connected)."
        : "File stored with a verified checksum.";
      deliverState.className = quarantined ? "nur-adjunct-status is-warn" : "nur-adjunct-status is-good";
      await renderProjectDetail(document, api, projectId, route);
    } catch (error) {
      deliverState.textContent = error instanceof Error ? error.message : "Upload failed.";
      deliverState.className = "nur-adjunct-status is-warn";
      uploadButton.disabled = false;
    }
  });

  generate.addEventListener("click", async () => {
    generate.disabled = true;
    deliverState.textContent = "Proposing, approving and queueing a bounded EVIDENCE_PACKAGE run…";
    deliverState.className = "nur-adjunct-status is-quiet";
    try {
      const firstTaskId = tasks.length ? recordId(tasks[0]) : null;
      const proposed = await api.proposeExecutionRun(projectId, {
        role: "verifier", request_summary: "Generate a deterministic evidence package.",
        adapter_key: "EVIDENCE_PACKAGE", task_id: firstTaskId,
      });
      const runId = recordId(proposed);
      await api.projectRunAction(runId, "approve");
      let run = await api.projectRunAction(runId, "queue");
      // In queued (non-inline) mode the worker runs asynchronously; poll for truth.
      for (let attempt = 0; attempt < 20 && text(run.status) === "QUEUED"; attempt += 1) {
        await new Promise(resolve => window.setTimeout(resolve, 500));
        run = await api.projectRun(runId);
      }
      const finalStatus = text(run.status);
      if (finalStatus === "SUCCEEDED") {
        deliverState.textContent = "Evidence package generated. It is listed above as a downloadable deliverable.";
        deliverState.className = "nur-adjunct-status is-good";
      } else if (finalStatus === "RUNNING" || finalStatus === "QUEUED") {
        deliverState.textContent = "The run is executing on the queue. Refresh shortly to download the package.";
        deliverState.className = "nur-adjunct-status is-quiet";
      } else {
        deliverState.textContent = `The run did not succeed (${finalStatus}${run.failure_code ? ` · ${text(run.failure_code)}` : ""}). Nothing was fabricated.`;
        deliverState.className = "nur-adjunct-status is-warn";
      }
      await renderProjectDetail(document, api, projectId, route);
    } catch (error) {
      deliverState.textContent = error instanceof Error ? error.message : "The evidence package run failed.";
      deliverState.className = "nur-adjunct-status is-warn";
      generate.disabled = false;
    }
  });

  return deliverables;
}

function renderGlow(document: Document, snapshot: V197BridgeSnapshot): void {
  const glow = snapshot.glow;
  const shell = mount(document, "Movement becomes visible light.", "Glow is a persisted, source-linked economy. Points appear only after a server-verified action; caps, idempotency and DEMO gates remain active.");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const level = panel(document, "Current constellation", `${glow.rank} · Level ${glow.level}`);
  level.classList.add("is-wide");
  const facts = element(document, "div", "nur-adjunct-facts");
  facts.append(fact(document, "Available Glow", text(glow.balance)), fact(document, "Lifetime", text(glow.lifetime_points)), fact(document, "Today", text(glow.today_points)), fact(document, "This week", text(glow.weekly_points)));
  level.append(facts);
  if (glow.next_unlock) {
    const remaining = text((glow.next_unlock as Record<string, unknown>).points_remaining, "0");
    const rank = text((glow.next_unlock as Record<string, unknown>).rank, "next constellation");
    level.append(status(document, `${remaining} source-linked Glow until ${rank}.`));
  } else level.append(status(document, "Current configured constellation reached.", "good"));

  const quests = panel(document, "Return tension", "Quests and mission");
  const questRows = [glow.daily_quest, glow.weekly_mission].filter(Boolean) as Array<Record<string, unknown>>;
  const questList = element(document, "div", "nur-adjunct-list");
  for (const quest of questRows) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, text(quest.title)), element(document, "span", "nur-adjunct-chip", quest.completed ? "RETURNED" : `${text(quest.progress, "0")}/${text(quest.target, "1")}`));
    row.append(head);
    questList.append(row);
  }
  if (!questRows.length) questList.append(empty(document, "No active quest", "NUR will not invent progress."));
  quests.append(questList);

  const streaks = panel(document, "Continuity", `Streaks · ${glow.streaks.length}`);
  const streakList = element(document, "div", "nur-adjunct-list");
  for (const streak of glow.streaks) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, streak.streak_key.replaceAll("_", " ")), element(document, "span", "nur-adjunct-chip", `${streak.current_count} current · ${streak.best_count} best`));
    row.append(head, element(document, "p", undefined, streak.repairs_remaining ? `${streak.repairs_remaining} recovery token${streak.repairs_remaining === 1 ? "" : "s"}` : "No recovery token recorded"));
    streakList.append(row);
  }
  if (!glow.streaks.length) streakList.append(empty(document, "No streak yet", "One eligible persisted action starts continuity."));
  streaks.append(streakList);

  const ledger = panel(document, "Source-linked ledger", `Recent Glow · ${glow.recent_transactions.length}`);
  ledger.classList.add("is-wide");
  const transactionList = element(document, "div", "nur-adjunct-list");
  for (const transaction of glow.recent_transactions) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, transaction.reason), element(document, "span", "nur-adjunct-chip", `+${transaction.final_points}`));
    row.append(head, element(document, "p", undefined, `${transaction.event_type} · ${date(transaction.created_at)}`));
    transactionList.append(row);
  }
  if (!glow.recent_transactions.length) transactionList.append(empty(document, "No transaction yet", "No points are displayed without persisted proof."));
  ledger.append(transactionList);
  grid.append(level, quests, streaks, ledger);
}

async function renderNotifications(document: Document, api: V197ApiClient): Promise<void> {
  const [preferences, notifications] = await Promise.all([api.notificationPreferences(), api.notifications()]);
  const shell = mount(document, "Return cues, under your control.", "NUR notifications are owner-scoped and factual. There are no fabricated replies, fake urgency or hidden external delivery channels.");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const inbox = panel(document, "In-app ledger", `Notifications · ${notifications.length}`);
  const list = element(document, "div", "nur-adjunct-list");
  if (!notifications.length) list.append(empty(document, "Nothing is demanding your attention", "NUR will not manufacture a social obligation."));
  for (const notification of notifications) {
    const row = element(document, "article", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, text(notification.title)), element(document, "span", "nur-adjunct-chip", `${notification.is_demo ? "DEMO · " : ""}${text(notification.category)}`));
    row.append(head, element(document, "p", undefined, text(notification.body)));
    const actions = element(document, "div", "nur-adjunct-actions");
    if (notification.route) {
      const open = button(document, "Open", `notification-open-${recordId(notification)}`);
      open.addEventListener("click", () => navigate(text(notification.route, "/today")));
      actions.append(open);
    }
    if (!notification.read_at) {
      const read = button(document, "Mark read", `notification-read-${recordId(notification)}`);
      read.addEventListener("click", async () => { await api.markNotificationRead(recordId(notification)); await renderNotifications(document, api); });
      actions.append(read);
    }
    row.append(actions);
    list.append(row);
  }
  inbox.append(list);

  const controls = panel(document, "Delivery boundary", "Frequency and quiet hours");
  const frequency = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  frequency.dataset.adjunctControl = "notification-frequency";
  for (const value of ["QUIET", "BALANCED", "ACTIVE"]) {
    const option = element(document, "option", undefined, value.toLowerCase()) as HTMLOptionElement;
    option.value = value; option.selected = value === preferences.frequency; frequency.append(option);
  }
  const quietStart = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  quietStart.dataset.adjunctControl = "notification-quiet-start";
  quietStart.type = "time"; quietStart.value = text(preferences.quiet_hours_start, "");
  const quietEnd = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  quietEnd.dataset.adjunctControl = "notification-quiet-end";
  quietEnd.type = "time"; quietEnd.value = text(preferences.quiet_hours_end, "");
  const save = button(document, "Save notification boundary", "notification-preferences-save", true);
  const preferenceState = status(document, `${text(preferences.delivery_status, "IN_APP_ONLY")} · external push is not claimed.`);
  controls.append(frequency, quietStart, quietEnd, save, preferenceState);
  save.addEventListener("click", async () => {
    save.disabled = true;
    try {
      await api.patchNotificationPreferences({ category_settings: preferences.category_settings ?? {}, frequency: frequency.value, quiet_hours_start: quietStart.value || null, quiet_hours_end: quietEnd.value || null, push_enabled: false, email_enabled: false });
      preferenceState.textContent = "Notification boundary persisted.";
      preferenceState.className = "nur-adjunct-status is-good";
    } catch (error) {
      preferenceState.textContent = error instanceof Error ? error.message : "Preferences were not saved.";
      preferenceState.className = "nur-adjunct-status is-warn";
      save.disabled = false;
    }
  });

  const reminder = panel(document, "Owner reminder", "Create one truthful re-entry cue");
  const title = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  title.dataset.adjunctControl = "notification-title";
  title.placeholder = "What should return?";
  const body = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  body.dataset.adjunctControl = "notification-body";
  body.placeholder = "Why will this still matter?";
  const route = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  route.dataset.adjunctControl = "notification-route";
  route.placeholder = "/plan";
  const create = button(document, "Create in-app reminder", "notification-reminder-create", true);
  const reminderState = status(document, "This creates a real owner-written reminder, not a fake human ping.");
  reminder.append(title, body, route, create, reminderState);
  create.addEventListener("click", async () => {
    if (!title.value.trim() || !body.value.trim()) return;
    create.disabled = true;
    try {
      await api.createReminder({ category: "PROGRESS", title: title.value.trim(), body: body.value.trim(), route: route.value.trim() || "/today" });
      await renderNotifications(document, api);
    } catch (error) {
      reminderState.textContent = error instanceof Error ? error.message : "Reminder was not created.";
      reminderState.className = "nur-adjunct-status is-warn";
      create.disabled = false;
    }
  });
  grid.append(inbox, controls, reminder);
}

const AGENTIC_TERMINAL_STATES = new Set(["SUCCEEDED", "FAILED", "CANCELLED", "EXPIRED"]);

function agenticField(
  document: Document,
  label: string,
  control: HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement,
): HTMLElement {
  const field = element(document, "label", "nur-adjunct-field");
  field.append(element(document, "span", undefined, label), control);
  return field;
}

function agenticSelect(document: Document, action: string): HTMLSelectElement {
  const select = element(document, "select", "nur-adjunct-select") as HTMLSelectElement;
  select.dataset.adjunctControl = action;
  return select;
}

function agenticOption(document: Document, value: string, label = value): HTMLOptionElement {
  const option = element(document, "option", undefined, label);
  option.value = value;
  return option;
}

function agenticWorkflowRows(
  document: Document,
  workflows: V197AgenticWorkflow[],
): HTMLElement {
  const grouped = groupWorkflows(workflows);
  const container = element(document, "div", "nur-agentic-groups");
  for (const section of DRAWER_SECTIONS) {
    const group = element(document, "section", "nur-agentic-group");
    group.append(element(document, "h3", undefined, `${section.label} · ${grouped[section.id].length}`));
    const list = element(document, "div", "nur-adjunct-list");
    for (const workflow of grouped[section.id]) {
      const row = element(document, "div", "nur-adjunct-row");
      const head = element(document, "div", "nur-adjunct-row-head");
      head.append(
        element(document, "strong", undefined, workflow.title),
        element(document, "span", "nur-adjunct-chip", workflow.state),
      );
      const progress = `${workflow.steps_done}/${workflow.step_count} steps · ${workflow.cost_cents} cents recorded`;
      const actions = element(document, "div", "nur-adjunct-actions");
      const open = button(document, "Open run ledger", `agentic-open-${workflow.id}`);
      open.addEventListener("click", () => navigate(`/agents/${workflow.id}`));
      actions.append(open);
      row.append(head, element(document, "p", undefined, workflow.objective), element(document, "p", undefined, progress), actions);
      list.append(row);
    }
    if (!grouped[section.id].length) list.append(empty(document, `Nothing ${section.label.toLowerCase()}`, "No owner-scoped workflow is placed here."));
    group.append(list);
    container.append(group);
  }
  return container;
}

async function renderAgents(
  document: Document,
  api: V197ApiClient,
  session: V197Session,
): Promise<void> {
  const [tools, policy, workflows, approvals] = await Promise.all([
    api.agenticTools(),
    api.agenticPolicy(),
    api.agenticWorkflows(),
    api.agenticApprovals(),
  ]);
  const shell = mount(
    document,
    "Agency under your authority.",
    "NUR can only run a bounded, owner-authored plan through the persisted policy, approval ledger and durable outbox.",
    "/systems",
  );
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);

  const policyPanel = panel(document, "Owner policy", "What NUR may prepare or run");
  policyPanel.classList.add("is-wide");
  const policyFacts = element(document, "div", "nur-adjunct-facts");
  policyFacts.append(
    fact(document, "Scope", "Account only"),
    fact(document, "Persisted", policy.persisted ? "Yes" : "No policy row yet"),
    fact(document, "Capabilities", policy.granted_capabilities.join(", ") || "None"),
  );
  const initiative = agenticSelect(document, "agentic-initiative");
  for (const level of ["OFF", "SUGGEST", "PREPARE", "INTERNAL", "CONNECTED", "DELEGATED"] as const) {
    const option = agenticOption(document, level, level.replace(/_/g, " "));
    option.selected = policy.initiative_level === level;
    initiative.append(option);
  }
  const maxRisk = agenticSelect(document, "agentic-max-risk");
  for (const risk of ["R0_READ_ONLY", "R1_PRIVATE_DRAFT", "R2_DURABLE_PRIVATE", "R3_EXTERNAL", "R4_IRREVERSIBLE"] as AgenticRiskClass[]) {
    const option = agenticOption(document, risk, describeRisk(risk, true).split(".")[0]);
    option.selected = policy.max_risk_class === risk;
    maxRisk.append(option);
  }
  const dailyBudget = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  dailyBudget.type = "number";
  dailyBudget.min = "0";
  dailyBudget.max = "10000000";
  dailyBudget.step = "1";
  dailyBudget.value = String(policy.daily_budget_cents);
  dailyBudget.dataset.adjunctControl = "agentic-daily-budget";
  const policyControls = element(document, "div", "nur-agentic-policy-controls");
  policyControls.append(
    agenticField(document, "Initiative level", initiative),
    agenticField(document, "Maximum risk class", maxRisk),
    agenticField(document, "Daily cost ceiling in cents", dailyBudget),
  );
  const toolList = element(document, "div", "nur-adjunct-list");
  for (const tool of tools) {
    const row = element(document, "div", "nur-adjunct-row nur-agentic-tool");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(
      element(document, "strong", undefined, tool.key.replace(/_/g, " ")),
      element(document, "span", "nur-adjunct-chip", tool.bound ? tool.risk_class : "UNBOUND"),
    );
    const permissions = element(document, "div", "nur-agentic-tool-permissions");
    const permitLabel = element(document, "label", "nur-adjunct-toggle");
    permitLabel.append(element(document, "span", undefined, "Permit this tool"));
    const permit = element(document, "input") as HTMLInputElement;
    permit.type = "checkbox";
    permit.checked = tool.bound && policy.permitted_tools.includes(tool.key);
    permit.disabled = !tool.bound;
    permit.dataset.agenticPermit = tool.key;
    permitLabel.append(permit);
    const autoLabel = element(document, "label", "nur-adjunct-toggle");
    autoLabel.append(element(document, "span", undefined, "Allow policy auto-run"));
    const auto = element(document, "input") as HTMLInputElement;
    auto.type = "checkbox";
    auto.checked = tool.bound && policy.auto_run_tools.includes(tool.key);
    auto.disabled = !tool.bound || !permit.checked;
    auto.dataset.agenticAuto = tool.key;
    permit.addEventListener("change", () => {
      auto.disabled = !permit.checked;
      if (!permit.checked) auto.checked = false;
    });
    autoLabel.append(auto);
    permissions.append(permitLabel, autoLabel);
    row.append(head, element(document, "p", undefined, tool.summary), element(document, "p", undefined, describeRisk(tool.risk_class, tool.reversible)), permissions);
    toolList.append(row);
  }
  const policyActions = element(document, "div", "nur-adjunct-actions");
  const savePolicy = button(document, "Save agency policy", "agentic-policy-save", true);
  const policyState = status(document, "Unbound tools stay visible but cannot be permitted or called.");
  policyActions.append(savePolicy);
  policyPanel.append(policyFacts, policyControls, toolList, policyActions, policyState);
  savePolicy.addEventListener("click", async () => {
    savePolicy.disabled = true;
    const permitted = [...policyPanel.querySelectorAll<HTMLInputElement>("[data-agentic-permit]:checked")]
      .map(input => input.dataset.agenticPermit ?? "").filter(Boolean);
    const autoRun = [...policyPanel.querySelectorAll<HTMLInputElement>("[data-agentic-auto]:checked")]
      .map(input => input.dataset.agenticAuto ?? "").filter(key => key && permitted.includes(key));
    try {
      const next = await api.putAgenticPolicy({
        initiative_level: initiative.value as V197AgenticPolicy["initiative_level"],
        max_risk_class: maxRisk.value as AgenticRiskClass,
        permitted_tools: permitted,
        auto_run_tools: autoRun,
        denied_tools: policy.denied_tools.filter(key => !permitted.includes(key)),
        daily_budget_cents: Math.max(0, Number.parseInt(dailyBudget.value || "0", 10)),
        max_proposals_per_day: policy.max_proposals_per_day,
        cooldown_minutes: policy.cooldown_minutes,
        quiet_hours: policy.quiet_hours && Object.keys(policy.quiet_hours).length ? policy.quiet_hours : null,
      });
      policy.permitted_tools = next.permitted_tools;
      policy.auto_run_tools = next.auto_run_tools;
      policyState.textContent = "Owner policy persisted. No workflow was started.";
      policyState.className = "nur-adjunct-status is-good";
    } catch (error) {
      policyState.textContent = error instanceof Error ? error.message : "Agency policy could not be saved.";
      policyState.className = "nur-adjunct-status is-warn";
    } finally {
      savePolicy.disabled = false;
    }
  });

  const builder = panel(document, "Owner-authored workflow", "One bounded step at a time");
  const title = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  title.dataset.adjunctControl = "agentic-title";
  title.placeholder = "Name this workflow";
  title.maxLength = 400;
  const objective = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  objective.dataset.adjunctControl = "agentic-objective";
  objective.placeholder = "What exact result should this workflow pursue?";
  objective.maxLength = 5000;
  const success = element(document, "input", "nur-adjunct-input") as HTMLInputElement;
  success.dataset.adjunctControl = "agentic-success";
  success.placeholder = "What observable result counts as done?";
  success.maxLength = 500;
  const toolSelect = agenticSelect(document, "agentic-tool");
  for (const tool of tools.filter(row => row.bound)) toolSelect.append(agenticOption(document, tool.key, tool.key.replace(/_/g, " ")));
  const role = agenticSelect(document, "agentic-role");
  for (const value of ["operator", "researcher", "implementer", "writer", "translator", "verifier", "critic", "qa", "security_reviewer", "visual_reviewer"]) {
    role.append(agenticOption(document, value, value.replace(/_/g, " ")));
  }
  const argumentsInput = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  argumentsInput.dataset.adjunctControl = "agentic-arguments";
  argumentsInput.value = "{}";
  argumentsInput.spellcheck = false;
  const rationale = element(document, "textarea", "nur-adjunct-textarea") as HTMLTextAreaElement;
  rationale.dataset.adjunctControl = "agentic-rationale";
  rationale.placeholder = "Why is this step necessary?";
  rationale.maxLength = 2000;
  const create = button(document, "Compile workflow draft", "agentic-workflow-create", true);
  const createState = status(document, "Create compiles and persists a draft. It does not start execution.");
  const createActions = element(document, "div", "nur-adjunct-actions");
  createActions.append(create);
  builder.append(
    agenticField(document, "Title", title),
    agenticField(document, "Objective", objective),
    agenticField(document, "Success criterion", success),
    agenticField(document, "Bound tool", toolSelect),
    agenticField(document, "Role", role),
    agenticField(document, "Tool arguments as JSON", argumentsInput),
    agenticField(document, "Rationale", rationale),
    createActions,
    createState,
  );
  create.addEventListener("click", async () => {
    if (!title.value.trim() || !objective.value.trim() || !success.value.trim() || !rationale.value.trim()) {
      createState.textContent = "Title, objective, success criterion and rationale are required.";
      createState.className = "nur-adjunct-status is-warn";
      return;
    }
    if (!policy.permitted_tools.includes(toolSelect.value)) {
      createState.textContent = "Permit the selected tool in the owner policy before compiling this workflow.";
      createState.className = "nur-adjunct-status is-warn";
      return;
    }
    let inputRefs: Record<string, unknown>;
    try {
      const parsed = JSON.parse(argumentsInput.value) as unknown;
      if (!parsed || Array.isArray(parsed) || typeof parsed !== "object") throw new Error("Tool arguments must be a JSON object.");
      inputRefs = parsed as Record<string, unknown>;
    } catch (error) {
      createState.textContent = error instanceof Error ? error.message : "Tool arguments must be valid JSON.";
      createState.className = "nur-adjunct-status is-warn";
      return;
    }
    create.disabled = true;
    try {
      const created = await api.createAgenticWorkflow({
        request_id: crypto.randomUUID(),
        title: title.value.trim(),
        objective: objective.value.trim(),
        context_manifest: { source: "owner-authored V197 agency chamber", orbit_id: session.orbit.id },
        success_criteria: [success.value.trim()],
        proposed_steps: [{
          key: "step-1",
          role: role.value,
          tool_key: toolSelect.value,
          depends_on: [],
          input_refs: inputRefs,
          rationale: rationale.value.trim(),
        }],
      });
      navigate(`/agents/${created.id}`);
    } catch (error) {
      createState.textContent = error instanceof Error ? error.message : "Workflow did not compile.";
      createState.className = "nur-adjunct-status is-warn";
      create.disabled = false;
    }
  });

  const approvalPanel = panel(document, "Waiting for you", `Approvals · ${approvals.length}`);
  const approvalList = element(document, "div", "nur-adjunct-list");
  for (const approval of approvals) {
    const card = buildApprovalCard(approval);
    const row = element(document, "div", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, approval.workflow_title ?? `Workflow ${approval.workflow_id.slice(0, 8)}`), element(document, "span", "nur-adjunct-chip", approval.risk_class));
    const exactArguments = element(document, "pre", "nur-adjunct-json", JSON.stringify(approval.redacted_arguments, null, 2));
    const decisionState = status(document, card.expiryNote ?? "This decision is bound to the displayed plan, call version and argument digest.");
    const decisions = element(document, "div", "nur-adjunct-actions");
    if (card.actionable) {
      const approve = button(document, "Approve exact call", `agentic-approval-approve-${approval.id}`, true);
      const reject = button(document, "Reject", `agentic-approval-reject-${approval.id}`);
      const edit = button(document, "Edit arguments", `agentic-approval-edit-${approval.id}`);
      const submitEdit = button(document, "Submit edited call", `agentic-approval-submit-edit-${approval.id}`, true);
      const editInput = element(
        document,
        "textarea",
        "nur-adjunct-json-input",
        JSON.stringify(approval.redacted_arguments, null, 2),
      ) as HTMLTextAreaElement;
      editInput.setAttribute("aria-label", "Edit the owner-visible approval arguments as JSON");
      editInput.hidden = true;
      submitEdit.hidden = true;
      const editorContract = resolveApprovalEditor(approval);
      const editorBoundary = status(
        document,
        editorContract.mode === "RAW_JSON"
          ? `${editorContract.reason} Review and submit the complete JSON object.`
          : "The API supplied an object input schema for this approval.",
      );
      editorBoundary.dataset.approvalEditorMode = editorContract.mode.toLowerCase().replace("_", "-");
      editorBoundary.hidden = true;
      const decide = async (choice: "APPROVE" | "REJECT" | "EDIT", editedArguments?: Record<string, unknown>) => {
        approve.disabled = true;
        reject.disabled = true;
        edit.disabled = true;
        submitEdit.disabled = true;
        try {
          await api.decideAgenticApproval(approval, choice, undefined, editedArguments);
          await renderAgents(document, api, session);
        } catch (error) {
          decisionState.textContent = error instanceof Error ? error.message : "Approval decision did not persist.";
          decisionState.className = "nur-adjunct-status is-warn";
          approve.disabled = false;
          reject.disabled = false;
          edit.disabled = false;
          submitEdit.disabled = false;
        }
      };
      const toggleEdit = () => {
        editInput.hidden = !editInput.hidden;
        submitEdit.hidden = editInput.hidden;
        editorBoundary.hidden = editInput.hidden;
        if (!editInput.hidden) editInput.focus();
      };
      submitEdit.addEventListener("click", () => {
        try {
          const parsed: unknown = JSON.parse(editInput.value);
          if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) {
            throw new Error("Edited arguments must be a JSON object.");
          }
          void decide("EDIT", parsed as Record<string, unknown>);
        } catch (error) {
          decisionState.textContent = error instanceof Error ? error.message : "Edited arguments must be valid JSON.";
          decisionState.className = "nur-adjunct-status is-warn";
        }
      });
      approve.addEventListener("click", () => void decide("APPROVE"));
      reject.addEventListener("click", () => void decide("REJECT"));
      edit.addEventListener("click", toggleEdit);
      decisions.append(approve, reject, edit, editorBoundary, editInput, submitEdit);
    }
    row.append(
      head,
      element(document, "p", undefined, card.why),
      fact(document, "Tool", card.toolLabel),
      fact(document, "Scope", card.scope),
      fact(document, "Risk", card.risk),
      fact(document, "Expected", card.expected),
      exactArguments,
      decisions,
      decisionState,
    );
    approvalList.append(row);
  }
  if (!approvals.length) approvalList.append(empty(document, "No approval is waiting", "NUR has no pending call that requires your consent."));
  approvalPanel.append(approvalList);

  const workflowPanel = panel(document, "Run ledger", `Owner workflows · ${workflows.length}`);
  workflowPanel.classList.add("is-wide");
  workflowPanel.append(agenticWorkflowRows(document, workflows));
  grid.append(policyPanel, builder, approvalPanel, workflowPanel);
}

async function renderAgenticDetail(
  document: Document,
  api: V197ApiClient,
  session: V197Session,
  workflowId: string,
): Promise<void> {
  const [workflow, events] = await Promise.all([
    api.agenticWorkflow(workflowId),
    api.agenticWorkflowEvents(workflowId),
  ]);
  const shell = mount(document, workflow.title, workflow.objective, "/agents");
  const grid = element(document, "div", "nur-adjunct-grid");
  shell.append(grid);
  const statePanel = panel(document, "Workflow state", workflow.state);
  statePanel.classList.add("is-wide");
  const stateFacts = element(document, "div", "nur-adjunct-facts");
  stateFacts.append(
    fact(document, "Plan version", String(workflow.plan_version)),
    fact(document, "Cost recorded", `${workflow.cost_cents} cents`),
    fact(document, "Success", workflow.success_criteria.join(" · ")),
  );
  const lifecycleActions = element(document, "div", "nur-adjunct-actions");
  const lifecycleState = status(document, "Every lifecycle write is owner-scoped, version-fenced and append-only in the run ledger.");
  if (workflow.state === "PLAN_READY") {
    const start = button(document, "Start this plan", "agentic-workflow-start", true);
    start.addEventListener("click", async () => {
      start.disabled = true;
      try {
        await api.startAgenticWorkflow(workflow.id, workflow.plan_version);
        await renderAgenticDetail(document, api, session, workflow.id);
      } catch (error) {
        lifecycleState.textContent = error instanceof Error ? error.message : "Workflow did not start.";
        lifecycleState.className = "nur-adjunct-status is-warn";
        start.disabled = false;
      }
    });
    lifecycleActions.append(start);
  }
  if (!AGENTIC_TERMINAL_STATES.has(workflow.state)) {
    const cancel = button(document, "Cancel workflow", "agentic-workflow-cancel");
    cancel.addEventListener("click", async () => {
      cancel.disabled = true;
      try {
        await api.cancelAgenticWorkflow(workflow.id);
        await renderAgenticDetail(document, api, session, workflow.id);
      } catch (error) {
        lifecycleState.textContent = error instanceof Error ? error.message : "Cancellation did not persist.";
        lifecycleState.className = "nur-adjunct-status is-warn";
        cancel.disabled = false;
      }
    });
    lifecycleActions.append(cancel);
  }
  statePanel.append(stateFacts, lifecycleActions, lifecycleState);

  const stepsPanel = panel(document, "Compiled plan", `Steps · ${workflow.steps.length}`);
  const stepList = element(document, "div", "nur-adjunct-list");
  for (const step of workflow.steps) {
    const row = element(document, "div", "nur-adjunct-row");
    const head = element(document, "div", "nur-adjunct-row-head");
    head.append(element(document, "strong", undefined, `${step.ordinal}. ${step.key}`), element(document, "span", "nur-adjunct-chip", step.state));
    row.append(head, element(document, "p", undefined, `${step.role} · ${step.tool_key ?? "No tool"} v${step.tool_version ?? "none"}`));
    row.append(element(document, "pre", "nur-adjunct-json", JSON.stringify(step.input_refs, null, 2)));
    if (step.retryable) {
      const actions = element(document, "div", "nur-adjunct-actions");
      const retry = button(document, "Retry workflow from this plan", `agentic-workflow-retry-${workflow.id}`);
      retry.addEventListener("click", async () => {
        retry.disabled = true;
        try {
          const successor = await api.retryAgenticWorkflow(workflow.id, requestKey("agentic-retry"), workflow.plan_version);
          navigate(`/agents/${successor.id}`);
        } catch (error) {
          lifecycleState.textContent = error instanceof Error ? error.message : "Workflow retry was refused.";
          lifecycleState.className = "nur-adjunct-status is-warn";
          retry.disabled = false;
        }
      });
      actions.append(retry);
      row.append(actions);
    }
    stepList.append(row);
  }
  stepsPanel.append(stepList);

  const eventPanel = panel(document, "Append-only evidence", `Run events · ${events.length}`);
  const eventList = element(document, "div", "nur-adjunct-list");
  for (const event of events) {
    const row = element(document, "div", "nur-adjunct-row");
    row.append(
      element(document, "strong", undefined, text(event.event_type)),
      element(document, "p", undefined, text(event.summary)),
      element(document, "p", undefined, `${text(event.actor)} · ${date(event.created_at)}`),
    );
    eventList.append(row);
  }
  if (!events.length) eventList.append(empty(document, "No event returned", "The API did not return an append-only event for this workflow."));
  eventPanel.append(eventList);
  grid.append(statePanel, stepsPanel, eventPanel);
}

function renderError(document: Document, error: unknown, backRoute = "/systems"): void {
  const shell = mount(document, "This chamber could not open.", "NUR kept the boundary closed instead of inventing data.", backRoute);
  const grid = element(document, "div", "nur-adjunct-grid");
  const errorPanel = panel(document, "Honest runtime state", "No fabricated fallback");
  errorPanel.classList.add("is-wide");
  errorPanel.append(status(document, error instanceof Error ? error.message : "The requested owner data is unavailable.", "warn"));
  grid.append(errorPanel);
  shell.append(grid);
}

export async function renderV197Adjunct(
  document: Document,
  route: string,
  api: V197ApiClient,
  snapshot: V197BridgeSnapshot | null,
  refreshSnapshot: RefreshSnapshot,
  session: V197Session,
): Promise<boolean> {
  const existing = document.getElementById(ROOT_ID);
  const isAdjunct = route === "/settings"
    || route === "/memory"
    || route === "/teach-nur"
    || route === "/billing"
    || route === "/capsules"
    || route === "/agents"
    || route.startsWith("/agents/")
    || route.startsWith("/capsule/")
    || route === "/universe/insights/candidates"
    || route.startsWith("/universe/insights/candidates/")
    || route === "/consultations"
    || route.startsWith("/consultations/")
    || route === "/universe/consultation"
    || route.startsWith("/universe/consultation/")
    || route === "/community"
    || route === "/universe/community"
    || route.startsWith("/community/")
    || route.startsWith("/universe/community/")
    || route === "/projects"
    || route.startsWith("/projects/")
    || route === "/glow"
    || route === "/notifications"
    || route === "/universe/omega"
    || route === "/universe/omega/review"
    || route.startsWith("/universe/omega/why-changed/");
  if (!isAdjunct) {
    existing?.remove();
    restoreAdjunctBackground(document);
    return false;
  }

  try {
    if (route === "/settings") {
      if (!snapshot) throw new Error("Settings require the full owner snapshot.");
      await renderSettings(document, api, snapshot, refreshSnapshot);
    }
    else if (route === "/memory") {
      if (!snapshot) throw new Error("Memory requires the full owner snapshot.");
      await renderMemory(document, api, snapshot);
    }
    else if (route === "/teach-nur") {
      if (!snapshot) throw new Error("Teach NUR requires the full owner snapshot.");
      await renderTeachNUR(document, api, snapshot);
    }
    else if (route === "/billing") await renderBilling(document, api);
    else if (route === "/capsules") {
      if (!snapshot) throw new Error("Capsules require the full owner snapshot.");
      await renderOwnerCapsules(document, api, snapshot);
    }
    else if (route === "/agents") await renderAgents(document, api, session);
    else if (route.startsWith("/agents/")) await renderAgenticDetail(document, api, session, decodeURIComponent(route.slice("/agents/".length)));
    else if (route.startsWith("/capsule/")) await renderCapsule(document, api, decodeURIComponent(route.slice("/capsule/".length)));
    else if (route === "/consultations" || route === "/universe/consultation") await renderConsultationIndex(document, api, session.orbit.id);
    else if (route.startsWith("/consultations/")) await renderConsultationDetail(document, api, decodeURIComponent(route.split("/")[2] ?? ""));
    else if (route.startsWith("/universe/consultation/")) await renderConsultationDetail(document, api, decodeURIComponent(route.split("/")[3] ?? ""));
    else if (route === "/universe/insights/candidates" || route.startsWith("/universe/insights/candidates/")) await renderCandidateInsights(document, api);
    else if (route.startsWith("/community/room/")) await renderCommunityRoom(document, api, decodeURIComponent(route.split("/")[3] ?? ""));
    else if (route.startsWith("/universe/community/room/")) await renderCommunityRoom(document, api, decodeURIComponent(route.split("/")[4] ?? ""));
    else if (route.startsWith("/community/post/")) await renderCommunityPost(document, api, decodeURIComponent(route.split("/")[3] ?? ""));
    else if (route.startsWith("/universe/community/post/")) await renderCommunityPost(document, api, decodeURIComponent(route.split("/")[4] ?? ""));
    else if (route === "/community" || route === "/universe/community" || route.startsWith("/community/")) await renderCommunityIndex(document, api);
    else if (route.startsWith("/universe/community/")) await renderCommunityIndex(document, api);
    else if (route === "/projects" || route === "/projects/new") await renderProjectsIndex(document, api);
    else if (route.startsWith("/projects/")) await renderProjectDetail(document, api, decodeURIComponent(route.split("/")[2] ?? ""), route);
    else if (route === "/glow") {
      if (!snapshot) throw new Error("Glow requires the full owner snapshot.");
      renderGlow(document, snapshot);
    }
    else if (route === "/notifications") await renderNotifications(document, api);
    else if (route === "/universe/omega/review") await renderOmegaReview(document, api);
    else if (route.startsWith("/universe/omega/why-changed/")) await renderOmegaWhyChanged(document, api, decodeURIComponent(route.slice("/universe/omega/why-changed/".length)));
    else await renderOmegaDashboard(document, api);
  } catch (error) {
    renderError(
      document,
      error,
      route.startsWith("/universe/omega")
        ? "/universe/omega"
        : route.startsWith("/universe/")
          ? "/universe"
          : "/systems",
    );
  }
  return true;
}
