# BLOCKERS — NUR V5 100% Completion

Candidate: `completion/nur-v5-full-pass` @ `6d7eeefe6e3923015de879719e1a09056f30a6ce`
Updated: 2026-07-25

Blockers are ordered by dependency, not by size. A `FOUNDER_ACTION_REQUIRED`
blocker never becomes PASS through agent work, and it prevents 100%.

---

## B1 — FOUNDER_ACTION_REQUIRED_CANONICAL_V197_HASH  (gate G00, blocks G03)

**Why required.** The binding V5 plan (§9.1, line 1243-1249) pins canonical V197 to
SHA-256 `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3`.
The repository pins and enforces
`d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6`.

This is not drift. Evidence:

- commit `6ce2c46` held a canonical host whose SHA-256 is **exactly** the plan value;
- commit `f8ddd7a` "Consolidate exact V197 star brain interface" (2026-07-18, five days
  **after** the plan lock) rebuilt the host via `apps/web/scripts/rebuild-v197-canonical.mjs`,
  which extracts the Base64 Entry/Universe documents, prunes dead legacy styles/scripts,
  and re-embeds them — size fell 1,029,176 → 718,041 bytes;
- that is exactly Masterplan §9.6 "Stage S — static-source extraction";
- the new hash is pinned in `scripts/check-v197-integrity.ts` and enforced by `npm run v197:integrity`;
- `f8ddd7a` is an ancestor of HEAD.

So the repository already advanced past the plan under the plan's own convergence design.
But product law says the canonical bytes/hash stand *unless the founder explicitly approves
a new canonical source*. That approval is not recorded anywhere.

**Founder action (local, no secret involved).**
Choose one and state it explicitly:

