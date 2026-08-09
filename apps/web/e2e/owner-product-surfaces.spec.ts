import { expect, test, type Locator, type Page, type Request, type Route } from "@playwright/test";

import { installNurMocks, mockOrbit, mockUser } from "./helpers/nurMocks";

const NOW = "2026-08-09T12:00:00.000Z";
const CSRF_TOKEN = "owner-product-csrf";
const MEMORY_CANDIDATE_ID = "33333333-3333-4333-8333-333333333333";
const MEMORY_ID = "44444444-4444-4444-8444-444444444444";
const TEACH_CONTRIBUTION_ID = "55555555-5555-4555-8555-555555555555";
const TEACH_CANDIDATE_ID = "66666666-6666-4666-8666-666666666666";
const CHECKOUT_SESSION_ID = "77777777-7777-4777-8777-777777777777";
const CAPSULE_ID = "88888888-8888-4888-8888-888888888888";
const CAPSULE_SOURCE_ID = "99999999-9999-4999-8999-999999999999";
const CAPSULE_SOURCE_OBJECT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa";
const CAPSULE_GRANT_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb";
const RECIPIENT_USER_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
const CHECKOUT_URL = "https://billing.nur.test/checkout/orbit_plus";

type RecordedRequest = {
  method: string;
  path: string;
  search: string;
  body: Record<string, unknown> | null;
  headers: Record<string, string>;
};

type CapsuleRow = {
  id: string;
  orbit_id: string;
  title: string;
  purpose: string;
  capability: string;
  expires_at: string | null;
  revoked_at: string | null;
  version: number;
  created_at: string;
};

type OwnerProductMockState = {
  requests: RecordedRequest[];
  memories: Array<Record<string, unknown>>;
  contributions: Array<Record<string, unknown>>;
  capsules: CapsuleRow[];
};

function apiPath(request: Request): string {
  return new URL(request.url()).pathname;
}

function adjunctRoot(page: Page): Locator {
  return page.frameLocator("#nur-universe-stage").locator("#nur-v197-adjunct-root");
}

async function json(route: Route, body: unknown, status = 200): Promise<void> {
  await route.fulfill({ status, contentType: "application/json", body: JSON.stringify(body) });
}

function memoryRow(canonicalText: string, orbitId = mockOrbit.id): Record<string, unknown> {
  return {
    id: MEMORY_ID,
    orbit_id: orbitId,
    scope: "PRIVATE_ORBIT",
    memory_type: "SEMANTIC",
    canonical_text: canonicalText,
    structured_value: {},
    source_object_ids: {},
    provenance_label: "OWNER_WRITTEN",
    confidence: 1,
    sensitivity: "PRIVATE",
    status: "ACTIVE",
    created_by: "OWNER",
    version: 1,
    superseded_by_memory_id: null,
    expires_at: null,
    deleted_at: null,
    created_at: NOW,
    updated_at: NOW,
  };
}

function memoryCandidate(): Record<string, unknown> {
  return {
    id: MEMORY_CANDIDATE_ID,
    orbit_id: mockOrbit.id,
    source_event_id: null,
    candidate_text: "Returned evidence matters more than confident language.",
    original_text: "Returned evidence matters more than confident language.",
    scope: "PRIVATE_ORBIT",
    memory_type: "EVIDENCE",
    provenance_label: "MODEL_PROPOSED_OWNER_REVIEW_REQUIRED",
    confidence: 0.78,
    sensitivity: "PRIVATE",
    created_by: "NUR",
    source_object_ids: {},
    status: "PENDING",
    review_note: null,
    reviewed_at: null,
    approved_memory_id: null,
    created_at: NOW,
    updated_at: NOW,
  };
}

function teachContribution(content: string, orbitId = mockOrbit.id): Record<string, unknown> {
  return {
    id: TEACH_CONTRIBUTION_ID,
    orbit_id: orbitId,
    contribution_kind: "CORRECTION",
    content,
    language_tag: "en",
    consent_scope: "PRIVATE_OWNER",
    consent_policy_version: "teach-nur-v1",
    consent_granted: true,
    provenance_label: "OWNER_CONTRIBUTION",
    sensitivity: "PRIVATE",
    confidence: 1,
    source_refs: [],
    risk_flags: [],
    deidentification_status: "NOT_REQUESTED",
    verification_status: "PENDING_REVIEW",
    status: "PENDING_REVIEW",
    reviewed_at: null,
    created_at: NOW,
    updated_at: NOW,
    candidate: {
      id: TEACH_CANDIDATE_ID,
      contribution_id: TEACH_CONTRIBUTION_ID,
      candidate_text: content,
      original_text_digest: "sha256:owner-contribution",
      deidentified_text: null,
      provenance_label: "OWNER_CONTRIBUTION_CANDIDATE",
      sensitivity: "PRIVATE",
      confidence: 1,
      source_refs: [],
      risk_flags: [],
      contradiction_refs: [],
      disagreement_map: {},
      status: "PENDING_REVIEW",
      current_knowledge_version_id: null,
      created_at: NOW,
      updated_at: NOW,
    },
    reviews: [],
    knowledge_versions: [],
    evaluations: [],
    model_training_status: "NOT_AUTHORIZED",
    institutional_promotion_status: "OWNER_SCOPED_ONLY",
  };
}

