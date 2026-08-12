#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

VERDICT=""
OUTPUT_DIR="${NUR_RELEASE_OUTPUT_DIR:-$ROOT/release}"
EVIDENCE_DIR="${NUR_RELEASE_EVIDENCE_DIR:-${NUR_GATE_DIR:-}}"
VERSION="${NUR_RELEASE_VERSION:-V5}"
DATE_STAMP="${NUR_RELEASE_DATE:-$(date -u +%Y%m%d)}"

usage() {
  printf 'Usage: bash infra/scripts/package-release.sh --verdict <verdict> [--output-dir <dir>] [--evidence-dir <dir>]\n' >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --verdict)
      VERDICT="${2:-}"
      shift 2
      ;;
    --output-dir)
      OUTPUT_DIR="${2:-}"
      shift 2
      ;;
    --evidence-dir)
      EVIDENCE_DIR="${2:-}"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      printf 'Unknown package option: %s\n' "$1" >&2
      usage
      exit 2
      ;;
  esac
done

VERDICT="${VERDICT^^}"
if [[ -z "$VERDICT" || ! "$VERDICT" =~ ^(FULL_PASS|HOLD|FOUNDER_ACTION_REQUIRED_[A-Z0-9_]+)$ ]]; then
  printf 'Invalid release verdict: %s\n' "${VERDICT:-empty}" >&2
  exit 2
fi
if [[ ! "$VERSION" =~ ^[A-Za-z0-9._-]+$ ]]; then
  printf 'Invalid release version: %s\n' "$VERSION" >&2
  exit 2
fi

if ! git diff --quiet || ! git diff --cached --quiet; then
  printf 'Release packaging requires a clean tracked worktree.\n' >&2
  exit 1
fi

SOURCE_SHA="$(git rev-parse HEAD)"
SOURCE_BRANCH="$(git branch --show-current)"
mkdir -p "$OUTPUT_DIR"
OUTPUT_DIR="$(cd "$OUTPUT_DIR" && pwd)"
BASE="NUR_${VERSION}_${VERDICT}_${DATE_STAMP}"
ZIP="$OUTPUT_DIR/$BASE.zip"
SHA_FILE="$ZIP.sha256"
MANIFEST="$OUTPUT_DIR/${BASE}_MANIFEST.json"

if [[ "$VERDICT" == "FULL_PASS" ]]; then
  if [[ -z "$EVIDENCE_DIR" || ! -d "$EVIDENCE_DIR" ]]; then
    printf 'FULL_PASS packaging requires --evidence-dir with current gate results.\n' >&2
    exit 1
  fi
  export NUR_PACKAGE_EVIDENCE_DIR="$EVIDENCE_DIR"
  export NUR_PACKAGE_SOURCE_SHA="$SOURCE_SHA"
  python3 - <<'PY'
from __future__ import annotations

import json
import os
from pathlib import Path

evidence = Path(os.environ["NUR_PACKAGE_EVIDENCE_DIR"])
source_sha = os.environ["NUR_PACKAGE_SOURCE_SHA"]
missing = []
invalid = []
for index in range(16):
    prefix = f"G{index:02d}_"
    candidates = sorted(evidence.rglob(f"{prefix}*/result.json"))
    if not candidates:
        missing.append(prefix)
        continue
    result = json.loads(candidates[-1].read_text(encoding="utf-8"))
    if result.get("verdict") != "PASS":
        invalid.append(f"{result.get('gate')}: {result.get('verdict')}")
    result_sha = result.get("commit") or result.get("source", {}).get("commit_sha")
    if result_sha != source_sha:
        invalid.append(f"{result.get('gate')}: source SHA mismatch")
if missing or invalid:
    raise SystemExit(
        "FULL_PASS evidence is incomplete: "
        + "; ".join([*(f"missing {item}" for item in missing), *invalid])
    )
PY
fi

export NUR_PACKAGE_ROOT="$ROOT"
export NUR_PACKAGE_ZIP="$ZIP"
export NUR_PACKAGE_MANIFEST="$MANIFEST"
export NUR_PACKAGE_VERDICT="$VERDICT"
export NUR_PACKAGE_VERSION="$VERSION"
export NUR_PACKAGE_DATE="$DATE_STAMP"
export NUR_PACKAGE_SOURCE_SHA="$SOURCE_SHA"
export NUR_PACKAGE_SOURCE_BRANCH="$SOURCE_BRANCH"
export NUR_PACKAGE_EVIDENCE_DIR="$EVIDENCE_DIR"

python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import subprocess
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath

root = Path(os.environ["NUR_PACKAGE_ROOT"]).resolve()
zip_path = Path(os.environ["NUR_PACKAGE_ZIP"]).resolve()
manifest_path = Path(os.environ["NUR_PACKAGE_MANIFEST"]).resolve()
evidence_value = os.environ["NUR_PACKAGE_EVIDENCE_DIR"]
evidence_dir = Path(evidence_value).resolve() if evidence_value else None

