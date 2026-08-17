import { V197ApiClient, type V197BridgeSnapshot, type V197Session } from "./v197ApiClient";
import { renderV197Adjunct } from "./v197Adjuncts";
import { ORBIT_ROUTE, renderV197Orbit } from "./v197Orbit";
import { MAP_ROUTE, renderV197Map } from "./v197Map";
import { TIMELINE_ROUTE, renderV197Timeline } from "./v197Timeline";
import { INSIGHTS_ROUTE, renderV197Insights } from "./v197Insights";
import { bindV197Actions, bindV197EntryAuth } from "./v197Bindings";
import {
  emitBridgeEvent,
  routeForPage,
  routeForWorldFocus,
  routeForWorldTab,
  V197_EVENTS,
  type V197NativeRoute,
} from "./v197Events";
import { hydrateTrackAV197, renderInsightInspection, renderWorldLens } from "./v197Hydration";
import {
  compactV197MiniStars,
  ensureV197EntryPolish,
  ensureV197PremiumPolish,
} from "./v197Polish";
import { cancelAllV197SearchCommits } from "./v197SearchInput";
import { selectRequired, V197_SELECTORS } from "./v197Selectors";

/** Routes a bridge-native surface owns end to end.
 *
 * Sourced from each surface's own exported constant so this list cannot drift
 * from what the surfaces actually claim.
 */
const SURFACE_ROOTS: readonly (readonly [string, string])[] = [
  [ORBIT_ROUTE, "nur-orbit-root"],
  [MAP_ROUTE, "nur-map-root"],
  [TIMELINE_ROUTE, "nur-timeline-root"],
  [INSIGHTS_ROUTE, "nur-insights-root"],
];

function isDedicatedUniverseRoute(route: string): boolean {
  return route === "/universe/insights/candidates"
    || route.startsWith("/universe/insights/candidates/");
}


type V197HostApi = {
  verifySources: () => Promise<{ pass: boolean }>;
  completeSignIn: (profile: Record<string, unknown>) => void;
  showEntry: () => void;
  getStage: () => "entry" | "universe";
};

type V197HostWindow = Window & { NURConsolidated?: V197HostApi };
type V197UniverseWindow = Window & { nurToast?: (message: string) => void };
type V197EntryWindow = Window & { nurShowFront?: () => void };

declare global {
  interface Window {
    __NUR_V197_BRIDGE__?: V197Bridge;
  }
}

function nativeRoute(pathname: string): V197NativeRoute {
  const value = pathname.replace(/\/+$/, "") || "/";
  if ([
    "/universe/consultation",
    "/universe/research",
    "/universe/community",
    "/universe/experts",
    "/universe/web-signals",
  ].some(route => value === route || value.startsWith(`${route}/`))) {
    return "/systems";
  }
  return value as V197NativeRoute;
}

function pause(milliseconds: number): Promise<void> {
  return new Promise(resolve => window.setTimeout(resolve, milliseconds));
}

async function waitForFrameDocument(frame: HTMLIFrameElement, requiredSelector: string, label: string): Promise<Document> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    const document = frame.contentDocument;
    if (document?.readyState === "complete" && document.querySelector(requiredSelector)) return document;
    await pause(25);
  }
  throw new Error(`${label} did not initialize.`);
}

async function waitForUniversePresentation(
  hostApi: V197HostApi,
  entryFrame: HTMLIFrameElement,
  universeFrame: HTMLIFrameElement,
): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (
      hostApi.getStage() === "universe"
      && universeFrame.classList.contains("is-visible")
      && universeFrame.getAttribute("aria-hidden") !== "true"
      && entryFrame.classList.contains("is-exiting")
      && entryFrame.getAttribute("aria-hidden") === "true"
      && entryFrame.hasAttribute("inert")
    ) return;
    await pause(25);
  }
  throw new Error("Canonical V197 Universe presentation did not settle.");
}

async function waitForEntryPresentation(
  hostApi: V197HostApi,
  entryFrame: HTMLIFrameElement,
  universeFrame: HTMLIFrameElement,
): Promise<void> {
  const deadline = Date.now() + 10_000;
  while (Date.now() < deadline) {
    if (
      hostApi.getStage() === "entry"
      && !entryFrame.classList.contains("is-exiting")
      && entryFrame.getAttribute("aria-hidden") !== "true"
      && !entryFrame.hasAttribute("inert")
      && !universeFrame.classList.contains("is-visible")
      && universeFrame.getAttribute("aria-hidden") === "true"
    ) return;
    await pause(25);
  }
  throw new Error("Canonical V197 Entry presentation did not settle.");
}

