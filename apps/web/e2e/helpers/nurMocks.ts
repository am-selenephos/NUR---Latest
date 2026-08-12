import { type Page, type Route } from "@playwright/test";

const now = new Date().toISOString();

export const mockUser = {
  id: "11111111-1111-1111-1111-111111111111",
  email: "selene@nurapp.dev",
  email_verified: true,
  profile: {
    chosen_name: "Selene",
    timezone: null,
    locale: "en",
    sound_enabled: false,
    reduced_effects: true,
    default_boundary: "PRIVATE_ORBIT",
    active_orbit_id: "22222222-2222-2222-2222-222222222222",
    omega_enabled: true,
    writing_preference: "default",
  },
  orbit: { id: "99999999-9999-9999-9999-999999999999", current_arrival_state: null, active_focus_area: null },
};

export const mockOrbit = {
  id: "22222222-2222-2222-2222-222222222222",
  title: "Quiet Ambition",
  kind: "PROJECT",
  description: "Build without noise",
  status: "ACTIVE",
  created_at: now,
};

export const mockClaim = {
  id: "33333333-3333-3333-3333-333333333333",
  orbit_id: mockOrbit.id,
  claim_text: "Outcome evidence should strengthen planning patterns only after persisted results.",
  claim_type: "PATTERN",
  truth_status: "OBSERVED",
  confidence: 0.82,
  support_count: 2,
  contradiction_count: 0,
  last_supported_at: now,
  last_contradicted_at: null,
  created_at: now,
  updated_at: now,
};

const systemTitles = [
  "Ambition",
  "Rebuild",
  "Creation",
  "Growth",
  "Introspection",
  "Connection",
] as const;

const mockSystems = systemTitles.map((title, index) => {
  const slug = title.toLowerCase();
  return {
    slug,
    title,
    definition: `${title} is held in the persisted owner ledger.`,
    orbit_id: index === 0 ? mockOrbit.id : `system-${slug}`,
    questions: [`What matters inside ${title}?`],
    checklist: [],
    progress_percent: 0,
    progress_sources: {
      completed_actions: 0,
      total_actions: 0,
      action_completion_percent: 0,
      goal_progress_percent: 0,
      latest_diagnostic_score: 0,
      glow_points: 0,
      formula: "Persisted owner evidence only.",
    },
    active_goal_count: 0,
    goals: [],
    actions: [],
    blockers: [],
    next_move: { kind: "NONE", id: null, title: `Choose one honest ${title} move.` },
    prediction: {
      if_ignored: "No outcome has been persisted.",
      if_followed: "A returned outcome can update this System.",
      basis: {},
      provenance_label: "OWNER_LEDGER",
    },
  };
});

const mockMapLayouts = [
  { x: 260, y: 220 },
  { x: 600, y: 170 },
  { x: 940, y: 220 },
  { x: 300, y: 520 },
  { x: 600, y: 560 },
  { x: 900, y: 520 },
] as const;

const mockMapGraph = {
  nodes: [
    { id: "nur", kind: "NUR", label: "NUR", parent_id: null, status: "ACTIVE", data: {} },
    ...mockSystems.map(row => ({
      id: `system:${row.slug}`,
      kind: "SYSTEM",
      label: row.title,
      parent_id: "nur",
      status: "ACTIVE",
      data: { system_slug: row.slug },
    })),
  ],
  edges: mockSystems.map(row => ({
    id: `edge:${row.slug}`,
    source: "nur",
    target: `system:${row.slug}`,
    kind: "MASTER_TO_SYSTEM",
    semantic: false,
    user_confirmed: true,
  })),
  system_regions: mockSystems.map((row, index) => ({
    slug: row.slug,
    title: row.title,
    node_id: `system:${row.slug}`,
    state: "ACTIVE",
    state_reason: "0% progress from persisted owner evidence; no returned outcome yet.",
    progress_percent: 0,
    active_goal_count: 0,
    blocker_count: 0,
    next_move: row.next_move,
    layout: { ...mockMapLayouts[index]!, radius: 132 },
  })),
  counts: { systems: mockSystems.length, nodes: mockSystems.length + 1, edges: mockSystems.length },
  suggested_changes: { candidate_edges: [], suggestions: [] },
  staleness: {},
  permissions: { can_move: true, can_accept_suggestions: true },
  future_paths: mockSystems.map(row => ({
    system_slug: row.slug,
    current_progress: 0,
    if_continued: row.prediction.if_followed,
    if_ignored: row.prediction.if_ignored,
    basis: "Persisted owner evidence only.",
  })),
};

const mockToday = {
  date: now.slice(0, 10),
  day_label: "Today",
  local_time: "12:00",
  timezone: "UTC",
  daypart: "day",
  body: { score: 0, sources: {}, calculation: "No persisted reading." },
  mind: { score: 0, sources: {}, calculation: "No persisted reading." },
  life: { score: 0, sources: {}, calculation: "No persisted reading." },
  glow_today: 0,
  active_systems: mockSystems,
  active_goals: [],
  active_plans: [],
  scheduled_today: [],
  completed_today: [],
  missed_today: [],
  daily_quest: {},
  next_move: null,
  latest_insight: null,
  latest_timeline_event: null,
  return_check: null,
  provenance_label: "OWNER_LEDGER",
};

const mockLiveUniverse = {
  generated_at: now,
  provenance_label: "OWNER_LEDGER_AGGREGATE",
  owner: {
    id: mockUser.id,
    email: mockUser.email,
    chosen_name: mockUser.profile.chosen_name,
    timezone: "UTC",
    locale: "en",
    writing_preference: "default",
    default_boundary: "PRIVATE_ORBIT",
  },
  state: {
    summary: "Six founder-locked Systems are active.",
    source_count: 0,
    confidence: 0,
    confidence_kind: "source_coverage_not_truth_probability",
    last_updated: now,
    today: mockToday,
    provenance_label: "DETERMINISTIC_OWNER_LEDGER_SYNTHESIS",
  },
  active_systems: mockSystems,
  active_goals: [],
  active_objectives: [],
  active_plans: [],
  people_orbits: [],
  group_orbits: [],
  projects: [],
  latest_insights: [],
  timeline_highlights: [],
  open_loops: [],
  next_moves: [],
  glow: { today_points: 0 },
  signals: [],
  community: {
    live_connected: false,
    status: "LOCAL_NOTES_ONLY",
    note_count: 0,
    latest_note: null,
    honest_state: "No live community activity is invented.",
  },
  what_changed: [],
};

