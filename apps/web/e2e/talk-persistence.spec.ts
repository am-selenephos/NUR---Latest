import { expect, test, type Page, type Route } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

async function authenticate(page: Page) {
  const state = await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "talk-persistence-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "talk-persistence-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  return state;
}

async function stream(route: Route, events: Array<{ id: number; event: string; data: unknown }>) {
  await route.fulfill({
    status: 200,
    headers: {
      "cache-control": "no-cache",
      "content-type": "text/event-stream; charset=utf-8",
    },
    body: events.map(row => (
      `id: ${row.id}\nevent: ${row.event}\ndata: ${JSON.stringify(row.data)}\n\n`
    )).join(""),
  });
}

test("Talk persists user and model turns through the current SSE bridge and API reload", async ({ page }) => {
  const state = await authenticate(page);
  await page.route("**/api/v1/cognition/talk/stream", async route => {
    const body = JSON.parse(route.request().postData() || "{}") as { message: string };
    const createdAt = new Date().toISOString();
    const result = {
      turn_event_id: "turn-persisted-new",
      response_event_id: "response-persisted-new",
      model_run_id: "model-run-persisted-new",
      provider: "openai",
      provider_available: true,
      provider_reason: null,
      output: {
        direct_response: "The current SSE turn was persisted.",
        observed: ["The owner supplied one line."],
        inferred: [],
        hypotheses: [],
        uncertainty: [],
        next_move: "Return one observed outcome.",
        memory_candidates: [],
        source_refs: [],
      },
      evidence: { retrieval: [], withheld: [] },
      verification: { verdict: "PASS", checks: {} },
    };
    state.thread.push(
      { id: result.turn_event_id, who: "user", text: body.message, structured_payload: {}, created_at: createdAt },
      {
        id: result.response_event_id,
        who: "nur",
        text: result.output.direct_response,
        structured_payload: {
          provider_available: true,
          model_run_id: result.model_run_id,
          talk_output: result.output,
        },
        created_at: createdAt,
      },
    );
    await stream(route, [
      { id: 1, event: "stream.open", data: { request_id: body.message } },
      { id: 2, event: "talk.accepted", data: { model_run_id: result.model_run_id } },
      { id: 3, event: "response.text.delta", data: { delta: result.output.direct_response } },
      { id: 4, event: "talk.completed", data: { durable: true, result } },
    ]);
  });

  await page.goto("/talk");
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.getByText("Persist this already.", { exact: true })).toBeVisible();
  await expect(universe.getByText("Persisted answer.", { exact: true })).toBeVisible();

  await universe.locator("#talk-input").fill("Persist this new SSE line too.");
  await universe.getByRole("button", { name: "Send to NUR" }).click();
  await expect(universe.getByText("The current SSE turn was persisted.", { exact: true })).toBeVisible();

  await page.reload();
  await expect(universe.getByText("Persist this already.", { exact: true })).toBeVisible();
  await expect(universe.getByText("Persist this new SSE line too.", { exact: true })).toBeVisible();
  await expect(universe.locator(
    "#talk-stream .talk-message.nur[data-event-id='response-persisted-new']",
  )).toContainText("The current SSE turn was persisted.");
});

test("former Glow action remains absent and a persisted outcome is required", async ({ page }) => {
  const state = await authenticate(page);
  await page.goto("/plan");
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.getByText("Mark a Personal Glow")).toHaveCount(0);
  await expect(universe.locator("#nur-outcome-composer")).toBeHidden();

  const before = state.outcomePosts;
  await universe.locator(".plan-check[data-plan-step-id]").first().click();
  await expect(universe.locator("#nur-outcome-composer")).toBeVisible();
  expect(state.outcomePosts).toBe(before);

  await universe.locator("#nur-outcome-input").fill("The owner returned the observed outcome.");
  await universe.locator('[data-action="return-outcome"]').click();
  await expect.poll(() => state.outcomePosts).toBe(before + 1);
});
