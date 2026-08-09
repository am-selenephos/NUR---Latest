# Historical capability gap map - V6 (superseded snapshot)

Historical candidate `6d7eeefe6e3923015de879719e1a09056f30a6ce` | 2026-07-25 | 229 requirements.

Historical source: `/home/nur/NUR-V5-100-COMPLETION/REQUIREMENT_MATRIX.csv`.

This document is retained for provenance. Its percentages, counts, file-presence claims, and gate
states are not current completion truth and must not be quoted as such.

## Reconciliation overlay at `7df3ade`

- PR #19 readiness is green on this exact baseline, but it is a bounded readiness lane rather than
  full release proof.
- The current founder-locked Systems are six: Ambition, Rebuild, Creation, Growth,
  Introspection, and Connection. The former seven-System rows below are superseded.
- Talk now enters the Mind cognitive loop: scope resolves before retrieval, capability routing and
  bounded hydration run before Brain/provider invocation, and workflow proposals pass to Agency.
- The sealed capability registry currently contains two capabilities. This is integrated partial
  coverage, not the complete Cognitive OS catalog.
- Agency now has typed tools, policy/compiler/runtime, exact-call approvals, outbox/worker
  foundations, and owner-scoped read/approval routes. Direct owner create/start/cancel/retry routes
  and the complete V197 owner Agent surface remain open.
- WhyChanged and the owner-scoped Hardness schema are present. Hardness training is constrained to
  `DRY_RUN`; there is no complete public Hardness product surface or autonomous promotion path.
- Documentation and evidence still require an exact-head completion ledger, current route/control
  matrices, broader browser/provider proof, release packaging, and external-provider acceptance.

`BACKEND_ONLY` and `UI_ONLY` are failing statuses: the orchestrator states neither is
product-complete. `UNPROVEN` means the code exists but the required runtime evidence has not
been captured on this candidate — it is never counted as green.

## Historical summary (do not use as a current percentage)

| Gate | Reqs | PASS | PARTIAL | UNPROVEN | BACKEND_ONLY | MISSING | BLOCKED_EXT | FOUNDER |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `G00_EVIDENCE` | 7 | 1 | 4 | 0 | 0 | 0 | 0 | 2 |
| `G01_STATIC` | 17 | 11 | 0 | 4 | 0 | 2 | 0 | 0 |
| `G02_AUTH` | 17 | 8 | 4 | 0 | 1 | 4 | 0 | 0 |
| `G03_V197` | 14 | 1 | 3 | 6 | 3 | 1 | 0 | 0 |
| `G04_PERFORMANCE` | 14 | 0 | 0 | 14 | 0 | 0 | 0 | 0 |
| `G05_LIVE_AI` | 14 | 6 | 4 | 1 | 0 | 1 | 2 | 0 |
| `G06_RECOVERY` | 8 | 2 | 3 | 1 | 0 | 1 | 1 | 0 |
| `G07_INTELLIGENCE` | 15 | 1 | 9 | 0 | 2 | 2 | 1 | 0 |
| `G08_REVENUE` | 12 | 0 | 5 | 1 | 0 | 5 | 1 | 0 |
| `G09_GLOW` | 16 | 0 | 12 | 0 | 0 | 4 | 0 | 0 |
| `G10_SYSTEMS` | 9 | 0 | 9 | 0 | 0 | 0 | 0 | 0 |
| `G11_LANGUAGE` | 13 | 0 | 5 | 3 | 0 | 4 | 0 | 1 |
| `G12_COMMUNITY` | 14 | 1 | 10 | 0 | 0 | 3 | 0 | 0 |
| `G13_GROUP_RESEARCH` | 10 | 0 | 7 | 0 | 0 | 2 | 1 | 0 |
| `G14_PROJECTS` | 14 | 0 | 11 | 0 | 0 | 3 | 0 | 0 |
| `G15_SCALE_OPS` | 21 | 0 | 10 | 3 | 0 | 7 | 1 | 0 |
| `G16_FULL_RELEASE` | 14 | 0 | 3 | 2 | 0 | 8 | 0 | 1 |
| **total** | **229** | **31** | **99** | **35** | **6** | **47** | **7** | **4** |

