import { describe, expect, it, vi } from "vitest";

import {
  V197_LOCALE_META,
  applyV197Locale,
  directionForPreference,
  ensureV197LanguageControls,
} from "../bridge/v197I18n";
import { renderPersistedGlow } from "../bridge/v197Rewards";
import {
  V197_COMPACT_MINI_STAR_CLASS,
  V197_ENTRY_POLISH_STYLE_ID,
  V197_LOCKUP_CLASS,
  V197_LOCKUP_SUBTITLE_CLASS,
  V197_PREMIUM_POLISH_STYLE_ID,
  V197_STABLE_WORDMARK_CLASS,
  V197_WORDMARK_CLASS,
  compactV197MiniStars,
  ensureV197EntryPolish,
  ensureV197PremiumPolish,
  removeV197TodayBrainAnnotations,
} from "../bridge/v197Polish";

function fixture(): Document {
  const document = window.document.implementation.createHTMLDocument("NUR");
  document.body.innerHTML = `
    <nav>
      <button data-page="today"><span class="clean-nav-title">Today</span></button>
      <button data-page="talk"><span class="clean-nav-title">Talk</span></button>
      <button data-page="journal"><span class="clean-nav-title">Journal</span></button>
      <button data-page="plan"><span class="clean-nav-title">Plan</span></button>
      <button data-page="systems"><span class="clean-nav-title">Systems</span></button>
    </nav>
    <button data-world-tab="map">
      <span class="nur-exact-mini-host"><span class="spark-core">STAR_GEOMETRY</span></span>
      <span class="world-label">Map</span>
    </button>
    <button data-world-tab="orbits"><span>Orbits</span></button>
    <button data-world-tab="timeline"><span>Timeline</span></button>
    <button data-world-tab="insights"><span>Insights</span></button>
    <div class="mobile-tabs">
      <button data-page="today">
        <i><span class="nur-exact-mini-host"><span class="spark-core">MOBILE_STAR</span></span></i>
        <span class="mobile-label">Today</span>
      </button>
    </div>
    <h1 id="talk-title">Talk in a room<br><em>that stays yours.</em></h1>
    <input id="talk-input" placeholder="Say it plainly...">
    <div class="universe-map-title"><b class="nur-holo-word">NUR</b><small>Neural Upgrade Rewiring</small></div>
    <section id="page-today">
      <div class="orbit-star-zone">
        <span class="orbit-annotation">mind</span>
        <span class="orbit-annotation">intention</span>
        <span class="orbit-annotation">one move</span>
      </div>
      <div class="today-grid"><article></article><aside>
        <div class="panel-top"><div><h2 class="panel-title">Recent Glows</h2><p class="panel-sub"></p></div></div>
        <div class="glow-row"><div class="glow-item">fake local glow</div></div>
      </aside></div>
    </section>
    <aside class="clean-right-rail">
      <section class="clean-right-card clean-glows-card">
        <div class="clean-card-heading"><span>Recent glows</span></div>
        <div class="clean-glow-list"><div>fake right rail glow</div></div>
      </section>
    </aside>
  `;
  return document;
}

