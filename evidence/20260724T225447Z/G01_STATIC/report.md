# G01_STATIC — INCOMPLETE

- commit: `9a88eedea3fac406a0410b54ef4d99aafd4cc341`
- branch: `completion/nur-v5-full-pass`
- environment: `local`
- window: 2026-07-24T22:54:48Z → 2026-07-24T22:55:53Z
- dirty entries: 9

## Steps

| step | exit | seconds | log |
| --- | --- | --- | --- |
| ruff
 | 0 | 0 | `ruff.log
` |
| backend_tests
 | 0 | 58 | `backend_tests.log
` |
| alembic_single_head
 | 0 | 0 | `alembic_single_head.log
` |
| web_typecheck
 | 0 | 2 | `web_typecheck.log
` |
| web_unit_tests
 | 0 | 1 | `web_unit_tests.log
` |
| web_build
 | 0 | 2 | `web_build.log
` |
| v197_integrity
 | 0 | 1 | `v197_integrity.log
` |
| secret_scan
 | 0 | 0 | `secret_scan.log
` |
| release_naming
 | 0 | 0 | `release_naming.log
` |
| diff_check
 | 0 | 0 | `diff_check.log
` |
| mobile_typecheck
 | 0 | 1 | `mobile_typecheck.log
` |
| dependency_audit
 | skipped | — | no dependency-audit gate implemented yet (G01-009)
 |
| sbom
 | skipped | — | no SBOM generator implemented yet (G01-009)
 |
| migration_upgrade_from_populated
 | skipped | — | no populated-revision upgrade test yet (G01-014)
 |
| migration_downgrade
 | skipped | — | no downgrade execution test yet (G01-015)
 |
| fresh_extract_boot
 | skipped | — | fresh-clone/extract boot not wired into this runner yet (G01-017)
 |