## Historical detail by gate

### G00_EVIDENCE

- **G00-001 Source authority + conflict ledger** — `PARTIAL`  
  gap: No docs/v6/conflict-and-supersession-report.md; V197 hash conflict unrecorded
- **G00-002 Canonical V197 source identity** — `FOUNDER_ACTION_REQUIRED`  
  gap: Plan pins 252eee80...; repo pins d4f7f2d3... Commit f8ddd7a (2026-07-18) rebuilt canonical via rebuild-v197-canonical.mjs AFTER plan lock
- **G00-003 Prior audit claim verification** — `PARTIAL`  
  gap: CSV artifact not yet written
- **G00-004 Historical archives containing live credentials** — `FOUNDER_ACTION_REQUIRED`  
  gap: Leaked keys not proven rotated; archives not regenerated without dotfiles
- **G00-005 GitHub/local divergence** — `PARTIAL`  
  gap: Divergence not yet written to a repo document
- **G00-007 Required repository documents** — `PARTIAL`  
  gap: missing: current-capability-gap-map, memory-learning-consent, adaptive-interface-spec, internet-verification-threat-model, engagement-policy, signal-feed-ranking, privacy-data-retention, moderation-safety-plan, deployment-sre-runbook, test-evaluation-plan, release-evidence

### G01_STATIC

- **G01-006 Production build** — `UNPROVEN`  
  gap: Not re-run on this candidate this session
- **G01-007 Mobile typecheck/build** — `UNPROVEN`  
  gap: Script declared; not run this session; apps/mobile completeness unverified
- **G01-009 Dependency audit / SBOM** — `MISSING`  
  gap: No SBOM generator, no dependency audit gate in repo
- **G01-014 Upgrade from populated prior revision** — `MISSING`  
  gap: No test upgrades a populated pre-0030 database
- **G01-015 Downgrade / rollback migration** — `UNPROVEN`  
  gap: Downgrade functions exist per revision but no test executes downgrade
- **G01-017 Clean boot from fresh clone/extract** — `UNPROVEN`  
  gap: boot-smoke.sh exists; not executed against a fresh extract this session

### G02_AUTH

- **G02-005 CSRF / origin enforcement** — `PARTIAL`  
  gap: Double-submit CSRF implemented; no full forged-origin x mutation matrix test
- **G02-006 Rate limiting** — `PARTIAL`  
  gap: Fixed-window Redis limiter works; fails OPEN in development; no distributed/bypass/race test
- **G02-009 Reset replay/race/expiry** — `PARTIAL`  
  gap: Replay/expiry covered; concurrent-race test not present
- **G02-012 Email verification** — `MISSING`  
  gap: No email verification implementation
- **G02-013 Security/session management UI** — `MISSING`  
  gap: No security-sessions surface or route; V5 SEC-001 requirement unmet
- **G02-014 Account export** — `BACKEND_ONLY`  
  gap: Omega export foundation exists; settings.export is NOT_IMPLEMENTED_VISIBLE in the control matrix
- **G02-015 Account deletion + receipts** — `MISSING`  
  gap: settings.delete is NOT_IMPLEMENTED_VISIBLE; no deletion_requests lifecycle
- **G02-016 Audit records** — `PARTIAL`  
  gap: Audit service exists; retention/redaction/export tests absent
- **G02-017 Full account-lifecycle E2E** — `MISSING`  
  gap: No single E2E covers the whole chain; export and delete legs do not exist

### G03_V197

- **G03-002 One Entry stage / one Universe stage** — `UNPROVEN`  
  gap: v197-forensic-shell.spec.ts asserts it; suite not run this session
- **G03-003 No React visual owner** — `UNPROVEN`  
  gap: v197-host-parity.spec.ts asserts it; not run this session
- **G03-004 No hidden duplicate shell** — `PARTIAL`  
  gap: rebuild-v197-canonical.mjs pruned duplicates; residual Base64 constants still embedded in the host
- **G03-005 Route/session lifecycle cleanup** — `UNPROVEN`  
  gap: v197-runtime-lifecycle.spec.ts exists; not run this session
