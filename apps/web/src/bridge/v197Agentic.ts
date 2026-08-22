/**
 * V197 agency surfaces: the drawer, the approval inbox, and run detail.
 *
 * The product law this implements is that agency is never invisible. If NUR is
 * doing something, it appears here; if NUR wants permission, it appears here
 * with enough detail to actually decide. Hiding either behind a server log
 * would make the whole approval mechanism decorative — an owner cannot withhold
 * consent they were never asked for.
 *
 * Two constraints carried over from the lens work, both learned the hard way:
 *
 *   No second rAF. Canonical already runs the galaxy loop; a drawer that
 *   animates on its own frame budget competes with the thing that makes the
 *   product feel alive. Everything here is event-driven and CSS-transitioned.
 *
 *   Real elements, never canonical's pseudo-elements. Painting on ::before or
 *   ::after of a canonical control silently destroys an existing effect. The
 *   drawer is appended DOM with its own classes.
 */

export type AgenticWorkflowState =
  | "DRAFT" | "PLANNING" | "PLAN_READY" | "POLICY_REVIEW" | "WAITING_APPROVAL"
  | "APPROVED" | "QUEUED" | "RUNNING" | "PAUSED" | "VERIFYING"
  | "NEEDS_REVISION" | "SUCCEEDED" | "FAILED" | "CANCEL_REQUESTED"
  | "CANCELLED" | "EXPIRED";

export type AgenticRiskClass =
  | "R0_READ_ONLY" | "R1_PRIVATE_DRAFT" | "R2_DURABLE_PRIVATE"
  | "R3_EXTERNAL" | "R4_IRREVERSIBLE";

export interface V197AgenticWorkflow {
  id: string;
  title: string;
  objective: string;
  state: AgenticWorkflowState;
  kind: string;
  step_count: number;
  steps_done: number;
  cost_cents: number;
  failure_code?: string | null;
  updated_at: string;
}

export interface V197AgenticStep {
  id: string;
  key: string;
  ordinal: number;
  state: string;
  role: string;
  tool_key: string | null;
  tool_version: string | null;
  risk_class: AgenticRiskClass;
  approval_required: boolean;
  depends_on: string[];
  input_refs: Record<string, unknown>;
  verification_verdict?: string | null;
  attempt: number;
  execution_attempt: string;
  idempotency_key: string;
  failure_code?: string | null;
  retryable: boolean;
}

export interface V197AgenticWorkflowDetail {
  id: string;
  title: string;
  objective: string;
  state: AgenticWorkflowState;
  kind: string;
  plan_version: number;
  context_manifest: Record<string, unknown>;
  success_criteria: string[];
  cost_cents: number;
  failure_code?: string | null;
  idempotent_replay?: boolean;
  steps: V197AgenticStep[];
}

export interface V197AgenticTool {
  key: string;
  version: string;
  risk_class: AgenticRiskClass;
  summary: string;
  reads: string[];
  writes: string[];
  reversible: boolean;
  required_capabilities: string[];
  bound: boolean;
}

export interface V197AgenticPolicy {
  id?: string;
  scope: "ACCOUNT";
  persisted: boolean;
  initiative_level: "OFF" | "SUGGEST" | "PREPARE" | "INTERNAL" | "CONNECTED" | "DELEGATED";
  max_risk_class: AgenticRiskClass;
  permitted_tools: string[];
  auto_run_tools: string[];
  denied_tools: string[];
  granted_capabilities: string[];
  daily_budget_cents: number;
  max_proposals_per_day: number;
  cooldown_minutes: number;
  quiet_hours: Record<string, unknown> | null;
}

export interface V197AgenticApproval {
  id: string;
  workflow_id: string;
  workflow_title?: string;
  tool_key: string;
  tool_version: string;
  /** Already redacted server-side. The client never sees raw secrets. */
  redacted_arguments: Record<string, unknown>;
  rationale: string;
  expected_result?: string | null;
  risk_class: AgenticRiskClass;
  reversible: boolean;
  scope_summary?: string | null;
  cost_ceiling_cents: number;
  expires_at?: string | null;
  approval_id: string;
  step_id?: string | null;
  argument_digest: string;
  plan_version: number;
  call_version: string;
  /** Optional future server contract. The current API does not expose it. */
  input_schema?: V197AgenticApprovalInputSchema | null;
}

export interface V197AgenticApprovalInputSchema {
  type: "object";
  properties?: Record<string, {
    type?: "string" | "number" | "integer" | "boolean" | "array" | "object";
    title?: string;
    description?: string;
  }>;
  required?: string[];
  additionalProperties?: boolean;
}

export type V197ApprovalEditor =
  | { mode: "SCHEMA"; schema: V197AgenticApprovalInputSchema; reason: null }
  | { mode: "RAW_JSON"; schema: null; reason: string };

export function resolveApprovalEditor(approval: V197AgenticApproval): V197ApprovalEditor {
  if (approval.input_schema?.type === "object") {
    return { mode: "SCHEMA", schema: approval.input_schema, reason: null };
  }
  return {
    mode: "RAW_JSON",
    schema: null,
    reason: "The API did not expose an input schema for this approval.",
  };
}