describe("Track A V197 translation bridge", () => {
  it("exposes every founder-mandated locale and native Korean label", () => {
    expect(V197_LOCALE_META).toHaveLength(35);
    expect(V197_LOCALE_META.map(row => row.locale)).toContain("ko");
    expect(V197_LOCALE_META.find(row => row.locale === "ko")?.label).toBe("한국어");
  });

  it("keeps Roman Urdu LTR and Urdu script RTL", () => {
    expect(directionForPreference("ur", "roman")).toBe("ltr");
    expect(directionForPreference("ur", "script")).toBe("rtl");
    expect(directionForPreference("ar", "default")).toBe("rtl");
  });

  it("translates safe V197 text slots without touching the NUR identity", () => {
    const document = fixture();
    applyV197Locale(document, "ur", "roman");

    expect(document.documentElement.lang).toBe("ur");
    expect(document.documentElement.dir).toBe("ltr");
    expect(document.querySelector('[data-page="today"] .clean-nav-title')?.textContent).toBe("Aaj");
    expect(document.querySelector('[data-page="talk"] .clean-nav-title')?.textContent).toBe("Baat");
    expect(document.querySelector("#talk-input")?.getAttribute("placeholder")).toBe("Seedha bolo...");
    expect(document.querySelector(".nur-holo-word")?.textContent).toBe("NUR");
  });

  it("updates only direct V197 labels and preserves nested exact-star geometry", () => {
    const document = fixture();
    applyV197Locale(document, "ur", "roman");

    expect(document.querySelector('[data-world-tab="map"] .nur-exact-mini-host')?.textContent).toBe("STAR_GEOMETRY");
    expect(document.querySelector('[data-world-tab="map"] .world-label')?.textContent).toBe("Naqsha");
    expect(document.querySelector('.mobile-tabs [data-page="today"] .nur-exact-mini-host')?.textContent).toBe("MOBILE_STAR");
    expect(document.querySelector('.mobile-tabs [data-page="today"] .mobile-label')?.textContent).toBe("Aaj");
  });

  it("mounts all locale slots inside the existing V197 scope chamber", async () => {
    const document = fixture();
    const modal = document.createElement("div");
    modal.id = "scope-modal";
    const chamber = document.createElement("div");
    chamber.className = "scope-modal";
    modal.append(chamber);
    document.body.append(modal);
    const save = vi.fn().mockResolvedValue(undefined);

    ensureV197LanguageControls(document, "ko", "default", save);
    const locale = document.querySelector<HTMLSelectElement>("#nur-v197-locale");
    expect(locale?.options).toHaveLength(35);
    expect(locale?.selectedOptions[0]?.textContent).toContain("한국어");
    document.querySelector<HTMLButtonElement>("#nur-v197-language-save")?.click();
    await Promise.resolve();
    expect(save).toHaveBeenCalledWith("ko", "default");
  });
});

describe("Track A persisted Glow renderer", () => {
  it("replaces fake rows using only server-confirmed transactions and streaks", () => {
    const document = fixture();
    const onReward = vi.fn();

    renderPersistedGlow(document, {
      balance: 12,
      lifetime_points: 18,
      recent_transactions: [{
        id: "txn-1",
        event_type: "journal_saved",
        source_kind: "JOURNAL_ENTRY",
        source_id: "journal-1",
        final_points: 4,
        reason: "Journal saved",
        created_at: "2026-07-11T10:00:00Z",
      }],
      streaks: [{
        streak_key: "returning",
        current_count: 3,
        best_count: 5,
        last_event_date: "2026-07-11",
        repairs_remaining: 0,
      }],
    }, onReward);

    expect(document.body.textContent).not.toContain("fake local glow");
    expect(document.body.textContent).not.toContain("fake right rail glow");
    expect(document.body.textContent).toContain("12 Glow Points");
    expect(document.body.textContent).toContain("Journal saved");
    expect(document.body.textContent).toContain("3 day streak");
    expect(onReward).not.toHaveBeenCalled();
  });
});

