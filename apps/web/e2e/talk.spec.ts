import { expect, test, type FrameLocator, type Page, type Route } from "@playwright/test";

import { installBundledFontPolicy } from "./helpers/nurMocks";

const V197_BRIDGE_READY_TIMEOUT_MS = 12_000;

async function readyUniverse(page: Page, pageSelector: string): Promise<FrameLocator> {
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, {
    timeout: V197_BRIDGE_READY_TIMEOUT_MS,
  });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator(pageSelector)).toBeVisible();
  return universe;
}

const user = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "selene@nurapp.dev",
  email_verified: true,
  profile: { chosen_name: "Selene", timezone: null, locale: "en", sound_enabled: false, reduced_effects: true },
  orbit: { id: "99999999-9999-9999-9999-999999999999", current_arrival_state: null, active_focus_area: null },
};

const orbit = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "Ambition",
  kind: "PROJECT",
  description: "Build without noise",
  status: "ACTIVE",
  created_at: new Date().toISOString(),
};

type ThreadRow = {
  id: string;
  who: "user" | "nur";
  text: string;
  structured_payload: Record<string, unknown>;
  created_at: string;
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({
    status,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function sse(route: Route, events: Array<{ id: number; event: string; data: unknown }>) {
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

async function installTalkMocks(page: Page, opts: { providerAvailable: boolean }) {
  await installBundledFontPolicy(page);
  const thread: ThreadRow[] = [];
  let lastTalkMode = "talk";
  let planCreated = false;
  let planStepDone = false;
  let correctionSaved = false;
  let outcomePosts = 0;

  await page.context().addCookies([{
    name: "nur_csrf",
    value: "readiness-talk-csrf",
    url: "http://localhost:4173",
    httpOnly: false,
    sameSite: "Lax",
  }]);
  await page.route("**/api/v1/auth/me", route => json(route, user));
  await page.route("**/api/v1/profile/preferences", route => json(route, {
    locale: "en",
    sound_enabled: false,
    reduced_effects: true,
    default_boundary: "PRIVATE_ORBIT",
    active_orbit_id: orbit.id,
    omega_enabled: true,
    writing_preference: "default",
    timezone: "UTC",
  }));
  await page.route("**/healthz", route => json(route, { status: "ok" }));
  await page.route("**/api/v1/universe/live", route => json(route, null));
  await page.route("**/api/v1/universe/map-summary", route => json(route, null));
  await page.route("**/api/v1/universe/orbits-summary", route => json(route, null));
  await page.route("**/api/v1/universe/timeline", route => json(route, null));
  await page.route("**/api/v1/map", route => json(route, null));
  await page.route("**/api/v1/glow/scoreboard", route => json(route, null));
  await page.route("**/api/v1/glow/summary", route => json(route, {
    balance: 0,
    lifetime_points: 0,
    today_points: 0,
    weekly_points: 0,
    level: 1,
    rank: "Orbit Seed",
    next_unlock: null,
    recent_transactions: [],
    streaks: [],
    achievements: [],
    daily_quest: {},
    weekly_mission: {},
  }));
  await page.route("**/api/v1/research/briefs", route => json(route, []));
  await page.route("**/api/v1/projects/summary", route => json(route, null));
  await page.route("**/api/v1/community/rooms", route => json(route, []));
  await page.route("**/api/v1/orbits/current-state", route => json(route, {
    active_systems: 1, outcomes_returned: outcomePosts, insights_evolving: 0,
    open_questions: 0, research_staged: 0, plans_active: 0, live_status: "owner_ledger",
  }));
  await page.route("**/api/v1/orbits", route => {
    if (route.request().method() === "GET") return json(route, [orbit]);
    return json(route, orbit, 201);
  });
  await page.route("**/api/v1/journal", route => json(route, []));
  await page.route("**/api/v1/plans", async route => {
    if (route.request().method() === "GET") return json(route, [{
      id: "plan-1",
      title: "Use this move",
      status: "ACTIVE",
      steps: [{
        id: "step-1",
        title: "Record what changed from Talk",
        body: null,
        position: 0,
        done: planStepDone,
        done_at: planStepDone ? new Date().toISOString() : null,
      }],
    }]);
    planCreated = true;
    return json(route, {
      id: "plan-1",
      title: "Use this move",
      status: "ACTIVE",
      steps: [{ id: "step-1", title: "Record what changed from Talk", body: null, position: 0, done: false, done_at: null }],
    }, 201);
  });
  await page.route("**/api/v1/plan-steps/step-1", route => {
    planStepDone = true;
    return json(route, {
      id: "step-1",
      title: "Record what changed from Talk",
      body: null,
      position: 0,
      done: true,
      done_at: new Date().toISOString(),
    });
  });
  await page.route("**/api/v1/outcomes", async route => {
    outcomePosts += 1;
    return json(route, { id: `outcome-${outcomePosts}` }, 201);
  });
  await page.route("**/api/v1/glow/rewards", route => json(route, {
    awarded_points: 0,
    balance: 0,
    lifetime_points: 0,
    idempotent_replay: true,
    streak: null,
    achievements_unlocked: [],
  }));
  await page.route("**/api/v1/universe/insights-summary", route => json(route, {
    provenance_label: "owner_ledger",
    counts: {
      claims: 1,
      dedicated_insights: 1,
      omega_claims: 0,
      open_contradictions: 0,
      predictions: 0,
      review_queue: 1,
      learning_proposals: 0,
    },
    dedicated_insights: [{
      record_kind: "DEDICATED_INSIGHT",
      id: "insight-1",
      title: "Source-faithful movement",
      claim_text: "The next move should stay grounded in owned evidence.",
      insight_type: "CROSS_DOMAIN_PATTERN",
      truth_status: "CANDIDATE",
      lifecycle_status: "SURFACED",
      epistemic_state: "PROVISIONAL",
      insight_version: 1,
      time_scale: "WEEKLY",
      source_domains: ["TALK", "DECISION"],
      source_diversity: 2,
      confidence: 0.72,
      evidence: [{ id: "relation-1" }],
      counter_evidence: [],
      alternative_explanations: ["The owner may choose a different pace."],
      what_nur_may_be_wrong_about: "The owner may choose a different pace.",
      suggested_action: "Write one visible owner-approved step.",
      provenance_label: "AGENTIC_INSIGHT_OWNER_LEDGER",
      detail_route: "/universe/insights/insight-1",
    }],
    omega_claims: [],
    claims: [{
      record_kind: "DEDICATED_INSIGHT",
      id: "insight-1",
      title: "Source-faithful movement",
      claim_text: "The next move should stay grounded in owned evidence.",
      insight_type: "CROSS_DOMAIN_PATTERN",
      truth_status: "CANDIDATE",
      lifecycle_status: "SURFACED",
      evidence: [{ id: "relation-1" }],
      what_nur_may_be_wrong_about: "The owner may choose a different pace.",
    }],
    contradictions: [],
    predictions: [],
    review_queue: [],
  }));
  await page.route("**/api/v1/insights?limit=80", route => json(route, [{
    id: "insight-1",
    orbit_id: user.orbit.id,
    insight_type: "CROSS_DOMAIN_PATTERN",
    title: "Source-faithful movement",
    claim: "The next move should stay grounded in owned evidence.",
    tone: "measured",
    confidence: 0.72,
    valence: "constructive",
    affected_system_slug: null,
    evidence: [{ id: "relation-1" }],
    counter_evidence: [],
    what_nur_may_be_wrong_about: "The owner may choose a different pace.",
    positive_interpretation: "A visible move can make return easier.",
    hard_interpretation: "Movement without evidence would be invented.",
    suggested_action: "Write one visible owner-approved step.",
    status: "CANDIDATE",
    correction: null,
    provenance_label: "AGENTIC_INSIGHT_OWNER_LEDGER",
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  }]));
  await page.route("**/api/v1/insights/insight-1", route => json(route, {
    id: "insight-1",
    title: "Source-faithful movement",
    claim: "The next move should stay grounded in owned evidence.",
    lifecycle_status: "SURFACED",
    epistemic_state: "PROVISIONAL",
    insight_version: 1,
    time_scale: "WEEKLY",
    source_domains: ["TALK", "DECISION"],
    source_diversity: 2,
    alternative_explanations: ["The owner may choose a different pace."],
    assumptions: [],
    contradictions: [],
    what_nur_may_be_wrong_about: "The owner may choose a different pace.",
    quality_dimensions: {},
    canonical_links: {
      timeline: "/universe/timeline",
      evidence: "/universe/insights/insight-1",
    },
  }));
  await page.route("**/api/v1/insights/insight-1/evidence", route => json(route, {
    insight_id: "insight-1",
    relations: [{
      id: "relation-1",
      source_kind: "COGNITIVE_EVENT",
      source_id: "44444444-4444-4444-4444-444444444444",
      source_domain: "TALK",
      relation: "SUPPORTS",
      provenance_label: "OWNER_WRITTEN",
      explicitness: "EXPLICIT",
      confidence: 1,
      evidence_summary: "The owner asked for source-faithful movement.",
      source_occurred_at: new Date().toISOString(),
      source_exists: true,
      canonical_route: "/talk",
    }],
  }));
  await page.route("**/api/v1/insights/insight-1/why-changed", route => json(route, {
    insight_id: "insight-1",
    changes: [],
    governance: "owner-governed",
  }));
  await page.route("**/api/v1/insights/insight-1/correct", route => {
    correctionSaved = true;
    return json(route, { id: "correction-1" }, 201);
  });
  await page.route("**/api/v1/cognition/talk-thread**", route => json(route, thread));
  await page.route("**/api/v1/cognition/talk/stream", async route => {
    const body = JSON.parse(route.request().postData() || "{}") as { message: string; mode?: string };
    lastTalkMode = body.mode ?? "talk";
    thread.push({
      id: `turn-${thread.length + 1}`,
      who: "user",
      text: body.message,
      structured_payload: {},
      created_at: new Date().toISOString(),
    });
    const output = opts.providerAvailable ? {
      direct_response: "You are asking for source-faithful movement.",
      observed: ["The current line asks for movement."],
      inferred: ["The next move should stay small."],
      hypotheses: ["If the move is visible, it will be easier to return to."],
      uncertainty: ["This is based only on the mocked owned source."],
      next_move: "Write one visible owner-approved step.",
      memory_candidates: [],
      source_refs: ["DECISION:33333333-3333-3333-3333-333333333333"],
    } : {
      direct_response: "I saved this turn, but live AI is disabled on this server.",
      observed: [],
      inferred: [],
      hypotheses: [],
      uncertainty: ["AI provider disabled."],
      next_move: "Keep one concrete next line.",
      memory_candidates: [],
      source_refs: [],
    };
    const response = {
      turn_event_id: "44444444-4444-4444-4444-444444444444",
      response_event_id: `55555555-5555-5555-5555-55555555555${thread.length}`,
      model_run_id: "66666666-6666-6666-6666-666666666666",
      provider: opts.providerAvailable ? "openai" : "disabled",
      provider_available: opts.providerAvailable,
      provider_reason: opts.providerAvailable ? null : "AI provider is disabled.",
      output,
      evidence: {
        retrieval: opts.providerAvailable ? [{
          kind: "DECISION",
          id: "33333333-3333-3333-3333-333333333333",
          excerpt: "The owner approved one visible step.",
          rank: 1,
        }] : [],
        withheld: [],
      },
      verification: { verdict: opts.providerAvailable ? "PASS" : "WARN", checks: {} },
    };
    if (!opts.providerAvailable) {
      // Match the real backend contract exactly: a disabled provider fails
      // closed. The user turn is accepted, but NO MODEL_RESPONSE is persisted
      // or streamed — the honest text is never invented as an assistant turn.
      // (Proven against the live API and asserted by the backend suite:
      // test_cognition_streaming.py::test_disabled_stream_ends_with_durable_error_and_no_fake_response.)
      return sse(route, [
        { id: 1, event: "stream.open", data: { request_id: body.message } },
        { id: 2, event: "talk.accepted", data: { model_run_id: response.model_run_id } },
        { id: 3, event: "provider.disabled", data: { reason: "AI provider is disabled." } },
        { id: 4, event: "talk.failed", data: { model_run_id: response.model_run_id, code: "provider_disabled", retryable: false } },
        { id: 5, event: "talk.error", data: { model_run_id: response.model_run_id, code: "provider_disabled", message: "AI provider is disabled. Configure NUR_AI_PROVIDER=openai with a server-only key to generate model output.", retryable: false, durable: true } },
      ]);
    }
    thread.push({
      id: response.response_event_id,
      who: "nur",
      text: output.direct_response,
      structured_payload: {
        talk_output: output,
        provider_reason: response.provider_reason,
        provider_available: response.provider_available,
        model_run_id: response.model_run_id,
      },
      created_at: new Date().toISOString(),
    });
    return sse(route, [
      { id: 1, event: "stream.open", data: { request_id: body.message } },
      { id: 2, event: "talk.accepted", data: { model_run_id: response.model_run_id } },
      { id: 3, event: "response.text.delta", data: { delta: output.direct_response } },
      { id: 4, event: "talk.completed", data: { durable: true, result: response } },
    ]);
  });

  return {
    thread,
    lastTalkMode: () => lastTalkMode,
    planCreated: () => planCreated,
    correctionSaved: () => correctionSaved,
    outcomePosts: () => outcomePosts,
  };
}

test("talk disabled provider fails closed with a visible honest error, never a silent user-only bubble", async ({ page }) => {
  await installTalkMocks(page, { providerAvailable: false });
  await page.goto("/talk");
  const universe = await readyUniverse(page, "#page-talk");
  await universe.locator("#talk-input").fill("Hold this without fake AI.");
  await universe.getByRole("button", { name: "Send to NUR" }).click();

  // The user turn stays visible.
  await expect(universe.locator("#talk-stream .talk-message.user")).toContainText("Hold this without fake AI.");
  // A visible, honest failure appears inside Talk — not a silent user-only bubble.
  const failure = universe.locator("#talk-stream [data-nur-talk-error='true']");
  await expect(failure).toBeVisible();
  await expect(failure).toContainText("Live AI is not connected");
  await expect(universe.locator("#toast")).toContainText("AI provider is disabled.");
  // NUR must never invent an assistant answer when the provider is disabled.
  await expect(universe.locator("#talk-stream")).not.toContainText("I saved this turn, but live AI is disabled on this server.");
  // Regression guard against the exact reported state (user bubbles, zero
  // responses): a failed turn MUST leave exactly one honest failure marker.
  await expect(universe.locator("#talk-stream [data-nur-talk-error='true']")).toHaveCount(1);

  await page.screenshot({
    path: process.cwd().endsWith("/apps/web")
      ? "../../proof/100/talk-disabled-provider-browser.png"
      : "proof/100/talk-disabled-provider-browser.png",
    fullPage: false,
  });
});

test("talk mocked semantic stream preserves structured result and plan/correction actions", async ({ page }) => {
  const mocks = await installTalkMocks(page, { providerAvailable: true });
  await page.goto("/talk");
  const universe = await readyUniverse(page, "#page-talk");
  await universe.locator("#talk-input").fill("Make this source faithful.");
  await universe.getByRole("button", { name: "Send to NUR" }).click();
  await expect(universe.locator("#talk-stream")).toContainText("You are asking for source-faithful movement.");
  expect(mocks.thread.at(-1)?.structured_payload).toMatchObject({
    talk_output: {
      observed: ["The current line asks for movement."],
      inferred: ["The next move should stay small."],
      hypotheses: ["If the move is visible, it will be easier to return to."],
      uncertainty: ["This is based only on the mocked owned source."],
    },
  });
  expect(mocks.lastTalkMode()).toBe("talk");

  await universe.locator('[data-thread-action="plan"]').click();
  await expect.poll(() => mocks.planCreated()).toBe(true);

  await universe.locator('[data-page="systems"]:visible').first().click();
  await universe.locator('.world-command[data-world-focus="insights"]').click();
  await expect(page).toHaveURL(/\/universe\/insights\/candidates$/);
  const candidate = universe.locator(".nur-candidate-card").filter({
    hasText: "Source-faithful movement",
  });
  await expect(candidate).toBeVisible();
  const correction = candidate.locator("textarea.nur-adjunct-textarea");
  await expect(correction).toBeEnabled();
  await correction.fill("Do not infer urgency without evidence.");
  await candidate.locator('[data-adjunct-action="candidate-correct-insight-1"]').click();
  await expect.poll(() => mocks.correctionSaved()).toBe(true);
});

test("former glow action is outcome-gated before visible count changes", async ({ page }) => {
  const mocks = await installTalkMocks(page, { providerAvailable: true });
  await page.goto("/systems");
  const universe = await readyUniverse(page, "#page-systems");
  const outcomesReturned = universe.locator(".universe-hero-stats > span").nth(1);
  await expect(outcomesReturned).toContainText("00");
  await expect(outcomesReturned).toContainText("outcomes returned");

  await page.goto("/plan");
  await readyUniverse(page, "#page-plan");
  await expect(universe.getByText("Mark a Personal Glow")).toHaveCount(0);
  await expect(universe.locator("#nur-outcome-composer")).toBeHidden();
  await universe.locator(".plan-check[data-plan-step-id='step-1']").click();
  await expect(universe.locator("#nur-outcome-composer")).toBeVisible();
  expect(mocks.outcomePosts()).toBe(0);

  await page.goto("/systems");
  await readyUniverse(page, "#page-systems");
  await expect(outcomesReturned).toContainText("00");

  await page.goto("/plan");
  await readyUniverse(page, "#page-plan");
  await universe.locator("#nur-outcome-input").fill("The owner shipped the visible fix.");
  await universe.locator('[data-action="return-outcome"]').click();
  await expect.poll(() => mocks.outcomePosts()).toBe(1);

  await page.goto("/systems");
  await readyUniverse(page, "#page-systems");
  await expect(outcomesReturned).toContainText("01");
});

test("talk thread survives reload from persisted API state", async ({ page }) => {
  const mocks = await installTalkMocks(page, { providerAvailable: true });
  mocks.thread.push(
    {
      id: "persisted-user",
      who: "user",
      text: "This line was already persisted.",
      structured_payload: {},
      created_at: new Date().toISOString(),
    },
    {
      id: "persisted-nur",
      who: "nur",
      text: "Persisted answer.",
      structured_payload: {
        provider_available: true,
        talk_output: {
          direct_response: "Persisted answer.",
          observed: [],
          inferred: [],
          hypotheses: [],
          uncertainty: [],
          next_move: null,
          memory_candidates: [],
          source_refs: [],
        },
      },
      created_at: new Date().toISOString(),
    },
  );

  await page.goto("/talk");
  const universe = await readyUniverse(page, "#page-talk");
  await expect(universe.getByText("This line was already persisted.", { exact: true })).toBeVisible();
  const answer = universe.locator("#talk-stream .talk-message.nur[data-event-id='persisted-nur']");
  await expect(answer).toContainText("Persisted answer.");
  await page.reload();
  await readyUniverse(page, "#page-talk");
  await expect(universe.getByText("This line was already persisted.", { exact: true })).toBeVisible();
  await expect(answer).toContainText("Persisted answer.");
});
