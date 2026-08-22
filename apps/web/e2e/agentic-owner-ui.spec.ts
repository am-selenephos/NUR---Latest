import { expect, test } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

test("owner policy compiles, starts and cancels a bounded workflow", async ({ page }) => {
  const state = await installNurMocks(page);
  await page.goto("/agents", { waitUntil: "networkidle" });
  const frame = page.frameLocator("#nur-universe-stage");
  const adjunct = frame.locator("#nur-v197-adjunct-root");
  await expect(adjunct.locator("h1")).toHaveText("Agency under your authority.");

  await adjunct.locator('[data-agentic-permit="get_today_state"]').check();
  await adjunct.locator('[data-adjunct-action="agentic-policy-save"]').click();
  await expect(adjunct.getByText("Owner policy persisted. No workflow was started.")).toBeVisible();
  expect(state.agenticWrites[0]).toMatchObject({
    path: "/api/v1/agentic/policy",
    body: { permitted_tools: ["get_today_state"] },
  });

  await adjunct.locator('[data-adjunct-control="agentic-title"]').fill("Read today's owner state");
  await adjunct.locator('[data-adjunct-control="agentic-objective"]').fill("Read the persisted Today state without changing it.");
  await adjunct.locator('[data-adjunct-control="agentic-success"]').fill("A source-labelled Today snapshot is returned.");
  await adjunct.locator('[data-adjunct-control="agentic-tool"]').selectOption("get_today_state");
  await adjunct.locator('[data-adjunct-control="agentic-role"]').selectOption("operator");
  await adjunct.locator('[data-adjunct-control="agentic-arguments"]').fill("{}");
  await adjunct.locator('[data-adjunct-control="agentic-rationale"]').fill("The owner asked to inspect the current persisted state.");
  await adjunct.locator('[data-adjunct-action="agentic-workflow-create"]').click();

  await expect(page).toHaveURL(/\/agents\/cccccccc-cccc-4ccc-8ccc-cccccccccccc$/);
  await expect(adjunct.locator("h1")).toHaveText("Read today's owner state");
  await expect(adjunct.getByText("PLAN_READY", { exact: true })).toBeVisible();
  await adjunct.locator('[data-adjunct-action="agentic-workflow-start"]').click();
  await expect(adjunct.getByText("QUEUED", { exact: true })).toBeVisible();
  await adjunct.locator('[data-adjunct-action="agentic-workflow-cancel"]').click();
  await expect(adjunct.getByText("CANCEL_REQUESTED", { exact: true })).toBeVisible();

  expect(state.agenticWrites.map(row => row.path)).toEqual([
    "/api/v1/agentic/policy",
    "/api/v1/agentic/workflows",
    "/api/v1/agentic/workflows/cccccccc-cccc-4ccc-8ccc-cccccccccccc/start",
    "/api/v1/agentic/workflows/cccccccc-cccc-4ccc-8ccc-cccccccccccc/cancel",
  ]);
});

test("approval action is bound to the displayed digest and plan versions", async ({ page }) => {
  const state = await installNurMocks(page);
  state.agenticApprovals.push({
    id: "abababab-abab-4bab-8bab-abababababab",
    approval_id: "abababab-abab-4bab-8bab-abababababab",
    workflow_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    workflow_title: "Read today's owner state",
    step_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    tool_key: "get_today_state",
    tool_version: "1",
    redacted_arguments: {},
    rationale: "Owner policy requires a visible decision.",
    expected_result: "One source-labelled Today snapshot.",
    risk_class: "R0_READ_ONLY",
    reversible: true,
    scope_summary: "This private Orbit only",
    cost_ceiling_cents: 0,
    expires_at: null,
    argument_digest: "sha256:displayed-arguments",
    plan_version: 3,
    call_version: "call-version-displayed",
  });

  await page.goto("/agents", { waitUntil: "networkidle" });
  const adjunct = page.frameLocator("#nur-universe-stage").locator("#nur-v197-adjunct-root");
  await expect(adjunct.getByText("Owner policy requires a visible decision.")).toBeVisible();
  await adjunct.locator('[data-adjunct-action="agentic-approval-approve-abababab-abab-4bab-8bab-abababababab"]').click();
  await expect(adjunct.getByText("No approval is waiting")).toBeVisible();

  expect(state.agenticWrites.at(-1)).toEqual({
    path: "/api/v1/agentic/approvals/abababab-abab-4bab-8bab-abababababab/decide",
    body: {
      decision: "APPROVE",
      seen_digest: "sha256:displayed-arguments",
      seen_plan_version: 3,
      seen_call_version: "call-version-displayed",
      note: null,
      edited_arguments: null,
    },
  });
});

