import { describe, expect, it } from "vitest";

import type { V197BridgeSnapshot } from "../bridge/v197ApiClient";
import { hydrateTrackAV197, renderInsightInspection, renderWorldLens } from "../bridge/v197Hydration";

function fixture(): Document {
  const document = window.document.implementation.createHTMLDocument("NUR universe");
  document.body.innerHTML = `
    <section id="page-systems"><header class="universe-hero-copy"><p class="page-sub">static overview</p></header></section>
    <div class="universe-hero-stats"><span><b>07</b> active</span><span><b>19</b> outcomes</span><span><b>04</b> insights</span></div>
    <div class="universe-field-readout"><b>System field · <em>live</em></b><span>fake metrics</span></div>
    <h2 data-context-title>Context, held gently.</h2>
    <div class="v172-boundary-current"><b>Private Orbit</b></div>
    <p class="page-kicker">Systems universe live feed</p>
    <div class="universe-system-lane"><article><small>active people</small><b>1,284</b><span>moving now</span></article><article><small>fake</small><b>2</b></article><article><small>fake</small><b>3</b></article></div>
    <aside class="universe-insight-panel">
      <div><span class="system-badge"><span class="nur-exact-mini-host"><span class="spark-core">BADGE_STAR</span></span>Candidate insight</span><span class="live-label">LIVE</span></div>
      <div class="universe-insight-title"><small>Theme</small><h2>Fake insight</h2></div>
      <p class="universe-insight-copy">fake advice</p>
      <div class="signal-list"><span>fake 1</span><span>fake 2</span><span>fake 3</span></div>
      <div class="insight-opportunity"><small>Possible move</small><b>fake move</b></div>
      <div class="insight-uncertainty"><span>What NUR may be wrong about</span><p>fake uncertainty</p></div>
      <div class="insight-strength"><span>Strength</span><b>78%</b></div>
      <div class="insight-evidence"><div><small>Evidence</small><b>fake</b><span>fake</span></div></div>
      <div class="insight-revision"><span>fake revision</span></div>
    </aside>
    <div class="universe-state-strip"><article><small>Alignment</small><b>78%</b><em>fake</em></article><article><small>Clarity</small><b>82%</b><em>fake</em></article><article><small>Momentum</small><b>63%</b><em>fake</em></article><article><small>fake</small><b>4</b><em>fake</em></article><article><small>fake</small><b>5</b><em>fake</em></article><article><small>fake</small><b>6</b><em>fake</em></article></div>
    <div class="clean-system-list"><button class="clean-system-row" data-system="old"><i><span class="nur-exact-mini-host"><span class="spark-core">RAIL_STAR</span></span></i><span class="system-label">old</span></button></div>
    <button class="universe-system-node quiet" data-system="old"><i><span class="nur-exact-mini-host"><span class="spark-core">NODE_STAR</span></span></i><span class="node-copy"><b>old</b><small>old</small></span></button>
    <button class="universe-system-node public" data-system="old"><span><b>old</b><small>old</small></span></button>
    <button class="universe-system-node wealth" data-system="old"><span><b>old</b><small>old</small></span></button>
    <button class="universe-system-node embodied" data-system="old"><span><b>old</b><small>old</small></span></button>
    <button class="universe-system-node relational" data-system="old"><span><b>old</b><small>old</small></span></button>
    <button class="universe-system-node social" data-system="old"><span><b>old</b><small>old</small></span></button>
    <button class="universe-system-node neural" data-system="old"><span><b>old</b><small>old</small></span></button>
    <div id="talk-stream"><div class="talk-message">fake Talk</div></div>
    <section id="page-journal"><p class="page-sub">static journal</p><p class="journal-prompt">prompt</p></section>
    <section id="page-plan"><div class="panel-top"><h2 class="panel-title">fake plan</h2><p class="panel-sub">fake</p></div><div class="plan-list"><div>fake step</div></div></section>
    <section id="universe-community"><div class="universe-card-head"><h2>fake community</h2></div><div class="community-items"><article>142 fake replies</article></div><button data-community-tab="People">People</button></section>
    <section id="universe-research"><div class="universe-card-head"><h2>fake web</h2></div><div class="research-results"><article>Harvard fake</article></div></section>
    <div id="page-today"><div class="panel-top"><h2 class="panel-title">Recent Glows</h2><p class="panel-sub">fake</p></div><div class="glow-row"><div>fake glow</div></div></div>
    <article class="v172-glow-list"><div class="clean-card-heading"><span>Recent glows</span></div><button class="v172-glow-row">fake glow rail</button></article>
  `;
  return document;
}

