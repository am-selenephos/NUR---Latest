# NUR Repository Rename Runbook

**Current canonical repository:** `am-selenephos/NUR---Latest`

**Rename status:** Not executed. The canonical repository name and all existing history remain unchanged.

A repository rename is a post-promotion administrative operation, not a completion proof. It must not be performed while the branch is `NUR_PARTIAL`, while any applicable release gate is held, or while the exact-head PR is draft.

## Preconditions

The owner must first confirm that the completion PR is approved, every applicable G00–G16 check is green on one exact SHA, the final tag points to that SHA, and all external provider, branch-ruleset, deployment, and independent-review blockers are resolved. The owner must record the old name, new name, exact SHA, PR number, tag, and operator identity in the release ledger before initiating the rename.

## Controlled operation

1. Freeze merges and record the current `main` SHA and tag.
2. Confirm that the intended new name is available and that the organization owner has approved the change.
3. Rename the repository through the GitHub repository settings or the authenticated repository API. Do not rewrite Git history.
4. Update canonical references in the organization, CI variables, deployment configuration, badges, documentation, branch rulesets, webhook targets, and local clone remotes.
5. Verify that GitHub redirects the old URL to the new URL and that clone, fetch, PR, Actions, release, and raw-file URLs resolve correctly.
6. Re-run exact-head CI and the release verification suite under the new canonical URL.
7. Record the old-to-new redirect, final `main` SHA, tag, CI run IDs, and rollback contact.

## Rollback

If redirects, Actions, webhooks, branch rulesets, or deployment URLs do not resolve, stop promotion and restore the prior repository name through the owner control plane. Do not force-push, delete branches, or recreate the repository as a substitute for a rename.

**K6 verdict for this completion branch:** `PASS-CANDIDATE` for the documented runbook; the rename operation itself remains intentionally unexecuted because canonical `main` must not be changed during this task.
