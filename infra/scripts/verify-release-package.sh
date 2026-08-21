#!/usr/bin/env bash
set -euo pipefail

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

python3 - "$SHA_FILE" "$ZIP" <<'PY'
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

sha_path = Path(sys.argv[1])
zip_path = Path(sys.argv[2])
lines = sha_path.read_text(encoding="utf-8").splitlines()
if len(lines) != 1:
    raise SystemExit("Package SHA file must contain exactly one checksum record")
match = re.fullmatch(r"([0-9a-fA-F]{64}) [ *](.+)", lines[0])
if match is None:
    raise SystemExit("Package SHA file has an invalid sha256sum record")
expected, recorded_name = match.groups()
if recorded_name not in {str(zip_path), zip_path.name}:
    raise SystemExit("Package SHA file does not name the requested ZIP")
actual = hashlib.sha256(zip_path.read_bytes()).hexdigest()
if actual != expected.lower():
    raise SystemExit("Package SHA-256 mismatch")
print(f"{zip_path}: OK")
PY

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
import re
import stat
import zipfile
from collections import Counter
from pathlib import Path, PurePosixPath

zip_path = Path(os.environ["NUR_VERIFY_ZIP"])
manifest_path = Path(os.environ["NUR_VERIFY_MANIFEST"])
target = Path(os.environ["NUR_VERIFY_TMP"])
manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
manifest_entries = manifest.get("archive_entries")
if not isinstance(manifest_entries, list) or not manifest_entries:
    raise SystemExit("Release manifest has no archive entries")
manifest_paths = [entry.get("path") for entry in manifest_entries]
duplicate_manifest_paths = sorted(
    path for path, count in Counter(manifest_paths).items() if count > 1
)
if duplicate_manifest_paths:
    raise SystemExit(f"Duplicate manifest entry: {duplicate_manifest_paths}")
expected = {entry["path"]: entry for entry in manifest_entries}
source_sha = manifest.get("source", {}).get("commit_sha")
if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", source_sha):
    raise SystemExit("Release manifest source SHA is missing or invalid")

sbom_records = manifest.get("sboms")
if not isinstance(sbom_records, list) or len(sbom_records) != 2:
    raise SystemExit("Release manifest must declare exactly two SBOMs")
if {record.get("ecosystem") for record in sbom_records} != {"node", "python"}:
    raise SystemExit("Release manifest SBOM ecosystems must be node and python")

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
secret_patterns = [
    re.compile(rb"(?<![A-Za-z0-9])sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(
        rb"(?i)(?:openai_api_key|api[_-]?key|secret[_-]?key)\s*[=:]\s*[\"']?"
        rb"(?![A-Za-z_][A-Za-z0-9_]*\.)[A-Za-z0-9._~+/=-]{12,}"
    ),
]

with zipfile.ZipFile(zip_path) as archive:
    infos = archive.infolist()
    file_names = [info.filename for info in infos if not info.is_dir()]
    duplicate_zip_entries = sorted(
        name for name, count in Counter(file_names).items() if count > 1
    )
    if duplicate_zip_entries:
        raise SystemExit(f"Duplicate ZIP entry: {duplicate_zip_entries}")
    actual = set(file_names)
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
        for pattern in secret_patterns:
            if pattern.search(payload):
                raise SystemExit(f"Secret-like value found in archive entry: {info.filename}")
        digest = hashlib.sha256(payload).hexdigest()
        record = expected[info.filename]
        if digest != record["sha256"] or len(payload) != record["bytes"]:
            raise SystemExit(f"Hash or size mismatch: {info.filename}")
        if stat.S_IMODE(mode) != record["mode"]:
            raise SystemExit(f"Mode mismatch: {info.filename}")
    archive.extractall(target)

canonical = target / manifest["canonical_v197"]["path"]
if hashlib.sha256(canonical.read_bytes()).hexdigest() != manifest["canonical_v197"]["sha256"]:
    raise SystemExit("Canonical V197 hash does not match the release manifest")

