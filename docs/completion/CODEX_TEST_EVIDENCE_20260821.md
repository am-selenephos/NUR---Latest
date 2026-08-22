# NUR Test Evidence - 2026-08-21

Evidence is accumulated during closure and rebound to the final exact SHA
before promotion.

| Command | Environment | SHA | Result | Count/runtime | Artifact or note |
| --- | --- | --- | --- | --- | --- |
| `.venv/bin/pytest -q app/tests/test_brain_semantic_addendum.py app/tests/test_addendum_dg_contracts.py app/tests/test_mind_brain_capability_closure.py app/tests/test_omega.py app/tests/test_intelligence_contracts.py app/tests/test_outcome_learning_loop.py app/tests/test_beliefs_attention_phase3.py` | local PostgreSQL; API venv | working tree on `633acc9` | PASS | 74 passed, 14.94s | cognitive authority/research/evaluation regression |
| `.venv/bin/ruff check <changed Python files>` | API venv | working tree on `633acc9` | PASS | all checks passed | changed Python boundary |
| `npm --workspace apps/web run test -- --run src/v197/phase1-host.test.ts` | local Node | working tree on `633acc9` | PASS | 4 passed, 0 failed | production host emits canonical `index.html` |
| `bash infra/tests/production-web-serving.test.sh` | local shell | working tree on `633acc9` | PASS | contract passed | static Nginx topology and same-origin proxy contract |
| `npm run web:build` | local Node/Vite | working tree on `633acc9` | PASS | 51 modules; `dist/index.html` 724.12 kB; bridge 1,198.71 kB | production static output |
| `docker build --network host ... -t nur-web:closure .` | Docker  local-only DNS workaround | working tree on `633acc9` | PASS | image `2ac43eac5b2a` | host networking was not committed |
| `docker run ... nur-web:closure` plus HTTP probes | isolated container at `127.0.0.1:15173` | working tree on `633acc9` | PASS | `/universe/map` 200 canonical V197; bridge 200 immutable; retired route 302 relative | production runtime proof |
| `docker run ... nginx:1.30.4-alpine nginx -t` | isolated Nginx container | working tree on `633acc9` | PASS | syntax successful | `api` bound to loopback only for syntax resolution |
| `bash infra/tests/cold-boot-compose.test.sh` | local shell | working tree on `633acc9` | PASS | contract passed | roles/database/health topology |
| `docker compose --profile full config --quiet` | Docker Compose | working tree on `633acc9` | PASS | configuration valid | full topology parse |
| isolated `nurclosure` Compose cold boot, HTTP probes, shutdown and restart | fresh named volume; ports 55432/56379/58000/55173 | working tree on `633acc9` | PASS | six services healthy; migration head `0060_narrow_auth_rls_boundary`; worker ping; Beat dispatch; four HTTP 200 probes; shutdown 3.316s; persisted-volume restart healthy | PostgreSQL 16.14, Redis 7.4.9, Python 3.12.13, Celery 5.6.3, Nginx 1.30.4 |
| `npm run web:typecheck` | local Node | working tree on `633acc9` | PASS | `tsc --noEmit` | includes production and real-stack Playwright configuration |
| real-stack B6 Chromium desktop | production Nginx, FastAPI, PostgreSQL, Redis | working tree on `633acc9` | PASS | 1 passed, 8.5s | genuine signup, Journal mutation, API read, reload and V197 rehydrate |
| real-stack C1 + C5 Chromium desktop | production Nginx, FastAPI, PostgreSQL, Redis, Celery worker | working tree on `633acc9` | PASS | 2 passed, 18.2s | honest disabled-provider Talk persistence and worker-verified Agent result |
| real-stack Phase-H route floor Chromium desktop | production Nginx, FastAPI and owner session | working tree on `633acc9` | PASS | 1 passed, 28.5s; 17 product surfaces | canonical V197 roots, route screenshots, zero observed 5xx responses and page errors |

The first B6 attempt correctly failed `403 Request origin is not allowed` because
the isolated stack was launched with its default `localhost:5173` web origin
while the browser used `127.0.0.1:55173`. The stack was restarted with the
actual public origin and the unchanged assertion passed. The first Phase-H
route-floor attempt also correctly exposed that Research is embedded in the
canonical Systems owner ledger rather than owning `/research`; the test was
corrected to assert `#universe-research` without changing product behavior.
