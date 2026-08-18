import { mkdir } from "node:fs/promises";
import { dirname, join } from "node:path";
import { expect, test, type Page, type Route } from "@playwright/test";

const proofRoot = process.env.NUR_SOL_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/sol-v197-adjuncts" : "proof/sol-v197-adjuncts");

const ownerId = "11111111-1111-1111-1111-111111111111";
const orbitId = "22222222-2222-2222-2222-222222222222";
const claimId = "33333333-3333-3333-3333-333333333333";
const consultationId = "44444444-4444-4444-4444-444444444444";
const roomId = "55555555-5555-5555-5555-555555555555";
const postId = "66666666-6666-6666-6666-666666666666";
const projectId = "77777777-7777-7777-7777-777777777777";
const notificationId = "88888888-8888-8888-8888-888888888888";

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

async function installMocks(page: Page): Promise<{
  preferenceWrites: Array<Record<string, unknown>>;
  consultationWrites: Array<{ path: string; body: Record<string, unknown> }>;
  communityWrites: Array<{ path: string; body: Record<string, unknown> }>;
  projectWrites: Array<{ path: string; body: Record<string, unknown> }>;
  notificationWrites: Array<{ path: string; body: Record<string, unknown> }>;
  passwordWrites: Array<Record<string, unknown>>;
}> {
  const preferenceWrites: Array<Record<string, unknown>> = [];
  const consultationWrites: Array<{ path: string; body: Record<string, unknown> }> = [];
  const communityWrites: Array<{ path: string; body: Record<string, unknown> }> = [];
  const projectWrites: Array<{ path: string; body: Record<string, unknown> }> = [];
  const notificationWrites: Array<{ path: string; body: Record<string, unknown> }> = [];
  const passwordWrites: Array<Record<string, unknown>> = [];
  let notificationRead = false;
  let passwordChanged = false;
  let notificationPreferences = {
    category_settings: {} as Record<string, unknown>, frequency: "BALANCED", quiet_hours_start: "22:00",
    quiet_hours_end: "08:00", push_enabled: false, email_enabled: false,
    delivery_status: "IN_APP_ONLY",
  };
  let savedPreferences = {
    locale: "en", writing_preference: "default", sound_enabled: true,
    reduced_effects: false, omega_enabled: true, timezone: "Asia/Karachi",
  };
  await page.context().addCookies([{ name: "nur_csrf", value: "adjunct-proof", domain: "localhost", path: "/" }]);
  await page.route("**/healthz", route => json(route, { status: "healthy", ai_provider: "openai" }));
  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname.replace("/api/v1", "");
    if (path === "/auth/me" && passwordChanged) return json(route, { detail: "Not authenticated" }, 401);
    if (path === "/auth/me") return json(route, {
      id: ownerId,
      email: "owner@nur.app",
      profile: { chosen_name: "Mahnoor", locale: "en", writing_preference: "default" },
      orbit: { id: orbitId, title: "Private Orbit", kind: "PERSONAL", status: "ACTIVE" },
    });
    if (path === "/auth/password/change" && request.method() === "POST") {
      passwordWrites.push(request.postDataJSON() as Record<string, unknown>);
      passwordChanged = true;
      return route.fulfill({ status: 204, body: "" });
    }
    if (path === "/profile/preferences" && request.method() === "PATCH") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      preferenceWrites.push(payload);
      savedPreferences = { ...savedPreferences, ...payload };
      return json(route, savedPreferences);
    }
    if (path === "/profile/preferences") return json(route, savedPreferences);
    if (path === "/orbits/current-state") return json(route, { active_systems: 7, outcomes_returned: 2, insights_evolving: 1, open_questions: 1, research_staged: 1, plans_active: 1, live_status: "OWNER_LEDGER" });
    if (path === "/universe/live") return json(route, {
      generated_at: new Date().toISOString(),
      provenance_label: "OWNER_LEDGER_AGGREGATE",
      owner: {
        id: ownerId,
        email: "owner@nur.app",
        chosen_name: "Mahnoor",
        timezone: "Asia/Karachi",
        locale: "en",
        writing_preference: "default",
        default_boundary: "PRIVATE_ORBIT",
      },
      state: {
        summary: "Six founder-locked Systems are active.",
        source_count: 1,
        confidence: 1,
        confidence_kind: "source_coverage_not_truth_probability",
        last_updated: new Date().toISOString(),
        today: null,
        provenance_label: "DETERMINISTIC_OWNER_LEDGER_SYNTHESIS",
      },
      active_systems: [],
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
    });
    if (path === "/universe/map-summary") return json(route, { provenance_label: "OWNER_LEDGER", counts: [], nodes: [] });
    if (path === "/universe/orbits-summary") return json(route, { provenance_label: "OWNER_LEDGER", orbits: [] });
    if (path === "/universe/timeline") return json(route, { provenance_label: "OWNER_LEDGER", items: [] });
    if (path === "/universe/insights-summary") return json(route, { provenance_label: "OWNER_LEDGER", counts: {}, claims: [], contradictions: [], predictions: [], review_queue: [] });
    if (path === "/glow/summary") return json(route, { balance: 12, lifetime_points: 12, today_points: 2, weekly_points: 12, level: 1, rank: "Orbit Seed", next_unlock: null, recent_transactions: [], streaks: [], achievements: [], daily_quest: {}, weekly_mission: {} });
    if (path === "/capsules/cap-active/view") return json(route, {
      capsule_id: "cap-active", state: "ACTIVE", title: "Quiet Ambition", purpose: "Prepare a useful design response",
      owner_display: "Mahnoor", capability: "ASK_SCOPED_QUESTIONS", expires_at: null,
      recipient_instructions: "Stay inside the approved decision.",
      safety_copy: "This does not speak for Mahnoor. It answers only from approved context.",
      included: [{ source_id: "decision-1", source_kind: "decision", representation: "full", title: "Trust boundary", body: "Postgres RLS is the trust boundary." }],
      excluded_summary: [{ source_kind: "reference", count: 1, note: "withheld by the owner" }], grant_id: "grant-1",
    });
    if (path === "/capsules/cap-active/questions") return json(route, {
      question: "What is the trust boundary?", answer_text: "Postgres RLS is the approved trust boundary.",
      answer_mode: "EXTRACTIVE", source_refs: ["decision-1"], confidence: 1,
      policy_explanation: "Answered only from one included decision.", created_at: new Date().toISOString(),
    }, 201);
    if (path === "/omega/dashboard") return json(route, {
      statuses: { evidence_graph: "IMPLEMENTED", sentience_status: "UNRESOLVED_SENTIENCE_STATUS" },
      claims: [{ id: claimId, claim_text: "Smaller moves improve return rate", truth_status: "HYPOTHESIS", confidence: .62 }],
      contradictions: [{ id: "c1", description: "Urgency conflicts with available capacity", proposed_resolution: "Compare the next outcome", severity: "MEDIUM" }],
      predictions: [{ id: "p1", prediction_text: "A smaller task will be returned", expected_observation: "One persisted outcome", status: "OPEN" }],
      consolidation_runs: [],
      learning_proposals: [{ id: "l1", description: "Prefer smaller next moves", evidence_summary: "Two owner outcomes", status: "PROPOSED" }],
      recent_experiences: [],
      review_queue: [{ id: "r1", candidate_claim_text: "Low-energy days need smaller moves", reason: "Sensitive inference", sensitivity: "PRIVATE", status: "PENDING_REVIEW" }],
    });
    if (path === "/omega/scheduler-status") return json(route, { enabled: true, scheduled_consolidation: true, interval_hours: 24, worker_mode: "local_celery_beat", last_consolidation_run_at: null, last_consolidation_status: "none_yet", provenance_label: "owner_ledger" });
    if (path === "/omega/review-queue") return json(route, [{ id: "r1", candidate_claim_text: "Low-energy days need smaller moves", reason: "Sensitive inference", sensitivity: "PRIVATE", status: "PENDING_REVIEW" }]);
    if (path === `/omega/claims/${claimId}/why-changed`) return json(route, { claim_id: claimId, claim_text: "Smaller moves improve return rate", current_truth_status: "HYPOTHESIS", current_confidence: .62, changed_because: ["A completed smaller action was recorded"], supporting_edges: ["OUTCOME"], contradicting_edges: [], unresolved_note: "One more outcome is needed." });
    if (path === `/omega/claims/${claimId}/evidence`) return json(route, [{ id: "edge1", claim_id: claimId, evidence_kind: "EXPERIENCE", evidence_id: "experience1", relation: "SUPPORTS", strength: .7, note: "Owner returned an outcome" }]);
    const consultation = {
      id: consultationId, owner_user_id: ownerId, room_id: null, orbit_id: orbitId,
      system_slug: "quiet-ambition", title: "Release consultation",
      question: "What evidence is enough to release?", purpose: "Make one bounded decision.",
      desired_outcome: "A release decision with a return check.",
      scope_statement: "Only explicit Consultation records.", current_stage: "GATHER",
      status: "ACTIVE", is_demo: false, current_user_role: "OWNER",
      privacy: "BOUNDED_CONSULTATION_ONLY", created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
    };
    if (path === "/consultations" && request.method() === "GET") return json(route, [consultation]);
    if (path === `/consultations/${consultationId}`) return json(route, {
      consultation,
      completed_stages: [{ id: "stage-1", consultation_id: consultationId, owner_user_id: ownerId, stage: "ORIENT", stage_payload: { actual_question: "What evidence is enough?" }, provenance_label: "OWNER_WRITTEN", created_at: new Date().toISOString() }],
      contributions: [{ id: "contribution-1", consultation_id: consultationId, owner_user_id: ownerId, contribution_type: "COUNTEREXAMPLE", body: "A green visual test does not replace privacy proof.", evidence: [], language_tag: "en", provenance_label: "MEMBER_WRITTEN", is_demo: false, created_at: new Date().toISOString() }],
      stage_order: ["ORIENT", "GATHER", "MAP", "MOVE", "RETURN"], next_stage: "GATHER",
      what_nur_may_be_wrong_about: "This synthesis is incomplete until RETURN evidence exists.",
    });
    if (path.startsWith(`/consultations/${consultationId}/`) && request.method() === "POST") {
      consultationWrites.push({ path, body: request.postDataJSON() as Record<string, unknown> });
      if (path.endsWith("/contributions")) return json(route, { id: "contribution-2", consultation_id: consultationId, owner_user_id: ownerId, contribution_type: "LIVED_EXPERIENCE", body: "The source-bound flow worked.", evidence: [], language_tag: "en", provenance_label: "MEMBER_WRITTEN", is_demo: false, created_at: new Date().toISOString() }, 201);
      return json(route, { id: "stage-2", consultation_id: consultationId, owner_user_id: ownerId, stage: "GATHER", stage_payload: { note: "Evidence gathered" }, provenance_label: "OWNER_WRITTEN", created_at: new Date().toISOString(), glow: null }, 201);
    }
    const room = { id: roomId, owner_user_id: ownerId, orbit_id: orbitId, title: "NUR release room", description: "Bounded release evidence only.", room_kind: "GROUP", system_slug: "quiet-ambition", language_tag: "en", status: "ACTIVE", is_demo: false, current_user_role: "OWNER", privacy: "Room content only. Private Talk, Journal, Timeline, and Omega stay unreachable.", created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    const post = { id: postId, room_id: roomId, owner_user_id: ownerId, title: "Release evidence", body: "Return one verified result.", language_tag: "en", provenance_label: "OWNER_WRITTEN", is_demo: false, created_at: new Date().toISOString() };
    if (path === "/community/rooms" && request.method() === "GET") return json(route, [room]);
    if (path === `/community/rooms/${roomId}`) return json(route, room);
    if (path === `/community/rooms/${roomId}/summary`) return json(route, { room, counts: { messages: 1, posts: 1, comments: 1, positions: 0, decisions: 0, members: 2 }, truth_state: "PERSISTED_ROOM_LEDGER", external_public_feed: "not_connected" });
    if (path === `/community/rooms/${roomId}/messages` && request.method() === "GET") return json(route, [{ id: "message-1", room_id: roomId, owner_user_id: ownerId, body: "The privacy suite is green.", language_tag: "en", provenance_label: "MEMBER_WRITTEN", is_demo: false, created_at: new Date().toISOString() }]);
    if (path === `/community/rooms/${roomId}/posts` && request.method() === "GET") return json(route, [post]);
    if (path === `/community/rooms/${roomId}/posts/${postId}/comments` && request.method() === "GET") return json(route, [{ id: "comment-1", room_id: roomId, post_id: postId, parent_comment_id: null, owner_user_id: ownerId, body: "Confirmed with owned evidence.", language_tag: "en", is_demo: false, created_at: new Date().toISOString() }]);
    if (path.startsWith(`/community/rooms/${roomId}/`) && request.method() === "POST") {
      communityWrites.push({ path, body: request.postDataJSON() as Record<string, unknown> });
      if (path.endsWith("/comments")) return json(route, { id: "comment-2", room_id: roomId, post_id: postId, parent_comment_id: null, owner_user_id: ownerId, body: "A bounded reply.", language_tag: "en", is_demo: false, created_at: new Date().toISOString(), glow: { status: "AWARDED", awarded_points: 6 } }, 201);
      return json(route, { id: "reaction-1", room_id: roomId }, 201);
    }
    const project = { id: projectId, owner_user_id: ownerId, orbit_id: orbitId, title: "NUR release", objective: "Ship evidence-backed V197 NUR.", status: "ACTIVE", system_slug: "quiet-ambition", deadline: null, budget_cents: 0, permission_policy: { external_actions_require_owner_approval: true }, created_at: new Date().toISOString(), updated_at: new Date().toISOString() };
    if (path === "/projects" && request.method() === "GET") return json(route, [project]);
    if (path === `/projects/${projectId}`) return json(route, project);
    if (path === `/projects/${projectId}/tasks` && request.method() === "GET") return json(route, [{ id: "task-1", project_id: projectId, title: "Run privacy proof", acceptance_criteria: "All RLS tests pass", status: "READY", priority: 90 }]);
    if (path === `/projects/${projectId}/runs` && request.method() === "GET") return json(route, [{ id: "run-1", project_id: projectId, role: "security reviewer", request_summary: "Review RLS evidence", status: "PROPOSED" }]);
    if (path === `/projects/${projectId}/evidence`) return json(route, [{ id: "evidence-1", project_id: projectId, summary: "78 backend tests passed", verification_status: "PASSED" }]);
    if (path === `/projects/${projectId}/reviews`) return json(route, [{ id: "review-1", project_id: projectId, decision: "APPROVE", note: "Boundary proof accepted" }]);
    if (path === `/projects/${projectId}/artifacts`) return json(route, []);
    if ((path.startsWith(`/projects/${projectId}/`) || path.startsWith("/projects/runs/")) && request.method() === "POST") {
      projectWrites.push({ path, body: request.postDataJSON() as Record<string, unknown> });
      return json(route, { id: "run-2", project_id: projectId, status: "PROPOSED" }, 201);
    }
    if (path === "/notifications/preferences" && request.method() === "GET") return json(route, notificationPreferences);
    if (path === "/notifications/preferences" && request.method() === "PATCH") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      notificationWrites.push({ path, body: payload });
      notificationPreferences = { ...notificationPreferences, ...payload, delivery_status: "IN_APP_ONLY" };
      return json(route, notificationPreferences);
    }
    if (path === "/notifications" && request.method() === "GET") return json(route, [{
      id: notificationId, category: "PROGRESS", title: "Return to one real move",
      body: "One owner-written reminder is waiting.", route: "/plan",
      source_type: "OWNER_REMINDER", provenance_label: "OWNER_WRITTEN",
      delivery_state: "IN_APP", is_demo: false,
      read_at: notificationRead ? new Date().toISOString() : null,
      created_at: new Date().toISOString(),
    }]);
    if (path === "/notifications/reminders" && request.method() === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      notificationWrites.push({ path, body: payload });
      return json(route, { id: "notification-2", ...payload, source_type: "OWNER_REMINDER", provenance_label: "OWNER_WRITTEN", delivery_state: "IN_APP", read_at: null, created_at: new Date().toISOString() }, 201);
    }
    if (path === `/notifications/${notificationId}/read` && request.method() === "POST") {
      notificationRead = true;
      notificationWrites.push({ path, body: request.postDataJSON() as Record<string, unknown> });
      return json(route, { id: notificationId, read_at: new Date().toISOString() });
    }
    if (["/cognition/talk-thread", "/journal", "/plans", "/research/briefs"].includes(path)) return json(route, []);
    if (["/universe/live", "/map", "/glow/scoreboard", "/projects/summary"].includes(path)) return json(route, null);
    return json(route, request.method() === "GET" ? [] : {}, request.method() === "POST" ? 201 : 200);
  });
  return { preferenceWrites, consultationWrites, communityWrites, projectWrites, notificationWrites, passwordWrites };
}

