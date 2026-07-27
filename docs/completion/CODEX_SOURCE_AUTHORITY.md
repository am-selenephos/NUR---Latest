# NUR Completion Source Authority

Generated during the full-completion pass. This file records provenance; it
does not claim that every product requirement is complete.

## Repository Authority

- Repository: `https://github.com/am-selenephos/NUR.git`
- Required base branch: `integration/nur-ui-reconcile-20260726`
- Verified base SHA: `2a4860aec319383c21844292821496532b48b0b5`
- Completion branch: `codex/nur-full-completion-20260726`
- Current evidence SHA when this record was created:
  `5f14ef55014e5dde7775773bf824a2e35e7a0497`
- Draft completion PR: `#8`
- PR URL: `https://github.com/am-selenephos/NUR/pull/8`
- The completion branch was created from the exact PR #7 head, not from
  `main`.

## Canonical Presentation

- Canonical host:
  `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`
- Canonical host SHA-256:
  `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`
- Presentation authority remains canonical V197.
- `apps/web/src/bridge/` is the nonvisual behavior and hydration owner.
- A generic replacement React interface is not an accepted source.
- The six-System contract at migration `0031_six_star_systems` is current.
  Older seven-System fixtures are superseded and must not be restored.

## Dependency Authority

- Root `package-lock.json` SHA-256:
  `764b54b19f3c2dce3efe6f0feaac04ef923073538864897f85d5f8c96eff804e`
- API `apps/api/requirements.lock` SHA-256:
  `e228367862675103cb87bce3825a14ac89c490f16b76ec85f239e4b389c3f273`
- Root npm workspaces own web and mobile JavaScript dependency resolution.
- API requirements are installed from the pinned lock in CI.

## Git and Agent Lineage

- PR #1 (`build-week-submission`) is an ancestor of the current branch.
- PR #2 (`rescue/lane-a-g09-uncommitted-20260722`) is an ancestor of the
  current branch.
- PR #5 (`integration/nur-one-system-20260722`) is an ancestor of PR #7 and
  the completion branch.
- PR #6 (`fable/v197-control-matrix-20260723`) was merged into PR #5.
- PR #3 contains Group Research, Community moderation, translation, and older
  seven-System commits. Its first three product domains are present in the
  current tree through equivalent/current commits; its seven-System contract
  is obsolete.
- PR #4 is a temporary pytest diagnostic workflow and is not product code.
- Commits with explicit `Co-Authored-By: Claude ...` or
  `Co-Authored-By: Claude Fable ...` trailers are already represented in the
  current ancestry where applicable. Authorship is not inferred for files
  without commit provenance.

## Preserved Sidecar Work

The dirty sidecar at
`/home/nur/Downloads/AM -Clean/NUR_FORENSIC_REBUILD` was inventoried without
being treated as canonical. It contains:

- large generated proof/log output that must not enter Git;
- an obsolete alternate migration chain and older canonical V197/CSS;
- candidate privacy lifecycle, Community realtime, engagement, intelligence,
  and billing extensions.

Any useful candidate must be ported deliberately onto the current post-`0031`
migration chain, reconciled with current models and RLS, and proven by current
tests. Wholesale copying is prohibited.

## Dirty State Preservation

The official completion worktree contains untracked generated Playwright proof
directories:

- `proof/100/`
- `proof/100-delta/`

They are not source authority and are intentionally not staged. Local `.env`
and `.nur-runtime` state are ignored runtime material and must not enter the
release.

## Truth Boundaries

- Green mocked tests do not prove live provider access.
- A backend route alone does not prove a complete product surface.
- Existing gap/status documents are historical inputs, not current proof.
- OpenAI, billing, email/push, research, and TRIBE claims require real provider
  or licence evidence. Missing external evidence remains explicitly blocked.
- The final report and matrices must be refreshed against one exact final
  commit after all implementation and release gates finish.
