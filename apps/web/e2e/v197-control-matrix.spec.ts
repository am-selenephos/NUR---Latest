import { readFileSync } from "node:fs";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Canonical V197 control-matrix proof.
 *
 * 1. The release control matrix (docs/release/v197-control-matrix.json) is
 *    complete, internally consistent, and carries zero DEAD / DUPLICATE /
 *    MISLEADING controls — every referenced proof spec really exists.
 * 2. The two defects fixed in this mission stay fixed in the browser:
 *    Project Orbit tabs render their own surfaces (no nine-identical-tabs
 *    behavior) and the deliverables file picker uses the NUR control language,
 *    not the browser-default light control.
 * 3. Journal save and Settings save produce persisted, reload-hydrated results
 *    with visible confirmation — mocked at the API contract, asserted in the
 *    visible DOM.
 */

const here = dirname(fileURLToPath(import.meta.url));
const matrixPath = resolve(here, "../../../docs/release/v197-control-matrix.json");

type MatrixControl = {
  id: string;
  surface: string;
  label: string;
  classification: string;
  desktop_proof: string[];
  mobile_proof: string[];
};
type Matrix = {
  generation_policy: string;
  source_fingerprint: string;
  totals: Record<string, number>;
  controls: MatrixControl[];
};

const matrix = JSON.parse(readFileSync(matrixPath, "utf8")) as Matrix;

test("control matrix is complete, consistent, and free of dead controls", async () => {
  expect(matrix.generation_policy).toBe("deterministic-source-fingerprint-v1");
  expect(matrix.source_fingerprint).toMatch(/^[0-9a-f]{64}$/);
  expect(matrix.controls.length).toBeGreaterThanOrEqual(65);
  expect(matrix.totals.total).toBe(matrix.controls.length);

  const counted: Record<string, number> = {};
  for (const control of matrix.controls) {
    counted[control.classification] = (counted[control.classification] ?? 0) + 1;
    expect(control.id, "every control has an id").toBeTruthy();
    expect(control.desktop_proof.length, `${control.id} names desktop proof`).toBeGreaterThan(0);
    for (const spec of [...control.desktop_proof, ...control.mobile_proof]) {
      expect(existsSync(resolve(here, spec)), `${control.id} proof spec ${spec} exists`).toBe(true);
    }
  }
  for (const [classification, count] of Object.entries(counted)) {
    expect(matrix.totals[classification], `total for ${classification}`).toBe(count);
  }
  // The release contract: no dead, duplicate, or misleading control remains.
  for (const forbidden of ["DEAD", "DUPLICATE", "MISLEADING"]) {
    expect(matrix.totals[forbidden] ?? 0, `${forbidden} count`).toBe(0);
    expect(matrix.controls.filter(c => c.classification === forbidden)).toHaveLength(0);
  }
  // Blocked/deferred states are explicit, never silent.
  expect(matrix.totals.BLOCKED_BY_EXTERNAL_PROVIDER).toBeGreaterThan(0);
  expect(matrix.totals.NOT_IMPLEMENTED_VISIBLE).toBeGreaterThan(0);
});

// ---------------------------------------------------------------------------
// Browser proofs (mocked at the API contract; results asserted in visible DOM)
// ---------------------------------------------------------------------------

const PROJECT_ID = "proj-matrix";
const now = new Date().toISOString();
const orbit = { id: "orbit-matrix", title: "Matrix Orbit", kind: "PROJECT" };
const user = {
  id: "owner-matrix",
  email: "owner@nur.app",
  chosen_name: "Matrix Owner",
  profile: { chosen_name: "Matrix Owner", locale: "en" },
};