1. **Ratify** `d4f7f2d3…` as canonical (recommended — it is the pruned Stage-S product of the
   plan's own convergence path and is already gate-enforced); or
2. **Restore** `252eee80…` as canonical, which reverts the Stage-S pruning.

**Verification after the decision.**
```bash
cd /home/nur/NUR-INTEGRATION-20260722
sha256sum apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html
npm run v197:integrity
```

**Nothing to paste into chat.** No secret is involved in this decision.

**Independent work that continues now.** All of G01, G02 browser proofs, G04 measurement,
G07/G09/G10/G12/G14 implementation. Only the *final* G03 verdict and G16 packaging wait
on this ratification.

---

## B2 — WITHDRAWN by FD-002 — key rotation cancelled  (was gate G00)

**Status: CLOSED — superseded by founder decision FD-002 on 2026-07-25.**

The founder locked the existing key. It is reused unchanged; no rotation, revocation,
replacement, or regeneration. `FOUNDER_ACTION_REQUIRED_ROTATE_OPENAI_KEYS` is withdrawn and
must not be re-emitted.

Residual risk accepted by decision: archive copies of the key were readable at `~/Downloads`
before quarantine, so anyone who took a copy holds a working credential. The archives are now
owner-only at `/home/nur/NUR-QUARANTINE-SECRETS/` (700/600) and excluded from every release
path. Reviewing provider usage for unexpected spend remains worthwhile.

<details><summary>Original B2 text (historical)</summary>

## B2 — FOUNDER_ACTION_REQUIRED_ROTATE_OPENAI_KEYS  (gate G00, blocks G05)

**Why required.** The prior forensic audit found **three distinct live OpenAI API keys**
committed inside historical archive snapshots (`.env.local` / `.env` in snapshots 04, 06,
07, 08, 09). Current Git is clean — `npm run secret-scan` exits 0 — but a leaked key stays
live until it is revoked at the provider.

**Founder action.**
1. Revoke all three keys in the OpenAI dashboard.
2. Create one new key.
3. Configure it locally, never in chat:
```bash
bash /home/nur/NUR-INTEGRATION-20260722/infra/scripts/configure-openai-local.sh
```
That script writes a hidden-input value into ignored, mode-600 `.env.local`.

**What must never be pasted into chat, a log, a screenshot, a patch, or a report:**
the API key value itself.

**Verification after completion.**
```bash
cd /home/nur/NUR-INTEGRATION-20260722
bash infra/scripts/validate-openai-local.sh
npm run secret-scan
```

**Independent work that continues now.** Everything except the G05 live-run legs.

---

</details>

## B3 — SATISFIED — OpenAI configured on the completion candidate  (gate G05)

**Status: CLOSED 2026-07-25.** The locked key was provisioned into
`/home/nur/NUR-INTEGRATION-20260722/.env.local` (mode 600, git-ignored, never displayed).
`SAME_OPENAI_KEY=true`. The stack runs in `openai` mode and the two-turn proof produced
`LIVE_TALK_PASS` on this candidate — not inherited from `33a5dab`.

<details><summary>Original B3 text (historical)</summary>

## B3 — FOUNDER_ACTION_REQUIRED_CONFIGURE_OPENAI  (gate G05)

**Why required.** `LIVE_AI_PASS_CURRENT` must be proven **on this candidate**. A real
two-turn proof exists, but only in worktree `/home/nur/NUR-LIVE-TALK-PROOF-20260723`
at commit `33a5dab`. The orchestrator forbids inheriting it. This worktree has no
`.env.local`, so Talk cannot reach a provider here.

**Founder action.** B2 step 3 satisfies this at the same time.

**Verification.**
```bash
cd /home/nur/NUR-INTEGRATION-20260722
bash RUN_NUR.sh stop
bash RUN_NUR.sh openai
bash infra/scripts/openai-smoke-local.sh
node infra/scripts/live-talk-two-turn-proof.mjs
```

---

</details>

## B4 — FOUNDER_ACTION_REQUIRED_CONFIGURE_EMAIL_PROVIDER  (gate G06)

**Why required.** Password reset currently uses local file capture, which is explicitly
development-only. Public release requires a real transactional adapter and a verified
public origin. `apps/api/app/services/password_delivery.py` has no retry, dedup, or
bounce handling either — that part is agent work and proceeds now.

**Founder action.** Select and provision a transactional email provider, then place its
credentials in server environment/secret storage only.

**Verification.** Reset mail delivered to a real inbox from a verified origin; the
delivery record shows a provider message id.

---

## B5 — FOUNDER_ACTION_REQUIRED_CONFIGURE_BILLING_TEST_PROVIDER  (gate G08)

**Why required.** `G08_REVENUE` demands a provider **test-mode** vertical slice:
checkout → signed webhook → idempotent receipt → entitlement → portal → cancel → refund.
No billing provider is configured. The plan's first candidate is Lemon Squeezy as merchant
of record.

**Founder action.** Create the provider account in test mode and supply test-mode keys
through server secret storage. Live charge activation is a separate, later approval.

---

## B6 — FOUNDER_ACTION_REQUIRED_STAGING_ACCESS  (gate G15)

**Why required.** `SCALE_PASS` requires a production-like staging environment with separate
secrets, a real deploy, synthetic probes, and a timed restore drill with measured RPO/RTO.
None exists.

---

## B7 — FOUNDER_ACTION_REQUIRED_LOCALE_HUMAN_REVIEW  (gate G11)

**Why required.** `LANGUAGE_PASS` requires English, Roman Urdu, Urdu script RTL, Roman
Hindi and Hindi to be **human reviewed**. An agent may build the catalog architecture, the
extraction test, the key-completeness validator, and honest `machine` labels — it may not
truthfully label its own output `native-reviewed`.

---

## B8 — FOUNDER_ACTION_REQUIRED_RELEASE_APPROVAL  (gate G16)

**Why required.** Completion law requires explicit founder approval before release.

---

## Agent-owned blockers (no founder action needed)

| # | Gate | Blocker | First action |
| --- | --- | --- | --- |
| A1 | G00 | V6 documents not authored | write `docs/v6/source-authority-report.md`, `git-lineage-reconciliation.md`, `audit-claim-verification.csv`, `current-capability-gap-map.md` |
| A2 | G03 | Control matrix stale — `generated_from_sha` is `33a5dab`, not `6d7eeef` | regenerate the matrix on this candidate |
| A3 | G01 | No SBOM / dependency audit; no populated-upgrade or downgrade migration test; web build and mobile typecheck not re-run | add the gates |
| A4 | G02/G03/G04 | Playwright suites never run on this candidate | run them and record device-named evidence |
| A5 | G16 | `infra/scripts/nur-gate.sh` does not exist | build the deterministic G00–G16 runner |
| A6 | G14 | Bounded agents module entirely absent | implement after the gates above |
| A7 | G12 | No realtime gateway, no Signal Feed ranking | implement after G07 |
| A8 | G09 | No fraud detection, leaderboards, notification delivery, or experiment engine | implement after G08 |
