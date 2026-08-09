"""Auth flows. Every function manages exactly one transaction and sets the
appropriate PostgreSQL RLS context as its first statement (see app/db/rls.py)."""
import datetime as dt
import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import log
from app.core.security import (
    email_fingerprint,
    hash_password,
    new_session_token,
    secret_matches,
    split_session_cookie,
    verify_password,
)
from app.db.rls import set_auth_context, set_user_context
from app.models import ConsentRecord, Orbit, Profile, Session, User
from app.services import audit_service

logger = logging.getLogger("nur.auth")

GENERIC_LOGIN_FAIL = "Invalid credentials."
GENERIC_REGISTER_FAIL = "Could not create an Orbit with those details."
CONSENT_POLICY_VERSION = "constitution-v5"

CORE_SYSTEMS: tuple[tuple[str, str, str], ...] = (
    ("Ambition", "CREATIVE", "Build meaningful work without abandoning quiet."),
    ("Rebuild", "CARE", "Recover capacity and rebuild from what is real."),
    ("Creation", "CREATIVE", "Move imagination into finished form."),
    ("Growth", "PROJECT", "Compound capability with evidence, not effort alone."),
    ("Introspection", "CARE", "Keep honest awareness of state inside every decision."),
    ("Connection", "CARE", "Hold relationships without losing the self."),
)


class AuthError(Exception):
    def __init__(self, status_code: int, detail: str):
        self.status_code = status_code
        self.detail = detail


def _normalize_email(email: str) -> str:
    return email.strip().lower()


def _expiry() -> dt.datetime:
    return dt.datetime.now(dt.UTC) + dt.timedelta(seconds=get_settings().session_ttl_seconds)


async def register(db: AsyncSession, *, chosen_name: str, email: str, password: str, consent: bool):
    """Creates user + profile + orbit + consent record + session, all audited.
    Returns (user, profile, orbit, session_cookie_value)."""
    if not consent:
        raise AuthError(400, "Consent is required to create an Orbit.")
    email_n = _normalize_email(email)
    try:
        async with db.begin():
            await set_auth_context(db)
            user = User(email=email_n, password_hash=hash_password(password))
            db.add(user)
            await db.flush()  # user.id

            profile = Profile(user_id=user.id, chosen_name=chosen_name.strip())
            orbit = Orbit(owner_user_id=user.id, title="Personal Orbit", kind="PERSONAL_BRIDGE")
            systems = [
                Orbit(owner_user_id=user.id, title=title, kind=kind, description=description)
                for title, kind, description in CORE_SYSTEMS
            ]
            consent_row = ConsentRecord(
                user_id=user.id,
                consent_type="privacy.default_private",
                granted=True,
                policy_version=CONSENT_POLICY_VERSION,
            )
            db.add_all([profile, orbit, *systems, consent_row])
            await db.flush()

            sid, cookie_value, secret_hash = new_session_token()
            db.add(Session(id=sid, user_id=user.id, session_secret_hash=secret_hash, expires_at=_expiry()))

            await audit_service.record(db, event_type="user.registered", object_type="user",
                                       actor_user_id=user.id, object_id=user.id,
                                       metadata={"email_fp": email_fingerprint(email_n)})
            await audit_service.record(db, event_type="consent.granted", object_type="consent_record",
                                       actor_user_id=user.id, object_id=consent_row.id,
                                       metadata={"consent_type": consent_row.consent_type,
                                                 "policy_version": CONSENT_POLICY_VERSION})
            await audit_service.record(db, event_type="session.created", object_type="session",
                                       actor_user_id=user.id, object_id=sid, metadata={"via": "register"})
    except IntegrityError:
        # duplicate email — same generic message as any other failure (no enumeration)
        log(logger, "registration failed", reason="integrity", email_fp=email_fingerprint(email_n))
        raise AuthError(400, GENERIC_REGISTER_FAIL)
    return user, profile, orbit, cookie_value


async def login(db: AsyncSession, *, email: str, password: str):
    """Returns (user_id, session_cookie_value) or raises AuthError(401, generic)."""
    email_n = _normalize_email(email)
    async with db.begin():
        await set_auth_context(db)
        user = (await db.execute(select(User).where(User.email == email_n))).scalar_one_or_none()
    ok = verify_password(password, user.password_hash if user else None)
    if not user or not ok or user.status != "active":
        # audit in its OWN transaction so the failure record survives the raise
        async with db.begin():
            await set_auth_context(db)
            await audit_service.record(db, event_type="auth.login_failed", object_type="user",
                                       metadata={"email_fp": email_fingerprint(email_n)})
        raise AuthError(401, GENERIC_LOGIN_FAIL)
    async with db.begin():
        await set_auth_context(db)
        sid, cookie_value, secret_hash = new_session_token()
        db.add(Session(id=sid, user_id=user.id, session_secret_hash=secret_hash, expires_at=_expiry()))
        await audit_service.record(db, event_type="session.created", object_type="session",
                                   actor_user_id=user.id, object_id=sid, metadata={"via": "login"})
    return user.id, cookie_value


async def resolve_session(db: AsyncSession, cookie_value: str | None) -> tuple[uuid.UUID, uuid.UUID] | None:
    """Validates the session cookie. Returns (user_id, session_id) or None."""
    if not cookie_value:
        return None
    parsed = split_session_cookie(cookie_value)
    if not parsed:
        return None
    sid, secret = parsed
    async with db.begin():
        await set_auth_context(db)
        resolved = (
            await db.execute(
                select(Session, User.status)
                .join(User, User.id == Session.user_id)
                .where(Session.id == sid)
            )
        ).one_or_none()
    if not resolved:
        return None
    row, user_status = resolved
    if user_status != "active" or row.revoked_at is not None:
        return None
    if row.expires_at <= dt.datetime.now(dt.UTC):
        return None
    if not secret_matches(secret, row.session_secret_hash):
        return None
    return row.user_id, row.id


async def revoke_session(db: AsyncSession, *, session_id: uuid.UUID, user_id: uuid.UUID) -> None:
    """Revokes ONE session belonging to ONE user.

    Constrained by BOTH session_id AND user_id at the query level: even if a
    future caller mistakenly passes a foreign session id, this function cannot
    revoke another user's session (regression-tested in test_rls.py)."""
    async with db.begin():
        await set_auth_context(db)
        row = (await db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user_id)
        )).scalar_one_or_none()
        if row and row.revoked_at is None:
            row.revoked_at = dt.datetime.now(dt.UTC)
            await audit_service.record(db, event_type="session.revoked", object_type="session",
                                       actor_user_id=user_id, object_id=session_id, metadata={"via": "logout"})


async def get_me(db: AsyncSession, user_id: uuid.UUID):
    """Owner-context read: RLS restricts every row to the authenticated user."""
    async with db.begin():
        await set_user_context(db, user_id)
        user = (await db.execute(select(User).where(User.id == user_id))).scalar_one_or_none()
        profile = (await db.execute(select(Profile).where(Profile.user_id == user_id))).scalar_one_or_none()
        orbit = (await db.execute(select(Orbit).where(Orbit.owner_user_id == user_id, Orbit.kind == 'PERSONAL_BRIDGE'))).scalar_one_or_none()
    if not user or not profile or not orbit:
        return None
    return user, profile, orbit
