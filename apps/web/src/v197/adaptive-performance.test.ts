import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const repositoryRoot = resolve(process.cwd(), "../..");
const read = (path: string) => readFileSync(resolve(repositoryRoot, path), "utf8");

describe("V197 adaptive rendering contract", () => {
  it("keeps the canonical source byte-identical", () => {
    const source = read("apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html");
    expect(createHash("sha256").update(source).digest("hex"))
      .toBe("c4699091db9f1ebc3a6e2076d483a3d41303d3e261ace0111c9411322f7ea3a5");
  });

  it("bounds repeated paint work without selecting rig or geometry owners", () => {
    const css = read("apps/web/src/styles/v197-adaptive-performance.css");
    expect(css).toContain(".nur-page:not(.active)");
    expect(css).toContain("html.nur-stage-inactive");
    expect(css).toContain(".nur-map-node.is-unresolved:not(.is-selected)");
    expect(css).toContain("backdrop-filter: none !important");
    expect(css).not.toMatch(/#space3d|#front-nur-star|#nur-brain-canvas|\.universe-master-star/);
    expect(css).not.toMatch(/--(?:galaxy|particle|node-x|node-y)|getParticleCount/);
  });

  it("covers all coarse-pointer actions and wins the final reduced-motion cascade", () => {
    const css = read("apps/web/src/styles/v197-adaptive-performance.css");
    expect(css).toContain("@media (max-width: 900px), (pointer: coarse)");
    expect(css).toContain("[tabindex]:not([tabindex=\"-1\"])");
    expect(css).toContain("min-width: 44px !important");
    expect(css).toContain("min-height: 44px !important");
    expect(css).toContain("scale: 1 1.158 !important");
    expect(css).toContain("#nur-front-v61#nur-front-v61#nur-front-v61");
    expect(css).toContain("@media (prefers-reduced-motion: reduce)");
    expect(css).toContain("animation: none !important");
  });

  it("stops the reduced celestial engine after one frame and invalidates it honestly", () => {
    const runtime = read("apps/web/src/bridge/v197CelestialRuntime.ts");
    expect(runtime).toContain("if (controller.reducedMotion && controller.staticFramePainted) return;");
    expect(runtime).toContain("controller.staticFramePainted = true;");
    expect(runtime).toContain("stageIsVisible(controller)");
    expect(runtime).toContain("controller.staticFramePainted = false;");
    expect(runtime).toContain("getDiagnostics");
    expect(runtime).toContain("getParticleDiagnostics");
  });
});
