# Founder decisions — V6

Binding record of explicit founder decisions taken during the V5 100% completion mission.
Each entry supersedes any earlier plan text it contradicts, per the Masterplan §0 conflict rule
(`newer explicit founder decision > older founder decision`).

---

## FD-001 — Ratification of the current canonical V197 source identity

**Decided:** 2026-07-25 · **Founder:** Mahnoor · **Status:** RATIFIED, CONDITIONAL
**Resolves:** CONFLICT-001 in [conflict-and-supersession-report.md](./conflict-and-supersession-report.md)

### Decision

The current canonical V197 source is ratified:

```
d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6
```

The historical source `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3`
**must not be restored**.

### Hashes

| Role | SHA-256 | Where |
| --- | --- | --- |
| superseded canonical | `252eee806ece31ef829a2dc5cd45aa8d8f8e855db1bde98b6f87193d786633c3` | blob `03c9de12bbf0ca4e098c85126e3ccf3f2726dc99` at commit `6ce2c46`; pinned by Masterplan V5 §9.1 and `NUR_V5_MASTERPACK_MANIFEST_20260713.json` → `canonical_v197_checkpoint.sha256` |
| **ratified canonical (host)** | `d4f7f2d3e4c8e36dfc0c6edd51a028f28a04afbc2afa434a319009cb2f122bc6` | `apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html` |
| ratified Entry reference | `cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030` | `docs/reference/entry_decoded_v197.html` |
| ratified Universe reference | `3cff07b31e8360e5ce793287298d66127c4f278705dc0f8e6abdfbe7e874dc40` | `docs/reference/universe_decoded_v197.html` |

The superseded value was verified, not assumed: `git cat-file blob 03c9de12 | sha256sum`
returns exactly `252eee80…`. The July 13 plan was accurate when it was written.

### Commit lineage

```
6ce2c46  Publish NUR V197 cousin-ready demo
         canonical host = 1,029,176 bytes, sha256 252eee80…   (the plan's checkpoint)
   │
   ▼
f8ddd7a  Consolidate exact V197 star brain interface
         am-selenephos · 2026-07-18 20:09:38 +0500
         canonical host = 718,041 bytes, sha256 d4f7f2d3…
   │
   ▼
6d7eeef  fix(ai): restore compatible live Talk payload and proof gate   (release/nur-p0-candidate)
   │
   ▼
HEAD     completion/nur-v5-full-pass
```

`f8ddd7a` is an ancestor of HEAD. The canonical bytes have not changed since.

### The transformation

`apps/web/scripts/rebuild-v197-canonical.mjs` performs, deterministically:

1. extracts the Base64-embedded Entry and Universe documents from the host by locating their
   `const <name> = "<base64>";` declarations;
2. parses each extracted document with JSDOM;
3. prunes every `<style>` and `<script>` node that is **not** on the keep-list —
   Entry keeps `nur-app-shell-styles`, `nur-v61-neural-rewiring-front`,
   `nur-v61-neural-rewiring-runtime`, `nur-v67-popup-close-hardening`;
   Universe keeps `nur-v180-canonical-cleaned`, `nur-v181-runtime`;
4. re-encodes and re-embeds the pruned documents into the host;
5. writes the pruned host and reports its hash.

Net effect: 1,029,176 → 718,041 bytes, −311,135 bytes (−30.2%) of dead legacy styles and
scripts. No visual layer, typography rule, color law, MasterStar geometry, or control was
authored, replaced, or approximated. React did not acquire ownership of any visible DOM.

### Why the newer source supersedes the July 13 checkpoint

The rebuild **is the plan executing itself**. Masterplan V5 §9.6 defines
*Stage S — static-source extraction* as required work:

> extract canonical V197 Entry/Universe assets at build time into readable static HTML/CSS/JS;
> create a generated manifest with source SHA, asset SHA, selector contract, and build version;
> **remove runtime Base64 decode, duplicate embedded copies, and dead legacy handlers**;
> keep a feature flag that can restore Stage R without losing data.

`f8ddd7a` performs exactly the third clause. A hash change is the *expected consequence* of
Stage S, not evidence of drift. Holding `252eee80…` would have required the plan to forbid its
own convergence stage.

Supporting reasons:

- the July 13 checkpoint recorded `source_untouched_in_auth_presentation_gate: true` — a
  statement about that gate, not a permanent freeze;
- the ledger's own authority rule states it is "historical evidence, not permission to ignore
  newer verified implementation";
- the new hash is machine-enforced, not merely documented: `scripts/check-v197-integrity.ts`
  pins all three files and `npm run v197:integrity` fails the build on any drift;
- the transformation is reproducible from a committed script, so the canonical identity is
  derivable rather than asserted.

### Affected integrity tests and documentation

