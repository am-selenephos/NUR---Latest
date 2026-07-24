# G02_AUTH — BLOCKED_EXTERNAL

- commit: `9a88eedea3fac406a0410b54ef4d99aafd4cc341`
- branch: `completion/nur-v5-full-pass`
- environment: `local`
- window: 2026-07-24T22:55:53Z → 2026-07-24T22:56:01Z
- dirty entries: 9

## Notes

API not reachable at http://localhost:8000/healthz — start the stack: bash RUN_NUR.sh

## Steps

| step | exit | seconds | log |
| --- | --- | --- | --- |
| auth_backend_tests
 | 0 | 8 | `auth_backend_tests.log
` |
| browser_suite
 | skipped | — | API stack not running
 |
| account_export_delete_e2e
 | skipped | — | export/delete surfaces not implemented (G02-014, G02-015)
 |
| session_management_ui
 | skipped | — | no session management surface (G02-013)
 |
