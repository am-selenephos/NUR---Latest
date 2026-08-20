import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { expect, test, type Locator, type Page, type Route } from "@playwright/test";

const now = new Date().toISOString();
const proofDir = process.env.NUR_PROOF_DIR ?? (process.cwd().endsWith("/apps/web") ? "../../proof/screenshots" : "proof/screenshots");

test.use({ serviceWorkers: "block" });

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
  created_at: now,
};

const decision = {
  id: "decision-1",
  orbit_id: orbit.id,
  statement: "Postgres RLS is the trust boundary.",
  rationale: "Recipient access must stay grant-scoped.",
  created_at: now,
};

const reference = {
  id: "reference-1",
  orbit_id: orbit.id,
  title: "Capsule spectrum palette",
  body: "Mango through pearl.",
  kind: "REFERENCE",
  created_at: now,
};

const source = {
  id: "source-decision-1",
  orbit_id: orbit.id,
  source_kind: "DECISION",
  source_id: decision.id,
  inclusion_mode: "FULL",
  created_at: now,
};

function shot(name: string) {
  const path = join(proofDir, name);
  mkdirSync(dirname(path), { recursive: true });
  return path;
}

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installMocks(page: Page) {
  const thread: Array<{ id: string; who: "user" | "nur"; text: string; structured_payload: Record<string, unknown>; created_at: string }> = [];
  await page.context().addCookies([{ name: "nur_csrf", value: "webkit-proof", domain: "localhost", path: "/" }]);
  await page.route("**/api/v1/auth/me", route => json(route, user));
  await page.route("**/api/v1/orbits/current-state", route => json(route, {
    active_systems: 1,
    outcomes_returned: 2,
    insights_evolving: 3,
    open_questions: 1,
    research_staged: 1,
    plans_active: 1,
    live_status: "owner_ledger",
  }));
  await page.route("**/api/v1/orbits", route => json(route, [orbit]));
  await page.route(`**/api/v1/orbits/${orbit.id}/decisions`, route => json(route, [decision]));
  await page.route(`**/api/v1/orbits/${orbit.id}/references`, route => json(route, [reference]));
  await page.route(`**/api/v1/orbits/${orbit.id}/sources`, route => json(route, [source]));
  await page.route("**/api/v1/journal", route => json(route, []));
  await page.route("**/api/v1/plans", route => json(route, []));
  await page.route("**/api/v1/research-drafts", route => json(route, []));
  await page.route("**/api/v1/capsules", route => json(route, [{
    id: "cap-active",
    orbit_id: orbit.id,
    title: "Quiet Ambition shared context",
    purpose: "Get a designer useful in 20 minutes",
    capability: "ASK_SCOPED_QUESTIONS",
    expires_at: null,
    revoked_at: null,
    version: 1,
    created_at: now,
  }]));
  await page.route("**/api/v1/capsules/cap-active/view", route => json(route, capsuleView("ACTIVE")));
  await page.route("**/api/v1/capsules/cap-revoked/view", route => json(route, capsuleView("REVOKED")));
  await page.route("**/api/v1/cognition/talk-thread**", route => json(route, thread));
  await page.route("**/api/v1/cognition/talk/stream", async route => {
    const body = JSON.parse(route.request().postData() || "{}") as { message?: string };
    const output = {
      direct_response: "I saved this turn, but live AI is disabled on this server.",
      observed: ["The disabled provider path is explicit."],
      inferred: [],
      hypotheses: ["Owner can configure OpenAI locally later."],
      uncertainty: ["AI provider is disabled."],
      next_move: "Record one outcome.",
      memory_candidates: [],
      source_refs: [],
    };
    thread.push(
      { id: "turn-1", who: "user", text: body.message || "", structured_payload: {}, created_at: now },
      {
        id: "turn-2",
        who: "nur",
        text: output.direct_response,
        structured_payload: { talk_output: output, provider_available: false, provider_reason: "AI provider is disabled." },
        created_at: now,
      },
    );
    const result = {
      turn_event_id: "turn-1",
      response_event_id: "turn-2",
      model_run_id: "model-run-1",
      provider: "disabled",
      provider_available: false,
      provider_reason: "AI provider is disabled.",
      output,
      evidence: { retrieval: [], withheld: [] },
      verification: { verdict: "WARN", checks: {} },
      omega: {
        enabled: true,
        workspace_frame_id: "frame-1",
        what_changed: ["Claim strengthened: outcome evidence gate"],
        open_contradictions: ["Potential conflict: shortcutting outcome proof."],
        unresolved_predictions: ["If the owner returns an outcome..."],
        memory_note: "I can hold this as a hypothesis, not a fact.",
      },
    };
    const sse = [
      `id: 1\nevent: talk.accepted\ndata: ${JSON.stringify({ event_id: "turn-1" })}`,
      `id: 2\nevent: talk.validated\ndata: ${JSON.stringify({ event_id: "turn-1" })}`,
      `id: 3\nevent: talk.completed\ndata: ${JSON.stringify({ result })}`,
    ].join("\n\n") + "\n\n";
    return route.fulfill({ status: 200, headers: { "content-type": "text/event-stream", "cache-control": "no-cache" }, body: sse });
  });
  await page.route("**/api/v1/glow/rewards", route => json(route, {
    id: "glow-talk-1",
    event_type: "talk_meaningful",
    source_kind: "COGNITIVE_EVENT",
    source_id: "turn-1",
    awarded_points: 0,
    balance: 0,
    idempotency_key: "talk:turn-1:meaningful",
  }, 201));
  await page.route("**/api/v1/omega/dashboard", route => json(route, omegaDashboard()));
  await page.route("**/api/v1/omega/scheduler-status", route => json(route, { enabled: true, scheduled_consolidation: true, interval_hours: 24, worker_mode: "local_celery_beat", last_consolidation_run_at: null, last_consolidation_status: "none_yet", provenance_label: "owner_ledger" }));
  await page.route("**/api/v1/omega/review-queue", route => json(route, omegaDashboard().review_queue));
  await page.route("**/api/v1/omega/claims/*/evidence", route => json(route, [{
    id: "edge-1",
    claim_id: "claim-1",
    evidence_kind: "EXPERIENCE",
    evidence_id: "experience-1",
    relation: "SUPPORTS",
    strength: 1,
    note: "created from observed outcome",
    created_at: now,
  }]));
  await page.route("**/api/v1/omega/claims/*/why-changed", route => json(route, {
    claim_id: "claim-1",
    claim_text: "Outcome evidence should strengthen planning patterns only after persisted results.",
    current_truth_status: "OBSERVED",
    current_confidence: 0.82,
    changed_because: ["1 supporting evidence edge increased confidence."],
    supporting_edges: ["SUPPORTS via EXPERIENCE strength 1.00"],
    contradicting_edges: [],
    unresolved_note: null,
  }));
  await page.route("**/api/v1/omega/consolidate", route => json(route, omegaDashboard().consolidation_runs[0]));
  await page.route("**/api/v1/omega/export", route => json(route, {
    exported_at: now,
    owner_user_id: user.id,
    safety: { owner_only: true, chain_of_thought_excluded: true },
    counts: { claims: 1, review_queue: 1 },
    ...omegaDashboard(),
  }));
  await page.route("**/api/v1/universe/live", route => json(route, {
    generated_at: now,
    provenance_label: "OWNER_LEDGER_AGGREGATE",
    owner: { id: user.id, email: user.email, chosen_name: "Selene", timezone: "UTC", locale: "en", writing_preference: "default", default_boundary: "PRIVATE_ORBIT" },
    state: { summary: "One owner-ledger System is active.", source_count: 1, confidence: 1, confidence_kind: "source_coverage_not_truth_probability", last_updated: now, today: null, provenance_label: "DETERMINISTIC_OWNER_LEDGER_SYNTHESIS" },
    active_systems: [],
    active_goals: [],
    active_objectives: [],
    active_plans: [],
    people_orbits: [],
    group_orbits: [],
    projects: [],
    latest_insights: [],
    timeline_highlights: [],
    open_loops: [],
    next_moves: [],
    glow: { today_points: 0 },
    signals: [],
    community: { live_connected: false, status: "LOCAL_NOTES_ONLY", note_count: 0, latest_note: null, honest_state: "No live community activity is invented." },
    what_changed: [],
  }));
  await page.route("**/api/v1/profile/preferences", route => json(route, {
    locale: "en",
    writing_preference: "default",
    sound_enabled: false,
    reduced_effects: true,
    omega_enabled: true,
    timezone: "UTC",
    default_boundary: "PRIVATE_ORBIT",
  }));
}