function suspendEntryStage(frame: HTMLIFrameElement): void {
  frame.style.display = "none";
  frame.dataset.nurStageSuspended = "true";
}

function resumeEntryStage(frame: HTMLIFrameElement): void {
  frame.style.removeProperty("display");
  delete frame.dataset.nurStageSuspended;
}

export class V197Bridge {
  private readonly api = new V197ApiClient();
  private applyingRoute = false;
  private universeDocument: Document | null = null;
  private session: V197Session | null = null;
  private snapshot: V197BridgeSnapshot | null = null;
  private fullSnapshotHydrated = false;
  private actionCleanup: (() => void) | null = null;
  private entryAuthDocument: Document | null = null;
  private entryAuthCleanup: (() => void) | null = null;
  private miniStarCompactionFrame: number | null = null;
  private authenticatedSessionActive = false;
  private stageGuard: MutationObserver | null = null;
  private entryPresentationTransition: Promise<void> | null = null;

  constructor(
    private readonly hostWindow: V197HostWindow,
    private readonly hostDocument: Document,
  ) {}

  async start(): Promise<void> {
    const hostApi = this.hostWindow.NURConsolidated;
    if (!hostApi) throw new Error("Canonical V197 host did not initialize.");

    const integrity = await hostApi.verifySources();
    if (!integrity.pass) throw new Error("Canonical V197 source verification failed.");
    const entryFrame = selectRequired<HTMLIFrameElement>(this.hostDocument, V197_SELECTORS.entryStage);
    resumeEntryStage(entryFrame);
    const entryDocument = await waitForFrameDocument(entryFrame, "#nur-front-v61", "Canonical V197 entry");
    ensureV197EntryPolish(entryDocument);
    this.hostDocument.documentElement.dataset.nurEntryPolished = "true";
    this.ensureEntryAuthBinding(entryDocument, hostApi);
    this.installStageGuard(hostApi);

    window.addEventListener("popstate", () => void this.applyCurrentRoute());
    emitBridgeEvent(V197_EVENTS.ready, { integrity: "pass", mode: "track-a-persisted" });

    let session: V197Session | null;
    try {
      session = await this.api.session();
    } catch (error) {
      const status = entryDocument.querySelector<HTMLElement>("#f4-status");
      const diagnostic = `NUR could not verify the local session. ${error instanceof Error ? error.message : "Check API readiness."}`;
      const showDiagnostic = () => {
        if (!status) return;
        status.textContent = diagnostic;
        status.classList.add("nur-v197-auth-error");
        status.setAttribute("role", "alert");
      };
      showDiagnostic();
      // The canonical Entry runtime clears its status slot when switching from
      // intro to signup/signin. Reapply the same factual startup error after
      // those native transitions so the failure remains visible and usable.
      entryDocument.addEventListener("click", event => {
        const target = event.target as Element | null;
        if (!target?.closest("#f4-begin, #f4-signin, [data-switch]")) return;
        window.setTimeout(showDiagnostic, 0);
      }, true);
      return;
    }
    if (session) {
      await this.activateSession(hostApi, session);
      return;
    }

    // `/auth` is an explicit return to the existing V197 sign-in surface (for
    // example after account deletion). Do not leave that route behind the
    // seven-second cinematic intro; the root route still owns that intro.
    if (!["/", "/onboarding"].includes(window.location.pathname)) {
      (entryDocument.defaultView as V197EntryWindow | null)?.nurShowFront?.();
    }
  }

  private ensureEntryAuthBinding(entryDocument: Document, hostApi: V197HostApi): void {
    if (this.entryAuthDocument === entryDocument && this.entryAuthCleanup) return;
    this.entryAuthCleanup?.();
    this.entryAuthDocument = entryDocument;
    this.entryAuthCleanup = bindV197EntryAuth(entryDocument, this.api, async authenticated => {
      await this.activateSession(hostApi, authenticated);
    });
  }

