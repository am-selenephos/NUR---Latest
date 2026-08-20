# NUR Legacy Gate Reconciliation — 2026-08-20

## Purpose and decision rule

This document reconciles every `skip` and every non-PASS override in `infra/scripts/nur-gate.sh` against the current Master Addendum requirement matrix. The historical runner is not treated as authoritative by silence: a skipped step is either mapped to a current requirement, superseded by the current release contract, already proven by newer evidence, externally blocked, or deferred by an explicit scope decision.

The runner itself was **not edited** to manufacture PASS. Its historical verdict semantics remain unchanged: a gate containing skips is `INCOMPLETE`, while an explicit override remains `FOUNDER_ACTION_REQUIRED` or `BLOCKED_EXTERNAL`. The current release decision is based on the exact-main matrix and the J-series evidence, not on an unqualified `nur-gate.sh ALL` result.

## Classification vocabulary

| Classification | Meaning in this reconciliation |
|---|---|
| `CURRENT_REQUIREMENT` | The skipped item maps directly to a current applicable Addendum requirement and still needs its own proof. |
| `SUPERSEDED` | The historical check is replaced by a newer, narrower, or differently structured current contract. |
| `ALREADY_PROVEN` | A current exact-main gate or artifact proves the underlying requirement; the historical step is redundant or stale. |
| `APPLICABLE_AND_MISSING` | The requirement remains internal and applicable, but the current evidence is not yet sufficient. |
| `EXTERNAL` | Completion depends on a provider, sender, staging account, licensed service, or human action outside this repository and sandbox. |
| `DEFERRED_BY_FOUNDER_SCOPE` | The item is intentionally outside the current founder-approved release slice and must remain explicitly labeled as deferred. |
| `STALE_GATE_IMPLEMENTATION` | The historical runner encodes an obsolete product shape, gate ID, or proof mechanism and should not be used as a current PASS/FAIL oracle. |

## G01 — Static, security, migration, and packaging skips

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `dependency_audit` | `CURRENT_REQUIREMENT` | Dependency provenance and vulnerability review remain part of the current static/security release boundary. Existing `npm ci` and lockfile checks are not the same as a complete cross-runtime audit. | Run or attach a reproducible API/web dependency audit and record the exact SHA. |
| `sbom` | `CURRENT_REQUIREMENT` | The current packaging requirement explicitly calls for a secret-free SBOM. The historical runner’s “no generator” note is stale after `infra/scripts/generate_sbom.py` became available. | Generate the final SBOM only for the exact release SHA and include its digest in the artifact index. |
| `migration_upgrade_from_populated` | `CURRENT_REQUIREMENT` | Forward migration safety from a populated database remains applicable to the recovery and exact-main release boundary. | Execute the isolated populated-revision upgrade receipt or record a narrowly scoped external/runtime hold. |
| `migration_downgrade` | `STALE_GATE_IMPLEMENTATION` | The current operational contract uses forward migrations plus verified backup/restore; routine destructive downgrade execution is not the release rollback contract. | Do not label the old downgrade skip as a product PASS. Replace it with the current restore/rollback proof. |
| `fresh_extract_boot` | `CURRENT_REQUIREMENT` | J1 requires a cold boot from a fresh extract/package, not merely a warm development server. | Run the isolated fresh-extract boot and record readiness, process, and seed receipts. |

## G03 — V197 control and surface skips

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `deferred_controls` | `DEFERRED_BY_FOUNDER_SCOPE` | Honest disabled or not-yet-visible capabilities remain outside the current V197 presentation slice. They must not be turned into fake enabled controls. | Keep each control labeled disabled/deferred in the current matrix and do not count it as a PASS. |
| `backend_only_surfaces` | `STALE_GATE_IMPLEMENTATION` | The historical gate assumes that every backend-only domain must already be reachable from the V197 shell. The current matrix records route ownership and reachability separately, including Personal Memory and Teach NUR gaps. | Retain the current route-specific dispositions; do not use this aggregate historical skip as a release verdict. |

## G04 — Performance, accessibility, and device skips

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `named_reference_devices` | `ALREADY_PROVEN` | The current Playwright projects declare Chromium desktop/mobile, WebKit iPhone, iPad, and desktop Safari tiers. The responsive matrix was executed on those declared dimensions. Large Desktop Safari page crashes are separately classified as an external WebKit runtime boundary, not silently passed. | Keep the device matrix and the J8 WebKit hold classification as the evidence of record. |
| `heap_soak` | `CURRENT_REQUIREMENT` | A bounded ten-minute performance/heap soak remains distinct from short acceptance checks. | Execute the explicit soak when runtime resources permit; do not infer it from ordinary browser passes. |

