import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const proofRoot = process.env.NUR_TRACK_A_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/track-a" : "proof/track-a");

const scenarioStamp = `${Date.now()}-${Math.floor(Math.random() * 10000)}`;
const persistedTalkLine = `Track A direct Talk ${scenarioStamp}`;
const scenario = {
  email: `track-a-${scenarioStamp}@nur.app`,
  password: `Track-A-${scenarioStamp}!`,
  todayLine: `Track A check-in ${scenarioStamp}`,
  talkLine: persistedTalkLine,
  journalLine: `Track A journal ${scenarioStamp}`,
  planTitle: persistedTalkLine,
  outcomeLine: `Track A outcome ${scenarioStamp}`,
  extraSystem: `Track A System ${scenarioStamp}`,
};

test.describe.configure({ mode: "serial" });

async function shot(page: Page, name: string): Promise<void> {
  await mkdir(proofRoot, { recursive: true });
  await page.screenshot({ path: join(proofRoot, `${name}.png`), fullPage: false, animations: "disabled" });
}

async function criticalMapOverlaps(page: Page): Promise<string[]> {
  return page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
    const elements = [
      ...document.querySelectorAll<HTMLElement>(".universe-system-node"),
      document.querySelector<HTMLElement>(".universe-field-readout"),
      document.querySelector<HTMLElement>(".universe-map-title"),
      document.querySelector<HTMLElement>(".universe-add-system"),
      document.querySelector<HTMLElement>(".universe-map-legend"),
      document.querySelector<HTMLElement>(".universe-map-mantra"),
    ].filter((node): node is HTMLElement => Boolean(node));
    const label = (node: HTMLElement): string => node.dataset.system
      ?? (node.className.split(" ").find(value => value.startsWith("universe-")) || node.tagName);
    const overlaps: string[] = [];
    for (let left = 0; left < elements.length; left += 1) {
      for (let right = left + 1; right < elements.length; right += 1) {
        const a = elements[left].getBoundingClientRect();
        const b = elements[right].getBoundingClientRect();
        const width = Math.max(0, Math.min(a.right, b.right) - Math.max(a.left, b.left));
        const height = Math.max(0, Math.min(a.bottom, b.bottom) - Math.max(a.top, b.top));
        if (width * height > 1) overlaps.push(`${label(elements[left])} / ${label(elements[right])}`);
      }
    }
    return overlaps;
  });
}

