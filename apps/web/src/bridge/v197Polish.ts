import V197_FUNCTIONAL_CSS from "../styles/v197-functional.css?raw";
import V197_COSMIC_SKIN_CSS from "../styles/v197-cosmic-skin.css?raw";
import V197_STAR_SEAL_CSS from "../styles/v197-star-seal.css?raw";
import V197_HOLOGRAPHIC_CSS from "../styles/v197-holographic.css?raw";
import V197_ADAPTIVE_PERFORMANCE_CSS from "../styles/v197-adaptive-performance.css?raw";
import { lockV197BrandIdentity } from "./v197Brand";
import { V197_FONT_FACE_CSS } from "./v197Fonts";
import { ensureV197BlackGalaxy, ensureV197StarBrain } from "./v197StarBrain";
import { installV197StarSeals, V197_STAR_SEAL_CLASS } from "./v197StarSeal";

export const V197_PREMIUM_POLISH_STYLE_ID = "nur-v197-track-a-premium-polish";
export const V197_STABLE_WORDMARK_CLASS = "nur-v197-stable-wordmark";
export const V197_COMPACT_MINI_STAR_CLASS = V197_STAR_SEAL_CLASS;
export const V197_ENTRY_POLISH_STYLE_ID = "nur-v197-entry-premium-polish";
export {
  V197_LOCKUP_CLASS,
  V197_LOCKUP_SUBTITLE_CLASS,
  V197_WORDMARK_CLASS,
} from "./v197Brand";

const V197_PRESENTATION_CSS = [
  V197_FONT_FACE_CSS,
  V197_FUNCTIONAL_CSS,
  V197_STAR_SEAL_CSS,
  V197_COSMIC_SKIN_CSS,
  V197_HOLOGRAPHIC_CSS,
  V197_ADAPTIVE_PERFORMANCE_CSS,
].join("\n");

function ensureStableMapWordmark(document: Document): HTMLElement | null {
  const title = document.querySelector<HTMLElement>(".universe-map-title");
  const source = title?.querySelector<HTMLElement>(":scope > .nur-holo-word");
  if (!title || !source) return null;

  title.querySelectorAll<HTMLElement>(`:scope > .${V197_STABLE_WORDMARK_CLASS}`)
    .forEach(element => {
      if (element !== source) element.remove();
    });
  source.dataset.nurStableSource = "true";
  source.classList.add(V197_STABLE_WORDMARK_CLASS);
  source.textContent = "NUR";
  return source;
}

function relocateSystemsMantra(document: Document): HTMLElement | null {
  const mantra = document.querySelector<HTMLElement>(".universe-map-mantra");
  const heroCopy = document.querySelector<HTMLElement>("#page-systems .universe-hero-copy > div");
  if (!mantra || !heroCopy) return null;

  mantra.classList.add("nur-systems-epigraph");
  mantra.dataset.nurRelocated = "systems-hero";
  if (mantra.parentElement !== heroCopy) heroCopy.append(mantra);
  return mantra;
}

export function removeV197TodayBrainAnnotations(document: Document): number {
  const annotations = Array.from(document.querySelectorAll<HTMLElement>(
    "#page-today .orbit-star-zone > .orbit-annotation",
  ));
  annotations.forEach(annotation => annotation.remove());
  return annotations.length;
}

/**
 * The owner control in the topbar rendered as an unlabelled circle, so nothing
 * told the owner it ends the session. Canonical CSS pins its size and display
 * with `!important`, so the correction is applied as important inline
 * declarations rather than as a stylesheet rule that would lose the cascade.
 */
