"""Stale-run recovery: dead-worker reclamation and dead-lettering (Phase 5).

A run claimed by a worker that then crashes stays RUNNING forever with no
recovery. These prove the reaper requeues a stale run still within its attempt
budget, dead-letters one that has exhausted its attempts (so it cannot retry
forever), and leaves a healthy in-flight run untouched.
"""

import datetime as dt
import uuid

from sqlalchemy import select

from app.db.rls import set_user_context
from app.db.session import get_sessionmaker
from app.models import AMProjectRun
from app.models._mixins import now_utc
from app.services.project_execution import recover_stale_runs
from app.tests.conftest import register_user
from app.workers import tasks as worker_tasks


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _scoped_db(owner_id: str):
    db = get_sessionmaker()()
    await set_user_context(db, uuid.UUID(owner_id))
    return db


async def _make_project(client) -> str:
    r = await client.post(
        "/api/v1/projects", headers=H(client),
        json={"title": "Recovery", "objective": "Reclaim stale runs."},
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _flush_running_run(db, *, owner: str, project_id: str, attempt: int, started_at):
    run = AMProjectRun(
        owner_user_id=uuid.UUID(owner),
        project_id=uuid.UUID(project_id),
        role="implementer",
        request_summary="stale-run recovery fixture",
        status="RUNNING",
        attempt=attempt,
        worker_id="dead-worker-1",
        started_at=started_at,
    )
    db.add(run)
    await db.flush()  # persist in-transaction without dropping the RLS GUC
    return run.id


async def test_stale_running_run_is_requeued_within_attempt_budget(client):
    owner = (await register_user(client, chosen_name="Recover Owner"))[0].json()["id"]
    project_id = await _make_project(client)
    db = await _scoped_db(owner)
    try:
        run_id = await _flush_running_run(
            db, owner=owner, project_id=project_id, attempt=1,
            started_at=now_utc() - dt.timedelta(seconds=3600),
        )
        result = await recover_stale_runs(db, stale_after_seconds=900, max_attempts=5)
        assert result == {"scanned": 1, "requeued": 1, "dead_lettered": 0}

        await set_user_context(db, uuid.UUID(owner))  # reaper committed; re-arm
        row = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))).scalar_one()
        assert row.status == "QUEUED"
        assert row.worker_id is None
        assert row.started_at is None
    finally:
        await db.close()


async def test_stale_running_run_is_dead_lettered_after_max_attempts(client):
    owner = (await register_user(client, chosen_name="Deadletter Owner"))[0].json()["id"]
    project_id = await _make_project(client)
    db = await _scoped_db(owner)
    try:
        run_id = await _flush_running_run(
            db, owner=owner, project_id=project_id, attempt=5,
            started_at=now_utc() - dt.timedelta(seconds=3600),
        )
        result = await recover_stale_runs(db, stale_after_seconds=900, max_attempts=5)
        assert result == {"scanned": 1, "requeued": 0, "dead_lettered": 1}

        await set_user_context(db, uuid.UUID(owner))
        row = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))).scalar_one()
        assert row.status == "FAILED"
        assert row.failure_code == "STALE_DEADLETTER"
        assert row.completed_at is not None
    finally:
        await db.close()


async def test_ops_recover_runs_endpoint_requeues_owner_stale_run(client):
    owner = (await register_user(client, chosen_name="Ops Recover"))[0].json()["id"]
    project_id = await _make_project(client)
    db = await _scoped_db(owner)
    try:
        run = AMProjectRun(
            owner_user_id=uuid.UUID(owner), project_id=uuid.UUID(project_id),
            role="implementer", request_summary="ops recovery fixture",
            status="RUNNING", attempt=1, worker_id="dead-worker-1",
            started_at=now_utc() - dt.timedelta(seconds=3600),
        )
        db.add(run)
        await db.commit()  # committed so the endpoint's own session sees it
        run_id = run.id
    finally:
        await db.close()

    # Default stale threshold (900s) < our 3600s-old run → requeued.
    r = await client.post("/api/v1/ops/recover-runs", headers=H(client))
    assert r.status_code == 200, r.text
    assert r.json()["recovered"] == {"scanned": 1, "requeued": 1, "dead_lettered": 0}

    db2 = await _scoped_db(owner)
    try:
        row = (await db2.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))).scalar_one()
        assert row.status == "QUEUED"
    finally:
        await db2.close()


async def test_fresh_running_run_is_not_reclaimed(client):
    owner = (await register_user(client, chosen_name="Fresh Owner"))[0].json()["id"]
    project_id = await _make_project(client)
    db = await _scoped_db(owner)
    try:
        run_id = await _flush_running_run(
            db, owner=owner, project_id=project_id, attempt=1, started_at=now_utc(),
        )
        result = await recover_stale_runs(db, stale_after_seconds=900, max_attempts=5)
        assert result["scanned"] == 0

        await set_user_context(db, uuid.UUID(owner))
        row = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))).scalar_one()
        assert row.status == "RUNNING"
    finally:
        await db.close()


async def test_scheduled_recovery_republishes_requeued_run_with_ids_only(client, monkeypatch):
    owner = (await register_user(client, chosen_name="Scheduled Recovery"))[0].json()["id"]
    project_id = await _make_project(client)
    db = await _scoped_db(owner)
    try:
        run_id = await _flush_running_run(
            db,
            owner=owner,
            project_id=project_id,
            attempt=1,
            started_at=now_utc() - dt.timedelta(seconds=3600),
        )
        await db.commit()
    finally:
        await db.close()

    published: list[tuple[str, str]] = []
    monkeypatch.setattr(
        worker_tasks.execute_project_run_task,
        "delay",
        lambda *args: published.append(args),
    )

    result = await worker_tasks._reconcile_project_runs_for_owner(uuid.UUID(owner))

    assert result == {
        "scanned": 1,
        "requeued": 1,
        "dead_lettered": 0,
        "dispatched": 1,
        "dispatch_failed": 0,
    }
    assert published == [(str(run_id), owner)]


async def test_recovery_broker_failure_leaves_run_queued_for_next_tick(client, monkeypatch):
    owner = (await register_user(client, chosen_name="Recovery Broker Outage"))[0].json()["id"]
    project_id = await _make_project(client)
    db = await _scoped_db(owner)
    try:
        run_id = await _flush_running_run(
            db,
            owner=owner,
            project_id=project_id,
            attempt=1,
            started_at=now_utc() - dt.timedelta(seconds=3600),
        )
        await db.commit()
    finally:
        await db.close()

    def unavailable(*_args):
        raise ConnectionError("broker unavailable")

    monkeypatch.setattr(worker_tasks.execute_project_run_task, "delay", unavailable)
    result = await worker_tasks._reconcile_project_runs_for_owner(uuid.UUID(owner))

    assert result["requeued"] == 1
    assert result["dispatched"] == 0
    assert result["dispatch_failed"] == 1

    db2 = await _scoped_db(owner)
    try:
        row = (
            await db2.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))
        ).scalar_one()
        assert row.status == "QUEUED"
    finally:
        await db2.close()