- **G03-006 Every visible control classified** — `PARTIAL`  
  gap: docs/release/v197-control-matrix.json: 73 LIVE_REAL, 8 INTENTIONAL_LOCAL_ONLY, 7 NOT_IMPLEMENTED_VISIBLE, 2 BLOCKED_BY_EXTERNAL_PROVIDER, 0 BROKEN. Matrix generated_from_sha=33a5dab (a different worktree) so it is STALE for 6d7eeef
- **G03-007 Seven deferred visible controls** — `MISSING`  
  gap: All 7 remain NOT_IMPLEMENTED_VISIBLE
- **G03-008 Personal Memory reachable from V197** — `BACKEND_ONLY`  
  gap: api/v1/memory.py + models/memory.py + migration 0023 exist; no control in the V197 matrix
- **G03-009 Teach NUR reachable from V197** — `BACKEND_ONLY`  
  gap: app/learning/ + migration 0024 exist; no control in the V197 matrix
- **G03-010 Billing reachable from V197** — `BACKEND_ONLY`  
  gap: app/billing/ + migration 0025 exist; no control in the V197 matrix
- **G03-011 Capsule creation from V197** — `PARTIAL`  
  gap: capsule.copy is INTENTIONAL_LOCAL_ONLY; capsules API + tests exist; owner creation UI unproven
- **G03-012 No native white controls** — `UNPROVEN`  
  gap: v197-adjunct-forensic-style.spec.ts asserts styling; not run this session
- **G03-013 Desktop and mobile parity** — `UNPROVEN`  
  gap: chromium-desktop and chromium-mobile projects configured; not run this session
- **G03-014 Physical viewport centring** — `UNPROVEN`  
  gap: Centring assertions exist in the V197 specs; the 4-viewport x 2-direction matrix is not proven

### G04_PERFORMANCE

- **G04-001 Chrome performance trace** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-002 RAF/canvas/listener/observer inventory** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-003 Long-task and LoAF attribution** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-004 Heap at 0s / 60s / 600s** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-005 Route/auth/Talk soak** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-006 Critical interaction timing** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-007 Bundle and font waterfall** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-008 Desktop galaxy FPS** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-009 Mobile galaxy FPS** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-010 Reduced motion** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-011 Cross-browser matrix** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-012 Keyboard-only + automated a11y** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-013 Long strings and RTL layout** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared
- **G04-014 Contractual centring delta** — `UNPROVEN`  
  gap: No measurement captured on 6d7eeef this session; named reference devices not declared

### G05_LIVE_AI

- **G05-002 Responses API via official SDK** — `PARTIAL`  
  gap: apps/api/app/ai/openai_provider.py implements the adapter; Responses-API conformance not re-verified this session
- **G05-004 Real semantic SSE stream** — `PARTIAL`  
  gap: app/api/v1/cognition.py streams; event-family conformance to the V5 list unproven
- **G05-008 MODEL_GENERATED response persisted + refresh** — `BLOCKED_EXTERNAL`  
  gap: Proven in worktree NUR-LIVE-TALK-PROOF-20260723 at 33a5dab; NOT proven on 6d7eeef (no .env.local here)
- **G05-009 Second turn succeeds** — `BLOCKED_EXTERNAL`  
  gap: live-talk-two-turn-proof.mjs exists; requires a configured key on this candidate
- **G05-010 Cancel succeeds** — `UNPROVEN`  
  gap: No cancel test found for the Talk stream path
- **G05-011 Reconnect / idempotence** — `PARTIAL`  
  gap: migration 0021_talk_stream_idempotency + test_cognition_streaming.py exist; reconnect not browser-proven
- **G05-013 Budgets enforced** — `MISSING`  
  gap: No budget enforcement module found in app/ai or app/cognition
- **G05-014 Prompt logging off by default** — `PARTIAL`  
  gap: Structured logging exists; no explicit test asserting prompts are never logged

### G06_RECOVERY

- **G06-001 Production email adapter** — `BLOCKED_EXTERNAL`  
  gap: app/services/password_delivery.py exists; no production provider configured
