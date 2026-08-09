"""Owner-facing lifecycle operations over the existing durable Agent spine."""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import json
import uuid
from zoneinfo import ZoneInfo

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic import registry
from app.agentic.compiler import (
    EXECUTOR_ROLES,
    VERIFIER_ROLES,
    CompileError,
    ProposedStep,
    compile_plan,
)
from app.agentic.enums import (
    STEP_TERMINAL,
    WORKFLOW_TERMINAL,
    RiskClass,
    StepState,
    WorkflowState,
    assert_step_transition,
    assert_workflow_transition,
)
from app.agentic.input_schemas import validate_arguments
from app.agentic.lifecycle_schemas import (
    AgentPolicyPut,
    WorkflowCreateIn,
    WorkflowRetryIn,
)
from app.agentic.orchestrator import (
    queue_ready_dependants,
    record_event,
    transition_step,
)
from app.agentic.policy import Decision, OwnerPolicy, evaluate
from app.agentic.policy_store import capabilities_for, load_policy
from app.agentic.runtime import _ensure_approval_row
from app.agentic.tools import KNOWN_CAPABILITIES
from app.models.agentic import AgentPolicy, AgentStep, AgentWorkflow


class LifecycleRefused(RuntimeError):
    """Expected refusal with a stable machine-readable code."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        status_code: int = 409,
        errors: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code
        self.errors = errors or []

    def detail(self) -> dict:
        detail: dict = {"code": self.code, "message": str(self)}
        if self.errors:
            detail["errors"] = self.errors
        return detail


def _now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def _policy_values(payload: AgentPolicyPut) -> dict:
    quiet = (
        {
            "start": payload.quiet_hours.start,
            "end": payload.quiet_hours.end,
            "tz": payload.quiet_hours.timezone,
        }
        if payload.quiet_hours is not None
        else {}
    )
    return {
        "initiative_level": payload.initiative_level.value,
        "max_risk_class": payload.max_risk_class.value,
        "permitted_tools": sorted(payload.permitted_tools),
        "auto_run_tools": sorted(payload.auto_run_tools),
        "denied_tools": sorted(payload.denied_tools),
        "daily_budget_cents": payload.daily_budget_cents,
        "max_proposals_per_day": payload.max_proposals_per_day,
        "cooldown_minutes": payload.cooldown_minutes,
        "quiet_hours": quiet,
    }


def _validate_policy(payload: AgentPolicyPut) -> None:
    named = set(payload.permitted_tools) | set(payload.auto_run_tools) | set(
        payload.denied_tools
    )
    unknown = sorted(named - set(registry.all_keys()))
    if unknown:
        raise LifecycleRefused(
            "UNKNOWN_POLICY_TOOL",
            f"Policy names unregistered tools: {unknown}",
            status_code=422,
        )
    unbound = sorted(key for key in payload.permitted_tools if not registry.is_bound(key))
    if unbound:
        raise LifecycleRefused(
            "UNBOUND_POLICY_TOOL",
            f"Unbound tools cannot be permitted for execution: {unbound}",
            status_code=422,
        )
    invalid_contracts = []
    for key in sorted(named):
        unknown_capabilities = sorted(
            registry.contract(key).required_capabilities - KNOWN_CAPABILITIES
        )
        if unknown_capabilities:
            invalid_contracts.append(
                {"tool_key": key, "unknown_capabilities": unknown_capabilities}
            )
    if invalid_contracts:
        raise LifecycleRefused(
            "INVALID_TOOL_CAPABILITIES",
            "One or more tool contracts request unknown capabilities.",
            status_code=422,
            errors=invalid_contracts,
        )
    if payload.quiet_hours is not None:
        try:
            ZoneInfo(payload.quiet_hours.timezone)
        except Exception as error:  # noqa: BLE001 - platform-specific ZoneInfo errors
            raise LifecycleRefused(
                "UNKNOWN_TIMEZONE",
                f"Unknown quiet-hours timezone: {payload.quiet_hours.timezone}",
                status_code=422,
            ) from error

    permitted = frozenset(payload.permitted_tools)
    proposed = OwnerPolicy(
        initiative_level=payload.initiative_level,
        max_risk_class=payload.max_risk_class,
        permitted_tools=permitted,
        auto_run_tools=frozenset(payload.auto_run_tools),
        denied_tools=frozenset(payload.denied_tools),
        granted_capabilities=capabilities_for(permitted),
        daily_budget_cents=payload.daily_budget_cents,
    )
    ineffective = []
    for key in sorted(payload.auto_run_tools):
        verdict = evaluate(registry.contract(key), proposed)
        if verdict.decision is not Decision.ALLOW:
            ineffective.append({"tool_key": key, "reason": verdict.reason})
    if ineffective:
        raise LifecycleRefused(
            "INEFFECTIVE_AUTO_RUN_POLICY",
            "auto_run_tools contains tools the selected initiative or risk ceiling cannot auto-run.",
            status_code=422,
            errors=ineffective,
        )


def _policy_snapshot(row: AgentPolicy | None) -> dict:
    if row is None:
        return {
            "id": None,
            "scope": "ACCOUNT",
            "persisted": False,
            "version": 0,
            "initiative_level": "SUGGEST",
            "max_risk_class": "R1_PRIVATE_DRAFT",
            "permitted_tools": [],
            "auto_run_tools": [],
            "denied_tools": [],
            "granted_capabilities": [],
            "daily_budget_cents": 0,
            "max_proposals_per_day": 3,
            "cooldown_minutes": 180,
            "quiet_hours": {},
        }
    permitted = frozenset(row.permitted_tools or ())
    return {
        "id": str(row.id),
        "scope": "ACCOUNT",
        "persisted": True,
        "version": row.version,
        "initiative_level": row.initiative_level,
        "max_risk_class": row.max_risk_class,
        "permitted_tools": sorted(permitted),
        "auto_run_tools": sorted(set(row.auto_run_tools or ()) & permitted),
        "denied_tools": sorted(row.denied_tools or ()),
        "granted_capabilities": sorted(capabilities_for(permitted)),
        "daily_budget_cents": row.daily_budget_cents,
        "max_proposals_per_day": row.max_proposals_per_day,
        "cooldown_minutes": row.cooldown_minutes,
        "quiet_hours": row.quiet_hours or {},
    }


async def _account_policy_row(
    db: AsyncSession, owner_user_id: uuid.UUID, *, lock: bool = False
) -> AgentPolicy | None:
    statement = select(AgentPolicy).where(
        AgentPolicy.owner_user_id == owner_user_id,
        AgentPolicy.orbit_id.is_(None),
        AgentPolicy.project_id.is_(None),
    )
    if lock:
        statement = statement.with_for_update()
    return (await db.execute(statement)).scalar_one_or_none()


async def get_account_policy(db: AsyncSession, *, owner_user_id: uuid.UUID) -> dict:
    return _policy_snapshot(await _account_policy_row(db, owner_user_id))


async def put_account_policy(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    payload: AgentPolicyPut,
) -> dict:
    _validate_policy(payload)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"agent-policy:{owner_user_id}"},
    )
    row = await _account_policy_row(db, owner_user_id, lock=True)
    if row is None:
        if payload.seen_version != 0:
            raise LifecycleRefused(
                "STALE_POLICY_VERSION",
                "The policy changed after it was displayed; reload before saving.",
            )
        row = AgentPolicy(
            owner_user_id=owner_user_id,
            orbit_id=None,
            project_id=None,
            version=1,
            **_policy_values(payload),
        )
        db.add(row)
    else:
        if row.version != payload.seen_version:
            raise LifecycleRefused(
                "STALE_POLICY_VERSION",
                "The policy changed after it was displayed; reload before saving.",
            )
        for key, value in _policy_values(payload).items():
            setattr(row, key, value)
        row.version += 1
        row.updated_at = _now()
    await db.flush()
    return _policy_snapshot(row)


def _digest_json(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _create_digest(payload: WorkflowCreateIn) -> str:
    return _digest_json(payload.model_dump(mode="json"))


def _retry_digest(original_id: uuid.UUID, payload: WorkflowRetryIn) -> str:
    return _digest_json(
        {
            "operation": "retry",
            "workflow_id": str(original_id),
            "request_id": str(payload.request_id),
            "seen_plan_version": payload.seen_plan_version,
        }
    )


def _proposed_steps(payload: WorkflowCreateIn) -> tuple[ProposedStep, ...]:
    return tuple(
        ProposedStep(
            key=step.key,
            role=step.role,
            tool_key=step.tool_key,
            depends_on=tuple(step.depends_on),
            input_refs=dict(step.input_refs),
            rationale=step.rationale,
        )
        for step in payload.proposed_steps
    )


def _reconstruct(steps: list[AgentStep]) -> tuple[ProposedStep, ...]:
    return tuple(
        ProposedStep(
            key=step.key,
            role=step.role,
            tool_key=step.tool_key or "",
            depends_on=tuple(step.depends_on or ()),
            input_refs=dict(step.input_refs or {}),
            rationale="owner-approved persisted step",
        )
        for step in steps
    )


def _compile_error(error: CompileError) -> dict:
    return {"code": error.code, "message": error.message, "step_key": error.step_key}


def _compile_or_refuse(
    proposed: tuple[ProposedStep, ...], policy: OwnerPolicy, *, status_code: int
):
    errors: list[CompileError] = []
    allowed_roles = EXECUTOR_ROLES | VERIFIER_ROLES
    for step in proposed:
        if step.role not in allowed_roles:
            errors.append(
                CompileError(
                    "UNKNOWN_ROLE",
                    f"role {step.role!r} is not executable or a verifier",
                    step.key,
                )
            )
        try:
            registry.contract(step.tool_key)
        except LookupError:
            continue
        if not registry.is_bound(step.tool_key):
            errors.append(
                CompileError(
                    "UNBOUND_TOOL",
                    f"tool {step.tool_key!r} has no bound handler",
                    step.key,
                )
            )
            continue
        errors.extend(
            CompileError("INVALID_TOOL_INPUT", problem, step.key)
            for problem in validate_arguments(step.tool_key, step.input_refs)
        )
        if len(json.dumps(step.input_refs, default=str).encode()) > 32_768:
            errors.append(
                CompileError(
                    "STEP_INPUT_TOO_LARGE",
                    "step input_refs exceeds the 32 KiB owner limit",
                    step.key,
                )
            )
    compiled = compile_plan(proposed, policy, within_scope=True)
    errors.extend(compiled.errors)
    if errors:
        raise LifecycleRefused(
            "PLAN_COMPILE_FAILED",
            "The proposed workflow did not compile; nothing was persisted or queued.",
            status_code=status_code,
            errors=[_compile_error(error) for error in errors],
        )
    return compiled


def _risk_ceiling(steps) -> str:
    order = list(RiskClass)
    return max((step.risk_class for step in steps), key=lambda item: order.index(RiskClass(item)))


def _workflow_snapshot(
    workflow: AgentWorkflow,
    steps: list[AgentStep],
    *,
    idempotent_replay: bool = False,
) -> dict:
    return {
        "id": str(workflow.id),
        "title": workflow.title,
        "objective": workflow.objective,
        "kind": workflow.kind,
        "state": workflow.state,
        "plan_version": workflow.plan_version,
        "retry_of_workflow_id": (
            str(workflow.retry_of_workflow_id) if workflow.retry_of_workflow_id else None
        ),
        "context_manifest": workflow.context_manifest,
        "success_criteria": workflow.success_criteria,
        "cost_cents": workflow.cost_cents,
        "failure_code": workflow.failure_code,
        "idempotent_replay": idempotent_replay,
        "retryable": workflow.state in {
            WorkflowState.FAILED.value,
            WorkflowState.NEEDS_REVISION.value,
        },
        "steps": [
            {
                "id": str(step.id),
                "key": step.key,
                "ordinal": step.ordinal,
                "state": step.state,
                "role": step.role,
                "tool_key": step.tool_key,
                "tool_version": step.tool_version,
                "risk_class": step.risk_class,
                "approval_required": step.approval_required,
                "depends_on": step.depends_on,
                "input_refs": step.input_refs,
                "verification_verdict": step.verification_verdict,
                "attempt": step.attempt,
                "execution_attempt": str(step.execution_attempt),
                "idempotency_key": step.idempotency_key,
                "failure_code": step.failure_code,
            }
            for step in steps
        ],
    }


async def _owned_workflow(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    lock: bool = False,
) -> tuple[AgentWorkflow, list[AgentStep]]:
    workflow_query = select(AgentWorkflow).where(
        AgentWorkflow.id == workflow_id,
        AgentWorkflow.owner_user_id == owner_user_id,
    ).execution_options(populate_existing=True)
    if lock:
        workflow_query = workflow_query.with_for_update()
    workflow = (await db.execute(workflow_query)).scalar_one_or_none()
    if workflow is None:
        raise LifecycleRefused(
            "WORKFLOW_NOT_FOUND", "workflow not found", status_code=404
        )
    step_query = (
        select(AgentStep)
        .where(
            AgentStep.workflow_id == workflow_id,
            AgentStep.owner_user_id == owner_user_id,
        )
        .order_by(AgentStep.ordinal)
        .execution_options(populate_existing=True)
    )
    if lock:
        step_query = step_query.with_for_update()
    steps = list((await db.execute(step_query)).scalars().all())
    return workflow, steps


async def get_workflow(
    db: AsyncSession, *, owner_user_id: uuid.UUID, workflow_id: uuid.UUID
) -> dict:
    workflow, steps = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id
    )
    return _workflow_snapshot(workflow, steps)


def _encode_cursor(updated_at: dt.datetime, row_id: uuid.UUID) -> str:
    raw = json.dumps(
        {"updated_at": updated_at.isoformat(), "id": str(row_id)},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[dt.datetime, uuid.UUID]:
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        value = json.loads(base64.urlsafe_b64decode(padded).decode())
        timestamp = dt.datetime.fromisoformat(value["updated_at"])
        if timestamp.tzinfo is None:
            raise ValueError("cursor timestamp needs a timezone")
        return timestamp, uuid.UUID(value["id"])
    except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
        raise LifecycleRefused(
            "INVALID_CURSOR", "The workflow cursor is invalid.", status_code=422
        ) from error


async def list_workflows(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    state: str | None,
    limit: int,
    cursor: str | None,
) -> dict:
    if state and state not in {member.value for member in WorkflowState}:
        raise LifecycleRefused("UNKNOWN_WORKFLOW_STATE", "unknown workflow state", status_code=422)
    statement = select(AgentWorkflow).where(
        AgentWorkflow.owner_user_id == owner_user_id
    )
    if state:
        statement = statement.where(AgentWorkflow.state == state)
    if cursor:
        cursor_time, cursor_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                AgentWorkflow.updated_at < cursor_time,
                and_(
                    AgentWorkflow.updated_at == cursor_time,
                    AgentWorkflow.id < cursor_id,
                ),
            )
        )
    rows = list(
        (
            await db.execute(
                statement.order_by(
                    AgentWorkflow.updated_at.desc(), AgentWorkflow.id.desc()
                ).limit(limit + 1)
            )
        ).scalars().all()
    )
    has_more = len(rows) > limit
    rows = rows[:limit]
    counts: dict[uuid.UUID, tuple[int, int]] = {}
    if rows:
        count_rows = (
            await db.execute(
                select(
                    AgentStep.workflow_id,
                    func.count(AgentStep.id),
                    func.count(AgentStep.id).filter(
                        AgentStep.state == StepState.SUCCEEDED.value
                    ),
                )
                .where(
                    AgentStep.owner_user_id == owner_user_id,
                    AgentStep.workflow_id.in_([row.id for row in rows]),
                )
                .group_by(AgentStep.workflow_id)
            )
        ).all()
        counts = {row[0]: (int(row[1]), int(row[2])) for row in count_rows}
    return {
        "workflows": [
            {
                "id": str(row.id),
                "title": row.title,
                "objective": row.objective,
                "state": row.state,
                "kind": row.kind,
                "step_count": counts.get(row.id, (0, 0))[0],
                "steps_done": counts.get(row.id, (0, 0))[1],
                "cost_cents": row.cost_cents,
                "failure_code": row.failure_code,
                "retry_of_workflow_id": (
                    str(row.retry_of_workflow_id) if row.retry_of_workflow_id else None
                ),
                "updated_at": row.updated_at.isoformat(),
            }
            for row in rows
        ],
        "count": len(rows),
        "next_cursor": (
            _encode_cursor(rows[-1].updated_at, rows[-1].id)
            if has_more and rows
            else None
        ),
    }


async def _persist_compiled(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    request_id: uuid.UUID,
    request_digest: str,
    title: str,
    objective: str,
    context_manifest: dict,
    success_criteria: list,
    proposed: tuple[ProposedStep, ...],
    compiled,
    policy: OwnerPolicy,
    kind: str,
    retry_of_workflow_id: uuid.UUID | None = None,
) -> dict:
    workflow = AgentWorkflow(
        owner_user_id=owner_user_id,
        kind=kind,
        title=title,
        objective=objective,
        state=WorkflowState.DRAFT.value,
        request_id=request_id,
        request_digest=request_digest,
        retry_of_workflow_id=retry_of_workflow_id,
        trigger_kind="OWNER_REQUEST",
        trigger_ref=request_id,
        initiative_level=policy.initiative_level.value,
        context_manifest=context_manifest,
        success_criteria=success_criteria,
        scope="PRIVATE",
        max_risk_class=_risk_ceiling(compiled.steps),
    )
    db.add(workflow)
    await db.flush()
    await record_event(
        db,
        owner_user_id=owner_user_id,
        workflow_id=workflow.id,
        event_type="WORKFLOW_CREATED",
        summary="owner created an explicit workflow draft",
        to_state=WorkflowState.DRAFT.value,
        actor="OWNER",
        detail={
            "request_id": str(request_id),
            "retry_of_workflow_id": (
                str(retry_of_workflow_id) if retry_of_workflow_id else None
            ),
        },
    )
    assert_workflow_transition(WorkflowState.DRAFT, WorkflowState.PLANNING)
    workflow.state = WorkflowState.PLANNING.value
    workflow.updated_at = _now()

    by_key = {step.key: step for step in proposed}
    rows: list[AgentStep] = []
    for step in compiled.steps:
        source = by_key[step.key]
        row = AgentStep(
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            ordinal=step.ordinal,
            key=step.key,
            state=step.state.value,
            depends_on=list(step.depends_on),
            role=step.role,
            tool_key=step.tool_key,
            tool_version=step.tool_version,
            risk_class=step.risk_class,
            requested_capabilities=list(step.requested_capabilities),
            approval_required=step.approval_required,
            input_refs=dict(source.input_refs),
            timeout_seconds=step.timeout_seconds,
            idempotency_key=(
                f"owner-workflow:{workflow.id}:{workflow.plan_version}:{step.key}"
            ),
        )
        db.add(row)
        rows.append(row)
    await db.flush()
    assert_workflow_transition(WorkflowState.PLANNING, WorkflowState.PLAN_READY)
    workflow.state = WorkflowState.PLAN_READY.value
    workflow.updated_at = _now()
    await db.flush()
    await record_event(
        db,
        owner_user_id=owner_user_id,
        workflow_id=workflow.id,
        event_type="PLAN_COMPILED",
        summary="owner plan compiled and persisted atomically",
        from_state=WorkflowState.PLANNING.value,
        to_state=WorkflowState.PLAN_READY.value,
        actor="OWNER",
        detail={
            "step_count": len(rows),
            "approval_keys": list(compiled.approval_keys),
        },
    )
    return _workflow_snapshot(workflow, rows)


async def _existing_request(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    request_id: uuid.UUID,
    request_digest: str,
) -> dict | None:
    existing = (
        await db.execute(
            select(AgentWorkflow).where(
                AgentWorkflow.owner_user_id == owner_user_id,
                AgentWorkflow.request_id == request_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        return None
    if existing.request_digest != request_digest:
        raise LifecycleRefused(
            "IDEMPOTENCY_KEY_REUSED",
            "request_id was already used for a different Agent operation.",
        )
    _, steps = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=existing.id
    )
    return _workflow_snapshot(existing, steps, idempotent_replay=True)


async def create_workflow(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    payload: WorkflowCreateIn,
) -> dict:
    digest = _create_digest(payload)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"agent-create:{owner_user_id}:{payload.request_id}"},
    )
    if replay := await _existing_request(
        db,
        owner_user_id=owner_user_id,
        request_id=payload.request_id,
        request_digest=digest,
    ):
        return replay
    if len(json.dumps(payload.context_manifest, default=str).encode()) > 65_536:
        raise LifecycleRefused(
            "CONTEXT_MANIFEST_TOO_LARGE",
            "context_manifest exceeds the 64 KiB owner limit.",
            status_code=422,
        )
    proposed = _proposed_steps(payload)
    policy = await load_policy(db, owner_user_id=owner_user_id)
    compiled = _compile_or_refuse(proposed, policy, status_code=422)
    return await _persist_compiled(
        db,
        owner_user_id=owner_user_id,
        request_id=payload.request_id,
        request_digest=digest,
        title=payload.title,
        objective=payload.objective,
        context_manifest=payload.context_manifest,
        success_criteria=payload.success_criteria,
        proposed=proposed,
        compiled=compiled,
        policy=policy,
        kind="OWNER_DEFINED",
    )


async def start_workflow(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    seen_plan_version: int,
) -> dict:
    workflow, steps = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, lock=True
    )
    if workflow.plan_version != seen_plan_version:
        raise LifecycleRefused(
            "STALE_PLAN_VERSION",
            "The workflow plan changed after it was displayed; reload before starting.",
        )
    if workflow.state != WorkflowState.PLAN_READY.value:
        raise LifecycleRefused(
            "WORKFLOW_NOT_STARTABLE",
            f"workflow is {workflow.state}, not PLAN_READY",
        )
    if not steps:
        raise LifecycleRefused("EMPTY_WORKFLOW", "A workflow with no steps cannot start.")

    policy = await load_policy(db, owner_user_id=owner_user_id)
    compiled = _compile_or_refuse(_reconstruct(steps), policy, status_code=409)
    compiled_by_key = {step.key: step for step in compiled.steps}
    stale = [
        step.key
        for step in steps
        if compiled_by_key[step.key].tool_version != step.tool_version
        or compiled_by_key[step.key].ordinal != step.ordinal
    ]
    if stale:
        raise LifecycleRefused(
            "COMPILED_PLAN_STALE",
            f"Registered tools changed for persisted steps: {stale}",
        )

    assert_workflow_transition(WorkflowState.PLAN_READY, WorkflowState.POLICY_REVIEW)
    workflow.state = WorkflowState.POLICY_REVIEW.value
    workflow.updated_at = _now()
    for row in steps:
        row.approval_required = compiled_by_key[row.key].approval_required
    await db.flush()
    await record_event(
        db,
        owner_user_id=owner_user_id,
        workflow_id=workflow.id,
        event_type="POLICY_REVALIDATED",
        summary="current owner policy revalidated the compiled plan",
        from_state=WorkflowState.PLAN_READY.value,
        to_state=WorkflowState.POLICY_REVIEW.value,
        actor="OWNER",
    )

    waiting: list[uuid.UUID] = []
    for row in steps:
        compiled_step = compiled_by_key[row.key]
        if not compiled_step.approval_required:
            continue
        if row.state == StepState.READY.value:
            moved = await transition_step(
                db,
                owner_user_id=owner_user_id,
                step_id=row.id,
                current=StepState.READY,
                nxt=StepState.WAITING_APPROVAL,
            )
            if not moved:
                raise LifecycleRefused(
                    "CONCURRENT_STEP_TRANSITION",
                    f"step {row.key!r} changed while the workflow was starting",
                )
            row.state = StepState.WAITING_APPROVAL.value
        elif row.state != StepState.WAITING_APPROVAL.value:
            continue
        contract = registry.contract(row.tool_key or "")
        verdict = evaluate(contract, policy, within_scope=True)
        await _ensure_approval_row(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            step_id=row.id,
            tool_key=contract.key,
            tool_version=contract.version,
            arguments=dict(row.input_refs or {}),
            rationale=verdict.reason,
            risk_class=contract.risk_class.value,
            reversible=contract.reversible,
            cost_ceiling_cents=contract.estimated_cost_cents,
            expected_result="; ".join(map(str, workflow.success_criteria))[:2000],
            scope_summary=json.dumps(workflow.context_manifest, sort_keys=True)[:2000],
        )
        await record_event(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            step_id=row.id,
            event_type="STEP_AWAITING_APPROVAL",
            summary=verdict.reason,
            from_state=StepState.READY.value,
            to_state=StepState.WAITING_APPROVAL.value,
            actor="OWNER",
        )
        waiting.append(row.id)

    queued = await queue_ready_dependants(
        db, owner_user_id=owner_user_id, workflow_id=workflow.id
    )
    if waiting:
        assert_workflow_transition(
            WorkflowState.POLICY_REVIEW, WorkflowState.WAITING_APPROVAL
        )
        workflow.state = WorkflowState.WAITING_APPROVAL.value
    else:
        assert_workflow_transition(WorkflowState.POLICY_REVIEW, WorkflowState.APPROVED)
        workflow.state = WorkflowState.APPROVED.value
        await db.flush()
        assert_workflow_transition(WorkflowState.APPROVED, WorkflowState.QUEUED)
        workflow.state = WorkflowState.QUEUED.value
    workflow.updated_at = _now()
    await db.flush()
    await record_event(
        db,
        owner_user_id=owner_user_id,
        workflow_id=workflow.id,
        event_type="WORKFLOW_STARTED",
        summary="owner started the compiled workflow through the durable outbox",
        from_state=WorkflowState.PLAN_READY.value,
        to_state=workflow.state,
        actor="OWNER",
        detail={
            "queued_step_ids": [str(item["step_id"]) for item in queued],
            "waiting_approval_step_ids": [str(item) for item in waiting],
        },
    )
    await db.refresh(workflow)
    _, refreshed = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow.id
    )
    result = _workflow_snapshot(workflow, refreshed)
    result["queued_step_ids"] = [str(item["step_id"]) for item in queued]
    result["waiting_approval_step_ids"] = [str(item) for item in waiting]
    return result


async def cancel_workflow(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
) -> dict:
    workflow, steps = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, lock=True
    )
    current = WorkflowState(workflow.state)
    if current in WORKFLOW_TERMINAL:
        raise LifecycleRefused(
            "WORKFLOW_TERMINAL", f"workflow is already terminal in {workflow.state}"
        )
    if current is WorkflowState.DRAFT:
        assert_workflow_transition(current, WorkflowState.CANCELLED)
    elif current is not WorkflowState.CANCEL_REQUESTED:
        assert_workflow_transition(current, WorkflowState.CANCEL_REQUESTED)
        workflow.state = WorkflowState.CANCEL_REQUESTED.value
        workflow.updated_at = _now()
        await db.flush()
        await record_event(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            event_type="WORKFLOW_CANCEL_REQUESTED",
            summary="owner requested cancellation",
            from_state=current.value,
            to_state=WorkflowState.CANCEL_REQUESTED.value,
            actor="OWNER",
        )

    await db.execute(
        text(
            "UPDATE agent_approvals SET invalidated_from = decision, "
            "decision = 'INVALIDATED', invalidated_at = now(), "
            "invalidation_reason = 'workflow cancelled by owner' "
            "WHERE owner_user_id = :owner AND workflow_id = :workflow "
            "AND decision IN ('PENDING', 'APPROVED', 'EDITED')"
        ),
        {"owner": owner_user_id, "workflow": workflow.id},
    )
    await db.execute(
        text(
            "UPDATE agent_dispatch_outbox SET state = 'CANCELLED', "
            "claimed_by = NULL, claim_token = NULL, lease_expires_at = NULL, "
            "sent_at = NULL, last_error = 'cancelled by owner' "
            "WHERE owner_user_id = :owner AND workflow_id = :workflow "
            "AND state IN ('RETRYABLE', 'CLAIMED')"
        ),
        {"owner": owner_user_id, "workflow": workflow.id},
    )
    for step in steps:
        state = StepState(step.state)
        if state in STEP_TERMINAL:
            continue
        assert_step_transition(state, StepState.CANCELLED)
        moved = await transition_step(
            db,
            owner_user_id=owner_user_id,
            step_id=step.id,
            current=state,
            nxt=StepState.CANCELLED,
        )
        if not moved:
            raise LifecycleRefused(
                "CONCURRENT_STEP_TRANSITION",
                f"step {step.key!r} changed while cancellation was applied",
            )
        await db.execute(
            text(
                "UPDATE agent_steps SET worker_id = NULL, lease_expires_at = NULL, "
                "execution_attempt = gen_random_uuid() "
                "WHERE id = :step AND owner_user_id = :owner"
            ),
            {"step": step.id, "owner": owner_user_id},
        )
        await record_event(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            step_id=step.id,
            event_type="STEP_CANCELLED",
            summary="owner cancellation fenced this unfinished step",
            from_state=state.value,
            to_state=StepState.CANCELLED.value,
            actor="OWNER",
        )
    if current is not WorkflowState.DRAFT:
        assert_workflow_transition(
            WorkflowState.CANCEL_REQUESTED, WorkflowState.CANCELLED
        )
    workflow.state = WorkflowState.CANCELLED.value
    workflow.updated_at = _now()
    await db.flush()
    await record_event(
        db,
        owner_user_id=owner_user_id,
        workflow_id=workflow.id,
        event_type="WORKFLOW_CANCELLED",
        summary="workflow, unfinished steps, approvals, and unsent dispatch were fenced",
        from_state=current.value,
        to_state=WorkflowState.CANCELLED.value,
        actor="OWNER",
    )
    await db.refresh(workflow)
    _, refreshed = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow.id
    )
    return _workflow_snapshot(workflow, refreshed)


async def retry_workflow(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    workflow_id: uuid.UUID,
    payload: WorkflowRetryIn,
) -> dict:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"agent-retry:{owner_user_id}:{payload.request_id}"},
    )
    digest = _retry_digest(workflow_id, payload)
    if replay := await _existing_request(
        db,
        owner_user_id=owner_user_id,
        request_id=payload.request_id,
        request_digest=digest,
    ):
        return replay
    original, steps = await _owned_workflow(
        db, owner_user_id=owner_user_id, workflow_id=workflow_id, lock=True
    )
    if original.plan_version != payload.seen_plan_version:
        raise LifecycleRefused(
            "STALE_PLAN_VERSION",
            "The failed plan changed after it was displayed; reload before retrying.",
        )
    if original.state not in {
        WorkflowState.FAILED.value,
        WorkflowState.NEEDS_REVISION.value,
    }:
        raise LifecycleRefused(
            "WORKFLOW_NOT_RETRYABLE",
            f"workflow is {original.state}; retry requires FAILED or NEEDS_REVISION",
        )
    proposed = _reconstruct(steps)
    policy = await load_policy(db, owner_user_id=owner_user_id)
    compiled = _compile_or_refuse(proposed, policy, status_code=409)
    return await _persist_compiled(
        db,
        owner_user_id=owner_user_id,
        request_id=payload.request_id,
        request_digest=digest,
        title=original.title,
        objective=original.objective,
        context_manifest=dict(original.context_manifest or {}),
        success_criteria=list(original.success_criteria or []),
        proposed=proposed,
        compiled=compiled,
        policy=policy,
        kind="OWNER_RETRY",
        retry_of_workflow_id=original.id,
    )


async def cancel_owner_workflows_for_deletion(
    db: AsyncSession, *, owner_user_id: uuid.UUID
) -> int:
    """Fence every nonterminal workflow before account access is disabled."""
    active_ids = list(
        (
            await db.execute(
                select(AgentWorkflow.id).where(
                    AgentWorkflow.owner_user_id == owner_user_id,
                    AgentWorkflow.state.not_in(
                        [state.value for state in WORKFLOW_TERMINAL]
                    ),
                )
            )
        ).scalars().all()
    )
    for workflow_id in active_ids:
        await cancel_workflow(
            db, owner_user_id=owner_user_id, workflow_id=workflow_id
        )
    return len(active_ids)