  async applyCurrentRoute(): Promise<void> {
    if (!this.universeDocument || !this.session) return;
    const route = nativeRoute(window.location.pathname);
    // Route dispatch early-returns on the matching dedicated surface. Cancel
    // every prior search commit here so a detached surface cannot repaint and
    // remount itself after the owner has already entered another world.
    cancelAllV197SearchCommits(this.universeDocument);
    const canonicalRoute: V197NativeRoute = route.startsWith("/talk/")
      ? "/talk"
      : route.startsWith("/journal/")
        ? "/journal"
        : route.startsWith("/plan/")
          ? "/plan"
          : route.startsWith("/systems/")
            ? "/systems"
            : route.startsWith("/universe/insights/candidates/")
                  ? "/universe/insights/candidates"
                  : route.startsWith("/universe/insights/")
                    ? "/universe/insights"
            : route === "/universe/life"
              ? "/universe"
              : route;
    const pageByRoute: Partial<Record<V197NativeRoute, string>> = {
      "/today": "today",
      "/talk": "talk",
      "/journal": "journal",
      "/plan": "plan",
      "/systems": "systems",
      "/universe": "systems",
    };
    const worldByRoute: Partial<Record<V197NativeRoute, string>> = {
      "/systems": "universe",
      "/universe": "universe",
      "/universe/map": "map",
      "/universe/orbits": "orbits",
      "/universe/timeline": "timeline",
      "/universe/insights": "insights",
      "/universe/insights/candidates": "insights",
    };
    const routeSurface = worldByRoute[canonicalRoute] ?? pageByRoute[canonicalRoute] ?? "today";
    this.universeDocument.body.dataset.nurWorldSurface = routeSurface;

    this.applyingRoute = true;
    try {
      if (!isDedicatedUniverseRoute(route)) {
        await this.ensureFullSnapshot();
      }
      const adjunctRendered = await renderV197Adjunct(
        this.universeDocument,
        route,
        this.api,
        this.snapshot,
        async () => this.refreshSnapshot(),
        this.session,
      );
      if (adjunctRendered) return;
      // Clear any surface root that does not own this route, *before* the chain
      // below. Each surface removes its own root only when it is called with a
      // non-matching route, and the chain early-returns as soon as one matches —
      // so going from Map to Orbits left `#nur-map-root` behind, with two
      // surfaces mounted at once. Only the roots are removed here, never the
      // host, which the matching surface is about to claim.
      for (const [surfaceRoute, rootId] of SURFACE_ROOTS) {
        if (route !== surfaceRoute) this.universeDocument.getElementById(rootId)?.remove();
      }
      // Orbit is a bridge-native surface like the other adjuncts: plain DOM and
      // SVG in the canonical document, never a React tree owning a product page.
      const orbitRendered = await renderV197Orbit(this.universeDocument, route, this.api);
      if (orbitRendered) {
        this.markWorldFocus("orbits");
        return;
      }
      // Map, likewise: it composes canonical Systems, goals, plans, decisions and
      // outcomes into a causal surface, and owns no life entity of its own.
      const mapRendered = await renderV197Map(this.universeDocument, route, this.api);
      if (mapRendered) {
        this.markWorldFocus("map");
        return;
      }
      // Timeline, likewise: it composes canonical timeline_events and
      // scheduled_actions into a temporal surface and owns no life entity of
      // its own.
      const timelineRendered = await renderV197Timeline(this.universeDocument, route, this.api);
      if (timelineRendered) {
        this.markWorldFocus("timeline");
        return;
      }
      const insightsRendered = renderV197Insights(this.universeDocument, route, this.snapshot);
      if (insightsRendered) {
        this.markWorldFocus("insights", false);
        return;
      }
      const page = pageByRoute[canonicalRoute];
      if (page) this.click(V197_SELECTORS.pageNav(page));
      const world = worldByRoute[canonicalRoute];
      if (world && world !== "universe") this.click(V197_SELECTORS.worldFocus(world));
      if (world && this.snapshot) {
        // Canonical V197 handles the native click first. Its handler can
        // repaint the selected System, so yield one task before applying the
        // owner-ledger lens as the final route state.
        if (world !== "universe") await pause(0);
        renderWorldLens(this.universeDocument, this.snapshot, world);
        if (world === "insights") {
          const routeInsightId = route.startsWith("/universe/insights/")
            ? decodeURIComponent(route.slice("/universe/insights/".length))
            : null;
          await this.renderInsightRoute(routeInsightId);
        }
        this.compactRenderedMiniStars(this.universeDocument);
      }
      if (route.startsWith("/systems/")) {
        const slug = decodeURIComponent(route.slice("/systems/".length));
        const system = this.universeDocument.querySelector<HTMLElement>(
          `[data-system="${CSS.escape(slug)}"], [data-system-slug="${CSS.escape(slug)}"]`,
        );
        system?.click();
      }
    } finally {
      this.applyingRoute = false;
    }
  }

