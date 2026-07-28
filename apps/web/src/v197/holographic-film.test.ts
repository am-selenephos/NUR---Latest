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

  it("is injected as a child by the bridge on both stages", () => {
    expect(polish).toContain('film.className = HOLO_FILM_CLASS');
    expect(polish).toContain("control.prepend(film)");
    // entry and universe both install it
    expect(polish.match(/installHolographicFilm\(document\)/g)?.length).toBe(2);
  });

  it("never injects twice into the same control", () => {
    expect(polish).toContain(':scope > .${HOLO_FILM_CLASS}');
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

  it("drifts on transform so the animation composites", () => {
    const frames = css.slice(css.indexOf("@keyframes nurHoloFilmDrift"));
    const body = frames.slice(0, frames.indexOf("}\n\n"));
    expect(body).toContain("translate3d");
    // background-position or filter here would force a repaint every frame.
    expect(body).not.toMatch(/background-position|filter:/);
  });

  it("stands down for reduced motion", () => {
    const query = css.slice(css.lastIndexOf("prefers-reduced-motion"));
    expect(query).toContain(".nur-holo-film::before");
    expect(query).toContain("animation: none");
  });
});
