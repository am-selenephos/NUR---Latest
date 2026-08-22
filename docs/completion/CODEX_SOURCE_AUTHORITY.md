# NUR Completion Source Authority

Refreshed on 2026-08-21 during the final-closure pass. This file records
provenance; it does not claim that every product requirement is complete.

## Repository Authority

- Repository: `https://github.com/am-selenephos/NUR---Latest.git`
- Base branch: `main`
- Verified base SHA: `1c6f5f1e9f3380204f6809d2a78364e046e4908e`
- Completion branch: `codex/nur-final-closure-20260820`
- Verified pushed baseline before the 2026-08-21 closure edits:
  `633acc9d5567de92a802a691570afec253a39123`
- Draft completion PR: `#5`
- PR URL: `https://github.com/am-selenephos/NUR---Latest/pull/5`
- The final evidence SHA is intentionally not predeclared. It becomes
  authoritative only after the complete gate sequence passes and that exact
  commit is pushed.

## Canonical Presentation

- Canonical host:
  `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html`
- Canonical host SHA-256:
  `397c302579472e60f5bd667546a96b6e3f262aa40bd932d10c1946e13b046dd2`
- Presentation authority remains canonical V197.
- `apps/web/src/bridge/` is the nonvisual behavior and hydration owner.
- A generic replacement React interface is not an accepted source.
- The six-System contract at migration `0031_six_star_systems` is current.
  Older seven-System fixtures are superseded and must not be restored.

## Dependency Authority

- Root `package-lock.json` SHA-256:
  `d8cce9f3614d615e11c62976b203fb6b439bf9d50c8b17c469bf4d23f05c0baf`
- API `apps/api/requirements.lock` SHA-256:
  `e228367862675103cb87bce3825a14ac89c490f16b76ec85f239e4b389c3f273`
- Root npm workspaces own web and mobile JavaScript dependency resolution.
- API requirements are installed from the pinned lock in CI.

## Superseded Git Lineage

The former repository `am-selenephos/NUR` and its PR #8 remain historical
lineage, not the active release authority. Its relevant work was reconciled
into `NUR---Latest` before this closure branch. The legacy remote remains
readable for provenance only.

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

The official closure worktree is
`/home/nur/Downloads/AM -Clean/NUR-FINAL-CLOSURE-20260820`. During active work
it may contain reviewed source and evidence-document edits. Generated proof,
local `.env*`, `.nur-runtime`, caches, reports, and test results are not source
authority and must not enter the release commit.

## Truth Boundaries

- Green mocked tests do not prove live provider access.
- A backend route alone does not prove a complete product surface.
- Existing gap/status documents are historical inputs, not current proof.
- OpenAI, billing, email/push, research, and TRIBE claims require real provider
  or licence evidence. Missing external evidence remains explicitly blocked.
- The final report and matrices must be refreshed against one exact final
  commit after all implementation and release gates finish.
