"""Approval-gated, capability-bounded, deterministic AM Project execution (G14).

Proves the real execution spine: an approved EVIDENCE_PACKAGE run produces real
archive bytes in the object store, links a checksum-verified artifact + evidence,
enforces the deny-by-default capability catalog, and behaves correctly under
duplicate delivery, cancellation, timeout, adapter failure, retry and budget.
"""
import hashlib
import io
import zipfile

from sqlalchemy import select, text

from app.db.rls import set_user_context
from app.db.session import get_sessionmaker
from app.models import AMProjectArtifact, AMProjectRun
from app.models._mixins import now_utc
from app.services import project_execution
from app.services.object_storage import bytes_stream, get_object_storage
from app.services.project_execution import (
    AdapterFailure,
    AdapterOutput,
    execute_run,
)
from app.tests.conftest import register_user


def H(client) -> dict[str, str]:
    return {"X-CSRF-Token": client.cookies.get("nur_csrf")}


async def _scoped_db(owner_id: str):
    db = get_sessionmaker()()
    import uuid
    await set_user_context(db, uuid.UUID(owner_id))
    return db


async def _project_with_source(client) -> tuple[str, str, str]:
    project = (await client.post(
        "/api/v1/projects", headers=H(client),
        json={"title": "Deliverable project", "objective": "Package verifiable evidence.",
              "budget_cents": 1000},
    )).json()
    task = (await client.post(
        f"/api/v1/projects/{project['id']}/tasks", headers=H(client),
        json={"title": "Assemble the package", "acceptance_criteria": "A checksummed archive exists."},
    )).json()
    up = (await client.post(
        f"/api/v1/projects/{project['id']}/files", headers=H(client),
        files={"upload": ("source.txt", b"real source bytes\n" * 8, "text/plain")},
    )).json()
    return project["id"], task["id"], up["id"]


