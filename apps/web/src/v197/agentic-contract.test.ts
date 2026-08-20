import { afterEach, describe, expect, it, vi } from "vitest";

import { V197ApiClient } from "../bridge/v197ApiClient";
import type { V197AgenticApproval } from "../bridge/v197Agentic";

const approval: V197AgenticApproval = {
  id: "approval-1",
  workflow_id: "workflow-1",
  workflow_title: "Draft plan",
  tool_key: "create_draft_plan",
  tool_version: "1",
  redacted_arguments: { title: "Draft" },
  rationale: "The owner asked for a bounded draft.",
  expected_result: "One private draft.",
  risk_class: "R1_PRIVATE_DRAFT",
  reversible: true,
  scope_summary: "Private owner state",
  cost_ceiling_cents: 0,
  approval_id: "approval-1",
  step_id: "step-1",
  argument_digest: "sha256:old",
  plan_version: 4,
  call_version: "call-4",
};

function ok(): Response {
  return new Response(JSON.stringify({ id: "workflow-2" }), {
    status: 200,
    headers: { "content-type": "application/json" },
  });
}

afterEach(() => {
  vi.restoreAllMocks();
  document.cookie = "nur_csrf=; Max-Age=0; path=/";
});

describe("Agentend browser contracts", () => {
  it("retries the immutable workflow through the public workflow-level route", async () => {
    document.cookie = "nur_csrf=csrf-test; path=/";
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(ok());
    const client = new V197ApiClient();

    await client.retryAgenticWorkflow("workflow-1", "retry-request-1", 4);

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/agentic/workflows/workflow-1/retry",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ request_id: "retry-request-1", seen_plan_version: 4 }),
      }),
    );
  });

  it("sends an editable approval with the owner-visible edited arguments", async () => {
    document.cookie = "nur_csrf=csrf-test; path=/";
    const fetch = vi.spyOn(globalThis, "fetch").mockResolvedValue(ok());
    const client = new V197ApiClient();
    const edited = { title: "Edited draft" };

    await client.decideAgenticApproval(approval, "EDIT", undefined, edited);

    expect(fetch).toHaveBeenCalledWith(
      "/api/v1/agentic/approvals/approval-1/decide",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          decision: "EDIT",
          seen_digest: "sha256:old",
          seen_plan_version: 4,
          seen_call_version: "call-4",
          note: null,
          edited_arguments: edited,
        }),
      }),
    );
  });
});