function capsuleRow(overrides: Partial<CapsuleRow> = {}): CapsuleRow {
  return {
    id: CAPSULE_ID,
    orbit_id: mockOrbit.id,
    title: "Focused launch context",
    purpose: "Let one reviewer inspect only the approved launch decision.",
    capability: "ASK_SCOPED_QUESTIONS",
    expires_at: null,
    revoked_at: null,
    version: 1,
    created_at: NOW,
    ...overrides,
  };
}

function recordedRequest(request: Request): RecordedRequest {
  const url = new URL(request.url());
  let body: Record<string, unknown> | null = null;
  if (request.postData()) body = request.postDataJSON() as Record<string, unknown>;
  return {
    method: request.method(),
    path: url.pathname,
    search: url.search,
    body,
    headers: request.headers(),
  };
}

async function installOwnerProductMocks(page: Page): Promise<OwnerProductMockState> {
  await installNurMocks(page);
  await page.context().addCookies([{
    name: "nur_csrf",
    value: CSRF_TOKEN,
    url: "http://localhost:4173",
    sameSite: "Lax",
  }]);

  const state: OwnerProductMockState = {
    requests: [],
    memories: [],
    contributions: [],
    capsules: [],
  };

  await page.route("**/api/v1/**", async route => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    const method = request.method();

    const ownerProductPath = path === "/api/v1/memory-candidates"
      || path === "/api/v1/memories"
      || path === "/api/v1/teach-nur/contributions"
      || path === "/api/v1/billing/plans"
      || path === "/api/v1/billing/subscription"
      || path === "/api/v1/billing/checkout"
      || path === `/api/v1/orbits/${mockOrbit.id}/sources`
      || path === `/api/v1/orbits/${mockOrbit.id}/capsules`
      || path === "/api/v1/capsules"
      || path.startsWith("/api/v1/capsules/");
    if (!ownerProductPath) return route.fallback();

    state.requests.push(recordedRequest(request));

    if (path === "/api/v1/memory-candidates" && method === "GET") {
      return json(route, [memoryCandidate()]);
    }
    if (path === "/api/v1/memories" && method === "GET") {
      return json(route, state.memories);
    }
    if (path === "/api/v1/memories" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      const row = memoryRow(String(payload.canonical_text ?? ""), String(payload.orbit_id ?? ""));
      state.memories.unshift(row);
      return json(route, row, 201);
    }

    if (path === "/api/v1/teach-nur/contributions" && method === "GET") {
      return json(route, state.contributions);
    }
    if (path === "/api/v1/teach-nur/contributions" && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      const row = teachContribution(String(payload.content ?? ""), String(payload.orbit_id ?? ""));
      state.contributions.unshift(row);
      return json(route, row, 201);
    }

    if (path === "/api/v1/billing/plans" && method === "GET") {
      return json(route, [
        {
          code: "orbit_scan_free",
          name: "Orbit Scan Free",
          description: "Owner-scoped foundations.",
          price_minor: 0,
          currency: "USD",
          billing_interval: "none",
          seat_cap: null,
          seats_remaining: null,
          is_free: true,
          active: true,
          legal_copy_version: "billing-v1",
          features: [{ feature_key: "owner_ledger", allowed: true, usage_limit: null }],
        },
        {
          code: "orbit_plus",
          name: "Orbit Plus",
          description: "Expanded governed NUR capacity.",
          price_minor: 1499,
          currency: "USD",
          billing_interval: "month",
          seat_cap: 1,
          seats_remaining: 1,
          is_free: false,
          active: true,
          legal_copy_version: "billing-v1",
          features: [{ feature_key: "expanded_capacity", allowed: true, usage_limit: 100 }],
        },
      ]);
    }
    if (path === "/api/v1/billing/subscription" && method === "GET") {
      return json(route, {
        subscription: null,
        entitlements: [{
          feature_key: "owner_ledger",
          allowed: true,
          usage_limit: null,
          usage_consumed: 0,
          valid_until: null,
          reason: "Orbit Scan Free",
          projection_version: 1,
        }],
        refunds: [],
        provider_configured: true,
        portal_available: false,
        cancellation_note: "No paid subscription. Orbit Scan Free remains available.",
        terms_url: "https://nur.test/terms",
        privacy_url: "https://nur.test/privacy",
        refund_policy_url: "https://nur.test/refunds",
      });
    }
    if (path === "/api/v1/billing/checkout" && method === "POST") {
      return json(route, {
        session_id: CHECKOUT_SESSION_ID,
        plan_code: "orbit_plus",
        provider: "test",
        checkout_url: CHECKOUT_URL,
        status: "PENDING",
        is_test: true,
        reservation_expires_at: "2026-08-09T12:15:00.000Z",
        renews_automatically: true,
        terms_url: "https://nur.test/terms",
        privacy_url: "https://nur.test/privacy",
        refund_policy_url: "https://nur.test/refunds",
      }, 201);
    }

    if (path === `/api/v1/orbits/${mockOrbit.id}/sources` && method === "GET") {
      return json(route, [{
        id: CAPSULE_SOURCE_ID,
        source_kind: "DECISION",
        source_id: CAPSULE_SOURCE_OBJECT_ID,
        inclusion_mode: "FULL",
        created_at: NOW,
      }]);
    }
    if (path === `/api/v1/orbits/${mockOrbit.id}/capsules` && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      const row = capsuleRow({
        title: String(payload.title ?? ""),
        purpose: String(payload.purpose ?? ""),
        capability: String(payload.capability ?? "READ_ONLY"),
        expires_at: payload.expires_at ? String(payload.expires_at) : null,
      });
      state.capsules.unshift(row);
      return json(route, row, 201);
    }
    if (path === "/api/v1/capsules" && method === "GET") {
      return json(route, state.capsules);
    }
    if (path === `/api/v1/capsules/${CAPSULE_ID}/view` && method === "GET") {
      return json(route, { detail: "No capsule is shared with you at this address." }, 404);
    }
    if (path === `/api/v1/capsules/${CAPSULE_ID}/grants` && method === "POST") {
      const payload = request.postDataJSON() as Record<string, unknown>;
      return json(route, {
        id: CAPSULE_GRANT_ID,
        capsule_id: CAPSULE_ID,
        recipient_user_id: RECIPIENT_USER_ID,
        capability: String(payload.capability ?? "READ_ONLY"),
        expires_at: payload.expires_at ? String(payload.expires_at) : null,
        revoked_at: null,
        last_accessed_at: null,
      }, 201);
    }
    if (path === `/api/v1/capsules/${CAPSULE_ID}/revoke` && method === "POST") {
      state.capsules = state.capsules.map(row => row.id === CAPSULE_ID
        ? { ...row, revoked_at: NOW, version: row.version + 1 }
        : row);
      return json(route, state.capsules.find(row => row.id === CAPSULE_ID));
    }
    if (path === `/api/v1/capsules/${CAPSULE_ID}/audit` && method === "GET") {
      return json(route, [{
        event_kind: "VIEWED",
        actor_user_id: mockUser.id,
        grant_id: CAPSULE_GRANT_ID,
        created_at: NOW,
        meta: { granted: true },
      }]);
    }

    return json(route, { detail: `Unhandled owner product mock ${method} ${path}` }, 404);
  });

  return state;
}

