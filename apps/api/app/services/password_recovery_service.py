"""Durable password reset and authenticated password change flows."""

import datetime as dt
import logging
import uuid
from urllib.parse import urlencode

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.core.security import (
    hash_password,
    hash_password_reset_token,
    new_password_reset_token,
    opaque_fingerprint,
    verify_password,
)
from app.db.rls import (
    lookup_user_id_by_email,
    lookup_user_id_by_reset_digest,
    set_user_context,
)
from app.db.session import get_sessionmaker
from app.models import PasswordResetChallenge, Session, User
from app.models._mixins import now_utc
from app.services import audit_service
from app.services.auth_service import AuthError
from app.services.password_delivery import PasswordResetDelivery, PasswordResetDispatch

logger = logging.getLogger("nur.password_recovery")

GENERIC_INVALID_RESET = "This reset link is invalid or has expired. Request a new one."
PASSWORD_LENGTH_ERROR = "Password must be between 8 and 256 characters."


def _validate_new_password(password: str) -> None:
    if not 8 <= len(password) <= 256:
        raise AuthError(400, PASSWORD_LENGTH_ERROR)


async def request_password_reset(
    db: AsyncSession,
    *,
    email: str,
    request_ip: str,
    delivery_name: str,
) -> PasswordResetDispatch | None:
    """Create a challenge without revealing whether the email exists."""
    settings = get_settings()
    email_normalized = email.strip().lower()
    raw_token, token_digest = new_password_reset_token()
    now = now_utc()
    expires_at = now + dt.timedelta(seconds=settings.password_reset_ttl_seconds)
    dispatch = None

    async with db.begin():
        user_id = await lookup_user_id_by_email(db, email_normalized, active_only=True)
        if user_id is not None:
            await set_user_context(db, user_id)
            user = (
                await db.execute(select(User).where(User.id == user_id))
            ).scalar_one_or_none()
        else:
            user = None
        active_user = user if user and user.status == "active" else None
        if active_user:
            await db.execute(
                update(PasswordResetChallenge)
                .where(
                    PasswordResetChallenge.user_id == active_user.id,
                    PasswordResetChallenge.consumed_at.is_(None),
                    PasswordResetChallenge.revoked_at.is_(None),
                )
                .values(revoked_at=now)
            )
            challenge = PasswordResetChallenge(
                user_id=active_user.id,
                token_digest=token_digest,
                request_fingerprint=opaque_fingerprint(request_ip, purpose="password-reset-ip"),
                delivery_adapter=delivery_name,
                delivery_status="PENDING",
                expires_at=expires_at,
            )
            db.add(challenge)
            await db.flush()
            reset_url = f"{settings.password_reset_origin}/reset-password?{urlencode({'token': raw_token})}"
            dispatch = PasswordResetDispatch(
                challenge_id=challenge.id,
                user_id=active_user.id,
                recipient=active_user.email,
                reset_url=reset_url,
                expires_at_iso=expires_at.isoformat(),
            )
        await audit_service.record(
            db,
            event_type="PASSWORD_RESET_REQUESTED",
            object_type="password_reset_challenge",
            actor_user_id=active_user.id if active_user else None,
            object_id=challenge.id if active_user else None,
            metadata={"email_fp": opaque_fingerprint(email_normalized, purpose="password-reset-email")},
        )
    return dispatch


async def deliver_password_reset(
    *,
    dispatch: PasswordResetDispatch,
    delivery: PasswordResetDelivery,
) -> None:
    delivered = False
    failure_type = None
    try:
        await delivery.deliver(dispatch)
        delivered = True
    except Exception as exc:
        failure_type = type(exc).__name__
        log(
            logger,
            "password reset delivery failed",
            challenge_id=dispatch.challenge_id,
            adapter=delivery.name,
            failure_type=failure_type,
        )

    async with get_sessionmaker()() as db:
        async with db.begin():
            await set_user_context(db, dispatch.user_id)
            challenge = (
                await db.execute(
                    select(PasswordResetChallenge)
                    .where(PasswordResetChallenge.id == dispatch.challenge_id)
                    .with_for_update()
                )
            ).scalar_one_or_none()
            if challenge is None or challenge.consumed_at is not None or challenge.revoked_at is not None:
                return
            now = now_utc()
            if delivered and challenge.expires_at > now:
                challenge.delivery_status = "DELIVERED"
                challenge.delivered_at = now
                event_type = "PASSWORD_RESET_DELIVERED"
                metadata = {"adapter": delivery.name}
            else:
                challenge.delivery_status = "FAILED"
                challenge.revoked_at = now
                event_type = "PASSWORD_RESET_DELIVERY_FAILED"
                metadata = {"adapter": delivery.name, "failure_type": failure_type or "expired"}
            await audit_service.record(
                db,
                event_type=event_type,
                object_type="password_reset_challenge",
                actor_user_id=challenge.user_id,
                object_id=challenge.id,
                metadata=metadata,
            )


