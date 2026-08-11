import { mkdir } from "node:fs/promises";
import { join } from "node:path";

import { expect, test, type FrameLocator, type Page } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

const proofRoot = process.env.NUR_SOL_PROOF_DIR
  ?? (process.cwd().endsWith("/apps/web") ? "../../proof/sol-living-v197" : "proof/sol-living-v197");

async function openSystems(page: Page): Promise<FrameLocator> {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "language-wordmark-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "language-wordmark-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });
  await expect(page.locator("#nur-universe-stage")).toHaveClass(/is-visible/, { timeout: 20_000 });
  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 20_000 });
  return universe;
}

test("V197 keeps Bodoni holographic NUR motion and dark native language controls", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "chromium-desktop", "Desktop visual lock runs once.");
  test.setTimeout(60_000);
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.emulateMedia({ reducedMotion: "no-preference" });
  const universe = await openSystems(page);
  await expect(page.locator("#root")).toHaveCount(0);

  const wordmark = universe.locator(".nur-v197-stable-wordmark");
  await expect(wordmark).toBeVisible();
  await expect(wordmark).toHaveAttribute("aria-label", "NUR");
  const before = await wordmark.evaluate(node => {
    const style = getComputedStyle(node);
    return {
      fontFamily: style.fontFamily,
      backgroundImage: style.backgroundImage,
      backgroundPosition: style.backgroundPosition,
      animationName: style.animationName,
      textFill: style.getPropertyValue("-webkit-text-fill-color"),
      visualPosition: getComputedStyle(node, "::after").backgroundPosition,
      visualAnimation: getComputedStyle(node, "::after").animationName,
    };
  });
  expect(before.fontFamily).toContain("Bodoni Moda");
  expect(before.backgroundImage).toContain("linear-gradient");
  expect(before.backgroundImage).toContain("rgb(94, 223, 255)");
  expect(before.backgroundImage).toContain("rgb(221, 128, 255)");
  expect(before.animationName).toContain("univPrism");
  expect(before.visualAnimation).toContain("univPrism");
  expect(before.textFill).toMatch(/^(transparent|rgba\(0, 0, 0, 0\))$/);
  await expect.poll(
    () => wordmark.evaluate(node => getComputedStyle(node, "::after").backgroundPosition),
  ).not.toBe(before.visualPosition);

  await mkdir(proofRoot, { recursive: true });
  await page.screenshot({
    path: join(proofRoot, "00g-v197-bodoni-holographic-rainbow-wordmark.png"),
    fullPage: false,
  });

  await universe.locator("#nur-v197-language-open").click();
  await expect(universe.locator("#scope-modal")).toHaveClass(/open/);
  await expect(universe.locator("#nur-v197-locale option")).toHaveCount(35);
  const selectVisuals = await universe.locator("#nur-v197-locale").evaluate(node => {
    const selectStyle = getComputedStyle(node);
    const shellStyle = getComputedStyle(node.parentElement as HTMLElement);
    return {
      appearance: selectStyle.appearance,
      colorScheme: selectStyle.colorScheme,
      textColor: selectStyle.color,
      shellColor: shellStyle.backgroundColor,
      shellBorder: shellStyle.borderColor,
    };
  });
  expect(selectVisuals.appearance).toBe("none");
  expect(selectVisuals.colorScheme).toBe("dark");
  expect(selectVisuals.shellColor).not.toBe("rgb(255, 255, 255)");
  expect(selectVisuals.textColor).not.toBe("rgb(0, 0, 0)");
  expect(selectVisuals.shellBorder).not.toBe("rgb(255, 255, 255)");
  await page.screenshot({
    path: join(proofRoot, "00h-v197-dark-glass-language-dropdown.png"),
    fullPage: false,
    animations: "disabled",
  });
});
