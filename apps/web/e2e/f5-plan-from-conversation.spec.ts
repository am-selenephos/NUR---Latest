import { expect, test, type Route } from "@playwright/test";

import { installNurMocks, json } from "./helpers/nurMocks";

const PREVIEW_MESSAGE = "Show me a plan for the migration\n- Backup the database\n- Run the migration\n- Verify the result";
const PREVIEW_ID = "preview-migration-1";
const WORKFLOW_ID = "77777777-7777-4777-8777-777777777777";
const APPROVAL_ID = "88888888-8888-4888-8888-888888888888";
const STEP_ID = "99999999-9999-4999-8999-999999999999";
const PLAN_ID = "plan-migration-1";

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

function approval() {
  return {
    id: APPROVAL_ID,
    approval_id: APPROVAL_ID,
    workflow_id: WORKFLOW_ID,
    workflow_title: "Plan: Migration foundation",
    step_id: STEP_ID,
    tool_key: "create_draft_plan",
    tool_version: "1",
    redacted_arguments: {
      title: "Migration foundation",
      steps: ["Backup the database", "Run the migration", "Verify the result"],
    },
    rationale: "The owner explicitly asked to save the reviewed conversational Plan preview.",
    expected_result: "One DRAFT Plan with the reviewed migration steps.",
    risk_class: "R1_PRIVATE_DRAFT",
    reversible: true,
    scope_summary: "This Private Orbit only",
    cost_ceiling_cents: 2,
    expires_at: null,
    argument_digest: "sha256:f5-displayed-plan-arguments",
    plan_version: 1,
    call_version: "f5-call-v1",
  };
}

function plan() {
  return {
    id: PLAN_ID,
    title: "Migration foundation",
    status: "DRAFT",
    orbit_id: "22222222-2222-2222-2222-222222222222",
    steps: [{
      id: "plan-step-migration-1",
      title: "Backup the database",
      body: "One reviewed owner-approved movement inside this Plan.",
      position: 0,
      done: false,
      done_at: null,
      experiment_id: null,
    }],
  };
}

