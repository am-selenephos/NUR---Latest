# RELEASE VERDICT

Repo: `/home/nur/NUR-INTEGRATION-20260722` · branch `release/nur-p0-candidate` ·
HEAD `6d7eeef` · tag `nur-p0-rc1`. Evidence: all audit-output/ reports.

## Decision by release surface
| Surface | Decision | Rationale |
|---|---|---|
| LOCAL_DEVELOPMENT | **GO** | Boots; 180 backend + 63 frontend tests green; single migration head; ruff/typecheck/secret-scan clean. |
| FOUNDER_DEMO | **GO_WITH_CONDITIONS** | Fully demoable; condition: configure a **rotated** OpenAI key in a mode-600 `.env.local` and run the live Talk proof once on the demo host. |
| CONTROLLED_BETA | **GO_WITH_CONDITIONS** | Conditions: (1) rotate the 3 leaked keys [F1]; (2) run the live Talk gate in THIS worktree to convert BLOCKED_EXTERNAL→PASS; (3) confirm demo seeding disabled in the beta env [F2]. |
| PAID_PILOT | **HOLD** | Billing is BACKEND_ONLY (no UI) and needs Stripe/LemonSqueezy live config; Talk live gate not yet run in this worktree. |
| PUBLIC_BETA | **HOLD** | Playwright E2E suite not executed this session; Teach NUR/Billing unwired; push/email delivery providers off; live Talk unproven here. |
| PUBLIC_PRODUCTION | **HOLD** | Above + external providers (OpenAI billing limits, Stripe, email/push) and a full E2E + load pass required. |

## HOLD blockers — exact evidence
- **PAID_PILOT / PUBLIC_*:** `LIVE_TALK_BLOCKED_EXTERNAL` — no server-only OpenAI
  credential in this worktree (`CURRENT_GIT_TEST_EVIDENCE.md`); Billing `BACKEND_ONLY`
  with Stripe unconfigured (`FEATURE_REACHABILITY_MATRIX.csv`); Playwright E2E (33
  specs) not executed in this session.
- **Cross-cutting security:** F1 leaked OpenAI keys in the archive
  (`SECURITY_PRIVACY_REPORT.md`) — rotate before any external distribution of the
  archive.

## What is NOT blocking
- Integration completeness: current Git is a clean superset of all 8 lanes;
  0 stranded production features; 6d7eeef == proven Live-Talk state byte-for-byte.
- The 3 "missing" Lane B migrations (renumbered, present) and the removed
  build-week-gate.sh (intentional) — documentation-only / by-design.

## Headline
The **code** is release-candidate quality (clean superset, all offline+DB gates
green, strong security posture). The gates to lift HOLDs are **operational**
(rotate keys, configure providers, run the live Talk + Playwright E2E in this
worktree), not code-integration defects.
