# NUR Main-Branch Ruleset Runbook

**Repository:** `am-selenephos/NUR---Latest`

**Protected branch:** `main`

**Completion-branch policy:** This runbook is evidence for Phase I6. It does not modify canonical `main` or repository settings from the completion worktree.

## Required rules

The canonical repository should enforce the following ruleset before any completion branch is promoted:

| Rule | Required setting |
|---|---|
| Pull request | Direct pushes to `main` are rejected; all changes arrive through a pull request. |
| Approval | At least one approving review is required, with stale approvals dismissed after new commits. |
| Required checks | The `web-and-security` and `api` jobs from `.github/workflows/readiness.yml` must pass on the exact proposed head SHA. |
| Conversation resolution | All review conversations must be resolved before merge. |
| Force push | Force pushes are blocked. |
| Deletion | Branch deletion is blocked. |
| Administrators | The rules apply to administrators unless an explicitly documented emergency exception is approved outside this task. |
| Linear history | Rebase or squash merge is preferred; merge commits are not required by the technical proof. |

## Exact-check contract

The required check names are derived from the workflow job identifiers, not from a local test summary. A promotion is eligible only when the GitHub check runs for the proposed SHA and both `web-and-security` and `api` are green. A local pass cannot substitute for an absent or differently named remote check.

## Current repository state

The completion-branch audit on 2026-08-18 found no active branch-protection configuration: `GET /repos/am-selenephos/NUR---Latest/branches/main/protection` returned HTTP 404 (`Branch not protected`), and the repository ruleset list was empty. Applying the desired ruleset would change canonical repository settings, so it is intentionally not performed under the requirement that canonical `main` remain unchanged.

## Owner-executed application command

A repository administrator may apply the policy after reviewing the final exact SHA. The command must be executed against the canonical repository, not from an untrusted fork, and should be reviewed in the GitHub UI before confirmation:

```bash
gh api --method POST \
  repos/am-selenephos/NUR---Latest/rulesets \
  --input /path/to/nur-main-ruleset.json
```

The JSON should use a repository ruleset targeting `main`, require pull requests and the exact `web-and-security` and `api` status checks, and set `non_fast_forward` and `deletion` to disabled. The owner must verify the resulting ruleset with:

```bash
gh api repos/am-selenephos/NUR---Latest/rulesets
gh api repos/am-selenephos/NUR---Latest/branches/main/protection
```

**Phase-I6 verdict for this completion SHA:** `HOLD-DEPENDENCY` until a repository administrator applies and verifies the ruleset without changing canonical code history.
