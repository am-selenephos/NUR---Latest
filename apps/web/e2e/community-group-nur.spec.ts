import { expect, test, type FrameLocator, type Page } from "@playwright/test";

/** Community / Group NUR through the exact V197 surface: a bounded room is
 * created and a message persists with server-verified Glow — no fake people,
 * no invented feed, and the message is provable through the owner API. */

async function signIn(page: Page): Promise<FrameLocator> {
  await page.goto("/", { waitUntil: "load" });
  const entry = page.frameLocator("#nur-entry-stage");
  await entry.locator("body").evaluate(() => {
    (window as unknown as { nurShowFront?: () => void }).nurShowFront?.();
  });
  await entry.locator("#f4-signin").click();
  await entry.locator("#f4-signin-email").fill("owner@nur.app");
  await entry.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await entry.locator("#f4-signin-form button[type='submit']").click();
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 20_000 });
  const universe = page.frameLocator("#nur-universe-stage");
  // The authenticated universe lands on Today in the rebuilt shell.
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  return universe;
}

test("bounded Community room and message persist through exact V197 controls", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The community proof runs once on desktop.");
  test.setTimeout(90_000);
  const universe = await signIn(page);

  await universe.locator('nav [data-page="systems"]').first().click();
  await expect(page).toHaveURL(/\/systems$/);
  await expect(universe.locator("#page-systems")).toBeVisible();
  await universe.locator('[data-world-tab="community"], [data-world-focus="community"]').first().click();
  await expect(page).toHaveURL(/\/universe\/community$/);
  await expect(universe.locator("#nur-v197-community-controls")).toBeVisible();

  const roomTitle = `Recovery proof room ${Date.now()}`;
  await universe.locator("#nur-v197-room-title").fill(roomTitle);
  const createResponse = page.waitForResponse(response =>
    response.url().includes("/api/v1/community/rooms") && response.status() === 201);
  await universe.locator('[data-adjunct-action="community-room-create"]').click();
  await createResponse;
  await expect(page).toHaveURL(/\/universe\/community\/room\/[0-9a-f-]+$/);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText(roomTitle);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("OWNER · GROUP");

  const messageBody = `One honest recovery line ${Date.now()}`;
  await universe.locator("#nur-v197-room-message").fill(messageBody);
  const messageResponse = page.waitForResponse(response =>
    response.url().includes("/messages") && response.status() === 201);
  await universe.locator('[data-adjunct-action="community-message-send"]').click();
  await messageResponse;

  // The message and its server-side Glow must be provable, not decorative.
  const persisted = await page.evaluate(async (expected) => {
    const rooms = await (await fetch("/api/v1/community/rooms")).json() as Array<{ id: string; title: string }>;
    const room = rooms.find(row => row.title === expected.roomTitle);
    if (!room) return { found: false, glow: 0 };
    const messages = await (await fetch(`/api/v1/community/rooms/${room.id}/messages`)).json() as Array<{ body: string }>;
    const glow = await (await fetch("/api/v1/glow/summary")).json() as {
      recent_transactions: Array<{ event_type: string }>;
    };
    return {
      found: messages.some(row => row.body === expected.messageBody),
      glow: glow.recent_transactions.filter(row => row.event_type === "community.message_posted").length,
    };
  }, { roomTitle, messageBody });
  expect(persisted.found).toBe(true);
  expect(persisted.glow).toBeGreaterThan(0);

  // The privacy law stays visible: rooms never advertise fake people or feeds.
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("Private Talk, Journal, Timeline, and Omega stay unreachable");
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("not_connected");

  // Membership grant to the second seeded demo account — the room becomes
  // genuinely multi-user through the V197 surface.
  await universe.locator("#nur-v197-member-email").fill("recipient@nur.app");
  const memberResponse = page.waitForResponse(response => response.url().includes("/members"));
  await universe.locator('[data-adjunct-action="community-member-add"]').click();
  const memberResult = await memberResponse;
  expect(memberResult.status()).toBe(201);

  // Council flow: start a Council, persist a position, record the decision.
  const councilTitle = `Recovery council ${Date.now()}`;
  await page.goto("/universe/community", { waitUntil: "load" });
  await expect(universe.locator("#nur-v197-community-controls")).toBeVisible();
  await universe.locator("#nur-v197-room-title").fill(councilTitle);
  const councilResponse = page.waitForResponse(response =>
    response.url().includes("/api/v1/community/rooms") && response.status() === 201);
  await universe.locator('[data-adjunct-action="community-council-create"]').click();
  await councilResponse;
  await expect(page).toHaveURL(/\/universe\/community\/room\/[0-9a-f-]+$/);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText(councilTitle);
  await expect(universe.locator("#nur-v197-adjunct-root")).toContainText("OWNER · COUNCIL");

  await universe.locator("#nur-v197-council-position").fill("Repair before boundary.");
  const positionResponse = page.waitForResponse(response =>
    response.url().includes("/positions") && response.status() === 201);
  await universe.locator('[data-adjunct-action="council-position-add"]').click();
  await positionResponse;

  await universe.locator("#nur-v197-council-decision").fill("Attempt one bounded repair first.");
  const decisionResponse = page.waitForResponse(response =>
    response.url().includes("/decision") && response.status() === 201);
  await universe.locator('[data-adjunct-action="council-decision-record"]').click();
  await decisionResponse;

  const council = await page.evaluate(async (expected) => {
    const rooms = await (await fetch("/api/v1/community/rooms")).json() as Array<{ id: string; title: string; room_kind: string }>;
    const groupRoom = rooms.find(row => row.title === expected.roomTitle);
    const councilRoom = rooms.find(row => row.title === expected.councilTitle);
    if (!groupRoom || !councilRoom) return null;
    const members = await (await fetch(`/api/v1/community/rooms/${groupRoom.id}/members`)).json() as Array<{ role: string }>;
    const positions = await (await fetch(`/api/v1/community/rooms/${councilRoom.id}/positions`)).json() as Array<{ position: string }>;
    const summary = await (await fetch(`/api/v1/community/rooms/${councilRoom.id}/summary`)).json() as { counts: { decisions: number } };
    return {
      kind: councilRoom.room_kind,
      memberRoles: members.map(row => row.role).sort(),
      positions: positions.map(row => row.position),
      decisions: summary.counts.decisions,
    };
  }, { roomTitle, councilTitle });
  expect(council).not.toBeNull();
  expect(council?.kind).toBe("COUNCIL");
  expect(council?.memberRoles).toEqual(["MEMBER", "OWNER"]);
  expect(council?.positions).toContain("Repair before boundary.");
  expect(council?.decisions).toBeGreaterThan(0);
});