async function masterStarClearance(page: Page): Promise<{
  creationLabelOwned: boolean;
  centerDelta: number;
  wordmarkCenterDelta: number;
  subtitleCenterDelta: number;
  panelCenterDelta: number;
  panelScrollLeft: number;
  subtitleOwnedByTitle: boolean;
  wordTopClearance: number;
  wordToSubtitleGap: number;
  clippedLabels: string[];
}> {
  return page.frameLocator("#nur-universe-stage").locator(".universe-map-panel").evaluate(panel => {
    const panelRect = panel.getBoundingClientRect();
    const star = panel.querySelector<HTMLElement>(".universe-master-star")?.getBoundingClientRect();
    const creationSelector = '.universe-system-node[data-system="Creation"]';
    const creation = panel.querySelector<HTMLElement>(creationSelector)?.getBoundingClientRect();
    const title = panel.querySelector<HTMLElement>(".universe-map-title")?.getBoundingClientRect();
    // The lockup word and subtitle carry deliberate ink-compensation
    // translateX nudges (see v197-star-brain.spec.ts); center laws compare
    // the untranslated design centers, so each nudge is subtracted.
    const measureLockup = (selector: string) => {
      const element = panel.querySelector<HTMLElement>(selector);
      if (!element) return null;
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      const transform = style.transform === "none" ? new DOMMatrix() : new DOMMatrix(style.transform);
      return { rect, center: rect.left + rect.width / 2 - transform.m41 };
    };
    const wordmarkLockup = measureLockup(".nur-v197-stable-wordmark");
    const subtitleLockup = measureLockup(".nur-master-subtitle");
    if (!star || !creation || !title || !wordmarkLockup || !subtitleLockup) {
      throw new Error("Required V197 map geometry is missing.");
    }
    const wordmark = wordmarkLockup.rect;
    const subtitle = subtitleLockup.rect;
    const starCenter = star.left + star.width / 2;
    // The consolidated star-brain chamber deliberately extends behind the
    // node cards (f8ddd7a); the law is that no node is BURIED by it. The
    // node may sit below the fold on short viewports, so it is brought into
    // view for the hit-test. scrollIntoView may scroll ANY scrollable
    // ancestor (the map panel itself, not just .nur-viewport), and later
    // probes reuse pre-scroll coordinates — so every ancestor is restored.
    const creationLabelElement = panel.querySelector<HTMLElement>(`${creationSelector} b`);
    let creationLabelOwned = false;
    if (creationLabelElement) {
      const scrolled: Array<{ element: HTMLElement | Element; top: number; left: number }> = [];
      for (let ancestor: HTMLElement | null = creationLabelElement.parentElement;
           ancestor; ancestor = ancestor.parentElement) {
        scrolled.push({ element: ancestor, top: ancestor.scrollTop, left: ancestor.scrollLeft });
      }
      const scrollingRoot = panel.ownerDocument.scrollingElement;
      if (scrollingRoot) {
        scrolled.push({ element: scrollingRoot, top: scrollingRoot.scrollTop, left: scrollingRoot.scrollLeft });
      }
      creationLabelElement.scrollIntoView({ block: "center" });
      const creationLabel = creationLabelElement.getBoundingClientRect();
      const creationOwner = panel.ownerDocument.elementFromPoint(
        creationLabel.left + creationLabel.width / 2,
        creationLabel.top + creationLabel.height / 2,
      );
      creationLabelOwned = Boolean(creationOwner?.closest(creationSelector));
      for (const entry of scrolled) {
        entry.element.scrollTop = entry.top;
        entry.element.scrollLeft = entry.left;
      }
    }
    const clippedLabels = [...panel.querySelectorAll<HTMLElement>(".universe-system-node b")]
      .filter(label => {
        const node = label.closest<HTMLElement>(".universe-system-node");
        if (!node) return false;
        const nodeStyle = getComputedStyle(node);
        const nodeRect = node.getBoundingClientRect();
        if (
          nodeStyle.display === "none"
          || nodeStyle.visibility === "hidden"
          || Number(nodeStyle.opacity) === 0
          || nodeRect.width === 0
          || nodeRect.height === 0
        ) return false;
        const rect = label.getBoundingClientRect();
        return rect.left < panelRect.left - 1 || rect.right > panelRect.right + 1;
      })
      .map(label => label.textContent?.trim() || "unnamed system");
    return {
      creationLabelOwned,
      centerDelta: Math.abs((title.left + title.width / 2) - starCenter),
      wordmarkCenterDelta: Math.abs(wordmarkLockup.center - starCenter),
      subtitleCenterDelta: Math.abs(subtitleLockup.center - starCenter),
      panelCenterDelta: Math.abs(starCenter - (panelRect.left + panelRect.width / 2)),
      panelScrollLeft: panel.scrollLeft,
      // The enlarged star chamber box rises behind the lockup; the law is
      // that the subtitle is not buried by it.
      subtitleOwnedByTitle: Boolean(panel.ownerDocument.elementFromPoint(
        subtitleLockup.center, subtitle.top + subtitle.height / 2,
      )?.closest(".universe-map-title")),
      wordTopClearance: wordmark.top - panelRect.top,
      wordToSubtitleGap: subtitle.top - wordmark.bottom,
      clippedLabels,
    };
  });
}