  private async activateSession(hostApi: V197HostApi, session: V197Session): Promise<void> {
    this.hostDocument.documentElement.dataset.nurUniversePolished = "false";
    this.session = session;
    this.snapshot = null;
    this.fullSnapshotHydrated = false;
    const initialRoute = nativeRoute(window.location.pathname);
    // Canonical worlds need the complete owner ledger before the protected
    // frame is revealed. Dedicated Universe chambers fetch only their own
    // records and defer this snapshot until the owner returns to Live Universe.
    if (!isDedicatedUniverseRoute(initialRoute)) {
      await this.loadFullSnapshot(session);
    }
    this.authenticatedSessionActive = true;
    let universeDocument: Document;
    try {
      universeDocument = await this.enterAuthenticatedUniverse(hostApi, this.hostDocument, session);
    } catch (error) {
      this.authenticatedSessionActive = false;
      await this.showEntry(hostApi);
      throw error;
    }
    this.universeDocument = universeDocument;
    ensureV197PremiumPolish(universeDocument);
    if (["/", "/auth", "/onboarding"].includes(window.location.pathname)) {
      window.history.replaceState({}, "", "/today");
    }
    this.bindNativeNavigation(universeDocument);
    if (this.snapshot) await this.ensureFullSnapshot();
    // Hydration paints the default live-System summary. Apply the requested
    // route afterwards so direct /universe/* loads retain their distinct lens
    // instead of being overwritten by the default System view.
    await this.applyCurrentRoute();
    this.compactRenderedMiniStars(universeDocument);
    this.hostDocument.documentElement.dataset.nurUniversePolished = "true";
    this.retireEntryStage();
  }

  private retireEntryStage(): void {
    this.entryAuthCleanup?.();
    this.entryAuthCleanup = null;
    this.entryAuthDocument = null;
    const entryFrame = this.hostDocument.querySelector<HTMLIFrameElement>(V197_SELECTORS.entryStage);
    if (!entryFrame) return;
    entryFrame.removeAttribute("srcdoc");
    entryFrame.remove();
    this.hostDocument.documentElement.dataset.nurEntryRetired = "true";
  }

  private async loadFullSnapshot(session: V197Session): Promise<V197BridgeSnapshot> {
    if (this.snapshot) return this.snapshot;
    let snapshot = await this.api.snapshot(session);
    if (!snapshot.preferences?.timezone) {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (timezone) {
        await this.api.patchPreferences({ timezone });
        snapshot = await this.api.snapshot(session);
      }
    }
    this.snapshot = snapshot;
    return snapshot;
  }

  private async ensureFullSnapshot(): Promise<V197BridgeSnapshot> {
    const hostApi = this.hostWindow.NURConsolidated;
    if (!hostApi) throw new Error("Canonical V197 host did not initialize.");
    if (!this.session) throw new Error("Your local Orbit session ended. Sign in again.");
    if (!this.universeDocument) throw new Error("Canonical V197 Universe is not ready.");
    const snapshot = await this.loadFullSnapshot(this.session);
    if (this.fullSnapshotHydrated) return snapshot;
    hydrateTrackAV197(this.universeDocument, snapshot);
    this.compactRenderedMiniStars(this.universeDocument);
    this.actionCleanup?.();
    this.actionCleanup = bindV197Actions(
      this.universeDocument,
      this.api,
      snapshot,
      async () => {
        const currentSession = await this.api.session();
        if (!currentSession) throw new Error("Your local Orbit session ended. Sign in again.");
        const next = await this.api.snapshot(currentSession);
        this.snapshot = next;
        return next;
      },
      async () => {
        window.location.replace("/");
      },
      undefined,
      async () => this.applyCurrentRoute(),
    );
    this.fullSnapshotHydrated = true;
    emitBridgeEvent(V197_EVENTS.sessionHydrate, this.snapshotEventDetail(snapshot));
    return snapshot;
  }

  private async enterAuthenticatedUniverse(hostApi: V197HostApi, hostDocument: Document, session: V197Session): Promise<Document> {
    const universeFrame = selectRequired<HTMLIFrameElement>(hostDocument, V197_SELECTORS.universeStage);
    hostApi.completeSignIn({
      email: session.email,
      chosen_name: session.profile.chosen_name ?? "",
      locale: session.profile.locale ?? "en",
      source: "track-a-persisted-bridge",
    });
    const universeDocument = await waitForFrameDocument(universeFrame, "#page-systems", "Canonical V197 universe frame");
    const entryFrame = selectRequired<HTMLIFrameElement>(hostDocument, V197_SELECTORS.entryStage);
    await waitForUniversePresentation(hostApi, entryFrame, universeFrame);
    suspendEntryStage(entryFrame);
    return universeDocument;
  }

