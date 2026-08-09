# Source Authority Report

Audited against repository baseline: `7df3ade9a9dea495b84d25cc7660350941c1e1f8`

## Canonical presentation

| Artifact | SHA-256 | Status |
|---|---|---|
| `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html` | `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6` | current ratified host |
| `docs/reference/entry_decoded_v197.html` | `cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030` | current ratified Entry reference |
| `docs/reference/universe_decoded_v197.html` | `3cff07b31e8360e5ce793287298d66127c4f278705dc0f8e6abdfbe7e874dc40` | current ratified Universe reference |
| historical host | `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3` | superseded; do not restore as current |
| historical Entry reference | `49e2e72fb3adea405428789d9235dfc5ecb122f8dc1e17205d4fa05de64ecd97` | superseded historical evidence |
| historical Universe reference | `b80eb5198d6fd9088e999020bd1cf85e95af9a20fd4ab172cfb7d5726dbd5a3c` | superseded historical evidence |

`scripts/check-v197-integrity.ts`, invoked by `npm run v197:integrity` and the shell gate,
is the executable authority for all three current hashes. A PASS is commit-specific and must be
rerun on the candidate; this report does not substitute for that output.

## Production presentation path

`apps/web/vite.config.ts` serves the canonical host document for V197-native routes and adds exactly one nonvisual module loader before `</body>`. `apps/web/src/main.ts` starts the bridge. The visible Entry and Universe remain isolated full-viewport documents owned by canonical V197.

## Non-authoritative visual code

Legacy React routes/components and old V197-extracted CSS remain source history only. They are not loaded into the visible canonical iframe documents. No React `#root`, `ReactDOM`, `global.css`, or React geometry sheet is accepted as presentation evidence.

## Allowed Track A mutation

The bridge may:

- update established copy/data slots;
- add controls required for a persisted action inside an existing V197 chamber;
- bind canonical controls to owner-scoped APIs;
- add the single `nur-v197-track-a-premium-polish` corrective stylesheet at runtime.

The corrective layer does not alter the canonical file on disk and does not replace V197 DOM, star geometry, wordmark, palette, or typography.
