from fastapi import APIRouter, Depends, HTTPException, Request, Response  # noqa: F401

from app.api.deps import (
    DB,
    Identity,
    require_csrf,
    require_public_browser_csrf,
    set_bootstrap_csrf_cookie,
)
from app.core.config import get_settings
from app.core.security import csrf_token_for, email_fingerprint, split_session_cookie
from app.schemas.auth import LoginRequest, MeResponse, OrbitOut, ProfileOut, RegisterRequest
from app.services import auth_service, rate_limit
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookies(response: Response, session_value: str) -> None:
    s = get_settings()
    parsed = split_session_cookie(session_value)
    assert parsed is not None  # session_value was just minted by auth_service
    csrf_value = csrf_token_for(parsed[0])  # signed, bound to this session
    common = dict(secure=s.cookies_secure, samesite="lax", path="/", max_age=s.session_ttl_seconds)
    response.set_cookie(s.session_cookie_name, session_value, httponly=True, **common)
    response.set_cookie(s.csrf_cookie_name, csrf_value, httponly=False, **common)


def _clear_auth_cookies(response: Response) -> None:
    s = get_settings()
    response.delete_cookie(s.session_cookie_name, path="/")
    set_bootstrap_csrf_cookie(response)


@router.post(
    "/register",
    status_code=201,
    response_model=MeResponse,
    dependencies=[Depends(require_public_browser_csrf)],
)
async def register(payload: RegisterRequest, request: Request, response: Response, db: DB):
    ip = request.client.host if request.client else "unknown"
    if not await rate_limit.allow_registration(request.app.state.redis, ip=ip):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
    try:
        user, profile, orbit, cookie_value = await auth_service.register(
            db, chosen_name=payload.chosen_name, email=payload.email,
            password=payload.password, consent=payload.consent,
        )
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    _set_auth_cookies(response, cookie_value)
    return MeResponse(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None,
        profile=ProfileOut.model_validate(profile, from_attributes=True),
        orbit=OrbitOut.model_validate(orbit, from_attributes=True),
    )


@router.post(
    "/login",
    response_model=dict,
    dependencies=[Depends(require_public_browser_csrf)],
)
async def login(payload: LoginRequest, request: Request, response: Response, db: DB):
    ip = request.client.host if request.client else "unknown"
    allowed = await rate_limit.allow_login(request.app.state.redis, ip=ip,
                                           email_fp=email_fingerprint(payload.email))
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
    try:
        _, cookie_value = await auth_service.login(db, email=payload.email, password=payload.password)
    except AuthError as e:
        raise HTTPException(status_code=e.status_code, detail=e.detail)
    _set_auth_cookies(response, cookie_value)
    return {"ok": True}


@router.post("/logout", status_code=204, dependencies=[Depends(require_csrf)])
async def logout(identity: Identity, response: Response, db: DB):
    user_id, session_id = identity
    await auth_service.revoke_session(db, session_id=session_id, user_id=user_id)
    _clear_auth_cookies(response)
    return None


@router.get("/me", response_model=MeResponse)
async def me(identity: Identity, db: DB):
    user_id, _ = identity
    result = await auth_service.get_me(db, user_id)
    if not result:
        raise HTTPException(status_code=401, detail="Not authenticated.")
    user, profile, orbit = result
    return MeResponse(
        id=user.id, email=user.email, email_verified=user.email_verified_at is not None,
        profile=ProfileOut.model_validate(profile, from_attributes=True),
        orbit=OrbitOut.model_validate(orbit, from_attributes=True),
    )
