export const V197_STAR_SEAL_CLASS = "nur-star-seal";
export const V197_CONTROL_STAR_SEAL_CLASS = "nur-star-seal--control";
export const V197_STATE_STAR_SEAL_CLASS = "nur-star-seal--state";
export const V197_STARTUP_STAR_CLASS = "nur-star-seal--startup";
export const V197_SIGIL_STAR_CLASS = "nur-v197-sigil-star";
export const V197_STARTUP_STAR_SOURCE_ID = "iSpark";

export type V197StarSealSize = 12 | 16 | 20 | 24 | 32;

const SIZES: readonly V197StarSealSize[] = [12, 16, 20, 24, 32];
const controlSealObservers = new WeakMap<Document, MutationObserver>();
const AUTHENTIC_HOST_ATTRIBUTE = "data-nur-authentic-star-host";

const PRIMARY_CONTROL_SELECTOR = [
  ".f4-primary",
  ".f4-submit",
  ".thought-send-button",
  ".universe-send",
  ".nur-adjunct-button.is-primary",
].join(",");

const SELECTED_STATE_HOST_SELECTOR = [
  ".clean-nav-button.active > .clean-nav-glyph",
  ".scope-option[aria-selected='true']",
  ".scope-option[aria-checked='true']",
  ".audit-scope.selected",
  ".clean-scope.selected",
  ".nur-community-nav .nur-adjunct-button[aria-current='page']",
].join(",");

const SYSTEM_NODE_GLYPHS: Readonly<Record<string, string>> = {
  quiet: "✦",
  public: "⌁",
  wealth: "✣",
  embodied: "◌",
  relational: "♡",
  social: "◈",
  neural: "✧",
};

function restoreSystemNodeGlyphs(document: Document): number {
  let restored = 0;
  document.querySelectorAll<HTMLElement>(".universe-system-node").forEach(node => {
    const icon = node.querySelector<HTMLElement>(":scope > i");
    const key = Object.keys(SYSTEM_NODE_GLYPHS).find(name => node.classList.contains(name));
    const glyph = key ? SYSTEM_NODE_GLYPHS[key] : null;
    if (!icon || !glyph) return;

    if (icon.textContent !== glyph || icon.childElementCount > 0) {
      icon.replaceChildren(document.createTextNode(glyph));
      restored += 1;
    }
    icon.classList.remove("nur-exact-mini-host", "nur-v136-v89-mini-host");
    icon.querySelectorAll(`.${V197_STAR_SEAL_CLASS}, .nur-star-module`).forEach(element => element.remove());
    icon.removeAttribute(AUTHENTIC_HOST_ATTRIBUTE);
    delete icon.dataset.nurMiniCompacted;
    delete icon.dataset.nurStarSeal;
    icon.dataset.nurNativeGlyph = "true";
  });
  return restored;
}

function createFallbackStartupStar(document: Document): HTMLElement {
  const star = document.createElement("div");
  star.className = "i-spark spark";

  ["spark-glow", "spark-halo", "spark-h2", "spark-core"].forEach(className => {
    const layer = document.createElement("div");
    layer.className = className;
    star.append(layer);
  });

  const rayset = document.createElement("div");
  rayset.className = "rayset";
  const rayColors = ["g", "h", "g", "p", "g", "h", "g", "p", "g", "h", "g", "p"];
  rayColors.forEach((color, index) => {
    const ray = document.createElement("div");
    ray.className = `ray ${color} r${index + 1}`;
    const glow = document.createElement("div");
    glow.className = "ray-glow";
    const core = document.createElement("div");
    core.className = "ray-core";
    ray.append(glow, core);
    rayset.append(ray);
  });
  star.append(rayset);

  ["ob1", "ob2", "ob3"].forEach(className => {
    const orbit = document.createElement("div");
    orbit.className = `ob ${className}`;
    star.append(orbit);
  });
  return star;
}

function cloneV197StartupStar(document: Document, keepIntroPresentation: boolean): HTMLElement {
  const source = document.getElementById(V197_STARTUP_STAR_SOURCE_ID);
  const star = source instanceof HTMLElement
    ? source.cloneNode(true) as HTMLElement
    : createFallbackStartupStar(document);

  star.removeAttribute("id");
  star.classList.remove("explode");
  if (keepIntroPresentation) {
    // The authenticated Universe source reuses #iSpark for its scaled hero and
    // carries hero-only classes. A startup seal must retain the exact child
    // structure while using only the canonical Entry loading-star classes,
    // otherwise the three orbiting sparks receive two competing motion rigs.
    star.className = `i-spark spark ${V197_SIGIL_STAR_CLASS}`;
    star.removeAttribute("role");
    star.removeAttribute("tabindex");
    star.removeAttribute("aria-label");
    star.setAttribute("aria-hidden", "true");
  } else {
    // This is the exact V197 mountMasterStar conversion used by the canonical runtime.
    star.classList.remove("i-spark");
    star.classList.add("f4-master-star", V197_SIGIL_STAR_CLASS);
    star.setAttribute("aria-hidden", "true");
  }
  return star;
}

function createSealHost(
  document: Document,
  size: number,
  twinkle: boolean,
  startup: boolean,
): HTMLElement {
  const seal = document.createElement("i");
  seal.className = [
    V197_STAR_SEAL_CLASS,
    startup ? V197_STARTUP_STAR_CLASS : `${V197_STAR_SEAL_CLASS}--${size}`,
  ].join(" ");
  seal.setAttribute("aria-hidden", "true");
  seal.dataset.nurStarSize = String(size);
  seal.dataset.nurStarTwinkle = String(twinkle);
  seal.dataset.nurV197SigilSource = `#${V197_STARTUP_STAR_SOURCE_ID}`;
  seal.style.setProperty("--nur-star-seal-size", `${size}px`);
  seal.style.setProperty("--nur-star-seal-scale", String(size / 100));
  seal.append(cloneV197StartupStar(document, startup));
  return seal;
}

