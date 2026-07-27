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
  outcomePosts: number;
  preferences: Record<string, unknown>;
};

export async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

export async function installNurMocks(page: Page) {
  const state: MockState = {
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

    if (path === "/api/v1/auth/me") return json(route, mockUser);
    if (path === "/api/v1/auth/logout") return json(route, undefined, 204);
    if (path === "/api/v1/universe/live") return json(route, mockLiveUniverse);
    if (path === "/api/v1/map") return json(route, null);
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
      steps: [{ id: "step-1", title: "Return an outcome", body: null, position: 0, done: false, done_at: null }],
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