| Artifact | Effect of this ratification |
| --- | --- |
| `scripts/check-v197-integrity.ts` | `V197_HASHES.host` is now founder-ratified. Any change requires a new FD entry. |
| `infra/scripts/check-v197-integrity.sh` / `npm run v197:integrity` | Authoritative canonical gate. Passes on this candidate. |
| `apps/web/e2e/v197-*.spec.ts` (16 specs) | Assert against the ratified source. Must be re-run on the candidate. |
| `apps/web/scripts/rebuild-v197-canonical.mjs` | The sanctioned regeneration path. Re-running it must reproduce `d4f7f2d3…` byte-for-byte. |
| `docs/release/v197-control-matrix.json` | Must be regenerated against the ratified source on this candidate — it currently carries `generated_from_sha: 33a5dab`. |
| Masterplan V5 §9.1, Status ledger V5 `SRC-002`/`UI-001`, Masterpack manifest | **Superseded on the hash value only.** Files preserved unmodified as historical evidence. |

### Conditions attached to the ratification

The founder ratified the **source identity**. Runtime and visual proof is **not** waived.
`G03_V197` cannot pass until all six conditions are proven on this candidate:

| # | Condition | State |
| --- | --- | --- |
| C1 | canonical integrity | **MET** — `npm run v197:integrity` `pass: true` on `6d7eeef` |
| C2 | complete regenerated V197 control matrix | OPEN |
| C3 | desktop/mobile geometry and visual parity | OPEN |
| C4 | no hidden duplicate visual engine | OPEN |
| C5 | no regression in source-native controls | OPEN |
| C6 | current browser E2E | OPEN |

Until C2–C6 are met, `G03_V197` stays `FAIL`, and `CONFLICT-001` is recorded as
**RESOLVED (identity) / CONDITIONS PENDING (proof)**.

---

## FD-002 — The existing OpenAI key is locked; no rotation

**Decided:** 2026-07-25 · **Founder:** Mahnoor · **Status:** IN FORCE
**Supersedes:** every earlier rotation instruction, including blocker B2 as originally written.

### Decision

The OpenAI API key that produced the verified `LIVE_TALK_PASS` is **reused unchanged**. It must
not be rotated, revoked, replaced, regenerated, or disabled. `FOUNDER_ACTION_REQUIRED_ROTATE_OPENAI_KEYS`
is withdrawn.

### Retrieval

Retrieved only from live local configuration, in the founder's stated priority order. Source:
`/home/nur/NUR-LIVE-TALK-PROOF-20260723/.env.local` (mode 600). Never recovered from chat
transcripts, audit reports, Git history, screenshots, public files, or archived plaintext.

Provenance was confirmed rather than assumed: the live key line fingerprints to the same value
the forensic audit recorded for archive snapshot 06 (`NUR-LIVE-TALK-PROOF`), which is the
configuration that produced `LIVE_TALK_PASS` at commit `33a5dab`.

### Competing configurations

Two distinct active key values exist in live local worktree configuration:

| Group | Paths |
| --- | --- |
| 1 — **selected** | `/home/nur/NUR-LIVE-TALK-PROOF-20260723/.env.local`, `/home/nur/NUR-FABLE-20260720-155600/.env.local` |
| 2 — not selected | `/home/nur/NUR-DEMO-COUSIN-20260722/.env.local`, `/home/nur/NUR-DEMO-TALK-FIXED/.env.local` |

`FOUNDER_ACTION_REQUIRED_IDENTIFY_EXISTING_OPENAI_KEY` was **not** raised. The founder's own
priority list names source #1 explicitly, and that source resolves to exactly one value, so the
choice is determinate rather than a guess. Group 2 belongs to demo worktrees that did not
produce `LIVE_TALK_PASS`. Values were never displayed. **If the founder intends group 2 to be
the locked key instead, say so and it will be re-provisioned.**

### Provisioning

The whole `.env.local` was copied to `/home/nur/NUR-INTEGRATION-20260722/.env.local` — it also
carries the provider, model (`gpt-4.1`) and reasoning-effort settings the proven run used.

| Control | State |
| --- | --- |
| value preserved exactly | `SAME_OPENAI_KEY=true` |
| file mode | `600` |
| ignored by Git | yes — `.gitignore:3` (`.env.*`) |
| appears in `git status` | no |
| `npm run secret-scan` | passes |
| displayed, echoed, or logged | never |
| in commits, patches, reports, evidence, ZIPs | never |
| fingerprints | only in `/home/nur/NUR-V5-100-COMPLETION/.secret-evidence/` (dir 700, file 600) |

### Exposure handling under this decision

The key stays active and valid. Historical archives containing duplicate plaintext copies remain
quarantined at `/home/nur/NUR-QUARANTINE-SECRETS/` (700/600) and are excluded from every release
path. `docs/v6/credential-exposure-inventory.csv` rotation state changes from `UNROTATED_P0` to
`FOUNDER_LOCKED_NO_ROTATION`.

**The residual risk is unchanged and is now accepted by decision, not by oversight:** the archive
copies were readable at `~/Downloads` before quarantine, so anyone who obtained them holds a
working credential. Quarantine limits further spread; it does not revoke access already taken.
Reviewing provider usage for unexpected spend remains worthwhile.
