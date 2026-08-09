import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.deps import DB, Identity, Scoped, require_csrf, require_trusted_origin
from app.core.config import get_settings
from app.core.security import email_fingerprint, opaque_fingerprint
from app.schemas.account import (
    AccountDeletionAccepted,
    AccountDeletionCancelIn,
    AccountDeletionCancelled,
    AccountDeletionReceiptIn,
    AccountDeletionReceiptOut,
    AccountDeletionRequestIn,
    OwnerExportManifest,
    SessionInventoryResponse,
    SessionRevocationResponse,
)
from app.services import account_service, rate_limit
from app.services.auth_service import AuthError

router = APIRouter(tags=["account"])


def _privacy_write_dependencies() -> list:
    return [Depends(require_csrf), Depends(require_trusted_origin)]


def _clear_auth_cookies(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(settings.session_cookie_name, path="/")
    response.delete_cookie(settings.csrf_cookie_name, path="/")


@router.post(
    "/account/export",
    dependencies=_privacy_write_dependencies(),
    response_model=OwnerExportManifest,
    responses={
        200: {
            "headers": {
                "Content-Disposition": {"schema": {"type": "string"}},
                "X-NUR-Export-Checksum": {"schema": {"type": "string"}},
            }
        }
    },
)
async def export_account(identity: Identity, db: Scoped) -> Response:
    owner_user_id, _ = identity
    manifest = await account_service.build_owner_export(
        db, owner_user_id=owner_user_id
    )
    body = account_service.canonical_json_bytes(manifest)
    return Response(
        content=body,
        media_type="application/json",
        headers={
            "Content-Disposition": 'attachment; filename="nur-owner-export-v1.json"',
            "X-NUR-Export-Checksum": manifest["checksum"]["value"],
        },
    )


@router.get("/auth/sessions", response_model=SessionInventoryResponse)
async def list_sessions(identity: Identity, db: Scoped) -> SessionInventoryResponse:
    owner_user_id, current_session_id = identity
    rows = await account_service.session_inventory(
        db,
        owner_user_id=owner_user_id,
        current_session_id=current_session_id,
    )
    return SessionInventoryResponse(sessions=rows)


@router.post(
    "/auth/sessions/revoke-others",
    response_model=SessionRevocationResponse,
    dependencies=_privacy_write_dependencies(),
)
async def revoke_other_sessions(
    identity: Identity, db: Scoped
) -> SessionRevocationResponse:
    owner_user_id, current_session_id = identity
    count = await account_service.revoke_other_sessions(
        db,
        owner_user_id=owner_user_id,
        current_session_id=current_session_id,
    )
    return SessionRevocationResponse(revoked_session_count=count)


@router.delete(
    "/auth/sessions/{session_id}",
    response_model=SessionRevocationResponse,
    dependencies=_privacy_write_dependencies(),
)
async def revoke_session(
    session_id: uuid.UUID,
    identity: Identity,
    db: Scoped,
) -> SessionRevocationResponse:
    owner_user_id, current_session_id = identity
    try:
        changed = await account_service.revoke_owned_session(
            db,
            owner_user_id=owner_user_id,
            current_session_id=current_session_id,
            target_session_id=session_id,
        )
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    if not changed:
        raise HTTPException(404, "Session not found or already revoked.")
    return SessionRevocationResponse(revoked_session_count=1)


@router.delete(
    "/account",
    status_code=202,
    response_model=AccountDeletionAccepted,
    dependencies=_privacy_write_dependencies(),
)
async def request_account_deletion(
    payload: AccountDeletionRequestIn,
    request: Request,
    response: Response,
    identity: Identity,
    db: Scoped,
) -> AccountDeletionAccepted:
    owner_user_id, _ = identity
    ip = request.client.host if request.client else "unknown"
    if not await rate_limit.allow_password_change(
        request.app.state.redis, ip=ip, user_id=str(owner_user_id)
    ):
        raise HTTPException(429, "Too many attempts. Please wait and try again.")
    try:
        result = await account_service.request_account_deletion(
            db,
            owner_user_id=owner_user_id,
            password=payload.password.get_secret_value(),
            confirmation=payload.confirmation,
        )
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    _clear_auth_cookies(response)
    return AccountDeletionAccepted.model_validate(result)


@router.post(
    "/account/deletion/cancel",
    response_model=AccountDeletionCancelled,
    dependencies=[Depends(require_trusted_origin)],
)
async def cancel_account_deletion(
    payload: AccountDeletionCancelIn,
    request: Request,
    db: DB,
) -> AccountDeletionCancelled:
    # This route deliberately has no session dependency: deletion has already
    # revoked every session. Reauthentication plus trusted-origin and a bounded
    # limiter are the cancellation authority.
    ip = request.client.host if request.client else "unknown"
    if not await rate_limit.allow_password_change(
        request.app.state.redis,
        ip=ip,
        user_id=email_fingerprint(str(payload.email)),
    ):
        raise HTTPException(429, "Too many attempts. Please wait and try again.")
    try:
        result = await account_service.cancel_account_deletion(
            db,
            email=str(payload.email),
            password=payload.password.get_secret_value(),
            confirmation=payload.confirmation,
        )
    except AuthError as exc:
        raise HTTPException(exc.status_code, exc.detail)
    return AccountDeletionCancelled.model_validate(result)


@router.post(
    "/account/deletion/receipt",
    response_model=AccountDeletionReceiptOut,
    dependencies=[Depends(require_trusted_origin)],
)
async def account_deletion_receipt(
    payload: AccountDeletionReceiptIn,
    request: Request,
    db: DB,
) -> AccountDeletionReceiptOut:
    token = payload.receipt_token.get_secret_value()
    ip = request.client.host if request.client else "unknown"
    if not await rate_limit.allow_password_reset(
        request.app.state.redis,
        ip=ip,
        token_fp=opaque_fingerprint(token, purpose="deletion-receipt"),
    ):
        raise HTTPException(429, "Too many attempts. Please wait and try again.")
    result = await account_service.deletion_receipt(
        db, request_id=payload.request_id, receipt_token=token
    )
    if result is None:
        raise HTTPException(404, "Deletion receipt not found.")
    return AccountDeletionReceiptOut.model_validate(result)