test("Track A owner mutation loop uses exact V197 controls", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  test.skip(testInfo.project.name !== "chromium-desktop", "The complete mutation journey runs once; mobile/WebKit parity has separate proof.");
  const { email, password, todayLine, talkLine, journalLine, planTitle, outcomeLine } = scenario;

  await page.goto("/", { waitUntil: "load" });
  await expect(page.locator("#root")).toHaveCount(0);
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await expect(entry.locator("#f4-begin")).toBeVisible();
  await shot(page, "01-v197-landing");
  await entry.locator("#f4-begin").click();
  await entry.locator("#f4-name").fill("Track A Owner");
  await entry.locator("#f4-email").fill(email);
  await entry.locator("#f4-password").fill(password);
  await entry.locator("#f4-consent-check").check();
  await shot(page, "02-v197-real-signup");
  await entry.locator("#f4-signup-form button[type='submit']").click();

  const universe = page.frameLocator("#nur-universe-stage");
  await expect(page).toHaveURL(/\/today$/);
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  await universe.locator('[data-page="systems"]:visible').first().click();
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  await expect(universe.locator(".universe-system-node:visible")).toHaveCount(6);
  await expect(universe.locator(".universe-system-node:visible b")).toHaveText([
    "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection",
  ]);
  // Rows lead with the canonical native ✦ glyph; the title lives in the span.
  await expect(universe.locator(".clean-system-row:visible > span")).toHaveText([
    "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection",
  ]);
  // World tabs lead with their canonical native glyph (e.g. "◌ Map").
  await expect(universe.locator('[data-world-tab="map"]')).toHaveText(/Map$/);
  await expect(universe.locator(".universe-insight-panel")).not.toContainText("78%");
  await expect(universe.locator(".universe-insight-panel")).not.toContainText("34 lived returns");
  await expect(universe.locator(`#nur-v197-track-a-premium-polish`)).toHaveCount(1);
  expect(await criticalMapOverlaps(page)).toEqual([]);
  const starGeometry = await masterStarClearance(page);
  expect(starGeometry.creationLabelOwned).toBe(true);
  expect(starGeometry.centerDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.wordmarkCenterDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.subtitleCenterDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.panelCenterDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.panelScrollLeft).toBe(0);
  expect(starGeometry.subtitleOwnedByTitle).toBe(true);
  expect(starGeometry.wordTopClearance).toBeGreaterThanOrEqual(10);
  expect(starGeometry.wordToSubtitleGap).toBeGreaterThanOrEqual(0);
  expect(starGeometry.clippedLabels).toEqual([]);
  await expect(universe.locator(".nur-v197-stable-wordmark")).toHaveText("NUR");
  const wordmarkStyle = await universe.locator(".nur-v197-stable-wordmark").evaluate(node => {
    const style = getComputedStyle(node);
    return {
      fontFamily: style.fontFamily,
      fontWeight: style.fontWeight,
      backgroundClip: style.webkitBackgroundClip,
      animationName: style.animationName,
    };
  });
  expect(wordmarkStyle.fontFamily).toContain("Bodoni Moda");
  expect(wordmarkStyle.fontWeight).toBe("500");
  expect(wordmarkStyle.backgroundClip).toBe("text");
  expect(wordmarkStyle.animationName).toContain("univPrism");
  const topbar = await universe.locator(".nur-topbar").evaluate(node => {
    const boundary = node.getBoundingClientRect();
    const nav = node.querySelector<HTMLElement>(".universe-nav-tabs");
    const tabs = nav ? [...nav.children].map(child => child.getBoundingClientRect()) : [];
    return {
      allTabsInside: tabs.every(rect => rect.left >= boundary.left && rect.right <= boundary.right),
      navScrollable: nav ? nav.scrollWidth > nav.clientWidth + 1 : true,
    };
  });
  expect(topbar).toEqual({ allTabsInside: true, navScrollable: false });
  await expect(universe.locator("#toast")).not.toHaveClass(/show/, { timeout: 7_000 });
  await shot(page, "03-v197-six-persisted-systems");
  await universe.locator(".universe-map-panel").scrollIntoViewIfNeeded();
  await shot(page, "03b-v197-overlap-free-map-1280");

  const aiProvider = await page.evaluate(async () => {
    const response = await fetch("/healthz");
    const body = await response.json() as { ai_provider?: string };
    return body.ai_provider ?? "unknown";
  });
  expect(["disabled", "openai"]).toContain(aiProvider);

  const selectedOrbitId = await universe.locator(".universe-system-node[data-orbit-id]").nth(1).getAttribute("data-orbit-id");
  await universe.locator(".universe-system-node[data-orbit-id]").nth(1).click();
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/profile/preferences");
    return (await response.json()).active_orbit_id as string | null;
  })).toBe(selectedOrbitId);

  await universe.locator('[data-page="today"]:visible').first().click();
  await expect(universe.locator("#page-today")).toHaveClass(/active/);
  await universe.locator('[data-action="checkin"]').click();
  await expect(universe.locator("#nur-v197-today-checkin")).toBeVisible();
  await universe.locator("#nur-checkin-energy").fill("7");
  await universe.locator("#nur-checkin-pain").fill("3");
  await universe.locator("#nur-checkin-sleep").fill("7");
  await universe.locator("#nur-checkin-nourishment").fill("7");
  await universe.locator("#nur-checkin-movement").fill("6");
  await universe.locator("#nur-checkin-load").fill("4");
  await universe.locator("#nur-checkin-clarity").fill("8");
  await universe.locator('[data-action="save-today-checkin"]').click();
  await expect(universe.locator("#nur-v197-today-checkin")).toBeHidden();
  await expect(universe.locator("#page-today .reading-line strong").first()).toContainText("persisted evidence");
  await universe.locator('[data-action="show-glows"]').click();
  await expect(universe.locator('[data-context-tab="glows"]')).toHaveAttribute("aria-selected", "true");
  await universe.locator("#today-input").fill(todayLine);
  await universe.locator('[data-send="today"]').click();
  await expect(universe.locator("#page-talk")).toHaveClass(/active/, { timeout: 20_000 });
  await expect(universe.locator("#talk-stream")).toContainText(todayLine);
  if (aiProvider === "openai") {
    const firstNurResponse = universe.locator("#talk-stream .talk-message.nur[data-event-id]").last();
    await expect(firstNurResponse.locator(".talk-meta")).toContainText("model-generated", { timeout: 20_000 });
    const firstNurResponseText = (await firstNurResponse.textContent())
      ?.replace(/NUR\s*·\s*model-generated/i, "")
      .trim() ?? "";
    expect(firstNurResponseText.length).toBeGreaterThan(0);
    await expect(firstNurResponse).not.toContainText(/AI is not connected|provider disabled/i);
  } else {
    const honestDisabledResponse = universe.locator("#talk-stream .talk-message.nur[data-nur-talk-error='true']").last();
    await expect(honestDisabledResponse.locator(".talk-meta"))
      .toHaveText("NUR · could not answer", { timeout: 20_000 });
    await expect(honestDisabledResponse)
      .toContainText("Live AI is not connected on this server, so NUR did not answer this turn.");
    await expect(universe.locator("#talk-stream .talk-message.nur[data-event-id]")).toHaveCount(0);
  }
  await universe.locator("#talk-input").fill(talkLine);
  await universe.locator('[data-send="talk"]').click();
  await expect(universe.locator("#talk-stream")).toContainText(talkLine, { timeout: 20_000 });
  await universe.locator('[data-thread-action="private"]').click();
  await expect(universe.locator("#toast")).toContainText(/remains private/i);
  await universe.locator('[data-thread-action="journal"]').click();
  await expect(universe.locator("#page-journal")).toHaveClass(/active/);
  await expect(universe.locator("#journal-input")).toHaveValue(talkLine);

  await universe.locator("[data-journal-prompt]").first().click();
  await expect(universe.locator("#journal-input")).not.toHaveValue("");
  await universe.locator("#journal-input").fill(journalLine);
  await universe.locator("#journal-save").click();
  await expect(universe.locator("#page-journal .journal-prompt")).toContainText(journalLine, { timeout: 20_000 });

  await universe.locator('[data-page="talk"]:visible').first().click();
  await universe.locator('[data-thread-action="plan"]').click();
  await expect(universe.locator("#page-plan")).toHaveClass(/active/, { timeout: 20_000 });
  await expect(universe.locator("#page-plan .panel-title").first()).toHaveText(planTitle);
  await universe.locator('[data-action="make-easier"]').click();
  await expect(universe.locator(".plan-step h3").first()).toContainText("Make it smaller:", { timeout: 20_000 });
  await universe.locator(".plan-check[data-plan-step-id]").first().click();
  await expect(universe.locator(".plan-step.done")).toHaveCount(1, { timeout: 20_000 });
  await expect(universe.locator("#nur-outcome-composer")).toBeVisible();
  await universe.locator("#nur-outcome-input").fill(outcomeLine);
  await universe.locator('[data-action="return-outcome"]').click();
  // Fresh-owner deterministic ledger:
  // check-in 2 + journal 4 + plan 4 + completed step 8 + returned outcome 15.
  // A connected model adds the separate 2-point meaningful-Talk award; the
  // honestly disabled provider does not fabricate that completion.
  const expectedGlow = aiProvider === "openai" ? 35 : 33;
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/glow/summary");
    return (await response.json()).balance as number;
  }), { timeout: 20_000 }).toBe(expectedGlow);
  await expect(universe.locator("#page-today .today-grid > aside .panel-title")).toContainText("Glow Points");

  await universe.locator('[data-page="systems"]:visible').first().click();
  await universe.locator('[data-world-tab="map"]').click();
  await expect(page).toHaveURL(/\/universe\/map$/);
  const mapRoot = universe.locator("#nur-map-root");
  await expect(mapRoot).toBeVisible({ timeout: 20_000 });
  await expect(mapRoot).toHaveAttribute("data-map-loaded", "true", { timeout: 20_000 });
  await expect(mapRoot.locator(".nur-map-nav")).toContainText("Systems");
  await expect.poll(() => mapRoot.locator(".nur-map-node").count()).toBeGreaterThan(0);
  await universe.locator('[data-world-tab="orbits"]').click();
  await expect(page).toHaveURL(/\/universe\/orbits$/);
  const orbitRoot = universe.locator("#nur-orbit-root");
  await expect(orbitRoot).toBeVisible({ timeout: 20_000 });
  await expect(orbitRoot.locator(".nur-orbit-title")).toHaveText("Orbit");
  await expect(orbitRoot.locator(".nur-orbit-subtitle")).toHaveText("People, circles and relational gravity");
  await universe.locator('[data-world-tab="timeline"]').click();
  await expect(page).toHaveURL(/\/universe\/timeline$/);
  const timelineRoot = universe.locator("#nur-timeline-root");
  await expect(timelineRoot).toBeVisible({ timeout: 20_000 });
  await expect(timelineRoot).toHaveAttribute("data-timeline-loaded", "true", { timeout: 20_000 });
  await expect(timelineRoot).toContainText(outcomeLine);
  await universe.locator('[data-world-tab="insights"]').click();
  await expect(page).toHaveURL(/\/universe\/insights$/);
  const insightsRoot = universe.locator("#nur-insights-root");
  await expect(insightsRoot).toBeVisible();
  await expect(insightsRoot).toHaveAttribute("data-v197-native-adjunct", "true");
  await expect(insightsRoot).toContainText("Candidate claims");
  // Review mutations belong to the dedicated Candidate Insights route; the
  // aggregate Insights surface must not duplicate or invent owner controls.
  await expect(universe.locator("#nur-v197-insight-controls")).toHaveCount(0);
  await expect(universe.locator("#toast")).not.toHaveClass(/show/, { timeout: 7_000 });
  await shot(page, "04-v197-real-insights-lens");

  await universe.locator("#scope-open").click();
  await expect(universe.locator("#nur-v197-locale")).toBeVisible();
  await universe.locator("#nur-v197-locale").selectOption("ko");
  await universe.locator("#nur-v197-language-save").click();
  await expect(universe.locator("html")).toHaveAttribute("lang", "ko");
  await expect(universe.locator('[data-page="today"] .clean-nav-title')).toHaveText("오늘");
  await shot(page, "05-v197-korean-language");

  await universe.locator("#nur-v197-locale").selectOption("ur");
  await universe.locator("#nur-v197-writing-preference").selectOption("roman");
  await universe.locator("#nur-v197-language-save").click();
  await expect(universe.locator("html")).toHaveAttribute("lang", "ur");
  await expect(universe.locator("html")).toHaveAttribute("dir", "ltr");
  await expect(universe.locator("#talk-input")).toHaveAttribute("placeholder", "Seedha bolo...");
  await expect(universe.locator('[data-world-tab="map"]')).toHaveText(/Naqsha$/);
  await universe.locator('#scope-modal .scope-option[data-scope="Private"]').click();
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/profile/preferences");
    return (await response.json()).default_boundary as string;
  })).toBe("PRIVATE_ORBIT");
  await shot(page, "06-v197-roman-urdu-ltr");
});

