# G12_COMMUNITY — BLOCKED_EXTERNAL

- commit: `9a88eedea3fac406a0410b54ef4d99aafd4cc341`
- branch: `completion/nur-v5-full-pass`
- environment: `local`
- window: 2026-07-24T22:56:51Z → 2026-07-24T22:56:57Z
- dirty entries: 9

## Notes

API not reachable at http://localhost:8000/healthz — start the stack: bash RUN_NUR.sh

## Steps

| step | exit | seconds | log |
| --- | --- | --- | --- |
| community_tests
 | 0 | 5 | `community_tests.log
` |
| browser_suite
 | skipped | — | API stack not running
 |
| realtime_gateway
 | skipped | — | no authenticated realtime gateway (G12-006)
 |
| signal_feed
 | skipped | — | no feed ranking module (G12-011)
 |
| anti_abuse
 | skipped | — | no anti-abuse suite (G12-013)
 |
