#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ZIP="${1:-}"

if [[ -z "$ZIP" || ! -f "$ZIP" ]]; then
  printf 'Usage: bash infra/scripts/verify-release-package.sh <release.zip>\n' >&2
  exit 2
fi

ZIP="$(cd "$(dirname "$ZIP")" && pwd)/$(basename "$ZIP")"
SHA_FILE="$ZIP.sha256"
MANIFEST="${ZIP%.zip}_MANIFEST.json"
[[ -s "$SHA_FILE" ]] || {
  printf 'Missing package SHA file: %s\n' "$SHA_FILE" >&2
  exit 1
}
[[ -s "$MANIFEST" ]] || {
  printf 'Missing package manifest: %s\n' "$MANIFEST" >&2
  exit 1
}

(cd "$(dirname "$ZIP")" && sha256sum -c "$(basename "$SHA_FILE")")

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
export NUR_VERIFY_ZIP="$ZIP"
export NUR_VERIFY_MANIFEST="$MANIFEST"
export NUR_VERIFY_TMP="$TMP"

python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import stat
import zipfile
from pathlib import Path, PurePosixPath

zip_path = Path(os.environ["NUR_VERIFY_ZIP"])
manifest_path = Path(os.environ["NUR_VERIFY_MANIFEST"])
target = Path(os.environ["NUR_VERIFY_TMP"])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
expected = {entry["path"]: entry for entry in manifest["archive_entries"]}

forbidden_parts = {
    ".git",
    "node_modules",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".nur-runtime",
    "playwright-report",
    "test-results",
}
forbidden_names = {".env", ".env.local", "dump.rdb"}

with zipfile.ZipFile(zip_path) as archive:
    infos = archive.infolist()
    actual = {info.filename for info in infos if not info.is_dir()}
    if actual != set(expected):
        missing = sorted(set(expected) - actual)
        extra = sorted(actual - set(expected))
        raise SystemExit(f"Manifest/archive mismatch: missing={missing} extra={extra}")
    total_uncompressed = sum(info.file_size for info in infos)
    if total_uncompressed > 500_000_000:
        raise SystemExit("Archive exceeds the 500 MB uncompressed safety limit")
    for info in infos:
        name = PurePosixPath(info.filename)
        if name.is_absolute() or ".." in name.parts:
            raise SystemExit(f"Unsafe archive path: {info.filename}")
        if any(part in forbidden_parts for part in name.parts):
            raise SystemExit(f"Forbidden release path: {info.filename}")
        if name.name in forbidden_names:
            raise SystemExit(f"Forbidden release file: {info.filename}")
        if name.name.startswith(".env.") and name.name != ".env.example":
            raise SystemExit(f"Forbidden release environment file: {info.filename}")
        mode = info.external_attr >> 16
        if stat.S_ISLNK(mode):
            raise SystemExit(f"Release archive contains a symlink: {info.filename}")
        payload = archive.read(info)
        digest = hashlib.sha256(payload).hexdigest()
        record = expected[info.filename]
        if digest != record["sha256"] or len(payload) != record["bytes"]:
            raise SystemExit(f"Hash or size mismatch: {info.filename}")
    archive.extractall(target)

canonical = target / manifest["canonical_v197"]["path"]
if hashlib.sha256(canonical.read_bytes()).hexdigest() != manifest["canonical_v197"]["sha256"]:
    raise SystemExit("Canonical V197 hash does not match the release manifest")
print(f"PACKAGE_ENTRIES={len(expected)}")
print(f"PACKAGE_UNCOMPRESSED_BYTES={total_uncompressed}")
print(f"PACKAGE_VERDICT={manifest['verdict']}")
PY

EXTRACTED="$TMP/NUR"
(cd "$EXTRACTED" && bash infra/scripts/secret-scan.sh)
(cd "$EXTRACTED" && bash infra/scripts/check-v197-integrity.sh)
(cd "$EXTRACTED" && bash infra/scripts/release-naming-scan.sh)

VERDICT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$MANIFEST")"
VERIFY_INSTALL="${NUR_VERIFY_INSTALL:-}"
if [[ -z "$VERIFY_INSTALL" ]]; then
  if [[ "$VERDICT" == "FULL_PASS" ]]; then
    VERIFY_INSTALL=1
  else
    VERIFY_INSTALL=0
  fi
fi

if [[ "$VERIFY_INSTALL" == "1" ]]; then
  (
    cd "$EXTRACTED"
    npm ci
    python3 -m venv apps/api/.venv
    apps/api/.venv/bin/pip install -r apps/api/requirements-dev.lock
    apps/api/.venv/bin/pip install --no-deps -e apps/api
    npm run web:typecheck
    npm run web:test
    npm run web:build
    npm run mobile:typecheck
    apps/api/.venv/bin/python -m ruff check apps/api
    PYTHONPATH=apps/api apps/api/.venv/bin/python -c \
      'from app.main import app; spec=app.openapi(); assert spec["paths"]; print(f"OPENAPI_PATHS={len(spec['"'"'paths'"'"'])}")'
  )
fi

printf 'RELEASE_PACKAGE_VERIFY=PASS\n'
printf 'PACKAGE=%s\n' "$ZIP"
printf 'MANIFEST=%s\n' "$MANIFEST"
printf 'CLEAN_INSTALL_CHECK=%s\n' "$VERIFY_INSTALL"