## G05 — Live AI/provider skips and overrides

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `live_two_turn_proof` when `.env.local` is absent | `ALREADY_PROVEN` for this local evidence window | The exact-main application path was rerun with a server-only credential boundary and endpoint-supported `gpt-4.1-mini`. Direct provider smoke, Chromium UI smoke, and the two-turn reload proof all returned live OpenAI results with no key printed. CI still cannot reproduce this without a securely supplied credential. | Keep the local live proof receipt, mark credential availability as environment-specific, and never inherit it into CI without a fresh exact-SHA run. |
| `budget_enforcement` | `CURRENT_REQUIREMENT` | Per-user/provider budget enforcement remains applicable. The old skip correctly identified a gap; the new live proof does not prove budget exhaustion or multi-scope accounting. | Run the budget-specific tests and retain the remaining internal hold if coverage is incomplete. |

## G06 — Account recovery delivery skips and override

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `FOUNDER_ACTION_REQUIRED_CONFIGURE_EMAIL_PROVIDER` | `EXTERNAL` | Local password-recovery and token-revocation tests pass, but production transactional delivery requires a verified sender/provider and account configuration. | Retain as an explicit external hold; do not claim production email delivery. |
| `production_delivery` | `EXTERNAL` | Delivery is not a sandbox-only implementation detail; it requires a real transactional provider. | Record provider and sender verification outside the source artifact when available. |
| `retry_dedup_bounce` | `EXTERNAL` | Delivery retry, bounce, and dead-letter behavior depends on the configured mail transport and its operational callbacks. | Keep unproven until a real delivery adapter and receipt exist. |

## G07 — Intelligence and Agentend skips

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `eval_suite` | `APPLICABLE_AND_MISSING` | The current Addendum still calls for an evaluation corpus covering multilingual, adversarial, and safety regressions. Ordinary unit tests are not an evaluation corpus. | Build or attach the bounded evaluator receipt, or retain an internal hold. |
| `tool_registry` | `ALREADY_PROVEN` | The historical “no bounded tool registry” assertion is stale: the current tree contains the Agentic registry, capability policy, approval, dispatch, and recovery suites. | Cite the current registry and Agentend test receipts rather than running the obsolete skip. |
| `whole_chain_runtime` | `APPLICABLE_AND_MISSING` | A single exact-main proof covering Talk → persisted Return → evidence/why-changed remains stronger than independent unit seams. | Run the current full-chain proof or retain an internal hold. |

## G08 — Billing and entitlement skips and override

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `FOUNDER_ACTION_REQUIRED_CONFIGURE_BILLING_TEST_PROVIDER` | `EXTERNAL` | Billing API contracts and safe UI fallbacks are locally testable; real checkout/webhook/refund/provider test mode requires an external billing account. | Keep provider configuration and payment evidence external. |
| `provider_test_mode` | `EXTERNAL` | A live provider test mode cannot be fabricated from local billing mocks. | Require a real test-provider receipt before claiming end-to-end billing. |
| `billing_ui` | `STALE_GATE_IMPLEMENTATION` | The old note that billing has no V197 control is stale relative to the current owner-product-surface browser proof; the remaining limitation is live provider proof, not absence of all UI. | Use the current route proof and external provider disposition. |

## G09 — Glow/progression skips

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `fraud_detection` | `APPLICABLE_AND_MISSING` | Abuse-safe reward behavior is a current requirement, and the historical runner explicitly acknowledges the missing fraud/abuse controls. | Add bounded fraud/abuse evidence or retain the internal hold. |
| `leaderboards` | `SUPERSEDED` | Leaderboards are not part of the current bounded owner-progression release contract. | Do not reopen a retired product surface solely to satisfy the historical gate. |
| `notification_delivery` | `EXTERNAL` | Push/email delivery requires external adapters; local in-app notification behavior is not delivery proof. | Keep provider delivery external. |
| `experiment_engine` | `SUPERSEDED` | No current Master Addendum requirement requires an experiment engine for this release slice. | Preserve the historical note as superseded, not as a hidden missing PASS. |

## G10 — Systems skip

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `per_system_vertical_slice` | `STALE_GATE_IMPLEMENTATION` | The historical gate encodes a broader per-System diagnostic/action/Return projection shape than the current six-System V197 contract. Current Systems geometry and route proofs are the applicable evidence. | Keep the current six-System contract and do not restore retired seven-System assertions. |

## G11 — Language skips and override

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `catalog_completeness` | `APPLICABLE_AND_MISSING` | Current locale fallback and language-safety requirements still need key-completeness evidence. | Add the validator or retain the internal hold. |
| `locale_slots_35` | `SUPERSEDED` | The current release does not promise thirty-five locale slots. | Do not use the retired count as a release gate. |
| `string_extraction` | `APPLICABLE_AND_MISSING` | Zero-raw-string extraction remains a current quality requirement where applicable. | Add the extraction check or retain an internal hold. |
| `FOUNDER_ACTION_REQUIRED_LOCALE_HUMAN_REVIEW` | `EXTERNAL` | Native-language and RTL review is a human qualification, not an agent self-certification. | Require founder/qualified reviewer sign-off before claiming reviewed-native status. |