  private bindNativeNavigation(universeDocument: Document): void {
    const universeWindow = universeDocument.defaultView as V197UniverseWindow | null;
    if (!universeWindow || universeDocument.documentElement.dataset.nurTrackANavigation === "bound") return;
    universeDocument.documentElement.dataset.nurTrackANavigation = "bound";

    let clickedWorldRoute: V197NativeRoute | null = null;
    universeDocument.addEventListener("click", event => {
      const target = event.target as Element | null;
      const control = target?.closest<HTMLElement>("[data-world-focus], [data-world-tab]");
      clickedWorldRoute = control?.dataset.worldTab
        ? routeForWorldTab(control.dataset.worldTab)
        : routeForWorldFocus(control?.dataset.worldFocus ?? "");
      window.setTimeout(() => {
        clickedWorldRoute = null;
      }, 0);
    }, true);

    universeDocument.addEventListener("click", event => {
      const target = event.target as Element | null;
      if (this.applyingRoute || !target || typeof target.closest !== "function") return;
      const control = target.closest<HTMLElement>("[data-page], [data-world-focus], [data-world-tab], [data-owner-route]");
      if (!control) return;
      const world = control.dataset.worldFocus ?? control.dataset.worldTab;
      const route = control.dataset.ownerRoute
        ? nativeRoute(control.dataset.ownerRoute)
        : routeForPage(control.dataset.page ?? "")
          ?? (control.dataset.worldTab
            ? routeForWorldTab(control.dataset.worldTab)
            : routeForWorldFocus(world ?? ""));
      if (!route) return;
      window.setTimeout(() => {
        this.pushRoute(route);
      }, 0);
    });

    // Canonical V197 emits these non-bubbling CustomEvents on `document`.
    // Listening on `window` only caught direct button clicks through the
    // fallback listener above; programmatic openPage() transitions were lost
    // and the next hydration reapplied the stale URL route.
    universeDocument.addEventListener("nur:page-change", event => {
      if (this.applyingRoute) return;
      const route = routeForPage((event as CustomEvent<{ page?: string }>).detail?.page ?? "");
      if (route) this.pushRoute(route);
    });
    universeWindow.addEventListener("nur:owner-route", event => {
      const route = (event as CustomEvent<{ route?: string }>).detail?.route;
      if (route) this.pushRoute(nativeRoute(route));
    });
    universeDocument.addEventListener("nur:world-focus", event => {
      if (this.applyingRoute) return;
      const focus = (event as CustomEvent<{ focus?: string }>).detail?.focus ?? "";
      // Native V197 emits the same focus name for a top-level world tab and a
      // lower workspace command. Route the event to the canonical world lens;
      // the real clicked control is resolved separately above and can then
      // choose a dedicated workspace such as Candidate Insights.
      const route = clickedWorldRoute ?? routeForWorldTab(focus) ?? routeForWorldFocus(focus);
      if (route) this.pushRoute(route);
    });
  }

  private installStageGuard(hostApi: V197HostApi): void {
    this.stageGuard?.disconnect();
    const enforce = () => {
      if (this.authenticatedSessionActive || hostApi.getStage() !== "universe") return;
      void this.showEntry(hostApi).catch(error => {
        console.error("NUR could not restore the canonical Entry presentation.", error);
      });
    };
    this.stageGuard = new MutationObserver(enforce);
    this.stageGuard.observe(this.hostDocument.documentElement, {
      attributes: true,
      attributeFilter: ["aria-hidden", "class", "inert"],
      childList: true,
      subtree: true,
    });
    enforce();
  }

  private async showEntry(hostApi: V197HostApi): Promise<void> {
    if (this.entryPresentationTransition) return this.entryPresentationTransition;
    const entryFrame = selectRequired<HTMLIFrameElement>(this.hostDocument, V197_SELECTORS.entryStage);
    const universeFrame = selectRequired<HTMLIFrameElement>(this.hostDocument, V197_SELECTORS.universeStage);
    const transition = (async () => {
      resumeEntryStage(entryFrame);
      hostApi.showEntry();
      await waitForEntryPresentation(hostApi, entryFrame, universeFrame);
    })();
    this.entryPresentationTransition = transition;
    try {
      await transition;
    } finally {
      if (this.entryPresentationTransition === transition) this.entryPresentationTransition = null;
    }
  }

