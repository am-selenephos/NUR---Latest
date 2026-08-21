#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

SOURCE="$TMP/NUR package source with spaces"
OUTPUT="$TMP/release output"
mkdir -p "$SOURCE" "$OUTPUT"

export NUR_TEST_COPY_ROOT="$ROOT"
export NUR_TEST_COPY_TARGET="$SOURCE"
python3 - <<'PY'
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

root = Path(os.environ["NUR_TEST_COPY_ROOT"])
target = Path(os.environ["NUR_TEST_COPY_TARGET"])
raw = subprocess.check_output(
    ["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root
)
for encoded in raw.split(b"\0"):
    if not encoded:
        continue
    relative = Path(encoded.decode("utf-8", "surrogateescape"))
    source = root / relative
    destination = target / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(os.readlink(source))
    else:
        shutil.copy2(source, destination)
PY

(
  cd "$SOURCE"
  git init -q
  git config user.name 'NUR release test'
  git config user.email 'release-test@invalid.example'
  git add -A
  git commit -qm 'test fixture'
  NUR_RELEASE_DATE=20260820 \
    bash infra/scripts/package-release.sh --verdict HOLD --output-dir "$OUTPUT"
)

ZIP="$OUTPUT/NUR_V5_HOLD_20260820.zip"
MANIFEST="$OUTPUT/NUR_V5_HOLD_20260820_MANIFEST.json"
SOURCE_SHA="$(git -C "$SOURCE" rev-parse HEAD)"

python3 - "$MANIFEST" "$SOURCE_SHA" <<'PY'
from __future__ import annotations

import json
import sys

manifest = json.load(open(sys.argv[1], encoding="utf-8"))
assert manifest["source"]["commit_sha"] == sys.argv[2]
assert len(manifest["sboms"]) == 2
assert {item["ecosystem"] for item in manifest["sboms"]} == {"node", "python"}
assert all(item["source_git_sha"] == sys.argv[2] for item in manifest["sboms"])
PY

valid_output="$(
  NUR_VERIFY_INSTALL=0 NUR_VERIFY_COLD_BOOT=0 \
    bash "$SOURCE/infra/scripts/verify-release-package.sh" "$ZIP"
)"
[[ "$valid_output" == *"SBOM_NODE=PASS"* ]]
[[ "$valid_output" == *"SBOM_PYTHON=PASS"* ]]
[[ "$valid_output" == *"FULL_STACK_COLD_BOOT=NOT_RUN_REQUIRES_POSTGRES_REDIS"* ]]

export NUR_TEST_BASE_ZIP="$ZIP"
export NUR_TEST_BASE_MANIFEST="$MANIFEST"
export NUR_TEST_ATTACK_DIR="$TMP/attacks"
python3 - <<'PY'
from __future__ import annotations

import hashlib
import json
import os
import stat
import warnings
import zipfile
from copy import deepcopy
from pathlib import Path

base_zip = Path(os.environ["NUR_TEST_BASE_ZIP"])
base_manifest = json.loads(Path(os.environ["NUR_TEST_BASE_MANIFEST"]).read_text())
attack_dir = Path(os.environ["NUR_TEST_ATTACK_DIR"])
attack_dir.mkdir()
warnings.filterwarnings("ignore", message="Duplicate name:.*")

with zipfile.ZipFile(base_zip) as archive:
    base_entries = [(deepcopy(info), archive.read(info)) for info in archive.infolist()]


def record(name: str, payload: bytes, mode: int = 0o100644) -> dict:
    return {
        "path": name,
        "sha256": hashlib.sha256(payload).hexdigest(),
        "bytes": len(payload),
        "mode": stat.S_IMODE(mode),
        "class": "source",
    }


def write_case(name: str, entries: list[tuple[zipfile.ZipInfo, bytes]], manifest: dict) -> None:
    zip_path = attack_dir / f"{name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as archive:
        for info, payload in entries:
            archive.writestr(info, payload)
    manifest_path = attack_dir / f"{name}_MANIFEST.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    digest = hashlib.sha256(zip_path.read_bytes()).hexdigest()
    (attack_dir / f"{name}.zip.sha256").write_text(f"{digest}  {name}.zip\n")


duplicate_entries = list(base_entries)
duplicate_entries.append((deepcopy(base_entries[0][0]), base_entries[0][1]))
write_case("duplicate", duplicate_entries, deepcopy(base_manifest))

traversal_manifest = deepcopy(base_manifest)
traversal_info = zipfile.ZipInfo("NUR/../escape.txt")
traversal_payload = b"escape"
traversal_manifest["archive_entries"].append(record(traversal_info.filename, traversal_payload))
write_case("traversal", [*base_entries, (traversal_info, traversal_payload)], traversal_manifest)

symlink_manifest = deepcopy(base_manifest)
symlink_info = zipfile.ZipInfo("NUR/unsafe-link")
symlink_info.create_system = 3
symlink_info.external_attr = (stat.S_IFLNK | 0o777) << 16
symlink_payload = b"README.md"
symlink_manifest["archive_entries"].append(
    record(symlink_info.filename, symlink_payload, stat.S_IFLNK | 0o777)
)
write_case("symlink", [*base_entries, (symlink_info, symlink_payload)], symlink_manifest)

