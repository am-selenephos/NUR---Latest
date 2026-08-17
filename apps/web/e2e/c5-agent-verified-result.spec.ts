import { expect, test, type FrameLocator, type Page } from "@playwright/test";

async function revealEntry(page: Page): Promise<FrameLocator> {
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await expect.poll(() => entry.locator("body").evaluate(() => (
    typeof (window as unknown as { nurShowFront?: unknown }).nurShowFront
  ))).toBe("function");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront: () => void }).nurShowFront();
  });
  return entry;
}

test("C5 observes a worker-verified Agent result and rehydrates the owner ledger", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The real Agent worker loop runs once on desktop.");
  test.setTimeout(150_000);

  const email = `c5-${Date.now()}-${Math.floor(Math.random() * 1e6)}@nurapp.dev`;
  const entry = await revealEntry(page);
  await entry.locator("#f4-begin").click();
  await entry.locator("#f4-name").fill("C5 Owner");
  await entry.locator("#f4-email").fill(email);
  await entry.locator("#f4-password").fill("orbit-pass-2026");
  await entry.locator("#f4-consent-check").check();
  const registered = page.waitForResponse(response => (
    response.url().includes("/api/v1/auth/register") && response.request().method() === "POST"
  ));
  await entry.locator("#f4-signup-form button[type='submit']").click();
  expect((await registered).status()).toBe(201);

  const workflow = await page.evaluate(async () => {
    const headers = {
      accept: "application/json",
      "content-type": "application/json",
      ...(document.cookie.split("; ").find(row => row.startsWith("nur_csrf="))
        ? { "X-CSRF-Token": decodeURIComponent(document.cookie.split("; ").find(row => row.startsWith("nur_csrf="))!.split("=").slice(1).join("=")) }
        : {}),
    };
    const policyResponse = await fetch("/api/v1/agentic/policy", { credentials: "include" });
    if (!policyResponse.ok) throw new Error(`policy GET failed: ${policyResponse.status}`);
    const policy = await policyResponse.json() as { version?: number };
    const policyPut = await fetch("/api/v1/agentic/policy", {
      method: "PUT",
      credentials: "include",
      headers,
      body: JSON.stringify({
        seen_version: policy.version ?? 0,
        initiative_level: "INTERNAL",
        max_risk_class: "R2_DURABLE_PRIVATE",
        permitted_tools: ["get_timeline"],
        auto_run_tools: ["get_timeline"],
        denied_tools: [],
        daily_budget_cents: 0,
        max_proposals_per_day: 3,
        cooldown_minutes: 0,
        quiet_hours: null,
      }),
    });
    if (!policyPut.ok) throw new Error(`policy PUT failed: ${policyPut.status} ${await policyPut.text()}`);

    const createResponse = await fetch("/api/v1/agentic/workflows", {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({
        request_id: crypto.randomUUID(),
        title: "C5 verified timeline read",
        objective: "Read the owner timeline and record a verified outcome.",
        context_manifest: { source: "C5 browser proof" },
        success_criteria: ["Timeline read is verified"],
        proposed_steps: [{
          key: "read_timeline",
          role: "operator",
          tool_key: "get_timeline",
          depends_on: [],
          input_refs: { limit: 3 },
          rationale: "Read the owner timeline through the approved first-party capability.",
        }],
      }),
    });
    if (!createResponse.ok) throw new Error(`workflow POST failed: ${createResponse.status} ${await createResponse.text()}`);
    const created = await createResponse.json() as { id: string; plan_version: number };
    const startResponse = await fetch(`/api/v1/agentic/workflows/${created.id}/start`, {
      method: "POST",
      credentials: "include",
      headers,
      body: JSON.stringify({ seen_plan_version: created.plan_version }),
    });
    if (!startResponse.ok) throw new Error(`workflow start failed: ${startResponse.status} ${await startResponse.text()}`);
    return created;
  });

  await expect.poll(async () => page.evaluate(async (workflowId) => {
    const response = await fetch(`/api/v1/agentic/workflows/${workflowId}`, { credentials: "include" });
    if (!response.ok) return "HTTP_ERROR";
    const body = await response.json() as { state: string };
    return body.state;
  }, workflow.id), { timeout: 90_000, intervals: [500, 1000, 2000] }).toBe("SUCCEEDED");

  await page.goto(`/agents/${workflow.id}`, { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator(".nur-adjunct-panel").first()).toBeVisible({ timeout: 30_000 });
  await expect(universe.getByRole("heading", { name: "SUCCEEDED", exact: true })).toBeVisible();
  await expect(universe.getByText("STEP_EXECUTED", { exact: true })).toBeVisible();
  await expect(universe.getByText("STEP_VERIFIED", { exact: true })).toBeVisible();
  await expect(universe.getByText("Timeline read is verified", { exact: true })).toBeVisible();
});
