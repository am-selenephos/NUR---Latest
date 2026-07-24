import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

import { chromium } from "@playwright/test";

const baseURL = process.env.WEB_ORIGIN || "http://localhost:5173";
const proofDir = resolve(process.env.NUR_OPENAI_PROOF_DIR || "proof/openai-live");
const ownerEmail = process.env.NUR_DEMO_OWNER_EMAIL || "owner@nur.app";
const ownerPassword = process.env.NUR_DEMO_OWNER_PASSWORD || "owner-demo-pass-123";
const stamp = `${Date.now()}-${process.pid}`;
const prompt = `OpenAI browser persistence smoke ${stamp}. Reply with one concise sentence about preserving evidence.`;

const browserEnvironment = Object.fromEntries(
  Object.entries(process.env).filter(([name]) => !/(KEY|TOKEN|SECRET|PASSWORD|DATABASE_URL|REDIS_URL)/i.test(name)),
);

await mkdir(proofDir, { recursive: true });
const browser = await chromium.launch({ headless: true, env: browserEnvironment });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
const page = await context.newPage();

try {
  await page.goto(baseURL, { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    window.nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill(ownerEmail);
  await entry.locator("#f4-signin-password").fill(ownerPassword);
  await entry.locator("#f4-signin-form button[type='submit']").click();

  let universe = page.frameLocator("#nur-universe-stage");
  await universe.locator(".nur-shell").waitFor({ state: "visible", timeout: 30_000 });
  await universe.locator('[data-page="talk"]:visible').first().click();
  await universe.locator("#page-talk").waitFor({ state: "visible" });
  const persistedResponses = universe.locator("#talk-stream .talk-message.nur[data-event-id]");
  const beforeResponses = await persistedResponses.count();
  await universe.locator("#talk-input").fill(prompt);
  await universe.locator('[data-send="talk"]').click();
  const transient = universe.locator(`#talk-stream [data-nur-transient]`);
  const persistedPrompt = universe.locator("#talk-stream").getByText(prompt, { exact: true });
  // A fast provider turn can persist and remove the transient before each
  // streaming checkpoint is observed, so every wait accepts either state.
  await Promise.race([
    transient.filter({ hasText: prompt }).waitFor({ timeout: 15_000 }),
    persistedPrompt.waitFor({ timeout: 15_000 }),
  ]);
  await page.waitForFunction(() => {
    const frame = document.querySelector("#nur-universe-stage");
    const doc = frame?.contentDocument;
    const target = doc?.querySelector("[data-nur-stream-text]");
    const value = target?.textContent?.trim() || "";
    if (value.length > 0 && value !== "Holding your context…") return true;
    return !doc?.querySelector("#talk-stream [data-nur-transient]")
      && Boolean(doc?.querySelector("#talk-stream .talk-message.nur[data-event-id]"));
  }, undefined, { timeout: 120_000 });
  await transient.first().waitFor({ state: "detached", timeout: 120_000 });
  await universe.locator("#talk-stream").getByText(prompt, { exact: true }).waitFor({ timeout: 120_000 });
  await persistedResponses.nth(beforeResponses).waitFor({ timeout: 120_000 });

  // The persisted element keeps receiving streamed text for a moment after it appears,
  // so a single innerText read can capture a partial answer. Comparing that partial
  // string against the stored row then fails as `model_response_persisted: false` —
  // a false negative that made this smoke flaky about half the time. Wait for the text
  // to stop changing before treating it as the answer.
  const answer = persistedResponses.nth(beforeResponses);
  let response = "";
  for (let stable = 0, elapsed = 0; stable < 3 && elapsed < 120_000; elapsed += 250) {
    await page.waitForTimeout(250);
    const current = (await answer.innerText()).replace(/^NUR · model-generated\s*/i, "").trim();
    stable = current && current === response ? stable + 1 : 0;
    response = current;
  }
  if (!response || /not connected|disabled|not enabled/i.test(response)) {
    throw new Error("V197 Talk did not display a real provider response.");
  }

  // Match the stored row by its event id, not by comparing rendered text. The message
  // element renders the structured payload (next move, uncertainty) alongside the answer,
  // and whether those appear depends on the model's output — so text equality failed
  // intermittently even though persistence was correct.
  const answerEventId = await answer.getAttribute("data-event-id");
  const persistence = await page.evaluate(async ({ expectedPrompt, expectedResponse, expectedEventId }) => {
    const threadResponse = await fetch("/api/v1/cognition/talk-thread", { credentials: "include" });
    if (!threadResponse.ok) throw new Error(`talk-thread returned ${threadResponse.status}`);
    const rows = await threadResponse.json();
    // innerText normalizes whitespace relative to the stored text, so compare
    // with collapsed whitespace instead of raw equality.
    const collapse = value => String(value || "").replace(/\s+/g, " ").trim();
    const userTurn = [...rows].reverse().find(row => row.who === "user" && collapse(row.text) === collapse(expectedPrompt));
    const modelTurn = [...rows].reverse().find(row => String(row.id) === String(expectedEventId))
      ?? [...rows].reverse().find(row => row.who === "nur" && collapse(expectedResponse).includes(collapse(row.text)));
    const payload = modelTurn?.structured_payload || {};
    const output = payload.talk_output || {};
    const schemaKeys = [
      "direct_response",
      "observed",
      "inferred",
      "hypotheses",
      "uncertainty",
      "next_move",
      "memory_candidates",
      "source_refs",
    ];
    return {
      user_turn_persisted: Boolean(userTurn),
      model_response_persisted: Boolean(modelTurn),
      provider: payload.provider,
      provider_available: payload.provider_available,
      model_run_id_present: Boolean(payload.model_run_id),
      schema_valid: schemaKeys.every(key => Object.hasOwn(output, key)),
      source_refs_valid: payload.verification?.checks?.source_refs_available === true,
    };
  }, { expectedPrompt: prompt, expectedResponse: response, expectedEventId: answerEventId });

  if (
    !persistence.user_turn_persisted
    || !persistence.model_response_persisted
    || persistence.provider !== "openai"
    || persistence.provider_available !== true
    || !persistence.model_run_id_present
    || !persistence.schema_valid
    || !persistence.source_refs_valid
  ) {
    throw new Error(`Persisted OpenAI proof failed: ${JSON.stringify(persistence)}`);
  }

  await persistedResponses.last().scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(proofDir, "talk-openai-real-response.png"), fullPage: false });
  // The post-talk refresh cycle can close a just-opened modal, so retry the
  // open until the provider status is actually visible.
  const providerStatus = universe.locator("#nur-v197-provider-status");
  const providerConfigured = providerStatus.getByText("OPENAI_CONFIGURED · server-side only", { exact: true });
  let providerVisible = false;
  for (let attempt = 0; attempt < 4 && !providerVisible; attempt += 1) {
    const modalOpen = (await universe.locator("#scope-modal.open").count()) > 0;
    if (!modalOpen) await universe.locator("#scope-open").click({ timeout: 5_000 }).catch(() => {});
    providerVisible = await providerConfigured.waitFor({ timeout: 10_000 }).then(() => true, () => false);
  }
  if (!providerVisible) throw new Error("V197 settings did not show the OpenAI provider status.");
  await page.screenshot({ path: resolve(proofDir, "settings-openai-configured.png"), fullPage: false });

  await page.reload({ waitUntil: "load" });
  universe = page.frameLocator("#nur-universe-stage");
  await universe.locator(".nur-shell").waitFor({ state: "visible", timeout: 30_000 });
  await universe.locator('[data-page="talk"]:visible').first().click();
  await universe.locator("#talk-stream").getByText(prompt, { exact: true }).waitFor({ timeout: 30_000 });
  const persistedResponse = universe.locator("#talk-stream .talk-message.nur").filter({ hasText: response }).last();
  await persistedResponse.waitFor({ timeout: 30_000 });
  await persistedResponse.scrollIntoViewIfNeeded();
  await page.screenshot({ path: resolve(proofDir, "talk-openai-after-refresh.png"), fullPage: false });

  process.stdout.write(`${JSON.stringify({
    provider: "openai",
    schema_valid: true,
    source_refs_valid: true,
    model_run_persisted: true,
    model_response_persisted: true,
    ui_response_visible: true,
    response_visible_after_refresh: true,
    settings_openai_configured: true,
    browser_secret_environment_removed: true,
  })}\n`);
} finally {
  await browser.close();
}