- **G06-003 Reset/verification templates** — `PARTIAL`  
  gap: Reset template path exists; verification template absent (see G02-012)
- **G06-004 Delivery retry/dedup/bounce** — `MISSING`  
  gap: No retry/dedup/bounce handling in password_delivery.py
- **G06-006 Origin validation** — `PARTIAL`  
  gap: Origin allowlist exists for API; public-origin binding for links unproven
- **G06-007 Provider-disabled honest UI** — `UNPROVEN`  
  gap: Not asserted by a browser test
- **G06-008 Operational runbook** — `PARTIAL`  
  gap: RUNBOOK.md exists; no delivery-provider section

### G07_INTELLIGENCE

- **G07-001 Full vertical intelligence cycle** — `PARTIAL`  
  gap: Every stage has backend code and tests; no single proof runs the whole chain end to end in a browser
- **G07-002 Identity kernel + multilingual voice** — `PARTIAL`  
  gap: System prompt encodes the contract; no versioned identity kernel artifact or persona eval
- **G07-003 Working/episodic/semantic/procedural/social/evidence/self/goal/meta memory** — `PARTIAL`  
  gap: Personal memory spine (0023) + omega exist; the nine-layer taxonomy is not explicitly modelled
- **G07-004 Personal Memory viewer/editor/delete/export** — `BACKEND_ONLY`  
  gap: Routes + tests exist; no V197 control (see G03-008)
- **G07-005 Provenance and source minimality** — `PARTIAL`  
  gap: Evidence packet built and cited; minimality not measured by an eval
- **G07-006 Contradiction and freshness handling** — `PARTIAL`  
  gap: Omega contradiction model exists; freshness scoring unproven
- **G07-007 Corrections and belief revision** — `PARTIAL`  
  gap: Correction routes exist; why-changed chain not browser-proven
- **G07-008 Outcome learning** — `PARTIAL`  
  gap: Models and services exist; calibration eval absent
- **G07-009 Omega consolidation/review/why-changed/export** — `PARTIAL`  
  gap: test_omega.py passes; scheduler idempotence/replay/rollback unproven
- **G07-010 Teach NUR quarantine + poisoning defence** — `BACKEND_ONLY`  
  gap: Migration 0024 + test_teach_nur.py exist; no V197 control (see G03-009)
- **G07-011 Research/Web gateway with citations** — `BLOCKED_EXTERNAL`  
  gap: research.live-fetch is BLOCKED_BY_EXTERNAL_PROVIDER in the control matrix
- **G07-012 Bounded tools with confirmation** — `SUPERSEDED`
  current overlay: Agency now has a typed registry, risk policy, and exact-call approvals; broader
  capability coverage and complete owner lifecycle proof remain open
- **G07-013 Multilingual/adversarial evaluation** — `MISSING`  
  gap: No packages/evals; no regression eval harness
- **G07-015 No false sentience claims** — `PARTIAL`  
  gap: Prompt forbids it; no adversarial persona eval proves it

### G08_REVENUE

- **G08-001 Plans / customers / subscriptions / entitlements** — `PARTIAL`  
  gap: app/billing/ + models/billing.py + migration 0025 + test_billing.py exist
- **G08-002 Provider test-mode checkout** — `BLOCKED_EXTERNAL`  
  gap: No billing provider configured; Lemon Squeezy is the plan's first candidate
- **G08-003 Signed webhook verification** — `PARTIAL`  
  gap: hmac.compare_digest verification present; no live provider signature fixture
- **G08-004 Replay/out-of-order/duplicate handling** — `PARTIAL`  
  gap: webhook_receipts modelled; out-of-order matrix test absent
- **G08-005 Entitlement survives refresh/relogin** — `UNPROVEN`  
  gap: No browser proof
- **G08-006 Billing UI in canonical V197** — `MISSING`  
  gap: No billing control in the V197 control matrix
- **G08-007 Receipts** — `MISSING`  
  gap: No receipt surface
- **G08-008 Accessible cancellation** — `MISSING`  
  gap: No cancellation surface
- **G08-009 Refund / past-due / expiry states** — `PARTIAL`  
  gap: Entitlement states modelled; state-transition E2E absent
