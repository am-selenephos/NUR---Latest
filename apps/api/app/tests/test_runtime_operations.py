"""Executable contracts for fail-closed DR and local recovery tooling."""

from __future__ import annotations

import json
import os
import shlex
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[4]
BACKUP_SCRIPT = REPO_ROOT / "infra" / "scripts" / "dr-backup.sh"
RESTORE_SCRIPT = REPO_ROOT / "infra" / "scripts" / "dr-restore.sh"
DRILL_SCRIPT = REPO_ROOT / "infra" / "scripts" / "dr-drill.sh"
RECOVERY_SCRIPT = REPO_ROOT / "infra" / "scripts" / "runtime-recovery-drill.sh"


def _executable(path: Path, body: str) -> Path:
    path.write_text("#!/usr/bin/env bash\nset -euo pipefail\n" + body)
    path.chmod(0o755)
    return path


def test_backup_propagates_an_object_copy_failure(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "pg_dump",
        """
while (( $# )); do
  if [[ "$1" == "--file" ]]; then
    shift
    printf 'PGDMP' > "$1"
  fi
  shift
done
""",
    )
    _executable(fake_bin / "psql", "printf '0059_exact_email_lookup_runtime\\n'\n")
    _executable(fake_bin / "cp", "exit 73\n")
    fake_python = _executable(fake_bin / "python", "exit 99\n")

    objects = tmp_path / "objects"
    objects.mkdir()
    (objects / "one").write_bytes(b"one")
    output = tmp_path / "backup"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "NUR_DR_DATABASE_URL": "postgresql://example.invalid/nur",
        "NUR_DR_OBJECT_ROOT": str(objects),
        "NUR_DR_PYTHON": str(fake_python),
    }

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT), str(output)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 73, result.stderr
    assert not (output / "manifest.json").exists()


