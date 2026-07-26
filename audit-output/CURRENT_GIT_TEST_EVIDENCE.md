# CURRENT GIT TEST EVIDENCE — Phase 6

All gates run against the CURRENT integration worktree
`/home/nur/NUR-INTEGRATION-20260722` @ `6d7eeef` (branch release/nur-p0-candidate).
Nothing inherited from another worktree. No product code modified. No secrets printed.

Infra used: local PostgreSQL 16 on :5432 (roles nur_admin/nur_app present) + an
ephemeral local Valkey/Redis started on :6379 for the test session (scratchpad dir).

## Gate results
| Gate | Command | Result |
|---|---|---|
| Python compile (all backend) | `python -m compileall app` | **exit 0** |
| AI files compile | `py_compile ai/openai_provider.py ai/prompts.py` | **OK** |
| reasoning-effort gate logic | unit-eval `_supports_reasoning_effort` | gpt-4.1/gpt-4o→False; o1/o3-mini/o4/gpt-5→True — **correct** |
| AI provider failure tests | `pytest test_ai_provider_failures.py` | **7 passed** |
| Verifier + structured-output units | `pytest test_verifier_grounding.py test_ai_structured_outputs.py` | **2 passed** |
| Talk-critical DB tests | `pytest test_cognition.py test_cognition_streaming.py test_intelligence_contracts.py test_verifier_grounding.py` | **17 passed** |
| **Full backend regression** | `pytest` (39 files) | **180 passed, 0 failed** in 53s |
| Migration single head | `alembic heads` | **0030_project_execution_storage (head)** — single |
| Backend lint | `ruff check app` | **All checks passed** |
| Secret scan | `infra/scripts/secret-scan.sh` | **passed** (no key/token/assignment) |
| git diff --check | `git diff --check` | **CLEAN** |
| Frontend typecheck | `npm run typecheck` (tsc --noEmit) | **exit 0** |
| Frontend unit tests | `vitest run` | **16 files, 63 passed** |

## Live OpenAI Talk gate — BLOCKED_EXTERNAL (not inherited)
The repository's live path is `RUN_NUR.sh openai` → `openai-smoke-local.sh` →
`live-talk-two-turn-proof.mjs`, all gated by `validate-openai-local.sh` which
requires a mode-600 `.env.local` carrying a server-only OpenAI key.

State of THIS worktree (verified, no values printed):
- `.env.local`: **absent**
- `.env`: **absent**
- `OPENAI_API_KEY` in environment: **unset**
- secret scan: **no key anywhere in the tree**

Therefore the live browser two-turn proof **cannot be executed in this worktree**.
Per the non-inheritance rule, the earlier `LIVE_TALK_PASS` achieved in the
separate `/home/nur/NUR-LIVE-TALK-PROOF-20260723` worktree is **NOT** claimed here.

What IS proven for the current worktree without a live key:
- The six proven files are byte-identical to that separately-proven state
  (LIVE_TALK_PORT_COMPARISON.md).
- The same server-side code paths are exercised and pass under real Postgres+Redis:
  durable semantic streaming, idempotent replay, fail-closed typed provider errors,
  unverified-output blocking, disabled-provider honest persistence
  (`test_cognition_streaming.py`, `test_intelligence_contracts.py` — all green).
- The gpt-4.1 payload fix is unit-verified (reasoning-effort gate).

## FINAL LIVE-TALK STATUS: **LIVE_TALK_BLOCKED_EXTERNAL**
Exact remaining blocker: no server-only OpenAI credential / `.env.local` is
configured in `/home/nur/NUR-INTEGRATION-20260722`. Configure one via
`infra/scripts/configure-openai-local.sh` and run `RUN_NUR.sh openai` +
`openai-smoke-local.sh` + `node infra/scripts/live-talk-two-turn-proof.mjs` to
convert this to `LIVE_TALK_PASS_CURRENT`. Code readiness for that PASS is
established (identical to proven state; all offline/DB gates green).