- **G08-010 Privacy policy / terms / refund policy links** — `MISSING`  
  gap: No legal surface links found
- **G08-011 API-boundary entitlement + cost enforcement** — `PARTIAL`  
  gap: Feature-lock endpoints exist (test_feature_lock_endpoints.py); cost enforcement absent (see G05-013)
- **G08-012 Export / delete** — `MISSING`  
  gap: See G02-014 and G02-015

### G09_GLOW

- **G09-001 Append-only Glow ledger + balance** — `PARTIAL`  
  gap: app/services/glow_service.py + migration 0026 + api/v1/glow.py exist
- **G09-002 Verified earning rules** — `PARTIAL`  
  gap: Rules exist; the full V5 earn-rule table is not proven complete
- **G09-003 Caps and multipliers** — `PARTIAL`  
  gap: Modelled; abuse suite absent
- **G09-004 Idempotency** — `PARTIAL`  
  gap: Modelled; replay test not confirmed
- **G09-005 Reversal** — `PARTIAL`  
  gap: glow_reversals modelled; no appeal flow
- **G09-006 Fraud flags** — `MISSING`  
  gap: No fraud detection implementation
- **G09-007 XP and levels** — `PARTIAL`  
  gap: Migration 0026 covers progression; level UI unproven
- **G09-008 Achievements and reward inventory** — `PARTIAL`  
  gap: Modelled; not browser-proven
- **G09-009 Streaks with timezone/DST/grace/repair** — `PARTIAL`  
  gap: Modelled; no timezone/DST test
- **G09-010 Capacity-aware quests** — `PARTIAL`  
  gap: Modelled; capacity linkage unproven
- **G09-011 Opt-in reputation/leaderboards** — `MISSING`  
  gap: No leaderboard implementation
- **G09-012 Deterministic engagement policy** — `PARTIAL`  
  gap: app/services/engagement_policy.py + models/engagement.py exist; reason-code audit unproven
- **G09-013 Notification preferences + categories/channels/quiet hours** — `PARTIAL`  
  gap: api/v1/notifications.py + migration 0020 + test_notifications.py exist
- **G09-014 Real push/email sandbox delivery** — `MISSING`  
  gap: No push or email delivery adapter for notifications
- **G09-015 Experiment assignment/exposure/guardrails/stop/rollback** — `MISSING`  
  gap: No experiment tables or service
- **G09-016 No reward from crisis/pain/time-spent** — `PARTIAL`  
  gap: Policy stated in engagement_policy.py; no test proves the exclusions

### G10_SYSTEMS

The old seven-System structure is superseded. Structural truth at `7df3ade` is:

- **G10-sys1 Star System: Ambition** — `PARTIAL`
- **G10-sys2 Star System: Rebuild** — `PARTIAL`
- **G10-sys3 Star System: Creation** — `PARTIAL`
- **G10-sys4 Star System: Growth** — `PARTIAL`
- **G10-sys5 Star System: Introspection** — `PARTIAL`
- **G10-sys6 Star System: Connection** — `PARTIAL`

For each System, backend/lens foundations exist; this overlay does not claim the complete
diagnostic -> action -> Return -> projection browser slice on the current docs commit.
- **G10-008 System progress + Body/Mind/Life composition** — `PARTIAL`  
  gap: Progress calculation exists; explainability surface and versioned weights unproven
- **G10-009 Today computed from real state** — `PARTIAL`  
  gap: Today surface exists; deterministic fixture-to-output test and Low Day Mode unproven

### G11_LANGUAGE

- **G11-001 One catalog architecture** — `PARTIAL`  
  gap: apps/api/app/i18n/ + packages/ exist; packages/i18n as specified not confirmed
- **G11-002 All first-party strings extracted** — `MISSING`  
  gap: No extraction test enforcing zero raw strings
- **G11-003 Zero missing keys** — `MISSING`  
  gap: No key-completeness validator
- **G11-004 35 locale slots** — `MISSING`  
  gap: Repo carries a small locale set, not 35 slots
