# V197 Parity Inventory - Phase 1

Status: `PHASE_1_PASS` candidate only. This is not a full-product acceptance.

## Immutable source contract

- Canonical source: `/home/nur/Downloads/NUR_V197_CHECKBOX_TICK_RESTORED.html`
- Served copy: `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`
- Canonical host SHA-256: `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`
- Decoded entry SHA-256: `cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030`
- Decoded universe SHA-256: `3cff07b31e8360e5ce793287298d66127c4f278705dc0f8e6abdfbe7e874dc40`
- Integrity command: `npm run v197:integrity`

The canonical host and both decoded documents are byte-checked. No Phase 1 code edits the canonical V197 file.

## Presentation ownership

| Surface | Phase 1 status | Evidence |
|---|---|---|
| V197 entry document | `IMPLEMENTED` | canonical nested `srcdoc` document |
| V197 universe document | `IMPLEMENTED` | canonical nested `srcdoc` document |
| Product route response | `IMPLEMENTED` | exact canonical host plus deterministic PWA metadata, fail-closed pre-srcdoc performance bootstrap, and one nonvisual external bridge loader |
| V197 `iframe` / `srcdoc` stages | `IMPLEMENTED` | canonical entry and universe stage documents remain V197-owned |
| Visible React root | `NOT_PRESENT` | no `#root` in route host or V197 frames |
| React geometry CSS | `NOT_LOADED` | route host does not load `global.css` |
| React visual routes/components | `BYPASSED` | `src/main.ts` starts only `bootstrapV197Bridge`; product routes have no `#root` |
| Read-only owner hydration | `WIRED` | existing V197 count, boundary, and context text slots only |

## Existing V197-native routes

| Route | V197 behavior in Phase 1 | Status |
|---|---|---|
| `/`, `/auth`, `/onboarding` | canonical V197 entry; source-local authentication submission is blocked with an honest status message | `HONEST_DISABLED` for auth persistence |
| `/today`, `/talk`, `/journal`, `/plan`, `/systems`, `/universe` | canonical V197 universe page switch; no write endpoint is called | `WIRED_READ_ONLY` |
| `/universe/map`, `/universe/orbits`, `/universe/timeline`, `/universe/insights` | canonical V197 world focus and outer URL synchronization | `WIRED_READ_ONLY` |
| `/universe/research`, `/universe/community`, `/universe/web-signals` | canonical V197 world focus and outer URL synchronization; source-local staging is blocked | `WIRED_READ_ONLY` |
| `/settings`, `/capsule/:id`, `/universe/omega*` | same V197 host plus bridge-owned plain semantic adjunct chamber; no React root/CSS | `WIRED` |

The default Systems/Universe route deliberately does not programmatically click V197's `Universe` tab because the canonical handler invokes `scrollIntoView`. Leaving the source default intact preserves its initial mobile viewport. Product-route HTML is deterministically composed from the exact canonical static host with PWA metadata, the fail-closed pre-srcdoc performance bootstrap, and one appended nonvisual bridge-loader tag. The static `/v197/` file remains exact and hash-verified.

## Native control law

| Control class | Phase 1 behavior | Status |
|---|---|---|
| `[data-page]` | canonical page handler plus outer history synchronization | `WIRED_READ_ONLY` |
| `[data-world-focus]`, `[data-world-tab]` | canonical world handler plus outer history synchronization | `WIRED_READ_ONLY` |
| `[data-system]`, native visual tabs, source map nodes | V197-local visual exploration only; no server mutation claim | `SOURCE_NATIVE_VISUAL_ONLY` |
| send/save/outcome/scope/research controls | capture-blocked before source-local fake persistence; V197's own toast says nothing was saved | `HONEST_DISABLED` |
| Enter on write-capable V197 inputs | capture-blocked with the same native toast | `HONEST_DISABLED` |
| entry signup/signin submit and source-local return | capture-blocked with V197's existing entry status slot | `HONEST_DISABLED` |

## Historical Phase 1 boundary

- no real auth binding;
- no write API bindings;
- no Talk streaming, OpenAI, research provider, or community provider changes;
- Capsule, Settings, and Omega were outside the original rescue checkpoint. They are now implemented as V197-native bridge adjuncts without altering the checkpointed canonical bytes;
- no new migrations or backend changes;
- no React visual rebuild.

The approved contracts under `docs/v197-adjuncts/` are implemented by `apps/web/src/bridge/v197Adjuncts.ts`. Desktop, Chromium mobile, and official-container WebKit E2E prove route/data/control behavior and no visible React root.

## Phase 1 proof

- `apps/web/e2e/v197-host-parity.spec.ts`
- `proof/v197-phase1/chromium-desktop-*.png`
- `proof/v197-phase1/chromium-mobile-*.png`
- `proof/v197-phase1/webkit-mobile-*.png`
- real WebKit run: official `mcr.microsoft.com/playwright:v1.61.1-jammy` image

### WebKit source-runtime note

V197's own `.universe-insight-panel` contains a flex child with `margin-top:auto`. Independent WebKit `srcdoc` runtimes can allocate that card's below-fold free height differently even when their viewport, loaded fonts, source bytes, computed V197 styles, map bounds, and insight anchor are identical. Phase 1 does not override that source-owned behavior. The parity test therefore asserts full map bounds, the insight panel's visible anchor/width, its computed style contract, source hashes, exact response composition, and no React/geometry stylesheet; it records the intrinsic card height in the evidence attachment rather than attributing it to the bridge.