type MockState = {
  events: Array<Record<string, unknown>>;
  decisions: Array<Record<string, unknown>>;
  references: Array<Record<string, unknown>>;
  sources: Array<Record<string, unknown>>;
  research: Array<Record<string, unknown>>;
  researchBriefs: Array<Record<string, unknown>>;
  researchNotes: Array<Record<string, unknown>>;
  communityNotes: Array<Record<string, unknown>>;
  webQuestions: Array<Record<string, unknown>>;
  webNotes: Array<Record<string, unknown>>;
  capsules: Array<Record<string, unknown>>;
  journal: Array<Record<string, unknown>>;
  orbits: Array<Record<string, unknown>>;
  thread: Array<Record<string, unknown>>;
  planStepDone: boolean;
  outcomePosts: number;
  preferences: Record<string, unknown>;
  ownerSessions: Array<Record<string, unknown>>;
  accountDeleted: boolean;
  accountWrites: Array<{ path: string; body: Record<string, unknown> }>;
  agenticPolicy: Record<string, unknown>;
  agenticWorkflows: Array<Record<string, unknown>>;
  agenticDetails: Record<string, Record<string, unknown>>;
  agenticApprovals: Array<Record<string, unknown>>;
  agenticWrites: Array<{ path: string; body: Record<string, unknown> }>;
};

export async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function installBundledFontPolicy(page: Page) {
  // Canonical V197 still carries its historical Google Fonts link, while the
  // production bridge supplies the exact Bodoni/Crimson faces from local
  // bundled files. Do not let mocked readiness wait on public DNS before an
  // iframe can reach readyState=complete.
  await page.route("https://fonts.googleapis.com/**", route => route.fulfill({
    status: 200,
    contentType: "text/css",
    body: "",
  }));
  await page.route("https://fonts.gstatic.com/**", route => route.fulfill({
    status: 204,
    body: "",
  }));
}

