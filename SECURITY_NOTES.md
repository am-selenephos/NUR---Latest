# Security Notes

## Secrets

- `.env` and `.env.local` are excluded from the bootable package.
- OpenAI keys must be entered only with
  `infra/scripts/configure-openai-local.sh`.
- The frontend never reads `OPENAI_API_KEY`.
- `infra/scripts/secret-scan.sh` scans source, frontend dist, reports, traces,
  logs, proof, and evidence artifacts for OpenAI key and bearer-token patterns.
- A credential reported in chat, an archive, a log, or another uncontrolled
  location is exposed even if it is Git-ignored or later quarantined. Revoke and
  rotate it through the provider control plane out of band. Never retrieve,
  transfer, or reuse the old value.

## AI Provider

Default boot mode is:

```text
NUR_AI_PROVIDER=disabled
```

Disabled mode is honest. It does not fake model output. OpenAI mode requires a
server-side `.env.local` and a configured model.

## RLS

The runtime role is `nur_app` with `NOBYPASSRLS`. Owner tables are expected to
use forced owner-only RLS. This includes Omega, Agentic, and Hardness data; the
schema-owner migration role is not a runtime identity.

Omega tables include:

- `omega_experiences`
- `omega_claims`
- `omega_evidence_edges`
- `omega_contradictions`
- `omega_workspace_frames`
- `omega_predictions`
- `omega_learning_proposals`
- `omega_consolidation_runs`
- `omega_review_queue`

Capsule recipient grants are separate from Omega owner memory and do not grant
access to Omega tables.

Agentic workflows, steps, approvals, events, checkpoints, and dispatch records
are owner-scoped. Hardness learning signals, candidates, curricula, dry-run
experiments, and promotion proposals are owner-scoped and forced-RLS protected.

## Mind, Brain, Capability, and Agency

- Mind resolves the authenticated scope before retrieval and assembles bounded context.
- Capability routing may choose only registered capability contracts or an honest fallback.
- Brain is the only server-side model-provider boundary; provider credentials never enter V197
  or the browser bridge.
- Side effects belong to Agency. Tools are registered and versioned, policy is checked, and
  durable actions require approval bound to the exact call where policy requires it.
- Queue payloads, telemetry, approval cards, and SSE events must not expose credentials, hidden
  prompts, chain-of-thought, or unrestricted private context.

The presence of these components is not a release-completion claim. The baseline still lacks a
complete owner lifecycle API/UI for creating, starting, cancelling, and retrying workflows.

## Hardness boundary

Hardness records governed learning evidence and proposals. The current training experiment
contract accepts `DRY_RUN` only. It must not silently train, self-modify, promote a checkpoint,
or convert owner-local material into global product learning. Promotion remains an inspectable
proposal requiring separate evidence and authorization.

## Omega Limits

Omega v1 is a governed research layer. It does not claim sentience, AGI,
consciousness, soul, feelings, free will, or autonomous external action. It
does not expose chain-of-thought. Learning proposals require owner approval and
cannot rewrite RLS, auth, secrets, recipient grants, or autonomous action
policy.

## Packaging

`infra/scripts/package-bootable.sh` excludes:

- `.env`, `.env.local`, other `.env.*` files except `.env.example`
- `node_modules`
- build/dist output
- `.git`
- database dumps and runtime volumes
- logs, traces, proof, evidence, and screenshots
- secret directories
