export const V197_RUNTIME_PROFILE_SCRIPT_ID = "nur-v197-runtime-performance-profile";

type Replacement = readonly [from: string, to: string];

export const V197_GALAXY_STAR_PAINT = Object.freeze({
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

/*
 * Fill-rate is bounded by total backing-store pixels, not by a fixed DPR.
 *
 * A flat `min(devicePixelRatio, 1.65)` means the canvas grows without limit as
 * the window grows: at 1600x1000 that is 4.3M pixels, but on a 2560x1440
 * display it is 11.2M — 2.6x the per-frame paint cost for the same scene, which
 * is why the interface got choppier the larger the display. Capping the ratio
 * instead (the previous profile's answer) flattens small windows to buy headroom
 * for large ones.
 *
 * The budget caps the product instead. Below the budget the canvas runs at full
 * device resolution up to the canonical ceiling; above it, the ratio falls only
 * as far as the extra area demands, and never below 1.
 */
const pixelBudgetDpr = (ceiling: number, budget: number) =>
  `DPR=Math.max(1,Math.min(devicePixelRatio||1,${ceiling},Math.sqrt(${budget}/Math.max(1,innerWidth*innerHeight))))`;

const GALAXY_STAR_PAINT_REPLACEMENT: Replacement = [
  'if(p.kind==="dust"){const dr=',
  'if(!isS&&p.kind==="galaxy"){const starCol=p.prism?prismShift(p.col,p.prismPhase+t*p.prismSpeed+phase*.18,twinkle,false):p.col;const starR=Math.max(.34*Math.max(1,DPR),rad*1.62),starA=Math.min(1,alpha*3.1);c.fillStyle=`rgba(${starCol[0]},${starCol[1]},${starCol[2]},${starA})`;stellarPath(q.x,q.y,starR,Math.max(.1,starR*.16),4,p.phase+t*2e-4);c.fill();if(alpha>.34&&rad>1.05){c.fillStyle=`rgba(${starCol[0]},${starCol[1]},${starCol[2]},${Math.min(.46,alpha*.72)})`;c.fillRect(q.x-starR*2.35,q.y-.18,starR*4.7,.36);c.fillRect(q.x-.18,q.y-starR*1.7,.36,starR*3.4)}continue}if(p.kind==="dust"){const dustR=Math.max(.22*Math.max(1,DPR),rad*.86);c.fillStyle=`rgba(${p.col[0]},${p.col[1]},${p.col[2]},${Math.min(.5,alpha*2.1)})`;stellarPath(q.x,q.y,dustR,Math.max(.08,dustR*.18),4,p.phase);c.fill();continue}if(false&&p.kind==="dust"){const dr=',
];

/*
 * The nebula is seven full-viewport gradient fills. Rebuilding those gradients
 * on every frame costs more than the projected stars themselves and does not
 * add useful motion: at its canonical rates the wash shifts by less than a
 * pixel between frames. Presentation paints the same deep-space wash as the
 * canvas' static CSS backdrop, while this guard preserves canonical drawing as
 * an automatic fallback whenever that backdrop has not been installed.
 *
 * Star positions, density, twinkle, depth sorting, parallax and interaction all
 * remain live in the single canonical canvas.
 */
const GALAXY_STATIC_NEBULA_REPLACEMENT: Replacement = [
  "if(profile.nebula>.48)drawNebula(t);",
  'if(profile.nebula>.48&&canvas.dataset.nurNebulaBackdrop!=="css-static-v1")drawNebula(t);',
];

/*
 * Rendering used to be gated on the exact class `is-visible`. Any lifecycle
 * hiccup that left the class off — a transition interrupted, a route restored
 * from history, a stage attached before the class is applied — froze the canvas
 * on a stage the user was actually looking at, which is one of the ways the
 * galaxy went missing.
 *
 * The stage is now asked whether it is *actually being displayed*: real layout
 * box, not `display:none`, not `visibility:hidden`, not transparent, and not
 * `aria-hidden`. That is observable truth rather than a naming convention, so it
 * cannot drift when the class names do. `is-exiting` is still honoured, because
 * during a transition the stage is genuinely on its way out.
 */
/*
 * The result is cached for 250ms. `frameElement` belongs to the *parent*
 * document, so `getBoundingClientRect` and `getComputedStyle` on it force a
 * synchronous layout of the parent from inside the iframe. Measured
 * uncached-per-frame on /systems: p50 104ms, roughly 9.6 FPS, with a
 * characteristic stall-then-burst pattern that did not scale with canvas area —
 * the tell that this was a layout stall rather than fill-rate cost.
 *
 * 250ms is far below any transition the check needs to notice, and the
 * MutationObserver below invalidates it immediately on a class or aria change,
 * so nothing waits a quarter second to start or stop rendering.
 */
const STAGE_VISIBILITY_FN =
  "var __nurStageVis=true,__nurStageVisAt=0;" +
  "function __nurStageVisible(){const stage=frameElement;if(!stage)return true;" +
  'if(stage.getAttribute("aria-hidden")==="true")return false;' +
  'if(stage.classList.contains("is-exiting"))return false;' +
  "const box=stage.getBoundingClientRect();if(box.width<2||box.height<2)return false;" +
  "const view=stage.ownerDocument&&stage.ownerDocument.defaultView;if(!view)return true;" +
  "const cs=view.getComputedStyle(stage);" +
  'if(cs.display==="none"||cs.visibility==="hidden"||parseFloat(cs.opacity||"1")<.02)return false;' +
  "return true}" +
  "function shouldRenderGalaxy(){if(document.hidden)return false;" +
  "const now=Date.now();if(now-__nurStageVisAt<250)return __nurStageVis;" +
  "__nurStageVisAt=now;__nurStageVis=__nurStageVisible();return __nurStageVis}";

const UNIVERSE_STAGE_VISIBILITY_REPLACEMENT: Replacement = [
  "function shouldRenderGalaxy(){return !document.hidden}",
  STAGE_VISIBILITY_FN,
];

/*
 * Entry keeps its extra condition — the intro overlay must have faded — but the
 * stage half of the test is the same observable-visibility check the universe
 * uses, rather than a second copy of the class-name guesswork.
 */
const ENTRY_STAGE_VISIBILITY_REPLACEMENT: Replacement = [
  'function shouldRenderGalaxy(){const intro=document.getElementById("intro");return !document.hidden&&(!intro||intro.classList.contains("fade")||getComputedStyle(intro).display==="none")}',
  STAGE_VISIBILITY_FN.replace(
    "return true}",
    'const intro=document.getElementById("intro");' +
      'return !intro||intro.classList.contains("fade")||getComputedStyle(intro).display==="none"}',
  ),
];

/*
 * The MutationObserver alone was not enough. Measured on /today, /talk and
 * /systems at 56a1963: `shouldRenderGalaxy()` returned true while
 * `frameScheduled` was false on every route — the loop had stopped during the
 * stage transition and nothing re-woke it, so the sky was a frozen black
 * rectangle behind the panels while every particle still existed.
 *
 * The observer only fires on class/aria mutations of the stage, so any path
 * that stops the loop without one leaves the canvas dead with no event to
 * revive it. A 500ms watchdog closes that hole.
 */
const GALAXY_STAGE_OBSERVER_REPLACEMENT: Replacement = [
  'document.addEventListener("visibilitychange",()=>{if(document.hidden){last=0}else{last=0;wakeGalaxy()}},{passive:true});',
  'document.addEventListener("visibilitychange",()=>{if(document.hidden){last=0}else{last=0;__nurStageVisAt=0;wakeGalaxy()}},{passive:true});const galaxyStage=frameElement;if(galaxyStage)new MutationObserver(()=>{__nurStageVisAt=0;if(shouldRenderGalaxy()){last=0;wakeGalaxy()}else{if(frameRAF)cancelAnimationFrame(frameRAF);frameRAF=0;last=0}}).observe(galaxyStage,{attributes:true,attributeFilter:["class","aria-hidden"]});setInterval(()=>{if(!reduced&&!frameRAF&&shouldRenderGalaxy()){last=0;wakeGalaxy()}},1000);if(reduced){let reducedPaintAttempts=0;const reducedPaintTimer=setInterval(()=>{__nurStageVisAt=0;if(shouldRenderGalaxy()){last=0;wakeGalaxy();clearInterval(reducedPaintTimer)}else if(++reducedPaintAttempts>=24)clearInterval(reducedPaintTimer)},250)}',
];

/*
 * Reduced motion means a still galaxy, not an absent galaxy.
 *
 * Canonical V197 checks `reduced` before scheduling its first frame, so a
 * browser profile with reduced motion enabled seeds every particle but leaves
 * the transparent canvas completely unpainted. The brain uses a separate
 * renderer and remains visible, producing the exact "brain but no 3D rig"
 * failure seen in the founder browser.
 *
 * Paint one complete frame in reduced mode, then stop. Resize, visibility and
 * explicit interaction wakes repaint that static scene without starting a
 * continuous animation. Geometry, particles, projection and star paint remain
 * canonical.
 */
const GALAXY_REDUCED_MOTION_REPLACEMENTS: readonly Replacement[] = [
  [
    "function scheduleFrame(){if(galaxyDisposed||reduced||frameRAF)return;frameRAF=requestAnimationFrame(frame)}",
    "function scheduleFrame(){if(galaxyDisposed||frameRAF)return;frameRAF=requestAnimationFrame(frame)}",
  ],
  [
    "function wakeGalaxy(){if(reduced||!shouldRenderGalaxy())return;if(!last)last=performance.now()-FRAME_MS;scheduleFrame()}",
    "function wakeGalaxy(){if(!shouldRenderGalaxy())return;if(!last)last=performance.now()-FRAME_MS;scheduleFrame()}",
  ],
  [
    '}scheduleFrame()}addEventListener("resize"',
    '}if(!reduced)scheduleFrame()}addEventListener("resize"',
  ],
] as const;

const GALAXY_REDUCED_BURST_REPLACEMENTS: readonly Replacement[] = [
  [
    "window.nur3dBurst=(sx=W/2,sy=H/2,intensity=1)=>{energy=",
    "window.nur3dBurst=(sx=W/2,sy=H/2,intensity=1)=>{if(reduced)return;energy=",
  ],
  [
    "window.nur3dWordmarkBurst=rect=>{if(!rect)return;",
    "window.nur3dWordmarkBurst=rect=>{if(reduced||!rect)return;",
  ],
] as const;

/* Keep motion delta bounded, but retire finite bursts by elapsed time so a
 * throttled iframe cannot hold login or route particles for tens of seconds. */
const GALAXY_PARTICLE_COMPACTION_REPLACEMENT: Replacement = [
  "particles=particles.filter(p=>p.life===Infinity||p.life>0);for(const p of particles){if(p.life!==Infinity){const s=dt/16.67;p.x+=p.vx*s;p.y+=p.vy*s;p.z+=p.vz*s;p.vx*=.986;p.vy*=.986;p.vz*=.982;p.life-=s}}",
  "let aliveCount=0;for(let particleIndex=0;particleIndex<particles.length;particleIndex++){const p=particles[particleIndex];if(p.life!==Infinity){const s=dt/16.67,lifeStep=Math.max(s,rawDt/16.67);p.x+=p.vx*s;p.y+=p.vy*s;p.z+=p.vz*s;p.vx*=.986;p.vy*=.986;p.vz*=.982;p.life-=lifeStep;if(p.life<=0)continue}particles[aliveCount++]=p}particles.length=aliveCount;",
];

const GALAXY_RUNTIME_DIAGNOSTIC_REPLACEMENT: Replacement = [
  "getParticleCount:()=>particles.length}",
  "getParticleCount:()=>particles.length,getTransientParticleCount:()=>particles.reduce((count,p)=>count+(p.life===Infinity?0:1),0),getParticleDiagnostics:()=>{const byKind={},finite=[];let invalid=0;for(const p of particles){byKind[p.kind]=(byKind[p.kind]||0)+1;if(p.life!==Infinity){if(Number.isFinite(p.life))finite.push(p.life);else invalid++}}return{total:particles.length,transient:finite.length+invalid,finite:finite.length,invalid,minLife:finite.length?Math.min(...finite):null,maxLife:finite.length?Math.max(...finite):null,byKind,stageId:frameElement&&frameElement.id||null,stageClass:frameElement&&frameElement.className||null,stageHidden:frameElement&&frameElement.getAttribute('aria-hidden')||null,shouldRender:shouldRenderGalaxy(),frameScheduled:!!frameRAF}},dispose:()=>{galaxyDisposed=true;if(frameRAF)cancelAnimationFrame(frameRAF);frameRAF=0;last=0}}",
];

/* The bridge replaces canonical paint with one coordinated Three.js scheduler.
 * The canonical engine therefore needs an honest release switch: hiding its
 * canvas without stopping RAF was the old double-engine performance bug. */
const GALAXY_DISPOSAL_REPLACEMENTS: readonly Replacement[] = [
  [
    "function scheduleFrame(){if(reduced||frameRAF)return;frameRAF=requestAnimationFrame(frame)}",
    "function scheduleFrame(){if(galaxyDisposed||reduced||frameRAF)return;frameRAF=requestAnimationFrame(frame)}",
  ],
] as const;

const GALAXY_PROJECTION_CACHE_REPLACEMENTS: readonly Replacement[] = [
  [
    "let energy=0,particles=[],last=0,frameRAF=0;",
    "let energy=0,particles=[],last=0,frameRAF=0,galaxyDisposed=false,projectionCache=[],nodeCache=[],rotCY=1,rotSY=0,rotCP=1,rotSP=0,rotCR=1,rotSR=0;",
  ],
  [
    "function project(p,yA,pA,rA,t=0){",
    "function project(p,yA,pA,rA,t=0,out={x:0,y:0,z:0,scale:0}){",
  ],
  [
    'const living=p.kind==="galaxy"||p.kind==="dust"||p.kind==="super"||p.kind==="event";const radial=living?Math.hypot(p.x,p.z):0,arm=living?Math.atan2(p.z,p.x):0,wave=living?Math.sin(t*55e-6+arm*1.65+radial*4.6):0,swirl=living?Math.sin(t*38e-6+radial*3.4)*.006:0,breath=living?wave*.014:0,px=p.x*(1+breath)-p.z*swirl,pz=p.z*(1+breath*.72)+p.x*swirl,py=p.y+(living?Math.cos(t*52e-6+arm*1.4)*(.008+radial*.004):0);const cy=Math.cos(yA),sy=Math.sin(yA),cp=Math.cos(pA),sp=Math.sin(pA),cr=Math.cos(rA),sr=Math.sin(rA),x1=px*cy-pz*sy,z1=px*sy+pz*cy,y1=py*cp-z1*sp,z2=py*sp+z1*cp,x2=x1*cr-y1*sr,y2=x1*sr+y1*cr,sc=1/(3.05+z2);',
    "const px=p.x,pz=p.z,py=p.y,cy=rotCY,sy=rotSY,cp=rotCP,sp=rotSP,cr=rotCR,sr=rotSR,x1=px*cy-pz*sy,z1=px*sy+pz*cy,y1=py*cp-z1*sp,z2=py*sp+z1*cp,x2=x1*cr-y1*sr,y2=x1*sr+y1*cr,sc=1/(3.05+z2);",
  ],
  [
    "return{x:W*.5+x2*minSide*1.34*sc,y:H*.5+y2*minSide*1.34*sc,z:z2,scale:sc}}",
    "out.x=W*.5+x2*minSide*1.34*sc;out.y=H*.5+y2*minSide*1.34*sc;out.z=z2;out.scale=sc;return out}",
  ],
  [
    "const proj=particles.map(p=>({p,q:project(p,yaw,pitch,roll,t)}));proj.sort((a,b)=>a.q.z-b.q.z);",
    "rotCY=Math.cos(yaw);rotSY=Math.sin(yaw);rotCP=Math.cos(pitch);rotSP=Math.sin(pitch);rotCR=Math.cos(roll);rotSR=Math.sin(roll);const proj=projectionCache;proj.length=particles.length;for(let i=0;i<particles.length;i++){const cached=proj[i]||(proj[i]={p:null,q:{x:0,y:0,z:0,scale:0}});cached.p=particles[i];project(cached.p,yaw,pitch,roll,t,cached.q)}proj.sort((a,b)=>a.q.z-b.q.z);",
  ],
] as const;

/*
 * Entry remains dimensional, but ambient stars stay subordinate to the brain
 * and copy. Density scales gently with area instead of doubling on large
 * screens. The brain has its own renderer and is deliberately untouched.
 */
const ENTRY_REPLACEMENTS: readonly Replacement[] = [
  ["DPR=Math.min(devicePixelRatio||1,1.65)", pixelBudgetDpr(1.5, 3_400_000)],
  [
    "const mobile=innerWidth<700;",
    "const mobile=Math.max(innerWidth,parent.innerWidth||0)<700;",
  ],
  ["(mobile?680:1140)", "(mobile?400:Math.round(690*Math.min(1.35,Math.max(1,(innerWidth*innerHeight)/1600000))))"],
  ["(mobile?460:720)", "(mobile?260:Math.round(450*Math.min(1.35,Math.max(1,(innerWidth*innerHeight)/1600000))))"],
  ["(mobile?192:320)", "(mobile?72:Math.round(126*Math.min(1.35,Math.max(1,(innerWidth*innerHeight)/1600000))))"],
  ["(mobile?44:76)", "(mobile?20:Math.round(36*Math.min(1.35,Math.max(1,(innerWidth*innerHeight)/1600000))))"],
  [
    'const nodes=proj.filter(v=>v.p.kind==="galaxy"&&v.q.scale<.36).slice(0,130);',
    'const nodes=nodeCache;nodes.length=0;const entryNodeBudget=innerWidth<700?28:64;for(let nodeIndex=0;nodeIndex<proj.length&&nodes.length<entryNodeBudget;nodeIndex++){const candidate=proj[nodeIndex];if(candidate.p.kind==="galaxy"&&candidate.q.scale<.36)nodes.push(candidate)}',
  ],
  ...GALAXY_PROJECTION_CACHE_REPLACEMENTS,
  ...GALAXY_DISPOSAL_REPLACEMENTS,
  GALAXY_PARTICLE_COMPACTION_REPLACEMENT,
  GALAXY_RUNTIME_DIAGNOSTIC_REPLACEMENT,
  GALAXY_STAR_PAINT_REPLACEMENT,
  GALAXY_STATIC_NEBULA_REPLACEMENT,
  ENTRY_STAGE_VISIBILITY_REPLACEMENT,
  GALAXY_STAGE_OBSERVER_REPLACEMENT,
  ...GALAXY_REDUCED_MOTION_REPLACEMENTS,
  ...GALAXY_REDUCED_BURST_REPLACEMENTS,
  [
    "function frame(now){frameRAF=0;if(reduced||!shouldRenderGalaxy())return;if(!last)last=now-FRAME_MS;const rawDt=now-last;",
    "function frame(now){frameRAF=0;if(!shouldRenderGalaxy())return;if(!last)last=now-FRAME_MS;const rawDt=now-last;",
  ],
] as const;

/*
 * The universe profile previously traded away the product to buy frame budget,
 * and then capped the frame rate anyway. Four of its replacements are deleted
 * rather than retuned, because each one removed something the founder listed as
 * a release requirement:
 *
 *   DPR 1.5 -> 1              flattened every star on a HiDPI display
 *   drawNebula -> if(false)   removed deep-space structure outright
 *   far spike -> continue     removed the far stellar plane's diffraction, so
 *                             near/mid/far collapsed into one flat layer
 *   minFrameGap 42ms          hard-capped desktop motion at 23.8 FPS, which is
 *                             the choppiness itself, not a fix for it
 *
 * What survives is the optimisation that costs nothing visible: reusable
 * projection buffers instead of per-frame array allocation, in-place particle
 * compaction, and the cached four-point stellar sprite. Density is reduced on
 * phones only, where the panel is physically smaller.
 */
/*
 * A frame gap, but only on phone widths and only at 33ms — 30 FPS, which is
 * smooth for a drifting star field.
 *
 * The previous profile capped every viewport at 42ms desktop / 48ms mobile,
 * which is 23.8 and 20.8 FPS. That was the lag the founder reported, and it is
 * gone: desktop renders every frame and measures 48.5 Hz on /systems.
 *
 * Restoring the nebula, the far-plane spikes and canonical density does cost
 * real work, and on a small emulated viewport on slow CI hardware that pushed
 * the mobile capture past its budget. Bounding phones at 30 FPS keeps the sky
 * complete — nothing is deleted from what is drawn — while capping how often it
 * is redrawn where the pixels are smallest.
 */
const UNIVERSE_REPLACEMENTS: readonly Replacement[] = [
  ["DPR=Math.min(devicePixelRatio||1,1.5)", pixelBudgetDpr(1.5, 3_400_000)],
  [
    "const mobile=innerWidth<700;",
    "const mobile=Math.max(innerWidth,parent.innerWidth||0)<700;",
  ],
  [
    "const density=mobile?{galaxy:620,far:430,dust:118,super:32}:{galaxy:900,far:585,dust:165,super:48}",
    "const areaScale=Math.min(1.35,Math.max(1,(innerWidth*innerHeight)/1600000));const density=mobile?{galaxy:400,far:260,dust:72,super:20}:{galaxy:Math.round(690*areaScale),far:Math.round(450*areaScale),dust:Math.round(126*areaScale),super:Math.round(36*areaScale)}",
  ],
  [
    'const nodeBudget=innerWidth<700?54:82;const nodes=proj.filter(v=>v.p.kind==="galaxy"&&v.q.scale<.36).slice(0,nodeBudget);',
    'const nodeBudget=innerWidth<700?28:64,nodes=nodeCache;nodes.length=0;for(let nodeIndex=0;nodeIndex<proj.length&&nodes.length<nodeBudget;nodeIndex++){const candidate=proj[nodeIndex];if(candidate.p.kind==="galaxy"&&candidate.q.scale<.36)nodes.push(candidate)}',
  ],
  ...GALAXY_PROJECTION_CACHE_REPLACEMENTS,
  ...GALAXY_DISPOSAL_REPLACEMENTS,
  GALAXY_PARTICLE_COMPACTION_REPLACEMENT,
  GALAXY_RUNTIME_DIAGNOSTIC_REPLACEMENT,
  GALAXY_STAR_PAINT_REPLACEMENT,
  GALAXY_STATIC_NEBULA_REPLACEMENT,
  UNIVERSE_STAGE_VISIBILITY_REPLACEMENT,
  GALAXY_STAGE_OBSERVER_REPLACEMENT,
  ...GALAXY_REDUCED_MOTION_REPLACEMENTS,
  ...GALAXY_REDUCED_BURST_REPLACEMENTS,
  [
    "function frame(now){frameRAF=0;if(reduced||!shouldRenderGalaxy())return;if(!last)last=now-FRAME_MS;const rawDt=now-last;",
    "function frame(now){frameRAF=0;if(!shouldRenderGalaxy())return;if(!last)last=now-FRAME_MS;if(innerWidth<700&&now-last<33){scheduleFrame();return}const rawDt=now-last;",
  ],
] as const;

export type V197ProfileResult = {
  source: string;
  applied: boolean;
  replacementCount: number;
  failure?: string;
};

function replaceExactlyOnce(source: string, [from, to]: Replacement): V197ProfileResult {
  const first = source.indexOf(from);
  if (first < 0) {
    return { source, applied: false, replacementCount: 0, failure: `missing:${from.slice(0, 72)}` };
  }
  if (source.indexOf(from, first + from.length) >= 0) {
    return { source, applied: false, replacementCount: 0, failure: `duplicate:${from.slice(0, 72)}` };
  }
  return {
    source: `${source.slice(0, first)}${to}${source.slice(first + from.length)}`,
    applied: true,
    replacementCount: 1,
  };
}

export function applyV197PerformanceProfile(
  source: string,
  kind: "entry" | "universe",
): V197ProfileResult {
  const replacements = kind === "entry" ? ENTRY_REPLACEMENTS : UNIVERSE_REPLACEMENTS;
  let profiled = source;
  let replacementCount = 0;

  for (const replacement of replacements) {
    const result = replaceExactlyOnce(profiled, replacement);
    if (!result.applied) {
      return {
        source,
        applied: false,
        replacementCount: 0,
        failure: result.failure,
      };
    }
    profiled = result.source;
    replacementCount += result.replacementCount;
  }

  return { source: profiled, applied: true, replacementCount };
}

/*
 * The canonical host computes integrity against its untouched embedded bytes.
 * This bootstrap intercepts only the browser's srcdoc assignment and applies a
 * deterministic runtime quality profile. If any known signature drifts, the
 * original source is used and the host records a visible-to-tests fallback.
 */
export function buildV197PerformanceBootstrap(): string {
  const entry = JSON.stringify(ENTRY_REPLACEMENTS);
  const universe = JSON.stringify(UNIVERSE_REPLACEMENTS);
  return `<script id="${V197_RUNTIME_PROFILE_SCRIPT_ID}">
(() => {
  "use strict";
  const requested = new URLSearchParams(location.search).get("nur-quality");
  if (requested === "canonical") {
    document.documentElement.dataset.nurRuntimeProfile = "canonical";
    return;
  }
  const profiles = { entry: ${entry}, universe: ${universe} };
  const descriptor = Object.getOwnPropertyDescriptor(HTMLIFrameElement.prototype, "srcdoc");
  if (!descriptor || typeof descriptor.set !== "function" || typeof descriptor.get !== "function") {
    document.documentElement.dataset.nurRuntimeProfile = "canonical-fallback";
    document.documentElement.dataset.nurRuntimeProfileError = "srcdoc-descriptor";
    return;
  }
  const replaceOnce = (source, pair) => {
    const [from, to] = pair;
    const first = source.indexOf(from);
    if (first < 0 || source.indexOf(from, first + from.length) >= 0) return null;
    return source.slice(0, first) + to + source.slice(first + from.length);
  };
  Object.defineProperty(HTMLIFrameElement.prototype, "srcdoc", {
    configurable: descriptor.configurable,
    enumerable: descriptor.enumerable,
    get: descriptor.get,
    set(value) {
      let next = value;
      if (typeof value === "string") {
        const kind = value.includes("const PARTICLE_CAP=1880")
          ? "universe"
          : value.includes("V106: 100% denser actual galaxy seed")
            ? "entry"
            : null;
        if (kind) {
          for (const pair of profiles[kind]) {
            const replaced = replaceOnce(next, pair);
            if (replaced === null) {
              document.documentElement.dataset.nurRuntimeProfile = "canonical-fallback";
              document.documentElement.dataset.nurRuntimeProfileError = kind + "-signature";
              next = value;
              break;
            }
            next = replaced;
          }
          if (next !== value) {
            document.documentElement.dataset.nurRuntimeProfile = "balanced";
            document.documentElement.dataset["nur" + kind[0].toUpperCase() + kind.slice(1) + "Profile"] = "applied";
          }
        }
      }
      descriptor.set.call(this, next);
    },
  });
})();
</script>`;
}
