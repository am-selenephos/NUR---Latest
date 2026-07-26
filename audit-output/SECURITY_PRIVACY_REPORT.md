# SECURITY & PRIVACY REPORT — Phase 8

Scope: current integration worktree `6d7eeef` + the forensic archive. No secret
values are reproduced anywhere in this report (keys referenced by SHA-256 prefix).

## FINDINGS (most severe first)

### F1 — HIGH — Live OpenAI API keys leaked inside the forensic archive
- **file:line / location:** archive `.env.local` in snapshots
  `04-NUR-FABLE-ROOT/.env.local`, `06-NUR-LIVE-TALK-PROOF/.env.local`,
  `07-NUR-DEMO-TALK-FIXED/.env.local`, `08-NUR-DEMO-COUSIN/.env.local`, and
  `09-NUR-OLDER-LOCAL/api/.env` — each has `OPENAI_API_KEY=sk-proj-…`.
- **evidence:** 3 distinct key fingerprints (SHA-256 of key line, first 16 hex):
  `152265b9490e48ad` (04), `a25760fb08cec58a` (06 & 09 — reused), `5bee0ad5976d93d5`
  (07 & 08 — reused). Values NOT printed.
- **impact:** Anyone with the archive `NUR-TRUE-FULL-AUDIT-20260801-144301.tar.zst`
  (204 MB, in `~/Downloads`, shareable) obtains 3 usable server-side OpenAI
  credentials → billing abuse / data exfiltration via the account.
- **reproduction:** `tar --zstd -xf … && grep -rl OPENAI_API_KEY <extract>/**/.env*`.
- **recommended fix:** (1) **Rotate all 3 OpenAI keys now.** (2) Regenerate the
  archive excluding `.env` and `.env.local` (the staging step captured working-tree
  dotfiles that git ignores). (3) Treat the existing archive as compromised —
  delete/re-issue copies.
- **confidence:** HIGH. **current or historical:** ARCHIVE-ONLY — **current Git is
  clean** (0 tracked env files; `.env`/`.env.local` gitignored; repo secret-scan
  passes). This is a backup-hygiene defect, not a code defect.

### F2 — LOW — Hardcoded demo credentials in seed scripts
- **file:line:** `infra/scripts/*seed*.sh` — `owner-demo-pass-123`,
  `recipient-demo-pass-123`, `demo-pass-123`.
- **impact:** Predictable demo-account passwords. Acceptable for local/demo; must
  not be seeded in production.
- **reproduction:** `grep -r demo-pass infra/scripts`.
- **fix:** Gate demo seeding behind `APP_ENV != production` (already done for
  `reset-demo`); ensure prod seeding never runs. **confidence:** HIGH. **current.**

### F3 — LOW — `sed` interpolation in bootstrap env writer
- **file:line:** `infra/scripts/bootstrap-dev.sh:99`
  `sed -i "s#^${key}=.*#${key}=${value}#" .env`.
- **impact:** `key`/`value` are internal controlled values (ports, container
  names, DSNs); a `#` in a value would break the expression. No external/user input
  reaches this. Low.
- **fix:** Prefer `python`/`printf`-based rewrite or a `#`-safe delimiter.
  **confidence:** MED. **current.**

### F4 — INFO — Runtime state captured in snapshots
- `celerybeat-schedule(-shm/-wal)` in snapshots 04/06/07/08 and 3 `.sqlite3` in 09.
  Should be gitignored. **No secrets/PII** in the sqlite (verified: 0 emails, 0
  key patterns; old chatbot session profiles only). **historical/archive.**

## POSITIVE CONTROLS VERIFIED (current Git)
| Area | Evidence | Verdict |
|---|---|---|
| RLS / cross-owner isolation | `0002_rls_policies.py`: 22 `ENABLE RLS`/`CREATE POLICY` on `current_setting('app.current_user_id', true)`; `db/rls.py set_config(...,true)` = txn-local; `test_cross_owner_cognition_is_invisible` passes | STRONG |
| Session / CSRF | `auth.py`: session cookie `httponly=True, samesite=lax`; CSRF signed double-submit (`deps.py require_csrf`), CSRF cookie readable by JS by design | STRONG |
| Secret handling | `config.py`: `openai_api_key`/`billing_webhook_secret`/`smtp_password`/`lemon_squeezy_api_key` all `SecretStr`; `NUR_AI_LOG_PROMPTS` default **False** | STRONG |
| OpenAI boundary | key server-side only (`AsyncOpenAI(api_key=…get_secret_value())`); frontend has no key ref (`PASS no frontend OpenAI key reference`); prompts treat evidence as untrusted | STRONG |
| Prompt / source verification | `verifier.py` blocks on missing/injection-bearing source_refs, persona/dependency/unverified-action flags; unverified output blocked before persistence (`test_unverified_provider_output_is_blocked…` passes) | STRONG |
| Billing webhook | `billing/service.py`: `hmac.compare_digest` constant-time signature check; length-bounded | STRONG |
| Object storage | `object_storage.py`: `Path(root).resolve()` + `is_relative_to(self._root)` traversal guard; `chmod 0700/0600` | STRONG |
| Synthetic-success paths | none found in `ai/`,`cognition/`; disabled provider returns honest ledger-only output; Talk fails closed with typed errors (backend tests confirm) | STRONG |
| Export / delete | deletion hygiene + orphan reconciliation + retention shipped (commits 78cd7bb Phase 8); covered by green backend suite | ADEQUATE |
| Capsule grants/revocation | `capsules.py` + `sharing` models + `capsule.spec.ts`; grant/revoke lifecycle present | ADEQUATE |

## Privacy
- Owner-scoped everything (RLS). No cross-owner read path found.
- Prompt logging off by default; audit metadata redacts errors (`safe_error_metadata`
  + `redact_for_audit`).
- Old-generation sqlite fixtures carry no PII.

## Net
Current Git security posture is **strong**. The single serious issue (F1) is an
**archive/backup hygiene leak of live OpenAI keys**, not a product-code defect —
but it is real and requires immediate key rotation + archive regeneration.