async def test_full_real_path_project_to_downloadable_verified_package(client):
    owner, _, _ = await register_user(client, chosen_name="Deliverable Owner")
    project_id, task_id, file_id = await _project_with_source(client)

    # Uploaded source bytes are server-verified before any run.
    assert (await client.post(f"/api/v1/projects/files/{file_id}/verify", headers=H(client))).json()["verified"] is True

    # A persisted agent binds the deterministic adapter with a safe capability grant.
    agent = (await client.post(
        f"/api/v1/projects/{project_id}/agents", headers=H(client),
        json={"name": "Packager", "adapter_key": "EVIDENCE_PACKAGE"},
    ))
    assert agent.status_code == 201, agent.text

    proposed = (await client.post(
        f"/api/v1/projects/{project_id}/runs", headers=H(client),
        json={"role": "verifier", "request_summary": "Package the evidence.",
              "adapter_key": "EVIDENCE_PACKAGE", "agent_id": agent.json()["id"],
              "task_id": task_id, "idempotency_key": "pkg-1"},
    ))
    assert proposed.status_code == 201, proposed.text
    run_id = proposed.json()["id"]
    assert proposed.json()["adapter_key"] == "EVIDENCE_PACKAGE"
    assert set(proposed.json()["requested_capabilities"]) == set(
        project_execution.ADAPTERS["EVIDENCE_PACKAGE"].required_capabilities
    )

    # A run cannot queue before approval.
    assert (await client.post(f"/api/v1/projects/runs/{run_id}/queue", headers=H(client))).status_code == 409

    approved = (await client.post(f"/api/v1/projects/runs/{run_id}/approve", headers=H(client))).json()
    assert approved["status"] == "APPROVED"
    assert set(approved["approved_capabilities"]) == set(approved["requested_capabilities"])

    queued = (await client.post(f"/api/v1/projects/runs/{run_id}/queue", headers=H(client)))
    assert queued.status_code == 200, queued.text
    run = queued.json()
    assert run["status"] == "SUCCEEDED", run
    assert run["output_artifact_id"]
    assert run["worker_id"] == "inline"
    assert run["attempt"] == 1
    assert run["cost_cents"] == 0

    # A checksum-verified, RUN_GENERATED artifact was linked to the run + task.
    artifacts = (await client.get(f"/api/v1/projects/{project_id}/artifacts")).json()
    generated = [a for a in artifacts if a["provenance_label"] == "RUN_GENERATED"]
    assert len(generated) == 1
    art = generated[0]
    assert art["run_id"] == run_id and art["task_id"] == task_id
    assert art["checksum_sha256"] and art["artifact_kind"] == "EVIDENCE_PACKAGE"

    # Run evidence was persisted and PASSED by the adapter.
    evidence = (await client.get(f"/api/v1/projects/{project_id}/evidence")).json()
    run_ev = [e for e in evidence if e["evidence_kind"] == "RUN_OUTPUT"]
    assert run_ev and run_ev[0]["verification_status"] == "PASSED"
    assert run_ev[0]["verifier"] == "adapter:EVIDENCE_PACKAGE@1"

    # The generated package is a real, downloadable file with matching checksum.
    files = (await client.get(f"/api/v1/projects/{project_id}/files")).json()
    outputs = [f for f in files if f["provenance"] == "RUN_OUTPUT"]
    assert len(outputs) == 1
    pkg = outputs[0]
    assert pkg["run_id"] == run_id
    dl = await client.get(f"/api/v1/projects/files/{pkg['id']}/download")
    assert dl.status_code == 200
    assert hashlib.sha256(dl.content).hexdigest() == pkg["checksum_sha256"] == art["checksum_sha256"]
    # The bytes are a real archive containing the deterministic manifest.
    with zipfile.ZipFile(io.BytesIO(dl.content)) as zf:
        names = set(zf.namelist())
        assert {"manifest.json", "checksums.txt", "reproducibility.json", "envelope.json"} <= names

    # Reload preserves the run, artifact and files.
    reload = (await client.get(f"/api/v1/projects/runs/{run_id}")).json()
    assert reload["status"] == "SUCCEEDED" and reload["output_artifact_id"] == art["id"]

    # Owner review + project lifecycle.
    review = await client.post(
        f"/api/v1/projects/{project_id}/reviews", headers=H(client),
        json={"run_id": run_id, "decision": "APPROVE", "note": "Package checksum verified."},
    )
    assert review.status_code == 201

    # Unrelated owner cannot access the run, artifact bytes or files.
    client.cookies.clear()
    await register_user(client, chosen_name="Stranger")
    assert (await client.get(f"/api/v1/projects/runs/{run_id}")).status_code == 404
    assert (await client.get(f"/api/v1/projects/files/{pkg['id']}/download")).status_code == 404
    assert (await client.get(f"/api/v1/projects/{project_id}/artifacts")).status_code == 404


async def test_denied_capabilities_and_unknown_adapter_are_rejected(client):
    await register_user(client, chosen_name="Boundary Owner")
    project = (await client.post(
        "/api/v1/projects", headers=H(client),
        json={"title": "Boundary", "objective": "Deny by default."},
    )).json()
    pid = project["id"]

    # A denied capability cannot be requested on a run.
    r1 = await client.post(
        f"/api/v1/projects/{pid}/runs", headers=H(client),
        json={"role": "operator", "request_summary": "Escalate.",
              "adapter_key": "EVIDENCE_PACKAGE", "requested_capabilities": ["shell.exec"]},
    )
    assert r1.status_code == 422 and "denied" in r1.json()["detail"].lower()

    # Capabilities cannot be requested without an adapter.
    r2 = await client.post(
        f"/api/v1/projects/{pid}/runs", headers=H(client),
        json={"role": "operator", "request_summary": "No adapter.",
              "requested_capabilities": ["file.read"]},
    )
    assert r2.status_code == 422

    # An unknown adapter is rejected.
    r3 = await client.post(
        f"/api/v1/projects/{pid}/runs", headers=H(client),
        json={"role": "operator", "request_summary": "Ghost.", "adapter_key": "NOPE"},
    )
    assert r3.status_code == 422

    # An agent cannot be granted a denied capability.
    a1 = await client.post(
        f"/api/v1/projects/{pid}/agents", headers=H(client),
        json={"name": "Rogue", "adapter_key": "EVIDENCE_PACKAGE",
              "allowed_capabilities": ["network.arbitrary"]},
    )
    assert a1.status_code == 422

    # The capability catalog is inspectable and lists the deny set.
    caps = (await client.get("/api/v1/projects/execution/capabilities")).json()
    assert "shell.exec" in caps["denied_capabilities"]
    assert any(a["key"] == "EVIDENCE_PACKAGE" and a["status"] == "LIVE_REAL" for a in caps["adapters"])
    assert any(b["status"] == "BLOCKED_BY_EXTERNAL_PROVIDER" for b in caps["blocked_adapters"])