export async function installNurMocks(page: Page) {
  await installBundledFontPolicy(page);
  await page.context().addCookies([
    {
      name: "nur_session",
      value: "mock-owner-session",
      url: "http://localhost:4173",
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "nur_csrf",
      value: "mock-owner-csrf",
      url: "http://localhost:4173",
      httpOnly: false,
      sameSite: "Lax",
    },
  ]);
  const state: MockState = {
    planStepDone: false,
    outcomePosts: 1,
    preferences: {
      locale: "en",
      sound_enabled: false,
      reduced_effects: true,
      default_boundary: "PRIVATE_ORBIT",
      active_orbit_id: mockOrbit.id,
      omega_enabled: true,
      writing_preference: "default",
      updated_at: now,
    },
    orbits: [mockOrbit],
    decisions: [{
      id: "decision-1",
      orbit_id: mockOrbit.id,
      statement: "Postgres RLS is the trust boundary.",
      rationale: "Recipient access must stay grant-scoped.",
      created_at: now,
    }],
    references: [{
      id: "reference-1",
      orbit_id: mockOrbit.id,
      title: "Capsule spectrum palette",
      body: "Mango through pearl.",
      kind: "REFERENCE",
      created_at: now,
    }],
    sources: [{ id: "source-decision-1", source_kind: "DECISION", source_id: "decision-1", inclusion_mode: "FULL" }],
    capsules: [capsuleRow("cap-active", null)],
    thread: [
      { id: "thread-1", who: "user", text: "Persist this already.", structured_payload: {}, created_at: now },
      {
        id: "thread-2",
        who: "nur",
        text: "Persisted answer.",
        structured_payload: {
          provider_available: false,
          provider_reason: "AI provider is disabled.",
          talk_output: {
            direct_response: "Persisted answer.",
            observed: ["The owner asked NUR to hold continuity."],
            inferred: [],
            hypotheses: [],
            uncertainty: ["Disabled mode cannot call a model."],
            next_move: "Return one outcome.",
            memory_candidates: [],
            source_refs: [],
          },
          omega: {
            enabled: true,
            workspace_frame_id: "frame-1",
            what_changed: ["Outcome-gated glow proof is active."],
            open_contradictions: ["Shortcutting outcome proof is still a risk."],
            unresolved_predictions: ["A returned outcome should strengthen planning confidence."],
            memory_note: "Held as an evidence-backed hypothesis.",
          },
        },
        created_at: now,
      },
    ],
    research: [{ id: "research-1", question: "What source should verify this system?", status: "STAGED", created_at: now }],
    researchBriefs: [{
      id: "brief-1",
      orbit_id: mockOrbit.id,
      question: "What source should verify this system?",
      intent: "Verify the system boundary.",
      status: "STAGED",
      provider_status: "NOT_CONNECTED",
      provenance_label: "OWNER_WRITTEN",
      created_at: now,
      updated_at: now,
    }],
    researchNotes: [{
      id: "research-note-1",
      orbit_id: mockOrbit.id,
      brief_id: "brief-1",
      title: "Local source note",
      source_url: null,
      note: "Saved locally; no live web fetched.",
      provenance_label: "OWNER_WRITTEN",
      created_at: now,
      updated_at: now,
    }],
    communityNotes: [{
      id: "community-1",
      orbit_id: mockOrbit.id,
      title: "Ask a collaborator to inspect the boundary.",
      note: "Community engine not connected; saved as local consultation.",
      status: "LOCAL_NOTE",
      provenance_label: "OWNER_WRITTEN",
      created_at: now,
      updated_at: now,
    }],
    webQuestions: [{
      id: "web-question-1",
      orbit_id: mockOrbit.id,
      question: "What outside signal should be checked later?",
      status: "STAGED",
      provider_status: "NOT_CONNECTED",
      provenance_label: "OWNER_WRITTEN",
      created_at: now,
      updated_at: now,
    }],
    webNotes: [{
      id: "web-note-1",
      orbit_id: mockOrbit.id,
      question_id: "web-question-1",
      title: "Local web signal note",
      source_url: null,
      note: "Web engine is not connected yet.",
      provenance_label: "OWNER_WRITTEN",
      created_at: now,
      updated_at: now,
    }],
    journal: [{ id: "journal-1", body: "The system stayed coherent.", orbit_id: mockOrbit.id, event_id: "evt-journal-1", created_at: now }],
    events: [
      event("evt-outcome", "OUTCOME_REPORTED", "The owner returned a visible outcome."),
      event("evt-community", "COMMUNITY_NOTE", "Ask a collaborator to inspect the boundary."),
      event("evt-web", "WEB_SIGNAL_QUESTION", "Check the outside signal later."),
    ],
    ownerSessions: [
      { id: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa", created_at: now, expires_at: "2026-09-01T00:00:00Z", revoked_at: null, current: true, state: "active" },
      { id: "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb", created_at: now, expires_at: "2026-09-01T00:00:00Z", revoked_at: null, current: false, state: "active" },
    ],
    accountDeleted: false,
    accountWrites: [],
    agenticPolicy: {
      scope: "ACCOUNT",
      persisted: false,
      initiative_level: "SUGGEST",
      max_risk_class: "R1_PRIVATE_DRAFT",
      permitted_tools: [],
      auto_run_tools: [],
      denied_tools: [],
      granted_capabilities: [],
      daily_budget_cents: 0,
      max_proposals_per_day: 3,
      cooldown_minutes: 180,
      quiet_hours: {},
    },
    agenticWorkflows: [],
    agenticDetails: {},
    agenticApprovals: [],
    agenticWrites: [],
  };

  await page.route("**/healthz", route => json(route, { status: "ok", ai_provider: "disabled" }));
  await page.route("**/readyz", route => json(route, { status: "ready", checks: { database: "ok", redis: "ok" } }));
  await page.route("**/metrics**", route => route.fulfill({
    status: 200,
    contentType: "text/plain",
    body: "nur_ai_provider_configured{provider=\"disabled\"} 0\nnur_requests_total 3\n",
  }));

  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    if (path === "/api/v1/auth/me" && state.accountDeleted) return json(route, { detail: "Not authenticated" }, 401);
    if (path === "/api/v1/auth/me") return json(route, mockUser);
    if (path === "/api/v1/auth/logout") return json(route, undefined, 204);
    if (path === "/api/v1/account/export" && method === "POST") {
      state.accountWrites.push({ path, body: JSON.parse(request.postData() || "{}") as Record<string, unknown> });
      const manifest = {
        schema: "https://nur.app/schemas/owner-export-manifest/v1",
        version: "1.0.0",
        owner_user_id: mockUser.id,
        provenance: { scope: "forced RLS plus explicit owner predicates" },
        summary: { table_count: 2, row_count: 4, object_count: 0, object_bytes_included_count: 0, object_bytes_unavailable_count: 0 },
        tables: [],
        objects: [],
        checksum: { algorithm: "sha256", covers: "entire manifest excluding checksum", value: "mock-owner-export-checksum" },
      };
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "content-disposition": 'attachment; filename="nur-owner-export-v1.json"',
          "x-nur-export-checksum": "mock-owner-export-checksum",
        },
        body: JSON.stringify(manifest),
      });
    }
    if (path === "/api/v1/auth/sessions" && method === "GET") return json(route, { sessions: state.ownerSessions });
    if (path === "/api/v1/auth/sessions/revoke-others" && method === "POST") {
      const activeOthers = state.ownerSessions.filter(row => !row.current && row.state === "active");
      for (const row of activeOthers) {
        row.state = "revoked";
        row.revoked_at = now;
      }
      state.accountWrites.push({ path, body: JSON.parse(request.postData() || "{}") as Record<string, unknown> });
      return json(route, { revoked_session_count: activeOthers.length });
    }
    if (path.startsWith("/api/v1/auth/sessions/") && method === "DELETE") {
      const sessionId = path.split("/").at(-1);
      const target = state.ownerSessions.find(row => row.id === sessionId && !row.current && row.state === "active");
      if (!target) return json(route, { detail: "Session not found or already revoked." }, 404);
      target.state = "revoked";
      target.revoked_at = now;
      state.accountWrites.push({ path, body: {} });
      return json(route, { revoked_session_count: 1 });
    }
    if (path === "/api/v1/account" && method === "DELETE") {
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      state.accountWrites.push({ path, body });
      if (body.password !== "owner-password" || body.confirmation !== "DELETE MY NUR ACCOUNT") {
        return json(route, { detail: "Password is incorrect." }, 400);
      }
      state.accountDeleted = true;
      return json(route, {
        deleted: true,
        revoked_session_count: 2,
        local_object_cleanup: { requested: 0, deleted: 0, already_absent: 0, failed: 0 },
        external_provider_deletion: { status: "not_applicable", providers: [], detail: "No external billing-provider identity was stored for this account." },
        retained_audit: "One non-sensitive ACCOUNT_DELETED tombstone is retained without user id or email.",
      });
    }
    if (path === "/api/v1/agentic/tools" && method === "GET") return json(route, {
      tools: [
        { key: "get_today_state", version: "1", risk_class: "R0_READ_ONLY", summary: "The owner's current day state and next move.", reads: ["Today"], writes: [], reversible: true, required_capabilities: ["read_today"], bound: true },
        { key: "get_timeline", version: "1", risk_class: "R0_READ_ONLY", summary: "Timeline events in a bounded window.", reads: ["Timeline"], writes: [], reversible: true, required_capabilities: ["read_timeline"], bound: true },
        { key: "create_draft_plan", version: "1", risk_class: "R1_PRIVATE_DRAFT", summary: "Draft a Plan for the owner to review.", reads: [], writes: ["Draft Plan"], reversible: true, required_capabilities: ["draft_plans"], bound: false },
      ],
      provenance_label: "First-party NUR tools. Unbound tools are declared but not callable.",
    });
    if (path === "/api/v1/agentic/policy" && method === "GET") return json(route, state.agenticPolicy);
    if (path === "/api/v1/agentic/policy" && method === "PUT") {
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      state.agenticWrites.push({ path, body });
      state.agenticPolicy = {
        ...state.agenticPolicy,
        ...body,
        persisted: true,
        granted_capabilities: (body.permitted_tools as string[] ?? []).map(key => key === "get_today_state" ? "read_today" : "read_timeline"),
      };
      return json(route, state.agenticPolicy);
    }
    if (path === "/api/v1/agentic/workflows" && method === "GET") return json(route, { workflows: state.agenticWorkflows, count: state.agenticWorkflows.length });
    if (path === "/api/v1/agentic/workflows" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      state.agenticWrites.push({ path, body });
      const id = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
      const detail = {
        id,
        title: body.title,
        objective: body.objective,
        kind: "OWNER_DEFINED",
        state: "PLAN_READY",
        plan_version: 1,
        context_manifest: body.context_manifest,
        success_criteria: body.success_criteria,
        cost_cents: 0,
        failure_code: null,
        idempotent_replay: false,
        steps: [{
          id: "dddddddd-dddd-4ddd-8ddd-dddddddddddd",
          key: "step-1",
          ordinal: 1,
          state: "READY",
          role: (body.proposed_steps as Array<Record<string, unknown>>)[0].role,
          tool_key: (body.proposed_steps as Array<Record<string, unknown>>)[0].tool_key,
          tool_version: "1",
          risk_class: "R0_READ_ONLY",
          approval_required: false,
          depends_on: [],
          input_refs: (body.proposed_steps as Array<Record<string, unknown>>)[0].input_refs,
          verification_verdict: null,
          attempt: 0,
          execution_attempt: "eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee",
          idempotency_key: "owner-workflow:mock:1:step-1",
          failure_code: null,
          retryable: false,
        }],
      };
      state.agenticDetails[id] = detail;
      state.agenticWorkflows.unshift({ id, title: body.title, objective: body.objective, state: "PLAN_READY", kind: "OWNER_DEFINED", step_count: 1, steps_done: 0, cost_cents: 0, failure_code: null, updated_at: now });
      return json(route, detail, 201);
    }
    const workflowMatch = path.match(/^\/api\/v1\/agentic\/workflows\/([^/]+)$/);
    if (workflowMatch && method === "GET") {
      const detail = state.agenticDetails[workflowMatch[1]];
      return detail ? json(route, detail) : json(route, { detail: "workflow not found" }, 404);
    }
    const startMatch = path.match(/^\/api\/v1\/agentic\/workflows\/([^/]+)\/start$/);
    if (startMatch && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      state.agenticWrites.push({ path, body });
      const detail = state.agenticDetails[startMatch[1]];
      if (!detail) return json(route, { detail: "workflow not found" }, 404);
      detail.state = "QUEUED";
      const listRow = state.agenticWorkflows.find(row => row.id === startMatch[1]);
      if (listRow) listRow.state = "QUEUED";
      return json(route, detail);
    }
    const cancelMatch = path.match(/^\/api\/v1\/agentic\/workflows\/([^/]+)\/cancel$/);
    if (cancelMatch && method === "POST") {
      const detail = state.agenticDetails[cancelMatch[1]];
      if (!detail) return json(route, { detail: "workflow not found" }, 404);
      state.agenticWrites.push({ path, body: JSON.parse(request.postData() || "{}") as Record<string, unknown> });
      detail.state = "CANCEL_REQUESTED";
      const listRow = state.agenticWorkflows.find(row => row.id === cancelMatch[1]);
      if (listRow) listRow.state = "CANCEL_REQUESTED";
      return json(route, detail);
    }
    const eventMatch = path.match(/^\/api\/v1\/agentic\/workflows\/([^/]+)\/events$/);
    if (eventMatch && method === "GET") return json(route, {
      events: [{ sequence: 1, event_type: "WORKFLOW_CREATED", from_state: null, to_state: "PLAN_READY", summary: "owner created an explicit workflow draft", actor: "OWNER", created_at: now }],
      count: 1,
      provenance_label: "Append-only run ledger",
    });
    if (path === "/api/v1/agentic/approvals" && method === "GET") return json(route, { approvals: state.agenticApprovals, count: state.agenticApprovals.length });
    const approvalMatch = path.match(/^\/api\/v1\/agentic\/approvals\/([^/]+)\/decide$/);
    if (approvalMatch && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      state.agenticWrites.push({ path, body });
      state.agenticApprovals = state.agenticApprovals.filter(row => row.id !== approvalMatch[1]);
      return json(route, { approval_id: approvalMatch[1], decision: body.decision, step_state: "QUEUED", workflow_state: "QUEUED", outbox_intent_id: "ffffffff-ffff-4fff-8fff-ffffffffffff" });
    }
    if (path === "/api/v1/universe/live") return json(route, mockLiveUniverse);
    if (path === "/api/v1/map/views") return json(route, {
      default_view_id: "mock-map-view",
      views: [{ id: "mock-map-view", name: "Owner Map", is_default: true }],
    });
    if (path === "/api/v1/map" || path === "/api/v1/map/views/mock-map-view/graph") {
      return json(route, mockMapGraph);
    }
    if (path === "/api/v1/map/smart-sections") return json(route, {
      current_focus: [],
      needs_decision: [],
      blocked: [],
      momentum: [],
      fragile_paths: [],
      recently_changed: [],
    });
    if (path === "/api/v1/orbit-field") return json(route, {
      people: [],
      groups: [],
      relationships: [],
      layout: [],
      thread_counts: {},
    });
    if (path === "/api/v1/orbit-threads") return json(route, []);
    if (path === "/api/v1/timeline/flow") return json(route, {
      now,
      entries: [{
        ref: "event:evt-outcome",
        id: "evt-outcome",
        kind: "EVENT",
        event_type: "OUTCOME_REPORTED",
        title: "The owner returned a visible outcome.",
        description: "Observed from a persisted owner outcome.",
        status: "OBSERVED",
        time_kind: "PAST",
        date_precision: "EXACT",
        scheduled_for: null,
        ends_at: null,
        all_day: false,
        actual_start_at: null,
        actual_end_at: null,
        completion_state: null,
        occurred_at: now,
        system_slug: "ambition",
        goal_id: null,
        plan_id: null,
        orbit_id: mockOrbit.id,
        phase_id: null,
        visibility_scope: "PRIVATE_ORBIT",
        energy_type: null,
        importance: 1,
        source_type: "OUTCOME",
      }],
      unscheduled: [],
      phases: [],
      dependencies: [],
      counts: { total: 1, past: 1, present: 0, future: 0, unscheduled: 0 },
    });
    if (path === "/api/v1/timeline/smart-sections") return json(route, {
      needs_attention: [],
      overdue: [],
      fragile: [],
      recently_changed: [],
    });
    if (path === "/api/v1/glow/scoreboard") return json(route, null);
    if (path === "/api/v1/glow/summary") return json(route, {
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
    });
    if (path === "/api/v1/glow/rewards" && method === "POST") return json(route, {
      awarded_points: 0,
      balance: 0,
      lifetime_points: 0,
      idempotent_replay: true,
      streak: null,
      achievements_unlocked: [],
    });
    if (path === "/api/v1/projects/summary") return json(route, null);
    if (path === "/api/v1/community/rooms" && method === "GET") return json(route, []);
    if (path === "/api/v1/orbits/current-state") return json(route, {
      active_systems: mockSystems.length,
      outcomes_returned: state.outcomePosts,
      insights_evolving: 2,
      open_questions: 1,
      research_staged: state.research.length,
      plans_active: 1,
      live_status: "owner_ledger",
    });
    if (path === "/api/v1/universe/map-summary") return json(route, {
      provenance_label: "owner_ledger",
      counts: [
        { key: "orbits", label: "owner-owned orbits", count: 1 },
        { key: "outcomes", label: "returned outcomes", count: state.outcomePosts },
      ],
      nodes: mockSystems.map(row => ({
        id: row.orbit_id,
        title: row.title,
        kind: "SYSTEM",
        orbit_id: row.orbit_id,
        active: true,
        counts: { progress: row.progress_percent, glow: row.progress_sources.glow_points },
      })),
    });
    if (path === "/api/v1/universe/orbits-summary") return json(route, {
      provenance_label: "owner_ledger",
      orbits: state.orbits.map(row => ({ ...row, counts: { decisions: 1, references: 1, sources: 1, capsules: 1 } })),
    });
    if (path === "/api/v1/universe/timeline") return json(route, {
      provenance_label: "owner_ledger",
      items: state.events.map(row => ({
        id: row.id,
        kind: row.event_kind,
        title: String(row.event_kind).toLowerCase(),
        body: row.content_text,
        created_at: row.created_at,
        provenance_label: "cognitive_event",
        route: "/today",
      })),
    });
    if (path === "/api/v1/universe/insights-summary") return json(route, {
      provenance_label: "omega_owner_ledger",
      counts: { claims: 1, open_contradictions: 1, predictions: 1, review_queue: 1, learning_proposals: 1 },
      claims: [mockClaim],
      contradictions: omegaDashboard().contradictions,
      predictions: omegaDashboard().predictions,
      review_queue: omegaDashboard().review_queue,
    });
    if (path === "/api/v1/universe/search") return json(route, [
      {
        kind: "decision",
        id: "decision-1",
        label: "Postgres RLS is the trust boundary.",
        excerpt: "Recipient access must stay grant-scoped.",
        route: "/universe/orbits",
        created_at: now,
        provenance_label: "owner_ledger",
      },
      {
        kind: "orbit",
        id: mockOrbit.id,
        label: "Quiet Ambition",
        excerpt: "Build without noise",
        route: "/universe/orbits",
        created_at: now,
        provenance_label: "owner_ledger",
      },
    ]);
    if (path === "/api/v1/profile/preferences" && method === "GET") return json(route, state.preferences);
    if (path === "/api/v1/profile/preferences" && method === "PATCH") {
      const body = JSON.parse(request.postData() || "{}") as Record<string, unknown>;
      state.preferences = { ...state.preferences, ...body, updated_at: new Date().toISOString() };
      return json(route, state.preferences);
    }
    if (path === "/api/v1/orbits" && method === "GET") return json(route, state.orbits);
    if (path === "/api/v1/orbits" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { title?: string; description?: string };
      const row = { ...mockOrbit, id: `orbit-created-${state.orbits.length}`, title: body.title || "Created Orbit", description: body.description || null };
      state.orbits.push(row);
      return json(route, row, 201);
    }
    if (path === `/api/v1/orbits/${mockOrbit.id}/decisions`) {
      if (method === "POST") {
        const body = JSON.parse(request.postData() || "{}") as { statement?: string; rationale?: string };
        const row = {
          id: `decision-${state.decisions.length + 1}`,
          orbit_id: mockOrbit.id,
          statement: body.statement || "Untitled decision",
          rationale: body.rationale ?? null,
          created_at: now,
        };
        state.decisions.unshift(row);
        return json(route, row, 201);
      }
      return json(route, state.decisions);
    }
    if (path === `/api/v1/orbits/${mockOrbit.id}/references`) {
      if (method === "POST") {
        const body = JSON.parse(request.postData() || "{}") as { title?: string; body?: string; kind?: string };
        const row = {
          id: `reference-${state.references.length + 1}`,
          orbit_id: mockOrbit.id,
          title: body.title || "Untitled reference",
          body: body.body ?? null,
          kind: body.kind ?? "REFERENCE",
          created_at: now,
        };
        state.references.unshift(row);
        return json(route, row, 201);
      }
      return json(route, state.references);
    }
    if (path === `/api/v1/orbits/${mockOrbit.id}/sources`) {
      if (method === "POST") {
        const body = JSON.parse(request.postData() || "{}") as { source_kind?: string; source_id?: string; inclusion_mode?: string };
        const row = {
          id: `source-${state.sources.length + 1}`,
          source_kind: body.source_kind || "REFERENCE",
          source_id: body.source_id || "reference-created",
          inclusion_mode: body.inclusion_mode || "FULL",
        };
        state.sources.unshift(row);
        return json(route, row, 201);
      }
      return json(route, state.sources);
    }
    if (path === "/api/v1/journal" && method === "GET") return json(route, state.journal);
    if (path === "/api/v1/journal" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { body?: string; orbit_id?: string };
      const row = { id: `journal-${state.journal.length + 1}`, body: body.body || "", orbit_id: body.orbit_id ?? mockOrbit.id, event_id: `evt-journal-${state.journal.length + 1}`, created_at: now };
      state.journal.unshift(row);
      return json(route, row, 201);
    }
    if (path === "/api/v1/plans" && method === "GET") return json(route, [{
      id: "plan-1",
      title: "Make one pattern into movement",
      status: "ACTIVE",
      steps: [{
        id: "step-1",
        title: "Return an outcome",
        body: null,
        position: 0,
        done: state.planStepDone,
        done_at: state.planStepDone ? now : null,
      }],
    }]);
    if (path === "/api/v1/plans" && method === "POST") return json(route, {
      id: "plan-created",
      title: "Use this move",
      status: "ACTIVE",
      steps: [{ id: "step-created", title: "Return one outcome.", body: null, position: 0, done: false, done_at: null }],
    }, 201);
    if (path === "/api/v1/plans/plan-1/steps" && method === "POST") return json(route, {
      id: "step-added",
      title: (JSON.parse(request.postData() || "{}") as { title?: string }).title ?? "Record what changed from Talk",
      body: (JSON.parse(request.postData() || "{}") as { body?: string }).body ?? "Outcome returned from a Talk follow-up.",
      position: 1,
      done: false,
      done_at: null,
    }, 201);
    if (path === "/api/v1/plan-steps/step-1" && method === "PATCH") {
      const body = JSON.parse(request.postData() || "{}") as { done?: boolean };
      state.planStepDone = body.done ?? state.planStepDone;
      return json(route, {
        id: "step-1",
        title: "Return an outcome",
        body: null,
        position: 0,
        done: state.planStepDone,
        done_at: state.planStepDone ? now : null,
      });
    }
    if (path === "/api/v1/outcomes") {
      state.outcomePosts += 1;
      return json(route, { id: `outcome-${state.outcomePosts}` }, 201);
    }
    if (path === "/api/v1/research-drafts" && method === "GET") return json(route, state.research);
    if (path === "/api/v1/research-drafts" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { question?: string };
      const row = { id: `research-${state.research.length + 1}`, question: body.question || "Untitled question", status: "STAGED", created_at: now };
      state.research.unshift(row);
      return json(route, row, 201);
    }
    if (path.startsWith("/api/v1/research-drafts/") && path.endsWith("/convert")) {
      const id = path.split("/")[4];
      state.research = state.research.map(row => row.id === id ? { ...row, status: "CONVERTED" } : row);
      return json(route, {
        source_kind: "RESEARCH_DRAFT",
        source_id: id,
        target_kind: "OPEN_QUESTION",
        target_id: "reference-converted",
        orbit_id: mockOrbit.id,
        orbit_source_id: "source-converted",
      });
    }
    if (path === "/api/v1/research/briefs" && method === "GET") return json(route, state.researchBriefs);
    if (path === "/api/v1/research/briefs" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { question?: string; intent?: string; orbit_id?: string };
      const row = {
        id: `brief-${state.researchBriefs.length + 1}`,
        orbit_id: body.orbit_id ?? mockOrbit.id,
        question: body.question || "Untitled research question",
        intent: body.intent || null,
        status: "STAGED",
        provider_status: "NOT_CONNECTED",
        provenance_label: "OWNER_WRITTEN",
        created_at: now,
        updated_at: now,
      };
      state.researchBriefs.unshift(row);
      return json(route, row, 201);
    }
    if (path.startsWith("/api/v1/research/briefs/") && path.endsWith("/convert")) {
      const id = path.split("/")[5];
      state.researchBriefs = state.researchBriefs.map(row => row.id === id ? { ...row, status: "CONVERTED" } : row);
      return json(route, {
        source_kind: "RESEARCH_BRIEF",
        source_id: id,
        target_kind: "OPEN_QUESTION",
        target_id: "research-brief-reference",
        orbit_id: mockOrbit.id,
        orbit_source_id: "source-research-brief",
      });
    }
    if (path === "/api/v1/research/source-notes" && method === "GET") return json(route, state.researchNotes);
    if (path === "/api/v1/research/source-notes" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { title?: string; note?: string; brief_id?: string; orbit_id?: string };
      const row = {
        id: `research-note-${state.researchNotes.length + 1}`,
        orbit_id: body.orbit_id ?? mockOrbit.id,
        brief_id: body.brief_id ?? null,
        title: body.title || "Local source note",
        source_url: null,
        note: body.note || "",
        provenance_label: "OWNER_WRITTEN",
        created_at: now,
        updated_at: now,
      };
      state.researchNotes.unshift(row);
      return json(route, row, 201);
    }
    if (path === "/api/v1/community/consultation-notes" && method === "GET") return json(route, state.communityNotes);
    if (path === "/api/v1/community/consultation-notes" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { prompt?: string; note?: string; orbit_id?: string };
      const row = {
        id: `community-${state.communityNotes.length + 1}`,
        orbit_id: body.orbit_id ?? mockOrbit.id,
        title: body.prompt || "Untitled consultation",
        note: body.note || "",
        status: "LOCAL_NOTE",
        provenance_label: "OWNER_WRITTEN",
        created_at: now,
        updated_at: now,
      };
      state.communityNotes.unshift(row);
      return json(route, row, 201);
    }
    if (path === "/api/v1/web-signals/questions" && method === "GET") return json(route, state.webQuestions);
    if (path === "/api/v1/web-signals/questions" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { question?: string; orbit_id?: string };
      const row = {
        id: `web-question-${state.webQuestions.length + 1}`,
        orbit_id: body.orbit_id ?? mockOrbit.id,
        question: body.question || "Untitled signal",
        status: "STAGED",
        provider_status: "NOT_CONNECTED",
        provenance_label: "OWNER_WRITTEN",
        created_at: now,
        updated_at: now,
      };
      state.webQuestions.unshift(row);
      return json(route, row, 201);
    }
    if (path === "/api/v1/web-signals/notes" && method === "GET") return json(route, state.webNotes);
    if (path === "/api/v1/web-signals/notes" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { question_id?: string; title?: string; note?: string; orbit_id?: string };
      const row = {
        id: `web-note-${state.webNotes.length + 1}`,
        orbit_id: body.orbit_id ?? mockOrbit.id,
        question_id: body.question_id ?? null,
        title: body.title || "Local web signal note",
        source_url: null,
        note: body.note || "",
        provenance_label: "OWNER_WRITTEN",
        created_at: now,
        updated_at: now,
      };
      state.webNotes.unshift(row);
      return json(route, row, 201);
    }
    if (path.startsWith("/api/v1/web-signals/notes/") && path.endsWith("/attach")) {
      return json(route, {
        source_kind: "WEB_SIGNAL_NOTE",
        source_id: path.split("/")[5],
        target_kind: "REFERENCE",
        target_id: "web-note-reference",
        orbit_id: mockOrbit.id,
        orbit_source_id: "source-web-note",
      });
    }
    if (path === "/api/v1/provider-capabilities" && method === "GET") return json(route, [
      { id: "cap-research", provider_key: "local_research_staging", surface: "research", status: "AVAILABLE", honest_label: "Saved local research briefs; no live web fetched.", created_at: now, updated_at: now },
      { id: "cap-community", provider_key: "community_local_notes", surface: "community", status: "NOT_CONNECTED", honest_label: "Community intelligence is not connected yet.", created_at: now, updated_at: now },
      { id: "cap-web", provider_key: "web_signals_local_staging", surface: "web_signals", status: "NOT_CONNECTED", honest_label: "Web Signals are not connected yet.", created_at: now, updated_at: now },
    ]);
    if (path.startsWith("/api/v1/journal/") && path.endsWith("/convert")) {
      const id = path.split("/")[4];
      return json(route, {
        source_kind: "JOURNAL_ENTRY",
        source_id: id,
        target_kind: "REFERENCE",
        target_id: "journal-reference-converted",
        orbit_id: mockOrbit.id,
        orbit_source_id: "journal-source-converted",
      });
    }
    if (path === "/api/v1/cognition/talk-thread") return json(route, state.thread);
    if (path === "/api/v1/cognition/talk") {
      const body = JSON.parse(request.postData() || "{}") as { message?: string };
      const response = {
        turn_event_id: "turn-new",
        response_event_id: "response-new",
        model_run_id: "model-run-disabled",
        provider: "disabled",
        provider_available: false,
        provider_reason: "AI provider is disabled.",
        output: {
          direct_response: "I saved this turn, but live AI is disabled on this server.",
          observed: ["The message was persisted."],
          inferred: [],
          hypotheses: [],
          uncertainty: ["AI provider is disabled."],
          next_move: "Record what changed.",
          memory_candidates: [],
          source_refs: [],
        },
        evidence: { retrieval: [], withheld: [] },
        verification: { verdict: "WARN", checks: {} },
        omega: {
          enabled: true,
          workspace_frame_id: "frame-1",
          what_changed: ["A Talk turn was recorded."],
          open_contradictions: [],
          unresolved_predictions: [],
          memory_note: "No model output was fabricated.",
        },
      };
      state.thread.push({ id: "turn-new", who: "user", text: body.message ?? "", structured_payload: {}, created_at: now });
      state.thread.push({ id: "response-new", who: "nur", text: response.output.direct_response, structured_payload: { talk_output: response.output, omega: response.omega, provider_available: false, provider_reason: response.provider_reason }, created_at: now });
      return json(route, response);
    }
    if (path === "/api/v1/cognition/corrections" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { correction_text?: string };
      const row = event(`correction-${state.events.length + 1}`, "USER_CORRECTION", body.correction_text || "Correction saved.");
      state.events.unshift(row);
      return json(route, { id: row.id }, 201);
    }
    if (path === "/api/v1/cognition/events" && method === "GET") {
      const kind = url.searchParams.get("kind");
      return json(route, kind ? state.events.filter(row => row.event_kind === kind) : state.events);
    }
    if (path === "/api/v1/cognition/events" && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { event_kind?: string; content_text?: string; structured_payload?: Record<string, unknown> };
      const row = event(`event-${state.events.length + 1}`, body.event_kind || "EVENT", body.content_text || "", body.structured_payload);
      state.events.unshift(row);
      return json(route, { event: row, cycle: null }, 201);
    }
    if (path === `/api/v1/orbits/${mockOrbit.id}/capsules` && method === "POST") {
      const body = JSON.parse(request.postData() || "{}") as { title?: string; purpose?: string; capability?: string; expires_at?: string | null };
      const row = {
        ...capsuleRow(`cap-created-${state.capsules.length + 1}`, null),
        title: body.title || "Quiet Ambition shared context",
        purpose: body.purpose || "Registry capsule purpose",
        capability: body.capability || "ASK_SCOPED_QUESTIONS",
        expires_at: body.expires_at ?? null,
      };
      state.capsules.unshift(row);
      return json(route, row, 201);
    }
    if (path === "/api/v1/capsules" && method === "GET") return json(route, state.capsules);
    if (path.startsWith("/api/v1/capsules/") && path.endsWith("/grants") && method === "POST") {
      const id = path.split("/")[4];
      return json(route, {
        id: `grant-${id}`,
        capsule_id: id,
        recipient_email: "recipient@nur.app",
        capability: "ASK_SCOPED_QUESTIONS",
        expires_at: null,
        created_at: now,
      }, 201);
    }
    if (path === "/api/v1/capsules/cap-active/view") return json(route, capsuleView("ACTIVE"));
    if (path === "/api/v1/capsules/cap-revoked/view") return json(route, capsuleView("REVOKED"));
    if (path === "/api/v1/capsules/cap-active/questions") return json(route, {
      question: "What is included?",
      answer_text: "Postgres RLS is the trust boundary.",
      answer_mode: "DIRECT_STATEMENT",
      source_refs: [{ source_kind: "DECISION", representation: "FULL", source_id: "decision-1" }],
      confidence: 1,
      policy_explanation: "Answered only from included sources.",
    });
    if (path === "/api/v1/omega/dashboard") return json(route, omegaDashboard());
    if (path === "/api/v1/omega/scheduler-status") return json(route, {
      enabled: true,
      scheduled_consolidation: true,
      interval_hours: 24,
      worker_mode: "local_celery_beat",
      last_consolidation_run_at: now,
      last_consolidation_status: "COMPLETED",
      provenance_label: "owner_ledger",
    });
    if (path === `/api/v1/omega/claims/${mockClaim.id}/evidence`) return json(route, [{
      id: "edge-1",
      claim_id: mockClaim.id,
      evidence_kind: "EXPERIENCE",
      evidence_id: "experience-1",
      relation: "SUPPORTS",
      strength: 1,
      note: "created from observed outcome",
      created_at: now,
    }]);
    if (path === `/api/v1/omega/claims/${mockClaim.id}/why-changed`) return json(route, {
      claim_id: mockClaim.id,
      claim_text: mockClaim.claim_text,
      current_truth_status: "OBSERVED",
      current_confidence: 0.82,
      changed_because: ["2 supporting evidence edges increased confidence."],
      supporting_edges: ["SUPPORTS via EXPERIENCE strength 1.00"],
      contradicting_edges: [],
      unresolved_note: null,
    });
    if (path === "/api/v1/omega/export") return json(route, {
      exported_at: now,
      owner_user_id: mockUser.id,
      safety: { owner_only: true, chain_of_thought_excluded: true },
      counts: { claims: 1, contradictions: 1, predictions: 1 },
      ...omegaDashboard(),
    });
    if (path === "/api/v1/omega/consolidate") return json(route, omegaDashboard().consolidation_runs[0]);
    if (path.startsWith("/api/v1/omega/review-queue/")) return json(route, { ...omegaDashboard().review_queue[0], status: "APPROVED", created_claim_id: mockClaim.id });
    if (path.startsWith("/api/v1/omega/contradictions/")) return json(route, { ...omegaDashboard().contradictions[0], status: "RESOLVED" });
    if (path.startsWith("/api/v1/omega/claims/")) return json(route, mockClaim);
    if (path.startsWith("/api/v1/omega/learning-proposals/")) return json(route, { ...omegaDashboard().learning_proposals[0], status: "APPROVED", approved_by_owner: true });
    return json(route, { detail: `Unhandled mock route ${method} ${path}` }, 404);
  });

  return state;
}

