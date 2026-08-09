import type { V197GlowAward, V197GlowSummary } from "./v197Rewards";

export interface V197Profile {
  chosen_name?: string | null;
  timezone?: string | null;
  locale?: string | null;
  writing_preference?: "default" | "roman" | "script";
  sound_enabled?: boolean;
  reduced_effects?: boolean;
  default_boundary?: string;
}

export interface V197Preferences extends V197Profile {
  active_orbit_id?: string | null;
  omega_enabled?: boolean;
}

export interface V197Health {
  status: string;
  ai_provider: "disabled" | "openai" | string;
}

export interface V197Orbit {
  id: string;
  title: string;
  kind: string;
  description?: string | null;
  status: string;
  created_at?: string;
}

export interface V197Session {
  id: string;
  email: string;
  profile: V197Profile;
  orbit: V197Orbit;
}

export interface V197OwnerState {
  active_systems: number;
  outcomes_returned: number;
  insights_evolving: number;
  open_questions: number;
  research_staged: number;
  plans_active: number;
  live_status: string;
}

export interface V197MapNode {
  id: string;
  title: string;
  kind: string;
  orbit_id: string | null;
  active: boolean;
  counts: Record<string, number>;
}

export interface V197MapSummary {
  provenance_label: string;
  counts: Array<{ key: string; label: string; count: number }>;
  nodes: V197MapNode[];
}

export interface V197OrbitsSummary {
  provenance_label: string;
  orbits: Array<V197Orbit & { counts: Record<string, number> }>;
}

export interface V197Timeline {
  provenance_label: string;
  items: Array<{
    id: string;
    kind: string;
    title: string;
    body: string;
    created_at: string;
    provenance_label: string;
    route: string;
    lane?: "past" | "present" | "future" | "prediction";
    due_at?: string | null;
  }>;
}

export interface V197Insights {
  provenance_label: string;
  counts: Record<string, number>;
  claims: Array<Record<string, unknown>>;
  contradictions: Array<Record<string, unknown>>;
  predictions: Array<Record<string, unknown>>;
  review_queue: Array<Record<string, unknown>>;
  feasibility?: Array<Record<string, unknown>>;
}

export interface V197SystemSnapshot {
  slug: string;
  title: string;
  definition: string;
  orbit_id: string;
  questions: string[];
  checklist: string[];
  progress_percent: number;
  progress_sources: {
    completed_actions: number;
    total_actions: number;
    action_completion_percent: number;
    goal_progress_percent: number;
    latest_diagnostic_score: number;
    glow_points: number;
    formula: string;
  };
  active_goal_count: number;
  goals: Array<Record<string, unknown>>;
  actions: Array<{
    id: string;
    title: string;
    status: string;
    due_at: string | null;
    effort_minutes: number | null;
  }>;
  blockers: string[];
  next_move: { kind: string; id: string | null; title: string };
  prediction: {
    if_ignored: string;
    if_followed: string;
    basis: Record<string, number>;
    provenance_label: string;
  };
}

export interface V197SystemsSnapshot {
  provenance_label: string;
  systems: V197SystemSnapshot[];
}

export interface V197TodayDimension {
  score: number;
  sources: Record<string, number | null>;
  calculation: string;
}

export interface V197TodaySnapshot {
  date: string;
  day_label: string;
  local_time: string;
  timezone: string;
  daypart: string;
  body: V197TodayDimension;
  mind: V197TodayDimension;
  life: V197TodayDimension;
  glow_today: number;
  active_systems: Array<Record<string, unknown>>;
  active_goals: Array<Record<string, unknown>>;
  active_plans: Array<Record<string, unknown>>;
  scheduled_today: Array<Record<string, unknown>>;
  completed_today: Array<Record<string, unknown>>;
  missed_today: Array<Record<string, unknown>>;
  daily_quest: Record<string, unknown>;
  next_move: { kind: string; id: string; title: string; scheduled_for?: string | null } | null;
  latest_insight: Record<string, unknown> | null;
  latest_timeline_event: Record<string, unknown> | null;
  return_check: Record<string, unknown> | null;
  provenance_label: string;
}

export interface V197MapGraph {
  generated_at: string;
  provenance_label: string;
  counts: Record<string, number>;
  nodes: Array<{
    id: string;
    kind: string;
    label: string;
    parent_id: string | null;
    status: string;
    data: Record<string, unknown>;
  }>;
  edges: Array<{ id: string; source: string; target: string; kind: string }>;
  future_paths: Array<Record<string, unknown>>;
}

export interface V197GlowScoreboard {
  scope: string;
  period: string;
  provenance_label: string;
  rows: Array<{
    rank: number;
    system_slug: string;
    system_title: string;
    score: number;
  }>;
}

export interface V197TalkThreadRow {
  id: string;
  who: "user" | "nur";
  text: string | null;
  structured_payload: Record<string, unknown>;
  created_at: string;
}

export interface V197TalkOutput {
  direct_response: string;
  observed: string[];
  inferred: string[];
  hypotheses: string[];
  uncertainty: string[];
  next_move: string;
  memory_candidates: string[];
  source_refs: string[];
}

export interface V197TalkResult {
  turn_event_id: string;
  response_event_id: string;
  model_run_id: string;
  provider: string;
  provider_available: boolean;
  provider_reason: string | null;
  output: V197TalkOutput;
  verification: { verdict: string; schema_valid?: boolean; source_refs_valid?: boolean };
  idempotent_replay?: boolean;
}

export interface V197JournalEntry {
  id: string;
  body: string;
  orbit_id: string | null;
  event_id: string | null;
  created_at: string;
}

export interface V197PlanStep {
  id: string;
  title: string;
  body: string | null;
  position: number;
  done: boolean;
  done_at: string | null;
  experiment_id: string | null;
}

export interface V197Plan {
  id: string;
  title: string;
  status: string;
  orbit_id: string | null;
  steps: V197PlanStep[];
}

