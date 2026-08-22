import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { V197Session } from "./v197ApiClient";
import type { V197AgenticWorkflowDetail } from "./v197Agentic";
import { renderV197Adjunct } from "./v197Adjuncts";

const session: V197Session = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "owner@nur.app",
  profile: { chosen_name: "Owner", locale: "en", writing_preference: "default" },
  orbit: {
    id: "22222222-2222-2222-2222-222222222222",
    title: "Private Orbit",
    kind: "PERSONAL",
    status: "ACTIVE",
  },
};

function workflow(state: V197AgenticWorkflowDetail["state"]): V197AgenticWorkflowDetail {
  return {
    id: "workflow-1",
    title: "Persist one plan",
    objective: "Create one owner-scoped plan",
    state,
    kind: "OWNER_AUTHORED",
    plan_version: 1,
    context_manifest: {},
    success_criteria: ["One plan is persisted"],
    cost_cents: 0,
    steps: [],
  };
}

function event(sequence: number, toState: string) {
  return {
    sequence,
    event_type: "workflow.transitioned",
    from_state: sequence === 1 ? "QUEUED" : "RUNNING",
    to_state: toState,
    summary: `Workflow moved to ${toState}`,
    actor: "worker",
    created_at: "2026-08-22T00:00:00Z",
  };
}

describe("V197 Agent detail durable polling", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    document.body.innerHTML = '<main class="nur-shell"><section class="nur-viewport"><div class="nur-page"></div></section></main>';
    window.history.replaceState({}, "", "/agents/workflow-1");
    Object.defineProperty(document, "hidden", { configurable: true, value: false });
  });

  afterEach(() => {
    vi.useRealTimers();
    document.body.innerHTML = "";
    vi.restoreAllMocks();
  });

  it("uses the last sequence and re-renders when a running workflow reaches terminal state", async () => {
    const api = {
      agenticWorkflow: vi.fn()
        .mockResolvedValueOnce(workflow("RUNNING"))
        .mockResolvedValueOnce(workflow("SUCCEEDED")),
      agenticWorkflowEvents: vi.fn()
        .mockResolvedValueOnce([event(7, "RUNNING")])
        .mockResolvedValueOnce([event(8, "SUCCEEDED")])
        .mockResolvedValueOnce([event(7, "RUNNING"), event(8, "SUCCEEDED")]),
    };

    await renderV197Adjunct(document, "/agents/workflow-1", api as never, null, vi.fn(), session);
    expect(api.agenticWorkflowEvents).toHaveBeenNthCalledWith(1, "workflow-1");

    await vi.advanceTimersByTimeAsync(1_500);

    expect(api.agenticWorkflowEvents).toHaveBeenNthCalledWith(2, "workflow-1", 7);
    expect(api.agenticWorkflow).toHaveBeenCalledTimes(2);
    expect(document.querySelector(".nur-adjunct-panel h2")?.textContent).toBe("SUCCEEDED");
  });

  it("does not poll a workflow that is already terminal", async () => {
    const api = {
      agenticWorkflow: vi.fn().mockResolvedValue(workflow("SUCCEEDED")),
      agenticWorkflowEvents: vi.fn().mockResolvedValue([event(8, "SUCCEEDED")]),
    };

    await renderV197Adjunct(document, "/agents/workflow-1", api as never, null, vi.fn(), session);
    await vi.advanceTimersByTimeAsync(3_000);

    expect(api.agenticWorkflowEvents).toHaveBeenCalledTimes(1);
  });

  it("defers polling while the document is hidden", async () => {
    const api = {
      agenticWorkflow: vi.fn().mockResolvedValue(workflow("RUNNING")),
      agenticWorkflowEvents: vi.fn()
        .mockResolvedValueOnce([event(7, "RUNNING")])
        .mockResolvedValueOnce([]),
    };

    await renderV197Adjunct(document, "/agents/workflow-1", api as never, null, vi.fn(), session);
    Object.defineProperty(document, "hidden", { configurable: true, value: true });
    await vi.advanceTimersByTimeAsync(1_500);

    expect(api.agenticWorkflowEvents).toHaveBeenCalledTimes(1);

    Object.defineProperty(document, "hidden", { configurable: true, value: false });
    await vi.advanceTimersByTimeAsync(1_500);

    expect(api.agenticWorkflowEvents).toHaveBeenNthCalledWith(2, "workflow-1", 7);
  });

  it("ignores an in-flight polling response after the route changes", async () => {
    let resolvePoll: ((events: Array<Record<string, unknown>>) => void) | undefined;
    const pendingPoll = new Promise<Array<Record<string, unknown>>>(resolve => {
      resolvePoll = resolve;
    });
    const api = {
      agenticWorkflow: vi.fn().mockResolvedValue(workflow("RUNNING")),
      agenticWorkflowEvents: vi.fn()
        .mockResolvedValueOnce([event(7, "RUNNING")])
        .mockReturnValueOnce(pendingPoll),
    };

    await renderV197Adjunct(document, "/agents/workflow-1", api as never, null, vi.fn(), session);
    await vi.advanceTimersByTimeAsync(1_500);
    await renderV197Adjunct(document, "/systems", api as never, null, vi.fn(), session);
    resolvePoll?.([event(8, "SUCCEEDED")]);
    await vi.runAllTicks();

    expect(api.agenticWorkflow).toHaveBeenCalledTimes(1);
    expect(document.getElementById("nur-v197-adjunct-root")).toBeNull();
  });
});