async def test_reject_run_and_cancel_transitions(client):
    await register_user(client, chosen_name="Lifecycle Owner")
    project = (await client.post(
        "/api/v1/projects", headers=H(client),
        json={"title": "Lifecycle", "objective": "State machine."},
    )).json()
    pid = project["id"]

    def _run_body(summary):
        return {"role": "verifier", "request_summary": summary, "adapter_key": "EVIDENCE_PACKAGE"}

    r = (await client.post(f"/api/v1/projects/{pid}/runs", headers=H(client), json=_run_body("reject me"))).json()
    rejected = await client.post(f"/api/v1/projects/runs/{r['id']}/reject", headers=H(client))
    assert rejected.status_code == 200 and rejected.json()["status"] == "REJECTED"
    # A rejected run cannot be queued or approved.
    assert (await client.post(f"/api/v1/projects/runs/{r['id']}/approve", headers=H(client))).status_code == 409

    r2 = (await client.post(f"/api/v1/projects/{pid}/runs", headers=H(client), json=_run_body("cancel me"))).json()
    await client.post(f"/api/v1/projects/runs/{r2['id']}/approve", headers=H(client))
    cancelled = await client.post(f"/api/v1/projects/runs/{r2['id']}/cancel", headers=H(client))
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert cancelled.json()["cancelled_at"] is not None


# --- Service-level execution laws -------------------------------------------

async def _approved_queued_run(client) -> tuple[str, str]:
    """Return (owner_id, run_id) for an approved run set to QUEUED without executing."""
    owner, _, _ = await register_user(client, chosen_name="Svc Owner")
    owner_id = owner.json()["id"]
    project_id, task_id, _ = await _project_with_source(client)
    proposed = (await client.post(
        f"/api/v1/projects/{project_id}/runs", headers=H(client),
        json={"role": "verifier", "request_summary": "svc run", "adapter_key": "EVIDENCE_PACKAGE"},
    )).json()
    await client.post(f"/api/v1/projects/runs/{proposed['id']}/approve", headers=H(client))
    db = await _scoped_db(owner_id)
    try:
        import uuid
        run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == uuid.UUID(proposed["id"])))).scalar_one()
        run.status = "QUEUED"
        run.queued_at = now_utc()
        await db.commit()
    finally:
        await db.close()
    return owner_id, proposed["id"]


async def _count_artifacts(owner_id: str, run_id: str) -> int:
    import uuid
    db = await _scoped_db(owner_id)
    try:
        return len((await db.execute(select(AMProjectArtifact).where(
            AMProjectArtifact.run_id == uuid.UUID(run_id),
        ))).scalars().all())
    finally:
        await db.close()


async def test_duplicate_delivery_is_idempotent_single_output(client):
    import uuid
    owner_id, run_id = await _approved_queued_run(client)
    db = await _scoped_db(owner_id)
    try:
        first = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w1")
        second = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w2")
    finally:
        await db.close()
    assert first.status == "SUCCEEDED"
    assert second.idempotent_noop is True
    assert await _count_artifacts(owner_id, run_id) == 1


async def test_cancel_requested_run_is_not_executed(client):
    import uuid
    owner_id, run_id = await _approved_queued_run(client)
    db = await _scoped_db(owner_id)
    try:
        run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == uuid.UUID(run_id)))).scalar_one()
        run.status = "CANCEL_REQUESTED"
        await db.commit()
        result = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w")
    finally:
        await db.close()
    assert result.status == "CANCELLED"
    assert await _count_artifacts(owner_id, run_id) == 0