test("Track A persists across a fresh session and keeps the premium V197 map clear at 1440", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The persisted continuation and laptop geometry proof run once in desktop Chromium.");
  test.setTimeout(60_000);
  const { email, password, todayLine, talkLine, journalLine, planTitle, extraSystem } = scenario;

  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill(email);
  await entry.locator("#f4-signin-password").fill(password);
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(entry.locator("#nur-v197-auth-wait")).toBeVisible();
  await expect(entry.locator("#nur-v197-auth-wait")).toContainText("NUR is opening your Orbit");
  await expect(page).toHaveURL(/\/today$/);
  const refreshed = page.frameLocator("#nur-universe-stage");
  await expect(refreshed.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  await expect(refreshed.locator("html")).toHaveAttribute("lang", "ur");
  await expect(refreshed.locator("html")).toHaveAttribute("dir", "ltr");
  await refreshed.locator('[data-page="journal"]:visible').first().click();
  await expect(refreshed.locator("#page-journal .journal-prompt")).toContainText(journalLine);
  await refreshed.locator('[data-page="plan"]:visible').first().click();
  await expect(refreshed.locator("#page-plan .panel-title").first()).toHaveText(planTitle);
  await refreshed.locator('[data-page="talk"]:visible').first().click();
  await expect(refreshed.locator("#talk-stream")).toContainText(todayLine);
  await refreshed.locator('[data-page="today"]:visible').first().click();
  await expect(refreshed.locator("#page-today .today-grid > aside .panel-title")).toContainText("Glow Points");
  await shot(page, "07-v197-persisted-after-refresh");

  const persisted = await page.evaluate(async () => {
    const [glow, plans, journal, state] = await Promise.all([
      fetch("/api/v1/glow/summary").then(response => response.json()),
      fetch("/api/v1/plans").then(response => response.json()),
      fetch("/api/v1/journal").then(response => response.json()),
      fetch("/api/v1/orbits/current-state").then(response => response.json()),
    ]);
    return { glow, plans, journal, state };
  });
  expect(persisted.glow.balance).toBeGreaterThanOrEqual(31);
  expect(persisted.plans[0].title).toBe(planTitle);
  expect(persisted.journal[0].body).toBe(journalLine);
  expect(persisted.state.active_systems).toBe(6);
  expect(persisted.state.outcomes_returned).toBe(1);

  await page.setViewportSize({ width: 1600, height: 900 });
  await refreshed.locator('[data-page="systems"]:visible').first().click();
  await expect(refreshed.locator("#universe-search, #deep-research-button, #universe-research")).toHaveCount(0);
  await expect(refreshed.locator("#universe-community")).toBeVisible();
  await expect(refreshed.locator("#universe-community")).toContainText(/owner|local|persisted/i);
  await expect(refreshed.locator(".expert-card")).toHaveCount(0);
  await refreshed.locator('[data-action="add-system"]').click();
  await expect(refreshed.locator("#nur-v197-system-create")).toBeVisible();
  await refreshed.locator("#nur-v197-system-title").fill(extraSystem);
  await refreshed.locator('[data-action="system-create-submit"]').click();
  await expect(refreshed.locator("#toast")).toContainText("System persisted", { timeout: 20_000 });
  await expect.poll(async () => page.evaluate(async title => {
    const response = await fetch("/api/v1/orbits");
    const orbits = await response.json() as Array<{ title: string }>;
    return orbits.some(orbit => orbit.title === title);
  }, extraSystem)).toBe(true);
  await expect(refreshed.locator(".universe-system-node:visible")).toHaveCount(6);

  await refreshed.locator('[data-page="talk"]:visible').first().click();
  const balanceBeforeReplay = await page.evaluate(async () => {
    const response = await fetch("/api/v1/glow/summary");
    return (await response.json()).balance as number;
  });
  await refreshed.locator('[data-thread-action="glow"]').click();
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/glow/summary");
    return (await response.json()).balance as number;
  })).toBeGreaterThanOrEqual(balanceBeforeReplay);
  const balanceAfterFirstGlow = await page.evaluate(async () => {
    const response = await fetch("/api/v1/glow/summary");
    return (await response.json()).balance as number;
  });
  expect(balanceAfterFirstGlow).toBeLessThanOrEqual(balanceBeforeReplay + 2);
  await refreshed.locator('[data-thread-action="glow"]').click();
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/glow/summary");
    return (await response.json()).balance as number;
  })).toBe(balanceAfterFirstGlow);
  await refreshed.locator('[data-thread-action="plan"]').click();
  await expect(refreshed.locator("#page-plan")).toHaveClass(/active/, { timeout: 20_000 });
  await expect(refreshed.locator("#page-plan .panel-title").first()).toHaveText(talkLine);

  await page.setViewportSize({ width: 1440, height: 900 });
  await refreshed.locator('[data-page="systems"]:visible').first().click();
  await expect(refreshed.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  await expect(refreshed.locator(".universe-system-node:visible")).toHaveCount(6);
  expect(await criticalMapOverlaps(page)).toEqual([]);
  const starGeometry = await masterStarClearance(page);
  expect(starGeometry.creationLabelOwned).toBe(true);
  expect(starGeometry.centerDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.wordmarkCenterDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.subtitleCenterDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.panelCenterDelta).toBeLessThanOrEqual(1);
  expect(starGeometry.panelScrollLeft).toBe(0);
  expect(starGeometry.subtitleOwnedByTitle).toBe(true);
  expect(starGeometry.wordTopClearance).toBeGreaterThanOrEqual(10);
  expect(starGeometry.wordToSubtitleGap).toBeGreaterThanOrEqual(0);
  expect(starGeometry.clippedLabels).toEqual([]);
  await expect(refreshed.locator(".nur-v197-stable-wordmark")).toHaveText("NUR");
  await refreshed.locator(".universe-map-panel").scrollIntoViewIfNeeded();
  await expect(refreshed.locator("#toast")).not.toHaveClass(/show/, { timeout: 7_000 });
  await shot(page, "08-v197-overlap-free-map-1440");
});