export interface V197EventResult {
  event: {
    id: string;
    event_kind: string;
    content_text: string | null;
    structured_payload: Record<string, unknown>;
    orbit_id: string | null;
    created_at: string;
  };
}

export interface V197Outcome {
  id: string;
  observed_result: string;
  plan_step_id: string | null;
  created_at: string;
}

export interface V197ResearchBrief {
  id: string;
  question: string;
  summary: string | null;
  status: string;
  provider_status: string;
  created_at: string;
}

export interface V197ProjectSummaryRow {
  id: string;
  orbit_id: string;
  title: string;
  objective: string;
  status: string;
  system_slug: string | null;
  deadline: string | null;
  budget_cents: number | null;
  task_counts: Record<string, number>;
  verified_evidence: number;
}

export interface V197ProjectSummary {
  provenance_label: string;
  counts: { projects: number; active: number; blocked_tasks: number };
  projects: V197ProjectSummaryRow[];
}

export interface V197LiveUniverse {
  generated_at: string;
  provenance_label: string;
  owner: {
    id: string;
    email: string;
    chosen_name: string | null;
    timezone: string;
    locale: string;
    writing_preference: string;
    default_boundary: string;
  };
  state: {
    summary: string;
    source_count: number;
    confidence: number;
    confidence_kind: "source_coverage_not_truth_probability";
    last_updated: string;
    today: V197TodaySnapshot;
    provenance_label: string;
  };
  active_systems: V197SystemSnapshot[];
  active_goals: Array<Record<string, unknown>>;
  active_objectives: Array<Record<string, unknown>>;
  active_plans: Array<Record<string, unknown>>;
  people_orbits: Array<Record<string, unknown>>;
  group_orbits: Array<Record<string, unknown>>;
  projects: Array<Record<string, unknown>>;
  latest_insights: Array<Record<string, unknown>>;
  timeline_highlights: Array<Record<string, unknown>>;
  open_loops: Array<Record<string, unknown>>;
  next_moves: Array<Record<string, unknown>>;
  glow: Record<string, unknown>;
  signals: Array<Record<string, unknown>>;
  community: {
    live_connected: boolean;
    bounded_rooms_connected?: boolean;
    external_public_feed_connected?: boolean;
    status: string;
    room_count?: number;
    rooms?: Array<Record<string, unknown>>;
    note_count: number;
    latest_note: Record<string, unknown> | null;
    honest_state: string;
  };
  what_changed: Array<Record<string, unknown>>;
}

export interface V197CommunityRoom {
  id: string;
  owner_user_id: string;
  title: string;
  description: string | null;
  room_kind: "GROUP" | "COUNCIL" | "SYSTEM" | "PROJECT" | "COMMUNITY";
  system_slug: string | null;
  language_tag: string;
  status: "ACTIVE" | "ARCHIVED" | "CLOSED";
  is_demo: boolean;
  current_user_role: string;
  privacy: string;
  created_at: string;
  updated_at: string;
}

export interface V197CommunityGlowNote {
  awarded_points: number;
  status: "AWARDED" | "GLOW_GATED" | "GLOW_UNAVAILABLE";
  note?: string;
  transaction_id?: string;
  idempotent_replay?: boolean;
}

export interface V197CommunityMessage {
  id: string;
  room_id: string;
  owner_user_id: string;
  body: string;
  language_tag: string;
  provenance_label: string;
  is_demo: boolean;
  created_at: string;
  glow?: V197CommunityGlowNote;
}

export interface V197CommunityPost {
  id: string;
  room_id: string;
  owner_user_id: string;
  title: string;
  body: string;
  language_tag: string;
  provenance_label: string;
  is_demo: boolean;
  created_at: string;
  glow?: V197CommunityGlowNote;
}

export interface V197CommunityComment {
  id: string;
  room_id: string;
  post_id: string;
  parent_comment_id: string | null;
  owner_user_id: string;
  body: string;
  language_tag: string;
  is_demo: boolean;
  created_at: string;
  glow?: V197CommunityGlowNote;
}

export interface V197CommunityRoomSummary {
  room: V197CommunityRoom;
  counts: {
    messages: number;
    posts: number;
    comments: number;
    positions: number;
    decisions: number;
    members: number | null;
  };
  truth_state: string;
  external_public_feed: string;
}

export interface V197CapsuleSource {
  source_id: string;
  source_kind: string;
  representation: string;
  title: string;
  body: string;
}

export interface V197CapsuleView {
  capsule_id: string;
  state: "ACTIVE" | "REVOKED" | "EXPIRED" | string;
  title: string;
  purpose: string;
  owner_display: string;
  capability: string;
  expires_at: string | null;
  recipient_instructions: string | null;
  safety_copy: string;
  included: V197CapsuleSource[];
  excluded_summary: Array<Record<string, unknown>>;
  grant_id: string | null;
}

export interface V197CapsuleAnswer {
  question: string;
  answer_text: string;
  answer_mode: string;
  source_refs: string[];
  confidence: number | null;
  policy_explanation: string | null;
  created_at: string;
}

export interface V197OwnedCapsule {
  id: string;
  orbit_id: string;
  title: string;
  purpose: string;
  capability: string;
  expires_at: string | null;
  revoked_at: string | null;
  version: number;
  created_at: string;
}

export type V197MemoryType =
  | "EPISODIC"
  | "SEMANTIC"
  | "PROCEDURAL"
  | "SOCIAL"
  | "EVIDENCE"
  | "SELF"
  | "GOAL"
  | "META_COGNITIVE"
  | "ADAPTIVE_INTERFACE";

export type V197MemorySensitivity = "LOW" | "PRIVATE" | "SENSITIVE";

export interface V197MemoryCandidate {
  id: string;
  orbit_id: string | null;
  candidate_text: string;
  original_text: string;
  memory_type: V197MemoryType | string;
  provenance_label: string;
  confidence: number;
  sensitivity: V197MemorySensitivity | string;
  status: string;
  review_note: string | null;
  approved_memory_id: string | null;
  created_at: string;
  updated_at: string;
}