function labelOwnerSignOutControl(document: Document): void {
  const control = document.querySelector<HTMLElement>(".nur-user");
  if (!control || control.dataset.nurSignOutLabelled === "true") return;
  control.dataset.nurSignOutLabelled = "true";
  control.setAttribute("role", "button");
  control.setAttribute("aria-label", "Sign out of NUR");
  control.tabIndex = 0;

  // A real text node rather than a ::after. The pseudo-element resolved its
  // content but rendered at zero width inside this control, and a text node is
  // also what a screen reader and a translation pass can actually reach.
  if (!control.querySelector(".nur-signout-label")) {
    const label = control.ownerDocument.createElement("span");
    label.className = "nur-signout-label";
    label.textContent = "\u23FB Sign out";
    label.style.setProperty("font", '500 12.5px/1 "Crimson Pro", serif', "important");
    label.style.setProperty("letter-spacing", "0.06em", "important");
    label.style.setProperty("color", "rgba(255, 240, 212, 0.92)", "important");
    label.style.setProperty("white-space", "nowrap", "important");
    control.append(label);
  }
  for (const [property, value] of [
    ["width", "auto"],
    ["min-width", "max-content"],
    ["height", "auto"],
    ["min-height", "38px"],
    ["padding", "0 15px"],
    ["gap", "7px"],
    ["display", "inline-flex"],
    ["align-items", "center"],
    ["justify-content", "center"],
    ["border-radius", "999px"],
    ["white-space", "nowrap"],
    ["aspect-ratio", "auto"],
  ] as const) {
    control.style.setProperty(property, value, "important");
  }
}

function labelCompactTopbarControls(document: Document): void {
  document.querySelectorAll<HTMLButtonElement>(".universe-nav-tabs button").forEach(button => {
    const label = button.querySelector("span")?.textContent?.trim();
    if (!label) return;
    button.setAttribute("aria-label", label);
    button.title = label;
  });

  const scope = document.querySelector<HTMLButtonElement>("#scope-open");
  if (scope) {
    scope.setAttribute("aria-label", "Privacy boundary");
    scope.title = "Privacy boundary";
  }
}

export function compactV197MiniStars(document: Document): number {
  return installV197StarSeals(document);
}

function installPresentationStyle(
  document: Document,
  styleId: string,
  layer: string,
): HTMLStyleElement {
  const existing = document.getElementById(styleId) as HTMLStyleElement | null;
  if (existing) return existing;

  const style = document.createElement("style");
  style.id = styleId;
  style.dataset.nurLayer = layer;
  style.textContent = V197_PRESENTATION_CSS;
  (document.body ?? document.head).append(style);
  return style;
}

function installEntrySheetState(document: Document): void {
  const root = document.documentElement;
  if (root.dataset.nurEntrySheetState === "bound") return;
  root.dataset.nurEntrySheetState = "bound";

  const sheet = document.querySelector<HTMLElement>("#f4-sheet");
  const sync = () => document.body?.classList.toggle(
    "nur-v197-auth-open",
    Boolean(sheet?.classList.contains("open")),
  );
  const openBeforeCanonicalHandler = (event: Event) => {
    const target = event.target as Element | null;
    if (!target?.closest("#f4-begin, #f4-signin, #f4-what, #f4-about-begin, [data-switch]")) return;
    document.body?.classList.add("nur-v197-auth-open");
  };

  document.addEventListener("click", openBeforeCanonicalHandler, true);
  sync();
  if (sheet && document.defaultView) {
    const observer = new document.defaultView.MutationObserver(sync);
    observer.observe(sheet, { attributes: true, attributeFilter: ["class"] });
  }
}


/**
 * Give every control a real holographic film.
 *
 * The controls read as two or three tones because canonical already owns both
 * pseudo elements on them — `nurHeroSheen` on ::before and `nurHeroSparkle` on
 * ::after. Two earlier attempts painted a spectrum on one of those and silently
 * destroyed the canonical effect underneath, which is a trade nobody asked for.
 *
 * So the film gets its own element, the same pattern the star seal and the
 * sign-out label already use here. Both canonical pseudo elements survive
 * untouched and the spectrum sits between them.
 */
const HOLO_FILM_CLASS = "nur-holo-film";
const HOLO_CONTROL_CLASS = "nur-holo-control";
const HOLO_ANCHOR_CLASS = "nur-holo-anchor";
const HOLO_TARGETS = [
  "button:not(.f4-brand)",
  "a.soft-button", "a.tiny-link", "a.universe-lens-tab", "a.nur-adjunct-button",
  ".scope-option", ".scope-chip", ".nur-chip",
].join(",");

type HolographicFilmController = {
  observer: MutationObserver;
  frame: number | null;
};

const holographicFilmControllers = new WeakMap<Document, HolographicFilmController>();

