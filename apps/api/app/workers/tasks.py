"""Phase 0 worker spine: idempotent, ID-only payloads, structured logs.
Workers never execute user-supplied code and never receive private raw text."""
import datetime as dt
import hashlib
import logging
import socket
import uuid

from sqlalchemy import select

from app.core.config import get_settings
from app.core.logging import configure_logging, log
from app.db.rls import set_user_context
from app.db.session import get_sessionmaker
from app.insights.due_owner_service import insight_consolidation_owner_ids
from app.insights.service import InsightRunBusy, consolidate_owner
from app.models import InsightProjectionCheckpoint
from app.models._mixins import now_utc
from app.omega.due_owner_service import omega_consolidation_due_owner_ids
from app.omega.replay_service import omega_consolidate_owner
from app.services.account_service import purge_due_account_deletions
from app.services.project_execution import execute_run, recover_stale_runs
from app.services.project_recovery import (
    project_recovery_owner_ids,
    queued_project_run_ids,
)
from app.workers.asyncrun import run_task
from app.workers.celery_app import celery

configure_logging()
logger = logging.getLogger("nur.worker")


@celery.task(name="nur.health_ping", ignore_result=False)
def health_ping() -> str:
    log(logger, "health_ping executed")
    return "pong"


@celery.task(name="nur.send_verification_email_stub", ignore_result=True, max_retries=3)
def send_verification_email_stub(user_id: str) -> None:
    """Stub: payload is a user ID only. Real delivery is a later phase; this task
    exists to prove the queue spine, not to fake email sending."""
    log(logger, "verification email stub", user_id=user_id, delivered=False, stub=True)


@celery.task(name="nur.omega_consolidate_owner", ignore_result=False)
def omega_consolidate_owner_task(owner_user_id: str, orbit_id: str | None = None, run_kind: str = "DAILY") -> dict:
    """Omega replay job: ID-only payloads, no raw private text."""
    return run_task(lambda: _omega_consolidate_owner(owner_user_id, orbit_id, run_kind))


async def _omega_consolidate_owner(owner_user_id: str, orbit_id: str | None, run_kind: str) -> dict:
    async with get_sessionmaker()() as db:
        owner_uuid = uuid.UUID(owner_user_id)
        orbit_uuid = uuid.UUID(orbit_id) if orbit_id else None
        await set_user_context(db, owner_uuid)
        run = await omega_consolidate_owner(
            db,
            owner_user_id=owner_uuid,
            orbit_id=orbit_uuid,
            run_kind=run_kind,
        )
        await db.commit()
        log(logger, "omega consolidation", owner_user_id=owner_user_id, run_id=str(run.id), status=run.status)
        return {"id": str(run.id), "status": run.status}


@celery.task(name="nur.execute_project_run", ignore_result=False, acks_late=True)
def execute_project_run_task(run_id: str, owner_user_id: str, worker_id: str | None = None) -> dict:
    """Execute one approved+queued AM Project run. Payload is IDs only; the run's
    deterministic adapter never touches external systems. The claim inside
    execute_run makes a duplicate delivery an idempotent no-op."""
    return run_task(lambda: _execute_project_run(run_id, owner_user_id, worker_id))


async def _execute_project_run(run_id: str, owner_user_id: str, worker_id: str | None) -> dict:
    async with get_sessionmaker()() as db:
        owner_uuid = uuid.UUID(owner_user_id)
        await set_user_context(db, owner_uuid)
        result = await execute_run(
            db,
            run_id=uuid.UUID(run_id),
            owner_user_id=owner_uuid,
            worker_id=worker_id or f"celery:{socket.gethostname()}:{uuid.uuid4().hex[:8]}",
        )
        log(logger, "project run execution", run_id=run_id, status=result.status,
            failure_code=result.failure_code, idempotent_noop=result.idempotent_noop)
        return {"run_id": str(result.run_id), "status": result.status,
                "failure_code": result.failure_code, "artifact_id": str(result.artifact_id) if result.artifact_id else None}


