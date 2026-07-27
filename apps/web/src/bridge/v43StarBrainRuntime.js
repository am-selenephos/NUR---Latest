(() => {
  'use strict';
  const REDUCED = matchMedia('(prefers-reduced-motion: reduce)').matches;
  const host = document.getElementById('front-nur-star');
  if(!host) return;
  host.setAttribute('title','drag to spin the mind - click: it dissolves into stardust and reforms - double-click: neural storm - scroll to zoom');
  host.setAttribute('aria-label','A living brain made of stars. Drag to spin it. Click and it dissolves into tiny star glitter, then flows back together.');

  const canvas = document.createElement('canvas');
  canvas.id = 'nur-brain-canvas';
  host.appendChild(canvas);
  const c = canvas.getContext('2d', { alpha:true });
  // Scaled drawImage with smoothing enabled resamples every blit. The stars are
  // soft radial sprites, so filtering buys nothing visible and doubled the
  // script time when the sprite paint was introduced.
  if(c) c.imageSmoothingEnabled=false;

  /* ---- exact V197 galaxy-rig palette ------------------------------------ */
  const SPECTRA={
    O:[[140,160,255],[158,178,255],[118,148,255]],
    B:[[172,192,255],[192,208,255],[162,185,255]],
    A:[[250,253,255],[255,255,255],[244,251,255]],
    F:[[255,252,215],[252,248,200],[255,250,188]],
    G:[[255,244,164],[255,238,138],[255,230,118]],
    K:[[255,210,78],[255,195,62],[255,178,48]],
    M:[[255,152,98],[255,130,68],[255,108,56]]
  };
  const SPECTRAL_DISTRIBUTION=[
    {t:'M',w:.3},{t:'K',w:.2},{t:'G',w:.16},{t:'F',w:.12},
    {t:'A',w:.1},{t:'B',w:.08},{t:'O',w:.04}
  ];
  const PRISM=[[255,108,128],[255,158,74],[255,222,92],[126,237,130],[99,224,255],[121,151,255],[194,138,255],[255,142,211]];
  const rnd=(a,b)=>a+Math.random()*(b-a);
  const pick=a=>a[(Math.random()*a.length)|0];
  function galaxyColor(){
    let r=Math.random(), cumulative=0;
    for(const {t,w} of SPECTRAL_DISTRIBUTION){
      cumulative+=w;
      if(r<cumulative) return pick(SPECTRA[t]);
    }
    return SPECTRA.G[0];
  }
  function mixCol(a,b,t){
    return [
      Math.round(a[0]+(b[0]-a[0])*t),
      Math.round(a[1]+(b[1]-a[1])*t),
      Math.round(a[2]+(b[2]-a[2])*t)
    ];
  }
  function prismShift(col,phase,twinkle=1){
    const orbit=(phase%(Math.PI*2)+Math.PI*2)/(Math.PI*2)*PRISM.length;
    const i0=Math.floor(orbit)%PRISM.length, i1=(i0+1)%PRISM.length;
    const prism=mixCol(PRISM[i0],PRISM[i1],orbit-i0);
    return mixCol(col,prism,Math.min(.58,.24+twinkle*.1));
  }

  /* ---- 3D star-brain point cloud ---------------------------------------
     axes: x = left/right (hemispheres), y = up, z = front(+)/back(-) */
  const MOBILE = innerWidth < 700;
  const N_CORTEX = MOBILE ? 740 : 1112;
  const N_CEREB  = MOBILE ? 154 : 225;
  const N_STEM   = MOBILE ? 97  : 147;
  // Dust: a dense population of very small stars filling the volume between the
  // structural points. These carry almost no individual weight but they are what
  // turns a scatter of dots into a mass with substance.
  // Reduced from 760: with the deep field now carrying the background, the
  // brain no longer has to supply all the fine detail, and a lighter dust layer
  // keeps the anatomy legible instead of veiling it.
  const N_DUST   = MOBILE ? 364 : 602;
  const pts = [];

  function addPoint(x,y,z,group,foldDim){
    const prism = Math.random() < .12;
    pts.push({
      x,y,z, group,
      ox:0, oy:0, oz:0, vx:0, vy:0, vz:0,        // jelly offset + velocity
      // Power-biased radius: many small stars, few large ones, which is how a
      // real field is distributed. A flat rnd(.7,2.1) made every star the same
      // apparent size and flattened the depth.
      r: (.34 + Math.pow(Math.random(),2.1)*1.95) * (group==='stem' ? .92 : 1),
      col: prism ? pick(PRISM) : galaxyColor(), prism,
      prismPhase:rnd(0,Math.PI*2), prismSpeed:rnd(12e-5,42e-5),
      tw: rnd(0,Math.PI*2), tws: rnd(.010,.032), twa: rnd(.25,.55),
      gl: rnd(0,Math.PI*2), gls: rnd(.014,.034), gla: rnd(.62,1.18),
      dim: foldDim||0
    });
  }
  // cortex: golden-spiral sphere -> brain ellipsoid + gyri folds + fissure
  for(let i=0;i<N_CORTEX;i++){
    const t=(i+.5)/N_CORTEX;
    const inc=Math.acos(1-2*t), az=Math.PI*(1+Math.sqrt(5))*i;
    let x=Math.sin(inc)*Math.cos(az), y=Math.cos(inc), z=Math.sin(inc)*Math.sin(az);
    // gyri: two interleaved wrinkle frequencies along the surface
    let fold = .058*Math.sin(az*7 + Math.sin(inc*4)*1.8) + .036*Math.sin(az*13 + inc*9);
    const nearFissure = Math.abs(x) < .12 && y > -.15;
    if(nearFissure) fold = -.05;                       // groove, not ridge
    const f = 1 + fold;
    x*=f; y*=f; z*=f;
    // ellipsoid proportions
    x*=1.00; y*=.83; z*=1.26;
    // longitudinal fissure: push hemispheres apart at the midline
    if(Math.abs(x) < .11 && y > -.12) x = Math.sign(x||rnd(-1,1)) * (.11 + Math.abs(x)*.35);
    // frontal taper + flattened underside + temporal bulge
    if(z > .55) x *= 1 - .16*(z-.55);
    if(y < -.42) y = -.42 + (y+.42)*.45;
    if(y < -.05 && Math.abs(x) > .52 && z > .1) y -= .07;
    addPoint(x,y,z,'cortex', nearFissure ? .45 : 0);
  }
  // cerebellum: small finely-striped ellipsoid, lower back
  for(let i=0;i<N_CEREB;i++){
    const t=(i+.5)/N_CEREB;
    const inc=Math.acos(1-2*t), az=Math.PI*(1+Math.sqrt(5))*i;
    let x=Math.sin(inc)*Math.cos(az), y=Math.cos(inc), z=Math.sin(inc)*Math.sin(az);
    const f = 1 + .045*Math.sin(inc*16);               // horizontal striations
    addPoint(x*.55*f, -.55 + y*.30*f, -.80 + z*.42*f, 'cereb', .1);
  }
  // brainstem: a curved, tapered star tube from midbrain through pons to medulla
  const stemAngle=Math.PI*(3-Math.sqrt(5));
  for(let i=0;i<N_STEM;i++){
    const t=(i+.5)/N_STEM, a=i*stemAngle;
    const pons=Math.exp(-Math.pow((t-.28)/.17,2));
    const shell=Math.sqrt(((i%7)+.65)/7);
    const rr=(.11-.045*t+.052*pons)*shell;
    const centerX=.014*Math.sin(t*Math.PI*1.3);
    const centerY=-.40-t*.62;
    const centerZ=-.38+t*.22-.045*Math.sin(t*Math.PI);
    addPoint(centerX+Math.cos(a)*rr, centerY, centerZ+Math.sin(a)*rr*.76, 'stem', .08);
  }
  // cortex-shaped dust: same golden-spiral shell, pulled inward to varying
  // depths so the volume fills rather than only the surface
  for(let i=0;i<N_DUST;i++){
    const t=(i+.5)/N_DUST;
    const inc=Math.acos(1-2*t), az=Math.PI*(1+Math.sqrt(5))*i*1.618;
    let x=Math.sin(inc)*Math.cos(az), y=Math.cos(inc), z=Math.sin(inc)*Math.sin(az);
    const depth=.42+Math.pow(Math.random(),.6)*.62;   // inside the shell
    x*=depth; y*=depth*.83; z*=depth*1.26;
    if(Math.abs(x)<.10 && y>-.12) x=Math.sign(x||rnd(-1,1))*(.10+Math.abs(x)*.35);
    if(y<-.42) y=-.42+(y+.42)*.45;
    const before=pts.length;
    addPoint(x,y,z,'dust',.35);
    const dot=pts[before];
    dot.r=.20+Math.pow(Math.random(),2.4)*.62;        // very small
    dot.twa*=.55;                                     // and quiet
  }

  host.dataset.nurDustCount=String(N_DUST);
  host.dataset.nurPointCount=String(pts.length);
  host.dataset.nurStemPointCount=String(N_STEM);
  host.dataset.nurSparkleProfile='exact-galaxy-rig-star';
  host.dataset.nurGalaxyPaint='v197-simple-galaxy-particle-v1';
  host.dataset.nurAnatomy='cortex-cerebellum-brainstem';

  /* ---- synapse edges (k-nearest within same tissue) --------------------- */
  const edges=[]; const adj=pts.map(()=>[]);
  for(let i=0;i<pts.length;i++){
    // Dust is texture, not structure. It carries no synapses: wiring 760 extra
    // points into the graph would both bury the anatomy under filaments and
    // triple the cost of this O(n^2) build.
    if(pts[i].group==='dust') continue;
    let n1=-1,n2=-1,d1=9,d2=9;
    for(let j=0;j<pts.length;j++){
      if(i===j || pts[i].group!==pts[j].group) continue;
      const dx=pts[i].x-pts[j].x, dy=pts[i].y-pts[j].y, dz=pts[i].z-pts[j].z;
      const d=dx*dx+dy*dy+dz*dz;
      if(d<d1){d2=d1;n2=n1;d1=d;n1=j}else if(d<d2){d2=d;n2=j}
    }
    for(const [j,dd] of [[n1,d1],[n2,d2]]){
      if(j<0 || dd>.09) continue;
      const key=i<j?i+'-'+j:j+'-'+i;
      if(!edges.some(e=>e.key===key)){
        edges.push({key,a:i,b:j});
        adj[i].push(j); adj[j].push(i);
      }
    }
  }

  /* ---- neural pulses (thought signals travelling the synapses) ---------- */
  const pulses=[];
  function firePulse(from){
    const start = from ?? (Math.random()*pts.length)|0;
    const path=[start]; let cur=start;
    for(let h=0;h<3+((Math.random()*4)|0);h++){
      const next=adj[cur][(Math.random()*adj[cur].length)|0];
      if(next==null) break;
      path.push(next); cur=next;
    }
    if(path.length>1) pulses.push({path, t:0, speed:rnd(.028,.05), col:Math.random()<.6?pick(PRISM):galaxyColor()});
  }

  /* ---- glitter motes drifting off the surface --------------------------- */
  const motes=[];
  function emitMote(p, px, py){
    if(motes.length>44) return;
    motes.push({x:px, y:py, vx:rnd(-.22,.22), vy:rnd(-.5,-.14), life:rnd(38,80), max:80, col:p?p.col:galaxyColor(), r:rnd(.6,1.6)});
  }

  /* ---- camera / interaction state --------------------------------------- */
  let W=0,H=0,cx=0,cy=0,scale=1,DPR=1;
  let onscreen=true,lastFrame=0;
  // Two canvases share this document: the full-viewport star field and this
  // brain. Measured on /systems, hiding the brain roughly doubled the galaxy's
  // rate (9.2 -> 18.9 Hz), so the two were competing for the same frame budget.
  //
  // The brain yields when the galaxy is present. It is a slowly drifting cloud —
  // at 20Hz it is indistinguishable from 33Hz — while the star field carries the
  // parallax the eye actually tracks. When the brain is the only canvas in the
  // document it keeps the original cadence.
  const GALAXY_PRESENT=!!document.querySelector('#space3d');
  const MIN_FRAME_GAP=MOBILE?(GALAXY_PRESENT?66:40):(GALAXY_PRESENT?50:30);
  let cosYaw=1,sinYaw=0,cosPitch=1,sinPitch=0;
  let yaw=.85, pitch=-.14, vyaw=REDUCED?0:.0022, vpitch=0;
  let zoom=1, targetZoom=1;
  let dragging=false, dragDist=0, lx=0, ly=0;
  let hoverX=-1e4, hoverY=-1e4;
  let mode='live', modeT=0;      // live | absorb | bloom
  // Lifecycle: this runtime is injected into the canonical iframe and previously
  // had no way to stop. Without a handle its loop outlives every route change,
  // which is how the interface ended up with several engines animating at once.
  let rafHandle=null;
  let disposed=false;
  const teardown=[];
  const frameStage=window.frameElement;
  function stageIsVisible(){
    if(!frameStage) return true;
    if(frameStage.id==='nur-entry-stage'){
      return !frameStage.classList.contains('is-exiting') && frameStage.getAttribute('aria-hidden')!=='true';
    }
    if(frameStage.id==='nur-universe-stage'){
      // Observable display state rather than a class name. A stage that is on
      // screen but momentarily without `is-visible` used to freeze this canvas.
      if(frameStage.getAttribute('aria-hidden')==='true') return false;
      const box=frameStage.getBoundingClientRect();
      if(box.width<2||box.height<2) return false;
      const view=frameStage.ownerDocument&&frameStage.ownerDocument.defaultView;
      if(!view) return true;
      const cs=view.getComputedStyle(frameStage);
      return cs.display!=='none'&&cs.visibility!=='hidden'&&parseFloat(cs.opacity||'1')>=0.02;
    }
    return true;
  }
  function requestBrainFrame(){
    if(disposed || rafHandle!==null || !stageIsVisible()) return;
    rafHandle=requestAnimationFrame(frame);
  }
  let energy=0;                  // storm brightness boost
  let breath=0;

  function resize(){
    DPR=Math.min(devicePixelRatio||1,1.1);
    const r=host.getBoundingClientRect();
    W=Math.max(2,r.width); H=Math.max(2,r.height);
    canvas.width=Math.round(W*DPR); canvas.height=Math.round(H*DPR);
    c.setTransform(DPR,0,0,DPR,0,0);
    cx=W/2; cy=H/2;
    const systemsScale=host.dataset.nurSurface==='universe';
    // Entry brain enlarged 40% (.34 -> .476) on founder instruction. The Systems
    // surface keeps its own framing because it shares the panel with the System
    // cards. Only the projection scale changes; rotation, physics, dispersal and
    // every interaction stay exactly as they were.
    scale=Math.min(W,H)*(systemsScale ? .43 : .476);
    host.dataset.nurScaleProfile=systemsScale?'systems-expanded':'entry-exact';
  }
  resize();
  addEventListener('resize',resize,{passive:true});
  teardown.push(()=>removeEventListener('resize',resize));
  // the host lives inside #welcome which starts display:none - the first real
  // measurement only exists once the front page reveals, so watch the box itself
  if(typeof ResizeObserver!=='undefined'){
    const ro=new ResizeObserver(resize); ro.observe(host);
    teardown.push(()=>ro.disconnect());
  }
  if(typeof IntersectionObserver!=='undefined'){
    const io=new IntersectionObserver(entries=>{
      onscreen=entries.some(entry=>entry.isIntersecting&&entry.intersectionRect.width>0&&entry.intersectionRect.height>0);
    });
    io.observe(host);
    teardown.push(()=>io.disconnect());
  }
  if(frameStage && typeof MutationObserver!=='undefined'){
    const stageObserver=new MutationObserver(()=>{
      if(stageIsVisible()) requestBrainFrame();
      else if(rafHandle!==null){
        cancelAnimationFrame(rafHandle);
        rafHandle=null;
        lastFrame=0;
      }
    });
    stageObserver.observe(frameStage,{attributes:true,attributeFilter:['class','aria-hidden']});
    teardown.push(()=>stageObserver.disconnect());
  }

  function project(p,out){
    const X=p.x+p.ox, Y=p.y+p.oy, Z=p.z+p.oz;
    const x1=X*cosYaw - Z*sinYaw, z1=X*sinYaw + Z*cosYaw;
    const y1=Y*cosPitch - z1*sinPitch,  z2=Y*sinPitch + z1*cosPitch;
    const sc=1/(2.7 - z2*.62);
    out.x=cx + x1*scale*zoom*sc*1.55;
    out.y=cy - y1*scale*zoom*sc*1.55;
    out.z=z2;
    out.sc=sc;
  }

  function starPath(context,x,y,r,rot){
    context.beginPath();
    for(let i=0;i<8;i++){
      const rr=i%2===0?r:r*.32, a=rot+i*Math.PI/4;
      const px=x+Math.cos(a)*rr, py=y+Math.sin(a)*rr;
      i===0?context.moveTo(px,py):context.lineTo(px,py);
    }
    context.closePath();
  }
  function star4(x,y,r,rot){
    starPath(c,x,y,r,rot);
  }

  /* ---- stellar star paint -------------------------------------------------
     The previous paint was a filled square plus two thin rectangles forming a
     cross. It is cheap but it reads as a pixel, not a star, which is why the
     anatomy looked flat next to the galaxy rig.

     This draws the rig's actual stellar form: a four-point star body with a
     bright core and, on the brighter stars, diffraction spikes. The soft halo is
     the expensive part — the rig allocates two radial gradients per star per
     frame — so halos are rasterised once into a small offscreen sprite and
     blitted afterwards. At ~1,500 points that removes roughly 180,000 gradient
     allocations per second while producing a richer star. */

  const starCache=new Map();
  const STAR_BUCKETS=[.30,.42,.58,.78,1.02,1.32,1.70,2.2,2.85,3.7];
  function starBucket(rad){
    for(let i=0;i<STAR_BUCKETS.length;i++) if(rad<=STAR_BUCKETS[i]) return STAR_BUCKETS[i];
    return STAR_BUCKETS[STAR_BUCKETS.length-1];
  }

  /* The whole star — halo, four-point body and white core — is rasterised once
     per colour and size bucket, then blitted. Drawing it live cost four
     operations per point (gradient halo, star path, core arc, spikes); at 1,820
     points that measured 66 ms per frame. One drawImage per point is a single
     composite, and the sprite set is small: ~29 palette colours x 8 buckets. */
  function starSprite(col,bucket){
    const key=col[0]+'_'+col[1]+'_'+col[2]+'_'+bucket;
    let sprite=starCache.get(key);
    if(sprite) return sprite;

    const glow=bucket*2.9;
    const size=Math.max(6,Math.ceil(glow*2));
    sprite=document.createElement('canvas');
    sprite.width=size; sprite.height=size;
    const g=sprite.getContext('2d');
    if(g){
      const mid=size/2;
      const grad=g.createRadialGradient(mid,mid,0,mid,mid,mid);
      grad.addColorStop(0,`rgba(${col[0]},${col[1]},${col[2]},.46)`);
      grad.addColorStop(.30,`rgba(${col[0]},${col[1]},${col[2]},.16)`);
      grad.addColorStop(.64,`rgba(${col[0]},${col[1]},${col[2]},.04)`);
      grad.addColorStop(1,`rgba(${col[0]},${col[1]},${col[2]},0)`);
      g.fillStyle=grad; g.fillRect(0,0,size,size);

      const outer=bucket*1.34;
      g.fillStyle=`rgba(${col[0]},${col[1]},${col[2]},.95)`;
      starPath(g,mid,mid,outer,-Math.PI/2);
      g.fill();

      if(bucket>=.75){
        g.fillStyle='rgba(255,252,240,.92)';
        g.beginPath(); g.arc(mid,mid,Math.max(.3,bucket*.34),0,6.2832); g.fill();
      }
      if(bucket>=1.45){
        const reach=outer*3.0;
        g.strokeStyle=`rgba(${col[0]},${col[1]},${col[2]},.26)`;
        g.lineWidth=.55;
        g.beginPath();
        g.moveTo(mid-reach,mid); g.lineTo(mid+reach,mid);
        g.moveTo(mid,mid-reach*.72); g.lineTo(mid,mid+reach*.72);
        g.stroke();
      }
    }
    sprite.__glow=glow;
    starCache.set(key,sprite);
    return sprite;
  }

  function paintGalaxyStar(x,y,rad,alpha,col){
    const a=Math.min(.95,alpha*2.35);
    if(a<=.014) return;
    const bucket=starBucket(rad);
    const sprite=starSprite(col,bucket);
    const reach=sprite.__glow*(rad/bucket);
    const prev=c.globalAlpha;
    c.globalAlpha=prev*a;
    c.drawImage(sprite,x-reach,y-reach,reach*2,reach*2);
    c.globalAlpha=prev;
  }

  /* ---- storms / absorb / bloom ------------------------------------------ */
  function storm(power=1){
    energy=Math.min(1.6, energy+power);
    const n=Math.round(10+16*power);
    for(let i=0;i<n;i++) setTimeout(()=>firePulse(), Math.random()*420);
    // jelly shockwave
    for(const p of pts){
      const m=Math.hypot(p.x,p.y,p.z)||1;
      const k=.028*power;
      p.vx+=p.x/m*k*rnd(.4,1); p.vy+=p.y/m*k*rnd(.4,1); p.vz+=p.z/m*k*rnd(.4,1);
    }
  }
  function absorb(){ mode='absorb'; modeT=0; }
  /* the mind dissolves into tiny star glitter, drifts, then flows back together */
  function shatter(){
    if(mode==='shatter' || mode==='reform') return;
    mode='shatter'; modeT=0;
    pulses.length=0;
    energy=Math.min(1.6, energy+1);
    for(const p of pts){
      const m=Math.hypot(p.x,p.y,p.z)||1;
      const s=rnd(.055,.16);
      p.vx += p.x/m*s + rnd(-.045,.045);
      p.vy += p.y/m*s + rnd(-.045,.045) + .015;   // a little lift: glitter rises
      p.vz += p.z/m*s + rnd(-.045,.045);
    }
    for(let i=0;i<28;i++){
      const q=projected[(Math.random()*pts.length)|0];
      if(q) emitMote(null,q.x,q.y);
    }
  }
  function dispose(){
    if(disposed) return;
    disposed=true;
    if(rafHandle!==null){ cancelAnimationFrame(rafHandle); rafHandle=null; }
    if(typeof brainWatchdog!=='undefined') clearInterval(brainWatchdog);
    for(const undo of teardown){ try{ undo(); }catch(e){} }
    teardown.length=0;
    try{ canvas.width=0; canvas.height=0; }catch(e){}
    canvas.remove();
    if(window.nurStarBrain && window.nurStarBrain.dispose===dispose) delete window.nurStarBrain;
  }
  window.nurStarBrain={ storm, absorb, shatter, firePulse, dispose };

  // map the existing V4/V5 class rituals onto the brain:
  // single click ritual (.is-bursting) = dissolve into stardust and reform;
  // step-inside ritual (.is-entry-absorbing) = collapse then bloom.
  new MutationObserver(()=>{
    if(host.classList.contains('is-entry-absorbing')) absorb();
    else if(host.classList.contains('is-bursting') && mode==='live') shatter();
  }).observe(host,{attributes:true,attributeFilter:['class']});

  /* ---- interaction ------------------------------------------------------- */
  canvas.addEventListener('pointerdown',e=>{
    dragging=true; dragDist=0; lx=e.clientX; ly=e.clientY;
    host.classList.add('is-grabbing');
    try{canvas.setPointerCapture(e.pointerId)}catch{}
    e.stopPropagation();                       // keep the galaxy camera out of it
  });
  canvas.addEventListener('pointermove',e=>{
    const r=canvas.getBoundingClientRect();
    hoverX=e.clientX-r.left; hoverY=e.clientY-r.top;
    if(!dragging) return;
    const dx=e.clientX-lx, dy=e.clientY-ly;
    dragDist+=Math.abs(dx)+Math.abs(dy);
    lx=e.clientX; ly=e.clientY;
    vyaw = dx*.0032; vpitch = dy*.0026;
    yaw+=vyaw; pitch=Math.max(-1.1,Math.min(1.1,pitch+vpitch));
  });
  const endDrag=()=>{ if(!dragging) return; dragging=false; host.classList.remove('is-grabbing'); };
  canvas.addEventListener('pointerup',endDrag);
  canvas.addEventListener('pointercancel',endDrag);
  canvas.addEventListener('pointerleave',()=>{hoverX=hoverY=-1e4;});
  canvas.addEventListener('click',e=>{
    if(dragDist>7){ e.stopPropagation(); return; }  // a drag is not a click
    // the host's own V4 click handler adds .is-bursting -> observer -> shatter (stardust dissolve)
  });
  canvas.addEventListener('wheel',e=>{
    e.preventDefault();
    targetZoom=Math.max(.72,Math.min(1.5,targetZoom + (e.deltaY<0?.09:-.09)));
  },{passive:false});
  canvas.addEventListener('dblclick',e=>{ e.stopPropagation(); storm(1.4); });

  /* ---- ambient rhythms ---------------------------------------------------- */
  let ambientPulseTimer=null;
  if(!REDUCED){
    ambientPulseTimer=setInterval(()=>{
      if(mode==='live' && !document.hidden && stageIsVisible() && pulses.length<9) firePulse();
    }, 640);
    teardown.push(()=>clearInterval(ambientPulseTimer));
  }

  /* ---- render loop -------------------------------------------------------- */
  const projected=Array.from({length:pts.length},()=>({x:0,y:0,z:0,sc:0}));
  const depthOrder=Array.from({length:pts.length},(_,index)=>index);
  let depthSortFrame=0;
  function frame(now){
    rafHandle=null;
    if(disposed) return;
    if(document.hidden || !stageIsVisible()) return;
    rafHandle=requestAnimationFrame(frame);
    if(!host.isConnected || !onscreen) return;
    if(lastFrame&&now-lastFrame<MIN_FRAME_GAP) return;
    lastFrame=now;
    if(W<10){ resize(); if(W<10) return; }   // first visible frame after reveal

    breath += .012;
    energy *= .965;
    zoom += (targetZoom-zoom)*.08;
    if(!dragging && !REDUCED){
      vyaw += (.0022 - vyaw)*.02;              // settle back to idle spin
      vpitch *= .92;
      yaw += vyaw; pitch = Math.max(-1.1,Math.min(1.1,pitch+vpitch))*.996;
    }

    // mode cycles: absorb -> bloom (step-inside) / shatter -> reform (click)
    let squeeze=1, cohesion=1, springK=.06, dampK=.86;
    if(mode==='absorb'){
      modeT++; squeeze=1-Math.min(.5,modeT*.032);
      if(modeT>24){
        mode='bloom'; modeT=0;
        storm(1.5);
      }
    } else if(mode==='bloom'){
      modeT++; squeeze=.5+Math.min(.5,modeT*.05);
      if(modeT>34) mode='live';
    } else if(mode==='shatter'){
      // stardust phase: spring nearly off, glitter drifts free
      modeT++; springK=.0022; dampK=.986;
      cohesion=Math.max(0,1-modeT*.055);
      if(modeT>80){ mode='reform'; modeT=0; }
    } else if(mode==='reform'){
      // the mind flows back together
      modeT++; springK=.026; dampK=.885;
      cohesion=Math.min(1,modeT*.018);
      if(modeT>95) mode='live';
    }

    // jelly physics: spring back to true anatomy
    for(const p of pts){
      p.vx+=-springK*p.ox; p.vy+=-springK*p.oy; p.vz+=-springK*p.oz;
      p.vx*=dampK; p.vy*=dampK; p.vz*=dampK;
      p.ox+=p.vx; p.oy+=p.vy; p.oz+=p.vz;
    }

    c.clearRect(0,0,W,H);
    cosYaw=Math.cos(yaw); sinYaw=Math.sin(yaw);
    cosPitch=Math.cos(pitch); sinPitch=Math.sin(pitch);

    // project all points (with squeeze + gentle float)
    const bob = REDUCED?0:Math.sin(breath*.7)*.02;
    for(let i=0;i<pts.length;i++){
      const p=pts[i];
      const bx=p.x, by=p.y, bz=p.z;
      p.x*=squeeze; p.y=p.y*squeeze+bob; p.z*=squeeze;
      project(p,projected[i]);
      p.x=bx; p.y=by; p.z=bz;
    }

    // synapse web (depth-faded, warm; dissolves with the mind)
    if(cohesion>.06){
      c.lineWidth=.55;
      const edgeEnergy=(1+energy*.8)*cohesion;
      for(let layer=0;layer<2;layer++){
        c.strokeStyle=`rgba(255,214,140,${Math.min(.2,(layer?.105:.052)*edgeEnergy)})`;
        c.beginPath();
        for(const e of edges){
          const A=projected[e.a], B=projected[e.b];
          const front=(A.z+B.z)>0;
          if(front!==(layer===1)) continue;
          c.moveTo(A.x,A.y); c.lineTo(B.x,B.y);
        }
        c.stroke();
      }
    }

    // stars, back-to-front
    if(dragging||depthSortFrame===0) depthOrder.sort((a,b)=>projected[a].z-projected[b].z);
    depthSortFrame=(depthSortFrame+1)%3;
    for(const i of depthOrder){
      const p=pts[i], q=projected[i];
      const isDust=p.group==='dust';
      if(!REDUCED){ p.tw+=p.tws; if(!isDust) p.gl+=p.gls; }
      const shimmer=.5+.5*Math.sin(p.tw);
      // Glint is a pow(x,18) plus a second sine per point per frame. The dust
      // population is too small on screen for a specular flash to be visible, so
      // it skips both — that is 760 of 1,820 points paying nothing for an effect
      // nobody can see.
      const glint=(REDUCED||isDust)?0:Math.pow(.5+.5*Math.sin(p.gl),18);
      const twinkle=1-p.twa+p.twa*(.38+.62*shimmer);
      const flash=1+glint*p.gla;
      const lit=.42+.58*Math.max(0,Math.min(1,(q.z+ .9)/1.7));   // front-facing glow
      let a=(.32+.68*lit)*twinkle*flash*(1-p.dim)*(1+energy*.55);
      // hover ripple: nearby stars brighten and get pushed
      const hoverDx=q.x-hoverX, hoverDy=q.y-hoverY;
      const hoverDistance2=hoverDx*hoverDx+hoverDy*hoverDy;
      if(!isDust&&hoverX>-1000&&hoverDistance2<3364){
        const k=1-Math.sqrt(hoverDistance2)/58;
        a*=1+.9*k;
        p.vx+=(p.x)*.0016*k; p.vy+=(p.y)*.0016*k; p.vz+=(p.z)*.0016*k;
        if(Math.random()<.05*k) emitMote(p,q.x,q.y);
      }
      a=Math.min(1,a);
      // as stardust: finer grains, quicker sparkle
      const r=Math.max(.55,p.r*q.sc*2.5*zoom*(.62+.38*cohesion));
      const starR=r*(1+glint*.48);
      if(cohesion<1) p.tw+=p.tws*(1-cohesion)*1.6;
      const starCol=(p.prism&&!isDust)
        ?prismShift(p.col,p.prismPhase+now*p.prismSpeed+p.gl*.18,twinkle)
        :p.col;
      paintGalaxyStar(q.x,q.y,starR,a,starCol);
    }

    // travelling neural pulses
    for(let i=pulses.length-1;i>=0;i--){
      const pu=pulses[i];
      pu.t+=pu.speed;
      const seg=Math.floor(pu.t), f=pu.t-seg;
      if(seg>=pu.path.length-1){ pulses.splice(i,1); continue; }
      const A=projected[pu.path[seg]], B=projected[pu.path[seg+1]];
      const x=A.x+(B.x-A.x)*f, y=A.y+(B.y-A.y)*f;
      const [cr,cg,cb]=pu.col;
      // trail
      c.strokeStyle=`rgba(${cr},${cg},${cb},.5)`;
      c.lineWidth=1.1;
      c.beginPath(); c.moveTo(A.x,A.y); c.lineTo(x,y); c.stroke();
      // spark head
      const pg=c.createRadialGradient(x,y,0,x,y,7);
      pg.addColorStop(0,`rgba(255,252,232,.95)`);
      pg.addColorStop(.3,`rgba(${cr},${cg},${cb},.75)`);
      pg.addColorStop(1,'rgba(0,0,0,0)');
      c.fillStyle=pg; c.beginPath(); c.arc(x,y,7,0,Math.PI*2); c.fill();
    }

    // drifting glitter motes
    for(let i=motes.length-1;i>=0;i--){
      const m=motes[i];
      m.x+=m.vx; m.y+=m.vy; m.life--;
      if(m.life<=0){ motes.splice(i,1); continue; }
      const a=(m.life/m.max)*.8;
      const [cr,cg,cb]=m.col;
      c.fillStyle=`rgba(${cr},${cg},${cb},${a})`;
      star4(m.x,m.y,m.r+ .6,m.life*.2); c.fill();
    }

    // ambient sparkle emission from the surface
    if(!REDUCED && Math.random()<.30 && mode==='live'){
      const i=(Math.random()*pts.length)|0;
      const q=projected[i];
      if(q.z>-.2) emitMote(pts[i],q.x,q.y);
    }
  }
  requestBrainFrame();

  // The visibility test now reads real layout, which is correct but can be
  // false during mount: a stage that has not been laid out yet reports a
  // zero-size box. `requestBrainFrame` bails in that case and nothing restarts
  // it, so a single early false left this canvas permanently blank — which is
  // exactly how the galaxy used to fail before it gained the same guard.
  const brainWatchdog=setInterval(()=>{
    if(disposed){ clearInterval(brainWatchdog); return; }
    if(rafHandle===null && !document.hidden && stageIsVisible()) requestBrainFrame();
  },500);
})();
