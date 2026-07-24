# Git lineage reconciliation — V6

Generated on candidate `6d7eeefe6e3923015de879719e1a09056f30a6ce`
(branch `completion/nur-v5-full-pass`, branched from `release/nur-p0-candidate`), 2026-07-25.

## Divergence

| Reference | Commit | Behind HEAD | Ahead of HEAD | Ancestor of HEAD |
| --- | --- | ---: | ---: | --- |
| public `main` | `f265123f727ca2c314f3eee03d00e0654c70ce76` | 49 | 0 | yes |
| PR #5 head `integration/nur-one-system-20260722` | `7a56510673b25768762265d20df8b07996571b70` | 1 | 0 | yes |
| PR #6 head `fable/v197-control-matrix-20260723` | `3102b48b932290f123585df5dcfc8454f046980f` | — | 0 | yes (merged into integration) |
| PR #1 `build-week-submission` | `c823512ee96b79df3dbe0fef851aa6adb8331a3c` | — | 0 | yes |
| PR #2 `rescue/lane-a-g09-uncommitted-20260722` | `eaa3c531eadaf1f9dce8610f603284815096e36c` | — | 0 | yes |
| PR #3 `rescue/lane-b-g13-uncommitted-20260722` | `4ded46c14b8756e7594383d32109400977ae8cec` | — | — | **no** — content-integrated, tip not merged |
| PR #4 `diagnostics/g09-pytest-20260722` | `eb94c2bdf9a86549f48f55d42bd23f96d41a946b` | — | — | **no** — diagnostic branch, superseded |

The single commit HEAD holds beyond PR #5 is
`6d7eeef fix(ai): restore compatible live Talk payload and proof gate`.

## What this means

- HEAD is a **strict superset** of public `main` and of the open draft PR #5. Nothing on the
  public remote is missing from the candidate.
- **Local work is unpushed.** Public `main` is 49 commits behind. There is therefore no CI
  evidence for this candidate — GitHub Actions has never run against `6d7eeef`. `G15_SCALE_OPS`
  records this as `UNPROVEN`, not as green.
- **Lane B (`4ded46c`, PR #3, G10–G15)** is not an ancestor. The prior forensic audit
  established that its content was integrated rather than merged: its four tip commits map to
  integration commits `dfa20bd`, `28f23e5`, `72c747c`, `85883b1`, and its migrations were
  renumbered 0022–0024 → 0027–0029. No stranded production feature results from this.
- **PR #4 (`eb94c2b`)** was a diagnostic branch for a G09 pytest failure; that failure no longer
  reproduces (`180 passed`), so the branch is superseded.

## Consequence for release

PR #5 remains **open and draft**. It must not be merged without founder approval. The
candidate for completion work is the local branch, not the public remote.
