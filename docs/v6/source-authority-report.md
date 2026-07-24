# Source authority report — V6

Candidate: `6d7eeefe6e3923015de879719e1a09056f30a6ce` · branch `completion/nur-v5-full-pass` · 2026-07-25

## 1. Canonical repository

`/home/nur/NUR-INTEGRATION-20260722` is the canonical working repository. It is a real Git
repository whose toplevel resolves to itself, with remote `https://github.com/am-selenephos/NUR.git`.
It is a strict superset of public `main` and of the open draft PR #5 — see
[git-lineage-reconciliation.md](./git-lineage-reconciliation.md).

Seven other worktrees exist on this machine. None of them is the completion candidate:

| Worktree | HEAD | Role |
| --- | --- | --- |
| `NUR-INTEGRATION-20260722` | `6d7eeef` | **completion candidate** |
| `NUR-LIVE-TALK-PROOF-20260723` | `33a5dab` | historical live-AI proof — evidence **must not be inherited** |
| `NUR-FABLE-CONTROL-MATRIX-20260723` | `3102b48` | merged into integration via PR #6 |
| `NUR-FABLE-20260720-155600` | `69d1d70` | earlier readiness lane |
| `NUR-DEMO-COUSIN-20260722` | `28f23e5` | demo lane, content integrated |
| `NUR-DEMO-TALK-FIXED` | `1682abc` | demo lane |
| `NUR-WT-BACKEND` | `4525110` | backend completion lane |

## 2. Canonical V197 presentation source

Runtime ownership:

```
apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html   (canonical host)
docs/reference/entry_decoded_v197.html                      (Entry reference)
docs/reference/universe_decoded_v197.html                   (Universe reference)
        ↓ thin, nonvisual bridge
apps/web/src/bridge/  — v197Bridge, v197Bindings, v197Selectors, v197Mutations,
                        v197ApiClient, v197StreamClient, v197I18n, v197Rewards,
                        v197Events, v197Hydration, v197Accessibility, v197Adjuncts
        ↓
FastAPI modular monolith → Postgres (RLS) → Redis/Celery → server-side AI gateway
```

Integrity is enforced by `scripts/check-v197-integrity.ts` via `npm run v197:integrity`,
which pins all three hashes and fails the build on any drift. It passes on this candidate.

**Open conflict.** The pinned host hash is `d4f7f2d3…`; the binding V5 plan pins `252eee80…`.
This is CONFLICT-001 — see [conflict-and-supersession-report.md](./conflict-and-supersession-report.md).

## 3. Backend reuse inventory

The candidate already owns real implementations. Completion work **extends** these; it does
not duplicate them.

| Domain | Location | Migration |
| --- | --- | --- |
| auth, sessions, CSRF | `app/api/v1/auth.py`, `app/services/auth_service.py`, `app/core/security.py` | 0001, 0002 |
| password recovery | `app/api/v1/password_recovery.py`, `app/services/password_recovery_service.py` | 0022 |
| cognition (Talk/Journal/Plan/outcomes) | `app/cognition/`, `app/api/v1/cognition.py` | 0003, 0021 |
| AI provider gateway | `app/ai/openai_provider.py`, `app/ai/prompts.py` | 0005, 0015 |
| personal memory | `app/api/v1/memory.py`, `app/models/memory.py` | 0023 |
| Teach NUR / learning | `app/learning/`, `app/models/learning.py` | 0024 |
| Omega | `app/omega/` | 0007, 0008 |
| living systems / universe | `app/living/`, `app/universe/`, `app/api/v1/{living,map,timeline,insights}.py` | 0012, 0013 |
| Glow / progression | `app/services/glow_service.py`, `app/api/v1/glow.py` | 0011, 0017, 0026 |
| community + moderation | `app/community/`, `app/api/v1/community*.py` | 0016, 0017, 0018, 0028 |
| consultations | `app/api/v1/consultations.py` | 0019 |
| group NUR / research | `app/api/v1/group_research.py` | 0016, 0029 |
| capsules / sharing | `app/sharing/`, `app/api/v1/capsules.py` | 0004 |
| projects / storage | `app/api/v1/projects.py`, `app/services/{project_execution,object_storage,storage_hygiene}.py` | 0014, 0030 |
| billing | `app/billing/`, `app/models/billing.py` | 0025 |
| notifications | `app/api/v1/notifications.py` | 0020 |
| translations / i18n | `app/i18n/`, `app/api/v1/translations.py` | 0010, 0027 |
| engagement policy | `app/services/engagement_policy.py` | — |
| audit / events / outbox | `app/services/{audit_service,domain_event_service}.py` | 0001 |
| observability / ops | `app/observability/`, `app/api/v1/ops.py` | — |
| DR | `app/services/dr.py`, `infra/scripts/dr-*.sh` | — |

## 4. Domains with no implementation to reuse

Building these from nothing is correct; nothing is being duplicated.

- bounded agents (tasks, runs, artifacts, reviews, permissions, budgets, cancel, rollback)
- authenticated realtime gateway (WebSocket/SSE with membership revalidation)
- Signal Feed candidate generation and ranking
- experiment engine (definitions, assignment, exposure, guardrails, stop, rollback)
- Glow fraud detection and leaderboards
- notification push/email delivery adapters
- privacy center (access, rectify, export, erase, restrict, portability, receipts)
- expert verification and watchlist/change-detection scheduler
- SBOM and dependency-audit pipeline
- the deterministic `infra/scripts/nur-gate.sh` G00–G16 runner

## 5. Evidence discipline

Every claim in this report was produced by a command run against this candidate today. The
live-AI proof held by `NUR-LIVE-TALK-PROOF-20260723` at `33a5dab` is **explicitly not inherited**;
`G05_LIVE_AI` stands at `BLOCKED_EXTERNAL` until it is reproduced here.
