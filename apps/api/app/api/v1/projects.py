"""Owner-scoped AM Projects with explicit approval, evidence and execution gates.

Project/task/evidence/review records are owner-ledger truth. Runs are executed
only through approved, capability-bounded, deterministic adapters (see
``app.services.project_execution``); files are real bytes in an owner-scoped,
local-first object store (``app.services.object_storage``). Nothing here spends,
publishes, deploys, messages, reads secrets, or grants an agent authority beyond
the deny-by-default capability catalog.
"""

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from app.api.deps import Identity, Scoped, require_csrf
from app.core.config import get_settings
from app.db.rls import set_user_context
from app.models import (
    AMProject,
    AMProjectAgent,
    AMProjectArtifact,
    AMProjectEvidence,
    AMProjectFile,
    AMProjectReview,
    AMProjectRun,
    AMProjectTask,
    AuditEvent,
    CognitiveEvent,
    Orbit,
)
from app.models._mixins import now_utc
from app.services import rate_limit
from app.services.glow_service import AwardResult, award_glow
from app.services.object_storage import (
    UploadTooLarge,
    classify_upload,
    get_object_storage,
    sanitize_filename,
)
from app.services.project_execution import (
    ADAPTERS,
    BLOCKED_ADAPTERS,
    DENIED_CAPABILITIES,
    SAFE_CAPABILITIES,
    AdapterUnknown,
    CapabilityDenied,
    execute_run,
    resolve_requested_capabilities,
)


router = APIRouter(prefix="/projects", tags=["am-projects"])

PROJECT_STATUSES = {"ACTIVE", "PAUSED", "COMPLETED", "ARCHIVED"}
TASK_STATUSES = {"BACKLOG", "READY", "IN_PROGRESS", "BLOCKED", "REVIEW", "DONE", "CANCELLED"}
RUN_STATUSES = {"PROPOSED", "APPROVED", "QUEUED", "RUNNING", "SUCCEEDED",
                "FAILED", "CANCELLED", "CANCEL_REQUESTED", "REJECTED"}
DENIED_TOOL_ACTIONS = ("spend", "publish", "deploy", "message", "modify_security", "read_secrets")


class ProjectIn(BaseModel):
    title: str = Field(min_length=1, max_length=240)
    objective: str = Field(min_length=1, max_length=12_000)
    orbit_id: uuid.UUID | None = None
    system_slug: str | None = Field(default=None, max_length=48)
    deadline: dt.datetime | None = None
    budget_cents: int | None = Field(default=None, ge=0)


class ProjectPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=240)
    objective: str | None = Field(default=None, min_length=1, max_length=12_000)
    status: str | None = None
    system_slug: str | None = Field(default=None, max_length=48)
    deadline: dt.datetime | None = None
    budget_cents: int | None = Field(default=None, ge=0)


class ProjectOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    orbit_id: uuid.UUID
    title: str
    objective: str
    status: str
    system_slug: str | None
    deadline: dt.datetime | None
    budget_cents: int | None
    permission_policy: dict
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class TaskIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=12_000)
    acceptance_criteria: str | None = Field(default=None, max_length=12_000)
    parent_task_id: uuid.UUID | None = None
    status: str = "BACKLOG"
    priority: int = Field(default=50, ge=0, le=100)
    assigned_role: str | None = Field(default=None, max_length=80)
    due_at: dt.datetime | None = None


class TaskPatch(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    description: str | None = Field(default=None, max_length=12_000)
    acceptance_criteria: str | None = Field(default=None, max_length=12_000)
    status: str | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    assigned_role: str | None = Field(default=None, max_length=80)
    due_at: dt.datetime | None = None


class TaskOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    parent_task_id: uuid.UUID | None
    title: str
    description: str | None
    acceptance_criteria: str | None
    status: str
    priority: int
    assigned_role: str | None
    due_at: dt.datetime | None
    completed_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class RunIn(BaseModel):
    task_id: uuid.UUID | None = None
    role: str = Field(min_length=1, max_length=80)
    request_summary: str = Field(min_length=1, max_length=12_000)
    tool_policy: dict = Field(default_factory=dict)
    budget_cents: int = Field(default=0, ge=0)
    adapter_key: str | None = Field(default=None, max_length=64)
    agent_id: uuid.UUID | None = None
    requested_capabilities: list[str] = Field(default_factory=list)
    input_refs: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)
    timeout_seconds: int | None = Field(default=None, ge=1, le=1800)


class RunOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    role: str
    request_summary: str
    status: str
    tool_policy: dict
    budget_cents: int
    approval_required: bool
    approved_at: dt.datetime | None
    started_at: dt.datetime | None
    completed_at: dt.datetime | None
    result_summary: str | None
    adapter_key: str | None
    agent_id: uuid.UUID | None
    requested_capabilities: list
    approved_capabilities: list
    input_refs: dict
    idempotency_key: str | None
    timeout_seconds: int | None
    cost_cents: int
    attempt: int
    worker_id: str | None
    failure_code: str | None
    output_artifact_id: uuid.UUID | None
    queued_at: dt.datetime | None
    failed_at: dt.datetime | None
    cancelled_at: dt.datetime | None
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class AgentIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    adapter_key: str = Field(min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=4000)
    allowed_capabilities: list[str] = Field(default_factory=list)


class AgentOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    name: str
    adapter_key: str
    description: str | None
    allowed_capabilities: list
    version: int
    is_active: bool
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class FileOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    run_id: uuid.UUID | None
    artifact_id: uuid.UUID | None
    original_filename: str
    safe_filename: str
    media_type: str
    byte_size: int
    checksum_sha256: str
    storage_state: str
    quarantine_reason: str | None
    scan_state: str
    provenance: str
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class ArtifactIn(BaseModel):
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    artifact_kind: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=500)
    locator: str = Field(min_length=1, max_length=4000)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    provenance_label: str = Field(default="OWNER_SUPPLIED", max_length=64)
    artifact_metadata: dict = Field(default_factory=dict)


class ArtifactOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    run_id: uuid.UUID | None
    artifact_kind: str
    title: str
    locator: str
    checksum_sha256: str | None
    provenance_label: str
    review_status: str
    artifact_metadata: dict
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class EvidenceIn(BaseModel):
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    evidence_kind: str = Field(min_length=1, max_length=64)
    summary: str = Field(min_length=1, max_length=12_000)
    locator: str | None = Field(default=None, max_length=4000)
    checksum_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    verification_status: str = "UNVERIFIED"
    verifier: str | None = Field(default=None, max_length=120)


class EvidenceOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    run_id: uuid.UUID | None
    evidence_kind: str
    summary: str
    locator: str | None
    checksum_sha256: str | None
    verification_status: str
    verifier: str | None
    created_at: dt.datetime
    updated_at: dt.datetime
    model_config = {"from_attributes": True}


class ReviewIn(BaseModel):
    task_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    decision: str
    note: str | None = Field(default=None, max_length=12_000)


class ReviewOut(BaseModel):
    id: uuid.UUID
    owner_user_id: uuid.UUID
    project_id: uuid.UUID
    task_id: uuid.UUID | None
    run_id: uuid.UUID | None
    decision: str
    note: str | None
    reviewer_label: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


def _event(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID,
    kind: str,
    text_value: str,
    object_type: str,
    object_id: uuid.UUID,
    project_id: uuid.UUID,
) -> None:
    payload = {
        "timeline_kind": kind,
        "object_type": object_type,
        "object_id": str(object_id),
        "project_id": str(project_id),
        "provenance_label": "OWNER_LEDGER",
    }
    db.add(CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_kind="SYSTEM_EVENT",
        content_text=text_value,
        source_ref=f"{object_type}:{object_id}",
        structured_payload=payload,
    ))
    db.add(AuditEvent(
        actor_user_id=owner_user_id,
        event_type=kind,
        object_type=object_type,
        object_id=object_id,
        event_metadata=payload,
    ))


def _glow(result: AwardResult | None, reason: str | None = None) -> dict:
    if result is None:
        return {"awarded_points": 0, "status": "GATED", "reason": reason}
    return {
        "awarded_points": result.transaction.final_points,
        "status": "AWARDED",
        "transaction_id": result.transaction.id,
        "balance": result.balance.balance,
        "idempotent_replay": result.idempotent_replay,
    }


async def _award_or_gate(db: Scoped, **kwargs) -> tuple[AwardResult | None, str | None]:
    try:
        return await award_glow(db, **kwargs), None
    except HTTPException as exc:
        if exc.status_code == 409:
            return None, str(exc.detail)
        raise