@celery.task(name="nur.reconcile_project_runs", ignore_result=False, acks_late=True)
def reconcile_project_runs_task() -> dict:
    """Recover stale runs and republish queued run IDs after broker outages."""
    return run_task(lambda: _reconcile_project_runs())


async def _reconcile_project_runs() -> dict:
    settings = get_settings()
    async with get_sessionmaker()() as db:
        owners = await project_recovery_owner_ids(
            db, limit=settings.project_run_recovery_owner_batch
        )

    totals = {
        "owner_count": len(owners),
        "scanned": 0,
        "requeued": 0,
        "dead_lettered": 0,
        "dispatched": 0,
        "dispatch_failed": 0,
    }
    for owner_id in owners:
        result = await _reconcile_project_runs_for_owner(owner_id)
        for key in (
            "scanned",
            "requeued",
            "dead_lettered",
            "dispatched",
            "dispatch_failed",
        ):
            totals[key] += result[key]
    log(logger, "project run recovery sweep", **totals)
    return totals


async def _reconcile_project_runs_for_owner(owner_user_id: uuid.UUID) -> dict[str, int]:
    settings = get_settings()
    async with get_sessionmaker()() as db:
        await set_user_context(db, owner_user_id)
        recovery = await recover_stale_runs(db)
        # recover_stale_runs commits when it changes rows, which clears the
        # transaction-local RLS context. Re-arm it before reading queued IDs.
        await set_user_context(db, owner_user_id)
        queued_ids = await queued_project_run_ids(
            db,
            owner_user_id=owner_user_id,
            limit=settings.project_run_recovery_run_batch,
        )

    dispatched = 0
    dispatch_failed = 0
    for run_id in queued_ids:
        try:
            execute_project_run_task.delay(str(run_id), str(owner_user_id))
            dispatched += 1
        except Exception as exc:  # noqa: BLE001 - next Beat tick retries the ID
            dispatch_failed += 1
            log(
                logger,
                "project run redispatch unavailable",
                run_id=str(run_id),
                owner_user_id=str(owner_user_id),
                error_type=type(exc).__name__,
            )

    return {
        **recovery,
        "dispatched": dispatched,
        "dispatch_failed": dispatch_failed,
    }


@celery.task(name="nur.omega_consolidate_due_owners", ignore_result=False)
def omega_consolidate_due_owners_task() -> dict:
    """Scheduled Omega pass: owner IDs only, never raw private text."""
    return run_task(lambda: _omega_consolidate_due_owners())


async def _omega_consolidate_due_owners() -> dict:
    dispatched: list[str] = []
    async with get_sessionmaker()() as db:
        owners = await omega_consolidation_due_owner_ids(db)
    for owner_id in owners:
        omega_consolidate_owner_task.delay(str(owner_id), None, "DAILY")
        dispatched.append(str(owner_id))
    log(logger, "omega due-owner dispatch", owner_count=len(dispatched))
    return {"dispatched_owner_ids": dispatched, "count": len(dispatched)}


@celery.task(name="nur.insights_consolidate_owner", ignore_result=False, acks_late=True)
def insights_consolidate_owner_task(owner_user_id: str, run_kind: str = "EVENT") -> dict:
    """Run one bounded Insight pass. The queue payload contains IDs and an enum only."""
    return run_task(lambda: _insights_consolidate_owner(owner_user_id, run_kind))


async def _insights_consolidate_owner(owner_user_id: str, run_kind: str) -> dict:
    owner_uuid = uuid.UUID(owner_user_id)
    normalized_kind = run_kind.upper()
    async with get_sessionmaker()() as db:
        await set_user_context(db, owner_uuid)
        checkpoint = (
            await db.execute(
                select(InsightProjectionCheckpoint).where(
                    InsightProjectionCheckpoint.owner_user_id == owner_uuid
                )
            )
        ).scalar_one_or_none()
        due_reason = _insight_due_reason(checkpoint, normalized_kind, now=now_utc())
        if due_reason is not None:
            return {"status": "SKIPPED", "reason": due_reason}
        idempotency_key = _insight_idempotency_key(checkpoint, normalized_kind)
        try:
            run = await consolidate_owner(
                db,
                owner_user_id=owner_uuid,
                run_kind=normalized_kind,
                idempotency_key=idempotency_key,
                worker_id=f"celery:{socket.gethostname()}",
            )
        except InsightRunBusy as exc:
            await db.rollback()
            return {"status": "SKIPPED", "reason": str(exc)}
        await db.commit()
        log(
            logger,
            "insight consolidation",
            owner_user_id=owner_user_id,
            run_id=str(run.id),
            status=run.status,
            run_kind=normalized_kind,
        )
        return {"id": str(run.id), "status": run.status, "run_kind": run.run_kind}


