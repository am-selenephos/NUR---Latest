import { expect, test, type Page, type Route } from "@playwright/test";
import { mkdirSync } from "node:fs";

import { installNurMocks } from "./helpers/nurMocks";

test.use({ serviceWorkers: "block" });

const proofRoot = process.cwd().endsWith("/apps/web") ? "../../proof/omega/screenshots" : "proof/omega/screenshots";
mkdirSync(proofRoot, { recursive: true });
const omegaFlagEnabled = process.env.VITE_NUR_ENABLE_OMEGA_RESEARCH === "true" || process.env.NUR_ENABLE_OMEGA_RESEARCH === "true";

const user = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "selene@nurapp.dev",
  email_verified: true,
  profile: { chosen_name: "Selene", timezone: null, locale: "en", sound_enabled: false, reduced_effects: true },
  orbit: { id: "99999999-9999-9999-9999-999999999999", current_arrival_state: null, active_focus_area: null },
};

const orbit = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "Quiet Ambition",
  kind: "PROJECT",
  description: "Build without noise",
  status: "ACTIVE",
  created_at: new Date().toISOString(),
};

const claim = {
  id: "33333333-3333-3333-3333-333333333333",
  orbit_id: orbit.id,
  claim_text: "Outcome evidence should strengthen planning patterns only after persisted results.",
  claim_type: "PATTERN",
  truth_status: "OBSERVED",
  confidence: 0.82,
  support_count: 2,
  contradiction_count: 0,
  last_supported_at: new Date().toISOString(),
  last_contradicted_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const contradiction = {
  id: "44444444-4444-4444-4444-444444444444",
  orbit_id: orbit.id,
  claim_a_id: claim.id,
  claim_b_id: "55555555-5555-5555-5555-555555555555",
  status: "OPEN",
  severity: "HIGH",
  description: "Potential conflict: shortcutting outcome proof vs outcome-gated learning.",
  proposed_resolution: "Return an outcome before strengthening the claim.",
  resolved_by_event_id: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const prediction = {
  id: "66666666-6666-6666-6666-666666666666",
  orbit_id: orbit.id,
  prediction_text: "If the owner returns an outcome, the planning claim will become easier to trust.",
  expected_observation: "owner returns an outcome",
  metric: null,
  time_window: "next session",
  confidence: 0.68,
  status: "OPEN",
  outcome_id: null,
  prediction_error: null,
  created_at: new Date().toISOString(),
  resolved_at: null,
};

const proposal = {
  id: "77777777-7777-7777-7777-777777777777",
  proposal_kind: "PLANNING_HEURISTIC",
  description: "Ask for a persisted outcome before upgrading repeated Talk guidance.",
  evidence_summary: "Two Omega claims were supported only after outcome rows existed.",
  supporting_evaluation_ids: [],
  risk_level: "LOW",
  status: "PROPOSED",
  approved_by_owner: false,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

const reviewItem = {
  id: "12121212-1212-1212-1212-121212121212",
  orbit_id: orbit.id,
  experience_id: "99999999-9999-9999-9999-999999999991",
  candidate_claim_text: "The owner may have a sensitive identity preference that requires confirmation.",
  candidate_claim_type: "PREFERENCE",
  candidate_truth_status: "HYPOTHESIS",
  sensitivity: "SENSITIVE",
  reason: "sensitive inferred domain: identity",
  model_candidate: { confidence: 0.57 },
  status: "PENDING_REVIEW",
  created_claim_id: null,
  reviewed_at: null,
  created_at: new Date().toISOString(),
  updated_at: new Date().toISOString(),
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function sse(route: Route, result: unknown) {
  await route.fulfill({
    status: 200,
    headers: { "cache-control": "no-cache", "content-type": "text/event-stream; charset=utf-8" },
    body: [
      `id: 1\nevent: talk.accepted\ndata: ${JSON.stringify({ event_id: "omega-talk-user" })}\n\n`,
      `id: 2\nevent: talk.completed\ndata: ${JSON.stringify({ result })}\n\n`,
    ].join(""),
  });
}

async function installOmegaMocks(page: Page) {
  await installNurMocks(page);
  const thread: Array<{ id: string; who: "user" | "nur"; text: string; structured_payload: Record<string, unknown>; created_at: string }> = [];
  let dashboard = {
    statuses: {
      experience_ledger: "IMPLEMENTED",
      evidence_graph: "IMPLEMENTED",
      contradiction_engine: "IMPLEMENTED",
      prediction_resolution: "IMPLEMENTED",
      consolidation: "IMPLEMENTED",
      learning_proposals: "IMPLEMENTED",
      sentience_status: "UNRESOLVED_SENTIENCE_STATUS",
    },
    claims: [claim],
    contradictions: [contradiction],
    predictions: [prediction],
    consolidation_runs: [{
      id: "88888888-8888-8888-8888-888888888888",
      run_kind: "MANUAL",
      orbit_id: orbit.id,
      input_counts: { summary: "Counts only; no raw private dump stored." },
      created_claims: 1,
      updated_claims: 0,
      contradictions_found: 1,
      predictions_resolved: 0,
      proposals_created: 1,
      status: "COMPLETED",
      completed_at: new Date().toISOString(),
      error_class: null,
      created_at: new Date().toISOString(),
    }],
    learning_proposals: [proposal],
    review_queue: [reviewItem],
    recent_experiences: [{
      id: "99999999-9999-9999-9999-999999999991",
      source_kind: "COGNITIVE_EVENT",
      source_id: "99999999-9999-9999-9999-999999999992",
      orbit_id: orbit.id,
      event_kind: "OUTCOME_REPORTED",
      scope: "PRIVATE_ORBIT",
      language_tag: "en",
      summary: "Owner returned a visible outcome.",
      raw_ref: { table: "cognitive_events" },
      provenance_label: "OBSERVED_OUTCOME",
      sensitivity: "PRIVATE",
      confidence: 1,
      created_at: new Date().toISOString(),
    }],
  };
  await page.route("**/api/v1/auth/me", route => json(route, user));
  await page.route("**/api/v1/orbits/current-state", route => json(route, {
    active_systems: 1, outcomes_returned: 1, insights_evolving: 1,
    open_questions: 0, research_staged: 0, plans_active: 0, live_status: "owner_ledger",
  }));
  await page.route("**/api/v1/orbits", route => json(route, [orbit]));
  await page.route("**/api/v1/journal", route => json(route, []));
  await page.route("**/api/v1/plans", route => json(route, []));
  await page.route("**/api/v1/cognition/talk-thread**", route => json(route, thread));
  await page.route("**/api/v1/omega/dashboard", route => json(route, dashboard));
  await page.route("**/api/v1/cognition/talk/stream", async route => {
    const body = JSON.parse(route.request().postData() || "{}") as { message?: string };
    const output = {
      direct_response: "I saved this turn, but live AI is disabled on this server.",
      observed: [],
      inferred: [],
      hypotheses: [],
      uncertainty: ["AI provider is disabled."],
      next_move: "Keep one concrete next line.",
      memory_candidates: [],
      source_refs: [],
    };
    const omega = {
      enabled: true,
      workspace_frame_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
      what_changed: ["Claim strengthened: outcome evidence gate"],
      open_contradictions: ["Potential conflict: shortcutting outcome proof."],
      unresolved_predictions: ["If the owner returns an outcome..."],
      memory_note: "I can hold this as a hypothesis, not a fact.",
    };
    thread.push(
      { id: "omega-talk-user", who: "user", text: body.message || "", structured_payload: {}, created_at: new Date().toISOString() },
      { id: "omega-talk-response", who: "nur", text: output.direct_response, structured_payload: { talk_output: output, omega, provider_available: false, provider_reason: "AI provider is disabled." }, created_at: new Date().toISOString() },
    );
    return sse(route, {
      turn_event_id: "omega-talk-user",
      response_event_id: "omega-talk-response",
      model_run_id: "omega-talk-model",
      provider: "disabled",
      provider_available: false,
      provider_reason: "AI provider is disabled.",
      output,
      omega,
      evidence: { retrieval: [], withheld: [] },
      verification: { verdict: "WARN", checks: {} },
    });
  });
  await page.route("**/api/v1/omega/scheduler-status", route => json(route, {
    enabled: true,
    scheduled_consolidation: true,
    worker_mode: "LOCAL",
    last_consolidation_status: "COMPLETED",
    interval_hours: 24,
  }));
  await page.route("**/api/v1/omega/claims/*/evidence", route => json(route, [{
    id: "edge-1",
    claim_id: claim.id,
    evidence_kind: "EXPERIENCE",
    evidence_id: "99999999-9999-9999-9999-999999999991",
    relation: "SUPPORTS",
    strength: 1,
    note: "created from observed outcome",
    created_at: new Date().toISOString(),
  }]));
  await page.route("**/api/v1/omega/claims/*/why-changed", route => json(route, {
    claim_id: claim.id,
    claim_text: claim.claim_text,
    current_truth_status: "OBSERVED",
    current_confidence: 0.82,
    changed_because: ["2 supporting evidence edge(s) increased confidence or support count."],
    supporting_edges: ["SUPPORTS via EXPERIENCE strength 1.00 · created from observed outcome"],
    contradicting_edges: [],
    unresolved_note: null,
  }));
  await page.route("**/api/v1/omega/review-queue", route => json(route, dashboard.review_queue));
  await page.route("**/api/v1/omega/review-queue/*/*", route => {
    dashboard = { ...dashboard, review_queue: [] };
    return json(route, { ...reviewItem, status: "APPROVED", created_claim_id: claim.id });
  });
  await page.route("**/api/v1/omega/export", route => json(route, {
    exported_at: new Date().toISOString(),
    owner_user_id: user.id,
    safety: { owner_only: true, chain_of_thought_excluded: true, capsule_recipient_context_excluded: true },
    counts: { claims: 1, contradictions: 1, predictions: 1, consolidation_runs: 1, learning_proposals: 1, review_queue: dashboard.review_queue.length },
    claims: [claim],
    contradictions: [contradiction],
    predictions: [prediction],
    consolidation_runs: dashboard.consolidation_runs,
    learning_proposals: [proposal],
    review_queue: dashboard.review_queue,
  }));
  await page.route("**/api/v1/omega/consolidate", route => {
    dashboard = {
      ...dashboard,
      consolidation_runs: [
        { ...dashboard.consolidation_runs[0], id: "run-after-click", created_claims: 2 },
        ...dashboard.consolidation_runs,
      ],
    };
    return json(route, dashboard.consolidation_runs[0]);
  });
  await page.route("**/api/v1/omega/contradictions/*/resolve", route => {
    dashboard = { ...dashboard, contradictions: [] };
    return json(route, { ...contradiction, status: "RESOLVED" });
  });
  await page.route("**/api/v1/omega/claims/*/confirm", route => json(route, { ...claim, truth_status: "OBSERVED" }));
  await page.route("**/api/v1/omega/claims/*/retire", route => json(route, { ...claim, truth_status: "RETIRED" }));
  await page.route("**/api/v1/omega/learning-proposals/*/*", route => json(route, { ...proposal, status: "APPROVED", approved_by_owner: true }));
  await page.route("**/api/v1/cognition/talk", route => {
    const body = JSON.parse(route.request().postData() || "{}") as { message?: string };
    const output = {
      direct_response: "I saved this turn, but live AI is disabled on this server.",
      observed: [],
      inferred: [],
      hypotheses: [],
      uncertainty: ["AI provider is disabled."],
      next_move: "Keep one concrete next line.",
      memory_candidates: [],
      source_refs: [],
    };
    const omega = {
      enabled: true,
      workspace_frame_id: "dddddddd-dddd-dddd-dddd-dddddddddddd",
      what_changed: ["Claim strengthened: outcome evidence gate"],
      open_contradictions: ["Potential conflict: shortcutting outcome proof."],
      unresolved_predictions: ["If the owner returns an outcome..."],
      memory_note: "I can hold this as a hypothesis, not a fact.",
    };
    thread.push(
      { id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa", who: "user", text: body.message || "", structured_payload: {}, created_at: new Date().toISOString() },
      {
        id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
        who: "nur",
        text: output.direct_response,
        structured_payload: {
          talk_output: output,
          omega,
          provider_available: false,
          provider_reason: "AI provider is disabled.",
          model_run_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
        },
        created_at: new Date().toISOString(),
      },
    );
    return json(route, {
      turn_event_id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
      response_event_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
      model_run_id: "cccccccc-cccc-cccc-cccc-cccccccccccc",
      provider: "disabled",
      provider_available: false,
      provider_reason: "AI provider is disabled.",
      output,
      omega,
      evidence: { retrieval: [], withheld: [] },
      verification: { verdict: "WARN", checks: {} },
    });
  });
}

test("seeded Omega dashboard renders inside the canonical iframe and supports governed actions", async ({ page }) => {
  test.skip(!omegaFlagEnabled, "Omega route is hidden unless NUR_ENABLE_OMEGA_RESEARCH=true or VITE_NUR_ENABLE_OMEGA_RESEARCH=true.");
  const shot = (name: string) => `${proofRoot}/${test.info().project.name}-${name}`;
  await installOmegaMocks(page);
  await page.goto("/universe/omega");
  const universe = page.frameLocator("#nur-universe-stage");
  const adjunct = universe.locator("#nur-v197-adjunct-root");
  await expect(adjunct).toBeVisible();
  await expect(adjunct).toContainText("Evidence changes the model, deliberately.");
  await expect(adjunct.locator(".nur-adjunct-panel").filter({ hasText: "Candidate understanding" })).toContainText(claim.claim_text);
  await expect(adjunct.locator(".nur-adjunct-panel").filter({ hasText: "Open tension" })).toContainText(contradiction.description);
  await expect(adjunct.locator(".nur-adjunct-panel").filter({ hasText: "Unresolved future" })).toContainText(prediction.prediction_text);
  await expect(adjunct.locator(".nur-adjunct-panel").filter({ hasText: "Governed learning" })).toContainText(proposal.description);
  await expect(adjunct).toContainText("Open review queue (1)");
  await page.screenshot({ path: shot("omega-dashboard.png"), fullPage: false });

  await adjunct.locator('[data-adjunct-action="omega-consolidate"]').click();
  await expect(adjunct.locator(".nur-adjunct-status")).toContainText("Run COMPLETED: 2 claims created");
  await adjunct.locator('[data-adjunct-action="omega-export"]').click();
  await expect(adjunct.locator(".nur-adjunct-status")).toContainText("Owner-scoped Omega export prepared locally.");
  await adjunct.locator('[data-adjunct-action="omega-review"]').click();
  await expect(page).toHaveURL(/\/universe\/omega\/review$/);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Owner confirmation gate");
  await page.screenshot({ path: shot("omega-review-deep-link.png"), fullPage: false });
});

test("seeded Omega review approval survives reload and why-changed deep link", async ({ page }) => {
  test.skip(!omegaFlagEnabled, "Omega proof run uses the flagged build.");
  const shot = (name: string) => `${proofRoot}/${test.info().project.name}-${name}`;
  await installOmegaMocks(page);
  await page.goto("/universe/omega/review");
  const universe = page.frameLocator("#nur-universe-stage");
  const adjunct = universe.locator("#nur-v197-adjunct-root");
  await expect(adjunct).toContainText("Pending review · 1");
  await expect(adjunct).toContainText(reviewItem.candidate_claim_text);
  await adjunct.locator(`[data-adjunct-action="omega-review-approve-${reviewItem.id}"]`).click();
  await expect(adjunct).toContainText("Pending review · 0");
  await page.reload();
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Pending review · 0");

  await page.goto(`/universe/omega/why-changed/${claim.id}`);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Why NUR changed its mind.");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("supporting evidence");
  await page.screenshot({ path: shot("omega-why-changed-deep-link.png"), fullPage: false });
});

test("talk preserves provider-disabled honesty without chain of thought", async ({ page }) => {
  test.skip(!omegaFlagEnabled, "Omega proof run uses the flagged build.");
  const shot = (name: string) => `${proofRoot}/${test.info().project.name}-${name}`;
  await installOmegaMocks(page);
  await page.goto("/talk");
  const universe = page.frameLocator("#nur-universe-stage");
  await universe.locator("#talk-input").fill("What changed?");
  await universe.getByRole("button", { name: "Send to NUR" }).click();
  await expect(universe.locator("#talk-stream")).toContainText("I saved this turn, but live AI is disabled on this server.");
  await expect(universe.locator("body")).not.toContainText("chain-of-thought");
  await expect(universe.locator("body")).not.toContainText("workspace_frame_id");
  await page.screenshot({ path: shot("talk-with-omega-context.png"), fullPage: false });
});