function installHolographicFilm(document: Document): number {
  const controls = document.querySelectorAll<HTMLElement>(HOLO_TARGETS);
  let added = 0;
  for (const control of controls) {
    control.classList.add(HOLO_CONTROL_CLASS);
    control.dataset.nurHolographicControl = "true";
    if (control.dataset.nurHolographicPosition === undefined) {
      const position = document.defaultView?.getComputedStyle(control).position;
      control.dataset.nurHolographicPosition = position ?? "unresolved";
      control.classList.toggle(HOLO_ANCHOR_CLASS, position === "static");
    }
    if (control.querySelector(`:scope > .${HOLO_FILM_CLASS}`)) continue;
    // A dedicated inert element avoids canonical `button > i` icon rules and
    // `button > span` label rules shrinking the optical layer into content.
    const film = document.createElement("nur-holo-film");
    film.className = HOLO_FILM_CLASS;
    film.setAttribute("aria-hidden", "true");
    // Prepended so it sits under the label and above the control's own fill.
    control.prepend(film);
    added += 1;
  }
  return added;
}

/**
 * Canonical hydration and bridge-native routes both add controls after the
 * first presentation pass. Observe those mounts once per document and batch a
 * single idempotent film scan into the next frame, so every real control gets
 * the same material without teaching each product renderer about presentation.
 */
function observeHolographicControls(document: Document): void {
  if (holographicFilmControllers.has(document)) return;
  const frameWindow = document.defaultView;
  const root = document.body ?? document.documentElement;
  if (!frameWindow || !root) return;

  const controller: HolographicFilmController = {
    observer: null as unknown as MutationObserver,
    frame: null,
  };
  const observer = new frameWindow.MutationObserver(records => {
    if (!records.some(record => record.addedNodes.length > 0) || controller.frame !== null) return;
    controller.frame = frameWindow.requestAnimationFrame(() => {
      controller.frame = null;
      installHolographicFilm(document);
    });
  });
  controller.observer = observer;
  observer.observe(root, { childList: true, subtree: true });
  holographicFilmControllers.set(document, controller);
}

export function ensureV197EntryPolish(document: Document): HTMLStyleElement {
  const style = installPresentationStyle(
    document,
    V197_ENTRY_POLISH_STYLE_ID,
    "v197-native-entry-presentation",
  );
  installEntrySheetState(document);
  lockV197BrandIdentity(document);
  installV197StarSeals(document);
  installHolographicFilm(document);
  observeHolographicControls(document);
  ensureV197BlackGalaxy(document);
  ensureV197StarBrain(document);
  return style;
}


/**
 * Match the universe background to Entry exactly.
 *
 * Measured: Entry's body is `rgb(0, 0, 0)` with no background image, while
 * `#page-systems` computed `rgba(0, 0, 0, 0.7)` plus a warm gold radial wash,
 * and `.nur-shell` carried a second radial. The two stages did not read as one
 * room, and that black sheet also dimmed the star field behind the panels.
 *
 * Canonical declares these by id under the same `body.universe-edition` prefix,
 * so a stylesheet rule ties on specificity and the winner depends on injection
 * order; raising specificity further still lost. Inline `important` is the
 * pattern already used here for the sign-out control, for the same reason, and
 * it cannot be outranked.
 */
function matchUniverseBackgroundToEntry(document: Document): void {
  const surfaces = document.querySelectorAll<HTMLElement>(
    ".nur-page, .universe-page-shell, .nur-shell, .nur-main, .nur-viewport",
  );
  for (const surface of surfaces) {
    surface.style.setProperty("background-color", "transparent", "important");
    surface.style.setProperty("background-image", "none", "important");
  }
  const body = document.body;
  if (body) {
    body.style.setProperty("background-color", "rgb(0, 0, 0)", "important");
    body.style.setProperty("background-image", "none", "important");
  }
}

export function ensureV197PremiumPolish(document: Document): HTMLStyleElement {
  const style = installPresentationStyle(
    document,
    V197_PREMIUM_POLISH_STYLE_ID,
    "v197-native-universe-presentation",
  );
  compactV197MiniStars(document);
  removeV197TodayBrainAnnotations(document);
  ensureStableMapWordmark(document);
  lockV197BrandIdentity(document);
  relocateSystemsMantra(document);
  labelCompactTopbarControls(document);
  labelOwnerSignOutControl(document);
  installHolographicFilm(document);
  observeHolographicControls(document);
  matchUniverseBackgroundToEntry(document);
  ensureV197BlackGalaxy(document);
  ensureV197StarBrain(document);
  return style;
}
