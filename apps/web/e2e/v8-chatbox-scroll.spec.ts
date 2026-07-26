/**
 * Behavioural proof that the transcript and the journal draft scroll inside
 * themselves, and that nothing else moves.
 *
 * The previous version of this file asserted geometry only. Its central check,
 * `stream.scrollHeight > stream.clientHeight + 4`, stays true under
 * `overflow: hidden` — so it passed on an implementation where the content
 * could not be scrolled at all. Every assertion below drives a real gesture
 * (wheel, keyboard, touch drag) and then reads what actually moved.
 *
 * Counterexamples for each replaced assertion: docs/v9/TEST_ORACLE_AUDIT.csv.
 */
import { expect, test, type Page, type FrameLocator } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import path from "node:path";

const OUT = path.resolve(process.cwd(), "../../proof/v11-scroll-behaviour");

// Video of the gesture itself — a still frame cannot show whether the wheel
// moved the transcript or the page. Must be file-level: `test.use({ video })`
// inside a describe forces a new worker and Playwright rejects it.
test.use({ video: "on" });

const VIEWPORTS = [
  { label: "desktop", width: 1440, height: 900 },
  { label: "short-desktop", width: 1280, height: 640 },
  { label: "mobile", width: 390, height: 844 },
  // The visual viewport when a phone keyboard is open: same width, ~half height.
  { label: "mobile-keyboard", width: 390, height: 400 },
] as const;

interface SurfaceResult {
  viewport: string;
  surface: string;
  gesture: string;
  scrollerDelta: number;
  pageDelta: number;
  ancestorsThatMoved: string[];
  endReachable: boolean;
  actionHitTestable: boolean;
}

/**
 * The entry sheet occasionally swallows the first submit — the front has to be
 * shown before the form exists, and that transition races the click. Retried
 * rather than left flaky, so a sign-in stumble can never be mistaken for a
 * scroll failure.
 */
async function signIn(page: Page): Promise<void> {
  const stage = page.locator("#nur-universe-stage");
  for (let attempt = 1; attempt <= 3; attempt += 1) {
    const entry = page.frameLocator("#nur-entry-stage");
    try {
      await entry.locator("body").evaluate(() =>
        (window as unknown as { nurShowFront?: () => void }).nurShowFront?.());
      await entry.locator("#f4-signin").click({ timeout: 10_000 });
      await entry.locator("#f4-signin-email").fill("owner@nur.app");
      await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
      await entry.locator("#f4-signin-form button[type='submit']").click();
      await expect(stage).toHaveClass(/is-visible/, { timeout: 25_000 });
      return;
    } catch (error) {
      if (attempt === 3) throw error;
      await page.goto("/");
      await page.waitForTimeout(2000);
    }
  }
}

/**
 * scrollTop of the document, the body, and every ancestor of `selector` up to
 * the root. A scroll that escapes the intended scroller shows up here as a
 * non-zero delta on some other node — which is exactly the bug the founder
 * reported and the old oracle could not see.
 */
const SCROLL_STATE = (_node: Element, sel: string) => {
  const out: Record<string, number> = {
    "#document": document.documentElement.scrollTop,
    "body": document.body.scrollTop,
  };
  const target = document.querySelector(sel);
  out["target"] = (target as HTMLElement | null)?.scrollTop ?? -1;
  let node = target?.parentElement ?? null;
  let depth = 0;
  while (node && depth < 10) {
    const id = node.id
      ? `#${node.id}`
      : `.${String(node.className || node.tagName).trim().split(/\s+/)[0]}`;
    out[`${depth}:${id}`] = node.scrollTop;
    node = node.parentElement;
    depth += 1;
  }
  return out;
};

/** True only if the element's own centre point hit-tests back to itself. */
const HIT_TEST = (_node: Element, sel: string) => {
  const el = document.querySelector<HTMLElement>(sel);
  if (!el) return false;
  const style = getComputedStyle(el);
  if (style.visibility === "hidden" || style.display === "none" || Number(style.opacity) < 0.1) {
    return false;
  }
  const box = el.getBoundingClientRect();
  if (box.width < 1 || box.height < 1) return false;
  // Off-screen fails: the founder's complaint was the composer falling below
  // the fold, which a bounding-box check alone reports as present.
  if (box.bottom > window.innerHeight + 1 || box.top < -1) return false;
  const hit = document.elementFromPoint(box.left + box.width / 2, box.top + box.height / 2);
  return Boolean(hit && (hit === el || el.contains(hit) || hit.contains(el)));
};