function event(id: string, event_kind: string, content_text: string, structured_payload: Record<string, unknown> = {}) {
  return { id, event_kind, content_text, structured_payload, orbit_id: mockOrbit.id, scope: "PRIVATE_ORBIT", parent_event_id: null, created_at: now };
}

function capsuleRow(id: string, revoked_at: string | null) {
  return {
    id,
    orbit_id: mockOrbit.id,
    title: "Quiet Ambition shared context",
    purpose: "Get a designer useful in 20 minutes",
    capability: "ASK_SCOPED_QUESTIONS",
    expires_at: null,
    revoked_at,
    version: 1,
    created_at: now,
  };
}

function capsuleView(state: "ACTIVE" | "REVOKED") {
  return {
    capsule_id: state === "ACTIVE" ? "cap-active" : "cap-revoked",
    state,
    title: "Quiet Ambition",
    purpose: "Get a designer useful in 20 minutes",
    owner_display: "Selene",
    capability: "ASK_SCOPED_QUESTIONS",
    expires_at: null,
    recipient_instructions: state === "ACTIVE" ? "Stay inside the approved boundary." : null,
    safety_copy: "This does not speak for Selene. It answers only from approved context.",
    included: state === "ACTIVE" ? [{
      source_id: "decision-1",
      source_kind: "DECISION",
      representation: "FULL",
      title: "Postgres RLS is the trust boundary.",
      body: "Recipient access must stay grant-scoped.",
    }] : [],
    excluded_summary: state === "ACTIVE" ? [{ source_kind: "REFERENCE", count: 1, note: "withheld by the owner" }] : [],
    grant_id: state === "ACTIVE" ? "grant-1" : null,
  };
}

