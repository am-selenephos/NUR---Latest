/**
 * The transcript and the journal draft must scroll inside themselves, and the
 * page must not scroll at all.
 *
 * Canonical already builds the transcript correctly
 * (`.talk-stream{flex:1;min-height:0;overflow:auto}`); the defect was
 * `.talk-chamber{min-height:calc(100dvh - 158px)}`, which ignores the topbar,
 * the page heading and the grid margin, so the chamber came out taller than the
 * space it sits in. The offsets below were derived from measurement — the
 * composer's own bottom edge at 800px and at 1080px — not guessed.
 */
import { expect, test, type Page } from "@playwright/test";
async function signIn(page: Page) {
  const e = page.frameLocator("#nur-entry-stage");
  await e.locator("body").evaluate(() => (window as unknown as { nurShowFront?: () => void }).nurShowFront?.());
  await e.locator("#f4-signin").click();
  await e.locator("#f4-signin-email").fill("owner@nur.app");
  await e.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await e.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 25_000 });
}
test("chatboxes scroll inside themselves and the page does not", async ({ page }) => {
  test.setTimeout(240_000);
  const errors: string[] = [];
  page.on("pageerror", e => errors.push(e.message));
  await page.setViewportSize({ width: 1440, height: 800 });
  await page.goto("/");
  await page.waitForTimeout(1500);
  await signIn(page);

  await page.goto("/talk"); await page.waitForTimeout(2500);
  const talk = await page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
    const stream = document.querySelector(".talk-stream") as HTMLElement;
    for (let i = 0; i < 40; i++) {
      const r = document.createElement("div");
      r.className = "talk-message nur zz"; r.textContent = `probe ${i}`; stream.append(r);
    }
    const vp = document.querySelector(".nur-viewport") as HTMLElement;
    const comp = document.querySelector(".talk-composer") as HTMLElement;
    const out = {
      streamScrolls: stream.scrollHeight > stream.clientHeight + 4,
      streamH: Math.round(stream.clientHeight),
      // overflow:hidden still leaves scrollHeight > clientHeight, so measure the
      // computed overflow and whether a scrollbar is actually laid out.
      viewportOverflowY: getComputedStyle(vp).overflowY,
      viewportHasScrollbar: vp.offsetWidth - vp.clientWidth > 2,
      gridOverflowY: (() => { const g = document.querySelector("#page-talk .page-grid"); return g ? getComputedStyle(g).overflowY : null; })(),
      composerBottom: Math.round(comp.getBoundingClientRect().bottom),
      windowH: window.innerHeight,
      composerVisible: comp.getBoundingClientRect().bottom <= window.innerHeight + 2,
      field: Boolean(document.getElementById("nur-deep-starfield")),
    };
    stream.querySelectorAll(".zz").forEach(n => n.remove());
    return out;
  });
  console.log("TALK " + JSON.stringify(talk));

  await page.goto("/journal"); await page.waitForTimeout(2500);
  const journal = await page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
    const f = document.getElementById("journal-input") as HTMLTextAreaElement;
    const orig = f.value;
    f.value = Array.from({ length: 90 }, (_, i) => `line ${i}`).join("\n");
    f.dispatchEvent(new Event("input", { bubbles: true }));
    const vp = document.querySelector(".nur-viewport") as HTMLElement;
    const tools = document.querySelector(".journal-tools") as HTMLElement | null;
    const out = {
      fieldScrolls: f.scrollHeight > f.clientHeight + 4,
      fieldH: Math.round(f.clientHeight),
      viewportOverflowY: getComputedStyle(vp).overflowY,
      viewportHasScrollbar: vp.offsetWidth - vp.clientWidth > 2,
      toolsVisible: tools ? tools.getBoundingClientRect().bottom <= window.innerHeight + 2 : null,
    };
    f.value = orig; f.dispatchEvent(new Event("input", { bubbles: true }));
    return out;
  });
  console.log("JOURNAL " + JSON.stringify(journal));
  console.log("ERRORS " + errors.length);

  expect(talk.field).toBe(false);
  expect(talk.streamScrolls).toBe(true);
  expect(talk.viewportOverflowY).toBe("hidden");
  expect(talk.composerVisible).toBe(true);
  expect(journal.fieldScrolls).toBe(true);
  expect(journal.viewportOverflowY).toBe("hidden");

  // The heights are viewport-relative, so prove they hold at a taller window too.
  await page.setViewportSize({ width: 1920, height: 1080 });
  await page.goto("/talk");
  await page.waitForTimeout(2500);
  const tall = await page.frameLocator("#nur-universe-stage").locator("body").evaluate(() => {
    const stream = document.querySelector(".talk-stream") as HTMLElement;
    const comp = document.querySelector(".talk-composer") as HTMLElement;
    return {
      streamH: Math.round(stream.clientHeight),
      composerBottom: Math.round(comp.getBoundingClientRect().bottom),
      windowH: window.innerHeight,
      streamOverflow: getComputedStyle(stream).overflowY,
    };
  });
  console.log("TALL " + JSON.stringify(tall));
  expect(tall.composerBottom).toBeLessThanOrEqual(tall.windowH + 2);
  expect(tall.streamH).toBeGreaterThan(400);
  expect(tall.streamOverflow).toBe("auto");
});
