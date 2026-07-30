/**
 * The starfield backdrop shared by Orbit, Map and Timeline.
 *
 * Why this exists, stated plainly because I got it wrong twice:
 *
 * First attempt — each surface painted a solid `#000000` at z-index 320. That
 * covered `#space3d`, the canonical galaxy canvas at z-index 280, so the three
 * surfaces rendered over a dead black field and NUR's universe disappeared
 * entirely. The founder's note was exact: there were no stars.
 *
 * Second attempt — making the surface root translucent brought the stars back
 * and also brought the *canonical page content* with them. `#nur-front-v61`,
 * the canonical product chrome, sits at z-index 10, below the galaxy. Through a
 * thin scrim its headline, Systems list and panels showed through and collided
 * with the surface's own UI. Two interfaces at once, both unreadable.
 *
 * What actually works, and what this module does: hide only the canonical
 * *content* layer while a bridge surface owns the screen, and leave `#space3d`
 * completely alone. The galaxy keeps rendering and stays visible; the competing
 * chrome does not. The surface root then needs only a light vignette for text
 * contrast rather than an opaque fill.
 *
 * This changes presentation state, never canonical bytes: one class on `<body>`,
 * added on mount and removed the moment the route stops matching, exactly the
 * mechanism canonical V197 already uses for `nur-v197-systems-active`. Leaving a
 * surface restores the canonical page with no other work, and
 * `check-v197-integrity.sh` is unaffected because nothing in the canonical
 * document is edited.
 */

const STYLE_ID = "nur-bridge-backdrop-style";
const BODY_CLASS = "nur-bridge-surface-active";

/** The elements that must keep rendering: the galaxy, and nothing else. */
const BACKDROP_CSS = `
/* While a bridge-native surface owns the screen, the canonical content layer
 * steps aside so the surface is readable — but the galaxy behind it keeps
 * rendering, because the starfield *is* the NUR universe and must stay visible.
 *
 * Uses visibility rather than display on purpose: it leaves layout, paint order
 * and every canonical measurement intact, so nothing in the canonical runtime
 * observes a reflow while a surface is mounted. */
body.${BODY_CLASS} #nur-front-v61 {
  visibility: hidden !important;
}

/* The nur-a11y-live region is the screen-reader announcement node and a direct
 * child of body, so hiding the chrome above did not cover it — its latest
 * announcement was painting as loose text across the top of every surface.
 *
 * It is clipped rather than hidden, because visibility:hidden and display:none
 * both remove a live region from the accessibility tree, which would silence
 * announcements a sighted-user fix has no business breaking. This is the standard
 * visually-hidden clip, so it keeps announcing and stops painting. */
body.${BODY_CLASS} #nur-a11y-live {
  position: absolute !important;
  width: 1px !important;
  height: 1px !important;
  margin: -1px !important;
  padding: 0 !important;
  overflow: hidden !important;
  clip: rect(0, 0, 0, 0) !important;
  white-space: nowrap !important;
  border: 0 !important;
}

/* Explicitly protected. If a future rule tries to dim or hide the galaxy while a
 * surface is active, this is the line that should fail a review. */
body.${BODY_CLASS} #space3d {
  visibility: visible !important;
  display: block !important;
}
`;

function ensureBackdropStyle(doc: Document): void {
  if (doc.getElementById(STYLE_ID)) return;
  const style = doc.createElement("style");
  style.id = STYLE_ID;
  style.textContent = BACKDROP_CSS;
  doc.head.append(style);
}

/**
 * Turn the starfield backdrop on or off for a bridge-native surface.
 *
 * Every surface must call this with `false` on its non-matching route branch, or
 * leaving the route would leave the canonical page hidden.
 */
export function setV197SurfaceBackdrop(doc: Document, active: boolean): void {
  if (active) {
    ensureBackdropStyle(doc);
    doc.body.classList.add(BODY_CLASS);
    return;
  }
  doc.body.classList.remove(BODY_CLASS);
}
