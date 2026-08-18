import { describe, expect, it } from "vitest";
import {
  initialCapabilityState,
  reduceCapabilityEvent,
  type CapabilityEvent,
} from "./v197CapabilityReducer";

describe("browser-safe capability event reducer", () => {
  it("reduces canonical events and never stores raw internal payloads", () => {
    const events: CapabilityEvent[] = [
      { type: "talk.scope.resolved", payload: { scope_id: "scope-1", sharing_boundary: "PRIVATE", raw: { secret: "x" } } },
      { type: "talk.capability.resolved", payload: { capability_id: "capability:plan_from_conversation" } },
      { type: "talk.preview.ready", payload: { preview_id: "preview-1", writes: false, direct_response: "Preview" } },
      { type: "workflow.proposed", payload: { workflow_id: "workflow-1", requires_approval: true, raw_plan: { hidden: "x" } } },
      { type: "workflow.approval.required", payload: { workflow_id: "workflow-1", approval_id: "approval-1" } },
    ];

    const state = events.reduce(reduceCapabilityEvent, initialCapabilityState());

    expect(state.scopeId).toBe("scope-1");
    expect(state.capabilityId).toBe("capability:plan_from_conversation");
    expect(state.preview?.writes).toBe(false);
    expect(state.workflowId).toBe("workflow-1");
    expect(state.approvalId).toBe("approval-1");
    expect(Object.prototype.hasOwnProperty.call(state, "raw")).toBe(false);
    expect(JSON.stringify(state)).not.toContain("hidden");
    expect(JSON.stringify(state)).not.toContain("secret");
  });

  it("keeps browser state non-authoritative for unknown or execution events", () => {
    const state = reduceCapabilityEvent(initialCapabilityState(), {
      type: "workflow.step.executed",
      payload: { workflow_id: "w", state: "SUCCEEDED", owner_truth: "do not store" },
    });
    expect(state.workflowState).toBe("EXECUTED");
    expect(state.durableSaveConfirmed).toBe(false);
    expect(JSON.stringify(state)).not.toContain("owner_truth");
  });
});