- **G11-005 Locale/script/direction metadata** — `PARTIAL`  
  gap: Direction handling exists in the V197 i18n bridge
- **G11-006 Mixed bidi correctness** — `UNPROVEN`  
  gap: v197-language-wordmark.spec.ts covers wordmark; full bidi matrix unproven
- **G11-007 Dates/numbers/forms per locale** — `UNPROVEN`  
  gap: Not asserted by tests
- **G11-008 Long-string and mobile layout tests** — `UNPROVEN`  
  gap: Not asserted on this candidate
- **G11-009 Dynamic translation + View Original** — `PARTIAL`  
  gap: api/v1/translations.py + migration 0027 + test_translations.py exist; View Original control unproven
- **G11-010 Glossary/version/cache/feedback** — `PARTIAL`  
  gap: Translation contract migration exists; glossary absent
- **G11-011 Privacy-scope preservation in translation** — `PARTIAL`  
  gap: Scope model exists; no test proves the boundary
- **G11-012 Honest quality labels** — `MISSING`  
  gap: No per-locale quality-state field surfaced
- **G11-013 Priority locale human review** — `FOUNDER_ACTION_REQUIRED`  
  gap: Human/founder review cannot be performed by an agent

### G12_COMMUNITY

- **G12-001 Real multi-user posts/comments/reactions/saves/follows** — `PARTIAL`  
  gap: app/community/ + community_social.py + migration 0017/0028 + test_community_completion.py exist
- **G12-002 Post revisions** — `PARTIAL`  
  gap: Modelled; unproven in UI
- **G12-003 Connections** — `PARTIAL`  
  gap: Routes exist; lifecycle unproven
- **G12-004 Rooms + membership + roles** — `PARTIAL`  
  gap: test_group_nur.py covers room scope
- **G12-005 Sequenced messages** — `PARTIAL`  
  gap: Modelled; sequence guarantees unproven
- **G12-006 Authenticated realtime + reconnect** — `MISSING`  
  gap: No realtime gateway found
- **G12-007 Block/mute/report** — `PARTIAL`  
  gap: community_moderation.py + migration 0028 exist
- **G12-008 Moderation queue/actions/audit/appeals** — `PARTIAL`  
  gap: Queue and actions modelled; appeals unproven
- **G12-009 Translation + View Original in community** — `PARTIAL`  
  gap: Translation service exists; community integration unproven
- **G12-010 Opt-in reputation** — `PARTIAL`  
  gap: reputation events modelled
- **G12-011 Explainable Signal Feed with stop points** — `MISSING`  
  gap: No feed ranking module
- **G12-013 Anti-abuse tests** — `MISSING`  
  gap: No anti-abuse suite
- **G12-014 No fake population** — `PARTIAL`  
  gap: migration 0018_council_demo_markers marks demo rows; no test asserts exclusion from counts

### G13_GROUP_RESEARCH

- **G13-001 Room-scoped Group NUR** — `PARTIAL`  
  gap: app/api/v1/group_research.py + migration 0016/0029 + test_group_nur.py exist
- **G13-002 Decisions / tensions / minority views** — `PARTIAL`  
  gap: Modelled; unproven in UI
- **G13-003 Questions / corrections / versions** — `PARTIAL`  
  gap: Modelled
- **G13-004 Consultation state machine ORIENT->GATHER->MAP->MOVE->RETURN** — `PARTIAL`  
  gap: api/v1/consultations.py + migration 0019 + test_consultations.py exist; full cycle E2E unproven
- **G13-005 Lawful Research/Web retrieval** — `BLOCKED_EXTERNAL`  
  gap: research.live-fetch BLOCKED_BY_EXTERNAL_PROVIDER
- **G13-006 Citations + counter-sources + freshness** — `PARTIAL`  
  gap: Grounding contract enforced in prompts; live source records absent
- **G13-007 Watchlists / change detection** — `MISSING`  
  gap: No watchlist scheduler
- **G13-008 PII minimisation + untrusted-content isolation** — `PARTIAL`  
  gap: Prompt treats evidence as untrusted data; no gateway to test
- **G13-009 Expert identity/credential/conflict verification** — `MISSING`  
  gap: No expert module
