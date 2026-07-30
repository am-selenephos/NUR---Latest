import { createHash } from "node:crypto";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { describe, expect, it } from "vitest";

const runtimePath = resolve(process.cwd(), "src/bridge/v43StarBrainRuntime.js");
const bridgePath = resolve(process.cwd(), "src/bridge/v197StarBrain.ts");
const runtime = readFileSync(runtimePath, "utf8");
const bridge = readFileSync(bridgePath, "utf8");

describe("V43-derived NUR star-brain source", () => {
  it("keeps the supplied V43 anatomy and adds the approved sparkle/stem extension", () => {
    expect(createHash("sha256").update(runtime).digest("hex"))
      .toBe("6c6c70fb566cacb658a693ab9d747c6b42fa02c9b588eb66b5d21968850a9eac");
    expect(runtime).toContain("canvas.id = 'nur-brain-canvas';");
    expect(runtime).toContain("const N_CORTEX = MOBILE ? 740 : 1112;");
    expect(runtime).toContain("const N_CEREB  = MOBILE ? 154 : 225;");
    expect(runtime).toContain("const N_STEM   = MOBILE ? 97  : 147;");
    expect(runtime).toContain("host.dataset.nurSparkleProfile='exact-galaxy-rig-star';");
    expect(runtime).toContain("host.dataset.nurGalaxyPaint='v197-simple-galaxy-particle-v1';");
    expect(runtime).toContain("host.dataset.nurAnatomy='cortex-cerebellum-brainstem';");
    // Glint is preserved for the structural stars; the dust population skips it
    // because a pow(x,18) specular flash is invisible at that size and it is 760
    // of 1,820 points paying for an effect nobody can see.
    expect(runtime).toContain("const glint=(REDUCED||isDust)?0:Math.pow(.5+.5*Math.sin(p.gl),18);");
    // The square-plus-cross particle was replaced with the galaxy rig's stellar
    // form on founder instruction. Anatomy is untouched; only the paint changed.
    expect(runtime).not.toContain("const simpleR=Math.max(.52,rad*.82);");
    expect(runtime).toContain("starPath(g,mid,mid,outer,-Math.PI/2);");
    // Halos are rasterised once per colour and size bucket rather than allocating
    // two radial gradients per star per frame, as the rig does.
    // Large stars are rasterised once per colour and size bucket. Sub-pixel
    // stars paint directly, while the prism palette is fixed to 32 steps, so
    // neither scaled blits nor unbounded colour-keyed canvases can stall RAF.
    expect(runtime).toContain("const starCache=new Map();");
    expect(runtime).toContain("const PRISM_WHEEL=Array.from({length:32}");
    expect(runtime).toContain("const starCssCache=new Map();");
    expect(runtime).toContain("function starSprite(col,bucket)");
    expect(runtime).toContain("if(rad<.78)");
    expect(runtime).toContain("c.fillRect(x-size/2,y-size/2,size,size);");
    expect(runtime).toContain("c.drawImage(sprite,x-sprite.width/2,y-sprite.height/2);");
    expect(runtime).toContain("host.dataset.nurRenderProfile='bounded-prism-cache-direct-pinpoints-v1';");
    expect(runtime).toContain("host.dataset.nurPrismWheel=String(PRISM_WHEEL.length);");
    expect(runtime).toContain("window.nurStarBrain={ storm, absorb, shatter, firePulse, dispose };");
    expect(runtime).not.toContain("nur-brain-canvas-v197");
    expect(() => new Function(runtime)).not.toThrow();
  });

  /**
   * The anatomy assertions above keep the founder-approved V43 form locked.
   * The lifecycle below prevents its RAF and ambient interval from continuing
   * after the canonical host hides that stage.
   */
  it("can release the surface it owns", () => {
    expect(runtime).toContain("cancelAnimationFrame(rafHandle)");
    expect(runtime).toContain("function dispose()");
    expect(runtime).toContain("function stageIsVisible()");
    expect(runtime).toContain("function requestBrainFrame()");
    expect(runtime).toContain("if(disposed || rafHandle!==null || !stageIsVisible()) return;");
    expect(runtime).toContain("if(document.hidden || !stageIsVisible()) return;");
    // Everything the runtime registers must be undone.
    expect(runtime).toContain("teardown.push(()=>removeEventListener('resize',resize));");
    expect(runtime).toContain("teardown.push(()=>ro.disconnect());");
    expect(runtime).toContain("teardown.push(()=>io.disconnect());");
    expect(runtime).toContain("teardown.push(()=>stageObserver.disconnect());");
    expect(runtime).toContain("teardown.push(()=>clearInterval(ambientPulseTimer));");
    expect(runtime).toContain("canvas.remove();");
    // The bridge must expose the release path to the scene orchestrator.
    expect(bridge).toContain("export function disposeV197StarBrain");
    // The previously rejected transform-profile approach must stay rejected.
    expect(bridge).not.toContain("applyV197StarBrainLifecycleProfile");
  });

  it("mounts the extended renderer directly without a source-transform profile", () => {
    expect(bridge).toContain('import V43_STAR_BRAIN_RUNTIME from "./v43StarBrainRuntime.js?raw";');
    expect(bridge).toContain("script.textContent = V43_STAR_BRAIN_RUNTIME;");
    expect(bridge).toContain('brainHost.dataset.nurDispersal = "radial-circle";');
    expect(bridge).not.toContain("applyV197StarBrainVisualProfile");
    expect(bridge).not.toContain("applyV197StarBrainLifecycleProfile");
  });
  it("carries a dust population of many small stars that is not wired into the synapse graph", () => {
    // "More stars of different smaller sizes" — a dense fine population filling
    // the volume between the structural points.
    expect(runtime).toContain("const N_DUST   = MOBILE ? 364 : 602;");
    expect(runtime).toContain("addPoint(x,y,z,'dust',.35);");

    // Radii are power-biased: many small, few large, like a real field.
    expect(runtime).toContain("r: (.34 + Math.pow(Math.random(),2.1)*1.95)");
    expect(runtime).toContain("dot.r=.20+Math.pow(Math.random(),2.4)*.62;");

    // Dust must stay out of the O(n^2) synapse build: it is texture, not
    // structure, and wiring it would bury the anatomy and triple the cost.
    expect(runtime).toContain("if(pts[i].group==='dust') continue;");
  });
});