async function screenshot(page: Page, name: string): Promise<void> {
  const path = join(proofRoot, name);
  await mkdir(dirname(path), { recursive: true });
  await page.screenshot({ path, fullPage: true, animations: "disabled" });
}

test("dedicated Universe chambers fetch only their scoped owner data", async ({ page }) => {
  test.slow();
  const requested: string[] = [];
  page.on("request", request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith("/api/v1/")) {
      requested.push(`${request.method()} ${url.pathname}${url.search}`);
    }
  });
  await installMocks(page);
  const chambers = [
    {
      route: "/universe/consultation",
      title: "A question moves when context returns.",
      current: "◌ Consultation",
      requests: [
        "GET /api/v1/auth/me",
        "GET /api/v1/consultations",
        "GET /api/v1/community/rooms",
      ],
    },
    {
      route: "/universe/research",
      title: "Research that shows its evidence.",
      current: "⌕ Research",
      requests: [
        "GET /api/v1/auth/me",
        "GET /api/v1/research/briefs",
        "GET /api/v1/research/jobs",
        "GET /api/v1/research/sources",
        "GET /api/v1/research/claims",
      ],
    },
    {
      route: "/universe/community",
      title: "Shared signal without private spill.",
      current: "◎ Community",
      requests: [
        "GET /api/v1/auth/me",
        "GET /api/v1/community/rooms",
        `GET /api/v1/community/rooms/${roomId}/posts`,
      ],
    },
    {
      route: "/universe/experts",
      title: "Expert voice with provenance attached.",
      current: "✣ Experts",
      requests: [
        "GET /api/v1/auth/me",
        "GET /api/v1/experts/profiles",
        "GET /api/v1/experts/verifications",
        "GET /api/v1/community/rooms",
        "GET /api/v1/research/sources",
        `GET /api/v1/experts/rooms/${roomId}/contributions`,
      ],
    },
    {
      route: "/universe/insights/candidates",
      title: "Candidate insight, never silent truth.",
      current: "✧ Candidates",
      requests: [
        "GET /api/v1/auth/me",
        "GET /api/v1/insights?limit=80",
      ],
    },
  ] as const;
  const universe = page.frameLocator("#nur-universe-stage");

  for (const chamber of chambers) {
    requested.length = 0;
    await page.goto(chamber.route, { waitUntil: "networkidle" });
    const root = universe.locator("#nur-v197-adjunct-root");
    await expect(root).toBeVisible();
    await expect(root.locator("h1")).toHaveText(chamber.title);
    await expect(root.locator('.nur-adjunct-universe-nav [aria-current="page"]'))
      .toHaveText(chamber.current);
    expect([...new Set(requested)].sort()).toEqual([...chamber.requests].sort());
    const geometry = await universe.locator("body").evaluate(() => {
      const ids = [...document.querySelectorAll("[id]")].map(node => node.id);
      const visible = (selector: string) => {
        const node = document.querySelector<HTMLElement>(selector);
        if (!node) return false;
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        return style.display !== "none" && style.visibility !== "hidden"
          && Number(style.opacity) > 0 && rect.width > 1 && rect.height > 1;
      };
      return {
        documentWidth: document.documentElement.scrollWidth,
        viewportWidth: innerWidth,
        duplicateIds: [...new Set(ids.filter((id, index) => ids.indexOf(id) !== index))],
        galaxy: visible("#space3d"),
        brain: visible("#nur-brain-canvas"),
      };
    });
    expect(geometry.documentWidth).toBe(geometry.viewportWidth);
    expect(geometry.duplicateIds).toEqual([]);
    expect(geometry.galaxy).toBe(true);
    expect(geometry.brain).toBe(true);
  }

  requested.length = 0;
  await universe.locator(".nur-adjunct-universe-nav button").first().click();
  await expect(page).toHaveURL(/\/universe$/);
  await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);
  await expect(universe.locator("#nur-brain-canvas")).toBeVisible();
  await expect(universe.locator("body"))
    .toHaveAttribute("data-nur-live-provenance", "OWNER_LEDGER_AGGREGATE");
  await expect(universe.locator("#page-systems .page-sub"))
    .toContainText("Six founder-locked Systems are active.");
  expect(requested).toContain("GET /api/v1/universe/live");
  expect(requested).toContain("GET /api/v1/cognition/talk-thread");
  expect(requested).toContain("GET /api/v1/community/rooms");
});

