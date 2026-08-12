import {
  V197_CONTROL_STAR_SEAL_CLASS,
  V197_SIGIL_STAR_CLASS,
  V197_STATE_STAR_SEAL_CLASS,
  V197_STAR_SEAL_CLASS,
  V197_STARTUP_STAR_CLASS,
  createV197StarSeal,
  createV197StartupStar,
  installV197StarSeals,
} from "../bridge/v197StarSeal";
import { applyV197Locale } from "../bridge/v197I18n";

describe("V197 star seal", () => {
  beforeEach(() => {
    document.body.replaceChildren();
  });

  it("reuses the exact V197 startup-star structure without an SVG approximation", () => {
    document.body.innerHTML = `
      <button class="active"><span class="nur-exact-mini-host" data-nur-star-size="16"><span class="nur-star-module"></span></span></button>
      <button><span class="nur-exact-mini-host" data-nur-star-size="24"><span class="nur-star-module"></span></span></button>
    `;

    expect(installV197StarSeals(document)).toBe(2);
    expect(installV197StarSeals(document)).toBe(0);
    const seals = [...document.querySelectorAll<HTMLElement>(`.${V197_STAR_SEAL_CLASS}`)];
    expect(seals).toHaveLength(2);
    seals.forEach(seal => {
      expect(seal.dataset.nurV197SigilSource).toBe("#iSpark");
      expect(seal.querySelectorAll(`:scope > .${V197_SIGIL_STAR_CLASS}.spark`)).toHaveLength(1);
      expect(seal.querySelectorAll(".ray")).toHaveLength(12);
      expect(seal.querySelectorAll(".ob")).toHaveLength(3);
      expect(seal.querySelector(".spark-glow")).not.toBeNull();
      expect(seal.querySelector(".spark-halo")).not.toBeNull();
      expect(seal.querySelector(".spark-h2")).not.toBeNull();
      expect(seal.querySelector(".spark-core")).not.toBeNull();
    });
    expect(document.querySelector("svg, use")).toBeNull();
    expect(document.querySelector(".nur-v197-mini-star-lite")).toBeNull();
    expect(document.querySelector<HTMLElement>(".nur-exact-mini-host")?.dataset.nurStarSeal).toBe("authentic");
    expect(document.querySelector<HTMLElement>(`.${V197_STAR_SEAL_CLASS}`)?.dataset.nurStarTwinkle).toBe("true");
  });

  it("supports the canonical 12, 16, 20, 24, and 32 pixel sizes", () => {
    for (const size of [12, 16, 20, 24, 32] as const) {
      const seal = createV197StarSeal(document, size);
      expect(seal.classList.contains(`${V197_STAR_SEAL_CLASS}--${size}`)).toBe(true);
      expect(seal.style.getPropertyValue("--nur-star-seal-size")).toBe(`${size}px`);
      expect(seal.dataset.nurStarTwinkle).toBe("false");
    }
  });

  it("can replay the exact intro presentation from the canonical iSpark source", () => {
    document.body.innerHTML = `
      <div id="iSpark" class="spark nur-v33-master nur-v34-exact-symbol f4-master-star f4-master-star--hero"
        role="button" tabindex="0" aria-label="Wake the NUR star">
        <div class="spark-glow"></div><div class="spark-halo"></div>
        <div class="spark-h2"></div><div class="spark-core"></div>
        <div class="rayset">${Array.from({ length: 12 }, (_, index) => `<div class="ray g r${index + 1}"><div class="ray-glow"></div><div class="ray-core"></div></div>`).join("")}</div>
        <div class="ob ob1"></div><div class="ob ob2"></div><div class="ob ob3"></div>
      </div>
    `;

    const startup = createV197StartupStar(document);
    expect(startup.classList.contains(V197_STARTUP_STAR_CLASS)).toBe(true);
    expect(startup.dataset.nurV197SigilSource).toBe("#iSpark");
    expect(startup.querySelector("#iSpark")).toBeNull();
    const star = startup.querySelector<HTMLElement>(`.i-spark.${V197_SIGIL_STAR_CLASS}`);
    expect(star).not.toBeNull();
    expect([...star!.classList]).toEqual(["i-spark", "spark", V197_SIGIL_STAR_CLASS]);
    expect(star!.hasAttribute("role")).toBe(false);
    expect(star!.hasAttribute("tabindex")).toBe(false);
    expect(star!.hasAttribute("aria-label")).toBe(false);
    expect(star!.getAttribute("aria-hidden")).toBe("true");
    expect(startup.querySelectorAll(".ray")).toHaveLength(12);
    expect(startup.querySelectorAll(".ob")).toHaveLength(3);
  });

  it("marks legacy icon shells and normalizes system seal sizes", () => {
    document.body.innerHTML = `
      <button class="universe-system-node active">
        <i class="nur-exact-icon-shell"><span class="nur-exact-mini-host"><span class="nur-star-module"></span></span></i>
      </button>
      <button class="clean-system-row">
        <i class="nur-exact-icon-shell nur-exact-mini-host"><span class="nur-star-module"></span></i>
      </button>
    `;

    expect(installV197StarSeals(document)).toBe(2);
    const hosts = document.querySelectorAll<HTMLElement>(".nur-exact-icon-shell");
    expect(hosts[0]?.dataset.nurAuthenticStarHost).toBe("true");
    expect(hosts[1]?.dataset.nurAuthenticStarHost).toBe("true");
    expect(hosts[0]?.querySelector(`.${V197_STAR_SEAL_CLASS}--24`)).not.toBeNull();
    expect(hosts[1]?.querySelector(`.${V197_STAR_SEAL_CLASS}--16`)).not.toBeNull();
  });

  it("keeps active Map twinkle on the selected authentic node", () => {
    document.body.innerHTML = `
      <main id="nur-front-v61">
        <button class="lens-map-node active"><span class="nur-exact-mini-host"><span class="nur-star-module"></span></span></button>
        <button class="lens-map-node"><span class="nur-exact-mini-host"><span class="nur-star-module"></span></span></button>
      </main>
    `;

    expect(installV197StarSeals(document)).toBe(2);
    const nodes = document.querySelectorAll<HTMLElement>(".lens-map-node");
    expect(nodes[0]?.querySelector(`.${V197_STAR_SEAL_CLASS}--16`)?.getAttribute("data-nur-star-twinkle")).toBe("true");
    expect(nodes[1]?.querySelector(`.${V197_STAR_SEAL_CLASS}--16`)?.getAttribute("data-nur-star-twinkle")).toBe("false");

    nodes[0]?.classList.remove("active");
    nodes[1]?.classList.add("active");
    expect(installV197StarSeals(document)).toBe(0);
    expect(nodes[0]?.querySelector(`.${V197_STAR_SEAL_CLASS}`)?.getAttribute("data-nur-star-twinkle")).toBe("false");
    expect(nodes[1]?.querySelector(`.${V197_STAR_SEAL_CLASS}`)?.getAttribute("data-nur-star-twinkle")).toBe("true");
  });

  it("uses authentic seals for primary and selected controls without duplicating them", () => {
    document.body.innerHTML = `
      <main id="nur-front-v61">
        <button class="f4-primary compact">Begin</button>
        <button class="thought-send-button">Send</button>
        <button class="clean-nav-button active"><span class="clean-nav-glyph">*</span><span>Today</span></button>
        <button class="clean-nav-button"><span class="clean-nav-glyph">*</span><span>Talk</span></button>
      </main>
    `;

    expect(installV197StarSeals(document)).toBe(3);
    expect(installV197StarSeals(document)).toBe(0);
    expect(document.querySelectorAll(`.${V197_CONTROL_STAR_SEAL_CLASS}`)).toHaveLength(2);
    expect(document.querySelectorAll(`.${V197_STATE_STAR_SEAL_CLASS}`)).toHaveLength(1);
    expect(document.querySelectorAll(`.${V197_CONTROL_STAR_SEAL_CLASS} > .spark`)).toHaveLength(2);
    expect(document.querySelector(`.clean-nav-button.active .${V197_STATE_STAR_SEAL_CLASS}`)).not.toBeNull();

    const nav = document.querySelectorAll<HTMLElement>(".clean-nav-button");
    nav[0]?.classList.remove("active");
    nav[1]?.classList.add("active");
    expect(installV197StarSeals(document)).toBe(1);
    expect(nav[0]?.querySelector(`.${V197_STATE_STAR_SEAL_CLASS}`)).toBeNull();
    expect(nav[1]?.querySelector(`.${V197_STATE_STAR_SEAL_CLASS}`)).not.toBeNull();
  });

  it("covers adjunct primary and current navigation controls", () => {
    document.body.innerHTML = `
      <main id="nur-front-v61"></main>
      <section id="nur-v197-adjunct-root">
        <button class="nur-adjunct-button is-primary">Continue</button>
        <nav class="nur-community-nav"><button class="nur-adjunct-button" aria-current="page">Feed</button></nav>
      </section>
    `;

    expect(installV197StarSeals(document)).toBe(2);
    expect(document.querySelector(".nur-adjunct-button.is-primary .nur-star-seal--control > .spark")).not.toBeNull();
    expect(document.querySelector(".nur-community-nav [aria-current='page'] .nur-star-seal--state > .spark")).not.toBeNull();
  });

  it("survives locale hydration on Send controls without becoming label text", () => {
    document.body.innerHTML = `
      <main id="nur-front-v61">
        <button class="thought-send-button" data-send="today"><span>Send</span></button>
      </main>
    `;

    expect(installV197StarSeals(document)).toBe(1);
    applyV197Locale(document, "en");

    const seal = document.querySelector<HTMLElement>(".thought-send-button > i.nur-star-seal--control");
    expect(seal?.textContent).toBe("");
    expect(seal?.querySelectorAll(".ray")).toHaveLength(12);
    expect(document.querySelector(".thought-send-button > span")?.textContent).toBe("Send");
  });
});
