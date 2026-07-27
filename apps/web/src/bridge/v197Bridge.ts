import { V197ApiClient, type V197BridgeSnapshot, type V197Session } from "./v197ApiClient";
import { renderV197Adjunct } from "./v197Adjuncts";
import { bindV197Actions, bindV197EntryAuth } from "./v197Bindings";
import { emitBridgeEvent, routeForPage, routeForWorldFocus, V197_EVENTS, type V197NativeRoute } from "./v197Events";
import { hydrateTrackAV197, renderWorldLens } from "./v197Hydration";
import {
  compactV197MiniStars,
  ensureV197EntryPolish,
  ensureV197PremiumPolish,
} from "./v197Polish";
import { selectRequired, V197_SELECTORS } from "./v197Selectors";

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

export class V197Bridge {
  private readonly api = new V197ApiClient();
  private applyingRoute = false;
  private universeDocument: Document | null = null;
  private snapshot: V197BridgeSnapshot | null = null;
  private actionCleanup: (() => void) | null = null;
  private entryAuthDocument: Document | null = null;
  private entryAuthCleanup: (() => void) | null = null;
  private miniStarCompactionFrame: number | null = null;

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
    const entryDocument = await waitForFrameDocument(entryFrame, "#nur-front-v61", "Canonical V197 entry");
    ensureV197EntryPolish(entryDocument);
    this.ensureEntryAuthBinding(entryDocument, hostApi);

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
    if (!this.universeDocument || !this.snapshot) return;
    const route = nativeRoute(window.location.pathname);
    const canonicalRoute: V197NativeRoute = route.startsWith("/talk/")
      ? "/talk"
      : route.startsWith("/journal/")
        ? "/journal"
        : route.startsWith("/plan/")
          ? "/plan"
          : route.startsWith("/systems/")
            ? "/systems"
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
      "/universe/research": "research",
      "/universe/community": "community",
      "/universe/web-signals": "web",
    };

    this.applyingRoute = true;
    try {
      const adjunctRendered = await renderV197Adjunct(
        this.universeDocument,
        route,
        this.api,
        this.snapshot,
        async () => this.refreshSnapshot(),
      );
      if (adjunctRendered) return;
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
    // Verify owner data before the canonical host reveals the protected
    // Universe. A failed snapshot therefore returns to the visible auth state
    // instead of leaving a staged or indefinitely loading interior.
    this.snapshot = await this.api.snapshot(session);
    if (!this.snapshot.preferences?.timezone) {
      const timezone = Intl.DateTimeFormat().resolvedOptions().timeZone;
      if (timezone) {
        await this.api.patchPreferences({ timezone });
        this.snapshot = await this.api.snapshot(session);
      }
    }
    const universeDocument = await this.enterAuthenticatedUniverse(hostApi, this.hostDocument, session);
    this.universeDocument = universeDocument;
    ensureV197PremiumPolish(universeDocument);
    if (["/", "/auth", "/onboarding"].includes(window.location.pathname)) {
      window.history.replaceState({}, "", "/today");
    }
    this.bindNativeNavigation(universeDocument);
    hydrateTrackAV197(universeDocument, this.snapshot);
    // Hydration paints the default live-System summary. Apply the requested
    // route afterwards so direct /universe/* loads retain their distinct lens
    // instead of being overwritten by the default System view.
    await this.applyCurrentRoute();
    this.compactRenderedMiniStars(universeDocument);

    this.actionCleanup?.();
    this.actionCleanup = bindV197Actions(
      universeDocument,
      this.api,
      this.snapshot,
      async () => {
        const currentSession = await this.api.session();
        if (!currentSession) throw new Error("Your local Orbit session ended. Sign in again.");
        const next = await this.api.snapshot(currentSession);
        this.snapshot = next;
        return next;
      },
      async () => {
        this.actionCleanup?.();
        this.actionCleanup = null;
        this.snapshot = null;
        this.universeDocument = null;
        window.history.replaceState({}, "", "/");
        hostApi.showEntry();
        const entryFrame = selectRequired<HTMLIFrameElement>(this.hostDocument, V197_SELECTORS.entryStage);
        const universeFrame = selectRequired<HTMLIFrameElement>(this.hostDocument, V197_SELECTORS.universeStage);
        await waitForEntryPresentation(hostApi, entryFrame, universeFrame);
        const entryDocument = await waitForFrameDocument(entryFrame, "#nur-front-v61", "Canonical V197 entry");
        // A refreshed authenticated page enters the Universe before the native
        // Entry intro has ever revealed its front surface. Restore that exact
        // V197 runtime state on logout instead of leaving the intro over it.
        (entryDocument.defaultView as V197EntryWindow | null)?.nurShowFront?.();
        entryDocument.querySelector<HTMLButtonElement>("#f4-close")?.click();
        this.ensureEntryAuthBinding(entryDocument, hostApi);
      },
    );
    emitBridgeEvent(V197_EVENTS.sessionHydrate, this.snapshotEventDetail(this.snapshot));
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
    return universeDocument;
  }

  private bindNativeNavigation(universeDocument: Document): void {
    const universeWindow = universeDocument.defaultView as V197UniverseWindow | null;
    if (!universeWindow || universeDocument.documentElement.dataset.nurTrackANavigation === "bound") return;
    universeDocument.documentElement.dataset.nurTrackANavigation = "bound";

    universeDocument.addEventListener("click", event => {
      const target = event.target as Element | null;
      if (this.applyingRoute || !target || typeof target.closest !== "function") return;
      const control = target.closest<HTMLElement>("[data-page], [data-world-focus], [data-world-tab]");
      if (!control) return;
      const world = control.dataset.worldFocus ?? control.dataset.worldTab;
      const route = routeForPage(control.dataset.page ?? "") ?? routeForWorldFocus(world ?? "");
      if (!route) return;
      window.setTimeout(() => {
        this.pushRoute(route);
        if (world && this.snapshot) {
          renderWorldLens(universeDocument, this.snapshot, world);
          this.compactRenderedMiniStars(universeDocument);
        }
      }, 0);
    });

    universeWindow.addEventListener("nur:page-change", event => {
      if (this.applyingRoute) return;
      const route = routeForPage((event as CustomEvent<{ page?: string }>).detail?.page ?? "");
      if (route) this.pushRoute(route);
    });
    universeWindow.addEventListener("nur:world-focus", event => {
      if (this.applyingRoute) return;
      const focus = (event as CustomEvent<{ focus?: string }>).detail?.focus ?? "";
      const route = routeForWorldFocus(focus);
      if (route) this.pushRoute(route);
      if (this.snapshot) {
        renderWorldLens(universeDocument, this.snapshot, focus);
        this.compactRenderedMiniStars(universeDocument);
      }
    });
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
