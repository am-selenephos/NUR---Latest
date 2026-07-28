# Handoff — the galaxy renders in every environment I can build, and not on the founder's screen

Written for whoever picks this up next. Branch `codex/nur-full-completion-20260726`.
Everything below is measured, not inferred. Where I was wrong, I say so, because
four of my hypotheses were wrong and repeating them wastes the next day.

## The symptom

The founder opens the app and the background star field is absent. The star
brain (`#nur-brain-canvas`) renders correctly in the same screenshot — colourful,
detailed, clearly alive. Only the full-viewport field (`#space3d`) is missing.

Their screenshot is 2552×1412. Every measurement I take at that exact viewport
shows the field present.

## What is definitely NOT the cause

Each of these was a real hypothesis I acted on. Each is falsified by measurement.
Do not spend time on them again.

### Not a stale build on the server

```
listening:        127.0.0.1:4173 only. No 5173, no second worktree, no proxy.
served bundle:    cc00f44cf0c8…
local dist:       cc00f44cf0c8…   identical
```

### Not the service worker

The service worker *was* genuinely broken — cache-first against a constant cache
name (`nur-v197-shell-v2`), so the first copy of `/assets/v197-bridge.js` a
browser ever fetched was kept forever and no deploy could reach it. That is a
real production defect and it is fixed (network-first, versioned cache,
`skipWaiting` + `clients.claim`).

**But it is not this bug.** The founder reproduced the missing field in a private
window, which starts with no service worker and no cache.

### Not the GPU

I capture with `--enable-gpu --ignore-gpu-blocklist`; a normal browser does not.
Tested all three at 2552×1412:

| launch | lit px | particles | frameScheduled |
| --- | --- | --- | --- |
| `--enable-gpu --ignore-gpu-blocklist` | 612,673 | 3790 | true |
| default flags | 598,148 | 3736 | true |
| `--disable-gpu` | 598,463 | 3736 | true |

The field renders in all three, including software rendering.

### Not particle count, density or exposure

Two real bugs were found and fixed here, and both are genuinely closed:

- **Density was a fixed count.** 900 galaxy / 585 far / 165 dust / 48 super
  regardless of screen. Spread over 2552×1412 that is 44% of the density it has
  at 1600×1000. Now scales with viewport area, capped at 2.2×. Verified across 13
  viewports from 360×640 to 3840×2160: lit density holds at 67k–82k per 100k
  canvas pixels across a 30× area range.
- **The radius floor was in CSS pixels.** Lowered to `.34` to restore depth, a
  distant star on a large canvas fell below one device pixel and stopped
  rendering. Floor is expressed in device pixels now.

At the founder's exact viewport the runtime currently reports 3,859 particles
(galaxy 1980, far 1287, dust 363, super 106), 73,241 lit px per 100k,
`maxLuminance 255`, `shouldRender: true`, `frameScheduled: true`.

### Not the render loop dying

`shouldRender` and `frameScheduled` are both true in every capture. An earlier
genuine bug — the loop stopping during a stage transition with nothing to wake
it — is fixed with a 1s watchdog.

## The one fact that should drive the next investigation

**`#nur-brain-canvas` renders for the founder and `#space3d` does not, in the
same frame.** Same document, same runtime, same JavaScript. Whatever the cause
is, it discriminates between two canvases in one iframe.

Relevant differences between them:

| | `#space3d` | `#nur-brain-canvas` |
| --- | --- | --- |
| position | `fixed` | in normal flow |
| size | full viewport (2552×1412) | ~452×452 |
| z-index | 280 on universe, 0 on entry | auto |
| opacity | 0.96–1 | 1 |

`position: fixed` at full viewport size is the standout. It is the only property
that would behave differently under conditions my captures do not reproduce.

## Concrete next diagnostics, in order

1. **Get the founder's actual environment.** `chrome://version` and
   `chrome://gpu`, plus OS display scaling and browser zoom. 2552×1412 is not a
   standard panel size — it suggests fractional scaling, and a fractional
   `devicePixelRatio` combined with a `position: fixed` full-viewport canvas is
   the most plausible untested path.

2. **Have them run this in the console on the entry frame** and send the output.
   It answers in one shot whether the canvas is missing, empty, transparent,
   covered, or off-screen:

   ```js
   const c = document.querySelector('#space3d');
   const r = c.getBoundingClientRect(), s = getComputedStyle(c);
   const ctx = c.getContext('2d');
   const d = ctx.getImageData(0, 0, Math.min(c.width,600), Math.min(c.height,400)).data;
   let lit = 0; for (let i = 0; i < d.length; i += 4) if (d[i]+d[i+1]+d[i+2] > 30) lit++;
   console.log({
     dpr: devicePixelRatio, zoom: (outerWidth/innerWidth).toFixed(2),
     backing: [c.width, c.height], css: [r.width, r.height], at: [r.x, r.y],
     opacity: s.opacity, display: s.display, visibility: s.visibility,
     zIndex: s.zIndex, transform: s.transform, filter: s.filter,
     litPixels: lit,
     covering: document.elementFromPoint(innerWidth/2, innerHeight/3)?.className,
   });
   ```

   - `litPixels: 0` → the runtime is not painting on their machine; look at the
     galaxy loop, not CSS.
   - `litPixels > 0` but nothing visible → a compositing or stacking problem;
     look at `covering`, `opacity`, `zIndex`.
   - `backing` far from `css × dpr` → fractional-scaling sizing bug.

3. **Test fractional `deviceScaleFactor`.** Every capture used 1, 1.5, 2 or 3.
   Try 1.25, 1.75, 2.25 at 2552×1412. If the canvas backing store is computed
   with a rounding assumption, a fractional ratio is where it breaks.

4. **Test a second real browser on their machine.** Firefox and WebKit are
   entirely unproven here — every measurement in this session is Chromium.

## What I would not do next

Do not re-tune density, exposure, floors or particle counts. Those were real
bugs, they are fixed, and they are verified across 13 viewports. Changing them
again without first reproducing the founder's environment will move numbers that
are already correct and make the real cause harder to see. That mistake has
already been made several times in this branch.

## Measurement note that matters

**Do not use CDP screencast for frame rate.** It JPEG-encodes every frame and
above roughly 1280×800 the encoder, not the page, sets the ceiling. It read
8 FPS where a real trace read 25, and it read 16 FPS under a 6× CPU throttle
against 8 unthrottled — an application cannot speed up when the machine slows
down, and that impossibility is the tell.

Use `infra/scripts/measure-frame-rate.mjs`. Read `commits/s`: one Commit is one
composited frame. Current real figures are 21–33 FPS on desktop against a ≥55
target — that gap is real and unclosed.
