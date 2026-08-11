import { createHash } from "node:crypto";

import { expect, test } from "@playwright/test";

import { buildV197PerformanceBootstrap } from "../src/bridge/v197PerformanceProfile";
import { installNurMocks } from "./helpers/nurMocks";

const CANONICAL_SHA256 = "d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6";
const PWA_METADATA = '<link rel="manifest" href="/manifest.webmanifest"><meta name="theme-color" content="#000000">';
const BRIDGE_LOADER = '<script type="module" src="/assets/v197-bridge.js"></script>';

test("product routes compose the byte-locked V197 host with deterministic runtime appendages", async ({ page }) => {
  const canonicalResponse = await page.request.get("/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html");
  expect(canonicalResponse.status()).toBe(200);
  const canonical = await canonicalResponse.text();
  expect(createHash("sha256").update(canonical).digest("hex")).toBe(CANONICAL_SHA256);

  const productResponse = await page.request.get("/systems");
  expect(productResponse.status()).toBe(200);
  const productDocument = await productResponse.text();
  expect(productDocument).toBe(
    canonical
      .replace("</head>", `${PWA_METADATA}${buildV197PerformanceBootstrap()}</head>`)
      .replace("</body>", `${BRIDGE_LOADER}</body>`),
  );

  await page.goto("/systems", { waitUntil: "load" });
  await expect(page.locator("#root")).toHaveCount(0);
  await expect(page.locator("#nur-entry-stage")).toHaveCount(1);
  await expect(page.locator("#nur-universe-stage")).toHaveCount(1);
  await expect(page.locator("#nur-entry-stage")).toHaveAttribute("srcdoc", /.+/);
  expect(await page.locator("#nur-universe-stage").getAttribute("srcdoc")).toBeNull();
});

test("current bridge hydrates six founder Systems without replacing canonical V197 geometry", async ({ page }) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "host-parity-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "host-parity-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });

  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  await expect(universe.locator(".universe-system-node:visible")).toHaveCount(6);
  await expect(universe.locator(".universe-system-node:visible b")).toHaveText([
    "Ambition", "Rebuild", "Creation", "Growth", "Introspection", "Connection",
  ]);
  const systemLabels = await universe.locator(".universe-system-node:visible b").allTextContents();
  expect(systemLabels.join(" ")).not.toMatch(/Quiet Ambition|Study|Money|Body|Neural Upgrade/);
  await expect(universe.locator("#front-nur-star")).toHaveCount(1);
  await expect(universe.locator("#nur-brain-canvas")).toHaveCount(1);
  await expect(universe.locator("#root")).toHaveCount(0);
  await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);

  const contract = await universe.locator("body").evaluate(() => ({
    documentWidth: document.documentElement.scrollWidth,
    viewportWidth: document.documentElement.clientWidth,
    mapPanel: document.querySelectorAll(".universe-map-panel").length,
    insightPanel: document.querySelectorAll(".universe-insight-panel").length,
    bridgeStyles: document.querySelectorAll("#nur-v197-track-a-premium-polish").length,
  }));
  expect(contract.documentWidth).toBeLessThanOrEqual(contract.viewportWidth + 1);
  expect(contract.mapPanel).toBe(1);
  expect(contract.insightPanel).toBe(1);
  expect(contract.bridgeStyles).toBe(1);
});

test("native V197 navigation synchronizes URL and world lens without React routing", async ({ page }) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "host-route-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "host-route-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible();

  await universe.locator("[data-world-tab='map']").click();
  await expect(page).toHaveURL(/\/universe\/map$/);
  await expect(universe.locator("body")).toHaveAttribute("data-nur-world-focus", "map");
  await expect(universe.locator(".universe-insight-panel")).toHaveAttribute("data-nur-lens", "map");

  await universe.locator("button[data-page='today']:visible").first().click();
  await expect(page).toHaveURL(/\/today$/);
  await expect(universe.locator("#page-today")).toHaveClass(/active/);
});

test("adjunct routes stay inside the canonical frame and return to NUR", async ({ page }) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "host-adjunct-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "host-adjunct-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/settings", { waitUntil: "load" });
  const universe = page.frameLocator("#nur-universe-stage");
  const adjunct = universe.locator("#nur-v197-adjunct-root");
  await expect(adjunct).toBeVisible();
  await expect(adjunct).toHaveAttribute("data-v197-native-adjunct", "true");
  await expect(page.locator("#root")).toHaveCount(0);
  await adjunct.locator("[data-adjunct-route='/systems']").click();
  await expect(page).toHaveURL(/\/systems$/);
  await expect(universe.locator("#page-systems")).toBeVisible();
  await expect(universe.locator("#nur-v197-adjunct-root")).toHaveCount(0);
});