def test_backup_refuses_a_reused_nonempty_destination(tmp_path: Path) -> None:
    output = tmp_path / "backup"
    output.mkdir()
    (output / "stale-object").write_text("must not survive into a new backup")
    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT), str(output)],
        cwd=REPO_ROOT,
        env={**os.environ, "NUR_DR_DATABASE_URL": "postgresql://example.invalid/nur"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "empty new directory" in result.stderr


def test_backup_propagates_a_revision_lookup_failure(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    _executable(
        fake_bin / "pg_dump",
        """
while (( $# )); do
  if [[ "$1" == "--file" ]]; then
    shift
    printf 'PGDMP' > "$1"
  fi
  shift
done
""",
    )
    _executable(fake_bin / "psql", "exit 75\n")
    fake_python = _executable(fake_bin / "python", "exit 99\n")
    output = tmp_path / "backup"
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "NUR_DR_DATABASE_URL": "postgresql://example.invalid/nur",
        "NUR_DR_OBJECT_ROOT": str(tmp_path / "absent-object-root"),
        "NUR_DR_PYTHON": str(fake_python),
    }

    result = subprocess.run(
        ["bash", str(BACKUP_SCRIPT), str(output)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 75, result.stderr
    assert not (output / "manifest.json").exists()


def test_restore_stages_objects_before_destructive_database_work(tmp_path: Path) -> None:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    marker = tmp_path / "pg-restore-called"
    _executable(fake_bin / "sha256sum", "exit 0\n")
    _executable(fake_bin / "cp", "exit 74\n")
    _executable(fake_bin / "pg_restore", f"touch {shlex.quote(str(marker))}\n")
    _executable(fake_bin / "psql", "exit 99\n")
    fake_python = _executable(
        fake_bin / "python",
        """
if [[ "${1:-}" == "-c" ]]; then
  printf '0059_exact_email_lookup_runtime\\n'
fi
exit 0
""",
    )

    backup = tmp_path / "backup"
    (backup / "objects").mkdir(parents=True)
    (backup / "objects" / "one").write_bytes(b"one")
    (backup / "db.dump").write_bytes(b"PGDMP")
    (backup / "manifest.json").write_text(
        json.dumps({"alembic_revision": "0059_exact_email_lookup_runtime"})
    )
    (backup / "manifest.json.sha256").write_text("fixture\n")
    env = {
        **os.environ,
        "PATH": f"{fake_bin}:{os.environ['PATH']}",
        "NUR_DR_RESTORE_DATABASE_URL": "postgresql://example.invalid/restore",
        "NUR_DR_RESTORE_OBJECT_ROOT": str(tmp_path / "restored-objects"),
        "NUR_DR_RESTORE_CONFIRM_DATABASE": "restore",
        "NUR_DR_RESTORE_CONFIRM_OBJECT_ROOT": str(tmp_path / "restored-objects"),
        "NUR_DR_PYTHON": str(fake_python),
    }

    result = subprocess.run(
        ["bash", str(RESTORE_SCRIPT), str(backup)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 74, result.stderr
    assert not marker.exists(), "database restore ran after the staged object copy failed"


def test_restore_refuses_filesystem_root_before_reading_the_archive(tmp_path: Path) -> None:
    fake_python = _executable(tmp_path / "python", "exit 99\n")
    result = subprocess.run(
        ["bash", str(RESTORE_SCRIPT), str(tmp_path / "missing-backup")],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "NUR_DR_RESTORE_DATABASE_URL": "postgresql://example.invalid/restore",
            "NUR_DR_RESTORE_OBJECT_ROOT": "/",
            "NUR_DR_RESTORE_CONFIRM_DATABASE": "restore",
            "NUR_DR_RESTORE_CONFIRM_OBJECT_ROOT": "/",
            "NUR_DR_PYTHON": str(fake_python),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "filesystem root" in result.stderr


def test_restore_requires_exact_destructive_target_confirmation(tmp_path: Path) -> None:
    root = tmp_path / "objects"
    result = subprocess.run(
        ["bash", str(RESTORE_SCRIPT), str(tmp_path / "missing-backup")],
        cwd=REPO_ROOT,
        env={
            **os.environ,
            "NUR_DR_RESTORE_DATABASE_URL": "postgresql://example.invalid/restore",
            "NUR_DR_RESTORE_OBJECT_ROOT": str(root),
            "NUR_DR_RESTORE_CONFIRM_DATABASE": "wrong_database",
            "NUR_DR_RESTORE_CONFIRM_OBJECT_ROOT": str(root),
        },
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "confirmation" in result.stderr.lower()


def test_dr_scripts_preserve_database_owners_and_privileges() -> None:
    backup = BACKUP_SCRIPT.read_text()
    restore = RESTORE_SCRIPT.read_text()

    assert "--no-owner" not in backup
    assert "--no-privileges" not in backup
    assert "--no-owner" not in restore
    assert "--no-privileges" not in restore
    assert 'cmp -s "$SOURCE_OBJECTS_BEFORE" "$SOURCE_OBJECTS_AFTER"' in backup
    assert 'cmp -s "$SOURCE_OBJECTS_AFTER" "$COPIED_OBJECTS"' in backup


def test_drill_fingerprints_all_durable_database_surfaces() -> None:
    source = DRILL_SCRIPT.read_text()

    assert "row_to_json(t)::text" in source
    assert "FROM pg_sequences" in source
    assert "FROM pg_policies" in source
    assert "information_schema.role_table_grants" in source
    assert "FROM pg_proc" in source
    assert "FROM pg_trigger" in source
    assert "pg_get_expr" in source
    assert "pg_get_functiondef" in source
    assert "runtime_role_probe" in source
    assert 'cmp -s "$SRC_BEFORE" "$SRC_AFTER"' in source
    assert 'cmp -s "$SRC_BEFORE" "$TARGET_FINGERPRINT"' in source


def test_recovery_drill_is_local_and_opt_in() -> None:
    result = subprocess.run(
        ["bash", str(RECOVERY_SCRIPT)],
        cwd=REPO_ROOT,
        env={key: value for key, value in os.environ.items() if key != "NUR_RECOVERY_DRILL_CONFIRM"},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert "NUR_RECOVERY_DRILL_CONFIRM=local-only" in result.stderr
