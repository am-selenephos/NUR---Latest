#!/usr/bin/env bash
# Compatibility entrypoint used by `RUN_NUR.sh package`. It delegates to the
# canonical release builder and verifier, and deliberately emits a HOLD package:
# packaging a bootable tree is not evidence for provider, staging, or approval.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATE_STAMP="${NUR_PACKAGE_DATE:-$(date -u +%Y%m%d)}"
OUT="${1:-/home/nur/Downloads/NUR_FULL_SYSTEM_COMPLETE_V197_AI_${DATE_STAMP}.zip}"
if [[ "$OUT" != /* ]]; then
  OUT="$PWD/$OUT"
fi

OUT_DIR="$(dirname "$OUT")"
OUT_MANIFEST="${OUT%.zip}_MANIFEST.json"
OUT_SHA="$OUT.sha256"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$OUT_DIR" "$TMP/release"

(
  cd "$ROOT"
  NUR_RELEASE_DATE="$DATE_STAMP" \
    bash infra/scripts/package-release.sh \
      --verdict HOLD \
      --output-dir "$TMP/release"
)

SOURCE_ZIP="$(find "$TMP/release" -maxdepth 1 -type f -name 'NUR_*_HOLD_*.zip' -print -quit)"
[[ -n "$SOURCE_ZIP" ]] || {
  printf 'Canonical HOLD package was not produced.\n' >&2
  exit 1
}
SOURCE_MANIFEST="${SOURCE_ZIP%.zip}_MANIFEST.json"
[[ -s "$SOURCE_MANIFEST" ]] || {
  printf 'Canonical HOLD manifest was not produced.\n' >&2
  exit 1
}

cp "$SOURCE_ZIP" "$OUT"
cp "$SOURCE_MANIFEST" "$OUT_MANIFEST"
(
  cd "$OUT_DIR"
  printf '%s  %s\n' "$(sha256sum "$(basename "$OUT")" | awk '{print $1}')" "$(basename "$OUT")" > "$(basename "$OUT_SHA")"
)

NUR_VERIFY_INSTALL="${NUR_BOOTABLE_VERIFY_INSTALL:-0}" \
NUR_VERIFY_COLD_BOOT="${NUR_BOOTABLE_VERIFY_COLD_BOOT:-0}" \
  bash "$ROOT/infra/scripts/verify-release-package.sh" "$OUT"

printf 'BOOTABLE_PACKAGE_VERDICT=HOLD\n'
printf 'Bootable package: %s\n' "$OUT"
printf 'Bootable manifest: %s\n' "$OUT_MANIFEST"
printf 'Bootable SHA-256: %s\n' "$OUT_SHA"