skip_roots = {
    ".git",
    "node_modules",
    "dist",
    "build",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".ruff_cache",
    ".nur-runtime",
    "playwright-report",
    "test-results",
    "evidence",
    "release",
}
skip_names = {
    ".env",
    ".env.local",
    "dump.rdb",
    "NUR_RECENTLY_CHANGED_FILES.txt",
    "NUR_WIP_FILE_LIST.txt",
}
skip_prefixes = ("BUILD_WEEK", "COU" + "SIN_", "FABLE_")
secret_patterns = [
    re.compile(rb"sk-[A-Za-z0-9_-]{16,}"),
    re.compile(rb"(?i)authorization:\s*bearer\s+[A-Za-z0-9._~+/=-]{12,}"),
    re.compile(rb"(?i)(?:openai_api_key|api[_-]?key|secret[_-]?key)\s*[=:]\s*[\"']?[A-Za-z0-9._~+/=-]{12,}"),
]


def excluded(relative: PurePosixPath) -> bool:
    if not relative.parts:
        return True
    if relative.parts[0] in skip_roots:
        return True
    if any(part in skip_roots for part in relative.parts):
        return True
    if relative.name in skip_names or relative.name.startswith(skip_prefixes):
        return True
    if relative.name.startswith(".env.") and relative.name != ".env.example":
        return True
    if relative.suffix in {".pyc", ".pyo", ".tsbuildinfo"}:
        return True
    if relative.parts[:2] == ("docs", "v5"):
        return True
    return False


def verify_payload(name: str, payload: bytes) -> None:
    for pattern in secret_patterns:
        if pattern.search(payload):
            raise SystemExit(f"Secret-like value found while packaging {name}")


def zip_info(name: str, mode: int) -> zipfile.ZipInfo:
    info = zipfile.ZipInfo(name)
    info.date_time = (2026, 1, 1, 0, 0, 0)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = (mode & 0xFFFF) << 16
    return info


tracked_raw = subprocess.check_output(["git", "ls-files", "-z"], cwd=root)
tracked = [
    item.decode("utf-8", "surrogateescape")
    for item in tracked_raw.split(b"\0")
    if item
]
entries: dict[str, tuple[bytes, int, str]] = {}
for relative_text in tracked:
    relative = PurePosixPath(relative_text)
    if excluded(relative):
        continue
    source = root / relative_text
    if source.is_symlink():
        raise SystemExit(f"Release package refuses tracked symlink: {relative}")
    payload = source.read_bytes()
    verify_payload(str(relative), payload)
    mode = source.stat().st_mode
    archive_name = f"NUR/{relative.as_posix()}"
    entries[archive_name] = (payload, mode, "source")

if evidence_dir and evidence_dir.is_dir():
    for source in sorted(evidence_dir.rglob("*")):
        if not source.is_file() or source.is_symlink():
            continue
        relative = source.relative_to(evidence_dir)
        if excluded(PurePosixPath(*relative.parts)):
            continue
        payload = source.read_bytes()
        verify_payload(f"evidence/{relative.as_posix()}", payload)
        archive_name = f"NUR/evidence/{relative.as_posix()}"
        entries[archive_name] = (payload, source.stat().st_mode, "evidence")

archive_entries = []
for name, (payload, mode, source_class) in sorted(entries.items()):
    archive_entries.append({
        "path": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "mode": stat.S_IMODE(mode),
        "class": source_class,
    })

manifest = {
    "schema_version": 1,
    "product": "NUR",
    "version": os.environ["NUR_PACKAGE_VERSION"],
    "verdict": os.environ["NUR_PACKAGE_VERDICT"],
    "date": os.environ["NUR_PACKAGE_DATE"],
    "created_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
    "source": {
        "commit_sha": os.environ["NUR_PACKAGE_SOURCE_SHA"],
        "branch": os.environ["NUR_PACKAGE_SOURCE_BRANCH"],
    },
    "canonical_v197": {
        "path": "NUR/apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html",
        "sha256": hashlib.sha256(
            (root / "apps/web/public/v197/NUR_V197_CHECKBOX_TICK_RESTORED.html").read_bytes()
        ).hexdigest(),
    },
    "archive_entries": archive_entries,
}
manifest_payload = json.dumps(manifest, indent=2, sort_keys=True).encode() + b"\n"
verify_payload(manifest_path.name, manifest_payload)
manifest_path.write_bytes(manifest_payload)

zip_path.unlink(missing_ok=True)
with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
    for name, (payload, mode, _) in sorted(entries.items()):
        archive.writestr(zip_info(name, mode), payload, compresslevel=9)
PY

sha256sum "$ZIP" | tee "$SHA_FILE"
printf 'Release package: %s\n' "$ZIP"
printf 'Release manifest: %s\n' "$MANIFEST"
printf 'Release SHA-256: %s\n' "$SHA_FILE"