test("Settings is a real V197-native owner surface and persists language", async ({ page }, testInfo) => {
  const state = await installMocks(page);
  await page.goto("/settings");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  const adjunct = universe.locator("#nur-v197-adjunct-root");
  await expect(adjunct).toBeVisible();
  await expect(adjunct).toHaveAttribute("data-v197-native-adjunct", "true");
  await expect(universe.locator('[data-adjunct-control="locale"] option')).toHaveCount(35);
  await universe.locator('[data-adjunct-control="locale"]').selectOption("ur");
  await universe.locator('[data-adjunct-control="writing-preference"]').selectOption("roman");
  await universe.locator('[data-adjunct-action="settings-save"]').click();
  await expect.poll(() => state.preferenceWrites.length).toBe(1);
  expect(state.preferenceWrites[0]).toMatchObject({ locale: "ur", writing_preference: "roman" });
  await screenshot(page, `${testInfo.project.name}-settings-v197-native.png`);
});

test("owner menu discovers adjunct chambers without a direct URL", async ({ page }) => {
  await installMocks(page);
  await page.goto("/today");
  const universe = page.frameLocator("#nur-universe-stage");
  await universe.locator(".nur-user").click();
  await expect(universe.locator("#nur-v197-owner-auth-menu")).toBeVisible();
  await universe.locator('[data-owner-route="/settings"]').click();
  await expect(page).toHaveURL(/\/settings$/);
  await expect(universe.locator("#nur-v197-adjunct-root")).toBeVisible();
  await expect(universe.locator("#nur-v197-adjunct-root h1")).toHaveText("Your NUR, held on your terms.");
});

