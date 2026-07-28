#!/usr/bin/env node
/**
 * Frame rate from a real Chrome trace.
 *
 * Use this, not CDP screencast. Screencast JPEG-encodes every frame, and at
 * 1920x1080 and above the encoder saturates well below the true rate — it read
 * 8 FPS where the trace reads 25, and it read 16 FPS under a 6x CPU throttle
 * against 8 unthrottled, which is impossible for an application and was the
 * clue that the harness was the thing being measured.
 *
 * `commits/s` is the number to read. One Commit is one composited frame.
 * DrawFrame and PipelineReporter fire several times per frame across pipeline
 * stages, so drawFPS reads in the hundreds and means nothing on its own.
 * rasterTasks/s shows how much content is being re-rasterised rather than
 * reused, which is the useful signal when commits are low.
 *
 *   node infra/scripts/measure-frame-rate.mjs
 */
import { chromium } from "@playwright/test";
const b=await chromium.launch({headless:false,args:["--enable-gpu","--ignore-gpu-blocklist"]});

// Authoritative frame timing: count compositor DrawFrame events from a real
// Chrome trace. No JPEG encoding in the loop, unlike screencast.
async function frames(p, seconds, label){
  const cdp=await p.context().newCDPSession(p);
  const events=[];
  cdp.on("Tracing.dataCollected", ({value}) => events.push(...value));
  await cdp.send("Tracing.start", {
    traceConfig:{ includedCategories:[
      "disabled-by-default-devtools.timeline.frame","disabled-by-default-devtools.timeline","benchmark","viz"] } });
  const t0=Date.now();
  await p.waitForTimeout(seconds*1000);
  const done=new Promise(r=>cdp.once("Tracing.tracingComplete",r));
  await cdp.send("Tracing.end"); await done;
  const el=(Date.now()-t0)/1000;
  const draws=events.filter(e=>e.name==="DrawFrame"||e.name==="PipelineReporter").length;
  const commits=events.filter(e=>e.name==="Commit").length;
  const raster=events.filter(e=>e.name==="RasterTask").length;
  await cdp.detach();
  console.log(`${label.padEnd(22)} drawFPS=${(draws/el).toFixed(1)}  commits/s=${(commits/el).toFixed(1)}  rasterTasks/s=${(raster/el).toFixed(0)}`);
  return draws/el;
}

for (const [w,h,tag] of [[1920,1080,"FHD"],[2560,1440,"QHD"]]) {
  const c=await b.newContext({viewport:{width:w,height:h},deviceScaleFactor:1});
  const p=await c.newPage();
  await p.goto("http://localhost:4173/"); await p.waitForTimeout(4000);
  await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>window.nurShowFront?.());
  await p.waitForTimeout(5000);
  await frames(p,5,`ENTRY ${tag}`);
  const e=p.frameLocator("#nur-entry-stage");
  await e.locator("#f4-signin").click();
  await e.locator("#f4-signin-email").fill("owner@nur.app");
  await e.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await e.locator("#f4-signin-form button[type='submit']").click();
  await p.waitForTimeout(9000);
  await p.goto("http://localhost:4173/systems"); await p.waitForTimeout(6000);
  await frames(p,5,`SYSTEMS ${tag}`);
  await c.close();
}
await b.close();
import { chromium } from "@playwright/test";
const b=await chromium.launch({headless:false,args:["--enable-gpu","--ignore-gpu-blocklist"]});

// Authoritative frame timing: count compositor DrawFrame events from a real
// Chrome trace. No JPEG encoding in the loop, unlike screencast.
async function frames(p, seconds, label){
  const cdp=await p.context().newCDPSession(p);
  const events=[];
  cdp.on("Tracing.dataCollected", ({value}) => events.push(...value));
  await cdp.send("Tracing.start", {
    traceConfig:{ includedCategories:[
      "disabled-by-default-devtools.timeline.frame","disabled-by-default-devtools.timeline","benchmark","viz"] } });
  const t0=Date.now();
  await p.waitForTimeout(seconds*1000);
  const done=new Promise(r=>cdp.once("Tracing.tracingComplete",r));
  await cdp.send("Tracing.end"); await done;
  const el=(Date.now()-t0)/1000;
  const draws=events.filter(e=>e.name==="DrawFrame"||e.name==="PipelineReporter").length;
  const commits=events.filter(e=>e.name==="Commit").length;
  const raster=events.filter(e=>e.name==="RasterTask").length;
  await cdp.detach();
  console.log(`${label.padEnd(22)} drawFPS=${(draws/el).toFixed(1)}  commits/s=${(commits/el).toFixed(1)}  rasterTasks/s=${(raster/el).toFixed(0)}`);
  return draws/el;
}

for (const [w,h,tag] of [[1920,1080,"FHD"],[2560,1440,"QHD"]]) {
  const c=await b.newContext({viewport:{width:w,height:h},deviceScaleFactor:1});
  const p=await c.newPage();
  await p.goto("http://localhost:4173/"); await p.waitForTimeout(4000);
  await p.frameLocator("#nur-entry-stage").locator("body").evaluate(()=>window.nurShowFront?.());
  await p.waitForTimeout(5000);
  await frames(p,5,`ENTRY ${tag}`);
  const e=p.frameLocator("#nur-entry-stage");
  await e.locator("#f4-signin").click();
  await e.locator("#f4-signin-email").fill("owner@nur.app");
  await e.locator("#f4-signin-password").fill("owner-demo-pass-123");
  await e.locator("#f4-signin-form button[type='submit']").click();
  await p.waitForTimeout(9000);
  await p.goto("http://localhost:4173/systems"); await p.waitForTimeout(6000);
  await frames(p,5,`SYSTEMS ${tag}`);
  await c.close();
}
await b.close();
