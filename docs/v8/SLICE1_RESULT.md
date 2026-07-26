# Slice 1 — Systems / Laniakea flagship: **STILL NOT ACCEPTED**

Branch `completion/nur-v5-full-pass` @ `902c31b`. Canonical SHA-256 unchanged:
`d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`.
Evidence: `proof/v8-baseline/`, `proof/v8-candidate/`, `docs/v8/CINEMATIC_QUALITY_RUBRIC.csv`.

Round 1 failed on architecture. Round 2 fixed the architecture and **failed on the thing that
actually matters** — it looks worse than what ships today.

## Round 2: what was fixed

| Defect | Round 1 | Round 2 | How |
| --- | --- | --- | --- |
| D1 third canvas | 3 canvases, legacy loop uncancellable | **2** (mine + canonical `#space3d`) | `dispose()` added to the V43 runtime; `disposeV197StarBrain()` hands the surface over and `teardown` restores it |
| D2 duplicated telemetry | figures painted twice | **0 duplicated pixels** | telemetry is now screen-reader-only; canonical already renders the visible figures |
| D3 1 of 7 Systems bound | 1 | **7 of 7** | hydration lands after mount, so a MutationObserver re-binds; proven in `binding-diagnostic.json` |
| D4 29.9 FPS | attributed to the candidate | **not attributable** | the baseline measures **identically** — see below |

## D4 was a measurement error on my part

Round 1 reported 29.9 FPS as a candidate failure. Measuring the shipping product with the
stage disabled gives:

| | baseline (stage off) | candidate (stage on) |
| --- | --- | --- |
| median frame | 33.4 ms | 33.4 ms |
| p95 frame | 50.1 ms | 50.1 ms |
| median FPS | **29.9** | **29.9** |
| canvases | 2 | 2 |

Identical to two decimal places. The 30 FPS is the **headless Playwright harness capping
rAF**, not the scene. A headed run on the founder machine is still required before any real
FPS claim is made. Recorded as unmeasured rather than passed.

Separately: the legacy runtime throttles itself with `MIN_FRAME_GAP = MOBILE ? 40 : 30`, an
intentional ~33 FPS cap inside the engine. That is a design choice in the existing product, not
a defect introduced here.

## Why it is still not accepted

Put the two stills side by side — `proof/v8-baseline/systems-1920x1080.png` against
`proof/v8-candidate/systems-1920x1080.png`.

**The baseline has a brain.** A dense, authored, brain-shaped particle mass, recognisable in
silhouette, sitting exactly where the composition needs weight.

**The candidate has a star field.** Radial tethers, a soft core, scattered points. It is
architecturally correct and visually poorer. The directive's own words condemn it: *"no uniform
random star soup"*, *"never reducible to a stock primitive"*.

Rubric result — `docs/v8/CINEMATIC_QUALITY_RUBRIC.csv`:

| Gate category | Required | Candidate | |
| --- | --- | --- | --- |
| originality | ≥4 | **2** | FAIL |
| depth | ≥4 | **2** | FAIL |
| scene_continuity | ≥4 | **1** | FAIL |
| nur_identity | ≥4 | **2** | FAIL |
| signature_silhouette | ≥3 | **1** | FAIL |
| particle_behaviour | ≥3 | **2** | FAIL |
| material_quality | ≥3 | **2** | FAIL |
| camera_choreography | ≥3 | **2** | FAIL |
| mobile_art_direction | ≥3 | **2** | FAIL |

Passing: data_meaning 4, interaction_quality 4, performance_discipline 4,
accessibility_equivalence 4, typographic_direction 4.

**5 of 14 categories pass.** Four of the five gate categories are below threshold. Under the
directive's own rule this cannot be recommended, and I am not recommending it.

The honest summary: I built a correct runtime and put a weaker picture inside it.

## What is genuinely won and must not be thrown away

- The V43 engine can now be **stopped**. Before this change nothing in NUR could stop it — 0
  `cancelAnimationFrame` in the entire product. Its anatomy is byte-identical; the diff is 25
  lines, all lifecycle, verified line by line.
- One canvas owner, one cancellable loop, deterministic teardown, listener registry — 18 guard
  tests plus in-browser teardown proof.
- `SpriteAtlas`: glow rasterised once and blitted, replacing per-star `createRadialGradient`
  (~168,000 allocations/second in the current engines).
- Quality tiers measured from the device and corrected from real frame cost.
- Honest data binding — 7/7 Systems, verbatim progress formula, hollow rendering for
  no-data, arcs only where `orbit_id` genuinely matches.

Cost: **315.56 → 341.51 kB raw, 80.43 → 89.04 kB gzip (+8.61 kB), no new dependency.**
90/90 controls intact, 82/82 unit tests, typecheck clean, build green, canonical hash unchanged.

## Two hash pins were moved, deliberately

`src/v197/v43-star-brain-source.test.ts` and `src/v197/phase1-host.test.ts` both pinned the
runtime at `ee34405b…`. Adding the lifecycle moved it to `4d89149a…`. Both were updated on
purpose, every anatomy assertion was kept and still passes, and a new test now asserts the
runtime can release its surface. The previously rejected
`applyV197StarBrainLifecycleProfile` approach remains rejected.

## Next exact action

Port the V43 brain anatomy — cortex/cerebellum/brainstem point cloud, 794 nodes — into the new
sprite pipeline as the scene's hero object, so the signature silhouette returns **and** the
lifecycle discipline is kept. Then add near/middle/far fields for real depth, and a headed FPS
measurement. Only after originality, depth and NUR identity clear 4 should Slice 2 begin.

Stage remains **off by default** (`localStorage["nur.visual.stage"] = "on"` to compare).