function capsuleView(state: "ACTIVE" | "REVOKED") {
  return {
    capsule_id: state === "ACTIVE" ? "cap-active" : "cap-revoked",
    state,
    title: "Quiet Ambition",
    purpose: "Get a designer useful in 20 minutes",
    owner_display: "Selene",
    capability: "ASK_SCOPED_QUESTIONS",
    expires_at: null,
    recipient_instructions: state === "ACTIVE" ? "Stay inside the approved boundary." : null,
    safety_copy: "This does not speak for Selene. It answers only from approved context.",
    included: state === "ACTIVE" ? [{
      source_id: "decision-1",
      source_kind: "DECISION",
      representation: "FULL",
      title: "Postgres RLS is the trust boundary.",
      body: "Recipient access must stay grant-scoped.",
    }] : [],
    excluded_summary: state === "ACTIVE" ? [{ source_kind: "REFERENCE", count: 1, note: "withheld by the owner" }] : [],
    grant_id: state === "ACTIVE" ? "grant-1" : null,
  };
}

function omegaDashboard() {
  const claim = {
    id: "claim-1",
    orbit_id: orbit.id,
    claim_text: "Outcome evidence should strengthen planning patterns only after persisted results.",
    claim_type: "PATTERN",
    truth_status: "OBSERVED",
    confidence: 0.82,
    support_count: 1,
    contradiction_count: 0,
    last_supported_at: now,
    last_contradicted_at: null,
    created_at: now,
    updated_at: now,
  };
  return {
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
    contradictions: [{
      id: "contradiction-1",
      orbit_id: orbit.id,
      claim_a_id: "claim-1",
      claim_b_id: "claim-2",
      status: "OPEN",
      severity: "HIGH",
      description: "Potential conflict: shortcutting outcome proof vs outcome-gated learning.",
      proposed_resolution: "Return an outcome first.",
      resolved_by_event_id: null,
      created_at: now,
      updated_at: now,
    }],
    predictions: [{
      id: "prediction-1",
      orbit_id: orbit.id,
      prediction_text: "If the owner returns an outcome, the planning claim will become easier to trust.",
      expected_observation: "owner returns an outcome",
      metric: null,
      time_window: "next session",
      confidence: 0.68,
      status: "OPEN",
      outcome_id: null,
      prediction_error: null,
      created_at: now,
      resolved_at: null,
    }],
    consolidation_runs: [{
      id: "run-1",
      run_kind: "MANUAL",
      orbit_id: orbit.id,
      input_counts: { summary: "Counts only; no raw private dump stored." },
      created_claims: 1,
      updated_claims: 0,
      contradictions_found: 1,
      predictions_resolved: 0,
      proposals_created: 1,
      status: "COMPLETED",
      completed_at: now,
      error_class: null,
      created_at: now,
    }],
    learning_proposals: [{
      id: "proposal-1",
      proposal_kind: "PLANNING_HEURISTIC",
      description: "Ask for a persisted outcome before upgrading repeated Talk guidance.",
      evidence_summary: "Outcome rows exist before strengthening.",
      supporting_evaluation_ids: [],
      risk_level: "LOW",
      status: "PROPOSED",
      approved_by_owner: false,
      created_at: now,
      updated_at: now,
    }],
    recent_experiences: [],
    review_queue: [{
      id: "review-1",
      orbit_id: orbit.id,
      experience_id: "experience-1",
      candidate_claim_text: "A sensitive inferred identity preference requires owner confirmation.",
      candidate_claim_type: "PREFERENCE",
      candidate_truth_status: "HYPOTHESIS",
      sensitivity: "SENSITIVE",
      reason: "sensitive inferred domain: identity",
      model_candidate: { confidence: 0.57 },
      status: "PENDING_REVIEW",
      created_claim_id: null,
      reviewed_at: null,
      created_at: now,
      updated_at: now,
    }],
  };
}

