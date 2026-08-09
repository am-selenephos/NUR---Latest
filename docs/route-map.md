# NUR Route Map

Audited against repository baseline: `7df3ade9a9dea495b84d25cc7660350941c1e1f8`

Presentation authority is the byte-checked V197 host at
`apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html` (SHA-256
`d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`). The
older `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3`
host hash is superseded historical evidence. Vite hosts V197 and loads the nonvisual bridge;
React does not own the visible interface.

## V197-native routes

These URLs serve the canonical V197 document. The bridge reads `location.pathname`, opens the
corresponding V197 page or bounded adjunct, and hydrates it from owner-scoped APIs.

| Route | Surface | Principal persisted path | Truth at the baseline |
|---|---|---|---|
| `/` | Entry/auth threshold | `/api/v1/auth/me`, `/auth/register`, `/auth/login` | live auth boundary |
| `/today` | Today | cognition, current state, plans, Glow | owner read/write surface |
| `/talk` | Talk | `/api/v1/cognition/talk`, `/talk/stream`, `/talk-thread`, corrections | Mind/Brain path; provider-disabled state is honest |
| `/journal` | Journal | `/api/v1/journal` | owner read/write surface |
| `/plan` | Plan | `/api/v1/plans`, `/plan-steps/{id}`, `/outcomes` | owner read/write surface |
| `/systems`, `/universe` | six-System Universe | living, Map, Orbit, Timeline, Insight, Research, Glow summaries | owner aggregate; full release parity not asserted |
| `/universe/map` | Map lens | `/api/v1/map/*`, `/universe/map-summary` | persisted graph/workspace paths exist |
| `/universe/orbits` | Orbits lens | `/api/v1/orbits/*`, `/universe/orbits-summary` | owner paths exist |
| `/universe/timeline` | Timeline lens | `/api/v1/timeline/*`, `/universe/timeline` | owner ledger/workspace paths exist |
| `/universe/insights` | Insights lens | `/api/v1/insights/*`, `/universe/insights-summary` | owner evidence paths exist |
| `/universe/research` | Research field | `/api/v1/research/briefs`, `/research/source-notes`, `/research/jobs`, `/research/sources`, `/research/claims` | owner backend exists; external retrieval remains provider-gated |
| `/universe/community` | Community field | `/api/v1/community/*` rooms, posts, messages, social and moderation | backend exists; complete V197 lifecycle is not asserted |
| `/universe/web-signals` | Web Signals | `/api/v1/web-signals/questions`, `/notes`, `/watchlists`, `/alerts` | owner staging/watch paths exist; no fabricated live-web claim |
| `/capsule/:id` | Capsule | `/api/v1/capsules/*` | bounded recipient/owner lifecycle path |
| `/settings` | Settings | profile/provider preference paths | partial owner surface; privacy-center completion not asserted |
| `/universe/omega` | Omega | `/api/v1/omega/*` | owner-only governed research paths |
| `/universe/omega/review` | Omega review | review queue decisions | owner confirmation path |
| `/universe/omega/why-changed/:claimId` | WhyChanged | `/api/v1/claims/{claimId}/why-changed` | provenance explanation path |

The automated control registry is `docs/interaction-registry.json`. Its presence does not prove
every route or control without an exact-candidate browser run.

## Cognition runtime

| API route | Current responsibility | Explicit limit |
|---|---|---|
| `POST /api/v1/cognition/talk` | authenticated Talk through the Mind cognitive loop | not a provider-success claim |
| `POST /api/v1/cognition/talk/stream` | resumable safe SSE coordination for the same kernel | must not expose prompts, secrets, or chain-of-thought |
| `GET /api/v1/cognition/talk-runs/{requestId}` | owner-scoped run/evidence status | metadata only |
| `POST /api/v1/cognition/talk-runs/{requestId}/cancel` | owner cancellation request | not an arbitrary worker kill surface |

Mind resolves scope before retrieval, applies the AI budget, resolves a registered capability or
fallback, hydrates bounded context, invokes Brain or a deterministic worker, verifies output, and
may submit a workflow proposal to Agency. At this baseline, the capability registry contains two
first-party capabilities; broader specialist coverage is not implied.

## Agency runtime

| API route | Current responsibility |
|---|---|
| `GET /api/v1/agentic/tools` | declared catalog with honest bound/unbound state |
| `GET /api/v1/agentic/workflows[/{id}]` | owner-scoped workflow and step reads |
| `GET /api/v1/agentic/workflows/{id}/events` | append-only owner run ledger reads |
| `GET /api/v1/agentic/approvals` | pending exact-call approval cards |
| `POST /api/v1/agentic/approvals/{id}/decide` | CSRF-protected approve/edit/reject bound to digest and versions |

Direct owner workflow create/start/cancel/retry routes and a complete V197 owner Agent surface are
not present at this baseline. The typed registry, compiler, policy, outbox, runtime, and workers do
not by themselves make that lifecycle complete.

## Intelligence and Hardness

- `GET /api/v1/intelligence/provider-status` reports server-side configuration and the owner's
  last recorded run without exposing credentials.
- `POST /api/v1/intelligence/evaluate` persists bounded evaluation-suite results.
- `GET /api/v1/claims/{claimId}/why-changed` reads owner-scoped WhyChanged provenance.
- Hardness tables and services persist owner-scoped learning signals, candidates, curricula,
  dry-run experiments, and promotion proposals. There is no dedicated public Hardness product
  route at this baseline, and no autonomous model promotion is claimed.

## Revenue backend routes

Owner-scoped billing contracts exist under `/api/v1/billing/*`. Their presence is not a claim that
live provider checkout, a paid V197 lifecycle, or production release proof has passed.