export function createV197StartupStar(document: Document): HTMLElement {
  return createSealHost(document, 100, true, true);
}

export function createV197StarSeal(
  document: Document,
  size: V197StarSealSize = 20,
  twinkle = false,
): HTMLElement {
  return createSealHost(document, size, twinkle, false);
}

function nearestSize(value: number): V197StarSealSize {
  return SIZES.reduce((nearest, size) => (
    Math.abs(size - value) < Math.abs(nearest - value) ? size : nearest
  ), 20);
}

function renderedHostSize(host: HTMLElement): V197StarSealSize {
  if (host.closest(".universe-system-node")) return 24;
  if (host.closest(".clean-system-row")) return 16;
  if (host.closest(".lens-map-node")) return 16;
  if (host.closest(".lens-legend")) return 12;
  const rect = host.getBoundingClientRect();
  const measured = Math.max(rect.width, rect.height);
  if (measured > 0) return nearestSize(measured);
  const declared = Number(host.dataset.nurStarSize ?? 20);
  return nearestSize(Number.isFinite(declared) ? declared : 20);
}

function syncV197LegacySealActivity(document: Document): void {
  document.querySelectorAll<HTMLElement>(".nur-exact-mini-host[data-nur-star-seal='authentic']")
    .forEach(host => {
      const control = host.closest("button, a");
      const active = Boolean(control?.matches(".active, [aria-current='page'], [aria-selected='true']"));
      const seal = host.querySelector<HTMLElement>(`:scope > .${V197_STAR_SEAL_CLASS}`);
      if (seal) seal.dataset.nurStarTwinkle = String(active);
    });
}

function ensureControlSeal(
  document: Document,
  host: HTMLElement,
  size: V197StarSealSize,
  stateSeal: boolean,
): number {
  const kind = stateSeal ? V197_STATE_STAR_SEAL_CLASS : V197_CONTROL_STAR_SEAL_CLASS;
  const existing = host.querySelector<HTMLElement>(`:scope > .${kind}`);
  if (existing) return 0;

  const seal = createV197StarSeal(document, size, stateSeal);
  seal.classList.add(kind);
  host.prepend(seal);
  host.classList.add(stateSeal ? "nur-has-state-star-seal" : "nur-has-control-star-seal");
  host.dataset.nurStarSeal = stateSeal ? "selected-control" : "primary-control";
  return 1;
}

function syncV197ControlSeals(document: Document): number {
  let installed = 0;

  document.querySelectorAll<HTMLElement>(PRIMARY_CONTROL_SELECTOR).forEach(control => {
    installed += ensureControlSeal(document, control, control.matches(".compact") ? 16 : 20, false);
  });

  const selectedHosts = new Set(document.querySelectorAll<HTMLElement>(SELECTED_STATE_HOST_SELECTOR));
  document.querySelectorAll<HTMLElement>(`.${V197_STATE_STAR_SEAL_CLASS}`).forEach(seal => {
    const host = seal.parentElement;
    if (host && selectedHosts.has(host)) return;
    seal.remove();
    host?.classList.remove("nur-has-state-star-seal");
    if (host?.dataset.nurStarSeal === "selected-control") delete host.dataset.nurStarSeal;
  });
  selectedHosts.forEach(host => {
    installed += ensureControlSeal(document, host, 20, true);
  });
  return installed;
}

function observeV197ControlSeals(document: Document): void {
  if (controlSealObservers.has(document)) return;
  const frameWindow = document.defaultView;
  const root = document.body ?? document.getElementById("nur-front-v61");
  if (!frameWindow || !root) return;

  let frame: number | null = null;
  const observer = new frameWindow.MutationObserver(() => {
    if (frame !== null) return;
    const schedule = typeof frameWindow.requestAnimationFrame === "function"
      ? frameWindow.requestAnimationFrame.bind(frameWindow)
      : (callback: FrameRequestCallback) => frameWindow.setTimeout(() => callback(frameWindow.performance.now()), 0);
    frame = schedule(() => {
      frame = null;
      restoreSystemNodeGlyphs(document);
      syncV197ControlSeals(document);
      syncV197LegacySealActivity(document);
    });
  });
  observer.observe(root, {
    subtree: true,
    childList: true,
    attributes: true,
    attributeFilter: ["class", "aria-selected", "aria-checked"],
  });
  controlSealObservers.set(document, observer);
}

export function installV197StarSeals(document: Document): number {
  let installed = restoreSystemNodeGlyphs(document);
  document.querySelectorAll<HTMLElement>(".nur-exact-mini-host").forEach(host => {
    if (host.querySelector(`:scope > .${V197_STAR_SEAL_CLASS}`)) return;
    const sourceModule = host.querySelector<HTMLElement>(":scope > .nur-star-module");
    if (!sourceModule) return;

    const control = host.closest("button, a");
    const active = Boolean(control?.matches(".active, [aria-current='page'], [aria-selected='true']"));
    host.replaceChildren(createV197StarSeal(document, renderedHostSize(host), active));
    host.dataset.nurMiniCompacted = "true";
    host.dataset.nurStarSeal = "authentic";
    const visualHost = host.matches(".nur-exact-icon-shell")
      ? host
      : host.closest<HTMLElement>(".nur-exact-icon-shell");
    visualHost?.setAttribute(AUTHENTIC_HOST_ATTRIBUTE, "true");
    installed += 1;
  });
  installed += syncV197ControlSeals(document);
  syncV197LegacySealActivity(document);
  observeV197ControlSeals(document);
  return installed;
}