test("Settings changes the password and returns to the signed-out Entry", async ({ page }) => {
  const state = await installMocks(page);
  await page.goto("/settings");
  const universe = page.frameLocator("#nur-universe-stage");
  await universe.locator('[data-adjunct-control="current-password"]').fill("current-private-password");
  await universe.locator('[data-adjunct-control="new-password"]').fill("new-private-password-2026");
  await universe.locator('[data-adjunct-control="confirm-password"]').fill("new-private-password-2026");
  await universe.locator('[data-adjunct-action="settings-change-password"]').click();

  await expect.poll(() => state.passwordWrites.length).toBe(1);
  expect(state.passwordWrites[0]).toEqual({
    current_password: "current-private-password",
    new_password: "new-private-password-2026",
  });
  await expect(page).toHaveURL(/\/auth$/);
  await expect(page.frameLocator("#nur-entry-stage").locator("#f4-signin")).toBeVisible();
});

test("full-screen adjuncts isolate and restore the canonical keyboard surface", async ({ page }) => {
  await installMocks(page);
  await page.goto("/settings");
  const universe = page.frameLocator("#nur-universe-stage");
  const adjunct = universe.locator("#nur-v197-adjunct-root");
  await expect(adjunct).toBeVisible();

  const isolated = await universe.locator("body").evaluate(() => {
    const root = document.getElementById("nur-v197-adjunct-root");
    const canonical = document.getElementById("nur-front-v61");
    const background = Array.from(document.body.children)
      .filter((node): node is HTMLElement => node instanceof HTMLElement && node !== root);
    return {
      backgroundCount: background.length,
      background: background.map(node => ({
        tag: node.tagName,
        id: node.id,
        className: node.className.toString(),
        inert: node.inert,
        ariaHidden: node.getAttribute("aria-hidden"),
      })),
      allBackgroundInert: background.every(node => node.inert),
      allBackgroundHidden: background.every(node => node.getAttribute("aria-hidden") === "true"),
      canonicalEffectivelyInert: Boolean(canonical?.closest("[inert]")),
      focusInsideAdjunct: Boolean(root?.contains(document.activeElement)),
    };
  });
  expect(isolated.backgroundCount).toBeGreaterThan(0);
  expect(isolated.allBackgroundInert, JSON.stringify(isolated.background)).toBe(true);
  expect(isolated.allBackgroundHidden, JSON.stringify(isolated.background)).toBe(true);
  expect(isolated.canonicalEffectivelyInert).toBe(true);
  expect(isolated.focusInsideAdjunct).toBe(true);

  await page.keyboard.press("Tab");
  await expect.poll(() => universe.locator("body").evaluate(() => (
    Boolean(document.getElementById("nur-v197-adjunct-root")?.contains(document.activeElement))
  ))).toBe(true);

  await universe.locator('[data-adjunct-route="/systems"]').click();
  await expect(adjunct).toHaveCount(0);
  const restored = await universe.locator("body").evaluate(() => ({
    canonicalEffectivelyInert: Boolean(document.getElementById("nur-front-v61")?.closest("[inert]")),
    inertBodyChildren: Array.from(document.body.children)
      .filter(node => node instanceof HTMLElement && node.inert).length,
  }));
  expect(restored).toEqual({ canonicalEffectivelyInert: false, inertBodyChildren: 0 });
});