function movedKeys(
  before: Record<string, number>,
  after: Record<string, number>,
  ignore: RegExp,
): string[] {
  return Object.keys(before)
    .filter(key => !ignore.test(key))
    .filter(key => Math.abs((after[key] ?? 0) - (before[key] ?? 0)) > 2);
}

async function talkSurface(
  page: Page,
  universe: FrameLocator,
  vp: string,
  touch: boolean,
): Promise<SurfaceResult> {
  const body = universe.locator("body");
  await body.evaluate(() => {
    const stream = document.querySelector(".talk-stream");
    if (!stream) throw new Error(".talk-stream not found");
    for (let index = 0; index < 60; index += 1) {
      const row = document.createElement("div");
      row.className = "talk-message nur nur-scroll-probe";
      row.textContent = `probe line ${index} — the end of the transcript must be reachable`;
      stream.append(row);
    }
    (stream as HTMLElement).scrollTop = 0;
  });
  await page.waitForTimeout(250);

  const before = await body.evaluate(SCROLL_STATE, ".talk-stream");

  // A real wheel gesture over the transcript. Not a scrollTop assignment.
  const box = await universe.locator(".talk-stream").boundingBox();
  if (!box) throw new Error(".talk-stream has no box");
  const midX = box.x + box.width / 2;
  const midY = box.y + box.height / 2;
  await page.mouse.move(midX, midY);
  for (let step = 0; step < 8; step += 1) {
    await page.mouse.wheel(0, 220);
    await page.waitForTimeout(40);
  }
  await page.waitForTimeout(350);

  // A real touch drag as well, so the phone viewports are proven with the
  // gesture a phone actually sends rather than with a wheel it never sends.
  // `Input.synthesizeScrollGesture` drives the compositor the same way a finger
  // does; a hand-dispatched `TouchEvent` would not scroll anything and would be
  // exactly the kind of oracle this rewrite exists to remove.
  if (touch) {
    // The gesture origin must sit inside the real window. When the transcript
    // overflows — which is precisely the broken case — its centre can be far
    // below the fold, and CDP rejects an out-of-bounds position outright.
    const size = page.viewportSize() ?? { width: 390, height: 800 };
    const clamp = (value: number, max: number) =>
      Math.round(Math.min(Math.max(value, 8), max - 8));
    const cdp = await page.context().newCDPSession(page);
    await cdp.send("Input.synthesizeScrollGesture", {
      x: clamp(midX, size.width),
      y: clamp(midY, size.height),
      yDistance: -320,
      gestureSourceType: "touch",
      speed: 1200,
    });
    await cdp.detach();
    await page.waitForTimeout(400);
  }

  const after = await body.evaluate(SCROLL_STATE, ".talk-stream");
  const scrollerDelta = (after["target"] ?? 0) - (before["target"] ?? 0);

  // Keep wheeling until the scroller stops moving, then ask whether the last
  // message is genuinely inside the visible box. Assigning `scrollTop` here
  // would prove nothing: `overflow: hidden` is still programmatically
  // scrollable, which is the very trap this rewrite exists to close.
  let previous = -1;
  for (let attempt = 0; attempt < 40; attempt += 1) {
    const now = await body.evaluate(() =>
      document.querySelector<HTMLElement>(".talk-stream")!.scrollTop);
    if (now === previous) break;
    previous = now;
    await page.mouse.wheel(0, 400);
    await page.waitForTimeout(60);
  }
  const endReachable = await body.evaluate(() => {
    const stream = document.querySelector<HTMLElement>(".talk-stream")!;
    const rows = stream.querySelectorAll<HTMLElement>(".nur-scroll-probe");
    const last = rows[rows.length - 1];
    if (!last) return false;
    const sBox = stream.getBoundingClientRect();
    const lBox = last.getBoundingClientRect();
    // Two claims: the gesture reached the true bottom, and the end of the last
    // message is on screen. Requiring the *whole* last row to fit would be a bad
    // check, not a strict one — on a short phone viewport a single wrapped
    // message is taller than the scroller, so no implementation could pass it.
    const atBottom = stream.scrollTop >= stream.scrollHeight - stream.clientHeight - 2;
    return atBottom && lBox.bottom <= sBox.bottom + 6 && lBox.bottom > sBox.top;
  });

  const composerSelector = ".talk-composer";
  const actionHitTestable = await body.evaluate(HIT_TEST, composerSelector);

  return {
    viewport: vp,
    surface: "talk",
    gesture: touch ? "mouse wheel ×8 + touch drag" : "mouse wheel ×8",
    scrollerDelta: Math.round(scrollerDelta),
    pageDelta: Math.round(Math.max(
      Math.abs((after["#document"] ?? 0) - (before["#document"] ?? 0)),
      Math.abs((after["body"] ?? 0) - (before["body"] ?? 0)),
    )),
    ancestorsThatMoved: movedKeys(before, after, /^target$|#document|^body$/),
    endReachable,
    actionHitTestable,
  };
}

async function journalSurface(
  page: Page,
  universe: FrameLocator,
  vp: string,
): Promise<SurfaceResult> {
  const body = universe.locator("body");
  await body.evaluate(() => {
    const field = document.getElementById("journal-input") as HTMLTextAreaElement | null;
    if (!field) throw new Error("#journal-input not found");
    field.value = Array.from(
      { length: 160 },
      (_, i) => `draft line ${i} — the end of the draft must be reachable`,
    ).join("\n");
    field.dispatchEvent(new Event("input", { bubbles: true }));
    field.scrollTop = 0;
  });
  await page.waitForTimeout(250);

  const before = await body.evaluate(SCROLL_STATE, "#journal-input");

  // Keyboard, not a programmatic scroll: caret to the end of the draft.
  await universe.locator("#journal-input").click();
  await page.keyboard.press("Control+End");
  await page.waitForTimeout(350);

  const after = await body.evaluate(SCROLL_STATE, "#journal-input");

  // The keyboard scrolls the *caret* into view, which stops one bottom-padding
  // short of the true scroll bottom (measured: 6433 of 6456, a 23px gap that is
  // exactly `padding-bottom`). The last line is on screen at that point, so the
  // tolerance is derived from the field's own padding and line box rather than
  // from a guessed constant.
  const keyboardState = await body.evaluate(() => {
    const field = document.getElementById("journal-input") as HTMLTextAreaElement;
    const style = getComputedStyle(field);
    const slack = parseFloat(style.paddingBottom || "0") + parseFloat(style.lineHeight || "0");
    const maxScroll = field.scrollHeight - field.clientHeight;
    return {
      scrollTop: field.scrollTop,
      caretAtEnd: field.selectionEnd === field.value.length,
      lastLineOnScreen: maxScroll > 0 && field.scrollTop >= maxScroll - slack,
    };
  });

  // And a wheel over the field must reach the true bottom.
  const fieldBox = await universe.locator("#journal-input").boundingBox();
  if (fieldBox) {
    await page.mouse.move(fieldBox.x + fieldBox.width / 2, fieldBox.y + fieldBox.height / 2);
    for (let step = 0; step < 30; step += 1) {
      await page.mouse.wheel(0, 500);
      await page.waitForTimeout(25);
    }
  }
  const bottomReached = await body.evaluate(() => {
    const field = document.getElementById("journal-input") as HTMLTextAreaElement;
    return field.scrollTop >= field.scrollHeight - field.clientHeight - 2;
  });
  // Containment is judged across both gestures, not just the keyboard one.
  const afterWheel = await body.evaluate(SCROLL_STATE, "#journal-input");

  const fieldState = {
    scrollTop: keyboardState.scrollTop,
    atEnd: keyboardState.caretAtEnd && keyboardState.lastLineOnScreen && bottomReached,
  };

  const actionHitTestable = await body.evaluate(HIT_TEST, ".journal-tools");

  return {
    viewport: vp,
    surface: "journal",
    gesture: "click + Control+End + wheel ×30",
    scrollerDelta: Math.round(fieldState.scrollTop),
    pageDelta: Math.round(Math.max(
      Math.abs((after["#document"] ?? 0) - (before["#document"] ?? 0)),
      Math.abs((after["body"] ?? 0) - (before["body"] ?? 0)),
      Math.abs((afterWheel["#document"] ?? 0) - (before["#document"] ?? 0)),
      Math.abs((afterWheel["body"] ?? 0) - (before["body"] ?? 0)),
    )),
    ancestorsThatMoved: [
      ...new Set([
        ...movedKeys(before, after, /^target$|#document|^body$/),
        ...movedKeys(before, afterWheel, /^target$|#document|^body$/),
      ]),
    ],
    endReachable: fieldState.atEnd,
    actionHitTestable,
  };
}

test.describe("chatbox scroll behaviour", () => {
  test.skip(({ browserName }) => browserName !== "chromium", "Gesture proof runs on Chromium.");

  for (const vp of VIEWPORTS) {
    test(`Talk and Journal scroll internally at ${vp.label}`, async ({ page }, testInfo) => {
      test.setTimeout(300_000);
      await mkdir(OUT, { recursive: true });
      const errors: string[] = [];
      page.on("pageerror", error => errors.push(error.message));

      await page.setViewportSize({ width: vp.width, height: vp.height });
      await page.goto("/");
      await page.waitForTimeout(1500);
      await signIn(page);
      const universe = page.frameLocator("#nur-universe-stage");

      await page.goto("/talk");
      await page.waitForTimeout(2500);
      const talk = await talkSurface(page, universe, vp.label, vp.width < 900);
      await page.screenshot({ path: path.join(OUT, `talk-${vp.label}.png`), fullPage: false });

      await page.goto("/journal");
      await page.waitForTimeout(2500);
      const journal = await journalSurface(page, universe, vp.label);
      await page.screenshot({ path: path.join(OUT, `journal-${vp.label}.png`), fullPage: false });

      await writeFile(
        path.join(OUT, `readings-${vp.label}.json`),
        `${JSON.stringify({ commit: process.env.NUR_PROOF_COMMIT ?? null, talk, journal, errors }, null, 2)}\n`,
        "utf8",
      );
      await testInfo.attach(`readings-${vp.label}`, {
        body: JSON.stringify({ talk, journal }, null, 2),
        contentType: "application/json",
      });
      console.log(`TALK ${vp.label} ${JSON.stringify(talk)}`);
      console.log(`JOURNAL ${vp.label} ${JSON.stringify(journal)}`);

      // 1. The gesture must move the intended scroller.
      expect(talk.scrollerDelta, `${vp.label} talk: wheel must scroll the transcript`)
        .toBeGreaterThan(40);
      expect(journal.scrollerDelta, `${vp.label} journal: Control+End must scroll the draft`)
        .toBeGreaterThan(40);

      // 2. Nothing outside it may move.
      expect(talk.pageDelta, `${vp.label} talk: the page must not scroll`).toBeLessThanOrEqual(2);
      expect(talk.ancestorsThatMoved, `${vp.label} talk: no ancestor may scroll`).toEqual([]);
      expect(journal.pageDelta, `${vp.label} journal: the page must not scroll`).toBeLessThanOrEqual(2);
      expect(journal.ancestorsThatMoved, `${vp.label} journal: no ancestor may scroll`).toEqual([]);

      // 3. The end of the content must be reachable.
      expect(talk.endReachable, `${vp.label} talk: the last message must be reachable`).toBe(true);
      expect(journal.endReachable, `${vp.label} journal: the last line must be reachable`).toBe(true);

      // 4. The composer and the tools must stay usable, not merely positioned.
      expect(talk.actionHitTestable, `${vp.label} talk: composer must be hit-testable`).toBe(true);
      expect(journal.actionHitTestable, `${vp.label} journal: tools must be hit-testable`).toBe(true);

      expect(errors, `${vp.label}: no page errors`).toEqual([]);
    });
  }
});
