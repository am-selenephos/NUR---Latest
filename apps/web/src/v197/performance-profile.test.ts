import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

import {
  V197_GALAXY_STAR_PAINT,
  applyV197PerformanceProfile,
  buildV197PerformanceBootstrap,
} from "../bridge/v197PerformanceProfile";

const repositoryRoot = resolve(process.cwd(), "../..");
const source = (path: string) => readFileSync(resolve(repositoryRoot, path), "utf8");

describe("V197 deterministic runtime performance profile", () => {
  /*
   * These assertions used to require the degradations: `PARTICLE_CAP=1200`,
   * `DPR=…,1`, `if(false)drawNebula(t)` and a 42ms frame gap were all asserted
   * as *requirements*, so the suite went green precisely when the galaxy was
   * flattened and the frame rate was capped at 24 FPS. The founder's rejection
   * of the running interface is the counterexample.
   *
   * Each check below now names the visible property it protects, and the
   * degradation it must never reintroduce.
   */
  it("keeps Entry's galaxy at canonical depth and never caps its frame rate", () => {
    const canonical = source("docs/reference/entry_decoded_v197.html");
    const result = applyV197PerformanceProfile(canonical, "entry");

    expect(result.applied).toBe(true);
    expect(result.replacementCount).toBe(17);

    // Optimisations that cost nothing visible are kept.
    expect(result.source).toContain("const mobile=Math.max(innerWidth,parent.innerWidth||0)<700");
    expect(result.source).toContain("const nodes=nodeCache");
    expect(result.source).not.toContain('proj.filter(v=>v.p.kind==="galaxy"');
    expect(result.source).toContain("projectionCache=[]");
    expect(result.source).toContain("project(cached.p,yaw,pitch,roll,t,cached.q)");
    expect(result.source).toContain("let aliveCount=0");
    expect(result.source).not.toContain("particles=particles.filter");
    expect(result.source).toContain("getTransientParticleCount");

    // Four-point stars are the visual target, not an optimisation.
    expect(result.source).toContain('if(!isS&&p.kind==="galaxy")');
    expect(result.source).toContain("stellarPath(q.x,q.y,starR");

    // Resolution must stay canonical: the 1.15 cap visibly flattened HiDPI.
    // Bounded by a pixel budget, not a flat ratio: full resolution on ordinary
    // windows, and only as much reduction as a very large window demands.
    expect(result.source).toContain("Math.sqrt(3400000/Math.max(1,innerWidth*innerHeight))");
    expect(result.source).toContain("Math.max(1,Math.min(devicePixelRatio||1,1.5");
    expect(result.source).not.toContain("devicePixelRatio||1,1.15");
    // Entry paints with the *same* star code as the Universe rig — the founder
    // asked for an exact match, not a tuned variant. If these ever diverge the
    // two skies stop looking like one product.
    expect(result.source).toContain("Math.max(.86,rad*1.34)");
    expect(result.source).toContain("Math.min(1,alpha*4.2)");
    expect(result.source).not.toContain("alpha*3.55");
    // Same star counts as the Universe rig: galaxy 900, far 585, dust 165, super 48.
    expect(result.source).toContain("(mobile?520:900)");
    expect(result.source).toContain("(mobile?340:585)");
    expect(result.source).toContain("(mobile?96:165)");
    expect(result.source).toContain("(mobile?26:48)");

    // Desktop density stays canonical; only phones are thinned.
    expect(result.source).not.toContain("(mobile?500:860)");

    // No hand-rolled frame cap: 34ms held Entry at 29 FPS.
    expect(result.source).not.toContain("minFrameGap");

    // Visibility is decided by observable display state, not a class name.
    expect(result.source).toContain("__nurStageVisible");
    expect(result.source).toContain("now-__nurStageVisAt<250");
    expect(result.source).not.toContain('stage.id==="nur-entry-stage"');
    expect(result.source).toContain("const galaxyStage=frameElement");
  });

  it("keeps the Universe nebula, far stellar plane and frame rate intact", () => {
    const canonical = source("docs/reference/universe_decoded_v197.html");
    const result = applyV197PerformanceProfile(canonical, "universe");

    expect(result.applied).toBe(true);
    expect(result.replacementCount).toBe(15);

    // The three deletions that removed depth outright.
    expect(result.source).toContain("if(profile.nebula>.48)drawNebula(t);");
    expect(result.source).not.toContain("if(false)drawNebula(t);");
    expect(result.source).toContain("if(farAlpha>.095&&farR>.7)spike(");
    expect(result.source).toContain("Math.max(1,Math.min(devicePixelRatio||1,1.5");
    expect(result.source).not.toContain("DPR=Math.min(devicePixelRatio||1,1)");

    // Particle budget and desktop density stay canonical.
    expect(result.source).toContain("const PARTICLE_CAP=1880");
    expect(result.source).toContain("galaxy:900,far:585,dust:165,super:48");
    expect(result.source).not.toContain("galaxy:660,far:370,dust:100,super:30");

    // Desktop renders every frame; only phone widths are bounded, at 30 FPS.
    expect(result.source).not.toContain("minFrameGap");
    expect(result.source).toContain("innerWidth<700&&now-last<33");
    expect(result.source).toContain(
      "function scheduleFrame(){if(reduced||frameRAF)return;frameRAF=requestAnimationFrame(frame)}",
    );

    // Kept optimisations.
    expect(result.source).toContain("const nodeBudget=innerWidth<700?28:64");
    expect(result.source).toContain("nodes=nodeCache");
    expect(result.source).toContain("projectionCache=[]");
    expect(result.source).toContain("let aliveCount=0");
    expect(result.source).toContain("getTransientParticleCount");
    expect(result.source).toContain('if(!isS&&p.kind==="galaxy")');

    expect(result.source).toContain("__nurStageVisible");
    expect(result.source).toContain("now-__nurStageVisAt<250");
    expect(result.source).not.toContain('stage.id==="nur-universe-stage"');
  });

  it("publishes the exact lightweight four-point paint used by the true 3D sky", () => {
    expect(V197_GALAXY_STAR_PAINT).toEqual({
      points: 4,
      minimumRadius: .58,
      radiusScale: .94,
      innerRadiusScale: .16,
      maximumBodyAlpha: .96,
      bodyAlphaScale: 2.65,
      flareAlphaThreshold: .2,
      flareRadiusThreshold: .76,
      maximumFlareAlpha: .22,
      flareAlphaScale: .46,
      horizontalFlareScale: 2.35,
      verticalFlareScale: 1.7,
      flareThickness: .36,
    });
  });

  it("fails closed on signature drift and keeps an explicit canonical rollback", () => {
    const drifted = applyV197PerformanceProfile("<html>unknown</html>", "entry");
    const bootstrap = buildV197PerformanceBootstrap();

    expect(drifted.applied).toBe(false);
    expect(drifted.source).toBe("<html>unknown</html>");
    expect(bootstrap).toContain('requested === "canonical"');
    expect(bootstrap).toContain('nurRuntimeProfile = "canonical-fallback"');
  });
});