test("F5 Talk preview requires explicit save, approval, and exactly one durable Plan", async ({ page }) => {
  const state = await installNurMocks(page);
  state.thread.splice(0, state.thread.length);
  state.agenticApprovals.splice(0, state.agenticApprovals.length);
  state.agenticWorkflows.splice(0, state.agenticWorkflows.length);

  let previewReadyEvents = 0;
  let workflowProposedEvents = 0;
  let saveStreamCalls = 0;
  let planPosts = 0;
  let durablePlan = false;
  let approvalDecision: Record<string, unknown> | null = null;

  await page.route("**/api/v1/cognition/talk/stream", async route => {
    const body = JSON.parse(route.request().postData() || "{}") as { message?: string };
    const message = body.message ?? "";
    const isExplicitSave = message.startsWith("Draft a plan to save this reviewed preview:");
    const userRow = {
      id: `talk-user-${state.thread.length + 1}`,
      who: "user" as const,
      text: message,
      structured_payload: {},
      created_at: new Date().toISOString(),
    };
    state.thread.push(userRow);

    if (!isExplicitSave) {
      previewReadyEvents += 1;
      const directResponse = "### Plan Preview: Migration foundation\n\n- Backup the database\n- Run the migration\n- Verify the result\n\nThis is a conversational preview. Nothing has been saved.";
      state.thread.push({
        id: "talk-preview-response",
        who: "nur",
        text: directResponse,
        structured_payload: {
          provider_available: true,
          provider: "DETERMINISTIC_WORKER",
          talk_output: {
            direct_response: directResponse,
            observed: [],
            inferred: [],
            hypotheses: [],
            uncertainty: ["The owner has not explicitly saved this preview."],
            next_move: "Review the preview before saving.",
            memory_candidates: [],
            source_refs: [],
          },
          capability_lifecycle: {
            preview_id: PREVIEW_ID,
            writes: false,
          },
        },
        created_at: new Date().toISOString(),
      });
      return sse(route, [
        { id: 1, event: "stream.open", data: { request_id: message } },
        { id: 2, event: "talk.scope.resolved", data: { scope_id: "scope-f5", sharing_boundary: "PRIVATE_ORBIT" } },
        { id: 3, event: "talk.capability.resolved", data: { capability_id: "capability:plan_from_conversation", resolution_source: "INFERRED" } },
        { id: 4, event: "talk.accepted", data: { model_run_id: "model-f5-preview" } },
        { id: 5, event: "talk.preview.ready", data: { preview_id: PREVIEW_ID, writes: false, direct_response: directResponse } },
        { id: 6, event: "response.text.delta", data: { delta: directResponse } },
        {
          id: 7,
          event: "talk.completed",
          data: {
            result: {
              turn_event_id: userRow.id,
              response_event_id: "talk-preview-response",
              model_run_id: "model-f5-preview",
              provider: "DETERMINISTIC_WORKER",
              provider_available: true,
              provider_reason: null,
              output: {
                direct_response: directResponse,
                observed: [],
                inferred: [],
                hypotheses: [],
                uncertainty: ["The owner has not explicitly saved this preview."],
                next_move: "Review the preview before saving.",
                memory_candidates: [],
                source_refs: [],
              },
              verification: { verdict: "PASS" },
            },
          },
        },
      ]);
    }

    saveStreamCalls += 1;
    const directResponse = "The reviewed Plan is proposed and waiting for your approval.";
    state.thread.push({
      id: "talk-save-response",
      who: "nur",
      text: directResponse,
      structured_payload: {
        provider_available: true,
        provider: "DETERMINISTIC_WORKER",
        talk_output: {
          direct_response: directResponse,
          observed: [],
          inferred: [],
          hypotheses: [],
          uncertainty: [],
          next_move: null,
          memory_candidates: [],
          source_refs: [],
        },
        capability_lifecycle: {
          workflow_id: WORKFLOW_ID,
          requires_approval: true,
        },
      },
      created_at: new Date().toISOString(),
    });
    workflowProposedEvents += 1;
    if (state.agenticApprovals.length === 0) state.agenticApprovals.push(approval());
    if (state.agenticWorkflows.length === 0) {
      state.agenticWorkflows.push({
        id: WORKFLOW_ID,
        title: "Plan: Migration foundation",
        objective: "Persist the owner-reviewed migration Plan.",
        state: "WAITING_APPROVAL",
        kind: "CAPABILITY_PROPOSAL",
        step_count: 1,
        steps_done: 0,
        cost_cents: 2,
        failure_code: null,
        updated_at: new Date().toISOString(),
      });
    }
    return sse(route, [
      { id: 1, event: "stream.open", data: { request_id: message } },
      { id: 2, event: "talk.scope.resolved", data: { scope_id: "scope-f5", sharing_boundary: "PRIVATE_ORBIT" } },
      { id: 3, event: "talk.capability.resolved", data: { capability_id: "capability:plan_from_conversation", resolution_source: "EXPLICIT_AUTHENTICATED" } },
      { id: 4, event: "talk.accepted", data: { model_run_id: "model-f5-save" } },
      { id: 5, event: "workflow.proposed", data: { workflow_id: WORKFLOW_ID, state: "WAITING_APPROVAL", requires_approval: true } },
      { id: 6, event: "workflow.approval.required", data: { workflow_id: WORKFLOW_ID, approval_id: APPROVAL_ID } },
      { id: 7, event: "response.text.delta", data: { delta: directResponse } },
      {
        id: 8,
        event: "talk.completed",
        data: {
          result: {
            turn_event_id: userRow.id,
            response_event_id: "talk-save-response",
            model_run_id: "model-f5-save",
            provider: "DETERMINISTIC_WORKER",
            provider_available: true,
            provider_reason: null,
            output: {
              direct_response: directResponse,
              observed: [],
              inferred: [],
              hypotheses: [],
              uncertainty: [],
              next_move: null,
              memory_candidates: [],
              source_refs: [],
            },
            verification: { verdict: "PASS" },
          },
        },
      },
    ]);
  });

  await page.route("**/api/v1/agentic/approvals", async route => {
    if (route.request().method() === "GET") {
      return json(route, { approvals: state.agenticApprovals, count: state.agenticApprovals.length });
    }
    return route.continue();
  });
  await page.route("**/api/v1/agentic/approvals/*/decide", async route => {
    approvalDecision = JSON.parse(route.request().postData() || "{}") as Record<string, unknown>;
    state.agenticApprovals.splice(0, state.agenticApprovals.length);
    state.agenticWorkflows[0] = { ...state.agenticWorkflows[0], state: "SUCCEEDED" };
    durablePlan = true;
    return json(route, {
      approval_id: APPROVAL_ID,
      decision: "APPROVE",
      step_state: "SUCCEEDED",
      workflow_state: "SUCCEEDED",
      outbox_intent_id: "f5-outbox-1",
    });
  });
  await page.route("**/api/v1/plans", async route => {
    if (route.request().method() === "GET") return json(route, durablePlan ? [plan()] : []);
    planPosts += 1;
    return json(route, plan(), 201);
  });

  await page.goto("/talk");
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-talk")).toBeVisible();
  await universe.locator("#talk-input").fill(PREVIEW_MESSAGE);
  await universe.getByRole("button", { name: "Send to NUR" }).click();

  await expect(universe.locator("[data-f5-plan-preview]")).toBeVisible();
  await expect(universe.locator("[data-f5-plan-preview]")).toContainText("Plan Preview: Migration foundation");
  await expect.poll(() => previewReadyEvents).toBe(1);
  expect(workflowProposedEvents).toBe(0);
  expect(planPosts).toBe(0);
  await expect(universe.locator('[data-thread-action="plan"]')).toHaveText("Save this Plan");

  await universe.locator('[data-thread-action="plan"]').click();
  await expect.poll(() => saveStreamCalls).toBe(1);
  await expect.poll(() => workflowProposedEvents).toBe(1);
  await expect(universe.locator("[data-f5-workflow-state]")).toContainText("Workflow proposed");
  await expect(universe.locator("[data-f5-workflow-state]")).toContainText("Owner approval required");
  expect(planPosts).toBe(0);

  // A repeated owner click is a replay, not a second workflow or direct Plan write.
  await universe.locator('[data-thread-action="plan"]').click();
  await expect.poll(() => saveStreamCalls).toBe(1);
  expect(planPosts).toBe(0);

  await page.goto("/agents");
  const adjunct = page.frameLocator("#nur-universe-stage").locator("#nur-v197-adjunct-root");
  await expect(adjunct.getByText("The owner explicitly asked to save the reviewed conversational Plan preview.")).toBeVisible();
  await adjunct.locator(`[data-adjunct-action="agentic-approval-approve-${APPROVAL_ID}"]`).click();
  await expect.poll(() => approvalDecision).toMatchObject({ decision: "APPROVE" });
  await expect(adjunct.getByText("No approval is waiting")).toBeVisible();

  await page.goto("/plan");
  const planFrame = page.frameLocator("#nur-universe-stage");
  await expect(planFrame.locator("#page-plan .panel-title").first()).toHaveText("Migration foundation");
  await expect(planFrame.locator("#page-plan .plan-list .plan-step")).toHaveCount(1);
  await expect(planFrame.locator("#page-plan .plan-list")).toContainText("Backup the database");
  expect(planPosts).toBe(0);

  await page.reload();
  const reloadedPlanFrame = page.frameLocator("#nur-universe-stage");
  await expect(reloadedPlanFrame.locator("#page-plan .panel-title").first()).toHaveText("Migration foundation");
  await expect(reloadedPlanFrame.locator("#page-plan .plan-list .plan-step")).toHaveCount(1);
  await expect(reloadedPlanFrame.locator("#page-plan .plan-list")).toContainText("Backup the database");
  expect(planPosts).toBe(0);
});
