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
      .toBe("d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6");
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

  it("stops the reduced brain after one frame and invalidates stage visibility", () => {
    const runtime = read("apps/web/src/bridge/v43StarBrainRuntime.js");
    expect(runtime).toContain("stageVisAt=0;");
    expect(runtime).toContain("if(!REDUCED) rafHandle=requestAnimationFrame(frame);");
    expect(runtime).toContain("if(REDUCED) staticFramePainted=true;");
    expect(runtime).toContain("if(REDUCED&&staticFramePainted) return;");
    expect(runtime).toContain("getDiagnostics");
  });
});
