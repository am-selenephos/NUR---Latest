"""Request-scoped PostgreSQL RLS context.

Every user-scoped statement runs inside a transaction that first sets a
transaction-local (SET LOCAL semantics) parameter via set_config(..., true):

  app.current_user_id  — the authenticated user's UUID; owner-only policies key on it
  exact SECURITY DEFINER lookup functions resolve only one email, session id,
  or reset-token digest before owner context is set.

The runtime role (nur_app) is NOBYPASSRLS and does not own the tables, so these
policies are enforced by PostgreSQL itself, not by application discipline.
"""
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_SET_USER = text("SELECT set_config('app.current_user_id', :uid, true)")
_USER_ID_BY_EMAIL = text("SELECT public.fn_user_id_by_email(:value)")
_ACTIVE_USER_ID_BY_EMAIL = text("SELECT public.fn_active_user_id_by_email(:value)")
_USER_ID_BY_SESSION = text("SELECT public.fn_user_id_by_session(:value)")
_USER_ID_BY_RESET_DIGEST = text(
    "SELECT public.fn_user_id_by_password_reset_digest(:value)"
)
_ACTIVE_USER_IDS = text("SELECT owner_user_id FROM public.fn_active_user_ids(:limit)")


async def set_user_context(db: AsyncSession, user_id: uuid.UUID) -> None:
    await db.execute(_SET_USER, {"uid": str(user_id)})


async def lookup_user_id_by_email(
    db: AsyncSession, email: str, *, active_only: bool = False
) -> uuid.UUID | None:
    statement = _ACTIVE_USER_ID_BY_EMAIL if active_only else _USER_ID_BY_EMAIL
    return (await db.execute(statement, {"value": email})).scalar_one_or_none()


async def lookup_user_id_by_session(
    db: AsyncSession, session_id: uuid.UUID
) -> uuid.UUID | None:
    return (await db.execute(_USER_ID_BY_SESSION, {"value": session_id})).scalar_one_or_none()


async def lookup_user_id_by_reset_digest(
    db: AsyncSession, digest: str
) -> uuid.UUID | None:
    return (await db.execute(_USER_ID_BY_RESET_DIGEST, {"value": digest})).scalar_one_or_none()


async def bounded_active_user_ids(db: AsyncSession, *, limit: int) -> list[uuid.UUID]:
    rows = (await db.execute(_ACTIVE_USER_IDS, {"limit": min(max(limit, 1), 100)})).scalars()
    return list(rows)
