# Systems candidate — FROZEN

Frozen 2026-07-26 by founder directive. No further hero-object polish until a global art direction is selected.

## Identity

```
branch : completion/nur-v5-full-pass
HEAD   : 902c31b67843ad2c755f8523b2f16e63d41abf41
canonical V197 sha256 : d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6  (UNCHANGED)
```

## Modified tracked files

```
 M apps/web/src/bridge/v197Bridge.ts
 M apps/web/src/bridge/v197Polish.ts
 M apps/web/src/bridge/v197StarBrain.ts
 M apps/web/src/bridge/v43StarBrainRuntime.js
 M apps/web/src/v197/phase1-host.test.ts
 M apps/web/src/v197/v43-star-brain-source.test.ts
 M docs/release/v197-control-matrix.json
```

## New files (visual runtime)

```
?? apps/web/e2e/v8-baseline-fps.spec.ts
?? apps/web/e2e/v8-cinematic-systems.spec.ts
?? apps/web/e2e/v9-ui-census.spec.ts
?? apps/web/src/styles/v197-cinematic-stage.css
?? apps/web/src/visual/
?? proof/v8-baseline/
?? proof/v8-candidate/
?? proof/v9-current-ui/
```

## Runtime source inventory

```
  109 apps/web/src/visual/DataBinding.ts
  163 apps/web/src/visual/MotionController.ts
  313 apps/web/src/visual/NURVisualRuntime.ts
  115 apps/web/src/visual/QualityTier.ts
  355 apps/web/src/visual/SceneOrchestrator.ts
  146 apps/web/src/visual/materials/SpriteAtlas.ts
  141 apps/web/src/visual/objects/DepthField.ts
  307 apps/web/src/visual/objects/NeuralCloud.ts
  348 apps/web/src/visual/scenes/SystemsScene.ts
  401 apps/web/src/visual/tests/visualRuntime.test.ts
 2398 total
```

## Rubric at freeze

11 of 14 categories pass — `docs/v8/CINEMATIC_QUALITY_RUBRIC.csv`.

Failing gates: **originality 3** (target ≥4), **camera choreography 2** (≥4),
**scene continuity 1** (≥4).

## Known defects carried into the freeze

| # | Defect | Note |
| --- | --- | --- |
| 1 | Hero reads as a structured star cluster, not an unmistakable brain silhouette | originality gate |
| 2 | No establishing shot, no route transition, no captured 20–30s sequence | camera gate |
| 3 | Only one scene exists; leaving Systems destroys the world | continuity gate |
| 4 | Desktop and mobile FPS unmeasured — headless harness caps rAF at 30, baseline identical | needs a headed run |
| 5 | Heap growth over 10 minutes unmeasured | not attempted |
| 6 | Mobile is a lower quality tier, not a separate composition | mobile art direction |

## What is proven and must survive any direction change

- one canvas owner, one cancellable RAF owner, deterministic teardown — **23 guard tests**
- `disposeV197StarBrain()` — the V43 engine can be stopped for the first time
  (the product previously contained **zero** `cancelAnimationFrame`)
- `SpriteAtlas` — glow rasterised once and blitted, replacing ~168,000 gradient
  allocations/second
- `NeuralCloud` — founder-approved anatomy with unit-tested geometry
- render-failure guard — a thrown frame no longer blanks the stage permanently
- honest data binding — 7/7 Systems, verbatim progress formula, hollow when no data

## Rollback

The stage is **off by default**; the product renders exactly as before with no action taken.

To remove the experiment entirely:

```bash
cd /home/nur/NUR-INTEGRATION-20260722
git checkout -- apps/web/src/bridge/v197Bridge.ts apps/web/src/bridge/v197Polish.ts \
                apps/web/src/bridge/v197StarBrain.ts apps/web/src/bridge/v43StarBrainRuntime.js \
                apps/web/src/v197/phase1-host.test.ts apps/web/src/v197/v43-star-brain-source.test.ts
rm -rf apps/web/src/visual apps/web/src/styles/v197-cinematic-stage.css \
       apps/web/e2e/v8-cinematic-systems.spec.ts apps/web/e2e/v8-baseline-fps.spec.ts
npm --prefix apps/web run typecheck && npm --prefix apps/web run test
```

Reverting `v43StarBrainRuntime.js` also reverts the hash pin in both test files, so those four
files must move together. Evidence under `proof/v8-*` and `docs/v8/` is kept regardless —
it is the record of why the direction changed.

Canonical V197 is untouched, so no rollback of the presentation layer is required.
