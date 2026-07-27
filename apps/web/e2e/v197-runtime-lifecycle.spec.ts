import { expect, test } from "@playwright/test";

import { installNurMocks } from "./helpers/nurMocks";

test("V43 brain owns one extended runtime with circular dispersal", async ({ page }, testInfo) => {
  await installNurMocks(page);
  await page.context().addCookies([
    { name: "nur_session", value: "runtime-lifecycle-session", url: "http://localhost:4173", httpOnly: true, sameSite: "Lax" },
    { name: "nur_csrf", value: "runtime-lifecycle-csrf", url: "http://localhost:4173", httpOnly: false, sameSite: "Lax" },
  ]);
  await page.goto("/systems", { waitUntil: "load" });

  const universe = page.frameLocator("#nur-universe-stage");
  await expect(universe.locator("#page-systems")).toBeVisible({ timeout: 15_000 });
  const host = universe.locator("#front-nur-star");
  const canvas = host.locator("#nur-brain-canvas");
  await expect(canvas).toHaveCount(1);
  await expect(host).toHaveAttribute("data-nur-model", "v43-v7-spark-stem");
  await expect(host).toHaveAttribute("data-nur-variant", "galaxy-rig-brainstem-v2");
  await expect(host).toHaveAttribute("data-nur-dispersal", "radial-circle");
  await expect(host).toHaveAttribute(
    "data-nur-point-count",
    testInfo.project.name.includes("mobile") ? "1355" : "2086",
  );
  await expect(host).toHaveAttribute(
    "data-nur-stem-point-count",
    testInfo.project.name.includes("mobile") ? "97" : "147",
  );
  await expect(host).toHaveAttribute("data-nur-sparkle-profile", "exact-galaxy-rig-star");
  await expect(host).toHaveAttribute("data-nur-galaxy-paint", "v197-simple-galaxy-particle-v1");
  await expect(universe.locator("#nur-v43-exact-star-brain-runtime"))
    .toHaveAttribute("data-nur-runtime-hash", "8e249a704734e0d60bedff389883e90460338d14ac806c00ca6e5019b5834192");
  await expect(universe.locator("#v197-sparkfield")).toHaveCount(0);

  const v43Contract = await canvas.evaluate(element => {
    const ordinary = new WheelEvent("wheel", { bubbles: true, cancelable: true, deltaY: 80 });
    const intentional = new WheelEvent("wheel", {
      bubbles: true,
      cancelable: true,
      ctrlKey: true,
      deltaY: -80,
    });
    element.dispatchEvent(ordinary);
    element.dispatchEvent(intentional);
    const host = element.closest<HTMLElement>("#front-nur-star");
    const style = host ? getComputedStyle(host) : null;
    return {
      ordinaryPrevented: ordinary.defaultPrevented,
      intentionalPrevented: intentional.defaultPrevented,
      rawController: typeof (window as unknown as { nurStarBrain?: { shatter?: unknown } }).nurStarBrain?.shatter,
      maskImage: style?.maskImage || style?.webkitMaskImage,
    };
  });
  expect(v43Contract.ordinaryPrevented).toBe(true);
  expect(v43Contract.intentionalPrevented).toBe(true);
  expect(v43Contract.rawController).toBe("function");
  expect(v43Contract.maskImage).toContain("radial-gradient");
});
