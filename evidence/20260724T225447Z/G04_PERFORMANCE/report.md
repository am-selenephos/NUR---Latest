# G04_PERFORMANCE — BLOCKED_EXTERNAL

- commit: `9a88eedea3fac406a0410b54ef4d99aafd4cc341`
- branch: `completion/nur-v5-full-pass`
- environment: `local`
- window: 2026-07-24T22:56:02Z → 2026-07-24T22:56:02Z
- dirty entries: 9

## Notes

API not reachable at http://localhost:8000/healthz — start the stack: bash RUN_NUR.sh

## Steps

| step | exit | seconds | log |
| --- | --- | --- | --- |
| browser_suite
 | skipped | — | API stack not running
 |
| named_reference_devices
 | skipped | — | reference device/browser tier not declared (G04-008, G04-009)
 |
| heap_soak
 | skipped | — | 10-minute heap/listener/observer soak not implemented (G04-004)
 |