test("Capsule adjunct answers only from the approved source", async ({ page }, testInfo) => {
  await installMocks(page);
  await page.goto("/capsule/cap-active");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("What is included");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("withheld by the owner");
  await universe.locator('[data-adjunct-control="capsule-question"]').fill("What is the trust boundary?");
  await universe.locator('[data-adjunct-action="capsule-ask"]').click();
  await expect(universe.locator(".nur-adjunct-answer")).toContainText("Postgres RLS");
  await expect(universe.locator(".nur-adjunct-answer")).toContainText("decision-1");
  await screenshot(page, `${testInfo.project.name}-capsule-active-answer.png`);
});

test("Omega dashboard, review, and why-changed are native evidence surfaces", async ({ page }, testInfo) => {
  await installMocks(page);
  await page.goto("/universe/omega");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Evidence changes the model");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Smaller moves improve return rate");
  await screenshot(page, `${testInfo.project.name}-omega-dashboard.png`);

  await universe.locator('[data-adjunct-action="omega-review"]').click();
  await expect(page).toHaveURL(/\/universe\/omega\/review$/);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Nothing sensitive becomes truth by accident");

  await page.goto(`/universe/omega/why-changed/${claimId}`);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Why NUR changed its mind");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Owner returned an outcome");
  await screenshot(page, `${testInfo.project.name}-omega-why-changed.png`);
});

