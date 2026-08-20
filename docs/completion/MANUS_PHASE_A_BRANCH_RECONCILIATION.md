# Phase-A Candidate Branch Reconciliation

**Canonical base:** `origin/main` at `6b04918611c6edff9b20b76f0c7df2d950bf4d4d`  
**Candidate branch:** `origin/fix/v197-interactive-celestial-20260813` at `d9fb88e6c0dfdc2ee9d468d9c8dd614f5d8dd4d3`  
**Completion branch:** `completion/nur-fullstack-agentend-20260818`  
**Audit mode:** No blind merge. Each changed file is classified against current-main ownership and current route truth.

## Classification key

`ALREADY_PRESENT` means the change is already in canonical main and should not be ported. `SUPERSEDED` means the candidate change corrects an obsolete expectation or path and should be replaced by current canonical behavior rather than ported as implementation. `UNIQUE_PORT` means the candidate contains a behavior or test not present on main and eligible for selective integration after targeted verification. `CONFLICT` means the candidate change touches a contract or ownership boundary that must be reconciled before it can be ported. `STALE` means the candidate assumption conflicts with the current Addendum or six-System source of truth. `DEAD` means the change has no current owner or route. `PRIVATE_ONLY` means it is test/proof-only and does not change shipped runtime behavior.

| Candidate file | Classification | Decision and reason |
|---|---|---|
| `apps/web/src/bridge/v197Bridge.ts` | `UNIQUE_PORT` + `CONFLICT` | Dedicated Insights host and global search-commit cancellation are absent from main and useful, but route ownership must be reconciled with adjunct candidate Insights and snapshot hydration before porting. |
| `apps/web/src/bridge/v197CelestialRuntime.ts` | `UNIQUE_PORT` | Adds visibility-aware animation, independent galaxy drag, inertia, pointer fencing, blur cleanup, diagnostics, and interaction profiles. It changes runtime semantics and requires unit/browser verification. |
| `apps/web/src/bridge/v197Insights.ts` | `UNIQUE_PORT` + `CONFLICT` | Adds a real dedicated owner Insights surface, but must be reconciled with the existing `/universe/insights/candidates` adjunct and the actual `V197Insights` snapshot schema. |
| `apps/web/src/bridge/v197SearchInput.ts` | `UNIQUE_PORT` | New bounded debounce/focus/cancellation helper with no provider or persistence boundary. Candidate for early port with unit tests. |
| `apps/web/src/bridge/v197SurfaceHost.ts` | `UNIQUE_PORT` | Hides the page-level composer while a dedicated bridge-native surface owns the viewport; eligible after host ownership tests. |
| `apps/web/src/bridge/v197Map.ts` | `UNIQUE_PORT` | Search debounce, focus restoration, and route cancellation are safe local improvements; must preserve Map API and disabled guided actions. |
| `apps/web/src/bridge/v197Orbit.ts` | `UNIQUE_PORT` | Search debounce, focus restoration, and route cancellation are safe local improvements; must preserve Orbit ownership. |
| `apps/web/src/bridge/v197Timeline.ts` | `UNIQUE_PORT` | Search debounce, focus restoration, and route cancellation are safe local improvements; must preserve Timeline ownership. |
| `apps/web/src/styles/v197-cosmic-skin.css` | `UNIQUE_PORT` | Cursor/touch interaction styling supports the candidate runtime; review for mobile and reduced-motion regressions. |
| `apps/web/src/styles/v197-holographic.css` | `UNIQUE_PORT` | Removes a duplicate Journal visual prompt while retaining the DOM contract; verify accessibility and hydration behavior. |
| `apps/web/src/styles/v197-insights.css` | `UNIQUE_PORT` | Styles the candidate dedicated Insights surface; port only with the matching runtime surface. |
| `apps/web/e2e/full-interface.spec.ts` | `SUPERSEDED` + `PRIVATE_ONLY` | Changes obsolete Research/Community/Web Signals expectations to current collapsed-route behavior and adds Insights-root assertions. Retain only the assertions that match the final ownership decision. |
| `apps/web/e2e/surface-navigation.spec.ts` | `UNIQUE_PORT` + `PRIVATE_ONLY` | Adds dedicated Insights navigation and stale-search-remount regression coverage. Eligible after Insights and search helper are integrated. |
| `apps/web/e2e/universe-lenses.spec.ts` | `SUPERSEDED` + `PRIVATE_ONLY` | Removes obsolete live Research/Web Signals expectations and adds dedicated Insights assertions. Port only after route ownership is finalized. |
| `apps/web/e2e/v197-seven-spectrum-celestial.spec.ts` | `UNIQUE_PORT` + `PRIVATE_ONLY` | Adds galaxy drag/parallax/inertia and surface-switch disposal proof. Port after runtime unit/typecheck and browser verification. |
| `apps/web/e2e/v197-universe-lenses-forensic.spec.ts` | `SUPERSEDED` + `PRIVATE_ONLY` | Removes retired four-route expectations and adds active dedicated Insights proof. Requires final route decision. |
| `apps/web/src/v197/search-input-performance.test.ts` | `UNIQUE_PORT` + `PRIVATE_ONLY` | New unit regression proof for debounce, focus/selection preservation, and route cancellation. Eligible for test-first port. |
| `apps/web/src/v197/v43-star-brain-source.test.ts` | `UNIQUE_PORT` + `PRIVATE_ONLY` | Extends source-contract assertions for interaction diagnostics and deterministic disposal. Eligible after runtime port. |

## Public-safety result

`infra/scripts/secret-scan.sh` passed on the completion worktree with no OpenAI key, bearer token, or key-assignment pattern in scanned artifacts. The candidate diff contains no direct browser provider call, direct WebSocket/EventSource channel, Redis/Celery transport, duplicate React root, or second Three.js renderer. The only `#root` match in the candidate diff is a test assertion requiring that the legacy React root remain absent.

The candidate branch is therefore safe to inspect and selectively port, but it is not safe to merge wholesale. The main conflicts are route ownership for Insights versus the existing candidate adjunct and the route-family decision for Research, Community, Experts, and Web Signals. Those decisions belong in the Contract Truth phase.