export interface V197Memory {
  id: string;
  orbit_id: string | null;
  memory_type: V197MemoryType | string;
  canonical_text: string;
  structured_value: Record<string, unknown>;
  provenance_label: string;
  confidence: number;
  sensitivity: V197MemorySensitivity | string;
  status: string;
  version: number;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface V197MemoryCreate {
  canonical_text: string;
  structured_value?: Record<string, unknown>;
  orbit_id?: string | null;
  memory_type?: V197MemoryType;
  sensitivity?: V197MemorySensitivity;
  confidence?: number;
  expires_at?: string | null;
}

export interface V197MemoryPatch {
  canonical_text?: string;
  structured_value?: Record<string, unknown>;
  memory_type?: V197MemoryType;
  sensitivity?: V197MemorySensitivity;
  confidence?: number;
  correction_reason?: string;
}

export type V197TeachNURContributionKind =
  | "FACT"
  | "LIVED_EXPERIENCE"
  | "CORRECTION"
  | "COUNTEREXAMPLE"
  | "LANGUAGE"
  | "RESEARCH"
  | "EXPERTISE"
  | "MISUNDERSTANDING"
  | "OUTCOME_EVIDENCE";

export type V197TeachNURConsentScope = "PRIVATE_OWNER" | "DEIDENTIFIED_RESEARCH";
export type V197TeachNURReviewAction =
  | "EDIT"
  | "APPROVE"
  | "REJECT"
  | "START_CANARY"
  | "ACTIVATE"
  | "ROLLBACK"
  | "WITHDRAW_CONSENT";

export interface V197TeachNURSourceRef {
  kind: "OWNER_REFERENCE" | "URL" | "DOI" | "MEMORY" | "OUTCOME" | "RESEARCH_NOTE";
  reference: string;
}

export interface V197TeachNURContributionCreate {
  contribution_kind: V197TeachNURContributionKind;
  content: string;
  orbit_id?: string | null;
  language_tag?: string;
  consent_scope: V197TeachNURConsentScope;
  consent_granted: boolean;
  consent_policy_version?: "teach-nur-v1";
  sensitivity?: V197MemorySensitivity | null;
  confidence?: number;
  source_refs?: V197TeachNURSourceRef[];
}

export interface V197TeachNURContribution {
  id: string;
  orbit_id: string | null;
  contribution_kind: V197TeachNURContributionKind | string;
  content: string;
  language_tag: string;
  consent_scope: V197TeachNURConsentScope | string;
  consent_granted: boolean;
  provenance_label: string;
  sensitivity: string;
  confidence: number;
  status: string;
  reviewed_at: string | null;
  created_at: string;
  updated_at: string;
  model_training_status: "NOT_AUTHORIZED";
  institutional_promotion_status: "OWNER_SCOPED_ONLY";
}

export interface V197BillingFeature {
  feature_key: string;
  allowed: boolean;
  usage_limit: number | null;
}

export interface V197BillingPlan {
  code: string;
  name: string;
  description: string;
  price_minor: number;
  currency: string;
  billing_interval: string;
  seat_cap: number | null;
  seats_remaining: number | null;
  is_free: boolean;
  active: boolean;
  legal_copy_version: string;
  features: V197BillingFeature[];
}

export interface V197BillingSubscription {
  id: string;
  plan_code: string;
  provider: string;
  provider_status: string;
  status: string;
  is_test: boolean;
  current_period_start: string | null;
  current_period_end: string | null;
  cancel_at_period_end: boolean;
  cancelled_at: string | null;
  ended_at: string | null;
  latest_receipt_url: string | null;
}

export interface V197BillingState {
  subscription: V197BillingSubscription | null;
  entitlements: Array<V197BillingFeature & {
    usage_consumed: number;
    valid_until: string | null;
    reason: string;
    projection_version: number;
  }>;
  refunds: Array<{
    id: string;
    amount_minor: number | null;
    currency: string | null;
    status: string;
    created_at: string;
  }>;
  provider_configured: boolean;
  portal_available: boolean;
  cancellation_note: string;
  terms_url: string | null;
  privacy_url: string | null;
  refund_policy_url: string | null;
}

export interface V197BillingCheckout {
  session_id: string;
  plan_code: string;
  provider: string;
  checkout_url: string;
  status: string;
  is_test: boolean;
  reservation_expires_at: string;
  renews_automatically: boolean;
}

export interface V197BillingPortal {
  url: string;
  expires_at: string;
  purpose: "MANAGE_CANCEL_INVOICES";
}

export interface V197OrbitSource {
  id: string;
  source_kind: string;
  source_id: string;
  inclusion_mode: string;
  created_at: string;
}

export interface V197CapsuleCreate {
  title: string;
  purpose: string;
  capability?: "READ_ONLY" | "ASK_SCOPED_QUESTIONS" | string;
  recipient_instructions?: string | null;
  expires_at?: string | null;
  orbit_source_ids: string[];
  representations?: Record<string, string>;
}

export interface V197CapsuleGrant {
  id: string;
  capsule_id: string;
  recipient_user_id: string | null;
  capability: string;
  expires_at: string | null;
  revoked_at: string | null;
  last_accessed_at: string | null;
}

export interface V197CapsuleAuditEvent {
  event_kind: string;
  actor_user_id: string | null;
  grant_id: string | null;
  created_at: string;
  meta: Record<string, unknown>;
}

export interface V197OmegaDashboard {
  statuses: Record<string, string>;
  claims: Array<Record<string, unknown>>;
  contradictions: Array<Record<string, unknown>>;
  predictions: Array<Record<string, unknown>>;
  consolidation_runs: Array<Record<string, unknown>>;
  learning_proposals: Array<Record<string, unknown>>;
  recent_experiences: Array<Record<string, unknown>>;
  review_queue: Array<Record<string, unknown>>;
}

export interface V197OmegaScheduler {
  enabled: boolean;
  scheduled_consolidation: boolean;
  interval_hours: number;
  worker_mode: string;
  last_consolidation_run_at: string | null;
  last_consolidation_status: string;
  provenance_label: string;
}

export interface V197Consultation {
  id: string;
  owner_user_id: string;
  room_id: string | null;
  orbit_id: string | null;
  system_slug: string | null;
  title: string;
  question: string;
  purpose: string;
  desired_outcome: string;
  scope_statement: string;
  current_stage: "ORIENT" | "GATHER" | "MAP" | "MOVE" | "RETURN";
  status: "ACTIVE" | "COMPLETED" | "CLOSED";
  is_demo: boolean;
  current_user_role: string;
  privacy: string;
  created_at: string;
  updated_at: string;
}

export interface V197ConsultationContribution {
  id: string;
  consultation_id: string;
  owner_user_id: string;
  contribution_type: string;
  body: string;
  evidence: Array<Record<string, unknown> | string>;
  language_tag: string;
  provenance_label: string;
  is_demo: boolean;
  created_at: string;
}

export interface V197ConsultationStage {
  id: string;
  consultation_id: string;
  owner_user_id: string;
  stage: string;
  stage_payload: Record<string, unknown>;
  provenance_label: string;
  created_at: string;
  glow?: Record<string, unknown> | null;
}

export interface V197ConsultationDetail {
  consultation: V197Consultation;
  completed_stages: V197ConsultationStage[];
  contributions: V197ConsultationContribution[];
  stage_order: string[];
  next_stage: string | null;
  what_nur_may_be_wrong_about: string;
}

export interface V197BridgeSnapshot {
  session: V197Session;
  health?: V197Health | null;
  live?: V197LiveUniverse | null;
  ownerState: V197OwnerState | null;
  map: V197MapSummary | null;
  orbits: V197OrbitsSummary | null;
  timeline: V197Timeline | null;
  insights: V197Insights | null;
  today?: V197TodaySnapshot | null;
  systems?: V197SystemsSnapshot | null;
  mapGraph?: V197MapGraph | null;
  scoreboard?: V197GlowScoreboard | null;
  preferences: V197Preferences | null;
  talkThread: V197TalkThreadRow[];
  journal: V197JournalEntry[];
  plans: V197Plan[];
  glow: V197GlowSummary;
  researchBriefs: V197ResearchBrief[];
  projects?: V197ProjectSummary | null;
  communityRooms?: V197CommunityRoom[];
  councilSummary?: V197CommunityRoomSummary | null;
  communityMessages?: V197CommunityMessage[];
}

export class V197ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string | null = null,
  ) {
    super(message);
  }
}