function snapshot(): V197BridgeSnapshot {
  const titles = ["Personal Orbit", "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection"];
  const nodes = titles.map((title, index) => ({
    id: `orbit-${index}`,
    title,
    kind: index === 0 ? "PERSONAL_BRIDGE" : "PROJECT",
    orbit_id: `orbit-${index}`,
    active: true,
    counts: { decisions: index, references: 0, sources: 0, capsules: 0 },
  }));
  return {
    session: {
      id: "owner",
      email: "owner@nur.app",
      profile: { chosen_name: "Mahnoor", locale: "en", writing_preference: "default" },
      orbit: { id: "orbit-0", title: "Personal Orbit", kind: "PERSONAL_BRIDGE", status: "ACTIVE" },
    },
    // System slots hydrate from living Systems, so the fixture must supply them.
    systems: {
      provenance_label: "OWNER_LEDGER",
      systems: ["Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection"].map(
        (title, index) => ({
          slug: title.toLowerCase(),
          title,
          definition: `${title} definition`,
          orbit_id: `orbit-${index + 1}`,
          questions: [],
          checklist: [],
          progress_percent: 0,
          progress_sources: {
            completed_actions: 0,
            total_actions: 0,
            action_completion_percent: 0,
            goal_progress_percent: 0,
            latest_diagnostic_score: 0,
            glow_points: 0,
            formula: "test",
          },
          active_goal_count: 0,
          goals: [],
          blockers: [],
          next_move: { kind: "action", id: null, title: "Persisted step" },
          prediction: { if_ignored: "", if_followed: "", basis: {}, provenance_label: "test" },
        }),
      ),
    } as never,
    ownerState: { active_systems: 6, outcomes_returned: 1, insights_evolving: 1, open_questions: 0, research_staged: 0, plans_active: 1, live_status: "owner_ledger" },
    live: {
      generated_at: "2026-07-11T10:00:00Z",
      provenance_label: "OWNER_LEDGER_AGGREGATE",
      owner: { id: "owner", email: "owner@nur.app", chosen_name: "Mahnoor", timezone: "Asia/Karachi", locale: "en", writing_preference: "default", default_boundary: "PRIVATE_ORBIT" },
      state: { summary: "The clearest persisted next move is: Finish the evidence pass.", source_count: 12, confidence: 1, confidence_kind: "source_coverage_not_truth_probability", last_updated: "2026-07-11T10:00:00Z", today: {} as never, provenance_label: "DETERMINISTIC_OWNER_LEDGER_SYNTHESIS" },
      active_systems: [],
      active_goals: [{ title: "Ship the first real NUR slice" }],
      active_objectives: [{ title: "Finish V197 proof" }],
      active_plans: [{ title: "Evidence pass" }],
      people_orbits: [],
      group_orbits: [],
      projects: [{ title: "NUR Track A" }],
      latest_insights: [{ claim: "Evidence is the release blocker" }],
      timeline_highlights: [],
      open_loops: [{ title: "Package proof" }],
      next_moves: [{ title: "Finish the evidence pass", why: "It is the earliest persisted move." }],
      glow: { today_points: 4 },
      signals: [{ title: "Performance audit" }],
      community: { live_connected: false, status: "LOCAL_NOTES_ONLY", note_count: 0, latest_note: null, honest_state: "Local only" },
      what_changed: [{ title: "Journal entry persisted" }],
    },
    map: { provenance_label: "owner_ledger", counts: [{ key: "orbits", label: "owner-owned orbits", count: 8 }], nodes },
    orbits: { provenance_label: "owner_ledger", orbits: nodes.map(node => ({ ...node, description: null, status: "ACTIVE", created_at: "2026-07-11T10:00:00Z" })) },
    timeline: { provenance_label: "owner_ledger", items: [{ id: "event-1", kind: "JOURNAL_ENTRY", title: "Journal entry", body: "Persisted journal", created_at: "2026-07-11T10:00:00Z", provenance_label: "owner_written", route: "/journal" }] },
    insights: {
      provenance_label: "agentic_insights_and_omega_owner_ledgers",
      counts: { claims: 2, dedicated_insights: 1, omega_claims: 1, open_contradictions: 1 },
      dedicated_insights: [{
        record_kind: "DEDICATED_INSIGHT",
        id: "insight-1",
        title: "Rest protects the work",
        claim_text: "Rest protects the work",
        insight_type: "CROSS_DOMAIN_PATTERN",
        truth_status: "CANDIDATE",
        lifecycle_status: "SURFACED",
        epistemic_state: "PROVISIONAL",
        insight_version: 2,
        time_scale: "WEEKLY",
        source_domains: ["OUTCOME", "PLAN"],
        source_diversity: 2,
        confidence: 0.72,
        evidence: [{ id: "evidence-1" }],
        counter_evidence: [],
        alternative_explanations: ["The workload may have changed."],
        what_nur_may_be_wrong_about: "The improvement may be temporary.",
        suggested_action: "Protect one recovery window.",
        provenance_label: "AGENTIC_INSIGHT_OWNER_LEDGER",
        detail_route: "/universe/insights/insight-1",
      }],
      omega_claims: [{
        record_kind: "OMEGA_CLAIM",
        id: "omega-1",
        claim_text: "Urgency may be rising",
        truth_status: "CANDIDATE",
        confidence: 0.54,
        provenance_label: "OMEGA_CANDIDATE",
        detail_route: "/universe/omega/why-changed/omega-1",
      }],
      claims: [
        { record_kind: "DEDICATED_INSIGHT", id: "insight-1", title: "Rest protects the work", claim_text: "Rest protects the work", insight_type: "CROSS_DOMAIN_PATTERN", lifecycle_status: "SURFACED", evidence: [{ id: "evidence-1" }] },
        { record_kind: "OMEGA_CLAIM", id: "omega-1", claim_text: "Urgency may be rising" },
      ],
      contradictions: [{ description: "Urgency conflicts with capacity" }],
      predictions: [],
      review_queue: [],
    },
    preferences: { locale: "en", writing_preference: "default", default_boundary: "PRIVATE_ORBIT", active_orbit_id: "orbit-1" },
    talkThread: [{ id: "talk-1", who: "user", text: "Persisted Talk", structured_payload: {}, created_at: "2026-07-11T10:00:00Z" }],
    journal: [{ id: "journal-1", body: "Persisted journal", orbit_id: "orbit-1", event_id: "event-1", created_at: "2026-07-11T10:00:00Z" }],
    plans: [{ id: "plan-1", title: "Persisted plan", status: "ACTIVE", orbit_id: "orbit-1", steps: [{ id: "step-1", title: "Persisted step", body: null, position: 0, done: false, done_at: null, experiment_id: null }] }],
    glow: { balance: 4, lifetime_points: 4, recent_transactions: [{ id: "txn-1", event_type: "journal_saved", source_kind: "JOURNAL_ENTRY", source_id: "journal-1", final_points: 4, reason: "Journal saved", created_at: "2026-07-11T10:00:00Z" }], streaks: [] },
    researchBriefs: [],
  };
}

