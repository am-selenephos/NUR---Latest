import { chromium } from "@playwright/test";
for (const [args,label] of [
  [["--enable-gpu","--ignore-gpu-blocklist"],"WITH gpu flags (my captures)"],
  [[],"DEFAULT flags (your browser)"],
  [["--disable-gpu"],"GPU disabled"],
]) {
  const b=await chromium.launch({headless:false,args});
  const c=await b.newContext({viewport:{width:2552,height:1412},deviceScaleFactor:1});
  const p=await c.newPage();
  await p.goto("http://localhost:4173/"); await p.waitForTimeout(4000);
  await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>window.nurShowFront?.());
  await p.waitForTimeout(6000);
  const r=await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>{
    const cv=document.querySelector("#space3d");
    if(!cv) return {canvas:false};
    const ctx=cv.getContext("2d",{willReadFrequently:true});
    const d=ctx.getImageData(0,0,Math.min(cv.width,1200),Math.min(cv.height,800)).data;
    let lit=0,mx=0; for(let i=0;i<d.length;i+=4){const L=.2126*d[i]+.7152*d[i+1]+.0722*d[i+2];if(L>10)lit++;if(L>mx)mx=L;}
    const g=window.__nurGalaxy||window.nurGalaxy; const dg=g?.getParticleDiagnostics?.();
    return {particles:dg?.total??null, lit, maxLum:Math.round(mx),
      shouldRender:dg?.shouldRender, frameScheduled:dg?.frameScheduled,
      cvW:cv.width, cvH:cv.height, opacity:getComputedStyle(cv).opacity};
  });
  console.log(`${label.padEnd(30)} lit=${String(r.lit).padEnd(8)} maxLum=${String(r.maxLum).padEnd(4)} particles=${r.particles} scheduled=${r.frameScheduled}`);
  await b.close();
}
