#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATE_STAMP="${NUR_PACKAGE_DATE:-$(date +%Y%m%d)}"
OUT="${1:-/home/nur/Downloads/NUR_FULL_SYSTEM_COMPLETE_V197_AI_${DATE_STAMP}.zip}"
SHA="${OUT}.sha256"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

export NUR_PACKAGE_ROOT="$ROOT"
export NUR_PACKAGE_OUT="$OUT"
export NUR_PACKAGE_TMP="$TMP"

python3 - <<'PY'
from __future__ import annotations

import os
import shutil
import stat
import zipfile
from pathlib import Path

root = Path(os.environ["NUR_PACKAGE_ROOT"]).resolve()
tmp = Path(os.environ["NUR_PACKAGE_TMP"]).resolve()
dest = tmp / "NUR"
out = Path(os.environ["NUR_PACKAGE_OUT"]).resolve()

skip_dirs = {
    ".git", "node_modules", "dist", "build", ".venv", "__pycache__",
    ".pytest_cache", ".ruff_cache", "nur_api.egg-info", ".nur-runtime",
    "playwright-report", "test-results", "proof", "evidence", "logs",
    "tmp", "secrets", "checkpoint",
}
skip_files = {".env", ".env.local", "dump.rdb", "remaining-gaps.md"}
# Internal construction/design history: kept in the repo as a development record,
# never shipped in the public release archive (they carry build-process naming).
skip_name_prefixes = ("BUILD_WEEK", "FABLE_")
# docs/v5 holds versioned construction planning (orchestrator/ledger/masterplan)
# with builder-agent and lane terminology — internal only, never in the package.
skip_rel_dirs = {("docs", "v5")}

def should_skip(path: Path) -> bool:
    rel = path.relative_to(root)
    parts = set(rel.parts)
    if parts & skip_dirs:
        return True
    if any(rel.parts[:len(prefix)] == prefix for prefix in skip_rel_dirs):
        return True
    if any(part.startswith("playwright-report") for part in rel.parts):
        return True
    if path.name in skip_files:
        return True
    if path.name.startswith(skip_name_prefixes):
        return True
    if path.name.startswith("playwright-report"):
        return True
    if path.name.startswith("celerybeat-schedule"):
        return True
    if path.name.startswith(".env.") and path.name != ".env.example":
        return True
    if path.suffix in {".pyc", ".pyo", ".tsbuildinfo"}:
        return True
    return False

for src in root.rglob("*"):
    if should_skip(src):
        if src.is_dir():
            continue
        continue
    rel = src.relative_to(root)
    target = dest / rel
    if src.is_dir():
        target.mkdir(parents=True, exist_ok=True)
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, target)

for script in (dest / "infra" / "scripts").glob("*.sh"):
    mode = script.stat().st_mode
    script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
for script_name in ("RUN_NUR.sh", "RUN_NUR.command", "START_NUR.sh", "START_NUR.desktop"):
    script = dest / script_name
    if script.exists():
        mode = script.stat().st_mode
        script.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

out.parent.mkdir(parents=True, exist_ok=True)
if out.exists():
    out.unlink()
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
    for src in sorted(dest.rglob("*")):
        if src.is_file():
            zf.write(src, src.relative_to(tmp))

forbidden_fragments = [
    "/.git/", "/node_modules/", "/dist/", "/build/", "/.venv/",
    "/.nur-runtime/", "/playwright-report/", "/test-results/", "/proof/",
    "/evidence/", "/logs/", "/secrets/", "/checkpoint/",
]
forbidden_names = {"NUR/.env", "NUR/.env.local", "NUR/apps/api/dump.rdb"}
with zipfile.ZipFile(out) as zf:
    names = set(zf.namelist())
    bad = [
        n for n in names
        if n in forbidden_names
        or Path(n).name.startswith("celerybeat-schedule")
        or Path(n).name.startswith("playwright-report")
        or Path(n).suffix == ".tsbuildinfo"
        or any(fragment in f"/{n}" for fragment in forbidden_fragments)
    ]
    secret_like = [n for n in names if n.endswith(".env.local") or (Path(n).name.startswith(".env.") and Path(n).name != ".env.example")]
if bad or secret_like:
    raise SystemExit(f"Forbidden bootable entries found: {bad + secret_like}")
print(out)
PY

(cd "$TMP/NUR" && bash infra/scripts/secret-scan.sh)
sha256sum "$OUT" | tee "$SHA"
printf 'Bootable package ready: %s\n' "$OUT"
