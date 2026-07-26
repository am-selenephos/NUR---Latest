# NUR complete UI audit — measured census

Branch `completion/nur-v5-full-pass` @ `902c31b`. Captured 2026-07-26 against the live seeded
owner (`owner@nur.app`) on the real running application, not mocks.

- **21 routes × 2 viewports = 42 records**, plus the signed-out entry at both viewports
- **44 screenshots** in `proof/v9-current-ui/`
- raw metrics: `proof/v9-current-ui/census.json`, `census.csv`
- census table: `docs/v9/CURRENT_UI_SCREEN_CENSUS.csv`
- findings: `docs/v9/NUR_COMPLETE_UI_FLAW_LEDGER.csv`

Every number below was measured in the browser. Nothing here is an impression.

## Coverage — and what is still missing

Captured: Today, Talk, Journal, Plan, Systems, Universe, Map, Orbits, Timeline, Insights,
Research, Web Signals, Community lens, Community, Consultations, Projects, Glow, Notifications,
Settings, Omega, Omega review — populated state, desktop and mobile, plus signed-out entry.

**Not yet captured, and therefore not audited:** signup, onboarding, new-empty-account, loading,
validation error, provider disabled, offline, timeout, cancelled, permission denied,
cross-owner rejected, mobile-keyboard-open, reduced motion, RTL, long strings, Rooms, Group NUR,
files, agents, Capsules, billing, security, export/delete, Neural Simulation Lab. That is a
larger surface than what was captured. The audit is a first pass, not the complete census the
directive asks for.

## The most serious finding

**F001 — six Universe lenses render the same page.**

| route | controls | cards | headings | characters | Δ text vs /systems |
| --- | --- | --- | --- | --- | --- |
| /systems | 92 | 17 | H1>H2×6 | 5,163 | — |
| /universe | 92 | 17 | H1>H2×6 | 5,163 | **+0** |
| /universe/map | 92 | 17 | H1>H2×6 | 5,201 | +38 |
| /universe/orbits | 92 | 17 | H1>H2×6 | 5,206 | +43 |
| /universe/timeline | 92 | 17 | H1>H2×6 | 5,210 | +47 |
| /universe/web-signals | 92 | 17 | H1>H2×6 | 5,205 | +42 |
| /universe/research | 92 | 17 | H1>H2×6 | 5,241 | +78 |
| /universe/community | 92 | 17 | H1>H2×6 | 5,254 | +91 |

Identical control count, identical card count, identical heading structure. The on-screen text
differs by **38–91 characters out of 5,163 — under 2%**.

`/universe` is byte-identical to `/systems`.

These are six named navigation destinations. A user who visits Map, then Orbits, then Timeline,
then Research, then Web Signals sees effectively one screen five times. No amount of cinematic
treatment on the Systems scene fixes this, and adding a hero object to a page that six routes
share would spread the same undifferentiated screen more convincingly.

This reframes the cinematic mission: **the problem is not that Systems lacks a hero object. It
is that six routes have no identity of their own.**

## Systematic findings across every route

| Finding | Measurement | Severity |
| --- | --- | --- |
| Controls below 44×44 | 62 of 92 desktop; 19 of 70 mobile | P1 |
| Text below 12px | 40–75 elements per route; Omega review 75 | P1 |
| Two H1 elements | 8 adjunct routes: `H1>H2×6>H1>H2×5` | P1 |
| Permanently disabled controls | 14 on every universe route, 16 on Settings | P1 |
| Unexplained 401 | one, during an authenticated session | P1 |
| Equal-weight card containers | 17–22 per route | P2 |
| Mobile recomposition | proportional trim only — Omega review keeps 113 of 135 controls | P2 |

**10 flaws: 1 P0, 5 P1, 4 P2.**

## What is genuinely good, measured

- **Console is nearly silent** — one 401 across 42 authenticated route loads. For an
  application of this size that is a strong signal.
- **Heading structure is present and consistent** on Tier A/B routes: exactly one H1 followed
  by H2 sections.
- **Text volume is proportionate to purpose** — Journal 1,456 characters, Talk 6,783,
  Omega review 11,614. Density tracks the job rather than being uniformly heavy.
- **Real data everywhere.** Every populated surface rendered the seeded owner's actual figures;
  no placeholder or lorem content appeared on any of the 21 routes.
- **Mobile does trim.** Today drops 50% of its text on a phone. The problem is that the trim is
  proportional rather than a recomposition, not that mobile was ignored.

## What this means for the cinematic direction

The Systems slice has been iterating on making one surface beautiful. The census says the
larger defect is **differentiation**: six routes that look identical, an adjunct language of
17–22 equal cards applied uniformly regardless of tier, and telemetry too small to read on the
surfaces that carry the most trust.

Recommended order, revised from evidence:

1. **F001 first.** Give each Universe lens its own primary layer. Until a lens owns its screen,
   Slice 1's scene continuity score cannot rise above 1 — there is nothing to be continuous
   *between*.
2. **F004 and F002** next: one H1 per route, and a minimum-target token. Both are global,
   cheap, and unblock the accessibility gates.
3. **F003**: a floor in the type scale. Provenance is NUR's trust surface and is currently its
   least readable text.
4. Only then return to hero-object polish.

## Honest limits of this audit

- One browser (Chromium), two viewports, one account state.
- No RTL, reduced-motion, offline, error or empty-state capture yet.
- Colour contrast was not measured — the checks here are size, structure and density only.
- No screen-reader pass; the accessibility findings are structural inference from the DOM.
- The 401 is recorded but not attributed to a request.

None of these gaps are closed, and the audit should not be cited as complete until they are.

---

## State census — partial, and why it stopped

Run 2026-07-26, `apps/web/e2e/v9-state-census.spec.ts`. **Failed after 15 minutes at the
offline step.** 5 of 13 states captured before the hang:

| State | Captured | Method |
| --- | --- | --- |
| signed-out entry (desktop) | yes | real first visit |
| signed-out entry (mobile) | yes | real first visit |
| signup form | yes | real onboarding surface |
| sign-in validation error | yes | **real rejected credential**, not a mocked error |
| settings populated | yes | authenticated owner |
| offline | **no** | hung here |
| permission denied, reduced motion, RTL, long strings, mobile keyboard | no | never reached |

**Cause, from the trace:**

```
Test timeout of 900000ms exceeded.
Error: locator.evaluate: waiting for
  locator('#nur-universe-stage').contentFrame().locator('body')
```

The offline step calls `context.setOffline(true)` and then measures *inside* the universe
iframe. With the network disabled the frame cannot resolve, and `locator.evaluate` has no
bounded timeout — so it waited out the entire 15-minute test budget instead of failing fast.

This is a defect in my harness, not in NUR. The offline state is exactly the case where the
iframe is unreachable, so it must be captured at page level with an explicit timeout.

**Fix before re-running:** give `measure()` a bounded `timeout` and fall back to a page-level
screenshot when the universe frame does not resolve; capture offline and permission-denied at
page scope only.

Until that run completes, **the census remains incomplete** — 21 routes at populated state plus
5 states. The directive's required set is not represented and this audit must not be cited as
finished.
