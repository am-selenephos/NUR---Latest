import { chromium } from "@playwright/test";
const OUT="/home/nur/.cache/nur-full-completion-20260726/proof/visual-acceptance";
const b=await chromium.launch({headless:false,args:["--enable-gpu","--ignore-gpu-blocklist"]});
const c=await b.newContext({viewport:{width:2552,height:1412},deviceScaleFactor:1});
const p=await c.newPage();
await p.goto("http://localhost:4173/"); await p.waitForTimeout(4500);
await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>window.nurShowFront?.());
await p.waitForTimeout(6500);
await p.screenshot({path:`${OUT}/RESTORED-entry.png`});
console.log("ENTRY:", JSON.stringify(await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>{
  const cv=document.querySelector("#space3d");
  const ctx=cv.getContext("2d",{willReadFrequently:true});
  const d=ctx.getImageData(0,0,Math.min(cv.width,1400),Math.min(cv.height,900)).data;
  let lit=0,mx=0; for(let i=0;i<d.length;i+=4){const L=.2126*d[i]+.7152*d[i+1]+.0722*d[i+2];if(L>10)lit++;if(L>mx)mx=L;}
  const g=window.__nurGalaxy||window.nurGalaxy; const dg=g?.getParticleDiagnostics?.();
  return {particles:dg?.total,byKind:dg?.byKind,litPer100k:Math.round(lit/((1400*900)/100000)),maxLum:Math.round(mx),
    shouldRender:dg?.shouldRender,frameScheduled:dg?.frameScheduled};
})));
await b.close();
