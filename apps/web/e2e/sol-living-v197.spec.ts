import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type Page } from "@playwright/test";

const proofRoot = process.env.NUR_SOL_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/sol-living-v197" : "proof/sol-living-v197");

async function shot(page: Page, name: string): Promise<void> {
  const toast = page.frameLocator("#nur-universe-stage").locator("#toast");
  if (await toast.count()) {
    await expect(toast).not.toHaveClass(/show/, { timeout: 7_000 });
  }
  await mkdir(proofRoot, { recursive: true });
  await page.screenshot({
    path: join(proofRoot, `${name}.png`),
    fullPage: false,
    animations: "disabled",
  });
}

async function expectSystemsInsideMap(page: Page): Promise<void> {
  const geometry = await page.frameLocator("#nur-universe-stage").locator(".universe-map-panel").evaluate(panel => {
    const map = panel.getBoundingClientRect();
    return [...panel.querySelectorAll<HTMLElement>(".universe-system-node")]
      .filter(node => {
        const style = getComputedStyle(node);
        const rect = node.getBoundingClientRect();
        return style.display !== "none"
          && style.visibility !== "hidden"
          && Number(style.opacity) > 0
          && rect.width > 0
          && rect.height > 0;
      })
      .map(node => {
        const rect = node.getBoundingClientRect();
        return {
          name: node.dataset.system ?? node.textContent?.trim() ?? "unknown",
          inside: rect.left >= map.left - 1
            && rect.right <= map.right + 1
            && rect.top >= map.top - 1
            && rect.bottom <= map.bottom + 1,
        };
      });
  });
  expect(geometry).toHaveLength(6);
  expect(geometry.filter(node => !node.inside), JSON.stringify(geometry, null, 2)).toEqual([]);
}

async function signInDemo(page: Page): Promise<void> {
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
}

