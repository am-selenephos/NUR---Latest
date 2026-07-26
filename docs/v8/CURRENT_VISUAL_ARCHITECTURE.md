# Current visual architecture — measured, not assumed

Branch `completion/nur-v5-full-pass` @ `902c31b`.
Canonical V197 SHA-256 `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`.

## 1. How the interface is actually assembled

`apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html` is 718,041 bytes but contains
only **10,637 bytes of code**. Everything else is two Base64 strings:

| Payload | Base64 chars | Decoded | Composition |
| --- | --- | --- | --- |
| `ENTRY_SOURCE_B64` | 172,120 | 129,089 | 90.5 KB CSS (70%), 29 KB JS, 9 KB markup |
| `UNIVERSE_SOURCE_B64` | 535,292 | 401,468 | 314 KB CSS (78%), 43.6 KB JS, 43.5 KB markup |

The shell decodes both on the main thread at boot and hands each to an `<iframe srcdoc>`.
Two full-viewport stages, `#nur-entry-stage` and `#nur-universe-stage`, are swapped by a
router in the shell. `window.NURConsolidated` exposes `verifySources`, `enterUniverse`,
`completeSignIn`, `showEntry`, `getStage`, `getSessionContext`.

**Base64 costs 176,855 bytes — 24% of the shipped file — in encoding alone**, and the decode
is a per-character loop over 707,412 characters before first paint.

## 2. The bridge

`src/main.ts` → `bootstrapV197Bridge()`. The bridge is nonvisual by contract: it verifies
source integrity, owns routing, binds actions, fetches the owner snapshot, hydrates V197 in
place, and renders adjunct surfaces. 21 modules, the largest being `v197Adjuncts.ts` (91 KB),
`v197Hydration.ts` (56 KB), `v197ApiClient.ts` (40 KB), `v197Bindings.ts` (41.5 KB).

Route handling splits in two:

- **Adjunct routes** (`/settings`, `/capsule/*`, `/consultations*`, `/community*`,
  `/projects*`, `/glow`, `/notifications`, `/universe/omega*`) — the bridge renders its own
  DOM into the universe document.
- **Canonical routes** (`/today`, `/talk`, `/journal`, `/plan`, `/systems`, `/universe/*`) —
  the bridge clicks the canonical nav and calls `renderWorldLens`, so V197's own markup stays
  the presentation.

## 3. The existing visual engine

`src/bridge/v43StarBrainRuntime.js` (18.9 KB) is injected as raw source into the iframe
document by `v197StarBrain.ts`, hash-pinned at
`ee34405b119b8f2d7b6a5b4b7fdedff2e6875f9bd7d472aff6ab5b8473b8d347`.

It mounts into whichever surface is active, resolved in this order:

1. `#page-today.active .orbit-star-zone > .f4-core`
2. `body.universe-edition #page-systems.active .universe-map-panel > .universe-master-star`
3. `body.universe-edition #page-universe-map.active .lens-map-master`
4. `#nur-front-v61 #f4-core`

Measured properties: **794 cortex nodes** on desktop (529 mobile), DPR capped at 1.1,
**2 `requestAnimationFrame` call sites, 0 `cancelAnimationFrame`**, 8 canvas listeners plus a
window `resize` listener, none removed.

Across the whole bridge: **4 `requestAnimationFrame`, 0 `cancelAnimationFrame`,
64 `addEventListener`, 6 `removeEventListener`.**

## 4. Control surface

`docs/release/v197-control-matrix.json` records **90 controls**:

| Classification | Count |
| --- | --- |
| LIVE_REAL | 73 |
| INTENTIONAL_LOCAL_ONLY | 8 |
| NOT_IMPLEMENTED_VISIBLE | 7 |
| BLOCKED_BY_EXTERNAL_PROVIDER | 2 |

The Systems surface already ships **seven canonical `.universe-system-node` buttons**
(Quiet Ambition, Public Resonance, Wealth Architecture, Embodied Edge, Relational Gravity,
Social Constellation, Neural Upgrade), and hydration adds `data-system-slug` and
`data-orbit-id` to them.

## 5. Complexity, separated

The directive is right that "not 3D" is not the same as "simple". Measured separately:

| Dimension | State | Evidence |
| --- | --- | --- |
| Product complexity | **High** | 90 controls, 34 surfaces, 30 Alembic revisions, RLS per entity |
| Interaction complexity | **High** | 73 live-real controls bound to real endpoints |
| Data complexity | **High** | Systems carry progress, formula, goals, blockers, next move, prediction with provenance |
| Visual complexity | **Moderate** | one canvas object plus conventional panel/grid language |
| Motion complexity | **Low** | ambient star motion; no route choreography, no scene continuity |
| Runtime complexity | **Poorly bounded** | 0 cancelAnimationFrame anywhere; listeners never removed |

The gap is therefore **motion and runtime discipline**, not product depth. The Systems page
already displays each System's percentage, `0 of 1 actions complete`, active goal count and
the verbatim formula `40% actions + 20% goals + 15% diagnostic + 15% returned outcomes +
10% Glow activity · blocker and missed-Return penalties`. Any cinematic layer must transform
that presentation, not restate it.