async def reset_password(db: AsyncSession, *, token: str, new_password: str) -> int:
    """Consume exactly one delivered challenge and revoke every old session."""
    _validate_new_password(new_password)
    if not 32 <= len(token) <= 512:
        raise AuthError(400, GENERIC_INVALID_RESET)
    digest = hash_password_reset_token(token)
    now = now_utc()
    failure = None
    revoked_sessions = 0

    async with db.begin():
        user_id = await lookup_user_id_by_reset_digest(db, digest)
        if user_id is not None:
            await set_user_context(db, user_id)
            challenge = (
                await db.execute(
                    select(PasswordResetChallenge)
                    .where(PasswordResetChallenge.token_digest == digest)
                    .with_for_update()
                )
            ).scalar_one_or_none()
        else:
            challenge = None
        if challenge is None:
            failure = "not_found"
        elif challenge.consumed_at is not None:
            failure = "replayed"
        elif challenge.revoked_at is not None:
            failure = "revoked"
        elif challenge.expires_at <= now:
            challenge.revoked_at = now
            failure = "expired"
        elif challenge.delivery_status != "DELIVERED":
            failure = "not_delivered"
        else:
            user = (
                await db.execute(select(User).where(User.id == challenge.user_id).with_for_update())
            ).scalar_one_or_none()
            if user is None or user.status != "active":
                challenge.revoked_at = now
                failure = "account_unavailable"
            elif verify_password(new_password, user.password_hash):
                failure = "password_reuse"
            else:
                user.password_hash = hash_password(new_password)
                user.updated_at = now
                challenge.consumed_at = now
                session_result = await db.execute(
                    update(Session)
                    .where(Session.user_id == user.id, Session.revoked_at.is_(None))
                    .values(revoked_at=now)
                )
                revoked_sessions = session_result.rowcount or 0
                await db.execute(
                    update(PasswordResetChallenge)
                    .where(
                        PasswordResetChallenge.user_id == user.id,
                        PasswordResetChallenge.id != challenge.id,
                        PasswordResetChallenge.consumed_at.is_(None),
                        PasswordResetChallenge.revoked_at.is_(None),
                    )
                    .values(revoked_at=now)
                )
                await audit_service.record(
                    db,
                    event_type="PASSWORD_RESET_COMPLETED",
                    object_type="password_reset_challenge",
                    actor_user_id=user.id,
                    object_id=challenge.id,
                    metadata={"revoked_session_count": revoked_sessions},
                )
        if failure:
            await audit_service.record(
                db,
                event_type="PASSWORD_RESET_REJECTED",
                object_type="password_reset_challenge",
                actor_user_id=challenge.user_id if challenge else None,
                object_id=challenge.id if challenge else None,
                metadata={"reason": failure},
            )

    if failure:
        raise AuthError(400, GENERIC_INVALID_RESET)
    return revoked_sessions


async def change_password(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    current_password: str,
    new_password: str,
) -> int:
    _validate_new_password(new_password)
    if not 1 <= len(current_password) <= 256:
        raise AuthError(400, "Current password is incorrect.")
    replacement_hash = hash_password(new_password)
    now = now_utc()
    failure = None
    revoked_sessions = 0

    async with db.begin():
        await set_user_context(db, user_id)
        user = (
            await db.execute(select(User).where(User.id == user_id).with_for_update())
        ).scalar_one_or_none()
        if user is None or user.status != "active" or not verify_password(current_password, user.password_hash if user else None):
            failure = "current_password_invalid"
        elif verify_password(new_password, user.password_hash):
            failure = "password_reuse"
        else:
            user.password_hash = replacement_hash
            user.updated_at = now
            session_result = await db.execute(
                update(Session)
                .where(Session.user_id == user_id, Session.revoked_at.is_(None))
                .values(revoked_at=now)
            )
            revoked_sessions = session_result.rowcount or 0
            await audit_service.record(
                db,
                event_type="PASSWORD_CHANGE_COMPLETED",
                object_type="user",
                actor_user_id=user_id,
                object_id=user_id,
                metadata={"revoked_session_count": revoked_sessions},
            )
        if failure:
            await audit_service.record(
                db,
                event_type="PASSWORD_CHANGE_REJECTED",
                object_type="user",
                actor_user_id=user_id,
                object_id=user_id,
                metadata={"reason": failure},
            )

    if failure == "password_reuse":
        raise AuthError(400, "Choose a password you have not just used.")
    if failure:
        raise AuthError(400, "Current password is incorrect.")
    return revoked_sessions
