import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import (
    BOOTSTRAP_CSRF_TTL_SECONDS,
    bootstrap_csrf_matches,
    csrf_matches,
    csrf_token_for,
    new_bootstrap_csrf_token,
)
from app.db.session import get_sessionmaker
from app.db.rls import set_user_context
from app.services import auth_service


async def get_db() -> AsyncSession:
    async with get_sessionmaker()() as session:
        yield session


DB = Annotated[AsyncSession, Depends(get_db)]


async def get_current_identity(request: Request, db: DB) -> tuple[uuid.UUID, uuid.UUID]:
    """(user_id, session_id) from the HTTP-only session cookie, else 401."""
    s = get_settings()
    resolved = await auth_service.resolve_session(db, request.cookies.get(s.session_cookie_name))
    if not resolved:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    return resolved


Identity = Annotated[tuple[uuid.UUID, uuid.UUID], Depends(get_current_identity)]


async def require_trusted_origin(request: Request) -> None:
    """Reject browser cross-site writes before they reach auth services.

    Non-browser clients omit Origin. They remain usable in development, while
    production requires an explicit configured origin for recovery writes.
    """
    settings = get_settings()
    origin = request.headers.get("origin")
    fetch_site = request.headers.get("sec-fetch-site", "").lower()
    if fetch_site == "cross-site":
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")
    if origin is None:
        if settings.app_env == "production":
            raise HTTPException(status_code=403, detail="Request origin is required.")
        return
    if origin.rstrip("/") not in settings.cors_origins:
        raise HTTPException(status_code=403, detail="Request origin is not allowed.")


TrustedOrigin = Annotated[None, Depends(require_trusted_origin)]


async def require_csrf(
    request: Request,
    identity: Identity,
    _trusted_origin: TrustedOrigin,
) -> None:
    """Require trusted origin and a session-bound signed double-submit token."""
    _, session_id = identity
    if not csrf_matches(request.headers.get("x-csrf-token"), csrf_token_for(session_id)):
        raise HTTPException(status_code=403, detail="CSRF token missing or invalid.")


async def require_public_browser_csrf(
    request: Request,
    _trusted_origin: TrustedOrigin,
) -> None:
    """Protect public browser writes before a durable session exists."""
    is_browser = bool(request.headers.get("origin") or request.headers.get("sec-fetch-site"))
    if not is_browser and get_settings().app_env != "production":
        return
    cookie_token = request.cookies.get(get_settings().csrf_cookie_name)
    if not bootstrap_csrf_matches(cookie_token):
        raise HTTPException(status_code=403, detail="Bootstrap CSRF token missing or invalid.")
    supplied = request.headers.get("x-csrf-token")
    if supplied is not None and not csrf_matches(supplied, cookie_token or ""):
        raise HTTPException(status_code=403, detail="Bootstrap CSRF token missing or invalid.")


def set_bootstrap_csrf_cookie(response: Response) -> None:
    settings = get_settings()
    response.set_cookie(
        settings.csrf_cookie_name,
        new_bootstrap_csrf_token(),
        httponly=False,
        secure=settings.cookies_secure,
        samesite="lax",
        path="/",
        max_age=BOOTSTRAP_CSRF_TTL_SECONDS,
    )


async def get_scoped_db(db: DB, identity: Identity) -> AsyncSession:
    """Session with app.current_user_id armed for the CURRENT transaction.
    resolve_session commits (session bookkeeping), which drops the
    transaction-local GUC — every data route must re-arm before touching
    RLS-guarded tables."""
    await set_user_context(db, identity[0])
    return db


Scoped = Annotated[AsyncSession, Depends(get_scoped_db)]
