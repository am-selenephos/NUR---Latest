# NUR HOLD Release Artifact Evidence

**Repository:** `am-selenephos/NUR---Latest`

**Completion branch:** `completion/nur-fullstack-agentend-20260818`

**Immutable implementation/release-candidate SHA:** `9acb056a1d5f24eeebaa01fcb998a39f99fb7d22`

**Verdict:** `HOLD` / `NUR_PARTIAL`

## Verified package

The package was generated from a clean detached worktree at the candidate SHA with `bash infra/scripts/package-release.sh --verdict HOLD --output-dir /home/ubuntu/NUR-final-evidence`, and verified with `bash infra/scripts/verify-release-package.sh`. The package contains **828 entries** and **9,215,468 uncompressed bytes**.

| Artifact | Value |
|---|---|
| ZIP | `/home/ubuntu/NUR-final-evidence/NUR_V5_HOLD_20260818.zip` |
| Manifest | `/home/ubuntu/NUR-final-evidence/NUR_V5_HOLD_20260818_MANIFEST.json` |
| Checksum file | `/home/ubuntu/NUR-final-evidence/NUR_V5_HOLD_20260818.zip.sha256` |
| Archive SHA-256 | `309d110d98cc092f1a445321717d39ee39d941de241cf46c0ffdbca598efde1a` |
| Manifest source SHA | `9acb056a1d5f24eeebaa01fcb998a39f99fb7d22` |
| Manifest verdict | `HOLD` |
| Verification result | `RELEASE_PACKAGE_VERIFY=PASS` |
| Clean-install check | `0` (not requested for HOLD) |

The verification also passed the package hash check, secret scan, canonical V197 integrity check, archive safety/manifest consistency checks, and release naming scan. The canonical V197 host hash in the candidate manifest is `397c302579472e60f5bd667546a96b6e3f262aa40bd932d10c1946e13b046dd2`; decoded Entry and Universe hashes are `cdeac0c8574333c7261be2bc410357ecc5407ee0dd5b1b8089630f3914026030` and `f83ebff9b6cb8abfc0e8e75af3e2ac45d68a0b018505c7157ae6b5df82bb04dc`.

The generated manifest, checksum, verification transcript, and ZIP are retained outside the repository under `/home/ubuntu/NUR-final-evidence/` for reviewer access and final attachment. This tracked note is documentation evidence only; it does not claim independent review, exact-head remote CI, Docker cold boot, live provider success, or a fully green WebKit responsive matrix.
