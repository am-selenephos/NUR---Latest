# NUR Data Flow Map

Audited against repository baseline: `7df3ade9a9dea495b84d25cc7660350941c1e1f8`

This map records implemented high-level flow. It does not assert that every UI, external provider,
or release gate is complete.

## Authenticated owner request

1. The API resolves the HTTP-only session and owner identity.
2. Mutating routes require CSRF where declared; the database session receives the owner context.
3. PostgreSQL forced RLS is the final owner-row isolation boundary for covered tables.
4. Services persist the owner row, provenance/audit data, and any eligible domain event in the
   same bounded transaction where the service contract requires it.

## Talk: V197 -> Mind -> Brain -> Agency

1. V197 sends the owner's message, locale, writing preference, scope hints, and optional Orbit to
   `POST /api/v1/cognition/talk` or the streaming variant.
2. Mind resolves `ScopeEnvelope` before retrieval and checks the daily AI budget.
3. The capability resolver selects one of the currently registered first-party capabilities or an
   honest fallback. The baseline registry contains `contextual_answer` and
   `plan_from_conversation`; it is not a general plugin marketplace.
4. Mind hydrates only context allowed by the resolved scope, then writes an owner-scoped ModelRun
   and source lineage.
5. A deterministic worker may handle a bounded capability. Otherwise Brain applies a server-side
   profile and calls the configured provider. Browser code never receives the provider key.
6. Mind synthesizes and verifies the owner-facing result, persists response/evaluation metadata,
   and emits safe stream progress. Hidden prompts and chain-of-thought are not response fields.
7. A proposed side effect is not executed by Brain. Mind submits a typed workflow proposal to
   Agency, where registry, schema, policy, risk, and approval rules apply.

## Agency

1. Agency resolves an exact registered tool contract and version, validates arguments, and rejects
   secret-bearing or unknown calls.
2. The compiler applies the owner's policy and builds durable workflow/step records.
3. Approval-required calls pause on an owner record bound to tool, version, argument digest, plan
   version, and call version.
4. Approval decisions, state changes, append-only events, and dispatch intent commit atomically.
5. The outbox and worker runtime claim work, re-read policy and approval, execute the bounded
   handler, record the result, and verify it.

The baseline exposes reads and approval decisions, but not a complete direct owner
create/start/cancel/retry API or finished V197 Agent surface. Agency is therefore integrated but
not a complete owner lifecycle.

## WhyChanged and Hardness

1. Owner corrections, verified failures, outcome misses, contradictions, capability gaps, and
   other bounded signals may become owner-scoped learning evidence.
2. Hardness can represent learning candidates, curriculum snapshots, dry-run experiments, and
   promotion proposals under forced RLS.
3. The database constrains the trainer type to `DRY_RUN` at this baseline. A proposal is not an
   autonomous model update or product-wide promotion.
4. WhyChanged retains inspectable claim/evidence history for owner-facing explanation.

Hardness has no complete public product route or owner UI at this baseline. Live training and
promotion evidence remain outside the implemented claim.

## Research, Community, and Web Signals

1. Research briefs/source notes and Web Signal questions/notes persist owner-scoped staging data.
2. Research jobs/sources/claims, watchlists/alerts, expert verification, and tender-insight backend
   paths exist, but lawful live provider acceptance remains environment-dependent.
3. Community rooms, messages, posts, comments, reactions, social relations, reports, moderation,
   and appeals use scoped backend routes. Their existence does not prove complete V197 coverage.
4. NUR must never invent web results, experts, community population, or provider success when an
   external integration is unavailable.

## Context Capsule

1. The owner selects an Orbit, purpose, recipient, expiry/capability, and included sources.
2. The backend creates a versioned Capsule and grant bound only to the selected representations.
3. The recipient reads and asks within that grant; revoked or expired grants fail closed.
4. A recipient grant does not confer access to owner Talk, Journal, Timeline, Omega, Hardness,
   Agentic workflows, or general memory.

## Language

1. Owner locale and writing preference persist separately.
2. V197 applies RTL direction for supported RTL locales; Roman Urdu is a writing preference, not a
   fabricated locale.
3. Talk passes locale/writing preference through Mind to the server provider profile.