secret_manifest = deepcopy(base_manifest)
secret_info = zipfile.ZipInfo("NUR/unsafe-secret.txt")
secret_payload = ("OPENAI" + "_API_KEY=" + "sk-" + "A" * 32).encode()
secret_manifest["archive_entries"].append(record(secret_info.filename, secret_payload))
write_case("secret", [*base_entries, (secret_info, secret_payload)], secret_manifest)

v197_manifest = deepcopy(base_manifest)
v197_path = v197_manifest["canonical_v197"]["path"]
v197_entries = []
for info, payload in base_entries:
    if info.filename == v197_path:
        payload += b"\nmodified\n"
        for item in v197_manifest["archive_entries"]:
            if item["path"] == v197_path:
                item.update(record(v197_path, payload))
                break
    v197_entries.append((info, payload))
write_case("v197", v197_entries, v197_manifest)

sbom_manifest = deepcopy(base_manifest)
sbom_path = sbom_manifest["sboms"][0]["path"]
sbom_entries = []
for info, payload in base_entries:
    if info.filename == sbom_path:
        document = json.loads(payload)
        for item in document["metadata"]["properties"]:
            if item["name"] == "source.git_sha":
                item["value"] = "0" * 40
        payload = (json.dumps(document, indent=2, sort_keys=True) + "\n").encode()
        for item in sbom_manifest["archive_entries"]:
            if item["path"] == sbom_path:
                item.update(record(sbom_path, payload))
                break
        sbom_manifest["sboms"][0]["sha256"] = hashlib.sha256(payload).hexdigest()
    sbom_entries.append((info, payload))
write_case("sbom-source", sbom_entries, sbom_manifest)

missing_sbom_manifest = deepcopy(base_manifest)
missing_sbom_path = missing_sbom_manifest["sboms"][1]["path"]
missing_sbom_entries = [
    (info, payload) for info, payload in base_entries if info.filename != missing_sbom_path
]
missing_sbom_manifest["archive_entries"] = [
    item for item in missing_sbom_manifest["archive_entries"] if item["path"] != missing_sbom_path
]
write_case("sbom-missing", missing_sbom_entries, missing_sbom_manifest)
PY

assert_rejected() {
  local name="$1"
  local expected="$2"
  local output
  local status
  set +e
  output="$(
    NUR_VERIFY_INSTALL=0 NUR_VERIFY_COLD_BOOT=0 \
      bash "$SOURCE/infra/scripts/verify-release-package.sh" "$TMP/attacks/$name.zip" 2>&1
  )"
  status=$?
  set -e
  [[ "$status" -ne 0 ]]
  [[ "$output" == *"$expected"* ]]
}

assert_rejected duplicate 'Duplicate ZIP entry'
assert_rejected traversal 'Unsafe archive path'
assert_rejected symlink 'symlink'
assert_rejected secret 'Secret-like value'
assert_rejected v197 'Canonical V197 hash'
assert_rejected sbom-source 'SBOM source SHA mismatch'
assert_rejected sbom-missing 'Required python SBOM is missing'

cp "$ZIP" "$TMP/attacks/full-pass.zip"
(cd "$TMP/attacks" && sha256sum full-pass.zip > full-pass.zip.sha256)
python3 - "$MANIFEST" "$TMP/attacks/full-pass_MANIFEST.json" <<'PY'
import json
import sys
manifest = json.load(open(sys.argv[1], encoding="utf-8"))
manifest["verdict"] = "FULL_PASS"
open(sys.argv[2], "w", encoding="utf-8").write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
PY
set +e
full_pass_output="$(
  NUR_VERIFY_INSTALL=0 \
  NUR_VERIFY_COLD_BOOT=0 \
  NUR_VERIFY_STATIC_CHECKS=0 \
  NUR_VERIFY_BUILD_CHECKS=0 \
    bash "$SOURCE/infra/scripts/verify-release-package.sh" "$TMP/attacks/full-pass.zip" 2>&1
)"
full_pass_status=$?
set -e
[[ "$full_pass_status" -ne 0 ]]
[[ "$full_pass_output" == *"FULL_PASS package verification may not disable static or build checks"* ]]

cp "$ZIP" "$TMP/attacks/checksum-target.zip"
cp "$MANIFEST" "$TMP/attacks/checksum-target_MANIFEST.json"
printf '%s  %s\n' "$(sha256sum "$ZIP" | awk '{print $1}')" "$ZIP" > "$TMP/attacks/checksum-target.zip.sha256"
set +e
checksum_output="$(
  NUR_VERIFY_INSTALL=0 NUR_VERIFY_COLD_BOOT=0 \
    bash "$SOURCE/infra/scripts/verify-release-package.sh" "$TMP/attacks/checksum-target.zip" 2>&1
)"
checksum_status=$?
set -e
[[ "$checksum_status" -ne 0 ]]
[[ "$checksum_output" == *"Package SHA file does not name the requested ZIP"* ]]

printf 'release package fresh extract: PASS\n'