describe("Track A V197 persisted hydration", () => {
  it("replaces fake V197 demo content with owner-scoped persisted state", () => {
    const document = fixture();
    hydrateTrackAV197(document, snapshot());

    expect(document.body.textContent).not.toContain("1,284");
    expect(document.body.textContent).not.toContain("142 fake replies");
    expect(document.body.textContent).not.toContain("Harvard fake");
    expect(document.body.textContent).toContain("Persisted Talk");
    expect(document.body.textContent).toContain("Persisted journal");
    expect(document.body.textContent).toContain("Persisted plan");
    expect(document.body.textContent).toContain("No rooms yet. Create one bounded room to open Group NUR.");
    expect(document.body.textContent).toContain("No fake people, replies, or rooms.");
    // System slots are driven by living Systems, never by the raw orbit graph.
    // A slot with no living System is hidden rather than showing a stale orbit.
    const visibleSystemTitles = [...document.querySelectorAll<HTMLElement>(".universe-system-node")]
      .filter(slot => !slot.hidden)
      .map(slot => slot.querySelector("b")?.textContent);
    expect(visibleSystemTitles).toEqual([
      "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection",
    ]);
    expect(document.querySelector(".plan-check")?.getAttribute("data-plan-step-id")).toBe("step-1");
    expect(document.querySelector(".clean-system-row .nur-exact-mini-host")?.textContent).toBe("RAIL_STAR");
    expect(document.querySelector(".clean-system-row .system-label")?.textContent).toBe("Ambition");
    expect(document.querySelector(".universe-system-node .nur-exact-mini-host")?.textContent).toBe("NODE_STAR");
    expect(document.querySelector(".universe-system-node .node-copy b")?.textContent).toBe("Ambition");
    expect(document.body.textContent).not.toContain("fake 1");
    expect(document.body.textContent).not.toContain("fake move");
    expect(document.body.textContent).not.toContain("fake revision");
    expect(document.body.textContent).not.toContain("Evidencefake");
    expect(document.body.textContent).not.toContain("78%");
    expect(document.querySelector(".system-badge .nur-exact-mini-host")?.textContent).toBe("BADGE_STAR");
    expect(document.querySelector(".insight-opportunity b")?.textContent).toBe("Persisted step");
    // Persisted progress now comes from the living System, not a raw orbit count.
    expect(document.querySelector(".insight-strength span")?.textContent).toBe("Persisted progress");
    expect(document.querySelector(".insight-strength b")?.textContent).toBe("0%");
    expect(document.querySelector("#page-systems .page-sub")?.textContent).toContain("12 owner-ledger sources");
    // With a System focused, the strip carries that System's persisted facts —
    // this is the state the Systems page actually renders for a populated owner.
    const strip = document.querySelector(".universe-state-strip")?.textContent ?? "";
    expect(strip).toContain("System progress");
    expect(strip).toContain("calculated from owner evidence");
    expect(strip).toContain("Actions");
    expect(strip).toContain("Active goals");
    expect(document.body.dataset.nurLiveProvenance).toBe("OWNER_LEDGER_AGGREGATE");
  });

  it("uses the existing V197 signal lane for real lens summaries", () => {
    const document = fixture();
    const state = snapshot();
    renderWorldLens(document, state, "timeline");
    expect(document.querySelector(".universe-system-lane")?.textContent).toContain("Journal entry");
    expect(document.querySelector(".universe-system-lane")?.textContent).toContain("Persisted journal");
    expect(document.querySelector(".universe-insight-title h2")?.textContent).toBe("Journal entry");
    expect(document.querySelector(".universe-insight-copy")?.textContent).toContain("Persisted journal");
    expect(document.querySelector(".system-badge .nur-exact-mini-host")?.textContent).toBe("BADGE_STAR");
    expect(document.querySelector(".system-badge")?.textContent).toContain("Timeline lens");
  });

  it("keeps Omega read-only while exposing owner-governed dedicated Insight evidence", () => {
    const document = fixture();
    const state = snapshot();
    renderWorldLens(document, state, "insights");

    const controls = document.querySelector<HTMLElement>("#nur-v197-insight-controls");
    expect(controls?.dataset.insightId).toBe("insight-1");
    expect(document.querySelector<HTMLButtonElement>('[data-action="insight-accept"]')?.disabled).toBe(false);
    expect(document.querySelector<HTMLButtonElement>('[data-action="insight-plan"]')?.disabled).toBe(true);
    expect(controls?.textContent).toContain("owner-governed Insight");

    renderInsightInspection(
      document,
      {
        id: "insight-1", title: "Rest protects the work", claim: "Rest protects the work",
        lifecycle_status: "SURFACED", epistemic_state: "PROVISIONAL", insight_version: 2,
        time_scale: "WEEKLY", source_domains: ["OUTCOME", "PLAN"], source_diversity: 2,
        alternative_explanations: ["The workload may have changed."], assumptions: [], contradictions: [],
        what_nur_may_be_wrong_about: "The improvement may be temporary.", quality_dimensions: {},
        canonical_links: { timeline: "/universe/timeline", evidence: "/universe/insights/insight-1" },
      },
      {
        insight_id: "insight-1",
        relations: [{
          id: "relation-1", source_kind: "OUTCOME", source_id: "outcome-1", source_domain: "OUTCOME",
          relation: "SUPPORTS", provenance_label: "OWNER_REPORTED", explicitness: "EXPLICIT",
          confidence: 1, evidence_summary: "A real outcome returned.", source_occurred_at: "2026-08-09T10:00:00Z",
          source_exists: true, canonical_route: "/universe/timeline",
        }],
      },
      {
        insight_id: "insight-1",
        changes: [{
          change_class: "MATERIAL_EVIDENCE", trigger: "Outcome returned", owner_correction: false,
          occurred_at: "2026-08-09T10:01:00Z", affected_future_behavior: "Evidence digest advanced.",
        }],
        governance: "owner-governed",
      },
    );
    const inspection = document.querySelector("#nur-v197-insight-inspection")?.textContent ?? "";
    expect(inspection).toContain("PROVISIONAL · WEEKLY · version 2");
    expect(inspection).toContain("source present");
    expect(inspection).toContain("Why changed: MATERIAL_EVIDENCE: Outcome returned");

    state.insights!.dedicated_insights = [];
    state.insights!.claims = state.insights!.omega_claims ?? [];
    renderWorldLens(document, state, "insights");
    expect(controls?.dataset.insightId).toBe("");
    expect(document.querySelector<HTMLButtonElement>('[data-action="insight-accept"]')?.disabled).toBe(true);
    expect(controls?.textContent).toContain("Omega claim shown read-only");
  });

  it("states the reliable-pattern evidence threshold honestly when Insights are empty", () => {
    const document = fixture();
    const state = snapshot();
    state.insights = {
      provenance_label: "owner_ledger",
      counts: { claims: 0, dedicated_insights: 0, omega_claims: 0, open_contradictions: 0 },
      dedicated_insights: [],
      omega_claims: [],
      claims: [],
      contradictions: [],
      predictions: [],
      review_queue: [],
    };

    renderWorldLens(document, state, "insights");

    expect(document.querySelector(".universe-insight-title h2")?.textContent).toBe(
      "NUR doesn't have enough evidence for a reliable pattern yet.",
    );
    expect(document.querySelector(".universe-insight-copy")?.textContent).toContain(
      "More owner evidence across time or domains is required",
    );
  });

  it("renders persisted bounded rooms with roles, DEMO marks, and privacy copy", () => {
    const document = fixture();
    const state = snapshot();
    state.communityRooms = [
      {
        id: "room-1", owner_user_id: "owner", title: "Rebuild circle", description: null,
        room_kind: "GROUP", system_slug: null, language_tag: "en", status: "ACTIVE",
        is_demo: false, current_user_role: "OWNER", privacy: "Room content only.",
        created_at: "2026-07-12T10:00:00Z", updated_at: "2026-07-12T10:00:00Z",
      },
      {
        id: "room-2", owner_user_id: "owner", title: "Walkthrough room", description: null,
        room_kind: "GROUP", system_slug: null, language_tag: "en", status: "ACTIVE",
        is_demo: true, current_user_role: "MEMBER", privacy: "Room content only.",
        created_at: "2026-07-12T10:00:00Z", updated_at: "2026-07-12T10:00:00Z",
      },
      {
        id: "room-3", owner_user_id: "owner", title: "Repair council", description: null,
        room_kind: "COUNCIL", system_slug: null, language_tag: "en", status: "ACTIVE",
        is_demo: false, current_user_role: "OWNER", privacy: "Room content only.",
        created_at: "2026-07-12T10:00:00Z", updated_at: "2026-07-12T10:00:00Z",
      },
    ];
    state.councilSummary = {
      room: state.communityRooms[2],
      counts: { messages: 0, posts: 0, comments: 0, positions: 2, decisions: 1, members: 3 },
      truth_state: "persisted_local_room_data",
      external_public_feed: "not_connected",
    };
    state.communityMessages = [
      {
        id: "msg-1", room_id: "room-1", owner_user_id: "owner",
        body: "First honest group line.", language_tag: "en",
        provenance_label: "OWNER_WRITTEN", is_demo: false,
        created_at: "2026-07-12T10:05:00Z",
      },
    ];
    hydrateTrackAV197(document, state);

    const community = document.querySelector("#universe-community");
    expect(community?.textContent).toContain("3 bounded rooms · persisted Group NUR.");
    expect(community?.textContent).toContain("Rebuild circle");
    expect(community?.textContent).toContain("Walkthrough room · DEMO");
    expect(community?.textContent).toContain("your role member");
    expect(community?.textContent).toContain("First honest group line.");
    expect(community?.textContent).toContain("owner written");
    expect(community?.textContent).not.toContain("142 fake replies");
    const postButton = document.querySelector<HTMLButtonElement>('[data-action="community-post-message"]');
    expect(postButton?.disabled).toBe(false);
    expect(document.querySelector<HTMLInputElement>("#nur-v197-room-title")).not.toBeNull();
    // Member and Council controls are live because a room and a Council exist.
    expect(document.querySelector<HTMLButtonElement>('[data-action="community-add-member"]')?.disabled).toBe(false);
    expect(document.querySelector<HTMLButtonElement>('[data-action="council-add-position"]')?.disabled).toBe(false);
    expect(document.querySelector<HTMLButtonElement>('[data-action="council-record-decision"]')?.disabled).toBe(false);

    renderWorldLens(document, state, "community");
    expect(document.querySelector(".system-badge")?.textContent).toContain("Community lens");
    expect(document.querySelector(".universe-insight-title h2")?.textContent).toContain("Rebuild circle");
    expect(document.querySelector(".universe-insight-copy")?.textContent).toContain("1 Council");
    expect(document.querySelector(".insight-uncertainty p")?.textContent).toContain("never enter a room automatically");
    expect(document.querySelector(".universe-system-lane")?.textContent).toContain("Repair council");
  });

  it("keeps the community composer honestly disabled until a room exists", () => {
    const document = fixture();
    const state = snapshot();
    state.communityRooms = [];
    hydrateTrackAV197(document, state);
    const postButton = document.querySelector<HTMLButtonElement>('[data-action="community-post-message"]');
    expect(postButton?.disabled).toBe(true);
    expect(postButton?.title).toContain("Create a room before posting");
    expect(document.querySelector<HTMLButtonElement>('[data-action="community-add-member"]')?.disabled).toBe(true);
    expect(document.querySelector<HTMLButtonElement>('[data-action="council-add-position"]')?.disabled).toBe(true);
    expect(document.querySelector<HTMLButtonElement>('[data-action="council-record-decision"]')?.title).toContain("Start a Council");
    expect(document.querySelector("#universe-community")?.textContent).toContain("No fake people, replies, or rooms.");
  });
});
