# NUR Security Boundary Map

Audited against repository baseline: `7df3ade9a9dea495b84d25cc7660350941c1e1f8`

## Credentials and secrets

- Provider credentials are server-side only and must never enter source, V197, frontend env,
  screenshots, logs, queues, traces, evidence packets, packages, or chat.
- A reportedly exposed credential must be revoked and rotated immediately through the provider's
  trusted control plane, out of band. Git ignore, mode `600`, quarantine, and secret scans do not
  make an exposed value safe to retain or reuse.
- `infra/scripts/configure-openai-local.sh` is the local hidden-input provisioning path. Never copy
  an old `.env` or `.env.local` between worktrees.
- Bootable packages exclude environment files, dependencies/build products, runtime artifacts,
  proof folders, Git data, database volumes, Redis dumps, and secret-like artifacts.

## Session and owner isolation

- Authentication uses an HTTP-only session. Mutating endpoints use CSRF dependencies where
  declared; trusted-origin enforcement must be verified route by route.
- The runtime role is `nur_app` with `NOBYPASSRLS`. Covered owner records carry
  `owner_user_id`, and PostgreSQL policies use forced RLS.
- Schema-owner/superuser access is for migrations and isolated tests, not runtime API sessions.
- Wrong-owner object reads return no row or `404`, avoiding object-existence disclosure.

## Mind and Capability

- Mind resolves authenticated scope before retrieval. Context hydration must not widen that scope.
- The current capability registry is a bounded first-party catalog with two registered
  capabilities. Unknown capabilities, context sources, and Agency tools fail closed.
- Capability metadata does not grant database, filesystem, shell, network, connector, or secret
  access. Workers receive bounded inputs through canonical services.

## Brain

- Brain owns model profile/provider invocation. The browser and bridge do not call OpenAI directly.
- Disabled-provider mode is explicit and must not fabricate model output or external action.
- Structured output, evidence verification, safe error mapping, and model-run lineage are required
  before an answer is represented as completed.
- Prompts, hidden reasoning, credentials, and unrestricted private context are not public response
  or SSE fields.

## Agency

- All side effects must pass through registered, versioned tools, schema validation, owner policy,
  risk classification, budgets, and approval rules.
- Approval is bound to the exact tool call with argument digest, tool version, plan version, and
  call version. Edited or expired calls must be revalidated.
- Approval decisions, workflow state, append-only events, and dispatch intent commit atomically;
  the broker is not called inside that transaction.
- Agent workflows, steps, approvals, checkpoints, events, and outbox records are owner-scoped.

At the audited baseline, the approval-decision route has CSRF protection but does not declare the
trusted-origin dependency used by some other sensitive writes. That is a residual release gap, not
permission to treat CSRF alone as complete origin protection. Direct owner workflow lifecycle
routes and the complete V197 Agent surface are also absent.

## Hardness and self-directed learning

- Learning signals, candidates, curricula, experiments, and promotion proposals use owner keys
  and forced RLS.
- The current database permits only `DRY_RUN` training experiments.
- Owner-local evidence must not silently become global product learning. No candidate may train,
  self-modify, deploy, or promote itself from a proposal row.
- WhyChanged/provenance and independent evaluation remain required for any later promotion path.

## Recipient Capsule boundary

- Capsule grants expose only approved source representations.
- Recipients cannot access owner Talk, Journal, Timeline, Omega, Hardness, Agentic workflows,
  general memory, or excluded sources.
- Revoked and expired grants block reads and questions. Answers expose source references, not
  chain-of-thought.

## Frontend boundary

- Canonical V197 owns visible presentation; the TypeScript bridge is nonvisual infrastructure and
  narrowly binds/hydrates existing surfaces.
- No frontend OpenAI SDK, `VITE_OPENAI_API_KEY`, or public provider-key path is allowed.
- Visible controls must be registered and proved on the exact candidate. Missing destructive or
  external capabilities remain honestly disabled.

## Billing boundary

- Billing is disabled by default and provider secrets remain server-side.
- Checkout requires authenticated CSRF plus idempotency; checkout completion alone grants nothing.
- Webhooks verify raw-body signatures and owner/session/plan/provider bindings before projecting
  subscription and entitlement state.
- Live charges require an explicit enable switch. Test adapters are rejected in production.
