from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response

from app.api.deps import (
    DB,
    Identity,
    require_csrf,
    require_public_browser_csrf,
    require_trusted_origin,
    set_bootstrap_csrf_cookie,
)
from app.core.config import get_settings
from app.core.security import email_fingerprint, opaque_fingerprint
from app.schemas.auth import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ForgotPasswordResponse,
    ResetPasswordRequest,
)
from app.services import password_recovery_service, rate_limit
from app.services.auth_service import AuthError

router = APIRouter(prefix="/auth/password", tags=["auth"])


def _request_ip(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    set_bootstrap_csrf_cookie(response)


@router.post(
    "/forgot",
    status_code=202,
    response_model=ForgotPasswordResponse,
    dependencies=[Depends(require_public_browser_csrf)],
)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    background_tasks: BackgroundTasks,
    db: DB,
):
    ip = _request_ip(request)
    allowed = await rate_limit.allow_password_forgot(
        request.app.state.redis,
        ip=ip,
        email_fp=email_fingerprint(payload.email),
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
    delivery = request.app.state.password_reset_delivery
    dispatch = await password_recovery_service.request_password_reset(
        db,
        email=payload.email,
        request_ip=ip,
        delivery_name=delivery.name,
    )
    if dispatch is not None:
        background_tasks.add_task(
            password_recovery_service.deliver_password_reset,
            dispatch=dispatch,
            delivery=delivery,
        )
    return ForgotPasswordResponse()


@router.post(
    "/reset",
    status_code=204,
    dependencies=[Depends(require_public_browser_csrf)],
)
async def reset_password(
    payload: ResetPasswordRequest,
    request: Request,
    db: DB,
):
    token = payload.token.get_secret_value()
    allowed = await rate_limit.allow_password_reset(
        request.app.state.redis,
        ip=_request_ip(request),
        token_fp=opaque_fingerprint(token, purpose="password-reset-rate-limit"),
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
    try:
        await password_recovery_service.reset_password(
            db,
            token=token,
            new_password=payload.new_password.get_secret_value(),
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return None


@router.post(
    "/change",
    status_code=204,
    dependencies=[Depends(require_csrf), Depends(require_trusted_origin)],
)
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    response: Response,
    identity: Identity,
    db: DB,
):
    user_id, _ = identity
    allowed = await rate_limit.allow_password_change(
        request.app.state.redis,
        ip=_request_ip(request),
        user_id=str(user_id),
    )
    if not allowed:
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait and try again.")
    try:
        await password_recovery_service.change_password(
            db,
            user_id=user_id,
            current_password=payload.current_password.get_secret_value(),
            new_password=payload.new_password.get_secret_value(),
        )
    except AuthError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    _clear_auth_cookies(response)
    return None