function requestFor(state: OwnerProductMockState, method: string, path: string): RecordedRequest {
  const match = state.requests.find(request => request.method === method && request.path === path);
  expect(match, `${method} ${path} should reach the current owner API contract`).toBeDefined();
  return match!;
}

function expectOwnerWrite(request: RecordedRequest): void {
  expect(request.headers["x-csrf-token"]).toBe(CSRF_TOKEN);
  expect(request.body).not.toHaveProperty("owner_user_id");
  expect(request.body).not.toHaveProperty("user_id");
}

test("owner session menu exposes all four real owner product routes", async ({ page }) => {
  await installOwnerProductMocks(page);
  await page.goto("/today", { waitUntil: "networkidle" });

  const universe = page.frameLocator("#nur-universe-stage");
  await universe.locator(".nur-user").click();
  const menu = universe.locator("#nur-v197-owner-auth-menu");
  await expect(menu).toBeVisible();
  for (const route of ["/memory", "/teach-nur", "/billing", "/capsules"]) {
    await expect(menu.locator(`[data-owner-route="${route}"]`), `${route} must be owner-reachable`).toBeVisible();
  }
});

test("Memory route reads owner state and writes only to the active Orbit", async ({ page }) => {
  const state = await installOwnerProductMocks(page);
  await page.goto("/memory", { waitUntil: "networkidle" });

  await expect(page).toHaveURL(/\/memory$/);
  await expect(page.locator("#root")).toHaveCount(0);
  const root = adjunctRoot(page);
  await expect(root).toHaveAttribute("data-v197-native-adjunct", "true");
  await expect(root.locator("h1")).toHaveText("Memory stays proposed until you choose it.");
  requestFor(state, "GET", "/api/v1/memory-candidates");
  requestFor(state, "GET", "/api/v1/memories");
  await expect(root.getByText("Returned evidence matters more than confident language.")).toBeVisible();

  const canonicalText = "Keep owner evidence separate from confident inference.";
  await root.locator('[data-adjunct-control="memory-create-text"]').fill(canonicalText);
  const writePromise = page.waitForRequest(request => (
    request.method() === "POST" && apiPath(request) === "/api/v1/memories"
  ));
  await root.locator('[data-adjunct-action="memory-create"]').click();
  const write = recordedRequest(await writePromise);

  expectOwnerWrite(write);
  expect(write.body).toMatchObject({
    canonical_text: canonicalText,
    structured_value: {},
    orbit_id: mockOrbit.id,
    memory_type: "SEMANTIC",
    sensitivity: "PRIVATE",
    confidence: 1,
  });
  expect(write.body?.orbit_id).not.toBe(mockUser.orbit.id);
  await expect(root.getByText(canonicalText)).toBeVisible();
  await expect(root.getByText("Memory persisted by your explicit choice.")).toBeVisible();
});

