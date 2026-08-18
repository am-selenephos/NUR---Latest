# J1 / J7 / J8 Readiness and Browser Matrix Evidence

**Working branch:** `completion/nur-fullstack-agentend-20260818`

**Release-candidate implementation SHA:** `9cc7afb9dd6b8f20d2c92fb98999a1f23f9c56cc`

**Evidence state:** This note records the completed runtime and browser evidence for the immutable implementation candidate above. Documentation commits may advance the branch head, but every release-candidate reference in the completion packet points to this SHA. No canonical `main` changes were made.

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

The previously recorded supported Chromium desktop matrix completed with **17 passed and 1 skipped**; the skipped case is the intentionally unavailable live-provider path, and no provider success was fabricated. After the final candidate changes, the focused core-route, control, responsive, and Universe-lens rerun completed with **13 passed and 3 skipped**. The Timeline branch-width correction removed the only concrete Chromium lens-geometry failure.

## J7 Chromium-mobile matrix

The final supported Chromium-mobile run completed with **10 passed**. It covered the Track-A hydrated route, direct-host geometry and DOM ownership, responsive/accessibility contracts, reduced motion, runtime lifecycle, adaptive performance, and supported final mobile routes.

Track-A was corrected at current source boundaries rather than by weakening assertions. The authenticated proof enters `/systems` explicitly, filters visible System labels, asserts the current scrollable mobile-tab contract, and waits for `#nur-map-root[data-map-loaded="true"]`. The direct-host proof uses the canonical host document, compares geometry against the canonical baseline, and retains strict visibility, geometry, no-React-root, and no-global-CSS assertions.

## J8 WebKit-mobile matrix

The final WebKit-mobile HOLD route proof now completes with **1 passed** after converting product selectors to the canonical Universe iframe, supplying the authenticated snapshot/CSRF fixtures, and using the current Talk SSE, Omega, and Capsule contracts. The responsive/accessibility matrix remains **3 passed and 1 failed**: its single failure is a WebKit page closure during the reused viewport-matrix run.

The remaining responsive failure occurs after the product surface mounts, when WebKit closes the page during the viewport-matrix layout-settle operation; every required viewport loads and settles successfully in independent diagnostic tests, and Chromium passes the complete responsive matrix. Track-A hydrated/direct-host WebKit proofs remain green from the recorded matrix. This is retained as a browser-runtime boundary rather than converted into a false pass.

The remaining WebKit result is recorded as a **J8 partial/runtime-boundary hold**, not converted into a false pass. The final HOLD route proof’s stale iframe ownership, missing authenticated fixtures, obsolete Talk transport, Omega route fixtures, and current copy assertions were repaired without weakening its semantic assertions. The responsive matrix still closes one WebKit page during the reused viewport sequence; no source assertion was weakened to conceal it.

## Evidence commands

The principal commands were:

```bash
CI=1 pnpm exec playwright test --project=chromium-desktop --workers=1
CI=1 pnpm exec playwright test --project=chromium-mobile --workers=1
CI=1 pnpm exec playwright test e2e/final-webkit-mobile.spec.ts --project=webkit-mobile --workers=1
CI=1 pnpm exec playwright test e2e/v197-responsive-accessibility.spec.ts --project=webkit-mobile --workers=1
CI=1 pnpm exec playwright test e2e/track-a-mobile-webkit.spec.ts -g 'Track A runs hydrated' --project=webkit-mobile --workers=1
CI=1 pnpm exec playwright test e2e/track-a-mobile-webkit.spec.ts -g 'Track A direct host' --project=webkit-mobile --workers=1
```

The exact per-project logs are retained outside the repository for this session; this note records their pass/fail totals and semantic failure boundaries. All reported evidence is bound to implementation SHA `9cc7afb9dd6b8f20d2c92fb98999a1f23f9c56cc`. The final independent review packet must use this same SHA.

## Current truthful interpretation

J1 is **PASS-CANDIDATE** locally with the actual runtime configuration. J7 is **PASS-CANDIDATE** for the completed Chromium desktop/mobile matrix. J8 remains **PARTIAL** because the responsive WebKit viewport matrix still has one browser page-closure failure, despite the green final HOLD route and isolated Track-A/direct-host proofs. The branch therefore cannot claim `NUR_FULL_PASS` until the remaining held gates, including protected-main authority, live provider access, definitive CI, independent review, and the WebKit runtime boundary, are resolved.
