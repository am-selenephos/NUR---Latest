/**
 * The canonical content host that Orbit, Map and Timeline mount into.
 *
 * Founder decision: the checkpoint UI stays. The left rail, the top nav
 * (UNIVERSE · MAP · ORBITS · TIMELINE · INSIGHTS), the starfield and the
 * star-brain are the product's identity, and a surface belongs *inside* that
 * shell rather than on top of it. This module is what makes that true.
 *
 * The canonical structure, confirmed against the live document:
 *
 *   #nur-front-v61 .nur-shell
 *     ASIDE.nur-rail          the left rail            (kept, untouched)
 *     MAIN.nur-main
 *       HEADER.nur-topbar     the world nav            (kept, untouched)
 *       SECTION.nur-viewport  the content region       (the host lives here)
 *         SECTION.nur-page    the canonical page       (hidden while mounted)
 *
 * Two earlier attempts were wrong and are recorded here so they are not
 * repeated. First, each surface painted an opaque `#000000` on a `position:
 * fixed` root at z-index 320: that covered `#space3d` — the galaxy canvas at 280
 * — and NUR lost its stars entirely. Second, making that root translucent
 * brought the stars back but also the canonical page beneath it, so two
 * interfaces rendered at once.
 *
 * Mounting inside the shell fixes both at the root. `#nur-front-v61` sits at
 * z-index 10, *below* the galaxy, and `#space3d` blends with `mix-blend-mode:
 * screen` — which only ever lightens. So canonical content and anything hosted
 * beside it receive the starfield painted over them, which is precisely how the
 * canonical page gets its stars. A surface in here needs no scrim and no
 * stacking tricks: it inherits the real thing.
 *
 * Nothing canonical is edited. One class and one appended child, both removed on
 * the way out, so `check-v197-integrity.sh` is unaffected.
 */

const STYLE_ID = "nur-surface-host-style";
const HOST_ID = "nur-surface-host";
const BODY_CLASS = "nur-surface-hosted";

const HOST_CSS = `
/* While a surface is hosted, the canonical page inside the viewport steps aside.
 * Only the page — never the rail, never the topbar, never the galaxy. */
body.${BODY_CLASS} .nur-viewport > .nur-page {
  display: none !important;
}

/* The host fills the canonical content region and adds nothing of its own: no
 * background, no border, no stacking context that could trap the surface below
 * the starfield. */
#${HOST_ID} {
  display: block;
  position: relative;
  width: 100%;
  min-height: calc(100vh - 96px);
  background: transparent;
}

/* Explicitly protected. If a future rule dims or hides the galaxy or the shell
 * while a surface is hosted, these are the lines that should fail a review. */
body.${BODY_CLASS} #space3d {
  visibility: visible !important;
  display: block !important;
}

body.${BODY_CLASS} #nur-front-v61,
body.${BODY_CLASS} .nur-rail,
body.${BODY_CLASS} .nur-topbar {
  visibility: visible !important;
}

/* The canonical mobile composer is a page-level control. It must not float on
 * top of a bridge-native surface where it has no route ownership. */
body.${BODY_CLASS}.${BODY_CLASS} #nur-front-v61 .global-composer {
  display: none !important;
}
`;

function ensureHostStyle(doc: Document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = HOST_CSS;
  doc.head.append(style);
}

/**
 * Claim the canonical content region for a bridge-native surface.
 *
 * Returns the element to mount into, or `null` when the canonical viewport is
 * not present. A null return must be treated as "do not render": falling back to
 * `document.body` would recreate the full-screen overlay this module exists to
 * replace.
 */
export function claimV197SurfaceHost(doc: Document): HTMLElement | null {
  const viewport = doc.querySelector<HTMLElement>(".nur-viewport");
  if (!viewport) return null;
  ensureHostStyle(doc);
  doc.body.classList.add(BODY_CLASS);
  let host = doc.getElementById(HOST_ID);
  if (!host) {
    host = doc.createElement("div");
    host.id = HOST_ID;
    viewport.append(host);
  }
  return host;
}

/** Give the canonical content region back. Safe to call when nothing is hosted. */
export function releaseV197SurfaceHost(doc: Document): void {
  doc.body.classList.remove(BODY_CLASS);
  doc.getElementById(HOST_ID)?.remove();
}