## G12 — Community skips

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `realtime_gateway` | `APPLICABLE_AND_MISSING` | The current community matrix still identifies realtime as incomplete where that surface is in scope. | Implement and prove the bounded authenticated gateway, or explicitly remove/defer the surface. |
| `signal_feed` | `APPLICABLE_AND_MISSING` | Owner-safe signals/feed behavior remains a current partial area rather than a proven release capability. | Complete the bounded feed contract or keep the internal hold. |
| `anti_abuse` | `APPLICABLE_AND_MISSING` | Social anti-abuse coverage remains a current internal gap. | Add abuse tests and operational boundaries. |

## G13 — Group research skips and override

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `BLOCKED_EXTERNAL` live-research override | `EXTERNAL` | Research Brain and supplied-source analysis are locally bounded, but lawful live retrieval needs an external provider/connector and policy configuration. | Keep live fetch blocked and disclose the provider boundary. |
| `live_research` | `EXTERNAL` | No live research-provider success may be inferred from local fixtures. | Require a real provider receipt before enabling live retrieval. |
| `expert_module` | `APPLICABLE_AND_MISSING` | Expert verification is an internal capability gap separate from external retrieval. | Implement bounded expert verification or retain the internal hold. |

## G14 — Projects/agent-run skip

| Historical step | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `bounded_agents` | `APPLICABLE_AND_MISSING` | Current Agentend requirements cover bounded proposals, approvals, capabilities, recovery, and evidence; the historical aggregate skip still maps to missing breadth and browser recovery proof. | Complete the missing bounded registry/evidence UI proof or retain the internal hold. |

## G15 — Operations, staging, restore, and privacy skips and override

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `FOUNDER_ACTION_REQUIRED_STAGING_ACCESS` | `EXTERNAL` | A real staging deployment and CI execution require repository/environment access outside the local sandbox. | Require exact-main GitHub Actions and staging receipts when available. |
| `staging_deploy` | `EXTERNAL` | No local substitute is equivalent to a real staging deployment. | Keep staging explicitly external. |
| `timed_restore_drill` | `CURRENT_REQUIREMENT` | J2/J3 require verified backup/restore evidence with measured or explicitly bounded RPO/RTO. | Run the isolated final drill and record measurements; do not infer it from unit tests. |
| `privacy_center` | `APPLICABLE_AND_MISSING` | Account export/deletion/privacy lifecycle is an internal current gap, not an external provider limitation. | Implement the current privacy surface or retain the internal hold. |

## G16 — Full-release skips and override

| Historical step or override | Classification | Current interpretation and evidence | Required disposition |
|---|---|---|---|
| `FOUNDER_ACTION_REQUIRED_RELEASE_APPROVAL` | `EXTERNAL` | Founder release approval is a human release-control dependency and cannot be inferred from tests. | Record explicit approval before any FULL_PASS/tag decision. |
| `all_gates_pass` | `CURRENT_REQUIREMENT` | The exact-main release contract still requires every applicable requirement to be green or explicitly external/deferred. | Recompute from the final matrix; never treat the historical skip as PASS. |
| `package_release` | `CURRENT_REQUIREMENT` | The final package must bind to the exact merged main SHA and be independently verifiable. | Emit only after the required gate receipts are complete. |
| `verify_release_package` | `CURRENT_REQUIREMENT` | Independent extraction, manifest, source-SHA, secret, and integrity checks remain mandatory. | Run the verifier against the final package and preserve its output. |
| `sbom` | `CURRENT_REQUIREMENT` | I7 is a current release requirement, even though the historical runner predates the generator. | Generate and bind the SBOM to the final package. |
| `status_ledger_v6` | `STALE_GATE_IMPLEMENTATION` | The current completion contract supersedes the old missing V6 ledger with the requirement matrix, gate status, evidence index, external blocker, and Codex takeover artifacts. | Publish the current documents; do not author a duplicate stale ledger solely for G16. |

## Overrides not produced by skips

The following historical overrides remain release controls rather than evidence of product failure: the unrotated historical-key check in G00 is `EXTERNAL` until a founder verifies rotation; email delivery, billing provider mode, locale human review, live research, staging access, and final release approval are all `EXTERNAL`. The local J6 provider proof is now independently recorded as live success for the exact application path; it must not be copied into a CI result without rerunning with a securely supplied credential.

## Reconciliation conclusion

The historical runner is useful as a map of prior concerns but is **not a complete current release runner**. Its skips divide into four groups: stale checks replaced by the current matrix, current internal requirements still missing, genuine external dependencies, and explicit deferred scope. No skipped line is silently counted as PASS. The final verdict must therefore be computed from the current exact-main matrix, current CI checks, J-series receipts, artifact verification, and founder release approval.
