export type CapabilityEvent = {
  type:
    | "talk.scope.resolved"
    | "talk.capability.resolved"
    | "talk.preview.ready"
    | "workflow.proposed"
    | "workflow.approval.required"
    | "workflow.step.executed"
    | "workflow.completed"
    | "workflow.failed";
  payload: Record<string, unknown>;
};

export type CapabilityState = {
  scopeId?: string;
  capabilityId?: string;
  preview?: { previewId: string; writes: boolean; directResponse: string };
  workflowId?: string;
  approvalId?: string;
  workflowState?: "PROPOSED" | "WAITING_APPROVAL" | "EXECUTED" | "COMPLETED" | "FAILED";
  durableSaveConfirmed: boolean;
};

export function initialCapabilityState(): CapabilityState {
  return { durableSaveConfirmed: false };
}

function stringField(payload: Record<string, unknown>, key: string): string | undefined {
  const value = payload[key];
  return typeof value === "string" && value.length > 0 ? value : undefined;
}

export function reduceCapabilityEvent(
  state: CapabilityState,
  event: CapabilityEvent,
): CapabilityState {
  const payload = event.payload;
  switch (event.type) {
    case "talk.scope.resolved":
      return { ...state, scopeId: stringField(payload, "scope_id") };
    case "talk.capability.resolved":
      return { ...state, capabilityId: stringField(payload, "capability_id") };
    case "talk.preview.ready": {
      const previewId = stringField(payload, "preview_id");
      const directResponse = stringField(payload, "direct_response");
      const writes = payload.writes === true;
      return previewId && directResponse
        ? { ...state, preview: { previewId, writes, directResponse } }
        : state;
    }
    case "workflow.proposed":
      return {
        ...state,
        workflowId: stringField(payload, "workflow_id"),
        workflowState: "PROPOSED",
      };
    case "workflow.approval.required":
      return {
        ...state,
        workflowId: stringField(payload, "workflow_id") ?? state.workflowId,
        approvalId: stringField(payload, "approval_id"),
        workflowState: "WAITING_APPROVAL",
      };
    case "workflow.step.executed":
      return {
        ...state,
        workflowId: stringField(payload, "workflow_id") ?? state.workflowId,
        workflowState: "EXECUTED",
        durableSaveConfirmed: false,
      };
    case "workflow.completed":
      return {
        ...state,
        workflowId: stringField(payload, "workflow_id") ?? state.workflowId,
        workflowState: "COMPLETED",
        durableSaveConfirmed: payload.server_confirmed === true,
      };
    case "workflow.failed":
      return {
        ...state,
        workflowId: stringField(payload, "workflow_id") ?? state.workflowId,
        workflowState: "FAILED",
        durableSaveConfirmed: false,
      };
    default:
      return state;
  }
}
