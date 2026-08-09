"""Approval-gated, capability-bounded execution for AM Project runs (G14).

Safe execution law
------------------
NUR never grants an "agent" uncontrolled authority. Capabilities are DENY by
default: only the members of ``SAFE_CAPABILITIES`` can ever be requested, and
dangerous authorities (shell, arbitrary filesystem/network, publish, deploy,
spend, messaging, credential/secret access, security changes, destructive ops)
are not in the catalog at all — requesting one is rejected before persistence.

Every executable run carries owner, project, optional task, adapter, requested
and approved capability sets, an owner approval record, input references, a
budget ceiling, a timeout, an idempotency key, queue/started/finished stamps,
worker identity, attempt count, failure code, and output artifact/evidence
references. State transitions are guarded so a duplicate queue delivery produces
exactly one durable output, and a cancelled/rejected run never executes.

The mandatory adapter (EVIDENCE_PACKAGE) is fully deterministic and needs no
external provider. Provider-backed "AI agent" execution is intentionally absent
and remains BLOCKED_BY_EXTERNAL_PROVIDER until a real provider is proven.
"""
from __future__ import annotations

import asyncio
import datetime as dt
import io
import json
import uuid
import zipfile
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import set_user_context
from app.models import (
    AMProject,
    AMProjectArtifact,
    AMProjectEvidence,
    AMProjectFile,
    AMProjectReview,
    AMProjectRun,
    AMProjectTask,
    AuditEvent,
    CognitiveEvent,
)
from app.models._mixins import now_utc
from app.services.object_storage import (
    LocalObjectStorage,
    bytes_stream,
    get_object_storage,
)

# --- Capability catalog (deny by default) ----------------------------------

CAP_PROJECT_READ = "project.read"
CAP_TASK_READ = "task.read"
CAP_EVIDENCE_READ = "evidence.read"
CAP_FILE_READ = "file.read"
CAP_FILE_WRITE = "file.write"
CAP_ARTIFACT_WRITE = "artifact.write"
CAP_EVIDENCE_WRITE = "evidence.write"

SAFE_CAPABILITIES: frozenset[str] = frozenset({
    CAP_PROJECT_READ, CAP_TASK_READ, CAP_EVIDENCE_READ, CAP_FILE_READ,
    CAP_FILE_WRITE, CAP_ARTIFACT_WRITE, CAP_EVIDENCE_WRITE,
})

# Explicitly denied authorities — never grantable, listed so the boundary is
# auditable and testable rather than merely implied by omission.
DENIED_CAPABILITIES: frozenset[str] = frozenset({
    "shell.exec", "process.spawn", "filesystem.arbitrary", "network.arbitrary",
    "publish", "deploy", "spend", "payments", "message.external",
    "credentials.read", "secrets.read", "repository.write", "destructive",
})


class CapabilityDenied(Exception):
    """A requested capability is outside the safe catalog."""

    def __init__(self, capability: str) -> None:
        super().__init__(f"Capability '{capability}' is denied by default and cannot be granted.")
        self.capability = capability


class AdapterUnknown(Exception):
    def __init__(self, adapter_key: str) -> None:
        super().__init__(f"Unknown execution adapter '{adapter_key}'.")
        self.adapter_key = adapter_key