async def test_cancel_during_adapter_discards_output_without_artifact(client, monkeypatch):
    import uuid

    owner_id, run_id = await _approved_queued_run(client)
    stored_key: str | None = None

    async def _cancel_then_return(db, run, storage):
        nonlocal stored_key
        run.status = "CANCEL_REQUESTED"
        await db.commit()
        stored = await storage.put(bytes_stream(b"discard me"), max_bytes=1024)
        stored_key = stored.object_key
        return AdapterOutput(
            artifact_kind="EVIDENCE_PACKAGE",
            artifact_title="cancelled output",
            object_key=stored.object_key,
            checksum_sha256=stored.checksum_sha256,
            byte_size=stored.byte_size,
            filename="cancelled.bin",
            media_type="application/octet-stream",
            result_summary="must not persist",
            manifest_digest=stored.checksum_sha256,
            evidence_summary="must not persist",
        )

    monkeypatch.setitem(
        project_execution._ADAPTER_FUNCS, "EVIDENCE_PACKAGE", _cancel_then_return
    )
    db = await _scoped_db(owner_id)
    try:
        result = await execute_run(
            db,
            run_id=uuid.UUID(run_id),
            owner_user_id=uuid.UUID(owner_id),
            worker_id="w",
        )
    finally:
        await db.close()

    assert result.status == "CANCELLED"
    assert await _count_artifacts(owner_id, run_id) == 0
    assert stored_key is not None
    assert get_object_storage().exists(stored_key) is False


async def test_adapter_failure_persists_honest_state_without_artifact(client, monkeypatch):
    import uuid
    owner_id, run_id = await _approved_queued_run(client)

    async def _boom(db, run, storage):
        raise RuntimeError("worker crashed")

    monkeypatch.setitem(project_execution._ADAPTER_FUNCS, "EVIDENCE_PACKAGE", _boom)
    db = await _scoped_db(owner_id)
    try:
        result = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w")
        await set_user_context(db, uuid.UUID(owner_id))  # re-arm after execute_run's commit
        run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == uuid.UUID(run_id)))).scalar_one()
    finally:
        await db.close()
    assert result.status == "FAILED" and result.failure_code == "ADAPTER_ERROR"
    assert run.failure_code == "ADAPTER_ERROR" and run.failed_at is not None
    assert await _count_artifacts(owner_id, run_id) == 0


async def test_timeout_produces_durable_failure(client, monkeypatch):
    import asyncio
    import uuid
    owner_id, run_id = await _approved_queued_run(client)

    async def _slow(db, run, storage):
        await asyncio.sleep(5)
        raise AssertionError("should have timed out")

    monkeypatch.setitem(project_execution._ADAPTER_FUNCS, "EVIDENCE_PACKAGE", _slow)
    db = await _scoped_db(owner_id)
    try:
        result = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w", timeout_seconds=1)
    finally:
        await db.close()
    assert result.status == "FAILED" and result.failure_code == "TIMEOUT"


async def test_retry_preserves_lineage_and_increments_attempt(client, monkeypatch):
    import uuid
    owner_id, run_id = await _approved_queued_run(client)

    async def _flaky(db, run, storage):
        if run.attempt < 2:
            raise AdapterFailure("FLAKY", "transient failure")
        stored = await storage.put(bytes_stream(b"recovered"), max_bytes=1024)
        return AdapterOutput(
            artifact_kind="EVIDENCE_PACKAGE", artifact_title="retry",
            object_key=stored.object_key, checksum_sha256=stored.checksum_sha256,
            byte_size=stored.byte_size, filename="retry.bin", media_type="application/octet-stream",
            result_summary="recovered on retry", manifest_digest=stored.checksum_sha256,
            evidence_summary="retry evidence",
        )

    monkeypatch.setitem(project_execution._ADAPTER_FUNCS, "EVIDENCE_PACKAGE", _flaky)
    db = await _scoped_db(owner_id)
    try:
        first = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w1")
        # Retry: re-queue the FAILED run (lineage preserved; attempt keeps climbing).
        await set_user_context(db, uuid.UUID(owner_id))  # re-arm after execute_run's commit
        run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == uuid.UUID(run_id)))).scalar_one()
        assert run.attempt == 1 and run.status == "FAILED"
        run.status = "QUEUED"
        await db.commit()
        second = await execute_run(db, run_id=uuid.UUID(run_id), owner_user_id=uuid.UUID(owner_id), worker_id="w2")
        await set_user_context(db, uuid.UUID(owner_id))
        run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == uuid.UUID(run_id)))).scalar_one()
    finally:
        await db.close()
    assert first.status == "FAILED" and first.failure_code == "FLAKY"
    assert second.status == "SUCCEEDED"
    assert run.attempt == 2
    assert await _count_artifacts(owner_id, run_id) == 1


