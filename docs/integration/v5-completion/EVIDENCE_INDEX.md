# EVIDENCE INDEX

All evidence below was produced on candidate `6d7eeefe6e3923015de879719e1a09056f30a6ce`
(branch `completion/nur-v5-full-pass`) on 2026-07-25. Nothing here is inherited from
another worktree, branch, or archive.

| Gate | Check | Command | Result | Artifact |
| --- | --- | --- | --- | --- |
| G00 | Environment gate | `whoami; uname -n; ls -ld …` | PASS (user nur, host archlinux) | DECISION_LOG.md D-001 |
| G00 | Git state | `git status/rev-parse/worktree/remote` | clean tree, 3 untracked dirs preserved | PRE_EDIT_GIT_STATE.md |
| G00 | Public GitHub | `gh api repos/am-selenephos/NUR` | main `f265123`, PR#5 `7a56510` OPEN draft, PR#6 MERGED | PRE_EDIT_GIT_STATE.md |
| G00 | Canonical V197 hash | `sha256sum …CHECKBOX_TICK_RESTORED.html` | `d4f7f2d3…` ≠ plan `252eee80…` | DECISION_LOG.md D-004 |
| G00 | Hash lineage | `git cat-file blob 03c9de12 \| sha256sum` | `6ce2c46` version == plan hash exactly | DECISION_LOG.md D-004 |
| G01 | Lint | `apps/api/.venv/bin/ruff check apps/api` | All checks passed, exit 0 | evidence/g01/static-part1.txt |
| G01 | Migration head | `alembic heads` | single head `0030_project_execution_storage` | evidence/g01/static-part1.txt |
| G01 | Backend tests | `pytest -q` | **180 passed** in 53.76s | DECISION_LOG.md D-005 |
| G01 | Web typecheck | `npm run web:typecheck` | exit 0, no diagnostics | evidence/g01/frontend-static.txt |
| G01 | Web unit tests | `npm run web:test` | 16 files / **63 tests** passed | evidence/g01/frontend-static.txt |
| G01 | V197 integrity | `npm run v197:integrity` | `pass: true` (host/entry/universe) | evidence/g01/frontend-static.txt |
| G01 | Secret scan | `npm run secret-scan` | PASS — no key/token/bearer pattern | evidence/g01/frontend-static.txt |
| G01 | Release naming | `npm run release:naming-scan` | PASS | evidence/g01/frontend-static.txt |
| G01 | Whitespace | `git diff --check` | clean | PRE_EDIT_GIT_STATE.md |
| G03 | Control matrix | `docs/release/v197-control-matrix.json` | 90 controls: 73 LIVE_REAL, 8 INTENTIONAL_LOCAL_ONLY, 7 NOT_IMPLEMENTED_VISIBLE, 2 BLOCKED_BY_EXTERNAL_PROVIDER, **0 BROKEN** — but `generated_from_sha` is `33a5dab`, so **STALE** for this candidate | REQUIREMENT_MATRIX.csv G03-006 |

## Evidence NOT yet captured on this candidate

These are honestly absent, not pending-but-assumed:

- Playwright browser suites (33 spec files) — none executed on `6d7eeef`
- Web production build — not re-run
- Mobile typecheck — not run
- Any performance trace, FPS, INP, long-task, or heap measurement
- Live AI run (no `.env.local` in this worktree)
- Billing provider test-mode run
- CI run (work is unpushed)
- Restore drill, staging deploy, packaged release artifact