test("Consultation adjunct preserves disagreement and persists stage movement", async ({ page }, testInfo) => {
  const state = await installMocks(page);
  await page.goto("/consultations");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("A question moves when context returns");
  await universe.locator(`[data-adjunct-action="consultation-open-${consultationId}"]`).click();
  await expect(page).toHaveURL(new RegExp(`/universe/consultation/${consultationId}$`));
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("A green visual test does not replace privacy proof");
  await universe.locator('textarea[placeholder^="Add only what belongs"]').fill("The source-bound flow worked.");
  await universe.locator('[data-adjunct-action="consultation-contribute"]').click();
  await expect.poll(() => state.consultationWrites.some(row => row.path.endsWith("/contributions"))).toBe(true);
  const movement = universe.locator(".nur-adjunct-panel").filter({ hasText: "Complete GATHER" });
  await movement.locator("textarea").fill("Evidence gathered without erasing disagreement.");
  await movement.locator('[data-adjunct-action="consultation-stage-gather"]').click();
  await expect.poll(() => state.consultationWrites.some(row => row.path.endsWith("/stages/GATHER"))).toBe(true);
  await screenshot(page, `${testInfo.project.name}-consultation-gather.png`);
});

test("Community adjunct renders only persisted bounded threads and reactions", async ({ page }, testInfo) => {
  const state = await installMocks(page);
  await page.goto("/community");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("No fake people, replies, activity or live public count");
  await universe.locator(`[data-adjunct-action="community-post-${postId}"]`).click();
  await expect(page).toHaveURL(new RegExp(`/community/post/${postId}`));
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Confirmed with owned evidence");
  await universe.locator('[data-adjunct-action="community-react-useful"]').click();
  await expect.poll(() => state.communityWrites.some(row => row.path.endsWith("/reactions"))).toBe(true);
  await screenshot(page, `${testInfo.project.name}-community-thread.png`);
});

