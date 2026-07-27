import { mkdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { expect, test, type FrameLocator, type Locator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const proofDir = process.env.NUR_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/screenshots" : "proof/screenshots");

test.use({ serviceWorkers: "block" });

function proofPath(name: string) {
  const path = join(proofDir, name);
  mkdirSync(dirname(path), { recursive: true });
  return path;
}

async function authenticate(page: Page): Promise<FrameLocator> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "lens-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "lens-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  return page.frameLocator("#nur-universe-stage");
}

async function visibleBox(label: string, locator: Locator) {
  await expect(locator, label).toBeVisible();
  const box = await locator.boundingBox();
  expect(box, `${label} has a DOM box`).not.toBeNull();
  return box!;
}

function overlaps(
  a: { x: number; y: number; width: number; height: number },
  b: { x: number; y: number; width: number; height: number },
  pad = 0,
) {
  return !(
    a.x + a.width + pad <= b.x
    || b.x + b.width + pad <= a.x
    || a.y + a.height + pad <= b.y
    || b.y + b.height + pad <= a.y
  );
}

async function assertNoHorizontalOverflow(frame: FrameLocator) {
  const widths = await frame.locator("html").evaluate(element => ({
    scroll: element.scrollWidth,
    client: element.clientWidth,
  }));
  expect(widths.scroll).toBeLessThanOrEqual(widths.client + 2);
}

test("Universe topbar routes to distinct canonical lenses and searches the owner ledger", async ({ page }) => {
  const frame = await authenticate(page);
  await page.goto("/universe");
  await expect(frame.locator("#page-systems")).toBeVisible();

  for (const lens of [
    { label: "Map", route: "/universe/map", focus: "map" },
    { label: "Orbits", route: "/universe/orbits", focus: "orbits" },
    { label: "Timeline", route: "/universe/timeline", focus: "timeline" },
    { label: "Insights", route: "/universe/insights", focus: "insights" },
  ] as const) {
    await frame.getByRole("tab", { name: lens.label, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${lens.route}$`));
    await expect(frame.locator("body")).toHaveAttribute("data-nur-world-focus", lens.focus);
    await expect(frame.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", lens.focus);
  }

  await frame.locator("#universe-search").fill("Postgres");
  await frame.locator("#universe-search").press("Enter");
  await expect(frame.locator("#universe-research .research-results"))
    .toContainText("Postgres RLS is the trust boundary.");
});

test("Systems map labels breathe at 1280 and Add System does not cover labels", async ({ page }) => {
  const frame = await authenticate(page);
  await page.setViewportSize({ width: 1280, height: 720 });
  await page.goto("/universe/map");

  const panel = frame.locator("#page-systems .universe-map-panel");
  await expect(panel).toBeVisible();
  const ambition = await visibleBox("Ambition label", panel.locator('.universe-system-node[data-system="Ambition"]'));
  const growth = await visibleBox("Growth label", panel.locator('.universe-system-node[data-system="Growth"]'));
  const connection = await visibleBox("Connection label", panel.locator('.universe-system-node[data-system="Connection"]'));
  const add = await visibleBox("Add System control", panel.locator(".universe-add-system"));
  const title = await visibleBox("map title", panel.locator(".universe-map-title"));
  await visibleBox("star brain", panel.locator(".universe-master-star"));

  expect(overlaps(ambition, growth, 10), "Ambition and Growth breathe").toBe(false);
  expect(overlaps(growth, connection, 10), "Growth and Connection breathe").toBe(false);
  expect(overlaps(add, ambition, 10), "Add System does not cover Ambition").toBe(false);
  expect(overlaps(add, connection, 10), "Add System does not cover Connection").toBe(false);
  expect(overlaps(title, ambition, 6), "NUR title and Ambition do not collide").toBe(false);
  expect(overlaps(title, growth, 6), "NUR title and Growth do not collide").toBe(false);
  await assertNoHorizontalOverflow(frame);

  await page.screenshot({ path: proofPath("systems-map-1280-label-breathing.png"), fullPage: false });
  await panel.locator('.universe-system-node[data-system="Growth"]').click();
  await expect(frame.locator(".universe-insight-title h2")).toHaveText("Growth");
  await panel.locator(".universe-add-system").click();
  await expect(frame.locator("#universe-composer-input")).toBeFocused();
});

test("timeline, research, web signals, and insights expose distinct persisted truth", async ({ page }) => {
  const frame = await authenticate(page);

  await page.goto("/universe/timeline");
  await expect(frame.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", "timeline");
  await expect(frame.locator(".universe-system-lane")).toHaveAttribute("aria-label", "Owner timeline summary");
  await expect(frame.locator(".universe-insight-panel")).toContainText("The owner returned a visible outcome.");

  await page.goto("/universe/research");
  await expect(frame.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", "research");
  await expect(frame.locator(".universe-system-lane")).toHaveAttribute("aria-label", "Owner research summary");
  await expect(frame.locator(".universe-insight-panel")).toContainText("What source should verify this system?");

  await page.goto("/universe/web-signals");
  await expect(frame.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", "web");
  await expect(frame.locator(".universe-system-lane")).toHaveAttribute("aria-label", "Owner web-signal staging summary");
  await expect(frame.locator(".universe-insight-panel")).toContainText("No fetched web signal yet");

  await page.goto("/universe/insights");
  await expect(frame.locator(".universe-insight-panel")).toContainText(
    "Outcome evidence should strengthen planning patterns only after persisted results.",
  );
  await expect(frame.locator("#nur-v197-insight-controls")).toBeVisible();
});

test("mobile map first viewport is usable, not clipped", async ({ page }) => {
  const frame = await authenticate(page);
  await page.setViewportSize({ width: 393, height: 852 });
  await page.goto("/universe/map");

  const panel = frame.locator("#page-systems .universe-map-panel");
  await expect(panel).toBeVisible();
  const addSystem = panel.locator(".universe-add-system");
  const addState = await addSystem.evaluate(element => {
    const style = getComputedStyle(element);
    const rect = element.getBoundingClientRect();
    return {
      display: style.display,
      visibility: style.visibility,
      opacity: style.opacity,
      width: rect.width,
      height: rect.height,
    };
  });
  expect(addState.display, JSON.stringify(addState)).not.toBe("none");
  expect(addState.visibility, JSON.stringify(addState)).toBe("visible");
  expect(Number(addState.opacity), JSON.stringify(addState)).toBeGreaterThan(0);
  expect(addState.width, JSON.stringify(addState)).toBeGreaterThan(0);
  expect(addState.height, JSON.stringify(addState)).toBeGreaterThan(0);
  await expect(addSystem).toBeVisible();
  await expect(panel.locator('.universe-system-node[data-system="Ambition"]')).toBeVisible();
  await expect(panel.locator(".universe-system-node:not([hidden])")).toHaveCount(6);
  await assertNoHorizontalOverflow(frame);
  await page.screenshot({ path: proofPath("systems-map-mobile-393-clean.png"), fullPage: false });
});
