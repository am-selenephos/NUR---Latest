/**
 * Agency surface logic.
 *
 * These test the decisions a card makes before it is drawn — which section a
 * workflow belongs in, whether an approval can still be acted on, and whether
 * every field an owner needs is present. A card missing one of those fields is
 * an owner consenting to something they could not fully read.
 */
import { describe, expect, it } from "vitest";
import {
  DRAWER_SECTIONS,
  buildApprovalCard,
  describeRisk,
  formatCost,
  groupWorkflows,
  isApprovalActionable,
  resolveApprovalEditor,
  sectionFor,
  type AgenticWorkflowState,
  type V197AgenticApproval,
  type V197AgenticWorkflow,
} from "./v197Agentic";

const ALL_STATES: AgenticWorkflowState[] = [
  "DRAFT", "PLANNING", "PLAN_READY", "POLICY_REVIEW", "WAITING_APPROVAL",
  "APPROVED", "QUEUED", "RUNNING", "PAUSED", "VERIFYING", "NEEDS_REVISION",
  "SUCCEEDED", "FAILED", "CANCEL_REQUESTED", "CANCELLED", "EXPIRED",
];

const workflow = (state: AgenticWorkflowState, id = state): V197AgenticWorkflow => ({
  id, title: "t", objective: "o", state, kind: "TEST",
  step_count: 3, steps_done: 1, cost_cents: 0, updated_at: "2026-07-29T00:00:00Z",
});

const approval = (over: Partial<V197AgenticApproval> = {}): V197AgenticApproval => ({
  id: "a", workflow_id: "w", workflow_title: "Scope review",
  tool_key: "schedule_timeline_event", tool_version: "1",
  redacted_arguments: { title: "Scope review", when: "2026-08-04" },
  rationale: "the scope review keeps moving",
  expected_result: "One Timeline event on 4 August",
  risk_class: "R2_DURABLE_PRIVATE", reversible: true,
  scope_summary: "Ambition system", cost_ceiling_cents: 0,
  approval_id: "a", step_id: "s", argument_digest: "sha256:arguments",
  plan_version: 1, call_version: "call-version-1",
  ...over,
});

describe("drawer sections", () => {
  it("places every workflow state in exactly one section", () => {
    const ids = new Set(DRAWER_SECTIONS.map(s => s.id));
    for (const state of ALL_STATES) {
      expect(ids.has(sectionFor(state)), state).toBe(true);
    }
  });

  it("never double-counts, because the counts are how an owner decides to open it", () => {
    const grouped = groupWorkflows(ALL_STATES.map(s => workflow(s)));
    const total = Object.values(grouped).reduce((sum, rows) => sum + rows.length, 0);
    expect(total).toBe(ALL_STATES.length);
    const seen = new Set<string>();
    for (const rows of Object.values(grouped)) {
      for (const row of rows) {
        expect(seen.has(row.id), `${row.id} appears twice`).toBe(false);
        seen.add(row.id);
      }
    }
  });

  it("puts what blocks the owner first", () => {
    expect(DRAWER_SECTIONS[0].id).toBe("waiting");
    expect(DRAWER_SECTIONS[0].blocking).toBe(true);
  });

  it("routes waiting, succeeded and failed states correctly", () => {
    expect(sectionFor("WAITING_APPROVAL")).toBe("waiting");
    expect(sectionFor("SUCCEEDED")).toBe("completed");
    expect(sectionFor("FAILED")).toBe("failed");
    expect(sectionFor("CANCELLED")).toBe("failed");
    expect(sectionFor("EXPIRED")).toBe("failed");
  });

  it("keeps a cancel-requested run in flight until the worker acknowledges", () => {
    expect(sectionFor("CANCEL_REQUESTED")).toBe("working");
  });
});

describe("risk wording", () => {
  it("never shows the raw enum to an owner", () => {
    for (const risk of ["R0_READ_ONLY", "R1_PRIVATE_DRAFT", "R2_DURABLE_PRIVATE",
                        "R3_EXTERNAL", "R4_IRREVERSIBLE"] as const) {
      const text = describeRisk(risk, true);
      expect(text).not.toContain("R0");
      expect(text).not.toContain("_");
    }
  });

  it("states reversibility separately, because it does not follow from risk", () => {
    // create_capsule is R2 and irreversible — the class alone would mislead.
    expect(describeRisk("R2_DURABLE_PRIVATE", false)).toContain("cannot be undone");
    expect(describeRisk("R2_DURABLE_PRIVATE", true)).toContain("can be undone");
  });

  it("says plainly when something leaves NUR", () => {
    expect(describeRisk("R3_EXTERNAL", true).toLowerCase()).toContain("leaves nur");
  });
});

describe("approval cards", () => {
  it("uses the typed raw-JSON fallback when the API exposes no input schema", () => {
    expect(resolveApprovalEditor(approval())).toEqual({
      mode: "RAW_JSON",
      schema: null,
      reason: "The API did not expose an input schema for this approval.",
    });
  });

  it("carries every field an owner needs to decide", () => {
    const card = buildApprovalCard(approval());
    for (const field of [card.what, card.why, card.scope, card.toolLabel,
                         card.risk, card.expected, card.cost]) {
      expect(field, JSON.stringify(card)).toBeTruthy();
    }
    expect(card.arguments.length).toBeGreaterThan(0);
  });

  it("shows the exact arguments, not a summary", () => {
    const card = buildApprovalCard(approval());
    const when = card.arguments.find(a => a.key === "when");
    expect(when?.value).toBe("2026-08-04");
  });

  it("says so when NUR stated no expected result rather than leaving it blank", () => {
    expect(buildApprovalCard(approval({ expected_result: null })).expected)
      .toContain("did not state");
  });

  it("pins the tool version, since the same args on a new version differ", () => {
    expect(buildApprovalCard(approval()).toolLabel).toBe("schedule_timeline_event v1");
  });

  it("withdraws the action when the request has expired", () => {
    const expired = approval({ expires_at: "2026-07-28T00:00:00Z" });
    const card = buildApprovalCard(expired, new Date("2026-07-29T00:00:00Z"));
    expect(card.actionable).toBe(false);
    expect(card.expiryNote).toContain("ask again");
  });

  it("stays actionable before expiry and when no expiry is set", () => {
    expect(isApprovalActionable(approval({ expires_at: "2026-08-30T00:00:00Z" }),
      new Date("2026-07-29T00:00:00Z"))).toBe(true);
    expect(isApprovalActionable(approval())).toBe(true);
  });

  it("treats an unparseable expiry as actionable rather than silently disabling", () => {
    expect(isApprovalActionable(approval({ expires_at: "not-a-date" }))).toBe(true);
  });
});

describe("cost", () => {
  it("reads as a ceiling, not a charge", () => {
    expect(formatCost(250)).toBe("Up to 2.50");
    expect(formatCost(0)).toBe("No cost");
  });
});
