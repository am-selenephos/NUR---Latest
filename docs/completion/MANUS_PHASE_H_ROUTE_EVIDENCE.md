# Phase-H Route Evidence

**Repository:** `am-selenephos/NUR---Latest`
**Branch:** `completion/nur-fullstack-agentend-20260818`
**Baseline under test:** `094b050810d230d2731339555334cfc4637b5973` before this evidence commit.
**Method:** Read-only route verification plus browser-fixture hardening; no production success is claimed from mock-only tests.

## Current evidence

The canonical navigation suite passed **7/7** after making the fixed-owner fixture self-provisioning on a fresh database. The core Map, Orbit, and Timeline suite passed **28 tests**, with two concrete remaining failures: Map had no seeded confirmed edge for the explanation assertion, and Orbit had no seeded owner row for the list-table assertion. The remaining 17 tests were serially skipped after those failures, not independently disproven.

The owner-product suite passed **18 tests**, with four expected mobile skips and one Track-A visual-layout failure. The Track-A failure is a real premium-surface overlap detector reporting `Ambition / universe-field-readout` and `Connection / universe-map-legend`; it is not being suppressed.

The adjunct sweep passed the control-heavy and project portions, while authentication/setup-dependent full-interface, auth, capsule, community, landing, and SOL seeded-surface tests remained red in the current local environment. The primary causes observed were fixed demo-account/fixture assumptions, missing seeded relational data, and setup-dependent route boot failures. These remain route evidence gaps rather than production PASS claims.

The owner-product tests directly passed for Memory, Teach NUR consent gating, Billing safe checkout fallback, Capsules owner controls, Talk persistence and disabled-provider honesty, Agent policy/approval controls, Journal save/reload, Settings persistence, Project tabs/file picker, and the broad adjunct material-style audit.

## Route status interpretation

| Route family | Current interpretation | Evidence basis |
|---|---|---|
| Today, Talk, Journal, Plan, Systems | `PARTIAL` pending a clean combined fresh-session route run | Talk persistence, disabled-provider, Journal, Settings, and core navigation tests passed; full-interface setup remains red |
| Orbit | `PARTIAL` | Mount, shell, controls, and most surface tests passed; list row fixture is absent |
| Map | `PARTIAL` | Mount, shell, modes, server regions, candidate separation, and most surface tests passed; confirmed-edge fixture is absent |
| Timeline | `PASS-CANDIDATE` | All executed Timeline assertions passed after fixture hardening; independent skipped cases need a clean rerun after upstream suite failures are removed |
| Insights / Research | `PARTIAL` | Candidate and Omega/research code paths exist, but current full-interface/SOL seeded-surface setup is red |
| Agents | `PASS-CANDIDATE` | Owner policy, bounded workflow, approval binding, and real C5 verified-result browser proof passed |
| Memory | `PASS-CANDIDATE` | Owner-product Memory read/write test passed; full fresh-session route matrix remains pending |
| Projects | `PASS-CANDIDATE` | Project deliverables and control-matrix tests passed under route mocks |
| Capsules | `PARTIAL` | Owner-product create/grant/revoke controls passed; two-account real lifecycle remains red |
| Community | `PARTIAL` | Route code and bounded adjunct path exist; real room/message test remains red in current setup |
| Billing | `PASS-CANDIDATE` | Safe HTTPS checkout fallback test passed |
| Notifications / Localization | `HOLD-DEPENDENCY` | No independent complete route proof was established in this sweep |

## Release implication

Phase-H is **not yet a full PASS**. The next concrete closures are to seed stable owner-scoped relational fixtures for Map/Orbit and rerun the skipped core tests, fix the Track-A overlap, make the fresh-interface/auth fixtures deterministic, and add independent Notifications/Localization route proofs before declaring a route-complete SHA.
