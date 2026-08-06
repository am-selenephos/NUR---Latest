// Types shared between the FastAPI contract and the web client.
// Type-only: no runtime code crosses the boundary.
export interface ProfileOut {
  chosen_name: string;
  timezone: string | null;
  locale: string | null;
  writing_preference: string;
  sound_enabled: boolean;
  reduced_effects: boolean;
}
export interface OrbitOut {
  id: string;
  current_arrival_state: string | null;
  active_focus_area: string | null;
}
export interface MeResponse {
  id: string;
  email: string;
  email_verified: boolean;
  profile: ProfileOut;
  orbit: OrbitOut;
}
export interface RegisterRequest {
  chosen_name: string;
  email: string;
  password: string;
  consent: boolean;
}
export interface LoginRequest { email: string; password: string; }
export interface ApiErrorBody { detail: string; }


// ── Reality Status Labels (§2.4) ──────────────────────────────────────────

export type RealityStatus =
  | "PRODUCTION"
  | "INTEGRATED_PARTIAL"
  | "TEST_ONLY"
  | "PROPOSED"
  | "DEFERRED"
  | "RESEARCH"
  | "RETIRED";


// ── Typed Uncertainty (§3) ────────────────────────────────────────────────

export type UncertaintyKind =
  | "unknown"
  | "insufficient_evidence"
  | "stale_evidence"
  | "disagreement"
  | "model_limitation"
  | "conflicting_owner_state";


// ── Evidence Types ────────────────────────────────────────────────────────

export type EvidenceKind =
  | "JOURNAL_ENTRY"
  | "PLAN_CREATED"
  | "PLAN_STEP"
  | "OUTCOME_REPORTED"
  | "RESEARCH_DRAFT"
  | "TALK_TURN"
  | "MODEL_RESPONSE"
  | "USER_CORRECTION"
  | "DECISION";

export interface EvidenceRef {
  kind: EvidenceKind;
  id: string;
  excerpt: string;
  rank: number;
}


// ── Talk Response View ────────────────────────────────────────────────────

export interface CognitiveClaim {
  claim_text: string;
  claim_kind: "observed" | "inferred" | "hypothesis";
  source_refs: string[];
  confidence: number;
  uncertainty_kind: UncertaintyKind | null;
}

export interface TalkResponseView {
  direct_response: string;
  observed: string[];
  inferred: string[];
  hypotheses: string[];
  uncertainty: string[];
  next_move: string | null;
  memory_candidates: string[];
  source_refs: string[];
}


// ── Capability Response ───────────────────────────────────────────────────

export interface CapabilityResponse {
  provider_name: string;
  provider_available: boolean;
  model: string | null;
  daily_budget_remaining: number;
  known_limitations: string[];
}


// ── SSE Event Types (§6.4 — versioned discriminated union) ────────────────

export interface TalkSSEEnvelope<T extends TalkSSEEventType = TalkSSEEventType> {
  schema_version: "1.0";
  event_id: string;
  request_id: string;
  trace_id?: string;
  sequence: number;
  occurred_at: string;  // ISO 8601
  type: T;
  data: TalkSSEEventData[T];
}

export type TalkSSEEventType =
  | "talk.scope.resolved"
  | "talk.accepted"
  | "talk.chunk"
  | "talk.validated"
  | "talk.failed"
  | "talk.cancelled"
  | "memory.candidate"
  | "workflow.proposed";

export interface TalkSSEEventData {
  "talk.scope.resolved": {
    scope_id: string;
    sharing_boundary: string;
  };
  "talk.accepted": {
    turn_event_id: string;
    model_run_id: string;
  };
  "talk.chunk": {
    text: string;
    is_final: boolean;
  };
  "talk.validated": {
    model_run_id: string;
    response_event_id: string;
    schema_valid: boolean;
    verification_verdict: "PASS" | "WARN" | "BLOCK";
  };
  "talk.failed": {
    code: string;
    retryable: boolean;
    reason?: string;
  };
  "talk.cancelled": {
    model_run_id: string;
    reason: string;
  };
  "memory.candidate": {
    candidate_id: string;
    status: string;
    requires_owner_approval: boolean;
  };
  "workflow.proposed": {
    workflow_id: string;
    state: string;
    requires_approval: boolean;
  };
}


// ── Scope Envelope (client-side reference) ────────────────────────────────

export interface ScopeEnvelopeView {
  scope_id: string;
  surface: string;
  sharing_boundary: string;
  memory_write_policy: string;
  sensitivity_ceiling: string;
}


// ── Belief View ───────────────────────────────────────────────────────────

export type BeliefStatus =
  | "candidate"
  | "supported"
  | "contested"
  | "contradicted"
  | "owner_corrected"
  | "stale"
  | "retracted";

export interface BeliefView {
  id: string;
  kind: string;
  status: BeliefStatus;
  claim_text: string;
  domain: string;
  confidence: number;
  evidence_for: string[];
  evidence_against: string[];
  owner_correction_text: string | null;
  created_at: string;
  updated_at: string;
}


// ── Attention Item View ───────────────────────────────────────────────────

export type AttentionItemStatus =
  | "candidate"
  | "active"
  | "snoozed"
  | "dismissed"
  | "resolved"
  | "expired"
  | "superseded";

export interface AttentionItemView {
  id: string;
  title: string;
  description: string;
  status: AttentionItemStatus;
  computed_score: number;
  deadline: string | null;
  created_at: string;
}