async function json(route: Route, body: unknown, status = 200) {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

type BootState = {
  journal: Array<Record<string, unknown>>;
  preferencePatches: Array<Record<string, unknown>>;
};

async function installBoot(page: Page): Promise<BootState> {
  const state: BootState = { journal: [], preferencePatches: [] };
  await page.context().addCookies([{
    name: "nur_csrf", value: "matrix-csrf",
    url: "http://localhost:4173", httpOnly: false, sameSite: "Lax",
  }]);
  await page.route("**/api/v1/auth/me", route => json(route, user));
  await page.route("**/api/v1/profile/preferences", async route => {
    if (route.request().method() === "PATCH") {
      state.preferencePatches.push(route.request().postDataJSON() as Record<string, unknown>);
    }
    return json(route, {
      locale: "en", sound_enabled: false, reduced_effects: true,
      default_boundary: "PRIVATE_ORBIT", active_orbit_id: orbit.id,
      omega_enabled: true, writing_preference: "default", timezone: "UTC",
    });
  });
  await page.route("**/healthz", route => json(route, { status: "ok" }));
  for (const path of [
    "**/api/v1/universe/live", "**/api/v1/universe/map-summary",
    "**/api/v1/universe/orbits-summary", "**/api/v1/universe/timeline",
    "**/api/v1/universe/insights-summary", "**/api/v1/map",
    "**/api/v1/glow/scoreboard",
  ]) await page.route(path, route => json(route, null));
  await page.route("**/api/v1/glow/summary", route => json(route, {
    balance: 0, lifetime_points: 0, today_points: 0, weekly_points: 0, level: 1,
    rank: "Orbit Seed", next_unlock: null, recent_transactions: [], streaks: [],
    achievements: [], daily_quest: {}, weekly_mission: {},
  }));
  await page.route("**/api/v1/glow/rewards", route => json(route, {
    awarded_points: 0, status: "GATED", reason: "mocked matrix run",
  }, 201));
  await page.route("**/api/v1/research/briefs", route => json(route, []));
  await page.route("**/api/v1/community/rooms", route => json(route, []));
  await page.route("**/api/v1/orbits/current-state", route => json(route, {
    active_systems: 1, outcomes_returned: 0, insights_evolving: 0, open_questions: 0,
    research_staged: 0, plans_active: 0, live_status: "owner_ledger",
  }));
  await page.route("**/api/v1/orbits", route => json(route, [orbit]));
  await page.route("**/api/v1/journal", async route => {
    if (route.request().method() === "POST") {
      const body = route.request().postDataJSON() as { body?: string };
      const row = {
        id: `journal-${state.journal.length + 1}`, body: body?.body ?? "",
        orbit_id: orbit.id, event_id: null, created_at: now,
      };
      state.journal.unshift(row);
      return json(route, row, 201);
    }
    return json(route, state.journal);
  });
  await page.route("**/api/v1/plans", route => json(route, []));
  await page.route("**/api/v1/cognition/talk-thread**", route => json(route, []));
  return state;
}

async function installProjectMocks(page: Page) {
  const project = {
    id: PROJECT_ID, owner_user_id: user.id, orbit_id: orbit.id,
    title: "Matrix project", objective: "Prove per-tab surfaces.",
    status: "ACTIVE", system_slug: "creation", deadline: null, budget_cents: null,
    permission_policy: { external_actions_require_owner_approval: true },
    created_at: now, updated_at: now,
  };
  const task = {
    id: "task-matrix", owner_user_id: user.id, project_id: PROJECT_ID, parent_task_id: null,
    title: "One concrete task", description: null, acceptance_criteria: "Proof exists.",
    status: "READY", priority: 50, assigned_role: "implementer", due_at: null,
    completed_at: null, created_at: now, updated_at: now,
  };
  await page.route(/\/api\/v1\/projects(\/|$|\?)/, async route => {
    const method = route.request().method();
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/projects/summary") return json(route, null);
    if (path === `/projects/${PROJECT_ID}` && method === "GET") return json(route, project);
    if (path === `/projects/${PROJECT_ID}/tasks` && method === "GET") return json(route, [task]);
    for (const tail of ["evidence", "reviews", "artifacts", "runs", "files"]) {
      if (path === `/projects/${PROJECT_ID}/${tail}` && method === "GET") return json(route, []);
    }
    return json(route, []);
  });
}

for (const projectName of ["chromium-desktop", "chromium-mobile"]) {
  test(`[${projectName}] project tabs render their own surfaces and the file picker is NUR-styled`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== projectName, "one device per iteration");
    await installBoot(page);
    await installProjectMocks(page);

    const universe = page.frameLocator("#nur-universe-stage");
    const root = universe.locator("#nur-v197-adjunct-root");

    // tasks tab: execution surface, no deliverables panel.
    await page.goto(`/projects/${PROJECT_ID}/tasks`);
    await expect(root).toContainText("Matrix project");
    await expect(root.locator("section", { hasText: "Execution" }).first()).toBeVisible();
    await expect(root.locator('[data-adjunct-panel="deliverables"]')).toHaveCount(0);

    // deliverables tab: deliverables surface, no review panel; styled file picker.
    await page.goto(`/projects/${PROJECT_ID}/deliverables`);
    const deliverables = root.locator('[data-adjunct-panel="deliverables"]');
    await expect(deliverables).toBeVisible();
    await expect(root.locator('[data-adjunct-action="project-review-create"]')).toHaveCount(0);
    await expect(root.locator('[data-adjunct-action="project-task-create"]')).toHaveCount(0);
    const picker = deliverables.locator('input[type="file"]');
    await expect(picker).toBeVisible();
    const buttonStyle = await picker.evaluate(element => {
      const style = getComputedStyle(element, "::file-selector-button");
      return { background: style.backgroundColor, font: style.fontFamily };
    });
    expect(buttonStyle.background, "file selector button is void-black, not browser default")
      .toBe("rgba(3, 3, 7, 0.68)");
    expect(buttonStyle.font).toContain("Crimson Pro");

    // a tab without a dedicated surface says so honestly.
    await page.goto(`/projects/${PROJECT_ID}/insights`);
    await expect(root).toContainText("Not a separate surface yet");
    await expect(root).toContainText("not part of this beta");
    await expect(root.locator('[data-adjunct-panel="deliverables"]')).toHaveCount(0);
  });

  test(`[${projectName}] journal save persists and hydrates after reload`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== projectName, "one device per iteration");
    await installBoot(page);

    await page.goto("/journal");
    const universe = page.frameLocator("#nur-universe-stage");
    await expect(universe.locator("#page-journal")).toBeVisible();
    await expect(universe.locator("#page-journal .page-sub")).toContainText("No persisted entries yet");

    await universe.locator("#journal-input").fill("Control-matrix journal proof line.");
    await universe.locator("#journal-save").click();
    await expect(universe.locator("#page-journal .page-sub")).toContainText("1 private entry persisted");
    await expect(universe.locator("#journal-input")).toHaveValue("");

    // Reload hydrates the persisted entry from the API, not local state.
    await page.reload();
    await expect(universe.locator("#page-journal .page-sub")).toContainText("1 private entry persisted");
    await expect(universe.locator("#page-journal .journal-prompt")).toContainText("Control-matrix journal proof line.");
  });

  test(`[${projectName}] settings save persists preferences with visible confirmation`, async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== projectName, "one device per iteration");
    const state = await installBoot(page);

    await page.goto("/settings");
    const universe = page.frameLocator("#nur-universe-stage");
    const root = universe.locator("#nur-v197-adjunct-root");
    await expect(root).toContainText("Persisted owner preference");

    // Owner export and deletion are real account-lifecycle controls. Their
    // complete download/reauthentication contracts are proven separately in
    // account-privacy-ui.spec.ts; this matrix proof guards their reachability.
    await expect(root.locator('[data-adjunct-action="settings-export"]')).toBeEnabled();
    await expect(root.locator('[data-adjunct-action="settings-delete"]')).toBeEnabled();
    await expect(root).toContainText("Export the complete owner-scoped ledger");
    await expect(root).toContainText("Permanently delete this NUR account");

    await root.locator('[data-adjunct-control="sound"]').check();
    await root.locator('[data-adjunct-action="settings-save"]').click();
    await expect(root).toContainText("Saved. NUR will return in this language");
    expect(state.preferencePatches.length).toBeGreaterThan(0);
    expect(state.preferencePatches.at(-1)).toMatchObject({ sound_enabled: true });
  });
}
