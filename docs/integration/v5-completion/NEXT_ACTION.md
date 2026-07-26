# NEXT ACTION

Repo: `/home/nur/NUR-INTEGRATION-20260722`
Branch: `completion/nur-v5-full-pass` @ `28a9117`  (base `6d7eeef`)
Tree: clean except preserved untracked dirs (`audit-output/`, `proof/*`)

## Gate state (runner verdicts, `evidence/20260724T225447Z`)

Zero gates PASS. 7 FOUNDER_ACTION_REQUIRED, 6 BLOCKED_EXTERNAL, 3 INCOMPLETE, 1 FAIL-free but incomplete.

## The one thing blocking six gates at once

`G02`, `G03`, `G04`, `G10`, `G12`, `G14` are all `BLOCKED_EXTERNAL` for the same reason:
**the API stack is not running**, so every browser spec that exercises real auth gets
`ECONNREFUSED` through the Vite proxy. Playwright's `webServer` starts Vite only.

## Exact next command

```bash
cd /home/nur/NUR-INTEGRATION-20260722
bash RUN_NUR.sh                      # or: bash RUN_NUR.sh disabled
curl -fsS http://localhost:8000/healthz     # must return before browser gates mean anything
bash infra/scripts/seed-demo-nur.sh         # demo owner the auth specs sign in as
bash infra/scripts/nur-gate.sh G02_AUTH
bash infra/scripts/nur-gate.sh G03_V197
bash infra/scripts/nur-gate.sh G04_PERFORMANCE
```

Once those produce real evidence, FD-001 conditions C2–C6 can be assessed and `G03` can move
off `BLOCKED_EXTERNAL`.

## Then, in dependency order

1. **G01 → PASS.** Five real gaps remain, all agent-owned: dependency audit, SBOM,
   populated-revision upgrade test, downgrade execution test, fresh-extract boot.
2. **G03.** Implement the 7 `NOT_IMPLEMENTED_VISIBLE` controls; surface Personal Memory,
   Teach NUR and Billing (the `BACKEND_ONLY` four).
3. **G04.** Declare named reference devices, then capture traces/FPS/INP/heap.
4. **G05.** After key rotation + local configuration, prove live AI **on this candidate**.
5. **G07 → G08 → G09 → G10 → …** per the founder's intelligence-before-revenue ordering.

## Founder actions outstanding

| ID | Action | Blocks |
| --- | --- | --- |
| B2/B3 | rotate the 3 exposed keys, then `bash infra/scripts/configure-openai-local.sh` | G05 |
| B4 | transactional email provider | G06 |
| B5 | billing provider test mode | G08 |
| B6 | staging environment | G15 |
| B7 | human review of 5 priority locales | G11 |
| B8 | release approval | G16 |

## Do not
- do not restart completed gates;
- do not trust this file over disk — re-read `STATE.json` and `evidence/<stamp>/*/result.json`;
- do not inherit the Live-Talk proof from `33a5dab`;
- do not merge, push, deploy, tag, package, or mark ready;
- do not test or reuse the revoked keys.