test("Teach NUR route keeps submission disabled until explicit scoped consent", async ({ page }) => {
  const state = await installOwnerProductMocks(page);
  await page.goto("/teach-nur", { waitUntil: "networkidle" });

  await expect(page).toHaveURL(/\/teach-nur$/);
  const root = adjunctRoot(page);
  await expect(root.locator("h1")).toHaveText("Teach NUR without surrendering authority.");
  requestFor(state, "GET", "/api/v1/teach-nur/contributions");
  await expect(root.getByText(/never authorizes model training/i)).toBeVisible();

  const submit = root.locator('[data-adjunct-action="teach-create"]');
  const content = "A returned outcome should outrank an untested prediction.";
  await expect(submit).toBeDisabled();
  await root.locator('[data-adjunct-control="teach-content"]').fill(content);
  await expect(submit).toBeDisabled();
  await root.locator('[data-adjunct-control="teach-consent"]').check();
  await expect(submit).toBeEnabled();

  const writePromise = page.waitForRequest(request => (
    request.method() === "POST" && apiPath(request) === "/api/v1/teach-nur/contributions"
  ));
  await submit.click();
  const write = recordedRequest(await writePromise);

  expectOwnerWrite(write);
  expect(write.headers["idempotency-key"]).toMatch(/^v197-teach-create:/);
  expect(write.body).toMatchObject({
    contribution_kind: "CORRECTION",
    content,
    orbit_id: mockOrbit.id,
    language_tag: "en",
    consent_scope: "PRIVATE_OWNER",
    consent_granted: true,
    consent_policy_version: "teach-nur-v1",
    sensitivity: "PRIVATE",
    confidence: 1,
    source_refs: [],
  });
  expect(write.body?.orbit_id).not.toBe(mockUser.orbit.id);
  await expect(root.getByText(content)).toBeVisible();
  await expect(root.getByText("Contribution entered your owner review ledger.")).toBeVisible();
});