describe("Track A V197 premium polish", () => {
  it("physically removes the rejected labels around the Today brain", () => {
    const document = fixture();

    expect(removeV197TodayBrainAnnotations(document)).toBe(3);
    expect(removeV197TodayBrainAnnotations(document)).toBe(0);
    expect(document.querySelectorAll("#page-today .orbit-annotation")).toHaveLength(0);
  });

  it("mounts one bridge-scoped corrective layer without replacing canonical DOM", () => {
    const document = fixture();
    const originalMap = document.createElement("section");
    originalMap.className = "universe-map-panel";
    document.body.append(originalMap);
    const miniHost = document.createElement("span");
    miniHost.className = "nur-exact-mini-host nur-mini-16";
    miniHost.innerHTML = `
      <span class="f4-master-star f4-master-star--hero nur-star-module">
        <span class="spark-core"></span>
        <span class="rayset"><span class="ray r1"><span class="ray-core"></span></span></span>
      </span>
    `;
    document.body.append(miniHost);
    const fullMasterStar = document.createElement("span");
    fullMasterStar.id = "iSpark";
    fullMasterStar.className = "f4-master-star f4-master-star--hero";
    fullMasterStar.innerHTML = '<span class="rayset"><span class="ray r1"></span></span>';
    document.body.append(fullMasterStar);

    ensureV197PremiumPolish(document);
    ensureV197PremiumPolish(document);

    const styles = document.querySelectorAll(`#${V197_PREMIUM_POLISH_STYLE_ID}`);
    expect(styles).toHaveLength(1);
    expect((styles[0] as HTMLElement | undefined)?.dataset.nurLayer).toBe("v197-native-universe-presentation");
    expect(document.querySelectorAll(`.${V197_STABLE_WORDMARK_CLASS}`)).toHaveLength(1);
    expect(document.querySelector(`.${V197_STABLE_WORDMARK_CLASS}`)?.textContent).toBe("NUR");
    expect(document.querySelector(".nur-holo-word")?.getAttribute("data-nur-stable-source")).toBe("true");
    expect(document.querySelector(".universe-map-title")?.classList.contains(V197_LOCKUP_CLASS)).toBe(true);
    expect(document.querySelector(".universe-map-title")?.getAttribute("data-nur-lockup-axis")).toBe("center");
    expect(document.querySelector(".nur-holo-word")?.classList.contains(V197_WORDMARK_CLASS)).toBe(true);
    expect(document.querySelector(".nur-holo-word")?.getAttribute("data-nur-holographic-wordmark")).toBe("animated");
    expect(document.querySelector(".universe-map-title small")?.classList.contains(V197_LOCKUP_SUBTITLE_CLASS)).toBe(true);
    expect(document.querySelector(".universe-map-panel")).toBe(originalMap);
    expect(miniHost.dataset.nurMiniCompacted).toBe("true");
    expect(miniHost.querySelectorAll(`.${V197_COMPACT_MINI_STAR_CLASS}`)).toHaveLength(1);
    expect(miniHost.querySelector(".nur-star-module")).toBeNull();
    expect(fullMasterStar.querySelector(".ray")).not.toBeNull();
    const holographicControls = Array.from(document.querySelectorAll<HTMLElement>("button:not(.f4-brand)"));
    expect(holographicControls.length).toBeGreaterThan(0);
    for (const control of holographicControls) {
      expect(control.classList.contains("nur-holo-control")).toBe(true);
      expect(control.dataset.nurHolographicControl).toBe("true");
      expect(control.querySelectorAll(":scope > .nur-holo-film")).toHaveLength(1);
    }
    expect(document.querySelector("#root")).toBeNull();
  });

  it("installs one Entry presentation layer with a stable centered header", () => {
    const document = fixture();
    document.body.innerHTML = `
      <section id="nur-front-v61">
        <header class="f4-head">
          <button class="f4-brand">
            <span class="f4-brand-copy">
              <span class="f4-brand-word">NUR</span>
              <span class="f4-brand-sub">Neural Upgrade Rewiring</span>
            </span>
          </button>
        </header>
        <aside id="f4-sheet" class="f4-sheet open"></aside>
      </section>
    `;
    ensureV197EntryPolish(document);
    ensureV197EntryPolish(document);
    expect(document.querySelectorAll(`#${V197_ENTRY_POLISH_STYLE_ID}`)).toHaveLength(1);
    expect(document.getElementById(V197_ENTRY_POLISH_STYLE_ID)?.dataset.nurLayer).toBe("v197-native-entry-presentation");
    expect(document.querySelector(".f4-brand-copy")?.classList.contains(V197_LOCKUP_CLASS)).toBe(true);
    expect(document.querySelector(".f4-brand-copy")?.getAttribute("data-nur-lockup-axis")).toBe("center");
    expect(document.querySelector(".f4-brand-word")?.classList.contains(V197_WORDMARK_CLASS)).toBe(true);
    expect(document.querySelector(".f4-brand-word")?.getAttribute("data-nur-holographic-wordmark")).toBe("animated");
    expect(document.querySelector(".f4-brand-sub")?.classList.contains(V197_LOCKUP_SUBTITLE_CLASS)).toBe(true);
    expect(document.body.classList.contains("nur-v197-auth-open")).toBe(true);
  });

  it("compacts only newly expanded mini stars and stays idempotent", () => {
    const document = fixture();
    const miniHost = document.createElement("span");
    miniHost.className = "nur-exact-mini-host nur-mini-18";
    miniHost.innerHTML = '<span class="nur-star-module"><span class="ray"></span></span>';
    document.body.append(miniHost);

    expect(compactV197MiniStars(document)).toBe(1);
    expect(compactV197MiniStars(document)).toBe(0);
    expect(miniHost.childElementCount).toBe(1);
    expect(miniHost.firstElementChild?.classList.contains(V197_COMPACT_MINI_STAR_CLASS)).toBe(true);
    expect(document.querySelector('[data-world-tab="map"] .spark-core')?.textContent).toBe("STAR_GEOMETRY");
  });
});