- **G13-010 Tender Insight uncertainty and revision** — `PARTIAL`  
  gap: insights.py exists; tender-specific contract absent

### G14_PROJECTS

- **G14-001 Project Orbits + members + permissions** — `PARTIAL`  
  gap: app/api/v1/projects.py + models/projects.py + migration 0014/0030 + test_am_projects.py exist
- **G14-002 Tasks/milestones/blockers/decisions/evidence** — `PARTIAL`  
  gap: Modelled and tested
- **G14-003 Files and deliverables** — `PARTIAL`  
  gap: test_am_project_storage.py passes
- **G14-004 Encrypted owner-scoped object metadata** — `PARTIAL`  
  gap: app/services/object_storage.py exists; encryption-at-rest claim unproven
- **G14-005 MIME/size/malware/quota validation** — `PARTIAL`  
  gap: Quota and MIME/size covered by test_am_project_quota.py; no malware scan
- **G14-006 Signed short-lived access** — `PARTIAL`  
  gap: Implemented; expiry/race test unproven
- **G14-007 Deletion/export lifecycle** — `PARTIAL`  
  gap: storage_hygiene.py + test_storage_hygiene.py exist
- **G14-008 Bounded agent tasks/runs/artifacts/reviews** — `SUPERSEDED`
  current overlay: Agentic workflow/run foundations exist; project-owner lifecycle/UI proof remains open
- **G14-009 Capabilities, budgets, cancel, rollback** — `SUPERSEDED`
  current overlay: tool capabilities, policy, budgets, recovery primitives, and runtime exist;
  complete direct owner cancel/retry lifecycle remains open
- **G14-010 Human approval before irreversible actions** — `SUPERSEDED`
  current overlay: exact-call approval infrastructure exists; complete headed owner proof remains open
- **G14-011 Timeline/Insights/Glow/Capsule projection** — `PARTIAL`  
  gap: Projection routes exist; parity unproven
- **G14-012 Capsule creation from canonical V197** — `PARTIAL`  
  gap: See G03-011
- **G14-013 Recipient grants/expiry/questions/immediate revoke** — `PARTIAL`  
  gap: app/sharing/ + test_capsules.py + capsule.spec.ts exist; cache/race tests unproven
- **G14-014 Audit trail** — `PARTIAL`  
  gap: audit_service.py covers events

### G15_SCALE_OPS

- **G15-001 Installable PWA** — `PARTIAL`  
  gap: apps/web/public/manifest.webmanifest + offline.html exist; install proof absent
- **G15-002 Offline-safe drafts** — `MISSING`  
  gap: No offline draft store
- **G15-003 Reconnect/conflict/update behaviour** — `MISSING`  
  gap: see required_behavior
- **G15-004 Push permission UX** — `MISSING`  
  gap: see required_behavior
- **G15-005 Complete CI required gates** — `SUPERSEDED`
  current overlay: PR #19 readiness passed on `7df3ade`; full release gates remain incomplete
- **G15-006 Browser matrix in CI** — `UNPROVEN`  
  gap: see required_behavior
- **G15-007 Secret/dependency/SBOM scans** — `PARTIAL`  
  gap: secret-scan only
- **G15-008 Staging environment** — `BLOCKED_EXTERNAL`  
  gap: No staging environment available
- **G15-009 Health/readiness/synthetic probes** — `PARTIAL`  
  gap: app/api/v1/ops.py + test_health.py + test_ops_diagnostics.py exist
- **G15-010 Logs/metrics/traces/alerts** — `PARTIAL`  
  gap: app/observability/ exists; alerting absent
- **G15-011 Incident and rollback runbooks** — `PARTIAL`  
  gap: RUNBOOK.md exists; incident roles unproven
- **G15-012 Encrypted backup** — `PARTIAL`  
  gap: infra/scripts/dr-backup.sh + dev-backup.sh exist
- **G15-013 Isolated restore + timed drill + RPO/RTO** — `UNPROVEN`  
  gap: infra/scripts/dr-drill.sh + dr-restore.sh + test_dr.py exist; no timed drill executed on this candidate
