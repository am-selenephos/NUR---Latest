"""Owner-controlled export, session inventory, and durable account erasure."""

from __future__ import annotations

import base64
import datetime as dt
import decimal
import hashlib
import json
import uuid
from collections import defaultdict
from typing import Any

from sqlalchemy import delete, or_, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    email_fingerprint,
    hash_account_deletion_receipt_token,
    hash_session_secret,
    new_account_deletion_receipt_token,
    opaque_fingerprint,
    verify_password,
)
from app.db.rls import set_auth_context, set_user_context
from app.db.session import get_sessionmaker
from app.models import (
    AccountCleanupItem,
    AccountDeletionRequest,
    Session,
    User,
)
from app.models._mixins import now_utc
from app.models.billing import BillingCustomer, BillingSubscription
from app.models.projects import AMProjectFile, AMProjectRun
from app.services import audit_service
from app.services.auth_service import AuthError
from app.services.object_storage import StoredObjectMissing, get_object_storage

EXPORT_SCHEMA = "https://nur.app/schemas/owner-export-manifest/v1"
EXPORT_VERSION = "1.0.0"
DELETE_CONFIRMATION = "DELETE MY NUR ACCOUNT"
CANCEL_CONFIRMATION = "CANCEL ACCOUNT DELETION"

_SENSITIVE_COLUMNS = {
    "users": {"password_hash"},
    "sessions": {"session_secret_hash"},
    "password_reset_challenges": {"token_digest", "request_fingerprint"},
    "account_deletion_requests": {"receipt_token_digest", "claim_token"},
    "account_cleanup_items": {"resource_ref"},
}

_CAPSULE_LINKED = {
    "capsule_access_events",
    "capsule_grants",
    "capsule_questions",
    "capsule_sources",
}


def _portable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        if value != value or value in (float("inf"), float("-inf")):
            return str(value)
        return value
    if isinstance(value, decimal.Decimal):
        return format(value, "f")
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, (dt.datetime, dt.date, dt.time)):
        return value.isoformat()
    if isinstance(value, bytes):
        return {"encoding": "hex", "value": value.hex()}
    if isinstance(value, dict):
        return {
            str(key): _portable(item)
            for key, item in sorted(value.items(), key=lambda pair: str(pair[0]))
        }
    if isinstance(value, (list, tuple)):
        return [_portable(item) for item in value]
    return str(value)


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        _portable(value),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


async def _schema_columns(db: AsyncSession) -> dict[str, list[str]]:
    rows = (
        await db.execute(
            text(
                "SELECT table_name, column_name FROM information_schema.columns "
                "WHERE table_schema='public' ORDER BY table_name, ordinal_position"
            )
        )
    ).all()
    columns: dict[str, list[str]] = defaultdict(list)
    for table_name, column_name in rows:
        columns[table_name].append(column_name)
    return dict(columns)


def _ownership_basis(table_name: str, columns: set[str]) -> tuple[str, str] | None:
    if table_name == "users":
        return "id", "account"
    if table_name in _CAPSULE_LINKED or table_name == "capsule_answers":
        return "capsule", "owned_capsule"
    if "owner_user_id" in columns:
        return "owner_user_id", "owner"
    if "user_id" in columns:
        return "user_id", "user"
    return None