test("approval EDIT uses the typed raw-JSON fallback and rerenders after persistence", async ({ page }) => {
  const state = await installNurMocks(page);
  state.agenticApprovals.push({
    id: "bcbcbcbc-bcbc-4cbc-8cbc-bcbcbcbcbcbc",
    approval_id: "bcbcbcbc-bcbc-4cbc-8cbc-bcbcbcbcbcbc",
    workflow_id: "cccccccc-cccc-4ccc-8ccc-cccccccccccc",
    workflow_title: "Read a bounded Today window",
    step_id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
    tool_key: "get_today_state",
    tool_version: "1",
    redacted_arguments: { window: "today" },
    rationale: "The owner must edit the exact call before it can run.",
    expected_result: "One bounded Today snapshot.",
    risk_class: "R0_READ_ONLY",
    reversible: true,
    scope_summary: "This private Orbit only",
    cost_ceiling_cents: 0,
    expires_at: null,
    argument_digest: "sha256:editable-arguments",
    plan_version: 4,
    call_version: "call-version-edit",
  });

  await page.goto("/agents", { waitUntil: "networkidle" });
  const adjunct = page.frameLocator("#nur-universe-stage").locator("#nur-v197-adjunct-root");
  await adjunct.locator('[data-adjunct-action="agentic-approval-edit-bcbcbcbc-bcbc-4cbc-8cbc-bcbcbcbcbcbc"]').click();
  const fallback = adjunct.locator('[data-approval-editor-mode="raw-json"]');
  await expect(fallback).toContainText("API did not expose an input schema");
  const editor = adjunct.getByLabel("Edit the owner-visible approval arguments as JSON");
  await expect(editor).toBeVisible();
  await editor.fill('{"window":"week","include_completed":false}');
  await adjunct.locator('[data-adjunct-action="agentic-approval-submit-edit-bcbcbcbc-bcbc-4cbc-8cbc-bcbcbcbcbcbc"]').click();

  await expect(adjunct.getByText("No approval is waiting")).toBeVisible();
  expect(state.agenticWrites.at(-1)).toEqual({
    path: "/api/v1/agentic/approvals/bcbcbcbc-bcbc-4cbc-8cbc-bcbcbcbcbcbc/decide",
    body: {
      decision: "EDIT",
      seen_digest: "sha256:editable-arguments",
      seen_plan_version: 4,
      seen_call_version: "call-version-edit",
      note: null,
      edited_arguments: { window: "week", include_completed: false },
    },
  });
});

test("retry opens the immutable successor returned by the API", async ({ page }) => {
  const state = await installNurMocks(page);
  const workflowId = "aaaaaaaa-1111-4111-8111-aaaaaaaaaaaa";
  const successorId = "eeeeeeee-2222-4222-8222-eeeeeeeeeeee";
  state.agenticDetails[workflowId] = {
    id: workflowId,
    title: "Retry the bounded read",
    objective: "Retry from an immutable plan without mutating history.",
    kind: "OWNER_DEFINED",
    state: "FAILED",
    plan_version: 5,
    context_manifest: {},
    success_criteria: ["A successor workflow is returned."],
    cost_cents: 0,
    failure_code: "TRANSIENT_FAILURE",
    idempotent_replay: false,
    steps: [{
      id: "ffffffff-3333-4333-8333-ffffffffffff",
      key: "step-1",
      ordinal: 1,
      state: "FAILED",
      role: "operator",
      tool_key: "get_today_state",
      tool_version: "1",
      risk_class: "R0_READ_ONLY",
      approval_required: false,
      depends_on: [],
      input_refs: {},
      verification_verdict: null,
      attempt: 1,
      execution_attempt: "attempt-old",
      idempotency_key: "retry-old",
      failure_code: "TRANSIENT_FAILURE",
      retryable: true,
    }],
  };

  await page.goto(`/agents/${workflowId}`, { waitUntil: "networkidle" });
  const adjunct = page.frameLocator("#nur-universe-stage").locator("#nur-v197-adjunct-root");
  await adjunct.locator(`[data-adjunct-action="agentic-workflow-retry-${workflowId}"]`).click();

  await expect(page).toHaveURL(new RegExp(`/agents/${successorId}$`));
  await expect(adjunct.getByText("PLAN_READY", { exact: true })).toBeVisible();
  expect(state.agenticWrites.at(-1)).toMatchObject({
    path: `/api/v1/agentic/workflows/${workflowId}/retry`,
    body: { seen_plan_version: 5 },
  });
});
