# NUR Final Closure Ledger - 2026-08-21

This ledger records the closure candidate on
`codex/nur-final-closure-20260820`. A source file, historical report, or mocked
success is not sufficient by itself. External provider, independent-review,
merge, main-CI, tag, and repository-rename gates remain explicit rather than
being represented as product PASS.

## Source authority

```text
repository: am-selenephos/NUR---Latest
baseline: 1c6f5f1e9f3380204f6809d2a78364e046e4908e
branch: codex/nur-final-closure-20260820
addendum sha256: 742f05c92ac3ff7815604c176713244fe9936dd31d79ca68a102d772299cd8d9
takeover sha256: 0288bee99a6169a3e053f234a525d459388d77cf1ea18741ab9d2264c6160035
```

## Implemented closure delta

| Area | Current closure |
| --- | --- |
| Contract truth | OpenAPI drift launcher works in local and CI environments; mutation-security matrix covers API mutations |
| Auth and ownership | Exact-email lookup migration, narrow auth RLS boundary, production-safe auth/account/password paths, and expanded RLS tests |
| Mind and Brain | V2 packet/result flow, richer context hydration, planner, simulator, independent critic, specialist routing, evaluation corpus, and bounded degradation |
| Agentend | Governed runtime dispatch, outbox/idempotency, worker readiness, retry successor UI, approval EDIT/raw JSON fallback, and verified-result tests |
| Learning | Prediction/outcome reconciliation, correction invalidation, belief and memory candidates, hardness signals, and held-out/shadow evaluation gate |
| Product surfaces | V197 control bindings, Talk semantics/capability/memory modes, project recovery, logout return, retired placeholder removal, and browser closure tests |
| Security and abuse | Expanded secret scan, HSTS in production, production demo-seed refusal, quota/rate-limit tests, mutation matrix, and dependency audit |
| Operations | Storage-hygiene service and schedule, backup/restore/drill hardening, recovery drill, SBOM freshness, release verification, and fresh-extract smoke |
| CI | Pinned actions, Chromium installation, intended two-project one-worker E2E lane, failure artifacts, OpenAPI and mutation gates |
| V197 law | Canonical V197 source hashes pass; no replacement React shell, second canvas owner, or direct browser-provider boundary was introduced |

## Candidate evidence

These receipts were produced from the closure worktree immediately before the
checkpoint commit. The pull-request CI run is the exact-head promotion proof.

| Command or receipt | Result |
| --- | --- |
| `apps/api/.venv/bin/ruff check apps/api/app apps/api/alembic` | PASS |
| `cd apps/api && .venv/bin/pytest -q` | PASS, 1,114 tests |
| `npm run web:typecheck` | PASS |
| `npm run web:test` | PASS, 125 tests in 25 files |
| `npm run web:build` | PASS |
| `npm run web:e2e:mocked` | PASS, 19 passed and 1 intentional mobile-evidence skip |
| changed headed/live browser sweep | PASS after canonical local stack boot; census rerun passed |
| `npm run mobile:typecheck` | PASS |
| `npm audit --audit-level=high` | PASS, 0 vulnerabilities |
| all `infra/tests/*.test.sh` contracts | PASS, 13 scripts |
| `npm run secret-scan` | PASS |
| `npm run release:naming-scan` | PASS |
| `npm run v197:integrity` | PASS |
| `npm run proof-hygiene` | PASS, 32 files and 0.2 MB |
| `npm run api:openapi-drift:test` | PASS, 3 tests |
| `npm run api:openapi-drift` | PASS, 144 client operations covered by 420 OpenAPI operations |
| `npm run api:mutation-security` | PASS |
| `git diff --check` | PASS |

## Honest remaining boundary

The addendum is not a final production release yet. Remaining work is grouped
in the adjacent completion assessment and includes route-wide proof gaps,
production email/billing/research providers, authorized production
backup/staging receipts, large Desktop Safari and human localization review,
independent review, exact-head CI, merge, main CI, tag, and repository rename.

## Current verdict

`NUR_PARTIAL`

The internally implemented candidate is substantially closed and locally
green, but `NUR_FULL_PASS` would be false until the remaining internal,
external, and promotion gates have their required evidence.
