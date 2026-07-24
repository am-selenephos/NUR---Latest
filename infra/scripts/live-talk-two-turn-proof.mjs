// Canonical V197 /talk live proof: two exact-reply turns plus reload persistence.
// Prints a JSON verdict; writes screenshots under proof/live-talk-two-turn/.
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { chromium } from "@playwright/test";

const baseURL = process.env.WEB_ORIGIN || "http://localhost:5173";
const proofDir = resolve(process.env.NUR_LIVE_TALK_PROOF_DIR || "proof/live-talk-two-turn");
const ownerEmail = process.env.NUR_DEMO_OWNER_EMAIL || "owner@nur.app";
const ownerPassword = process.env.NUR_DEMO_OWNER_PASSWORD || "owner-demo-pass-123";

const TURNS = [
  { prompt: "Reply with exactly: NUR TALK LIVE ONE", expected: "NUR TALK LIVE ONE" },
  { prompt: "Reply with exactly: NUR TALK LIVE TWO", expected: "NUR TALK LIVE TWO" },
];

const browserEnvironment = Object.fromEntries(
  Object.entries(process.env).filter(([name]) => !/(KEY|TOKEN|SECRET|PASSWORD|DATABASE_URL|REDIS_URL)/i.test(name)),
);

await mkdir(proofDir, { recursive: true });
const browser = await chromium.launch({ headless: true, env: browserEnvironment });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

function universeFrame() {
  return page.frameLocator("#nur-universe-stage");
}

async function openTalk() {
  const universe = universeFrame();
  await universe.locator(".nur-shell").waitFor({ state: "visible", timeout: 30_000 });
  await universe.locator('[data-page="talk"]:visible').first().click();
  await universe.locator("#page-talk").waitFor({ state: "visible", timeout: 15_000 });
}

async function modelReplyText(messageLocator) {
  const raw = (await messageLocator.innerText()).replace(/^NUR · model-generated\s*/i, "").trim();
  return raw;
}

try {
  await page.goto(`${baseURL}/talk`, { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    window.nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill(ownerEmail);
  await entry.locator("#f4-signin-password").fill(ownerPassword);
  await entry.locator("#f4-signin-form button[type='submit']").click();

  await openTalk();
  const universe = universeFrame();
  const persistedResponses = universe.locator("#talk-stream .talk-message.nur[data-event-id]");

  const turnResults = [];
  for (const turn of TURNS) {
    const before = await persistedResponses.count();
    await universe.locator("#talk-input").fill(turn.prompt);
    await universe.locator('[data-send="talk"]').click();
    await universe.locator("#talk-stream").getByText(turn.prompt, { exact: true }).last().waitFor({ timeout: 120_000 });
    await persistedResponses.nth(before).waitFor({ timeout: 120_000 });
    const reply = await modelReplyText(persistedResponses.last());
    turnResults.push({
      prompt: turn.prompt,
      expected: turn.expected,
      actual: reply,
      exact_match: reply === turn.expected,
    });
  }

  await persistedResponses.last().scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(proofDir, "talk-two-turns-live.png"), fullPage: false });

  await page.reload({ waitUntil: "load" });
  await openTalk();
  const afterReload = universeFrame();
  const stream = afterReload.locator("#talk-stream");
  const persistence = { user_turns: [], model_turns: [] };
  for (const turn of TURNS) {
    const userVisible = await stream
      .getByText(turn.prompt, { exact: true })
      .first()
      .isVisible({ timeout: 30_000 })
      .catch(() => false);
    persistence.user_turns.push({ prompt: turn.prompt, visible_after_reload: userVisible });
    const modelMessages = afterReload.locator("#talk-stream .talk-message.nur").filter({ hasText: turn.expected });
    const modelVisible = (await modelMessages.count()) > 0;
    persistence.model_turns.push({ expected: turn.expected, visible_after_reload: modelVisible });
  }
  await afterReload.locator("#talk-stream .talk-message").last().scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(proofDir, "talk-two-turns-after-reload.png"), fullPage: false });

  const pass =
    turnResults.every((turn) => turn.exact_match) &&
    persistence.user_turns.every((turn) => turn.visible_after_reload) &&
    persistence.model_turns.every((turn) => turn.visible_after_reload);

  process.stdout.write(`${JSON.stringify({ verdict: pass ? "LIVE_TALK_PASS" : "LIVE_TALK_HOLD", turns: turnResults, persistence }, null, 2)}\n`);
  if (!pass) process.exitCode = 1;
} finally {
  await browser.close();
}