async function assertNoHorizontalOverflow(body: Locator) {
  const overflow = await body.evaluate(() => ({
    documentScrollWidth: document.documentElement.scrollWidth,
    documentClientWidth: document.documentElement.clientWidth,
    bodyScrollWidth: document.body.scrollWidth,
    bodyClientWidth: document.body.clientWidth,
  }));
  expect(overflow.documentScrollWidth).toBeLessThanOrEqual(overflow.documentClientWidth + 1);
  expect(overflow.bodyScrollWidth).toBeLessThanOrEqual(overflow.bodyClientWidth + 1);
}

async function assertNotNativeWhite(locator: Locator, label: string) {
  await expect(locator).toBeVisible();
  const style = await locator.evaluate(el => {
    const cs = getComputedStyle(el);
    return {
      backgroundColor: cs.backgroundColor,
      backgroundImage: cs.backgroundImage,
      color: cs.color,
    };
  });
  expect(style.backgroundColor, `${label} not native white`).not.toBe("rgb(255, 255, 255)");
  expect(style.color, `${label} not native black`).not.toBe("rgb(0, 0, 0)");
}

function requireWebkitMobile(testInfo: { project: { name: string } }): void {
  test.skip(testInfo.project.name !== "webkit-mobile", "This proof must run in the real WebKit mobile project.");
}

