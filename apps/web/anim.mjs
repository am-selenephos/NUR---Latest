import { chromium } from "@playwright/test";
const b=await chromium.launch({headless:false,args:["--enable-gpu","--ignore-gpu-blocklist"]});
const c=await b.newContext({viewport:{width:1920,height:1080},deviceScaleFactor:1});
const p=await c.newPage();
await p.goto("http://localhost:4173/"); await p.waitForTimeout(4000);
await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>window.nurShowFront?.());
await p.waitForTimeout(5000);
const e=p.frameLocator("#nur-entry-stage");
console.log(JSON.stringify(await e.locator("body").evaluate(()=>{
  const anims=document.getAnimations();
  const running=anims.filter(a=>a.playState==="running");
  const byName={};
  for(const a of running){const n=a.animationName||a.constructor.name||"?";byName[n]=(byName[n]||0)+1;}
  const seals=document.querySelectorAll(".nur-star-seal, .nur-mini-star, [class*='star-seal'], [class*='mini-star']");
  return { totalElements: document.querySelectorAll("*").length,
    animationsTotal: anims.length, animationsRunning: running.length,
    topAnimations: Object.entries(byName).sort((a,b)=>b[1]-a[1]).slice(0,6),
    starSealHosts: seals.length,
    svgNodes: document.querySelectorAll("svg").length,
    blurred: [...document.querySelectorAll("*")].filter(el=>{const f=getComputedStyle(el).filter;return f&&f!=="none"&&/blur/.test(f);}).length };
}),null,1));
await b.close();