  private async renderInsightRoute(requestedInsightId: string | null): Promise<void> {
    if (!this.universeDocument || !this.snapshot) return;
    const summary = this.snapshot.insights;
    const fallback = summary?.dedicated_insights?.[0]
      ?? summary?.claims.find(row => row.record_kind === "DEDICATED_INSIGHT");
    const fallbackId = typeof fallback?.id === "string" ? fallback.id : null;
    const insightId = requestedInsightId || fallbackId;
    if (!insightId) {
      renderInsightInspection(this.universeDocument, null, null, null);
      return;
    }
    renderInsightInspection(this.universeDocument, null, null, null, "Loading canonical evidence and change history…");
    try {
      const [detail, evidence, history] = await Promise.all([
        this.api.insightDetail(insightId),
        this.api.insightEvidence(insightId),
        this.api.insightWhyChanged(insightId),
      ]);
      renderInsightInspection(this.universeDocument, detail, evidence, history);
    } catch (error) {
      const detail = error instanceof Error ? error.message : "The Insight could not be inspected.";
      renderInsightInspection(this.universeDocument, null, null, null, detail);
    }
  }

  private compactRenderedMiniStars(universeDocument: Document): void {
    compactV197MiniStars(universeDocument);
    const universeWindow = universeDocument.defaultView;
    if (!universeWindow || this.miniStarCompactionFrame !== null) return;
    this.miniStarCompactionFrame = universeWindow.requestAnimationFrame(() => {
      this.miniStarCompactionFrame = null;
      compactV197MiniStars(universeDocument);
    });
  }

  private click(selector: string): void {
    const button = this.universeDocument?.querySelector<HTMLElement>(selector);
    button?.click();
  }

  private markWorldFocus(focus: string, renderCanonicalLens = true): void {
    if (!this.universeDocument || !this.snapshot) return;
    this.universeDocument.body.dataset.nurWorldFocus = focus;
    this.universeDocument.querySelectorAll<HTMLElement>("[data-world-focus], [data-world-tab]").forEach(control => {
      const active = (control.dataset.worldFocus ?? control.dataset.worldTab) === focus;
      control.classList.toggle("active", active);
      if (control.matches(".universe-nav-tabs button, [role='tab']")) {
        control.setAttribute("aria-selected", String(active));
      }
    });
    if (renderCanonicalLens) renderWorldLens(this.universeDocument, this.snapshot, focus);
    this.compactRenderedMiniStars(this.universeDocument);
  }

  private async refreshSnapshot(): Promise<V197BridgeSnapshot> {
    const currentSession = await this.api.session();
    if (!currentSession) throw new Error("Your local Orbit session ended. Sign in again.");
    const next = await this.api.snapshot(currentSession);
    this.snapshot = next;
    return next;
  }

  private pushRoute(route: V197NativeRoute): void {
    if (window.location.pathname === route) return;
    window.history.pushState({}, "", route);
    // `pushState` does NOT fire `popstate` — that event is only for back/forward.
    // The bridge listened for `popstate` alone, so every in-app navigation changed
    // the URL and then rendered nothing: clicking Map, Orbits or Timeline in the
    // canonical top nav landed on the right address with the canonical Systems
    // page still on screen. Direct loads worked only because boot calls
    // `applyCurrentRoute` itself. Applying the route here is what makes the nav
    // actually navigate.
    void this.applyCurrentRoute();
  }

  private snapshotEventDetail(snapshot: V197BridgeSnapshot): Record<string, unknown> {
    return {
      authenticated: true,
      hasMap: snapshot.map !== null,
      hasOrbits: snapshot.orbits !== null,
      hasTimeline: snapshot.timeline !== null,
      hasInsights: snapshot.insights !== null,
      glowBalance: snapshot.glow.balance,
      locale: snapshot.preferences?.locale ?? snapshot.session.profile.locale ?? "en",
      mode: "track-a-persisted",
    };
  }
}

export async function bootstrapV197Bridge(): Promise<V197Bridge> {
  if (window.__NUR_V197_BRIDGE__) return window.__NUR_V197_BRIDGE__;
  selectRequired<HTMLIFrameElement>(document, V197_SELECTORS.entryStage);
  selectRequired<HTMLIFrameElement>(document, V197_SELECTORS.universeStage);
  const bridge = new V197Bridge(window as V197HostWindow, document);
  window.__NUR_V197_BRIDGE__ = bridge;
  await bridge.start();
  return bridge;
}