test("final WebKit mobile Systems surface is bounded and geometrically safe", async ({ page }, testInfo) => {
  requireWebkitMobile(testInfo);
  test.setTimeout(30_000);
  await installMocks(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await page.goto("/systems");

  const universe = page.frameLocator("#nur-universe-stage");
  const universeBody = universe.locator("body");
  const systemsPage = universe.locator("#page-systems");
  await expect(systemsPage).toBeVisible();
  await assertNoHorizontalOverflow(universeBody);
  await expect(universe.locator(".universe-master-star")).toBeVisible();
  await expect(universe.locator(".universe-map-title")).toBeVisible();
  const readout = universe.locator(".universe-field-readout");
  if (await readout.isVisible()) {
    const readoutBox = await readout.boundingBox();
    expect(readoutBox?.x ?? -1).toBeGreaterThanOrEqual(0);
    expect((readoutBox?.x ?? 0) + (readoutBox?.width ?? 0)).toBeLessThanOrEqual(393);
  }
  const titleBox = await universe.locator(".universe-map-title").boundingBox();
  expect(titleBox?.x ?? -1).toBeGreaterThanOrEqual(0);
  expect((titleBox?.x ?? 0) + (titleBox?.width ?? 0)).toBeLessThanOrEqual(393);
  const addSystem = universe.locator('[data-action="add-system"]');
  if (await addSystem.isVisible()) {
    const box = await addSystem.boundingBox();
    expect((box?.y ?? 999) + (box?.height ?? 0)).toBeLessThan(760);
  }
  await page.screenshot({ path: shot("webkit-mobile-systems-393x852.png"), fullPage: false });
});

test("final WebKit mobile Share Orbit boundary is explicit", async ({ page }, testInfo) => {
  requireWebkitMobile(testInfo);
  test.setTimeout(30_000);
  await installMocks(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await page.goto("/systems");

  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible();
  // The current V197 boundary chamber is the canonical Share Orbit affordance.
  await universe.locator("#scope-open").scrollIntoViewIfNeeded();
  await universe.locator("#scope-open").click();
  const scopeModal = universe.locator("#scope-modal");
  await expect(scopeModal).toHaveClass(/open/);
  await expect(scopeModal).toHaveAttribute("aria-hidden", "false");
  await assertNotNativeWhite(scopeModal.locator('.scope-option[data-scope="System Shared"]'), "System Shared boundary");
  await expect(scopeModal).toContainText("Share pseudonymously in one selected Star System.");
  await page.screenshot({ path: shot("webkit-mobile-share-orbit-393x852.png"), fullPage: false });
  await scopeModal.locator(".scope-modal-close").click();
  await expect(scopeModal).toHaveAttribute("aria-hidden", "true");
});

test("final WebKit mobile Talk proves actionable honest provider-disabled behavior", async ({ page }, testInfo) => {
  requireWebkitMobile(testInfo);
  test.setTimeout(30_000);
  await installMocks(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await page.goto("/talk");

  const universe = page.frameLocator("#nur-universe-stage");
  const universeBody = universe.locator("body");
  await expect(universe.locator("#page-talk")).toBeVisible();
  await universe.locator("#talk-input").fill("Hold this without fake AI.");
  const sendButton = universe.getByRole("button", { name: "Send to NUR" });
  await expect(sendButton).toBeVisible();
  await expect(sendButton).toBeEnabled();
  await sendButton.click();
  await expect(universe.getByText("I saved this turn, but live AI is disabled on this server.")).toBeVisible();
  await expect(universe.locator("#toast")).toHaveText("AI provider is disabled.");
  await assertNoHorizontalOverflow(universeBody);
  await page.screenshot({ path: shot("webkit-mobile-talk-393x852.png"), fullPage: false });
});

test("final WebKit mobile Omega surface renders governed evidence state", async ({ page }, testInfo) => {
  requireWebkitMobile(testInfo);
  test.setTimeout(30_000);
  await installMocks(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await page.goto("/universe/omega");

  const universe = page.frameLocator("#nur-universe-stage");
  const universeBody = universe.locator("body");
  const omega = universe.locator("#nur-v197-adjunct-root");
  await expect(omega).toBeVisible();
  await expect(omega).toContainText("Evidence changes the model, deliberately.");
  await expect(omega).toContainText("sensitive inferences still require owner review.");
  await assertNoHorizontalOverflow(universeBody);
  await page.screenshot({ path: shot("webkit-mobile-omega-393x852.png"), fullPage: false });
});

test("final WebKit mobile Capsule and revocation surfaces remain bounded", async ({ page }, testInfo) => {
  requireWebkitMobile(testInfo);
  test.setTimeout(30_000);
  await installMocks(page);
  await page.setViewportSize({ width: 393, height: 852 });

  const universe = page.frameLocator("#nur-universe-stage");
  const universeBody = universe.locator("body");
  await page.goto("/capsule/cap-active");
  const activeCapsule = universe.locator("#nur-v197-adjunct-root");
  await expect(activeCapsule).toBeVisible();
  await expect(activeCapsule).toContainText("What is included");
  await expect(activeCapsule).toContainText("ACTIVE");
  await assertNoHorizontalOverflow(universeBody);
  await page.screenshot({ path: shot("webkit-mobile-capsule-393x852.png"), fullPage: false });

  await page.goto("/capsule/cap-revoked");
  const revokedCapsule = universe.locator("#nur-v197-adjunct-root");
  await expect(revokedCapsule).toBeVisible();
  await expect(revokedCapsule).toContainText("REVOKED");
});