test("Billing route exposes a safe HTTPS fallback when the checkout popup is blocked", async ({ page }) => {
  const state = await installOwnerProductMocks(page);
  await page.addInitScript(() => {
    window.open = () => null;
  });
  let popupCount = 0;
  page.on("popup", () => { popupCount += 1; });
  await page.goto("/billing", { waitUntil: "networkidle" });

  await expect(page).toHaveURL(/\/billing$/);
  const root = adjunctRoot(page);
  await expect(root.locator("h1")).toHaveText("Billing without hidden authority.");
  requestFor(state, "GET", "/api/v1/billing/plans");
  requestFor(state, "GET", "/api/v1/billing/subscription");
  await expect(root.getByText("Orbit Plus · $14.99")).toBeVisible();

  const writePromise = page.waitForRequest(request => (
    request.method() === "POST" && apiPath(request) === "/api/v1/billing/checkout"
  ));
  await root.locator('[data-adjunct-action="billing-checkout-orbit_plus"]').click();
  const write = recordedRequest(await writePromise);

  expectOwnerWrite(write);
  expect(write.headers["idempotency-key"]).toMatch(/^v197-billing-checkout:/);
  expect(write.body).toEqual({ plan_code: "orbit_plus" });
  await expect.poll(() => popupCount).toBe(0);
  await expect(page).toHaveURL(/\/billing$/);
  await expect(root).toContainText(/pop-?up.*blocked|browser.*blocked/i);
  const fallback = root.locator(`a[href="${CHECKOUT_URL}"]`);
  await expect(fallback).toBeVisible();
  await expect(fallback).toHaveAttribute("target", "_blank");
  await expect(fallback).toHaveAttribute("rel", /noopener/);
});

test("Capsules route creates from the active Orbit, grants separately, then revokes in owner controls", async ({ page }) => {
  const state = await installOwnerProductMocks(page);
  await page.goto("/capsules", { waitUntil: "networkidle" });

  await expect(page).toHaveURL(/\/capsules$/);
  let root = adjunctRoot(page);
  await expect(root.locator("h1")).toHaveText("Share a room, never your whole mind.");
  requestFor(state, "GET", `/api/v1/orbits/${mockOrbit.id}/sources`);
  requestFor(state, "GET", "/api/v1/capsules");
  await expect(root.getByText(/creating a capsule does not share it/i)).toBeVisible();

  const capsuleTitle = "Focused launch context";
  await root.locator('[data-adjunct-control="capsules-title"]').fill(capsuleTitle);
  await root.locator('[data-adjunct-control="capsules-purpose"]').fill("Let one reviewer inspect only the approved launch decision.");
  await root.locator('[data-adjunct-control="capsules-capability"]').selectOption("ASK_SCOPED_QUESTIONS");
  await root.locator(`[data-capsule-source-id="${CAPSULE_SOURCE_ID}"]`).check();
  const createPromise = page.waitForRequest(request => (
    request.method() === "POST" && apiPath(request) === `/api/v1/orbits/${mockOrbit.id}/capsules`
  ));
  await root.locator('[data-adjunct-action="capsules-create"]').click();
  const create = recordedRequest(await createPromise);

  expectOwnerWrite(create);
  expect(create.body).toMatchObject({
    title: capsuleTitle,
    purpose: "Let one reviewer inspect only the approved launch decision.",
    capability: "ASK_SCOPED_QUESTIONS",
    orbit_source_ids: [CAPSULE_SOURCE_ID],
    representations: {},
  });
  expect(create.path).not.toContain(mockUser.orbit.id);
  await expect(root.getByText(capsuleTitle)).toBeVisible();
  await expect(root.getByText(/No recipient has access yet/i)).toBeVisible();

  const recipientEmail = "recipient@nur.app";
  await root.locator(`[data-adjunct-control="capsules-grant-email-${CAPSULE_ID}"]`).fill(recipientEmail);
  const grantPromise = page.waitForRequest(request => (
    request.method() === "POST" && apiPath(request) === `/api/v1/capsules/${CAPSULE_ID}/grants`
  ));
  await root.locator(`[data-adjunct-action="capsules-grant-${CAPSULE_ID}"]`).click();
  const grant = recordedRequest(await grantPromise);

  expectOwnerWrite(grant);
  expect(grant.body).toEqual({
    recipient_email: recipientEmail,
    capability: "ASK_SCOPED_QUESTIONS",
    expires_at: null,
  });
  await expect(root.getByText("Recipient grant persisted. Delivery and opening remain unclaimed.")).toBeVisible();

  await root.locator(`[data-adjunct-action="capsules-open-${CAPSULE_ID}"]`).click();
  await expect(page).toHaveURL(new RegExp(`/capsule/${CAPSULE_ID}$`));
  root = adjunctRoot(page);
  await expect(root.locator("h1")).toHaveText("A bounded room you control.");
  const revokePromise = page.waitForRequest(request => (
    request.method() === "POST" && apiPath(request) === `/api/v1/capsules/${CAPSULE_ID}/revoke`
  ));
  await root.locator('[data-adjunct-action="capsule-revoke"]').click();
  const revoke = recordedRequest(await revokePromise);

  expectOwnerWrite(revoke);
  expect(revoke.body).toEqual({});
  await expect(root.getByText("Revoked. Recipient reads and asks are blocked immediately.")).toBeVisible();
});