function omegaDashboard() {
  return {
    statuses: {
      experience_ledger: "IMPLEMENTED",
      evidence_graph: "IMPLEMENTED",
      contradiction_engine: "IMPLEMENTED",
      prediction_resolution: "IMPLEMENTED",
      consolidation: "IMPLEMENTED",
      learning_proposals: "IMPLEMENTED",
      sentience_status: "UNRESOLVED_SENTIENCE_STATUS",
    },
    claims: [mockClaim],
    contradictions: [{
      id: "contradiction-1",
      orbit_id: mockOrbit.id,
      claim_a_id: mockClaim.id,
      claim_b_id: "claim-2",
      status: "OPEN",
      severity: "HIGH",
      description: "Potential conflict: shortcutting outcome proof vs outcome-gated learning.",
      proposed_resolution: "Return an outcome before strengthening the claim.",
      resolved_by_event_id: null,
      created_at: now,
      updated_at: now,
    }],
    predictions: [{
      id: "prediction-1",
      orbit_id: mockOrbit.id,
      prediction_text: "If the owner returns an outcome, planning confidence should improve.",
      expected_observation: "owner returns an outcome",
      metric: null,
      time_window: "next session",
      confidence: 0.68,
      status: "OPEN",
      outcome_id: null,
      prediction_error: null,
      created_at: now,
      resolved_at: null,
    }],
    consolidation_runs: [{
      id: "run-1",
      run_kind: "MANUAL",
      orbit_id: mockOrbit.id,
      input_counts: { experiences: 3 },
      created_claims: 1,
      updated_claims: 0,
      contradictions_found: 1,
      predictions_resolved: 0,
      proposals_created: 1,
      status: "COMPLETED",
      completed_at: now,
      error_class: null,
      created_at: now,
    }],
    learning_proposals: [{
      id: "proposal-1",
      proposal_kind: "PLANNING_HEURISTIC",
      description: "Ask for a persisted outcome before upgrading repeated Talk guidance.",
      evidence_summary: "Supported by outcome rows.",
      supporting_evaluation_ids: [],
      risk_level: "LOW",
      status: "PROPOSED",
      approved_by_owner: false,
      created_at: now,
      updated_at: now,
    }],
    review_queue: [{
      id: "review-1",
      orbit_id: mockOrbit.id,
      experience_id: "experience-1",
      candidate_claim_text: "The owner may prefer evidence-gated learning.",
      candidate_claim_type: "PREFERENCE",
      candidate_truth_status: "HYPOTHESIS",
      sensitivity: "SENSITIVE",
      reason: "requires owner confirmation",
      model_candidate: { confidence: 0.57 },
      status: "PENDING_REVIEW",
      created_claim_id: null,
      reviewed_at: null,
      created_at: now,
      updated_at: now,
    }],
    recent_experiences: [{
      id: "experience-1",
      source_kind: "COGNITIVE_EVENT",
      source_id: "evt-outcome",
      orbit_id: mockOrbit.id,
      event_kind: "OUTCOME_REPORTED",
      scope: "PRIVATE_ORBIT",
      language_tag: "en",
      summary: "Owner returned a visible outcome.",
      raw_ref: { table: "cognitive_events" },
      provenance_label: "OBSERVED_OUTCOME",
      sensitivity: "PRIVATE",
      confidence: 1,
      created_at: now,
    }],
  };
}