async def test_checksum_mismatch_fails_run_without_fabricating_package(client):
    """If a stored input's bytes are tampered, the run FAILS honestly rather than
    packaging over corrupt inputs."""
    import uuid
    owner, _, _ = await register_user(client, chosen_name="Integrity Owner")
    owner_id = owner.json()["id"]
    project_id, task_id, file_id = await _project_with_source(client)
    proposed = (await client.post(
        f"/api/v1/projects/{project_id}/runs", headers=H(client),
        json={"role": "verifier", "request_summary": "package", "adapter_key": "EVIDENCE_PACKAGE"},
    )).json()
    await client.post(f"/api/v1/projects/runs/{proposed['id']}/approve", headers=H(client))

    # Tamper with the stored bytes on disk (checksum will no longer match).
    storage = get_object_storage()
    db = await _scoped_db(owner_id)
    try:
        from app.models import AMProjectFile
        row = (await db.execute(select(AMProjectFile).where(AMProjectFile.id == uuid.UUID(file_id)))).scalar_one()
        object_key = row.object_key
        run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == uuid.UUID(proposed["id"])))).scalar_one()
        run.status = "QUEUED"
        await db.commit()
        path = storage._path_for(object_key)
        path.write_bytes(b"tampered")
        result = await execute_run(db, run_id=uuid.UUID(proposed["id"]), owner_user_id=uuid.UUID(owner_id), worker_id="w")
    finally:
        await db.close()
    assert result.status == "FAILED" and result.failure_code == "CHECKSUM_MISMATCH"
    assert await _count_artifacts(owner_id, proposed["id"]) == 0


async def test_run_and_agent_metadata_owner_isolated(client, app_engine):
    owner_a, _, _ = await register_user(client, chosen_name="Run Owner A")
    project_id, task_id, _ = await _project_with_source(client)
    await client.post(
        f"/api/v1/projects/{project_id}/agents", headers=H(client),
        json={"name": "A-agent", "adapter_key": "EVIDENCE_PACKAGE"},
    )
    run = (await client.post(
        f"/api/v1/projects/{project_id}/runs", headers=H(client),
        json={"role": "verifier", "request_summary": "private", "adapter_key": "EVIDENCE_PACKAGE"},
    )).json()

    client.cookies.clear()
    owner_b, _, _ = await register_user(client, chosen_name="Run Owner B")
    assert (await client.get(f"/api/v1/projects/runs/{run['id']}")).status_code == 404
    assert (await client.get(f"/api/v1/projects/{project_id}/agents")).status_code == 404

    async with app_engine.connect() as conn:
        await conn.execute(
            text("SELECT set_config('app.current_user_id', :uid, true)"),
            {"uid": owner_b.json()["id"]},
        )
        agent_count = (await conn.execute(text("SELECT count(*) FROM am_project_agents"))).scalar_one()
        forced = dict((await conn.execute(text(
            "SELECT relname, relforcerowsecurity FROM pg_class WHERE relname = ANY(:t)"
        ), {"t": ["am_project_agents", "am_project_files"]})).all())
        await conn.rollback()
    assert agent_count == 0
    assert all(forced.values())
    assert owner_a.json()["id"] != owner_b.json()["id"]