/**
 * Drawer sections, in the order the directive names them. Order is deliberate:
 * what needs the owner comes before what is merely happening, because the first
 * is blocking and the second is not.
 */
export const DRAWER_SECTIONS = [
  { id: "waiting", label: "Waiting for you", blocking: true },
  { id: "working", label: "NUR is working", blocking: false },
  { id: "scheduled", label: "Scheduled", blocking: false },
  { id: "completed", label: "Completed", blocking: false },
  { id: "failed", label: "Failed", blocking: false },
] as const;

export type DrawerSectionId = (typeof DRAWER_SECTIONS)[number]["id"];

const WORKING: ReadonlySet<AgenticWorkflowState> = new Set([
  "PLANNING", "POLICY_REVIEW", "APPROVED", "QUEUED", "RUNNING", "VERIFYING",
]);
const SCHEDULED: ReadonlySet<AgenticWorkflowState> = new Set([
  "DRAFT", "PLAN_READY", "PAUSED", "NEEDS_REVISION",
]);
const FAILED: ReadonlySet<AgenticWorkflowState> = new Set([
  "FAILED", "CANCELLED", "EXPIRED",
]);

/**
 * A workflow appears in exactly one section. Duplication would make the counts
 * lie, and the drawer's counts are how an owner decides whether to open it.
 */
export function sectionFor(state: AgenticWorkflowState): DrawerSectionId {
  if (state === "WAITING_APPROVAL") return "waiting";
  if (state === "SUCCEEDED") return "completed";
  if (FAILED.has(state)) return "failed";
  if (WORKING.has(state)) return "working";
  if (SCHEDULED.has(state)) return "scheduled";
  // CANCEL_REQUESTED is still in flight until the worker acknowledges it.
  return "working";
}

export function groupWorkflows(
  workflows: readonly V197AgenticWorkflow[],
): Record<DrawerSectionId, V197AgenticWorkflow[]> {
  const grouped = Object.fromEntries(
    DRAWER_SECTIONS.map(section => [section.id, [] as V197AgenticWorkflow[]]),
  ) as Record<DrawerSectionId, V197AgenticWorkflow[]>;
  for (const workflow of workflows) grouped[sectionFor(workflow.state)].push(workflow);
  return grouped;
}

/** Owner-facing risk wording. The enum name is not an explanation. */
export function describeRisk(risk: AgenticRiskClass, reversible: boolean): string {
  const base: Record<AgenticRiskClass, string> = {
    R0_READ_ONLY: "Reads your records. Changes nothing.",
    R1_PRIVATE_DRAFT: "Creates a private draft you can discard.",
    R2_DURABLE_PRIVATE: "Changes your own records.",
    R3_EXTERNAL: "Leaves NUR and reaches someone or something else.",
    R4_IRREVERSIBLE: "Cannot be undone.",
  };
  // Reversibility is stated separately because it is the question an owner
  // actually asks, and it does not follow from the risk class alone —
  // create_capsule is R2 and irreversible.
  return `${base[risk]} ${reversible ? "This can be undone." : "This cannot be undone."}`;
}

export function formatCost(cents: number): string {
  if (!cents) return "No cost";
  return `Up to ${(cents / 100).toFixed(2)}`;
}

/**
 * An approval whose expiry has passed must not offer an Approve button — the
 * server would refuse it, and a button that cannot work is worse than none.
 */
export function isApprovalActionable(
  approval: V197AgenticApproval,
  now: Date = new Date(),
): boolean {
  if (!approval.expires_at) return true;
  const expires = Date.parse(approval.expires_at);
  return Number.isNaN(expires) ? true : expires > now.getTime();
}

/**
 * Every field the owner needs before consenting, in one place, so a card cannot
 * be rendered missing one. The directive lists these; keeping them as data means
 * a missing field is a type error rather than an omission nobody notices.
 */
export interface ApprovalCardModel {
  what: string;
  why: string;
  scope: string;
  toolLabel: string;
  arguments: ReadonlyArray<{ key: string; value: string }>;
  risk: string;
  expected: string;
  cost: string;
  actionable: boolean;
  expiryNote: string | null;
}

export function buildApprovalCard(
  approval: V197AgenticApproval,
  now: Date = new Date(),
): ApprovalCardModel {
  const actionable = isApprovalActionable(approval, now);
  return {
    what: approval.tool_key.replace(/_/g, " "),
    why: approval.rationale,
    scope: approval.scope_summary ?? "This Orbit only",
    toolLabel: `${approval.tool_key} v${approval.tool_version}`,
    arguments: Object.entries(approval.redacted_arguments).map(([key, value]) => ({
      key: key.replace(/_/g, " "),
      value: typeof value === "string" ? value : JSON.stringify(value),
    })),
    risk: describeRisk(approval.risk_class, approval.reversible),
    expected: approval.expected_result ?? "NUR did not state an expected result.",
    cost: formatCost(approval.cost_ceiling_cents),
    actionable,
    expiryNote: actionable
      ? null
      : "This request expired. NUR will ask again rather than assume you still agree.",
  };
}
