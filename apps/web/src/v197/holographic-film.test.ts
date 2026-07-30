/**
 * The controls carry a holographic film, and it must not cost a canonical effect.
 *
 * Two earlier attempts painted the spectrum straight onto `.f4-primary::before`
 * and then `::after`. Canonical owns both — `nurHeroSheen` on one and
 * `nurHeroSparkle` on the other — so each attempt silently deleted an effect
 * nobody agreed to trade away, and nothing failed to say so. Hence a real child
 * element, and hence these tests: the next person who reaches for a pseudo
 * element here gets a red test instead of a quiet regression.
 */
import { describe, expect, it } from "vitest";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

const read = (path: string) => readFileSync(resolve(process.cwd(), path), "utf8");
const css = read("src/styles/v197-holographic.css");
const polish = read("src/bridge/v197Polish.ts");

describe("holographic film", () => {
  it("paints on its own element, never on a control's pseudo elements", () => {
    // Any rule that styles ::before/::after of a control directly would be
    // overwriting canonical. The film's own pseudo elements are the exception.
    const controlPseudoRules = css
      .split("\n")
      .filter(line => /^\s*\.(f4-primary|f4-signin|f4-link|soft-button|send-holo-pill)[^{,]*::(before|after)/.test(line))
      .filter(line => !line.includes(".nur-holo-film"));
    expect(controlPseudoRules).toEqual([]);
  });

  it("is injected as a child on both stages and refreshed after async mounts", () => {
    expect(polish).toContain('film.className = HOLO_FILM_CLASS');
    expect(polish).toContain('document.createElement("nur-holo-film")');
    expect(polish).not.toContain('document.createElement("i")');
    expect(polish).toContain("control.prepend(film)");
    expect(polish).toContain('"button:not(.f4-brand)"');
    expect(polish).toContain('control.classList.add(HOLO_CONTROL_CLASS)');
    expect(polish).toContain("control.dataset.nurHolographicPosition === undefined");
    expect(polish).toContain('control.classList.toggle(HOLO_ANCHOR_CLASS, position === "static")');
    // Entry and Universe install immediately; the observer performs the one
    // batched refresh for controls mounted later.
    expect(polish.match(/installHolographicFilm\(document\);/g)?.length).toBe(3);
  });

  it("never injects twice into the same control", () => {
    expect(polish).toContain(':scope > .${HOLO_FILM_CLASS}');
  });

  it("covers controls rendered after hydration without rescanning per mutation", () => {
    expect(polish).toContain("const holographicFilmControllers = new WeakMap");
    expect(polish).toContain("controller.frame !== null");
    expect(polish).toContain("frameWindow.requestAnimationFrame");
    expect(polish.match(/observeHolographicControls\(document\)/g)?.length).toBe(2);
  });

  it("shows a full spectrum across the control, not a slice of one", () => {
    // A single wheel stretched over a 300% surface puts only a third of the
    // spectrum over the button, which is what read as two or three tones.
    // Repeating the wheel every third keeps a whole wheel on the control.
    expect(css).toContain("repeating-linear-gradient");
    const wheel = css.slice(css.indexOf("repeating-linear-gradient"));
    const stops = wheel.slice(0, wheel.indexOf(");")).match(/rgba\(/g) ?? [];
    expect(stops.length).toBeGreaterThanOrEqual(11);
    expect(wheel).toContain("33.33%");
  });

  it("drives every film from one inherited transform phase", () => {
    const frames = css.slice(css.indexOf("@keyframes nurHoloGlobalPhase"));
    const body = frames.slice(0, frames.indexOf("}\n\n"));
    expect(body).toContain("--nur-holo-global-x");
    expect(css).toContain(
      "transform: translate3d(calc(var(--nur-holo-global-x) + var(--nur-holo-local-x)), 0, 0)",
    );
    expect(css).toContain("animation: nurHoloGlobalPhase 18s linear infinite");
    expect(css).toContain("--nur-holo-local-x: -16.5%");
    // Background-position or hue rotation would repaint the film every frame.
    expect(body).not.toMatch(/background-position|filter:/);
  });

  it("keeps a transparent full spectrum moving on every control and brightens attention states", () => {
    const globalFilm = css.slice(
      css.indexOf(".nur-holo-film {"),
      css.indexOf("/* ── 14. System-node crystal"),
    );
    expect(css).toContain(".nur-holo-control:is(");
    expect(css).toContain(".nur-holo-control:is(:hover, :focus-visible)");
    expect(globalFilm).toContain("opacity: .075");
    expect(globalFilm).toContain("opacity: .09");
    expect(globalFilm).toContain("rgba(0, 0, 0, .025)");
    expect(css).toContain("filter: brightness(1.18) saturate(1.1)");
    expect(css).not.toContain("animation: nurHoloFilmDrift");
    expect(css.match(/animation: nurHoloGlobalPhase 18s linear infinite/g)).toHaveLength(1);
  });

  it("gives the six brain nodes restrained crystal states without touching their geometry", () => {
    const start = css.indexOf("/* ── 14. System-node crystal");
    const end = css.indexOf("@media (prefers-reduced-motion: reduce)", start);
    expect(start).toBeGreaterThan(-1);
    expect(end).toBeGreaterThan(start);
    const crystal = css.slice(start, end);
    const baseRule = crystal.match(
      /\.universe-system-node\.nur-holo-control\[data-nur-holographic-control="true"\]\s*\{([\s\S]*?)\n\}/,
    )?.[1] ?? "";

    expect(baseRule).toContain("rgba(0, 0, 0, .02)");
    expect(baseRule).toContain("blur(14px)");
    expect(baseRule).toContain("rgba(255, 222, 153, .12)");
    expect(baseRule).not.toMatch(/(?:^|\n)\s*(?:left|right|top|bottom|width|height|transform)\s*:/);
    expect(crystal).toContain(".universe-system-node > .nur-holo-film");
    expect(crystal).toContain("rgba(255, 222, 153, .14)");
    expect(crystal).toContain("opacity: .07");
    expect(crystal).toContain("rgba(255, 82, 111, .012)");
    expect(crystal).toContain("opacity: .09");
    expect(crystal).toContain("opacity: 1");
    expect(crystal).toContain(".universe-system-node.nur-holo-control:is(:hover, :focus-visible)");
    expect(crystal).toContain('[aria-selected="true"]');
    expect(crystal).toContain('[aria-pressed="true"]');
    expect(crystal).toContain(".universe-add-system.nur-holo-control");
    expect(crystal).toContain("button.nur-holo-control[data-switch][data-nur-holographic-control=\"true\"]");
    expect(crystal).toContain("min-width: 132px");
    expect(crystal).toContain("min-height: 36px");
    expect(crystal).toContain(".f4-primary.nur-holo-control");
    expect(crystal).toContain("rgba(255, 211, 90, .19)");
    expect(crystal).toContain("@keyframes nurSystemsItalicGold");
  });

  it("stands down for reduced motion", () => {
    const query = css.slice(css.lastIndexOf("prefers-reduced-motion"));
    expect(query).toContain(":root:has(#nur-front-v61)");
    expect(query).toContain("animation: none");
    expect(query).toContain("--nur-holo-global-x: 0%");
  });
});
