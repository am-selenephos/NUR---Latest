"""Storage hygiene: orphan reconciliation, deletion hygiene, retention (Phase 8).

Proves orphaned bytes (on disk, no row) are found and swept while dangling rows
(row, no bytes) are surfaced not hidden; that deleting a file actually removes
its bytes and leaves no orphan; and that DELETED file rows are purged after the
retention window.
"""

import datetime as dt
import uuid
from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.db.rls import set_user_context
from app.db.session import get_sessionmaker
from app.models import AMProjectFile
from app.models._mixins import now_utc
from app.services.object_storage import (
    LocalObjectStorage,
    bytes_stream,
    get_object_storage,
)
from app.services.storage_hygiene import (
    assert_cross_owner_maintenance_role,
    purge_deleted_files,
    reconcile_exit_code,
    reconcile_object_index,
    sweep_orphan_objects,
)
from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _scoped_db(owner_id: str):
    db = get_sessionmaker()()
    await set_user_context(db, uuid.UUID(owner_id))
    return db


async def _make_project(client) -> str:
    r = await client.post(
        "/api/v1/projects", headers=H(client),
        json={"title": "Hygiene", "objective": "Keep storage and rows in sync."},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


def test_reconcile_object_index_separates_orphans_from_dangling():
    report = reconcile_object_index(
        db_object_keys=["a" * 32, "b" * 32],           # b has no bytes on disk
        disk_object_keys=["a" * 32, "c" * 32],          # c has no row
    )
    assert report.orphans == ["c" * 32]
    assert report.dangling == ["b" * 32]
    assert not report.clean
    assert reconcile_object_index(db_object_keys=["a" * 32], disk_object_keys=["a" * 32]).clean


class _RoleProbeResult:
    def __init__(self, *, name: str, superuser: bool, bypass_rls: bool) -> None:
        self._row = {
            "rolname": name,
            "rolsuper": superuser,
            "rolbypassrls": bypass_rls,
        }

    def mappings(self):
        return SimpleNamespace(one=lambda: self._row)


class _RoleProbeSession:
    def __init__(self, *, name: str, superuser: bool = False, bypass_rls: bool = False) -> None:
        self._result = _RoleProbeResult(
            name=name,
            superuser=superuser,
            bypass_rls=bypass_rls,
        )

    async def execute(self, _statement):
        return self._result


async def test_cross_owner_reconcile_refuses_rls_scoped_runtime_role():
    db = _RoleProbeSession(name="nur_app")
    with pytest.raises(RuntimeError, match="BYPASSRLS"):
        await assert_cross_owner_maintenance_role(db)  # type: ignore[arg-type]


async def test_cross_owner_reconcile_accepts_narrow_bypass_maintenance_role():
    db = _RoleProbeSession(name="nur_storage_maintenance", bypass_rls=True)
    assert await assert_cross_owner_maintenance_role(db) == "nur_storage_maintenance"  # type: ignore[arg-type]


def test_reconcile_exit_code_reports_unresolved_drift():
    clean = reconcile_object_index(db_object_keys=["a" * 32], disk_object_keys=["a" * 32])
    orphan = reconcile_object_index(db_object_keys=[], disk_object_keys=["b" * 32])
    dangling = reconcile_object_index(db_object_keys=["c" * 32], disk_object_keys=[])

    assert reconcile_exit_code(clean, delete_orphans=False) == 0
    assert reconcile_exit_code(orphan, delete_orphans=False) == 2
    assert reconcile_exit_code(orphan, delete_orphans=True) == 0
    assert reconcile_exit_code(dangling, delete_orphans=True) == 2


async def test_sweep_deletes_orphan_bytes_only(tmp_path):
    storage = LocalObjectStorage(tmp_path / "objects")
    kept = await storage.put(bytes_stream(b"owned by a real row"), max_bytes=1024)
    orphan = await storage.put(bytes_stream(b"no row points at me"), max_bytes=1024)

    report = sweep_orphan_objects(
        storage, db_object_keys=[kept.object_key], delete_orphans=True
    )
    assert report.orphans == [orphan.object_key]
    assert report.dangling == []
    assert storage.exists(kept.object_key) is True       # live object untouched
    assert storage.exists(orphan.object_key) is False    # orphan bytes removed


async def test_delete_file_removes_bytes_and_leaves_no_orphan(client):
    owner = (await register_user(client, chosen_name="Delete Owner"))[0].json()["id"]
    project_id = await _make_project(client)
    up = await client.post(
        f"/api/v1/projects/{project_id}/files", headers=H(client),
        files={"upload": ("gone.txt", b"soon to be deleted", "text/plain")},
    )
    assert up.status_code == 201, up.text
    file_id = up.json()["id"]

    db = await _scoped_db(owner)
    try:
        object_key = (await db.execute(
            select(AMProjectFile.object_key).where(AMProjectFile.id == uuid.UUID(file_id))
        )).scalar_one()
    finally:
        await db.close()

    storage = get_object_storage()
    assert storage.exists(object_key) is True

    deleted = await client.delete(f"/api/v1/projects/files/{file_id}", headers=H(client))
    assert deleted.status_code == 200, deleted.text
    assert deleted.json()["storage_state"] == "DELETED"

    # The bytes are gone and no orphan is left behind on disk.
    assert storage.exists(object_key) is False
    assert object_key not in set(storage.iter_object_keys())


async def test_purge_removes_deleted_rows_past_retention_window(client):
    owner = (await register_user(client, chosen_name="Retention Owner"))[0].json()["id"]
    project_id = await _make_project(client)
    kept = (await client.post(
        f"/api/v1/projects/{project_id}/files", headers=H(client),
        files={"upload": ("keep.txt", b"still here", "text/plain")},
    )).json()["id"]
    doomed = (await client.post(
        f"/api/v1/projects/{project_id}/files", headers=H(client),
        files={"upload": ("purge.txt", b"marked deleted", "text/plain")},
    )).json()["id"]

    db = await _scoped_db(owner)
    try:
        row = (await db.execute(
            select(AMProjectFile).where(AMProjectFile.id == uuid.UUID(doomed))
        )).scalar_one()
        row.storage_state = "DELETED"
        await db.flush()  # keep the RLS GUC armed for the purge below

        # Retention is relative to "now"; view from a day ahead so the just-marked
        # row is safely past a 1-hour window without racing the wall clock.
        purged = await purge_deleted_files(
            db, older_than_seconds=3600, now=now_utc() + dt.timedelta(days=1)
        )
        assert purged == 1

        await set_user_context(db, uuid.UUID(owner))  # purge committed; re-arm
        remaining = set((await db.execute(select(AMProjectFile.id))).scalars().all())
        assert uuid.UUID(kept) in remaining
        assert uuid.UUID(doomed) not in remaining
    finally:
        await db.close()
