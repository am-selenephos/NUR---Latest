# J1 / J7 / J8 Readiness and Browser Matrix Evidence

**Working branch:** `completion/nur-fullstack-agentend-20260818`

**Evidence state:** This note records the completed pre-freeze runtime and browser evidence. The final candidate SHA and independent-review verdict are recorded separately after the final documentation commit. No canonical `main` changes were made.

## J1 readiness investigation

The readiness endpoint is implemented in `apps/api/app/api/health.py`. `/readyz` checks a live `SELECT 1` through the configured SQLAlchemy sessionmaker and a live Redis `PING`; it returns HTTP 200 only when both checks are `ok`. The earlier port-8099 failure was an environment/configuration mismatch: `infra/scripts/boot-smoke.sh` defaults to `postgresql+asyncpg://nur_app:change_me@localhost:5432/nur`, while the working local runtime uses `postgresql+asyncpg://nur_app:test_app_pw@localhost:5432/nur_b6` and `redis://localhost:6379/0`.

The corrected smoke command was:

```bash
DATABASE_URL='postgresql+asyncpg://nur_app:test_app_pw@localhost:5432/nur_b6' \
REDIS_URL='redis://localhost:6379/0' \
NUR_SMOKE_PORT=8099 \
bash infra/scripts/boot-smoke.sh
```

The corrected run passed: `/readyz` returned 200, `/healthz` returned 200, `/metrics` returned 200, and the smoke process exited on SIGTERM within the 15-second deadline with `rc=143`. This is distinct from the unavailable Docker executable and the separate live-provider hold.

## J7 Chromium desktop matrix

The final supported Chromium desktop run completed with **17 passed and 1 skipped**. The skipped case is the intentionally unavailable live-provider path; no provider success was fabricated. The corrected Entry forensic selector and unauthenticated Entry fixture preserved the strict nested star-seal and glass-material assertions.

## J7 Chromium-mobile matrix

The final supported Chromium-mobile run completed with **10 passed**. It covered the Track-A hydrated route, direct-host geometry and DOM ownership, responsive/accessibility contracts, reduced motion, runtime lifecycle, adaptive performance, and supported final mobile routes.

Track-A was corrected at current source boundaries rather than by weakening assertions. The authenticated proof enters `/systems` explicitly, filters visible System labels, asserts the current scrollable mobile-tab contract, and waits for `#nur-map-root[data-map-loaded="true"]`. The direct-host proof uses the canonical host document, compares geometry against the canonical baseline, and retains strict visibility, geometry, no-React-root, and no-global-CSS assertions.

## J8 WebKit-mobile matrix

The WebKit binary and reported host dependencies were installed, and the final supported WebKit-mobile matrix was executed. It produced **7 passed, 2 flaky retry-only results, and 2 failed tests**.

The two failed tests were the final HOLD route proof, which did not find the legacy top-level `#page-systems` selector after `/systems`, and the first responsive viewport proof, which encountered the same iframe/stage boundary followed by a WebKit page crash on retry. The adaptive 44px-target proof and the long-label responsive proof each passed on retry; the reduced-motion, runtime lifecycle, Track-A, direct-host, and remaining responsive proofs passed. The isolated Track-A hydrated and direct-host proofs passed on both Chromium mobile and WebKit mobile.

The WebKit failures are recorded as a **J8 partial/runtime-boundary hold**, not converted into false passes. The final HOLD proof still targets a stale host-page selector rather than the canonical Universe iframe, while the responsive retry includes a browser page crash. No source assertion was weakened to conceal either result.

## Evidence commands

The principal commands were:

```bash
CI=1 pnpm exec playwright test --project=chromium-desktop --workers=1
CI=1 pnpm exec playwright test --project=chromium-mobile --workers=1
CI=1 pnpm exec playwright test --project=webkit-mobile --workers=1
CI=1 pnpm exec playwright test e2e/track-a-mobile-webkit.spec.ts -g 'Track A runs hydrated' --project=webkit-mobile --workers=1
CI=1 pnpm exec playwright test e2e/track-a-mobile-webkit.spec.ts -g 'Track A direct host' --project=webkit-mobile --workers=1
```

The exact per-project logs are retained outside the repository for this session; this note records their pass/fail totals and the semantic failure boundaries. The final independent review packet must bind these results to one exact release-candidate SHA.

## Current truthful interpretation

J1 is **PASS-CANDIDATE** locally with the actual runtime configuration. J7 is **PASS-CANDIDATE** for the completed Chromium desktop/mobile matrix. J8 remains **PARTIAL** because the complete WebKit-mobile matrix has two failed tests and two retry-only flaky results, despite green isolated Track-A and direct-host proofs. The branch therefore cannot claim `NUR_FULL_PASS` until the remaining held gates, including protected-main authority, live provider access, definitive CI, independent review, and the WebKit matrix boundary, are resolved.
