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
  it("profiles the exact decoded Entry signatures without touching its source file", () => {
    const canonical = source("docs/reference/entry_decoded_v197.html");
    const result = applyV197PerformanceProfile(canonical, "entry");

    expect(result.applied).toBe(true);
    expect(result.replacementCount).toBe(18);
    expect(result.source).toContain("const mobile=Math.max(innerWidth,parent.innerWidth||0)<700");
    expect(result.source).toContain("DPR=Math.min(devicePixelRatio||1,1.15)");
    expect(result.source).toContain("(mobile?500:860)");
    expect(result.source).toContain("const nodes=nodeCache");
    expect(result.source).not.toContain('proj.filter(v=>v.p.kind==="galaxy"');
    expect(result.source).toContain("projectionCache=[]");
    expect(result.source).toContain("project(cached.p,yaw,pitch,roll,t,cached.q)");
    expect(result.source).toContain('if(!isS&&p.kind==="galaxy")');
    expect(result.source).toContain("stellarPath(q.x,q.y,starR");
    expect(result.source).toContain('stage.id==="nur-entry-stage"');
    expect(result.source).toContain("const galaxyStage=frameElement");
    expect(result.source).toContain("let aliveCount=0");
    expect(result.source).toContain("particles.length=aliveCount;rotCY");
    expect(result.source).not.toContain("particles=particles.filter");
    expect(result.source).toContain("getTransientParticleCount");
    expect(result.source).toContain("const minFrameGap=innerWidth<700?44:34");
    expect(canonical).toContain("(mobile?680:1140)");
  });

  it("profiles the exact decoded Universe signatures with a bounded particle cap", () => {
    const canonical = source("docs/reference/universe_decoded_v197.html");
    const result = applyV197PerformanceProfile(canonical, "universe");

    expect(result.applied).toBe(true);
    expect(result.replacementCount).toBe(18);
    expect(result.source).toContain("const mobile=Math.max(innerWidth,parent.innerWidth||0)<700");
    expect(result.source).toContain("const PARTICLE_CAP=1200");
    expect(result.source).toContain("DPR=Math.min(devicePixelRatio||1,1)");
    expect(result.source).toContain("mobile?{galaxy:660,far:370,dust:100,super:30}");
    expect(result.source).toContain("galaxy:660,far:370,dust:100,super:30");
    expect(result.source).toContain("const nodeBudget=innerWidth<700?10:16");
    expect(result.source).toContain("nodes=nodeCache");
    expect(result.source).not.toContain('proj.filter(v=>v.p.kind==="galaxy"');
    expect(result.source).toContain("projectionCache=[]");
    expect(result.source).toContain("project(cached.p,yaw,pitch,roll,t,cached.q)");
    expect(result.source).toContain("if(false)drawNebula(t);");
    expect(result.source).toContain('if(!isS&&p.kind==="galaxy")');
    expect(result.source).toContain("stellarPath(q.x,q.y,starR");
    expect(result.source).toContain('stage.id==="nur-universe-stage"');
    expect(result.source).toContain("const galaxyStage=frameElement");
    expect(result.source).toContain("let aliveCount=0");
    expect(result.source).toContain("particles.length=aliveCount;rotCY");
    expect(result.source).not.toContain("particles=particles.filter");
    expect(result.source).toContain("getTransientParticleCount");
    expect(result.source).toContain("const minFrameGap=innerWidth<700?48:42");
    expect(result.source).toContain("function scheduleFrame(){if(reduced||frameRAF)return;frameRAF=requestAnimationFrame(frame)}");
    expect(result.source).not.toContain("__q");
    expect(result.source).not.toContain("setTimeout(()=>{frameRAF=requestAnimationFrame(frame)},delay)");
    expect(result.source).not.toContain('?72:25');
    expect(canonical).toContain("const PARTICLE_CAP=1880");
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