def _quoted(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def _owner_where(table_name: str, key: str) -> str:
    if key != "capsule":
        return f"{_quoted(key)} = :owner"
    if table_name == "capsule_answers":
        return (
            '"question_id" IN (SELECT q.id FROM capsule_questions q '
            "JOIN context_capsules c ON c.id=q.capsule_id "
            "WHERE c.owner_user_id=:owner)"
        )
    return (
        '"capsule_id" IN (SELECT id FROM context_capsules '
        "WHERE owner_user_id=:owner)"
    )


async def build_owner_export(db: AsyncSession, *, owner_user_id: uuid.UUID) -> dict[str, Any]:
    """Build deterministic owner data without mutating export-time state."""
    schema = await _schema_columns(db)
    exported_tables: list[dict[str, Any]] = []
    object_rows: list[dict[str, Any]] = []
    total_rows = 0

    for table_name in sorted(schema):
        available = set(schema[table_name])
        basis = _ownership_basis(table_name, available)
        if basis is None:
            continue
        key, basis_label = basis
        included_columns = [
            name
            for name in schema[table_name]
            if name not in _SENSITIVE_COLUMNS.get(table_name, set())
        ]
        projection = ", ".join(_quoted(name) for name in included_columns)
        statement = text(
            f"SELECT {projection} FROM {_quoted(table_name)} "
            f"WHERE {_owner_where(table_name, key)}"
        )
        rows = [
            {name: _portable(row[name]) for name in included_columns}
            for row in (await db.execute(statement, {"owner": owner_user_id})).mappings()
        ]
        rows.sort(key=canonical_json_bytes)
        if table_name == "am_project_files":
            object_fields = (
                "id",
                "project_id",
                "object_key",
                "original_filename",
                "safe_filename",
                "media_type",
                "byte_size",
                "checksum_sha256",
                "storage_backend",
                "storage_state",
                "scan_state",
                "provenance",
                "created_at",
                "updated_at",
            )
            object_rows = [
                {field: row.get(field) for field in object_fields} for row in rows
            ]
        total_rows += len(rows)
        exported_tables.append(
            {
                "name": table_name,
                "ownership_basis": basis_label,
                "row_count": len(rows),
                "rows": rows,
            }
        )

    object_rows.sort(key=canonical_json_bytes)
    storage = get_object_storage()
    included_object_count = 0
    unavailable_object_count = 0
    for row in object_rows:
        if row.get("storage_backend") != "local":
            row["content"] = {
                "status": "external_backend_not_connected",
                "encoding": None,
                "value": None,
            }
            unavailable_object_count += 1
            continue
        try:
            payload_bytes = storage.read_bytes(str(row["object_key"]))
        except (StoredObjectMissing, OSError, ValueError):
            row["content"] = {
                "status": "missing_local_object",
                "encoding": None,
                "value": None,
            }
            unavailable_object_count += 1
            continue
        actual_checksum = hashlib.sha256(payload_bytes).hexdigest()
        row["content"] = {
            "status": (
                "included_verified"
                if actual_checksum == row.get("checksum_sha256")
                else "included_integrity_mismatch"
            ),
            "encoding": "base64",
            "value": base64.b64encode(payload_bytes).decode("ascii"),
            "checksum_sha256": actual_checksum,
        }
        included_object_count += 1

    payload: dict[str, Any] = {
        "schema": EXPORT_SCHEMA,
        "version": EXPORT_VERSION,
        "owner_user_id": str(owner_user_id),
        "provenance": {
            "source": "NUR PostgreSQL owner-scoped API",
            "scope": "forced RLS plus explicit owner predicates",
            "canonicalization": "NUR canonical JSON v1: UTF-8, sorted keys, compact separators",
            "object_bytes_included": unavailable_object_count == 0,
            "object_metadata_included": True,
            "object_bytes_boundary": (
                "Local object bytes are embedded as base64. A non-local or missing "
                "object is identified explicitly and never represented as exported."
            ),
            "excluded_secret_fields": sorted(
                f"{table}.{column}"
                for table, columns in _SENSITIVE_COLUMNS.items()
                for column in columns
            ),
            "shared_global_catalogs_included": False,
            "platform_audit_rows_included": False,
            "platform_audit_boundary": (
                "audit_events remain append-only and unreadable to the runtime role"
            ),
        },
        "summary": {
            "table_count": len(exported_tables),
            "row_count": total_rows,
            "object_count": len(object_rows),
            "object_bytes_included_count": included_object_count,
            "object_bytes_unavailable_count": unavailable_object_count,
        },
        "tables": exported_tables,
        "objects": object_rows,
    }
    payload["checksum"] = {
        "algorithm": "sha256",
        "covers": "entire manifest excluding checksum",
        "value": hashlib.sha256(canonical_json_bytes(payload)).hexdigest(),
    }
    return payload


def _session_state(row: Session, now: dt.datetime) -> str:
    if row.revoked_at is not None:
        return "revoked"
    if row.expires_at <= now:
        return "expired"
    return "active"


async def session_inventory(
    db: AsyncSession, *, owner_user_id: uuid.UUID, current_session_id: uuid.UUID
) -> list[dict[str, Any]]:
    rows = (
        await db.execute(
            select(Session)
            .where(Session.user_id == owner_user_id)
            .order_by(Session.created_at.desc(), Session.id)
        )
    ).scalars().all()
    now = now_utc()
    return [
        {
            "id": row.id,
            "created_at": row.created_at,
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "current": row.id == current_session_id,
            "state": _session_state(row, now),
        }
        for row in rows
    ]


async def revoke_other_sessions(
    db: AsyncSession, *, owner_user_id: uuid.UUID, current_session_id: uuid.UUID
) -> int:
    result = await db.execute(
        update(Session)
        .where(
            Session.user_id == owner_user_id,
            Session.id != current_session_id,
            Session.revoked_at.is_(None),
        )
        .values(revoked_at=now_utc())
    )
    count = result.rowcount or 0
    await audit_service.record(
        db,
        event_type="SESSIONS_REVOKED",
        object_type="session",
        actor_user_id=owner_user_id,
        metadata={"scope": "other", "revoked_session_count": count},
    )
    await db.commit()
    return count


async def revoke_owned_session(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    current_session_id: uuid.UUID,
    target_session_id: uuid.UUID,
) -> bool:
    if target_session_id == current_session_id:
        raise AuthError(400, "Use logout to revoke the current session.")
    row = (
        await db.execute(
            select(Session).where(
                Session.id == target_session_id,
                Session.user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if row is None or row.revoked_at is not None:
        return False
    row.revoked_at = now_utc()
    await audit_service.record(
        db,
        event_type="SESSION_REVOKED",
        object_type="session",
        actor_user_id=owner_user_id,
        object_id=target_session_id,
        metadata={"via": "session_inventory"},
    )
    await db.commit()
    return True


def _cleanup_ref_hash(kind: str, value: str) -> str:
    return hash_session_secret(f"account-cleanup:{kind}:{value}")


async def request_account_deletion(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    password: str,
    confirmation: str,
) -> dict[str, Any]:
    if confirmation != DELETE_CONFIRMATION:
        raise AuthError(400, f'Type "{DELETE_CONFIRMATION}" to confirm account deletion.')
    if not 1 <= len(password) <= 256:
        raise AuthError(400, "Password is incorrect.")

    user = (
        await db.execute(select(User).where(User.id == owner_user_id).with_for_update())
    ).scalar_one_or_none()
    if user is None or user.status != "active" or not verify_password(password, user.password_hash):
        await audit_service.record(
            db,
            event_type="ACCOUNT_DELETION_REJECTED",
            object_type="user",
            actor_user_id=owner_user_id if user else None,
            metadata={"reason": "reauthentication_failed"},
        )
        await db.commit()
        raise AuthError(400, "Password is incorrect.")

    request_id = uuid.uuid4()
    receipt_token, receipt_digest = new_account_deletion_receipt_token()
    now = now_utc()
    purge_after = now + dt.timedelta(hours=get_settings().account_deletion_grace_hours)
    row = AccountDeletionRequest(
        id=request_id,
        owner_user_id=owner_user_id,
        account_ref=opaque_fingerprint(
            f"{owner_user_id}:{request_id}", purpose="account-deletion"
        ),
        receipt_token_digest=receipt_digest,
        status="PENDING",
        requested_at=now,
        purge_after=purge_after,
    )
    db.add(row)
    await db.flush()

    cleanup_rows: list[AccountCleanupItem] = []
    seen: set[tuple[str, str]] = set()

    files = (
        await db.execute(
            select(AMProjectFile.object_key, AMProjectFile.storage_backend).where(
                AMProjectFile.owner_user_id == owner_user_id
            )
        )
    ).all()
    for object_key, storage_backend in files:
        kind = "LOCAL_OBJECT" if storage_backend == "local" else "EXTERNAL_OBJECT"
        ref = str(object_key)
        if (kind, ref) in seen:
            continue
        seen.add((kind, ref))
        cleanup_rows.append(
            AccountCleanupItem(
                deletion_request_id=request_id,
                owner_user_id=owner_user_id,
                cleanup_kind=kind,
                provider=str(storage_backend),
                resource_ref=ref,
                resource_ref_hash=_cleanup_ref_hash(kind, ref),
            )
        )

    customers = (
        await db.execute(
            select(BillingCustomer.provider, BillingCustomer.provider_customer_id).where(
                BillingCustomer.owner_user_id == owner_user_id
            )
        )
    ).all()
    for provider, customer_id in customers:
        kind = "EXTERNAL_BILLING_CUSTOMER"
        ref = str(customer_id)
        if (kind, ref) in seen:
            continue
        seen.add((kind, ref))
        cleanup_rows.append(
            AccountCleanupItem(
                deletion_request_id=request_id,
                owner_user_id=owner_user_id,
                cleanup_kind=kind,
                provider=str(provider),
                resource_ref=ref,
                resource_ref_hash=_cleanup_ref_hash(kind, ref),
            )
        )

    subscriptions = (
        await db.execute(
            select(
                BillingSubscription.provider,
                BillingSubscription.provider_subscription_id,
            ).where(BillingSubscription.owner_user_id == owner_user_id)
        )
    ).all()
    for provider, subscription_id in subscriptions:
        kind = "EXTERNAL_BILLING_SUBSCRIPTION"
        ref = str(subscription_id)
        if (kind, ref) in seen:
            continue
        seen.add((kind, ref))
        cleanup_rows.append(
            AccountCleanupItem(
                deletion_request_id=request_id,
                owner_user_id=owner_user_id,
                cleanup_kind=kind,
                provider=str(provider),
                resource_ref=ref,
                resource_ref_hash=_cleanup_ref_hash(kind, ref),
            )
        )
    db.add_all(cleanup_rows)

    # Disable every owner-controlled execution surface before access and
    # sessions are revoked. Agent cancellation also invalidates approvals,
    # fences execution tokens, and cancels unsent outbox rows atomically.
    from app.agentic.lifecycle_service import cancel_owner_workflows_for_deletion

    cancelled_agent_workflows = await cancel_owner_workflows_for_deletion(
        db, owner_user_id=owner_user_id
    )
    project_runs = await db.execute(
        update(AMProjectRun)
        .where(
            AMProjectRun.owner_user_id == owner_user_id,
            AMProjectRun.status.in_(
                ["PROPOSED", "APPROVED", "QUEUED", "RUNNING", "CANCEL_REQUESTED"]
            ),
        )
        .values(
            status=text(
                "CASE WHEN status = 'RUNNING' THEN 'CANCEL_REQUESTED' "
                "ELSE 'CANCELLED' END"
            ),
            cancelled_at=text(
                "CASE WHEN status = 'RUNNING' THEN cancelled_at ELSE now() END"
            ),
            updated_at=now,
        )
    )

    revoked = await db.execute(
        update(Session)
        .where(Session.user_id == owner_user_id, Session.revoked_at.is_(None))
        .values(revoked_at=now)
    )
    user.status = "deletion_pending"
    user.updated_at = now
    await audit_service.record(
        db,
        event_type="ACCOUNT_DELETION_REQUESTED",
        object_type="account_deletion_request",
        actor_user_id=owner_user_id,
        object_id=request_id,
        metadata={
            "account_ref": row.account_ref,
            "purge_after": purge_after.isoformat(),
            "revoked_session_count": revoked.rowcount or 0,
            "cleanup_item_count": len(cleanup_rows),
            "cancelled_agent_workflow_count": cancelled_agent_workflows,
            "cancelled_or_stopping_project_run_count": project_runs.rowcount or 0,
        },
    )
    await db.commit()
    return {
        "request_id": request_id,
        "status": "PENDING",
        "requested_at": now,
        "purge_after": purge_after,
        "immediate_access_shutdown": True,
        "receipt_token": receipt_token,
    }


async def cancel_account_deletion(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    confirmation: str,
) -> dict[str, Any]:
    generic = "Could not cancel account deletion with those details."
    if confirmation != CANCEL_CONFIRMATION or not 1 <= len(password) <= 256:
        raise AuthError(400, generic)

    normalized_email = email.strip().lower()
    await set_auth_context(db)
    user = (
        await db.execute(
            select(User).where(User.email == normalized_email)
        )
    ).scalar_one_or_none()
    password_ok = verify_password(password, user.password_hash if user else None)
    if user is None or not password_ok or user.status != "deletion_pending":
        await audit_service.record(
            db,
            event_type="ACCOUNT_DELETION_CANCEL_REJECTED",
            object_type="account_deletion_request",
            metadata={"email_fp": email_fingerprint(normalized_email)},
        )
        await db.commit()
        raise AuthError(400, generic)

    owner_user_id = user.id
    await set_user_context(db, owner_user_id)
    user = (
        await db.execute(
            select(User).where(User.id == owner_user_id).with_for_update()
        )
    ).scalar_one_or_none()
    if (
        user is None
        or user.status != "deletion_pending"
        or not verify_password(password, user.password_hash)
    ):
        await db.rollback()
        raise AuthError(400, generic)
    request_row = (
        await db.execute(
            select(AccountDeletionRequest)
            .where(
                AccountDeletionRequest.owner_user_id == user.id,
                AccountDeletionRequest.status == "PENDING",
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if request_row is None or request_row.purge_after <= now_utc():
        await db.rollback()
        raise AuthError(409, "Account deletion has already entered irreversible purge.")

    now = now_utc()
    request_row.status = "CANCELLED"
    request_row.cancelled_at = now
    request_row.lease_expires_at = None
    request_row.claim_token = None
    request_row.failure_code = None
    request_row.updated_at = now
    user.status = "active"
    user.updated_at = now
    await db.execute(
        update(AccountCleanupItem)
        .where(
            AccountCleanupItem.deletion_request_id == request_row.id,
            AccountCleanupItem.owner_user_id == user.id,
        )
        .values(
            status="CANCELLED",
            resource_ref=None,
            completed_at=now,
            updated_at=now,
        )
    )
    await audit_service.record(
        db,
        event_type="ACCOUNT_DELETION_CANCELLED",
        object_type="account_deletion_request",
        actor_user_id=user.id,
        object_id=request_row.id,
        metadata={"account_ref": request_row.account_ref},
    )
    await db.commit()
    return {"cancelled": True, "status": "CANCELLED", "login_required": True}


async def deletion_receipt(
    db: AsyncSession, *, request_id: uuid.UUID, receipt_token: str
) -> dict[str, Any] | None:
    digest = hash_account_deletion_receipt_token(receipt_token)
    row = (
        await db.execute(
            text(
                "SELECT * FROM fn_account_deletion_receipt("
                ":request_id, CAST(:digest AS varchar))"
            ),
            {"request_id": request_id, "digest": digest},
        )
    ).mappings().one_or_none()
    return dict(row) if row else None


def _cleanup_summary(items: list[AccountCleanupItem], *, database_status: str) -> dict[str, Any]:
    local = [item for item in items if item.cleanup_kind == "LOCAL_OBJECT"]
    external_objects = [item for item in items if item.cleanup_kind == "EXTERNAL_OBJECT"]
    external_billing = [
        item for item in items if item.cleanup_kind.startswith("EXTERNAL_BILLING_")
    ]

    def counts(rows: list[AccountCleanupItem]) -> dict[str, int]:
        return {
            "total": len(rows),
            "done": sum(item.status == "DONE" for item in rows),
            "blocked": sum(item.status == "BLOCKED" for item in rows),
            "failed": sum(item.status == "FAILED" for item in rows),
        }

    external_required = any(
        item.status == "BLOCKED" for item in (*external_objects, *external_billing)
    )
    return {
        "local_objects": counts(local),
        "external_objects": counts(external_objects),
        "external_billing": counts(external_billing),
        "internal_database": {"status": database_status},
        "external_action_required": external_required,
    }


async def _due_owner_ids(*, limit: int) -> list[uuid.UUID]:
    async with get_sessionmaker()() as db:
        rows = (
            await db.execute(
                text("SELECT owner_user_id FROM fn_due_account_deletion_owners(:limit)"),
                {"limit": min(max(limit, 1), 100)},
            )
        ).scalars().all()
    return list(rows)


async def _claim_deletion(
    db: AsyncSession, *, owner_user_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID] | None:
    await set_user_context(db, owner_user_id)
    now = now_utc()
    row = (
        await db.execute(
            select(AccountDeletionRequest)
            .where(
                AccountDeletionRequest.owner_user_id == owner_user_id,
                AccountDeletionRequest.purge_after <= now,
                or_(
                    AccountDeletionRequest.status == "PENDING",
                    (
                        (AccountDeletionRequest.status == "PURGING")
                        & (AccountDeletionRequest.lease_expires_at.is_not(None))
                        & (AccountDeletionRequest.lease_expires_at <= now)
                    ),
                ),
            )
            .with_for_update(skip_locked=True)
        )
    ).scalar_one_or_none()
    if row is None:
        await db.rollback()
        return None
    token = uuid.uuid4()
    row.status = "PURGING"
    row.claim_token = token
    row.purge_started_at = row.purge_started_at or now
    row.lease_expires_at = now + dt.timedelta(
        seconds=get_settings().account_deletion_lease_seconds
    )
    row.attempt_count += 1
    row.failure_code = None
    row.updated_at = now
    await db.commit()
    return row.id, token


async def _release_retryable_failure(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    request_id: uuid.UUID,
    claim_token: uuid.UUID,
    failure_code: str,
    summary: dict[str, Any],
) -> None:
    await db.rollback()
    await set_user_context(db, owner_user_id)
    row = (
        await db.execute(
            select(AccountDeletionRequest)
            .where(
                AccountDeletionRequest.id == request_id,
                AccountDeletionRequest.owner_user_id == owner_user_id,
                AccountDeletionRequest.status == "PURGING",
                AccountDeletionRequest.claim_token == claim_token,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    if row is None:
        await db.rollback()
        return
    backoff_minutes = min(2 ** min(row.attempt_count, 6), 60)
    now = now_utc()
    row.status = "PENDING"
    row.purge_after = now + dt.timedelta(minutes=backoff_minutes)
    row.lease_expires_at = None
    row.claim_token = None
    row.failure_code = failure_code
    row.cleanup_summary = summary
    row.updated_at = now
    await db.commit()


async def _purge_one(owner_user_id: uuid.UUID) -> str:
    async with get_sessionmaker()() as db:
        claim = await _claim_deletion(db, owner_user_id=owner_user_id)
        if claim is None:
            return "noop"
        request_id, claim_token = claim

        await set_user_context(db, owner_user_id)
        request_row = (
            await db.execute(
                select(AccountDeletionRequest).where(
                    AccountDeletionRequest.id == request_id,
                    AccountDeletionRequest.owner_user_id == owner_user_id,
                    AccountDeletionRequest.status == "PURGING",
                    AccountDeletionRequest.claim_token == claim_token,
                )
            )
        ).scalar_one_or_none()
        if request_row is None:
            await db.rollback()
            return "noop"
        items = list(
            (
                await db.execute(
                    select(AccountCleanupItem)
                    .where(
                        AccountCleanupItem.deletion_request_id == request_id,
                        AccountCleanupItem.owner_user_id == owner_user_id,
                    )
                    .order_by(AccountCleanupItem.created_at, AccountCleanupItem.id)
                )
            ).scalars().all()
        )
        storage = get_object_storage()
        now = now_utc()
        for item in items:
            if item.status in {"DONE", "CANCELLED"}:
                continue
            item.attempt_count += 1
            item.updated_at = now
            if item.cleanup_kind == "LOCAL_OBJECT":
                try:
                    existed = bool(item.resource_ref and storage.exists(item.resource_ref))
                    removed = bool(item.resource_ref and storage.delete(item.resource_ref))
                except (OSError, ValueError):
                    existed = True
                    removed = False
                if removed or not existed:
                    item.status = "DONE"
                    item.last_error_code = None
                    item.completed_at = now
                    item.resource_ref = None
                else:
                    item.status = "FAILED"
                    item.last_error_code = "local_object_cleanup_failed"
            elif item.cleanup_kind == "EXTERNAL_OBJECT":
                item.status = "BLOCKED"
                item.last_error_code = "external_object_adapter_not_connected"
            elif item.provider in {None, "disabled", "test"}:
                item.status = "DONE"
                item.last_error_code = None
                item.completed_at = now
                item.resource_ref = None
            else:
                item.status = "BLOCKED"
                item.last_error_code = "provider_erasure_adapter_not_connected"

        summary = _cleanup_summary(items, database_status="pending")
        if any(
            item.cleanup_kind == "LOCAL_OBJECT" and item.status == "FAILED"
            for item in items
        ):
            await db.flush()
            await db.commit()
            await _release_retryable_failure(
                db,
                owner_user_id=owner_user_id,
                request_id=request_id,
                claim_token=claim_token,
                failure_code="local_object_cleanup_failed",
                summary=summary,
            )
            return "failed_retryable"
        await db.commit()

        await set_user_context(db, owner_user_id)
        request_row = (
            await db.execute(
                select(AccountDeletionRequest)
                .where(
                    AccountDeletionRequest.id == request_id,
                    AccountDeletionRequest.owner_user_id == owner_user_id,
                    AccountDeletionRequest.status == "PURGING",
                    AccountDeletionRequest.claim_token == claim_token,
                )
                .with_for_update()
            )
        ).scalar_one_or_none()
        user = (
            await db.execute(select(User).where(User.id == owner_user_id).with_for_update())
        ).scalar_one_or_none()
        if request_row is None or user is None or user.status != "deletion_pending":
            await db.rollback()
            return "noop"
        items = list(
            (
                await db.execute(
                    select(AccountCleanupItem).where(
                        AccountCleanupItem.deletion_request_id == request_id,
                        AccountCleanupItem.owner_user_id == owner_user_id,
                    )
                )
            ).scalars().all()
        )
        external_required = any(item.status == "BLOCKED" for item in items)
        final_status = (
            "PURGED_EXTERNAL_ACTION_REQUIRED" if external_required else "PURGED"
        )
        summary = _cleanup_summary(items, database_status="purged")
        finished_at = now_utc()
        request_row.status = final_status
        request_row.purged_at = finished_at
        request_row.lease_expires_at = None
        request_row.claim_token = None
        request_row.failure_code = None
        request_row.cleanup_summary = summary
        request_row.updated_at = finished_at
        await audit_service.record(
            db,
            event_type="ACCOUNT_PURGED",
            object_type="account_tombstone",
            actor_user_id=owner_user_id,
            metadata={
                "account_ref": request_row.account_ref,
                "status": final_status,
                "cleanup_summary": summary,
            },
        )
        deleted = await db.execute(delete(User).where(User.id == owner_user_id))
        if deleted.rowcount != 1:
            await _release_retryable_failure(
                db,
                owner_user_id=owner_user_id,
                request_id=request_id,
                claim_token=claim_token,
                failure_code="database_purge_failed",
                summary=summary,
            )
            return "failed_retryable"
        await db.commit()
        return (
            "purged_external_action_required" if external_required else "purged"
        )


async def purge_due_account_deletions(*, limit: int | None = None) -> dict[str, int]:
    """Run one bounded, idempotent scheduler pass using owner IDs only."""
    batch = limit or get_settings().account_deletion_purge_batch
    owners = await _due_owner_ids(limit=batch)
    counts = {
        "processed": 0,
        "purged": 0,
        "purged_external_action_required": 0,
        "failed_retryable": 0,
        "noop": 0,
    }
    for owner_id in owners:
        outcome = await _purge_one(owner_id)
        counts["processed"] += 1
        counts[outcome] += 1
    return counts