for sbom_record in sorted(sbom_records, key=lambda item: item["ecosystem"]):
    ecosystem = sbom_record["ecosystem"]
    sbom_path = target / sbom_record["path"]
    if not sbom_path.is_file():
        raise SystemExit(f"Required {ecosystem} SBOM is missing")
    payload = sbom_path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != sbom_record.get("sha256"):
        raise SystemExit(f"{ecosystem} SBOM digest mismatch")
    if len(payload) != sbom_record.get("bytes"):
        raise SystemExit(f"{ecosystem} SBOM byte count mismatch")
    document = json.loads(payload)
    properties = {
        item["name"]: item["value"]
        for item in document.get("metadata", {}).get("properties", [])
    }
    if properties.get("source.git_sha") != source_sha:
        raise SystemExit(f"SBOM source SHA mismatch: {ecosystem}")
    if properties.get("source.ecosystem") != ecosystem:
        raise SystemExit(f"SBOM ecosystem mismatch: {ecosystem}")
    if properties.get("source.input_sha256") != sbom_record.get("source_input_sha256"):
        raise SystemExit(f"SBOM input digest mismatch: {ecosystem}")
    if len(document.get("components", [])) != sbom_record.get("components"):
        raise SystemExit(f"SBOM component count mismatch: {ecosystem}")
    print(f"SBOM_{ecosystem.upper()}=PASS")
print(f"PACKAGE_ENTRIES={len(expected)}")
print(f"PACKAGE_UNCOMPRESSED_BYTES={total_uncompressed}")
print(f"PACKAGE_VERDICT={manifest['verdict']}")
PY

EXTRACTED="$TMP/NUR"
SOURCE_SHA="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["source"]["commit_sha"])' "$MANIFEST")"
(cd "$EXTRACTED" && bash infra/scripts/secret-scan.sh)
(cd "$EXTRACTED" && bash infra/scripts/check-v197-integrity.sh)
(cd "$EXTRACTED" && bash infra/scripts/release-naming-scan.sh)
(cd "$EXTRACTED" && python3 infra/scripts/generate_sbom.py \
  --check \
  --source-sha "$SOURCE_SHA" \
  --output-dir docs/completion/sbom)

VERDICT="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["verdict"])' "$MANIFEST")"
VERIFY_INSTALL="${NUR_VERIFY_INSTALL:-}"
if [[ -z "$VERIFY_INSTALL" ]]; then
  if [[ "$VERDICT" == "FULL_PASS" ]]; then
    VERIFY_INSTALL=1
  else
    VERIFY_INSTALL=0
  fi
fi

VERIFY_COLD_BOOT="${NUR_VERIFY_COLD_BOOT:-}"
if [[ -z "$VERIFY_COLD_BOOT" ]]; then
  VERIFY_COLD_BOOT="$VERIFY_INSTALL"
fi
VERIFY_STATIC_CHECKS="${NUR_VERIFY_STATIC_CHECKS:-}"
if [[ -z "$VERIFY_STATIC_CHECKS" ]]; then
  VERIFY_STATIC_CHECKS="$VERIFY_INSTALL"
fi
VERIFY_BUILD_CHECKS="${NUR_VERIFY_BUILD_CHECKS:-}"
if [[ -z "$VERIFY_BUILD_CHECKS" ]]; then
  VERIFY_BUILD_CHECKS="$VERIFY_INSTALL"
fi
if [[ "$VERDICT" == "FULL_PASS" ]]; then
  if [[ "$VERIFY_STATIC_CHECKS" != "1" || "$VERIFY_BUILD_CHECKS" != "1" ]]; then
    printf 'FULL_PASS package verification may not disable static or build checks.\n' >&2
    exit 1
  fi
fi
(cd "$EXTRACTED" && \
  NUR_FRESH_EXTRACT_INSTALL="$VERIFY_INSTALL" \
  NUR_FRESH_EXTRACT_COLD_BOOT="$VERIFY_COLD_BOOT" \
  NUR_FRESH_EXTRACT_STATIC_CHECKS="$VERIFY_STATIC_CHECKS" \
  NUR_FRESH_EXTRACT_BUILD_CHECKS="$VERIFY_BUILD_CHECKS" \
  bash infra/scripts/fresh-extract-smoke.sh)

printf 'RELEASE_PACKAGE_VERIFY=PASS\n'
printf 'PACKAGE=%s\n' "$ZIP"
printf 'MANIFEST=%s\n' "$MANIFEST"
printf 'CLEAN_INSTALL_CHECK=%s\n' "$VERIFY_INSTALL"
printf 'APPLICATION_COLD_BOOT_CHECK=%s\n' "$VERIFY_COLD_BOOT"
printf 'STATIC_CHECK=%s\n' "$VERIFY_STATIC_CHECKS"
printf 'PRODUCTION_BUILD_CHECK=%s\n' "$VERIFY_BUILD_CHECKS"
