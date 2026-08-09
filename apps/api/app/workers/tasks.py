"""Phase 0 worker spine: idempotent, ID-only payloads, structured logs.
Workers never execute user-supplied code and never receive private raw text."""
import logging
import socket
import uuid

from app.core.logging import configure_logging, log
from app.db.rls import set_user_context
from app.db.session import get_sessionmaker
from app.workers.asyncrun import run_task
from app.omega.due_owner_service import omega_consolidation_due_owner_ids
from app.omega.replay_service import omega_consolidate_owner
from app.services.project_execution import execute_run
from app.services.account_service import purge_due_account_deletions
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


@celery.task(name="nur.account_deletion_purge", ignore_result=False, acks_late=True)
def account_deletion_purge_task() -> dict:
    """Bounded scheduled erasure pass. The scheduler payload contains no owner data."""
    return run_task(lambda: _account_deletion_purge())


async def _account_deletion_purge() -> dict:
    result = await purge_due_account_deletions()
    log(logger, "account deletion purge", **result)
    return result