- **G15-014 Graceful shutdown/draining** — `MISSING`  
  gap: see required_behavior
- **G15-015 Queue recovery / dead-letter** — `PARTIAL`  
  gap: domain_event_service.py outbox exists; dead-letter tooling absent
- **G15-016 Object reconciliation** — `PARTIAL`  
  gap: storage_hygiene.py
- **G15-017 Quotas / rate limits** — `PARTIAL`  
  gap: Upload quota + auth limits exist
- **G15-018 Bounded load test** — `PARTIAL`  
  gap: test_bounded_load.py exists; no recorded load report
- **G15-019 Privacy-center operations** — `MISSING`  
  gap: No privacy center
- **G15-020 Retention schedule + provider deletion** — `MISSING`  
  gap: see required_behavior
- **G15-021 Production configuration review** — `MISSING`  
  gap: see required_behavior

### G16_FULL_RELEASE

- **G16-001 Deterministic gate runner** — `MISSING`  
  gap: infra/scripts/release-gate.sh exists but is not the G00..G16 runner specified by the plan
- **G16-002 All applicable gates PASS on one candidate** — `MISSING`  
  gap: G00 through G15 are not all PASS
- **G16-003 No inherited evidence** — `PARTIAL`  
  gap: Live-Talk proof currently exists only at 33a5dab; the control matrix is generated_from_sha 33a5dab
- **G16-004 Fresh-clone / fresh-extract boot** — `UNPROVEN`  
  gap: infra/scripts/package-bootable.sh exists; not executed this session
- **G16-005 Package contents inspected + secret scanned** — `UNPROVEN`  
  gap: see required_behavior
- **G16-006 SBOM** — `MISSING`  
  gap: No SBOM generator
- **G16-007 Migration manifest** — `MISSING`  
  gap: see required_behavior
- **G16-008 Operations runbook** — `PARTIAL`  
  gap: RUNBOOK.md exists
- **G16-009 Rollback and restore evidence** — `MISSING`  
  gap: see required_behavior
- **G16-010 Founder demo and release scripts** — `PARTIAL`  
  gap: DEMO_SCRIPT.md + RUN_NUR.sh exist
- **G16-011 Status ledger updated to V6** — `MISSING`  
  gap: Not yet authored
- **G16-012 Seven release deliverables** — `MISSING`  
  gap: None produced
- **G16-013 Independent artifact verification** — `MISSING`  
  gap: infra/scripts/verify-release-package.sh does not exist
- **G16-014 Founder release approval** — `FOUNDER_ACTION_REQUIRED`  
  gap: Release approval is founder-controlled

## Historical backend-only examples

This incomplete table records the older candidate and must be re-audited against current V197
controls before assigning a present-day status:

| Requirement | Domain | Server side | Missing |
| --- | --- | --- | --- |
| G03-008 / G07-004 | Personal Memory | `app/api/v1/memory.py`, migration 0023 | viewer/editor/delete/export control |
| G03-009 / G07-010 | Teach NUR | `app/learning/`, migration 0024 | teach mode + review status control |
| G03-010 | Billing | `app/billing/`, migration 0025 | plan/checkout/portal/cancel control |
| G02-014 | Account export | Omega export foundation | `settings.export` is NOT_IMPLEMENTED_VISIBLE |

## Historical NOT_IMPLEMENTED_VISIBLE controls

From `docs/release/v197-control-matrix.json` (stale — regenerate on this candidate):
`plan.direction`, `community.legacy-tabs`, `ritual.control`, `voice.composer`,
`settings.export`, `settings.delete`, `community.future-tabs`.

## Historical required-document inventory

24 of the 35 documents named in Masterplan §30 exist. Missing: 
`docs/current-capability-gap-map.md`, `docs/memory-learning-consent.md`, `docs/adaptive-interface-spec.md`, `docs/internet-verification-threat-model.md`, `docs/engagement-policy.md`, `docs/signal-feed-ranking.md`, `docs/privacy-data-retention.md`, `docs/moderation-safety-plan.md`, `docs/deployment-sre-runbook.md`, `docs/test-evaluation-plan.md`, `docs/release-evidence.md`.