async def _owned_project(db: Scoped, owner_user_id: uuid.UUID, project_id: uuid.UUID) -> AMProject:
    row = (await db.execute(select(AMProject).where(
        AMProject.id == project_id,
        AMProject.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "AM Project not found.")
    return row


async def _owned_task(
    db: Scoped, owner_user_id: uuid.UUID, task_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> AMProjectTask:
    query = select(AMProjectTask).where(
        AMProjectTask.id == task_id,
        AMProjectTask.owner_user_id == owner_user_id,
    )
    if project_id is not None:
        query = query.where(AMProjectTask.project_id == project_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "AM Project task not found.")
    return row


async def _owned_run(
    db: Scoped, owner_user_id: uuid.UUID, run_id: uuid.UUID, project_id: uuid.UUID | None = None
) -> AMProjectRun:
    query = select(AMProjectRun).where(
        AMProjectRun.id == run_id,
        AMProjectRun.owner_user_id == owner_user_id,
    )
    if project_id is not None:
        query = query.where(AMProjectRun.project_id == project_id)
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "AM Project run not found.")
    return row


async def _validate_links(
    db: Scoped,
    owner_user_id: uuid.UUID,
    project_id: uuid.UUID,
    *,
    task_id: uuid.UUID | None,
    run_id: uuid.UUID | None,
) -> None:
    if task_id is not None:
        await _owned_task(db, owner_user_id, task_id, project_id)
    if run_id is not None:
        run = await _owned_run(db, owner_user_id, run_id, project_id)
        if task_id is not None and run.task_id not in {None, task_id}:
            raise HTTPException(409, "Run and task do not belong to the same work branch.")


@router.get("/summary")
async def project_summary(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    projects = (await db.execute(select(AMProject).where(
        AMProject.owner_user_id == owner_user_id,
    ).order_by(AMProject.updated_at.desc()))).scalars().all()
    rows = []
    for project in projects:
        task_counts = dict((await db.execute(select(
            AMProjectTask.status, func.count(AMProjectTask.id),
        ).where(
            AMProjectTask.owner_user_id == owner_user_id,
            AMProjectTask.project_id == project.id,
        ).group_by(AMProjectTask.status))).all())
        evidence_passed = int((await db.execute(select(func.count(AMProjectEvidence.id)).where(
            AMProjectEvidence.owner_user_id == owner_user_id,
            AMProjectEvidence.project_id == project.id,
            AMProjectEvidence.verification_status == "PASSED",
        ))).scalar_one())
        rows.append({
            **ProjectOut.model_validate(project).model_dump(),
            "task_counts": task_counts,
            "verified_evidence": evidence_passed,
        })
    return {
        "provenance_label": "OWNER_PROJECT_LEDGER",
        "counts": {
            "projects": len(projects),
            "active": sum(row.status == "ACTIVE" for row in projects),
            "blocked_tasks": sum(row["task_counts"].get("BLOCKED", 0) for row in rows),
        },
        "projects": rows,
    }


@router.post("", response_model=ProjectOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_project(payload: ProjectIn, db: Scoped, identity: Identity) -> ProjectOut:
    owner_user_id, _ = identity
    if payload.orbit_id:
        orbit = (await db.execute(select(Orbit).where(
            Orbit.id == payload.orbit_id,
            Orbit.owner_user_id == owner_user_id,
        ))).scalar_one_or_none()
        if orbit is None:
            raise HTTPException(404, "Orbit not found.")
    else:
        orbit = Orbit(
            owner_user_id=owner_user_id,
            title=payload.title,
            kind="PROJECT",
            description=payload.objective,
        )
        db.add(orbit)
        await db.flush()
    permission_policy = {
        "external_actions_require_owner_approval": True,
        **{key: False for key in DENIED_TOOL_ACTIONS},
    }
    row = AMProject(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        title=payload.title,
        objective=payload.objective,
        system_slug=payload.system_slug,
        deadline=payload.deadline,
        budget_cents=payload.budget_cents,
        permission_policy=permission_policy,
    )
    db.add(row)
    await db.flush()
    _event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        kind="PROJECT_CREATED",
        text_value=row.title,
        object_type="am_project",
        object_id=row.id,
        project_id=row.id,
    )
    await _award_or_gate(
        db,
        owner_user_id=owner_user_id,
        event_type="project.created",
        source_kind="AM_PROJECT",
        source_id=row.id,
        orbit_id=orbit.id,
        idempotency_key=f"project:{row.id}:created",
    )
    await db.commit()
    return ProjectOut.model_validate(row)


@router.get("", response_model=list[ProjectOut])
async def list_projects(db: Scoped, identity: Identity) -> list[ProjectOut]:
    owner_user_id, _ = identity
    rows = (await db.execute(select(AMProject).where(
        AMProject.owner_user_id == owner_user_id,
    ).order_by(AMProject.updated_at.desc()))).scalars()
    return [ProjectOut.model_validate(row) for row in rows]


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(project_id: uuid.UUID, db: Scoped, identity: Identity) -> ProjectOut:
    owner_user_id, _ = identity
    return ProjectOut.model_validate(await _owned_project(db, owner_user_id, project_id))


@router.patch("/{project_id}", response_model=ProjectOut, dependencies=[Depends(require_csrf)])
async def patch_project(
    project_id: uuid.UUID, payload: ProjectPatch, db: Scoped, identity: Identity
) -> ProjectOut:
    owner_user_id, _ = identity
    row = await _owned_project(db, owner_user_id, project_id)
    updates = payload.model_dump(exclude_unset=True)
    if (status := updates.get("status")) is not None and status not in PROJECT_STATUSES:
        raise HTTPException(422, "Unsupported project status.")
    if status == "COMPLETED":
        task_states = (await db.execute(select(AMProjectTask.status).where(
            AMProjectTask.owner_user_id == owner_user_id,
            AMProjectTask.project_id == project_id,
            AMProjectTask.status != "CANCELLED",
        ))).scalars().all()
        if not task_states or any(value != "DONE" for value in task_states):
            raise HTTPException(409, "Project completion requires at least one task and every active task DONE.")
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_at = now_utc()
    await db.commit()
    return ProjectOut.model_validate(row)


@router.post("/{project_id}/tasks", response_model=TaskOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_task(
    project_id: uuid.UUID, payload: TaskIn, db: Scoped, identity: Identity
) -> TaskOut:
    owner_user_id, _ = identity
    project = await _owned_project(db, owner_user_id, project_id)
    if payload.status not in TASK_STATUSES:
        raise HTTPException(422, "Unsupported task status.")
    if payload.parent_task_id:
        await _owned_task(db, owner_user_id, payload.parent_task_id, project_id)
    row = AMProjectTask(owner_user_id=owner_user_id, project_id=project_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    _event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=project.orbit_id,
        kind="PROJECT_TASK_CREATED",
        text_value=row.title,
        object_type="am_project_task",
        object_id=row.id,
        project_id=project.id,
    )
    await db.commit()
    return TaskOut.model_validate(row)


@router.get("/{project_id}/tasks", response_model=list[TaskOut])
async def list_tasks(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[TaskOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectTask).where(
        AMProjectTask.owner_user_id == owner_user_id,
        AMProjectTask.project_id == project_id,
    ).order_by(AMProjectTask.priority.desc(), AMProjectTask.created_at))).scalars()
    return [TaskOut.model_validate(row) for row in rows]


@router.patch("/tasks/{task_id}", dependencies=[Depends(require_csrf)])
async def patch_task(task_id: uuid.UUID, payload: TaskPatch, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = await _owned_task(db, owner_user_id, task_id)
    project = await _owned_project(db, owner_user_id, row.project_id)
    updates = payload.model_dump(exclude_unset=True)
    target_status = updates.get("status")
    if target_status is not None and target_status not in TASK_STATUSES:
        raise HTTPException(422, "Unsupported task status.")
    glow_result = None
    glow_reason = None
    if target_status == "DONE" and row.status != "DONE":
        acceptance = updates.get("acceptance_criteria", row.acceptance_criteria)
        if not acceptance:
            raise HTTPException(409, "Task completion requires explicit acceptance criteria.")
        passed = (await db.execute(select(func.count(AMProjectEvidence.id)).where(
            AMProjectEvidence.owner_user_id == owner_user_id,
            AMProjectEvidence.project_id == row.project_id,
            AMProjectEvidence.task_id == row.id,
            AMProjectEvidence.verification_status == "PASSED",
        ))).scalar_one()
        if not passed:
            raise HTTPException(409, "Task completion requires at least one PASSED evidence record.")
        row.completed_at = now_utc()
    elif target_status != "DONE":
        row.completed_at = None
    for key, value in updates.items():
        setattr(row, key, value)
    row.updated_at = now_utc()
    if target_status == "DONE":
        _event(
            db,
            owner_user_id=owner_user_id,
            orbit_id=project.orbit_id,
            kind="PROJECT_TASK_COMPLETED",
            text_value=row.title,
            object_type="am_project_task",
            object_id=row.id,
            project_id=project.id,
        )
        glow_result, glow_reason = await _award_or_gate(
            db,
            owner_user_id=owner_user_id,
            event_type="project.task_completed",
            source_kind="AM_PROJECT_TASK",
            source_id=row.id,
            orbit_id=project.orbit_id,
            idempotency_key=f"project-task:{row.id}:completed",
        )
    await db.commit()
    return {"task": TaskOut.model_validate(row), "glow": _glow(glow_result, glow_reason)}


@router.post("/{project_id}/runs", response_model=RunOut, status_code=201, dependencies=[Depends(require_csrf)])
async def propose_run(project_id: uuid.UUID, payload: RunIn, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    project = await _owned_project(db, owner_user_id, project_id)
    await _validate_links(db, owner_user_id, project_id, task_id=payload.task_id, run_id=None)

    # Idempotent proposal: an existing run for the same key is returned unchanged.
    if payload.idempotency_key:
        existing = (await db.execute(select(AMProjectRun).where(
            AMProjectRun.owner_user_id == owner_user_id,
            AMProjectRun.idempotency_key == payload.idempotency_key,
        ))).scalar_one_or_none()
        if existing is not None:
            return RunOut.model_validate(existing)

    requested_policy = {key: bool(value) for key, value in payload.tool_policy.items()}
    policy = {
        "external_actions_require_owner_approval": True,
        **{key: False for key in DENIED_TOOL_ACTIONS},
        **requested_policy,
    }
    if any(policy.get(key) for key in DENIED_TOOL_ACTIONS):
        raise HTTPException(422, "Proposed runs cannot pre-authorize spending, publishing, deployment, messaging, secret access, or security changes.")
    if project.budget_cents is not None and payload.budget_cents > project.budget_cents:
        raise HTTPException(409, "Run budget exceeds the persisted project budget.")

    # Deny-by-default capability resolution. Without an adapter the run is a
    # record-only proposal and cannot request execution capabilities.
    requested_capabilities: list[str] = []
    agent: AMProjectAgent | None = None
    if payload.adapter_key:
        try:
            requested_capabilities = resolve_requested_capabilities(payload.adapter_key, payload.requested_capabilities)
        except AdapterUnknown:
            raise HTTPException(422, f"Unknown execution adapter '{payload.adapter_key}'.")
        except CapabilityDenied as exc:
            raise HTTPException(422, str(exc))
        if payload.agent_id is not None:
            agent = (await db.execute(select(AMProjectAgent).where(
                AMProjectAgent.id == payload.agent_id,
                AMProjectAgent.owner_user_id == owner_user_id,
                AMProjectAgent.project_id == project_id,
            ))).scalar_one_or_none()
            if agent is None:
                raise HTTPException(404, "Agent definition not found.")
            if agent.adapter_key != payload.adapter_key:
                raise HTTPException(409, "Agent adapter does not match the requested adapter.")
            granted = set(agent.allowed_capabilities or [])
            if not set(requested_capabilities) <= granted:
                raise HTTPException(422, "Agent is not granted every requested capability.")
    elif payload.requested_capabilities:
        raise HTTPException(422, "Capabilities require an execution adapter_key.")

    row = AMProjectRun(
        owner_user_id=owner_user_id,
        project_id=project_id,
        task_id=payload.task_id,
        role=payload.role,
        request_summary=payload.request_summary,
        tool_policy=policy,
        budget_cents=payload.budget_cents,
        status="PROPOSED",
        approval_required=True,
        adapter_key=payload.adapter_key,
        agent_id=agent.id if agent else None,
        requested_capabilities=requested_capabilities,
        approved_capabilities=[],
        input_refs=payload.input_refs,
        idempotency_key=payload.idempotency_key,
        timeout_seconds=payload.timeout_seconds,
    )
    db.add(row)
    try:
        await db.flush()
    except IntegrityError:
        await db.rollback()
        replay = (await db.execute(select(AMProjectRun).where(
            AMProjectRun.owner_user_id == owner_user_id,
            AMProjectRun.idempotency_key == payload.idempotency_key,
        ))).scalar_one_or_none()
        if replay is not None:
            return RunOut.model_validate(replay)
        raise HTTPException(409, "Run proposal conflicted.")
    _event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=project.orbit_id,
        kind="PROJECT_RUN_PROPOSED",
        text_value=row.request_summary,
        object_type="am_project_run",
        object_id=row.id,
        project_id=project.id,
    )
    await db.commit()
    return RunOut.model_validate(row)


@router.get("/{project_id}/runs", response_model=list[RunOut])
async def list_runs(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[RunOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectRun).where(
        AMProjectRun.owner_user_id == owner_user_id,
        AMProjectRun.project_id == project_id,
    ).order_by(AMProjectRun.created_at.desc()))).scalars()
    return [RunOut.model_validate(row) for row in rows]


@router.post("/runs/{run_id}/approve", response_model=RunOut, dependencies=[Depends(require_csrf)])
async def approve_run(run_id: uuid.UUID, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    row = await _owned_run(db, owner_user_id, run_id)
    project = await _owned_project(db, owner_user_id, row.project_id)
    if row.status != "PROPOSED":
        raise HTTPException(409, "Only a PROPOSED run can be approved.")
    row.status = "APPROVED"
    row.approved_at = now_utc()
    row.updated_at = now_utc()
    # Approval grants exactly what was requested — never a silent expansion.
    row.approved_capabilities = list(row.requested_capabilities or [])
    _event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=project.orbit_id,
        kind="PROJECT_RUN_APPROVED",
        text_value=row.request_summary,
        object_type="am_project_run",
        object_id=row.id,
        project_id=project.id,
    )
    await db.commit()
    return RunOut.model_validate(row)


@router.post("/runs/{run_id}/reject", response_model=RunOut, dependencies=[Depends(require_csrf)])
async def reject_run(run_id: uuid.UUID, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    row = await _owned_run(db, owner_user_id, run_id)
    if row.status not in {"PROPOSED", "APPROVED"}:
        raise HTTPException(409, "Only a PROPOSED or APPROVED run can be rejected.")
    row.status = "REJECTED"
    row.updated_at = now_utc()
    await db.commit()
    return RunOut.model_validate(row)


@router.post("/runs/{run_id}/cancel", response_model=RunOut, dependencies=[Depends(require_csrf)])
async def cancel_run(run_id: uuid.UUID, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    row = await _owned_run(db, owner_user_id, run_id)
    if row.status in {"SUCCEEDED", "FAILED", "CANCELLED", "REJECTED"}:
        raise HTTPException(409, "This run is already terminal.")
    if row.status == "RUNNING":
        # Cooperative cancel: the worker honours CANCEL_REQUESTED at a safe point.
        row.status = "CANCEL_REQUESTED"
    else:
        row.status = "CANCELLED"
        row.cancelled_at = now_utc()
        row.completed_at = now_utc()
    row.updated_at = now_utc()
    await db.commit()
    return RunOut.model_validate(row)


@router.get("/runs/{run_id}", response_model=RunOut)
async def get_run(run_id: uuid.UUID, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    return RunOut.model_validate(await _owned_run(db, owner_user_id, run_id))


def _dispatch_run(run: AMProjectRun) -> None:
    """Queue an approved run for execution. Inline mode runs the deterministic
    adapter in-process (tests / local smoke); otherwise it is dispatched to the
    Celery worker. A broker outage surfaces as an honest 503, never fake success."""
    settings = get_settings()
    if settings.project_run_inline:
        return  # caller executes inline after commit
    from app.workers.tasks import execute_project_run_task
    try:
        execute_project_run_task.delay(str(run.id), str(run.owner_user_id))
    except Exception as exc:  # noqa: BLE001 - broker/queue unavailable
        raise HTTPException(503, "The execution queue is unavailable; the run stays QUEUED and was not lost.") from exc


@router.post("/runs/{run_id}/queue", response_model=RunOut, dependencies=[Depends(require_csrf)])
async def queue_run(run_id: uuid.UUID, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    row = await _owned_run(db, owner_user_id, run_id)
    project = await _owned_project(db, owner_user_id, row.project_id)
    if row.status != "APPROVED":
        raise HTTPException(409, "Only an APPROVED run can be queued.")
    if not row.adapter_key or row.adapter_key not in ADAPTERS:
        raise HTTPException(422, "This run has no executable adapter; it is a record-only proposal.")
    missing = ADAPTERS[row.adapter_key].required_capabilities - set(row.approved_capabilities or [])
    if missing:
        raise HTTPException(409, f"Approved capabilities are missing {sorted(missing)}.")
    row.status = "QUEUED"
    row.queued_at = now_utc()
    row.updated_at = now_utc()
    row.failure_code = None
    _event(
        db, owner_user_id=owner_user_id, orbit_id=project.orbit_id,
        kind="PROJECT_RUN_QUEUED", text_value=row.request_summary,
        object_type="am_project_run", object_id=row.id, project_id=project.id,
    )
    await db.commit()
    _dispatch_run(row)
    if get_settings().project_run_inline:
        await execute_run(db, run_id=row.id, owner_user_id=owner_user_id, worker_id="inline")
        await set_user_context(db, owner_user_id)  # execute_run's commit dropped the GUC
        row = await _owned_run(db, owner_user_id, run_id)
    return RunOut.model_validate(row)


@router.post("/runs/{run_id}/retry", response_model=RunOut, dependencies=[Depends(require_csrf)])
async def retry_run(run_id: uuid.UUID, db: Scoped, identity: Identity) -> RunOut:
    owner_user_id, _ = identity
    row = await _owned_run(db, owner_user_id, run_id)
    if row.status != "FAILED":
        raise HTTPException(409, "Only a FAILED run can be retried.")
    if not row.adapter_key or row.adapter_key not in ADAPTERS:
        raise HTTPException(422, "This run has no executable adapter.")
    # Retry preserves lineage: attempt keeps incrementing on the next claim.
    row.status = "QUEUED"
    row.queued_at = now_utc()
    row.updated_at = now_utc()
    row.failure_code = None
    await db.commit()
    _dispatch_run(row)
    if get_settings().project_run_inline:
        await execute_run(db, run_id=row.id, owner_user_id=owner_user_id, worker_id="inline")
        await set_user_context(db, owner_user_id)  # execute_run's commit dropped the GUC
        row = await _owned_run(db, owner_user_id, run_id)
    return RunOut.model_validate(row)


@router.post("/{project_id}/artifacts", response_model=ArtifactOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_artifact(
    project_id: uuid.UUID, payload: ArtifactIn, db: Scoped, identity: Identity
) -> ArtifactOut:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    await _validate_links(db, owner_user_id, project_id, task_id=payload.task_id, run_id=payload.run_id)
    if payload.provenance_label == "MODEL_GENERATED" and not payload.checksum_sha256:
        raise HTTPException(409, "Generated artifacts require a SHA-256 checksum.")
    row = AMProjectArtifact(owner_user_id=owner_user_id, project_id=project_id, **payload.model_dump())
    db.add(row)
    await db.commit()
    return ArtifactOut.model_validate(row)


@router.get("/{project_id}/artifacts", response_model=list[ArtifactOut])
async def list_artifacts(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[ArtifactOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectArtifact).where(
        AMProjectArtifact.owner_user_id == owner_user_id,
        AMProjectArtifact.project_id == project_id,
    ).order_by(AMProjectArtifact.created_at.desc()))).scalars()
    return [ArtifactOut.model_validate(row) for row in rows]


@router.post("/{project_id}/evidence", status_code=201, dependencies=[Depends(require_csrf)])
async def create_evidence(
    project_id: uuid.UUID, payload: EvidenceIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    project = await _owned_project(db, owner_user_id, project_id)
    await _validate_links(db, owner_user_id, project_id, task_id=payload.task_id, run_id=payload.run_id)
    if payload.verification_status not in {"UNVERIFIED", "PASSED", "FAILED"}:
        raise HTTPException(422, "Unsupported evidence verification status.")
    if payload.verification_status == "PASSED" and (not payload.verifier or not (payload.locator or payload.checksum_sha256)):
        raise HTTPException(409, "PASSED evidence requires a named verifier and a locator or checksum.")
    row = AMProjectEvidence(owner_user_id=owner_user_id, project_id=project_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    _event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=project.orbit_id,
        kind="PROJECT_EVIDENCE_ADDED",
        text_value=row.summary,
        object_type="am_project_evidence",
        object_id=row.id,
        project_id=project.id,
    )
    glow_result = None
    glow_reason = None
    if row.verification_status == "PASSED":
        glow_result, glow_reason = await _award_or_gate(
            db,
            owner_user_id=owner_user_id,
            event_type="project.evidence_verified",
            source_kind="AM_PROJECT_EVIDENCE",
            source_id=row.id,
            orbit_id=project.orbit_id,
            idempotency_key=f"project-evidence:{row.id}:verified",
        )
    await db.commit()
    return {"evidence": EvidenceOut.model_validate(row), "glow": _glow(glow_result, glow_reason)}


@router.get("/{project_id}/evidence", response_model=list[EvidenceOut])
async def list_evidence(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[EvidenceOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectEvidence).where(
        AMProjectEvidence.owner_user_id == owner_user_id,
        AMProjectEvidence.project_id == project_id,
    ).order_by(AMProjectEvidence.created_at.desc()))).scalars()
    return [EvidenceOut.model_validate(row) for row in rows]


@router.post("/{project_id}/reviews", response_model=ReviewOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_review(
    project_id: uuid.UUID, payload: ReviewIn, db: Scoped, identity: Identity
) -> ReviewOut:
    owner_user_id, _ = identity
    project = await _owned_project(db, owner_user_id, project_id)
    if payload.decision not in {"APPROVE", "REJECT", "CORRECT"}:
        raise HTTPException(422, "Unsupported review decision.")
    await _validate_links(db, owner_user_id, project_id, task_id=payload.task_id, run_id=payload.run_id)
    row = AMProjectReview(
        owner_user_id=owner_user_id,
        project_id=project_id,
        reviewer_label="OWNER",
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    _event(
        db,
        owner_user_id=owner_user_id,
        orbit_id=project.orbit_id,
        kind="PROJECT_REVIEW_RECORDED",
        text_value=f"{row.decision}: {row.note or 'No note'}",
        object_type="am_project_review",
        object_id=row.id,
        project_id=project.id,
    )
    await db.commit()
    return ReviewOut.model_validate(row)


@router.get("/{project_id}/reviews", response_model=list[ReviewOut])
async def list_reviews(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[ReviewOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectReview).where(
        AMProjectReview.owner_user_id == owner_user_id,
        AMProjectReview.project_id == project_id,
    ).order_by(AMProjectReview.created_at.desc()))).scalars()
    return [ReviewOut.model_validate(row) for row in rows]


# --- Execution capability catalog (inspection; no secrets) ------------------

@router.get("/execution/capabilities")
async def execution_capabilities(identity: Identity) -> dict:
    return {
        "safe_capabilities": sorted(SAFE_CAPABILITIES),
        "denied_capabilities": sorted(DENIED_CAPABILITIES),
        "adapters": [
            {
                "key": spec.key,
                "label": spec.label,
                "description": spec.description,
                "required_capabilities": sorted(spec.required_capabilities),
                "status": "LIVE_REAL",
            }
            for spec in ADAPTERS.values()
        ],
        "blocked_adapters": [
            {"key": key, "status": status} for key, status in BLOCKED_ADAPTERS.items()
        ],
    }


# --- Agent definitions ------------------------------------------------------

@router.post("/{project_id}/agents", response_model=AgentOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_agent(project_id: uuid.UUID, payload: AgentIn, db: Scoped, identity: Identity) -> AgentOut:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    if payload.adapter_key not in ADAPTERS:
        raise HTTPException(422, f"Unknown execution adapter '{payload.adapter_key}'.")
    required = ADAPTERS[payload.adapter_key].required_capabilities
    denied = [cap for cap in payload.allowed_capabilities if cap not in SAFE_CAPABILITIES]
    if denied:
        raise HTTPException(422, f"Capabilities {sorted(denied)} are denied by default and cannot be granted.")
    allowed = sorted(set(payload.allowed_capabilities)) if payload.allowed_capabilities else sorted(required)
    if not required <= set(allowed):
        raise HTTPException(422, f"allowed_capabilities must include the adapter's required set {sorted(required)}.")
    row = AMProjectAgent(
        owner_user_id=owner_user_id,
        project_id=project_id,
        name=payload.name,
        adapter_key=payload.adapter_key,
        description=payload.description,
        allowed_capabilities=allowed,
    )
    db.add(row)
    await db.commit()
    return AgentOut.model_validate(row)


@router.get("/{project_id}/agents", response_model=list[AgentOut])
async def list_agents(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[AgentOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectAgent).where(
        AMProjectAgent.owner_user_id == owner_user_id,
        AMProjectAgent.project_id == project_id,
    ).order_by(AMProjectAgent.created_at.desc()))).scalars()
    return [AgentOut.model_validate(row) for row in rows]


# --- Files: real owner-scoped object storage --------------------------------

async def _owned_file(db: Scoped, owner_user_id: uuid.UUID, file_id: uuid.UUID) -> AMProjectFile:
    row = (await db.execute(select(AMProjectFile).where(
        AMProjectFile.id == file_id,
        AMProjectFile.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Project file not found.")
    return row


@router.post("/{project_id}/files", response_model=FileOut, status_code=201, dependencies=[Depends(require_csrf)])
async def upload_file(
    project_id: uuid.UUID,
    request: Request,
    db: Scoped,
    identity: Identity,
    upload: UploadFile = File(...),
    task_id: uuid.UUID | None = None,
) -> FileOut:
    owner_user_id, _ = identity
    project = await _owned_project(db, owner_user_id, project_id)
    if task_id is not None:
        await _owned_task(db, owner_user_id, task_id, project_id)
    settings = get_settings()

    # Per-owner upload rate limit — an expensive write path beyond the auth
    # endpoints (fails closed outside development, like the other limiters).
    if not await rate_limit.allow_owner_upload(request.app.state.redis, user_id=str(owner_user_id)):
        raise HTTPException(429, "Upload rate limit reached. Try again shortly.")

    # Serialize quota accounting for this owner until the metadata insert is
    # committed. The advisory lock does not bypass RLS; it only prevents two
    # owner-scoped transactions from both approving against the same stale sum.
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:lock_key, 0))"),
        {"lock_key": f"nur:project-storage-quota:{owner_user_id}"},
    )

    # Per-owner storage quota — bound the total stored bytes, not just per-file.
    # The owner's real current usage; reject before reading the body if already
    # at the cap so an over-quota owner cannot even spend bandwidth.
    used = (await db.execute(
        select(func.coalesce(func.sum(AMProjectFile.byte_size), 0))
        .where(
            AMProjectFile.owner_user_id == owner_user_id,
            AMProjectFile.storage_state != "DELETED",
        )
    )).scalar_one()
    quota = settings.project_storage_quota_bytes
    if used >= quota:
        raise HTTPException(413, f"Storage quota reached ({quota} bytes). Delete files to free space.")

    storage = get_object_storage()
    safe = sanitize_filename(upload.filename)
    media = (upload.content_type or "application/octet-stream")[:180]

    async def _chunks():
        while True:
            chunk = await upload.read(64 * 1024)
            if not chunk:
                break
            yield chunk

    try:
        stored = await storage.put(_chunks(), max_bytes=settings.project_upload_max_bytes)
    except UploadTooLarge as exc:
        raise HTTPException(413, f"File exceeds the {exc.limit}-byte upload limit.")

    # Enforce the quota against the real stored size; if it would exceed, delete
    # the just-stored bytes so nothing is persisted past the cap.
    if used + stored.byte_size > quota:
        storage.delete(stored.object_key)
        raise HTTPException(
            413,
            f"Upload would exceed the {quota}-byte storage quota "
            f"(using {used}, file {stored.byte_size}).",
        )
    storage_state, quarantine_reason = classify_upload(safe, media)
    row = AMProjectFile(
        owner_user_id=owner_user_id,
        project_id=project_id,
        task_id=task_id,
        object_key=stored.object_key,
        original_filename=(upload.filename or safe).replace("\x00", "")[:255],
        safe_filename=safe,
        media_type=media,
        byte_size=stored.byte_size,
        checksum_sha256=stored.checksum_sha256,
        storage_backend="local",
        storage_state=storage_state,
        quarantine_reason=quarantine_reason,
        scan_state="SCAN_NOT_CONNECTED",
        provenance="OWNER_UPLOAD",
    )
    db.add(row)
    await db.flush()
    _event(
        db, owner_user_id=owner_user_id, orbit_id=project.orbit_id,
        kind="PROJECT_FILE_UPLOADED", text_value=row.safe_filename,
        object_type="am_project_file", object_id=row.id, project_id=project.id,
    )
    await db.commit()
    return FileOut.model_validate(row)


@router.get("/{project_id}/files", response_model=list[FileOut])
async def list_files(project_id: uuid.UUID, db: Scoped, identity: Identity) -> list[FileOut]:
    owner_user_id, _ = identity
    await _owned_project(db, owner_user_id, project_id)
    rows = (await db.execute(select(AMProjectFile).where(
        AMProjectFile.owner_user_id == owner_user_id,
        AMProjectFile.project_id == project_id,
        AMProjectFile.storage_state != "DELETED",
    ).order_by(AMProjectFile.created_at.desc()))).scalars()
    return [FileOut.model_validate(row) for row in rows]


@router.get("/files/{file_id}/download")
async def download_file(file_id: uuid.UUID, db: Scoped, identity: Identity) -> StreamingResponse:
    owner_user_id, _ = identity
    row = await _owned_file(db, owner_user_id, file_id)
    if row.storage_state == "DELETED":
        raise HTTPException(404, "This file has been deleted.")
    if row.storage_state == "QUARANTINED":
        raise HTTPException(409, row.quarantine_reason or "This file is quarantined and cannot be downloaded.")
    storage = get_object_storage()
    if not storage.exists(row.object_key):
        raise HTTPException(410, "The stored bytes for this file are no longer available.")
    headers = {
        "Content-Disposition": f'attachment; filename="{row.safe_filename}"',
        "X-Content-Type-Options": "nosniff",
        "Cache-Control": "private, no-store",
        "Content-Length": str(row.byte_size),
    }
    return StreamingResponse(
        storage.read_chunks(row.object_key),
        media_type="application/octet-stream",
        headers=headers,
    )


@router.post("/files/{file_id}/verify")
async def verify_file(file_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = await _owned_file(db, owner_user_id, file_id)
    if row.storage_state == "DELETED":
        raise HTTPException(404, "This file has been deleted.")
    verified = get_object_storage().verify(row.object_key, row.checksum_sha256)
    return {
        "file_id": str(row.id),
        "verified": verified,
        "checksum_sha256": row.checksum_sha256,
        "byte_size": row.byte_size,
        "storage_state": row.storage_state,
        "scan_state": row.scan_state,
    }


@router.delete("/files/{file_id}", dependencies=[Depends(require_csrf)])
async def delete_file(file_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = await _owned_file(db, owner_user_id, file_id)
    if row.storage_state != "DELETED":
        get_object_storage().delete(row.object_key)
        row.storage_state = "DELETED"
        row.updated_at = now_utc()
        await db.commit()
    return {"file_id": str(row.id), "storage_state": "DELETED"}
