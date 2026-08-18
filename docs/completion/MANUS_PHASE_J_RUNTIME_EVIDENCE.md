# Phase-J Runtime and Release Evidence

**Repository:** `am-selenephos/NUR---Latest`

**Branch:** `completion/nur-fullstack-agentend-20260818`

**Code SHA used for the latest runtime evidence:** `375e0f8ebeb9adceabd48840390aed407e1b6fe8`

## J1 — cold boot

The official `RUN_NUR.sh` Docker cold-boot path could not execute in this sandbox because `docker` is not installed. The Docker-independent `infra/scripts/boot-smoke.sh` was also attempted against the real local PostgreSQL/Redis services; its API process started, but `/readyz` returned HTTP 503 for the full readiness window and the smoke did not claim success. J1 therefore remains `HOLD-DEPENDENCY`.

## J2/J3 — backup and restore

The isolated disaster-recovery drill passed against the real `nur_b6` PostgreSQL database. It wrote a backup manifest at revision `0058_agentic_insights_engine`, restored into isolated target `nur_dr_drill_29976`, and verified revision parity, object digests, database-dump digest, and row parity. The recorded drill output is retained at `/home/ubuntu/nur-dr-drill.txt` for the session and the reproducible script is `infra/scripts/dr-drill.sh`.

> `DR DRILL PASS: backup restored into an isolated target and verified (revision, object digests, db dump digest, row parity).`

J2 and J3 are `PASS` for this exact code SHA. This is a local isolated restore proof, not a production backup-service availability claim.

## J4 — crash and recovery

The real-broker restart/redelivery and crash-recovery tests passed:

```text
3 passed, 6 deselected in 28.29s
```

The tested paths include a restarted worker completing committed work, broker redelivery producing one durable effect, and a claimed execution being reclaimed after a simulated crash/lease expiry.

## J5 — static release gate

The complete static release gate passed after correcting the stale local-provider regression expectation. The gate reported canonical V197 integrity pass, secret-scan pass, all three local OpenAI safety regressions pass, API tests pass, web typecheck pass, web unit tests pass, production build pass, and the mocked Talk/visual browser gate passed 9 tests with 1 explicitly skipped mobile evidence test.

```text
STATIC_GATE=PASS
RELEASE_GATE=PASS mode=static
```

This does not prove live provider authentication or model access.

## J6 — live provider gate

The live gate was run with reachable local API/web origins and correctly stopped at the provider boundary:

```text
FAIL live release gate requires ai_provider=openai; got disabled
live_gate_exit=1
```

No live-provider success is claimed. J6 remains externally blocked until an approved provider credential and reachable model catalog are supplied through the repository’s trusted local configuration flow.

## J9 — fresh-extract artifact

A truthful `HOLD` package was created and independently verified from frozen implementation SHA `9cc7afb9dd6b8f20d2c92fb98999a1f23f9c56cc`:

| Artifact | Value |
|---|---|
| Archive | `/home/ubuntu/NUR-final-evidence/NUR_V5_HOLD_20260818.zip` |
| Archive SHA-256 | `21b5902ba18a6dc991682a1e12c42e17158459c3f08f39683170be85c29db2d7` |
| Manifest | `/home/ubuntu/NUR-final-evidence/NUR_V5_HOLD_20260818_MANIFEST.json` |
| Manifest source SHA | `9cc7afb9dd6b8f20d2c92fb98999a1f23f9c56cc` |
| Archive entries | `829` |
| Uncompressed bytes | `9,225,297` |
| V197 integrity | `PASS` in the extracted tree |
| Secret scan | `PASS` in the extracted tree |
| Naming scan | `PASS` in the extracted tree |
| Clean install check | `0` because the package verdict is `HOLD` |

The artifact is intentionally not labeled `FULL_PASS`.

## Remaining J7/J8/J10 status

The full real-stack browser matrix, independent cross-browser/accessibility/performance review, and independent final review were not completed. Existing focused B6/C1/C5 browser proofs and static visual gates remain valid, but they do not substitute for the complete J7/J8/J10 acceptance matrix. These tasks remain `HOLD-DEPENDENCY`.