const REQUEST_TIMEOUT_MS = 12_000;

function cookie(name: string): string | null {
  const prefix = `${name}=`;
  const row = document.cookie.split(";").map(value => value.trim()).find(value => value.startsWith(prefix));
  return row ? decodeURIComponent(row.slice(prefix.length)) : null;
}

export class V197ApiClient {
  private async request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const controller = new AbortController();
    const timedOut = { value: false };
    const timeout = window.setTimeout(() => {
      timedOut.value = true;
      controller.abort();
    }, REQUEST_TIMEOUT_MS);
    const abortFromCaller = () => controller.abort();
    init.signal?.addEventListener("abort", abortFromCaller, { once: true });
    try {
      const response = await fetch(`/api/v1${path}`, {
        ...init,
        credentials: "include",
        signal: controller.signal,
        headers: {
          accept: "application/json",
          ...(init.body ? { "content-type": "application/json" } : {}),
          ...init.headers,
        },
      });
      if (response.status === 204) return undefined as T;
      const raw = await response.text();
      let body: unknown;
      try {
        body = raw ? JSON.parse(raw) : undefined;
      } catch {
        throw new V197ApiError(`NUR API returned an invalid response for ${path}.`, response.status);
      }
      if (!response.ok) {
        const detail = typeof body === "object" && body && "detail" in body
          ? String((body as { detail: unknown }).detail)
          : `${path} returned ${response.status}`;
        throw new V197ApiError(detail, response.status);
      }
      return body as T;
    } catch (error) {
      if (error instanceof V197ApiError) throw error;
      if (timedOut.value) {
        throw new V197ApiError(`NUR API did not respond within ${REQUEST_TIMEOUT_MS / 1000} seconds. Check API readiness.`, 0);
      }
      if (init.signal?.aborted) throw new V197ApiError("The NUR request was cancelled.", 0);
      throw new V197ApiError("NUR API is unreachable. Check that RUN_NUR.sh reports API ready.", 0);
    } finally {
      window.clearTimeout(timeout);
      init.signal?.removeEventListener("abort", abortFromCaller);
    }
  }

  private writeHeaders(extra: Record<string, string> = {}): HeadersInit {
    const csrf = cookie("nur_csrf");
    if (!csrf) throw new V197ApiError("The local session is missing its CSRF token.", 401);
    return { "X-CSRF-Token": csrf, ...extra };
  }

  get<T>(path: string): Promise<T> {
    return this.request<T>(path);
  }

  post<T>(path: string, body: unknown, csrf = true): Promise<T> {
    return this.request<T>(path, {
      method: "POST",
      headers: csrf ? this.writeHeaders() : {},
      body: JSON.stringify(body),
    });
  }

  patch<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PATCH",
      headers: this.writeHeaders(),
      body: JSON.stringify(body),
    });
  }

  /** Added for Map's layout write, which replaces a whole node set at once. */
  put<T>(path: string, body: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "PUT",
      headers: this.writeHeaders(),
      body: JSON.stringify(body),
    });
  }

  delete<T>(path: string, body?: unknown): Promise<T> {
    return this.request<T>(path, {
      method: "DELETE",
      headers: this.writeHeaders(),
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  }

  async register(payload: { chosen_name: string; email: string; password: string; consent: boolean }): Promise<V197Session> {
    const created = await this.post<V197Session>("/auth/register", payload, false);
    const session = await this.session();
    if (!session) throw new V197ApiError("Your Orbit was created, but the browser session could not be verified. Please sign in.", 401);
    if (created.id !== session.id) throw new V197ApiError("The active browser session does not match the Orbit that was just created.", 409);
    return session;
  }

  async login(payload: { email: string; password: string }): Promise<V197Session> {
    await this.post<{ ok: boolean }>("/auth/login", payload, false);
    const session = await this.session();
    if (!session) throw new V197ApiError("The session was not established.", 401);
    return session;
  }

  logout(): Promise<void> {
    return this.post<void>("/auth/logout", {});
  }

  async session(): Promise<V197Session | null> {
    try {
      return await this.get<V197Session>("/auth/me");
    } catch (error) {
      if (error instanceof V197ApiError && error.status === 401) return null;
      throw error;
    }
  }

  async health(): Promise<V197Health> {
    const response = await fetch("/healthz", {
      credentials: "include",
      headers: { accept: "application/json" },
    });
    if (!response.ok) throw new V197ApiError(`healthz returned ${response.status}`, response.status);
    return response.json() as Promise<V197Health>;
  }

  event(payload: {
    event_kind: string;
    content_text?: string;
    structured_payload?: Record<string, unknown>;
    orbit_id?: string | null;
  }): Promise<V197EventResult> {
    return this.post<V197EventResult>("/cognition/events", payload);
  }

  talk(payload: {
    message: string;
    orbit_id?: string | null;
    locale: string;
    writing_preference: string;
    mode?: string;
  }): Promise<V197TalkResult> {
    return this.post<V197TalkResult>("/cognition/talk", payload);
  }

  createJournal(body: string, orbitId: string | null): Promise<V197JournalEntry> {
    return this.post<V197JournalEntry>("/journal", { body, orbit_id: orbitId });
  }

  createPlan(title: string, orbitId: string | null): Promise<V197Plan> {
    return this.post<V197Plan>("/plans", {
      title,
      orbit_id: orbitId,
      steps: [{ title: `Make one visible move: ${title}`, position: 0 }],
    });
  }

  patchPlanStep(stepId: string, body: { done?: boolean; title?: string }): Promise<V197PlanStep> {
    return this.patch<V197PlanStep>(`/plan-steps/${encodeURIComponent(stepId)}`, body);
  }

  createOutcome(observedResult: string, stepId: string): Promise<V197Outcome> {
    return this.post<V197Outcome>("/outcomes", {
      observed_result: observedResult,
      plan_step_id: stepId,
      structured_measurements: {},
    });
  }

  rewardGlow(payload: {
    event_type: string;
    source_kind: string;
    source_id: string;
    orbit_id?: string | null;
    idempotency_key: string;
  }): Promise<V197GlowAward> {
    return this.post<V197GlowAward>("/glow/rewards", payload);
  }

  patchPreferences(payload: Partial<V197Preferences>): Promise<V197Preferences> {
    return this.patch<V197Preferences>("/profile/preferences", payload);
  }

  memoryCandidates(status?: string, limit = 100): Promise<V197MemoryCandidate[]> {
    const query = new URLSearchParams({ limit: String(limit) });
    if (status) query.set("status", status);
    return this.get<V197MemoryCandidate[]>(`/memory-candidates?${query.toString()}`);
  }

  approveMemoryCandidate(
    candidateId: string,
    payload: { memory_type?: V197MemoryType; sensitivity?: V197MemorySensitivity; review_note?: string | null } = {},
  ): Promise<V197Memory> {
    return this.post<V197Memory>(`/memory-candidates/${encodeURIComponent(candidateId)}/approve`, payload);
  }

  rejectMemoryCandidate(candidateId: string, reviewNote?: string | null): Promise<V197MemoryCandidate> {
    return this.post<V197MemoryCandidate>(
      `/memory-candidates/${encodeURIComponent(candidateId)}/reject`,
      { review_note: reviewNote ?? null },
    );
  }

  correctMemoryCandidate(candidateId: string, payload: {
    canonical_text: string;
    correction_reason: string;
    memory_type?: V197MemoryType;
    sensitivity?: V197MemorySensitivity;
  }): Promise<V197MemoryCandidate> {
    return this.post<V197MemoryCandidate>(`/memory-candidates/${encodeURIComponent(candidateId)}/correct`, payload);
  }

  memories(options: { orbitId?: string | null; includeRetired?: boolean; limit?: number } = {}): Promise<V197Memory[]> {
    const query = new URLSearchParams({
      include_retired: String(options.includeRetired ?? false),
      limit: String(options.limit ?? 100),
    });
    if (options.orbitId) query.set("orbit_id", options.orbitId);
    return this.get<V197Memory[]>(`/memories?${query.toString()}`);
  }

  createMemory(payload: V197MemoryCreate): Promise<V197Memory> {
    return this.post<V197Memory>("/memories", payload);
  }

  patchMemory(memoryId: string, payload: V197MemoryPatch): Promise<V197Memory> {
    return this.patch<V197Memory>(`/memories/${encodeURIComponent(memoryId)}`, payload);
  }

  deleteMemory(memoryId: string): Promise<void> {
    return this.delete<void>(`/memories/${encodeURIComponent(memoryId)}`);
  }

  teachNURContributions(status?: string, limit = 100): Promise<V197TeachNURContribution[]> {
    const query = new URLSearchParams({ limit: String(limit) });
    if (status) query.set("status", status);
    return this.get<V197TeachNURContribution[]>(`/teach-nur/contributions?${query.toString()}`);
  }

  createTeachNURContribution(
    payload: V197TeachNURContributionCreate,
    idempotencyKey: string,
  ): Promise<V197TeachNURContribution> {
    return this.request<V197TeachNURContribution>("/teach-nur/contributions", {
      method: "POST",
      headers: this.writeHeaders({ "Idempotency-Key": idempotencyKey }),
      body: JSON.stringify(payload),
    });
  }

  reviewTeachNURContribution(
    contributionId: string,
    payload: { action: V197TeachNURReviewAction; edited_text?: string; review_note?: string | null },
    idempotencyKey: string,
  ): Promise<V197TeachNURContribution> {
    return this.request<V197TeachNURContribution>(
      `/teach-nur/contributions/${encodeURIComponent(contributionId)}/review`,
      {
        method: "POST",
        headers: this.writeHeaders({ "Idempotency-Key": idempotencyKey }),
        body: JSON.stringify(payload),
      },
    );
  }

  billingPlans(): Promise<V197BillingPlan[]> {
    return this.get<V197BillingPlan[]>("/billing/plans");
  }

  billingSubscription(): Promise<V197BillingState> {
    return this.get<V197BillingState>("/billing/subscription");
  }

  billingCheckout(planCode: string, idempotencyKey: string): Promise<V197BillingCheckout> {
    return this.request<V197BillingCheckout>("/billing/checkout", {
      method: "POST",
      headers: this.writeHeaders({ "Idempotency-Key": idempotencyKey }),
      body: JSON.stringify({ plan_code: planCode }),
    });
  }

  billingPortal(): Promise<V197BillingPortal> {
    return this.post<V197BillingPortal>("/billing/portal", {});
  }

  createResearchBrief(question: string, orbitId: string | null): Promise<V197ResearchBrief> {
    return this.post<V197ResearchBrief>("/research/briefs", { question, orbit_id: orbitId });
  }

  createOrbit(title: string): Promise<V197Orbit> {
    return this.post<V197Orbit>("/orbits", { title, kind: "PROJECT", description: "Created from the V197 Systems field." });
  }

  communityRooms(): Promise<V197CommunityRoom[]> {
    return this.get<V197CommunityRoom[]>("/community/rooms");
  }

  createCommunityRoom(title: string, roomKind: "GROUP" | "COUNCIL"): Promise<V197CommunityRoom> {
    return this.post<V197CommunityRoom>("/community/rooms", { title, room_kind: roomKind });
  }

  postCommunityMessage(roomId: string, body: string, languageTag: string): Promise<V197CommunityMessage> {
    return this.post<V197CommunityMessage>(
      `/community/rooms/${encodeURIComponent(roomId)}/messages`,
      { body, language_tag: languageTag },
    );
  }

  communityRoomSummary(roomId: string): Promise<V197CommunityRoomSummary> {
    return this.get<V197CommunityRoomSummary>(`/community/rooms/${encodeURIComponent(roomId)}/summary`);
  }

  communityMessages(roomId: string): Promise<V197CommunityMessage[]> {
    return this.get<V197CommunityMessage[]>(`/community/rooms/${encodeURIComponent(roomId)}/messages`);
  }

  communityPosts(roomId: string): Promise<V197CommunityPost[]> {
    return this.get<V197CommunityPost[]>(`/community/rooms/${encodeURIComponent(roomId)}/posts`);
  }

  createCommunityPost(roomId: string, title: string, body: string, languageTag: string): Promise<V197CommunityPost> {
    return this.post<V197CommunityPost>(`/community/rooms/${encodeURIComponent(roomId)}/posts`, {
      title, body, language_tag: languageTag,
    });
  }

  communityComments(roomId: string, postId: string): Promise<V197CommunityComment[]> {
    return this.get<V197CommunityComment[]>(`/community/rooms/${encodeURIComponent(roomId)}/posts/${encodeURIComponent(postId)}/comments`);
  }

  createCommunityComment(roomId: string, postId: string, body: string, languageTag: string): Promise<V197CommunityComment> {
    return this.post<V197CommunityComment>(`/community/rooms/${encodeURIComponent(roomId)}/posts/${encodeURIComponent(postId)}/comments`, {
      body, language_tag: languageTag,
    });
  }

  createCommunityReaction(roomId: string, targetKind: string, targetId: string, reaction: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/community/rooms/${encodeURIComponent(roomId)}/reactions`, {
      target_kind: targetKind, target_id: targetId, reaction,
    });
  }

  addCommunityMember(roomId: string, email: string): Promise<{ id: string; room_id: string; user_id: string; role: string }> {
    return this.post(`/community/rooms/${encodeURIComponent(roomId)}/members`, { email, role: "MEMBER" });
  }

  createCouncilPosition(roomId: string, position: string): Promise<Record<string, unknown>> {
    return this.post(`/community/rooms/${encodeURIComponent(roomId)}/positions`, { position, evidence: [], is_minority: false });
  }

  createCouncilDecision(roomId: string, decision: string): Promise<Record<string, unknown>> {
    return this.post(`/community/rooms/${encodeURIComponent(roomId)}/decision`, { decision });
  }

  capsuleView(capsuleId: string): Promise<V197CapsuleView> {
    return this.get<V197CapsuleView>(`/capsules/${encodeURIComponent(capsuleId)}/view`);
  }

  askCapsule(capsuleId: string, question: string): Promise<V197CapsuleAnswer> {
    return this.post<V197CapsuleAnswer>(`/capsules/${encodeURIComponent(capsuleId)}/questions`, { question });
  }

  ownedCapsules(): Promise<V197OwnedCapsule[]> {
    return this.get<V197OwnedCapsule[]>("/capsules");
  }

  orbitSources(orbitId: string): Promise<V197OrbitSource[]> {
    return this.get<V197OrbitSource[]>(`/orbits/${encodeURIComponent(orbitId)}/sources`);
  }

  createCapsule(orbitId: string, payload: V197CapsuleCreate): Promise<V197OwnedCapsule> {
    return this.post<V197OwnedCapsule>(`/orbits/${encodeURIComponent(orbitId)}/capsules`, payload);
  }

  grantCapsule(capsuleId: string, payload: {
    recipient_email: string;
    capability?: "READ_ONLY" | "ASK_SCOPED_QUESTIONS" | string;
    expires_at?: string | null;
  }): Promise<V197CapsuleGrant> {
    return this.post<V197CapsuleGrant>(`/capsules/${encodeURIComponent(capsuleId)}/grants`, payload);
  }

  capsuleAudit(capsuleId: string): Promise<V197CapsuleAuditEvent[]> {
    return this.get<V197CapsuleAuditEvent[]>(`/capsules/${encodeURIComponent(capsuleId)}/audit`);
  }

  revokeCapsule(capsuleId: string): Promise<V197OwnedCapsule> {
    return this.post<V197OwnedCapsule>(`/capsules/${encodeURIComponent(capsuleId)}/revoke`, {});
  }

  omegaDashboard(): Promise<V197OmegaDashboard> {
    return this.get<V197OmegaDashboard>("/omega/dashboard");
  }

  omegaScheduler(): Promise<V197OmegaScheduler> {
    return this.get<V197OmegaScheduler>("/omega/scheduler-status");
  }

  omegaReviewQueue(): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>("/omega/review-queue");
  }

  omegaWhyChanged(claimId: string): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(`/omega/claims/${encodeURIComponent(claimId)}/why-changed`);
  }

  omegaEvidence(claimId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/omega/claims/${encodeURIComponent(claimId)}/evidence`);
  }

  consolidateOmega(): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/omega/consolidate", { run_kind: "MANUAL" });
  }

  reviewOmegaItem(reviewId: string, action: "approve" | "reject"): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/omega/review-queue/${encodeURIComponent(reviewId)}/${action}`, {});
  }

  transitionOmegaProposal(proposalId: string, action: "approve" | "reject" | "rollback"): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/omega/learning-proposals/${encodeURIComponent(proposalId)}/${action}`, {});
  }

  resolveOmegaContradiction(contradictionId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/omega/contradictions/${encodeURIComponent(contradictionId)}/resolve`, { status: "RESOLVED" });
  }

  confirmOmegaClaim(claimId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/omega/claims/${encodeURIComponent(claimId)}/confirm`, {});
  }

  retireOmegaClaim(claimId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/omega/claims/${encodeURIComponent(claimId)}/retire`, {});
  }

  omegaExport(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>("/omega/export");
  }

  consultations(): Promise<V197Consultation[]> {
    return this.get<V197Consultation[]>("/consultations");
  }

  consultation(consultationId: string): Promise<V197ConsultationDetail> {
    return this.get<V197ConsultationDetail>(`/consultations/${encodeURIComponent(consultationId)}`);
  }

  createConsultation(payload: {
    title: string;
    question: string;
    purpose: string;
    desired_outcome: string;
    scope_statement: string;
    room_id?: string | null;
    orbit_id?: string | null;
    system_slug?: string | null;
  }): Promise<V197Consultation> {
    return this.post<V197Consultation>("/consultations", payload);
  }

  addConsultationContribution(
    consultationId: string,
    payload: { contribution_type: string; body: string; language_tag: string },
  ): Promise<V197ConsultationContribution> {
    return this.post<V197ConsultationContribution>(
      `/consultations/${encodeURIComponent(consultationId)}/contributions`,
      payload,
    );
  }

  completeConsultationStage(
    consultationId: string,
    stage: string,
    payload: Record<string, unknown>,
  ): Promise<V197ConsultationStage> {
    return this.post<V197ConsultationStage>(
      `/consultations/${encodeURIComponent(consultationId)}/stages/${encodeURIComponent(stage)}`,
      { payload },
    );
  }

  projects(): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>("/projects");
  }

  project(projectId: string): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}`);
  }

  createProject(payload: { title: string; objective: string; system_slug?: string | null }): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/projects", payload);
  }

  projectTasks(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/tasks`);
  }

  createProjectTask(projectId: string, payload: { title: string; acceptance_criteria: string; assigned_role?: string }): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/tasks`, payload);
  }

  patchProjectTask(taskId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.patch<Record<string, unknown>>(`/projects/tasks/${encodeURIComponent(taskId)}`, payload);
  }

  projectRuns(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/runs`);
  }

  proposeProjectRun(projectId: string, payload: { task_id?: string | null; role: string; request_summary: string }): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/runs`, {
      ...payload, tool_policy: {}, budget_cents: 0,
    });
  }

  proposeExecutionRun(projectId: string, payload: {
    role: string; request_summary: string; adapter_key: string;
    task_id?: string | null; agent_id?: string | null; idempotency_key?: string | null;
  }): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/runs`, {
      ...payload, tool_policy: {}, budget_cents: 0,
    });
  }

  projectRunAction(runId: string, action: "approve" | "cancel" | "reject" | "queue" | "retry"): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/runs/${encodeURIComponent(runId)}/${action}`, {});
  }

  projectRun(runId: string): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>(`/projects/runs/${encodeURIComponent(runId)}`);
  }

  executionCapabilities(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>("/projects/execution/capabilities");
  }

  projectAgents(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/agents`);
  }

  createProjectAgent(projectId: string, payload: { name: string; adapter_key: string; allowed_capabilities?: string[] }): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/agents`, payload);
  }

  projectFiles(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/files`);
  }

  async uploadProjectFile(projectId: string, file: File, taskId?: string | null): Promise<Record<string, unknown>> {
    const csrf = cookie("nur_csrf");
    if (!csrf) throw new V197ApiError("The local session is missing its CSRF token.", 401);
    const form = new FormData();
    form.append("upload", file, file.name);
    const query = taskId ? `?task_id=${encodeURIComponent(taskId)}` : "";
    const response = await fetch(`/api/v1/projects/${encodeURIComponent(projectId)}/files${query}`, {
      method: "POST",
      credentials: "include",
      headers: { accept: "application/json", "X-CSRF-Token": csrf },
      body: form,
    });
    const raw = await response.text();
    let body: unknown;
    try {
      body = raw ? JSON.parse(raw) : undefined;
    } catch {
      throw new V197ApiError("NUR returned an invalid upload response.", response.status);
    }
    if (!response.ok) {
      const detail = typeof body === "object" && body && "detail" in body
        ? String((body as { detail: unknown }).detail)
        : `Upload failed (${response.status}).`;
      throw new V197ApiError(detail, response.status);
    }
    return body as Record<string, unknown>;
  }

  verifyProjectFile(fileId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/files/${encodeURIComponent(fileId)}/verify`, {});
  }

  deleteProjectFile(fileId: string): Promise<Record<string, unknown>> {
    return this.request<Record<string, unknown>>(`/projects/files/${encodeURIComponent(fileId)}`, {
      method: "DELETE",
      headers: this.writeHeaders(),
    });
  }

  fileDownloadPath(fileId: string): string {
    return `/api/v1/projects/files/${encodeURIComponent(fileId)}/download`;
  }

  async downloadProjectFile(fileId: string): Promise<Blob> {
    const response = await fetch(this.fileDownloadPath(fileId), {
      method: "GET",
      credentials: "include",
      headers: { accept: "application/octet-stream" },
    });
    if (!response.ok) {
      let detail = `Download failed (${response.status}).`;
      try {
        const body = await response.json() as { detail?: unknown };
        if (body?.detail) detail = String(body.detail);
      } catch {
        /* non-JSON error body */
      }
      throw new V197ApiError(detail, response.status);
    }
    return response.blob();
  }

  projectEvidence(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/evidence`);
  }

  createProjectEvidence(projectId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/evidence`, payload);
  }

  projectReviews(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/reviews`);
  }

  createProjectReview(projectId: string, payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/projects/${encodeURIComponent(projectId)}/reviews`, payload);
  }

  projectArtifacts(projectId: string): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>(`/projects/${encodeURIComponent(projectId)}/artifacts`);
  }

  notificationPreferences(): Promise<Record<string, unknown>> {
    return this.get<Record<string, unknown>>("/notifications/preferences");
  }

  patchNotificationPreferences(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.patch<Record<string, unknown>>("/notifications/preferences", payload);
  }

  notifications(): Promise<Array<Record<string, unknown>>> {
    return this.get<Array<Record<string, unknown>>>("/notifications");
  }

  createReminder(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/notifications/reminders", payload);
  }

  markNotificationRead(notificationId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/notifications/${encodeURIComponent(notificationId)}/read`, {});
  }

  acceptInsight(insightId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/insights/${encodeURIComponent(insightId)}/accept`, {});
  }

  rejectInsight(insightId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/insights/${encodeURIComponent(insightId)}/reject`, {});
  }

  correctInsight(insightId: string, correction: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/insights/${encodeURIComponent(insightId)}/correct`, { correction });
  }

  convertInsightToPlan(insightId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/insights/${encodeURIComponent(insightId)}/convert-to-plan`, {});
  }

  addInsightToTimeline(insightId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>(`/insights/${encodeURIComponent(insightId)}/add-to-timeline`, {});
  }

  saveTodayCheckIn(payload: {
    energy: number;
    pain: number;
    sleep_quality: number;
    nourishment: number;
    movement: number;
    emotional_load: number;
    clarity: number;
    note?: string | null;
  }): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/today/check-in", payload);
  }

  completeTodayAction(actionId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/today/complete-action", { action_id: actionId });
  }

  missTodayAction(actionId: string): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/today/miss-action", { action_id: actionId });
  }

  makeTodayActionEasier(actionId: string, title: string, effortMinutes: number): Promise<Record<string, unknown>> {
    return this.post<Record<string, unknown>>("/today/make-easier", {
      action_id: actionId,
      title,
      effort_minutes: effortMinutes,
    });
  }

  async snapshot(session: V197Session): Promise<V197BridgeSnapshot> {
    const read = async <T>(path: string, fallback: T): Promise<T> => {
      try {
        return await this.get<T>(path);
      } catch {
        return fallback;
      }
    };

    const emptyGlow: V197GlowSummary = {
      balance: 0,
      lifetime_points: 0,
      today_points: 0,
      weekly_points: 0,
      level: 1,
      rank: "Orbit Seed",
      next_unlock: null,
      recent_transactions: [],
      streaks: [],
      achievements: [],
      daily_quest: {},
      weekly_mission: {},
    };
    const [health, live, ownerState, map, orbits, timeline, insights, mapGraph, scoreboard, preferences, talkThread, journal, plans, glow, researchBriefs, projects] = await Promise.all([
      this.health().catch(() => null),
      read<V197LiveUniverse | null>("/universe/live", null),
      read<V197OwnerState | null>("/orbits/current-state", null),
      read<V197MapSummary | null>("/universe/map-summary", null),
      read<V197OrbitsSummary | null>("/universe/orbits-summary", null),
      read<V197Timeline | null>("/universe/timeline", null),
      read<V197Insights | null>("/universe/insights-summary", null),
      read<V197MapGraph | null>("/map", null),
      read<V197GlowScoreboard | null>("/glow/scoreboard", null),
      read<V197Preferences | null>("/profile/preferences", null),
      read<V197TalkThreadRow[]>("/cognition/talk-thread", []),
      read<V197JournalEntry[]>("/journal", []),
      read<V197Plan[]>("/plans", []),
      read<V197GlowSummary>("/glow/summary", emptyGlow),
      read<V197ResearchBrief[]>("/research/briefs", []),
      read<V197ProjectSummary | null>("/projects/summary", null),
    ]);
    const communityRooms = await read<V197CommunityRoom[]>("/community/rooms", []);
    const council = communityRooms.find(room => room.room_kind === "COUNCIL" && room.status === "ACTIVE");
    const councilSummary = council
      ? await read<V197CommunityRoomSummary | null>(`/community/rooms/${encodeURIComponent(council.id)}/summary`, null)
      : null;
    const latestRoom = communityRooms.find(room => room.status === "ACTIVE");
    const communityMessages = latestRoom
      ? await read<V197CommunityMessage[]>(`/community/rooms/${encodeURIComponent(latestRoom.id)}/messages?limit=25`, [])
      : [];

    return {
      session,
      health,
      live,
      ownerState,
      map,
      orbits,
      timeline,
      insights,
      today: live?.state.today ?? null,
      systems: live ? { provenance_label: live.provenance_label, systems: live.active_systems } : null,
      mapGraph,
      scoreboard,
      preferences,
      talkThread,
      journal,
      plans,
      glow,
      researchBriefs,
      projects,
      communityRooms,
      councilSummary,
      communityMessages,
    };
  }
}