test("SOL living backend hydrates and moves the exact V197 presentation", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "The full living mutation proof runs once on desktop.");
  test.setTimeout(90_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await signInDemo(page);

  let today = await page.evaluate(async () => {
    const response = await fetch("/api/v1/today");
    return response.json() as Promise<{ next_move: { title: string } | null; completed_today: unknown[] }>;
  });
  if (!today.next_move) {
    await page.evaluate(async () => {
      const csrf = document.cookie.split("; ").find(row => row.startsWith("nur_csrf="))?.split("=")[1];
      const response = await fetch("/api/v1/systems/ambition/actions", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRF-Token": decodeURIComponent(csrf ?? "") },
        body: JSON.stringify({
          title: "Review the exact V197 owner ledger",
          description: "Browser-isolated proof action.",
          effort_minutes: 10,
        }),
      });
      if (!response.ok) throw new Error(`Could not create SOL proof action: ${response.status}`);
    });
    await page.reload({ waitUntil: "load" });
    await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 20_000 });
    today = await page.evaluate(async () => {
      const response = await fetch("/api/v1/today");
      return response.json() as Promise<{ next_move: { title: string } | null; completed_today: unknown[] }>;
    });
  }
  expect(today.next_move).not.toBeNull();
  const expectedMove = today.next_move?.title ?? "";
  const completedBefore = today.completed_today.length;

  await expect(page.locator("#root")).toHaveCount(0);
  const universe = page.frameLocator("#nur-universe-stage");
  // The authenticated universe lands on Today; open Systems deliberately.
  await expect(universe.locator("#page-today")).toBeVisible({ timeout: 20_000 });
  await universe.locator('[data-page="systems"]:visible').first().click();
  await expect(universe.locator("#page-systems")).toBeVisible();
  await expect(universe.locator(".universe-system-node:visible")).toHaveCount(6);
  await expect(universe.locator(".universe-system-node:visible b")).toHaveText([
    "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection",
  ]);
  await universe.locator('.universe-system-node[data-system="Ambition"]').click();
  await expect(universe.locator(".universe-system-node").first().locator("small")).toContainText(/% · \d+ Glow/);
  await expect(universe.locator(".universe-insight-title h2")).toHaveText("Ambition");
  await expect(universe.locator(".universe-insight-copy")).toContainText("Private hunger");
  await expect(universe.locator(".universe-state-strip")).toContainText("calculated from owner evidence");
  await expect(universe.locator(".universe-system-lane")).toContainText("persisted Glow");
  await expect(universe.locator("#nur-v197-language-open")).toHaveText("English");
  await expect(universe.locator("#nur-v197-locale option")).toHaveCount(35);
  await expectSystemsInsideMap(page);
  await shot(page, "01-systems-real-owner-ledger");

  await universe.locator('.universe-system-node[data-system="Rebuild"]').click();
  await expect(universe.locator(".universe-insight-title h2")).toHaveText("Rebuild");
  await expect(universe.locator(".universe-insight-copy")).toContainText("damaged");
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/profile/preferences");
    return (await response.json()).active_orbit_id as string | null;
  })).toBe(await universe.locator('.universe-system-node[data-system="Rebuild"]').getAttribute("data-orbit-id"));

  await universe.locator('[data-page="today"]:visible').first().click();
  await expect(universe.locator("#page-today")).toHaveClass(/active/);
  await expect(universe.locator("#page-today .page-kicker")).toContainText("Today in NUR");
  await expect(universe.locator("#page-today .page-kicker")).toContainText(new Date().getFullYear().toString());
  await expect(universe.locator("#page-today .reading-line strong")).toHaveText([
    /% · persisted evidence/,
    /% · persisted evidence/,
    /% · persisted evidence/,
  ]);
  await expect(universe.locator("#page-today .next-move h3")).toHaveText(expectedMove);
  await expect(universe.locator('[data-action="today-did-it"]')).toBeEnabled();
  await expect(universe.locator("#page-today .panel-title").nth(1)).toContainText(/Glow Points · Level/);
  await shot(page, "02-today-calculated-body-mind-life");

  await universe.locator('[data-action="checkin"]').click();
  await expect(universe.locator("#nur-v197-today-checkin")).toBeVisible();
  await universe.locator("#nur-checkin-energy").fill("8");
  await universe.locator("#nur-checkin-pain").fill("2");
  await universe.locator("#nur-checkin-clarity").fill("9");
  await universe.locator("#nur-checkin-note").fill("Browser-proven capacity reading.");
  const checkInResponse = page.waitForResponse(response => response.url().includes("/api/v1/today/check-in") && response.status() === 200);
  await universe.locator('[data-action="save-today-checkin"]').click();
  await checkInResponse;
  await expect(universe.locator("#nur-v197-today-checkin")).toBeHidden();

  const before = await page.evaluate(async () => {
    const response = await fetch("/api/v1/glow/summary");
    return (await response.json()).lifetime_points as number;
  });
  // Miss open actions until the return path surfaces. The owner ledger may
  // legitimately hold several open actions from earlier sessions; the proof
  // is that every miss persists AND the "Return to:" state appears once no
  // open action remains — not that exactly one action existed beforehand.
  for (let round = 0; round < 12; round += 1) {
    const move = await page.evaluate(async () => {
      const response = await fetch("/api/v1/today");
      const body = await response.json() as { next_move: { id: string; title: string } | null };
      return body.next_move;
    });
    if (!move || move.title.startsWith("Return to:")) break;
    const control = universe.locator('[data-action="today-missed-it"]');
    await control.click();
    // Duplicate titles cannot signal progress; wait until the persisted next
    // move changes — or the SAME action legitimately returns as the
    // "Return to:" target (missing the final open action re-surfaces it).
    await expect.poll(async () => page.evaluate(async () => {
      const response = await fetch("/api/v1/today");
      const body = await response.json() as { next_move: { id: string; title: string } | null };
      const returned = body.next_move?.title.startsWith("Return to:") ?? false;
      return returned ? "returned" : body.next_move?.id ?? "none";
    })).not.toBe(move.id);
    await expect(control).not.toHaveAttribute("aria-busy", "true");
  }
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/today");
    return (await response.json()).missed_today.length as number;
  })).toBeGreaterThan(0);
  await expect(universe.locator("#page-today .next-move h3")).toContainText("Return to:");
  const completion = page.waitForResponse(response =>
    response.url().includes("/api/v1/today/complete-action") && response.status() === 200);
  await universe.locator('[data-action="today-did-it"]').click();
  // §17 law: the action always persists; the reward is server-verified when
  // granted and honestly gated when a daily cap/anti-spam window is reached.
  const completionGlow = (await (await completion).json() as { glow: { status: string } }).glow;
  if (completionGlow.status === "AWARDED") {
    await expect.poll(async () => page.evaluate(async () => {
      const response = await fetch("/api/v1/glow/summary");
      return (await response.json()).lifetime_points as number;
    })).toBeGreaterThan(before);
  } else {
    expect(completionGlow.status).toBe("CAP_OR_SPAM_GATED");
    expect(await page.evaluate(async () => {
      const response = await fetch("/api/v1/glow/summary");
      return (await response.json()).lifetime_points as number;
    })).toBe(before);
  }
  await expect.poll(async () => page.evaluate(async () => {
    const response = await fetch("/api/v1/today");
    return ((await response.json()).completed_today as unknown[]).length;
  })).toBe(completedBefore + 1);
  await expect(universe.locator("#page-today .page-sub")).toContainText(`${completedBefore + 1} completed`);
  await shot(page, "03-today-returned-action-glow");

  await universe.locator('[data-page="systems"]:visible').first().click();
  await universe.locator('[data-world-tab="map"]').click();
  await expect(page).toHaveURL(/\/universe\/map$/);
  await expect(universe.locator(".universe-insight-panel")).toContainText("persisted Map nodes");
  const graph = await page.evaluate(async () => {
    const response = await fetch("/api/v1/map");
    return response.json() as Promise<{ counts: { systems: number; goals: number; open_predictions: number }; nodes: Array<{ kind: string }> }>;
  });
  expect(graph.counts.systems).toBe(6);
  expect(graph.counts.goals).toBeGreaterThan(0);
  expect(graph.counts.open_predictions).toBeGreaterThan(0);
  expect(graph.nodes.some(node => node.kind === "GLOW_MILESTONE")).toBe(true);
  await shot(page, "04-map-derived-graph-and-paths");

  await universe.locator('[data-world-tab="timeline"]').click();
  await expect(page).toHaveURL(/\/universe\/timeline$/);
  await expect(universe.locator(".universe-insight-panel")).toContainText(/completed|checkin|diagnostic/i);
  // The demo owner's ledger legitimately accumulates across runs; the law is
  // that the composed timeline SURFACES these kinds, so it is asserted over
  // the endpoint's full documented window (limit caps at 200), not the
  // default newest-80 slice that fresh recent events crowd out.
  const timelineKinds = await page.evaluate(async () => {
    const response = await fetch("/api/v1/universe/timeline?limit=200");
    const body = await response.json() as { items: Array<{ kind: string }> };
    return body.items.map(row => row.kind);
  });
  expect(timelineKinds).toContain("SYSTEM_ACTION_MISSED");
  expect(timelineKinds).toContain("SYSTEM_ACTION_COMPLETED");
  expect(timelineKinds).toContain("FEASIBILITY_CREATED");
  expect(timelineKinds).toContain("PREDICTION_MADE");
});