test("AM Project adjunct exposes evidence and owner approval gates", async ({ page }, testInfo) => {
  const state = await installMocks(page);
  await page.goto("/projects");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  await universe.locator(`[data-adjunct-action="project-open-${projectId}"]`).click();
  await expect(page).toHaveURL(new RegExp(`/projects/${projectId}/overview$`));
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("78 backend tests passed");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("No run can pre-authorize spending");
  await universe.locator('[data-adjunct-action="project-run-approve-run-1"]').click();
  await expect.poll(() => state.projectWrites.some(row => row.path.endsWith("/approve"))).toBe(true);
  await screenshot(page, `${testInfo.project.name}-am-project-evidence-gate.png`);
});

test("Notifications are owner-written, persisted, and never fake social pressure", async ({ page }, testInfo) => {
  const state = await installMocks(page);
  await page.goto("/notifications");
  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  const adjunct = universe.locator("#nur-v197-adjunct-root");
  await expect(adjunct).toContainText("Return cues, under your control");
  await expect(adjunct).toContainText("There are no fabricated replies");
  await expect(adjunct).toContainText("Return to one real move");

  await universe.locator('[data-adjunct-action="notification-read-88888888-8888-8888-8888-888888888888"]').click();
  await expect.poll(() => state.notificationWrites.some(row => row.path.endsWith("/read"))).toBe(true);
  await expect(universe.locator('[data-adjunct-action="notification-read-88888888-8888-8888-8888-888888888888"]')).toHaveCount(0);

  await universe.locator('[data-adjunct-control="notification-frequency"]').selectOption("QUIET");
  await universe.locator('[data-adjunct-action="notification-preferences-save"]').click();
  await expect.poll(() => state.notificationWrites.some(row => row.path === "/notifications/preferences" && row.body.frequency === "QUIET")).toBe(true);

  await universe.locator('[data-adjunct-control="notification-title"]').fill("Return to the release proof");
  await universe.locator('[data-adjunct-control="notification-body"]').fill("Run the final owner-scoped check.");
  await universe.locator('[data-adjunct-action="notification-reminder-create"]').click();
  await expect.poll(() => state.notificationWrites.some(row => row.path === "/notifications/reminders")).toBe(true);
  await screenshot(page, `${testInfo.project.name}-notifications-owner-ledger.png`);
});

