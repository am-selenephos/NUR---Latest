# NUR

**Neural Upgrade Rewiring: a private, evidence-bound cognitive operating system.**

This is the canonical NUR platform repository. The founder-approved V197 interface is connected
through one nonvisual TypeScript bridge to a FastAPI backend with owner-scoped persistence,
retrieval, verification, controlled sharing, Mind/Brain cognition, bounded capabilities, and an
Agency execution boundary.

The currently shipped owner experience includes:

- private Today, Talk, Journal, Plan, and Systems workflows;
- dedicated Map, Orbit, Timeline, and governed Insights surfaces;
- the canonical Entry galaxy, V43 star-brain, Systems star-brain, and loading sigil runtimes;
- structured Talk, persisted plans and outcomes, owner memory, Context Capsules, and revocation;
- bounded Agency, capability, billing, notification, Glow, Omega, and operations foundations.

Retired consultation, web-research, community-intelligence, and expert-voice placeholders are not
part of the visible canonical product. External providers remain fail-closed until their real
server-side configuration is supplied. Read [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md) for the verified
demonstration flow and [`RUNBOOK.md`](RUNBOOK.md) for local operations.

## Why NUR

Ordinary AI products often blur four separate operations:

1. reasoning over sensitive context;
2. deciding what becomes durable memory;
3. choosing what another person may see;
4. revoking that access later.

NUR keeps those operations separate and inspectable.

- **Talk** returns a structured response: observed facts, inference, hypotheses, uncertainty, and one next move.
- **Evidence and verification** record what owner-scoped material was retrieved and reject unavailable source references.
- **Persistence** stores Talk turns, model runs, decisions, references, journals, plans, corrections, and outcomes.
- **Context Capsules** snapshot only explicitly selected Orbit sources.
- **Representations** support full content, owner-approved summaries, or metadata only.
- **Recipient rooms** show included context, withheld-source counts, answer modes, and source references.
- **Revocation and expiry** close access through distinct audited states.

## Architecture

```text
Canonical V197 Entry + Universe presentation
        |
        +--> nonvisual TypeScript bridge (no second visible renderer)
        |
        v
FastAPI API + HTTP-only session + CSRF
        |
        +--> Mind: scope, capability routing, hydration, verification
        +--> Brain: server-only provider profiles and structured cognition
        +--> Agency: typed tools, policy, exact-call approval, outbox/runtime
        +--> Postgres with forced owner RLS
        +--> Redis + Celery worker / scheduler
        +--> evidence, model-run, WhyChanged, and Hardness ledgers
        |
        v
Owner surfaces + versioned Context Capsule/grant/audit/revoke
```

At the canonical recovery checkpoint `bf6411c74f96e2380a72a492337c6c14b970885e`, Talk enters the
Mind loop, resolves scope before retrieval, selects one of the registered bounded capabilities or a
fallback, invokes Brain through the server provider boundary when needed, and submits proposed
side effects to Agency. A source file, test, or historical screenshot is not release proof: every
candidate must pass the repository gates and live browser verification on its exact commit.

## Quick boot

Requirements include Docker Engine/Desktop, Node.js, npm, Python 3, and standard PostgreSQL client tools.

```bash
bash START_NUR.sh
```

The first interactive launch securely asks for the local OpenAI API configuration. The key is written only to ignored, mode-600 `.env.local`; it never belongs in browser code, screenshots, logs, commits, or distributable archives.

Later launches are one command. Open:

```text
http://localhost:5173
```

The launcher starts the local services selected by its mode, runs health checks, and opens the
browser. A successful local boot is not release proof.

Useful commands:

```bash
bash RUN_NUR.sh status
bash RUN_NUR.sh logs
bash RUN_NUR.sh doctor
bash RUN_NUR.sh seed
bash RUN_NUR.sh stop
bash RUN_NUR.sh package
```

## Release verification

Release readiness is verified by the release gate before any candidate is cut.

Static acceptance:

```bash
bash infra/scripts/release-gate.sh static
```

Start real OpenAI mode and run the live acceptance path:

```bash
bash START_NUR.sh openai
bash infra/scripts/release-gate.sh live
```

Run both against the exact candidate commit:

```bash
bash infra/scripts/release-gate.sh all
```

The gate fails closed on V197 integrity, secret scan, API tests, web typecheck, unit tests, production build, mocked Talk/visual readiness, OpenAI structured-output persistence smoke, or the two-account Context Capsule lifecycle.

A PASS from another commit is not proof for the current commit.

## Main surfaces

- Web app: `apps/web`
- API: `apps/api`
- Shared TypeScript package: `packages/shared-types`
- Postgres/Redis compose: `docker-compose.yml`, `docker-compose.dev.yml`
- Boot and verification scripts: `infra/scripts`
- Alembic migrations: `apps/api/alembic/versions`

## OpenAI boundary

- OpenAI calls are server-side only.
- Responses must match the NUR structured schema.
- Authentication and provider errors fail closed.
- Disabled-provider mode is explicit and does not fabricate model text.
- External web research remains disabled for this readiness gate.
- The current recipient Capsule answer path is deliberately constrained to approved source representations; do not claim broader private-memory access.

## Omega v1

Omega is an owner-only governed research layer, not a consciousness, AGI, sentience, soul, or autonomous real-world actor. It stores owner-scoped experiences, claims, evidence edges, contradictions, predictions, learning proposals, review-queue items, and consolidation runs under forced Postgres RLS.

The hidden UI is available only when `VITE_NUR_ENABLE_OMEGA_RESEARCH=true`:
- `/universe/omega`
- `/universe/omega/review`

Omega is not required for the core vertical-slice demo.

## Manual test commands

```bash
python -m pytest apps/api/app/tests -q
npm --workspace apps/web run typecheck
npm --workspace apps/web test -- --run
npm --workspace apps/web run build
npm --workspace apps/web run e2e -- e2e/talk.spec.ts e2e/visual-readiness.spec.ts --project=chromium-desktop --workers=1
npm --workspace apps/web run e2e -- e2e/capsule.spec.ts --project=chromium-desktop --workers=1
```

See [`QUICKSTART_BOOT.md`](QUICKSTART_BOOT.md), [`RUNBOOK.md`](RUNBOOK.md), and [`SECURITY_NOTES.md`](SECURITY_NOTES.md) for the complete local operations flow.