class AdapterFailure(Exception):
    """Deterministic, honest failure raised by an adapter (mapped to failure_code)."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class AdapterOutput:
    artifact_kind: str
    artifact_title: str
    object_key: str
    checksum_sha256: str
    byte_size: int
    filename: str
    media_type: str
    result_summary: str
    manifest_digest: str
    evidence_summary: str
    notes: dict = field(default_factory=dict)


@dataclass(frozen=True)
class AdapterSpec:
    key: str
    label: str
    required_capabilities: frozenset[str]
    description: str


ADAPTERS: dict[str, AdapterSpec] = {
    "EVIDENCE_PACKAGE": AdapterSpec(
        key="EVIDENCE_PACKAGE",
        label="Evidence package",
        required_capabilities=frozenset({
            CAP_PROJECT_READ, CAP_TASK_READ, CAP_EVIDENCE_READ, CAP_FILE_READ,
            CAP_FILE_WRITE, CAP_ARTIFACT_WRITE, CAP_EVIDENCE_WRITE,
        }),
        description="Package owner project metadata, tasks, reviews, evidence and verified "
                    "file checksums into a deterministic, downloadable archive.",
    ),
    "DETERMINISTIC_TEXT_TRANSFORM": AdapterSpec(
        key="DETERMINISTIC_TEXT_TRANSFORM",
        label="Deterministic text normalizer",
        required_capabilities=frozenset({
            CAP_PROJECT_READ, CAP_FILE_READ, CAP_FILE_WRITE, CAP_ARTIFACT_WRITE,
        }),
        description="Normalize a project-owned UTF-8 text file (CRLF→LF, trailing "
                    "whitespace trimmed, single final newline) into a sanitized deliverable.",
    ),
}

# Provider-backed execution advertised by the product but intentionally inert.
BLOCKED_ADAPTERS: dict[str, str] = {
    "AI_AGENT": "BLOCKED_BY_EXTERNAL_PROVIDER",
}


def resolve_requested_capabilities(adapter_key: str, extra: list[str] | None) -> list[str]:
    """The adapter's required safe set, plus any extra safe capabilities the owner
    explicitly requests. Anything outside the catalog is rejected."""
    spec = ADAPTERS.get(adapter_key)
    if spec is None:
        raise AdapterUnknown(adapter_key)
    requested = set(spec.required_capabilities)
    for cap in extra or []:
        if cap not in SAFE_CAPABILITIES:
            raise CapabilityDenied(cap)
        requested.add(cap)
    return sorted(requested)


# --- Deterministic archive helpers -----------------------------------------

_ZIP_EPOCH = (1980, 1, 1, 0, 0, 0)


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")


def _zip_member(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(filename=name, date_time=_ZIP_EPOCH)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o600 << 16
    archive.writestr(info, data)


def _iso(value: dt.datetime | None) -> str | None:
    return value.isoformat() if value else None


# --- Adapters ---------------------------------------------------------------

async def _load_project_scope(db: AsyncSession, run: AMProjectRun):
    project = (await db.execute(select(AMProject).where(
        AMProject.id == run.project_id, AMProject.owner_user_id == run.owner_user_id,
    ))).scalar_one_or_none()
    if project is None:
        raise AdapterFailure("PROJECT_MISSING", "Project not found for run scope.")
    tasks = (await db.execute(select(AMProjectTask).where(
        AMProjectTask.owner_user_id == run.owner_user_id,
        AMProjectTask.project_id == run.project_id,
    ).order_by(AMProjectTask.created_at))).scalars().all()
    evidence = (await db.execute(select(AMProjectEvidence).where(
        AMProjectEvidence.owner_user_id == run.owner_user_id,
        AMProjectEvidence.project_id == run.project_id,
    ).order_by(AMProjectEvidence.created_at))).scalars().all()
    reviews = (await db.execute(select(AMProjectReview).where(
        AMProjectReview.owner_user_id == run.owner_user_id,
        AMProjectReview.project_id == run.project_id,
    ).order_by(AMProjectReview.created_at))).scalars().all()
    files = (await db.execute(select(AMProjectFile).where(
        AMProjectFile.owner_user_id == run.owner_user_id,
        AMProjectFile.project_id == run.project_id,
        AMProjectFile.storage_state != "DELETED",
    ).order_by(AMProjectFile.created_at))).scalars().all()
    return project, tasks, evidence, reviews, files


async def adapter_evidence_package(
    db: AsyncSession, run: AMProjectRun, storage: LocalObjectStorage
) -> AdapterOutput:
    project, tasks, evidence, reviews, files = await _load_project_scope(db, run)

    file_entries: list[dict] = []
    verified = 0
    for row in files:
        state = row.storage_state
        checksum_ok: bool | None
        if state == "STORED":
            checksum_ok = storage.verify(row.object_key, row.checksum_sha256)
            if checksum_ok:
                verified += 1
            else:
                # Never fabricate a clean package over corrupt inputs, and never
                # silently omit the failure — fail the run with the honest code.
                raise AdapterFailure(
                    "CHECKSUM_MISMATCH",
                    f"Stored file {row.id} failed checksum verification and cannot be packaged.",
                )
        else:
            checksum_ok = None  # quarantined bytes are recorded, never verified or served
        file_entries.append({
            "id": str(row.id),
            "filename": row.original_filename,
            "media_type": row.media_type,
            "byte_size": row.byte_size,
            "checksum_sha256": row.checksum_sha256,
            "storage_state": state,
            "scan_state": row.scan_state,
            "checksum_verified": checksum_ok,
            "included_bytes": state == "STORED",
            "created_at": _iso(row.created_at),
        })

    manifest_core = {
        "project": {
            "id": str(project.id),
            "title": project.title,
            "objective": project.objective,
            "status": project.status,
            "system_slug": project.system_slug,
            "budget_cents": project.budget_cents,
        },
        "tasks": [
            {"id": str(t.id), "title": t.title, "status": t.status,
             "acceptance_criteria": t.acceptance_criteria,
             "completed_at": _iso(t.completed_at)}
            for t in tasks
        ],
        "reviews": [
            {"id": str(r.id), "decision": r.decision, "note": r.note,
             "reviewer_label": r.reviewer_label, "created_at": _iso(r.created_at)}
            for r in reviews
        ],
        "evidence": [
            {"id": str(e.id), "evidence_kind": e.evidence_kind, "summary": e.summary,
             "verification_status": e.verification_status, "verifier": e.verifier,
             "checksum_sha256": e.checksum_sha256}
            for e in evidence
        ],
        "files": file_entries,
        "counts": {
            "tasks": len(tasks),
            "reviews": len(reviews),
            "evidence": len(evidence),
            "files": len(files),
            "files_checksum_verified": verified,
        },
    }
    manifest_digest = uuid.uuid5(
        uuid.NAMESPACE_URL, "nur:evidence-package:" + _canonical(manifest_core).decode()
    ).hex

    checksums_txt = "\n".join(
        f"{entry['checksum_sha256']}  {entry['filename']}"
        for entry in file_entries if entry["checksum_sha256"]
    ) + ("\n" if file_entries else "")
    reproducibility = {
        "adapter": "EVIDENCE_PACKAGE",
        "adapter_version": 1,
        "manifest_content_digest": manifest_digest,
        "canonicalization": "json(sort_keys,separators=,:); zip(fixed-epoch,deflate)",
        "run_id": str(run.id),
        "project_id": str(project.id),
    }
    envelope = {
        "kind": "nur.evidence_package",
        "version": 1,
        "generated_at": now_utc().isoformat(),
        "manifest_content_digest": manifest_digest,
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        _zip_member(archive, "envelope.json", _canonical(envelope))
        _zip_member(archive, "manifest.json", _canonical(manifest_core))
        _zip_member(archive, "checksums.txt", checksums_txt.encode("utf-8"))
        _zip_member(archive, "reproducibility.json", _canonical(reproducibility))
    archive_bytes = buffer.getvalue()

    stored = await storage.put(bytes_stream(archive_bytes), max_bytes=len(archive_bytes) + 1)
    filename = f"evidence-package-{project.id}.zip"
    return AdapterOutput(
        artifact_kind="EVIDENCE_PACKAGE",
        artifact_title=f"Evidence package · {project.title}"[:500],
        object_key=stored.object_key,
        checksum_sha256=stored.checksum_sha256,
        byte_size=stored.byte_size,
        filename=filename,
        media_type="application/zip",
        result_summary=(
            f"Packaged {len(tasks)} task(s), {len(evidence)} evidence record(s), "
            f"{len(reviews)} review(s) and {verified}/{len(files)} checksum-verified file(s)."
        ),
        manifest_digest=manifest_digest,
        evidence_summary=(
            f"EVIDENCE_PACKAGE adapter verified {verified} file checksum(s) and produced a "
            f"{stored.byte_size}-byte archive (sha256 {stored.checksum_sha256})."
        ),
        notes={"manifest_content_digest": manifest_digest},
    )


async def adapter_text_transform(
    db: AsyncSession, run: AMProjectRun, storage: LocalObjectStorage
) -> AdapterOutput:
    input_refs = run.input_refs or {}
    file_id = input_refs.get("file_id")
    if not file_id:
        raise AdapterFailure("INPUT_MISSING", "DETERMINISTIC_TEXT_TRANSFORM requires input_refs.file_id.")
    row = (await db.execute(select(AMProjectFile).where(
        AMProjectFile.owner_user_id == run.owner_user_id,
        AMProjectFile.project_id == run.project_id,
        AMProjectFile.id == uuid.UUID(str(file_id)),
    ))).scalar_one_or_none()
    if row is None:
        raise AdapterFailure("INPUT_MISSING", "Input file not found in project scope.")
    if row.storage_state != "STORED":
        raise AdapterFailure("INPUT_NOT_AVAILABLE", f"Input file is {row.storage_state}, not STORED.")
    if not storage.verify(row.object_key, row.checksum_sha256):
        raise AdapterFailure("CHECKSUM_MISMATCH", "Input file failed checksum verification.")
    raw = storage.read_bytes(row.object_key)
    try:
        text_value = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AdapterFailure("NOT_TEXT", "Input file is not valid UTF-8 text.") from exc
    normalized = "\n".join(line.rstrip() for line in text_value.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    normalized = normalized.rstrip("\n") + "\n"
    data = normalized.encode("utf-8")
    stored = await storage.put(bytes_stream(data), max_bytes=len(data) + 1)
    filename = f"normalized-{row.original_filename}"
    return AdapterOutput(
        artifact_kind="TEXT_DELIVERABLE",
        artifact_title=f"Normalized · {row.original_filename}"[:500],
        object_key=stored.object_key,
        checksum_sha256=stored.checksum_sha256,
        byte_size=stored.byte_size,
        filename=filename,
        media_type="text/plain; charset=utf-8",
        result_summary=f"Normalized {row.byte_size}-byte input into {stored.byte_size}-byte deterministic deliverable.",
        manifest_digest=stored.checksum_sha256,
        evidence_summary=f"DETERMINISTIC_TEXT_TRANSFORM produced sha256 {stored.checksum_sha256} from file {row.id}.",
    )


_ADAPTER_FUNCS = {
    "EVIDENCE_PACKAGE": adapter_evidence_package,
    "DETERMINISTIC_TEXT_TRANSFORM": adapter_text_transform,
}


# --- Timeline / audit -------------------------------------------------------

def _record_event(db: AsyncSession, run: AMProjectRun, orbit_id: uuid.UUID, kind: str, text_value: str) -> None:
    payload = {
        "timeline_kind": kind,
        "object_type": "am_project_run",
        "object_id": str(run.id),
        "project_id": str(run.project_id),
        "provenance_label": "RUN_EXECUTION",
        "adapter_key": run.adapter_key,
    }
    db.add(CognitiveEvent(
        owner_user_id=run.owner_user_id,
        orbit_id=orbit_id,
        event_kind="SYSTEM_EVENT",
        content_text=text_value,
        source_ref=f"am_project_run:{run.id}",
        structured_payload=payload,
    ))
    db.add(AuditEvent(
        actor_user_id=run.owner_user_id,
        event_type=kind,
        object_type="am_project_run",
        object_id=run.id,
        event_metadata=payload,
    ))


# --- Execution orchestration ------------------------------------------------

@dataclass
class ExecutionResult:
    run_id: uuid.UUID
    status: str
    failure_code: str | None = None
    artifact_id: uuid.UUID | None = None
    idempotent_noop: bool = False


async def _invoke_adapter(
    adapter_key: str, run_id: uuid.UUID, owner_uuid: uuid.UUID, storage: LocalObjectStorage
) -> AdapterOutput:
    """Run a read-only adapter on a dedicated, owner-scoped session. The adapter
    only reads owner data and writes bytes to the object store; the orchestrator
    persists the artifact/evidence/file rows on its own session afterwards. Using a
    separate session keeps a timeout cancellation from corrupting the orchestrator."""
    from app.db.session import get_sessionmaker
    adapter = _ADAPTER_FUNCS[adapter_key]
    async with get_sessionmaker()() as adb:
        await set_user_context(adb, owner_uuid)
        run = (await adb.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))).scalar_one()
        return await adapter(adb, run, storage)


async def execute_run(
    db: AsyncSession,
    *,
    run_id: uuid.UUID,
    owner_user_id: uuid.UUID | None = None,
    worker_id: str,
    storage: LocalObjectStorage | None = None,
    timeout_seconds: int | None = None,
) -> ExecutionResult:
    """Execute one approved+queued run. Safe to call more than once for the same
    run: only a QUEUED run is claimed, so duplicate deliveries are idempotent.

    Each commit ends the transaction and drops the transaction-local RLS GUC, so
    the owner context is re-armed after every commit before the next scoped query.
    """
    storage = storage or get_object_storage()
    if owner_user_id is not None:
        await set_user_context(db, owner_user_id)

    run = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == run_id))).scalar_one_or_none()
    if run is None:
        return ExecutionResult(run_id=run_id, status="NOT_FOUND", idempotent_noop=True)
    owner_uuid = run.owner_user_id

    project = (await db.execute(select(AMProject).where(AMProject.id == run.project_id))).scalar_one_or_none()
    orbit_id = project.orbit_id if project else owner_uuid

    if run.status == "CANCEL_REQUESTED":
        run.cancelled_at = now_utc()
        run.status = "CANCELLED"
        run.updated_at = now_utc()
        _record_event(db, run, orbit_id, "PROJECT_RUN_CANCELLED", "Run cancelled before execution.")
        await db.commit()
        return ExecutionResult(run_id=run_id, status="CANCELLED")

    # Atomic claim: only a QUEUED run becomes RUNNING; a duplicate delivery finds
    # no QUEUED row and is a no-op against the already-claimed/terminal run.
    now = now_utc()
    claimed = (await db.execute(
        update(AMProjectRun)
        .where(AMProjectRun.id == run_id, AMProjectRun.status == "QUEUED")
        .values(status="RUNNING", started_at=now, updated_at=now,
                worker_id=worker_id, attempt=AMProjectRun.attempt + 1)
        .returning(AMProjectRun.id)
    )).scalar_one_or_none()
    await db.commit()
    await set_user_context(db, owner_uuid)
    if claimed is None:
        return ExecutionResult(run_id=run_id, status=run.status, idempotent_noop=True)

    await db.refresh(run)
    adapter = _ADAPTER_FUNCS.get(run.adapter_key)
    if adapter is None:
        return await _fail(db, run, orbit_id, "ADAPTER_UNKNOWN", f"No adapter '{run.adapter_key}'.")

    # Capability gate: the adapter's required set must be within the approved set.
    approved = set(run.approved_capabilities or [])
    spec = ADAPTERS[run.adapter_key]
    missing = spec.required_capabilities - approved
    if missing:
        return await _fail(db, run, orbit_id, "INSUFFICIENT_CAPABILITY",
                           f"Approved capabilities missing {sorted(missing)}.")

    timeout = float(timeout_seconds or run.timeout_seconds or get_settings_timeout())
    # The read-only adapter runs on its OWN session so a timeout can cancel it
    # without corrupting the orchestration session that records the outcome
    # (SQLAlchemy async sessions are not cancellation-safe).
    try:
        output = await asyncio.wait_for(
            _invoke_adapter(run.adapter_key, run_id, owner_uuid, storage), timeout=timeout
        )
    except AdapterFailure as exc:
        return await _fail(db, run, orbit_id, exc.code, str(exc))
    except (TimeoutError, asyncio.TimeoutError):
        return await _fail(db, run, orbit_id, "TIMEOUT", f"Run exceeded {timeout}s timeout.")
    except Exception as exc:  # noqa: BLE001 - honest catch-all → durable failure
        return await _fail(db, run, orbit_id, "ADAPTER_ERROR", repr(exc))

    # Budget: deterministic adapters cost nothing; enforce the ceiling regardless.
    cost_cents = 0
    if run.budget_cents is not None and cost_cents > run.budget_cents:
        return await _fail(db, run, orbit_id, "BUDGET_EXCEEDED", "Run cost exceeded its budget ceiling.")

    # Cancellation is cooperative across the adapter boundary. A running
    # adapter uses its own session, so refresh after it returns and discard its
    # uncommitted object if the owner (or account deletion) requested a stop.
    await db.refresh(run)
    if run.status == "CANCEL_REQUESTED":
        storage.delete(output.object_key)
        run.status = "CANCELLED"
        run.cancelled_at = now_utc()
        run.updated_at = run.cancelled_at
        _record_event(
            db,
            run,
            orbit_id,
            "PROJECT_RUN_CANCELLED",
            "Run cancelled after the adapter returned; no artifact was persisted.",
        )
        await db.commit()
        return ExecutionResult(run_id=run_id, status="CANCELLED")

    artifact = AMProjectArtifact(
        owner_user_id=run.owner_user_id,
        project_id=run.project_id,
        task_id=run.task_id,
        run_id=run.id,
        artifact_kind=output.artifact_kind,
        title=output.artifact_title,
        locator=f"object:{output.object_key}",
        checksum_sha256=output.checksum_sha256,
        provenance_label="RUN_GENERATED",
        artifact_metadata={
            "byte_size": output.byte_size,
            "media_type": output.media_type,
            "manifest_digest": output.manifest_digest,
            **output.notes,
        },
    )
    db.add(artifact)
    await db.flush()

    generated_file = AMProjectFile(
        owner_user_id=run.owner_user_id,
        project_id=run.project_id,
        task_id=run.task_id,
        run_id=run.id,
        object_key=output.object_key,
        original_filename=output.filename,
        safe_filename=output.filename,
        media_type=output.media_type,
        byte_size=output.byte_size,
        checksum_sha256=output.checksum_sha256,
        storage_backend="local",
        storage_state="STORED",
        scan_state="SCAN_NOT_CONNECTED",
        provenance="RUN_OUTPUT",
        artifact_id=artifact.id,
    )
    db.add(generated_file)

    db.add(AMProjectEvidence(
        owner_user_id=run.owner_user_id,
        project_id=run.project_id,
        task_id=run.task_id,
        run_id=run.id,
        evidence_kind="RUN_OUTPUT",
        summary=output.evidence_summary,
        locator=f"object:{output.object_key}",
        checksum_sha256=output.checksum_sha256,
        verification_status="PASSED",
        verifier=f"adapter:{run.adapter_key}@1",
    ))

    finished = now_utc()
    run.status = "SUCCEEDED"
    run.completed_at = finished
    run.updated_at = finished
    run.output_artifact_id = artifact.id
    run.result_summary = output.result_summary
    run.cost_cents = cost_cents
    _record_event(db, run, orbit_id, "PROJECT_RUN_SUCCEEDED", output.result_summary)
    await db.commit()
    return ExecutionResult(run_id=run_id, status="SUCCEEDED", artifact_id=artifact.id)


async def _fail(db: AsyncSession, run: AMProjectRun, orbit_id: uuid.UUID, code: str, message: str) -> ExecutionResult:
    # Capture plain values before rollback: rollback expires the ORM object, and a
    # later attribute access would trigger a lazy load outside the greenlet.
    owner_uuid = run.owner_user_id
    run_pk = run.id
    await db.rollback()
    await set_user_context(db, owner_uuid)  # rollback also drops the transaction-local GUC
    fresh = (await db.execute(select(AMProjectRun).where(AMProjectRun.id == run_pk))).scalar_one_or_none()
    if fresh is None:
        return ExecutionResult(run_id=run_pk, status="NOT_FOUND", failure_code=code)
    finished = now_utc()
    fresh.status = "FAILED"
    fresh.failed_at = finished
    fresh.updated_at = finished
    fresh.failure_code = code
    fresh.result_summary = message[:2000]
    _record_event(db, fresh, orbit_id, "PROJECT_RUN_FAILED", f"{code}: {message}"[:2000])
    await db.commit()
    return ExecutionResult(run_id=run.id, status="FAILED", failure_code=code)


def get_settings_timeout() -> int:
    from app.core.config import get_settings
    return get_settings().project_run_timeout_seconds


async def recover_stale_runs(
    db: AsyncSession,
    *,
    stale_after_seconds: int | None = None,
    max_attempts: int | None = None,
    now: dt.datetime | None = None,
) -> dict[str, int]:
    """Reclaim runs stuck in RUNNING because their worker died mid-execution.

    A run is stale once it has been RUNNING longer than ``stale_after_seconds``.
    Stale runs still within their attempt budget are requeued (QUEUED, worker
    cleared) so a healthy worker picks them up; runs that have exhausted
    ``max_attempts`` are dead-lettered (FAILED / STALE_DEADLETTER) so they cannot
    retry forever. Every transition is written to the run's audit + timeline.

    Operates within the session's RLS scope: with forced row-level security the
    sweep sees only the current owner's runs, so it runs per-owner (via the ops
    path or a per-owner maintenance context), never as a privileged cross-tenant
    job. Returns ``{scanned, requeued, dead_lettered}``.
    """
    from app.core.config import get_settings

    s = get_settings()
    stale_after = s.run_stale_after_seconds if stale_after_seconds is None else stale_after_seconds
    ceiling = s.run_max_attempts if max_attempts is None else max_attempts
    now = now or now_utc()
    cutoff = now - dt.timedelta(seconds=stale_after)

    rows = (await db.execute(
        select(AMProjectRun).where(
            AMProjectRun.status == "RUNNING",
            AMProjectRun.started_at.is_not(None),
            AMProjectRun.started_at <= cutoff,
        )
    )).scalars().all()

    requeued = 0
    dead_lettered = 0
    for run in rows:
        orbit_id = (await db.execute(
            select(AMProject.orbit_id).where(AMProject.id == run.project_id)
        )).scalar_one()
        if (run.attempt or 0) >= ceiling:
            summary = (
                f"Dead-lettered after {run.attempt} attempt(s): worker "
                f"{run.worker_id or 'unknown'} did not finish within {stale_after}s."
            )[:2000]
            run.status = "FAILED"
            run.failure_code = "STALE_DEADLETTER"
            run.failed_at = now
            run.completed_at = now
            run.result_summary = summary
            run.updated_at = now
            _record_event(db, run, orbit_id, "PROJECT_RUN_DEAD_LETTERED", summary)
            dead_lettered += 1
        else:
            run.status = "QUEUED"
            run.worker_id = None
            run.started_at = None
            run.queued_at = now
            run.updated_at = now
            _record_event(
                db, run, orbit_id, "PROJECT_RUN_REQUEUED",
                f"Requeued stale run (attempt {run.attempt}); prior worker did not "
                f"finish within {stale_after}s.",
            )
            requeued += 1

    if rows:
        await db.commit()
    return {"scanned": len(rows), "requeued": requeued, "dead_lettered": dead_lettered}