test("Phase-H Notifications and Localization routes persist owner state across reload", async ({ page }) => {
  const state = await installMocks(page);
  const universe = page.frameLocator("#nur-universe-stage");

  await page.goto("/notifications", { waitUntil: "networkidle" });
  const notifications = universe.locator("#nur-v197-adjunct-root");
  await expect(notifications).toContainText("Return cues, under your control");
  await expect(notifications).toContainText("IN_APP_ONLY");
  await universe.locator('[data-adjunct-control="notification-frequency"]').selectOption("QUIET");
  await universe.locator('[data-adjunct-action="notification-preferences-save"]').click();
  await expect.poll(() => state.notificationWrites.some(row => row.path === "/notifications/preferences" && row.body.frequency === "QUIET")).toBe(true);
  await page.reload({ waitUntil: "networkidle" });
  await expect(universe.locator('[data-adjunct-control="notification-frequency"]')).toHaveValue("QUIET");

  await page.goto("/settings", { waitUntil: "networkidle" });
  const settings = universe.locator("#nur-v197-adjunct-root");
  await expect(settings).toContainText("Language and voice");
  await universe.locator('[data-adjunct-control="locale"]').selectOption("ur");
  await universe.locator('[data-adjunct-control="writing-preference"]').selectOption("roman");
  await universe.locator('[data-adjunct-action="settings-save"]').click();
  await expect.poll(() => state.preferenceWrites.some(row => row.locale === "ur" && row.writing_preference === "roman")).toBe(true);
  await page.reload({ waitUntil: "networkidle" });
  await expect(universe.locator('[data-adjunct-control="locale"]')).toHaveValue("ur");
  await expect(universe.locator('[data-adjunct-control="writing-preference"]')).toHaveValue("roman");
  await expect(universe.locator("html")).toHaveAttribute("lang", "ur");
  await expect(universe.locator("html")).toHaveAttribute("dir", "ltr");
});