def _insight_due_reason(
    checkpoint: InsightProjectionCheckpoint | None, run_kind: str, *, now: dt.datetime
) -> str | None:
    if checkpoint is None:
        return "NO_PENDING_EVENTS"
    if checkpoint.attempt_count >= checkpoint.max_attempts:
        return "RETRY_CEILING_REACHED"
    if checkpoint.claim_token and checkpoint.lease_expires_at and checkpoint.lease_expires_at > now:
        return "OWNER_RUN_LEASED"
    if checkpoint.next_eligible_at and checkpoint.next_eligible_at > now:
        return "BACKOFF_ACTIVE"
    if run_kind == "EVENT":
        return None if checkpoint.pending_event_count > 0 else "NO_PENDING_EVENTS"
    age = now - checkpoint.last_run_at if checkpoint.last_run_at else None
    if run_kind == "DAILY":
        return None if age is None or age >= dt.timedelta(days=1) else "DAILY_NOT_DUE"
    if run_kind == "WEEKLY":
        return None if age is None or age >= dt.timedelta(days=7) else "WEEKLY_NOT_DUE"
    return "UNKNOWN_RUN_KIND"


def _insight_idempotency_key(
    checkpoint: InsightProjectionCheckpoint, run_kind: str
) -> str:
    now = now_utc()
    if run_kind == "DAILY":
        basis = f"daily:{now.date().isoformat()}"
    elif run_kind == "WEEKLY":
        iso_year, iso_week, _ = now.isocalendar()
        basis = f"weekly:{iso_year}-W{iso_week:02d}"
    else:
        basis = ":".join(
            (
                "event",
                str(checkpoint.last_cognitive_event_id or "start"),
                str(checkpoint.last_domain_event_id or "start"),
                str(checkpoint.pending_since or checkpoint.updated_at),
                str(checkpoint.pending_event_count),
                str(checkpoint.attempt_count),
            )
        )
    return f"{run_kind.lower()}:{hashlib.sha256(basis.encode('utf-8')).hexdigest()}"


@celery.task(name="nur.insights_consolidate_due_owners", ignore_result=False)
def insights_consolidate_due_owners_task(run_kind: str = "EVENT") -> dict:
    """Dispatch a bounded active-owner batch; each owner job performs its due check."""
    return run_task(lambda: _insights_consolidate_due_owners(run_kind))


async def _insights_consolidate_due_owners(run_kind: str) -> dict:
    normalized_kind = run_kind.upper()
    if normalized_kind not in {"EVENT", "DAILY", "WEEKLY"}:
        raise ValueError("Unknown scheduled Insight run kind.")
    async with get_sessionmaker()() as db:
        owners = await insight_consolidation_owner_ids(
            db, limit=get_settings().insights_owner_batch
        )
    for owner_id in owners:
        insights_consolidate_owner_task.delay(str(owner_id), normalized_kind)
    log(
        logger,
        "insight due-owner dispatch",
        owner_count=len(owners),
        run_kind=normalized_kind,
    )
    return {"count": len(owners), "run_kind": normalized_kind}


@celery.task(name="nur.account_deletion_purge", ignore_result=False, acks_late=True)
def account_deletion_purge_task() -> dict:
    """Bounded scheduled erasure pass. The scheduler payload contains no owner data."""
    return run_task(lambda: _account_deletion_purge())


async def _account_deletion_purge() -> dict:
    result = await purge_due_account_deletions()
    log(logger, "account deletion purge", **result)
    return result
