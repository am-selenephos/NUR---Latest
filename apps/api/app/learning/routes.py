import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from app.api.deps import Identity, Scoped, require_csrf
from app.learning import service
from app.learning.schemas import (
    TeachNURCandidateOut,
    TeachNURContributionCreate,
    TeachNURContributionDetail,
    TeachNURContributionOut,
    TeachNUREvaluationOut,
    TeachNURKnowledgeVersionOut,
    TeachNURReviewIn,
    TeachNURReviewOut,
)
from app.observability.metrics import record_counter

router = APIRouter(prefix="/teach-nur", tags=["teach-nur"])


def _detail(bundle: service.ContributionBundle) -> TeachNURContributionDetail:
    row = TeachNURContributionOut.model_validate(bundle.contribution)
    return TeachNURContributionDetail(
        **row.model_dump(),
        candidate=TeachNURCandidateOut.model_validate(bundle.candidate),
        reviews=[TeachNURReviewOut.model_validate(item) for item in bundle.reviews],
        knowledge_versions=[
            TeachNURKnowledgeVersionOut.model_validate(item)
            for item in bundle.knowledge_versions
        ],
        evaluations=[
            TeachNUREvaluationOut.model_validate(item) for item in bundle.evaluations
        ],
    )


def _raise_service_error(exc: Exception) -> None:
    if isinstance(exc, service.TeachNURNotFoundError):
        raise HTTPException(404, str(exc)) from exc
    if isinstance(exc, (service.TeachNURConflictError, service.TeachNURReviewBlockedError)):
        raise HTTPException(409, str(exc)) from exc
    if isinstance(
        exc,
        (service.TeachNURConsentError, service.TeachNURUnsafeContentError),
    ):
        raise HTTPException(422, str(exc)) from exc
    raise exc


@router.post(
    "/contributions",
    response_model=TeachNURContributionDetail,
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def create_teach_nur_contribution(
    payload: TeachNURContributionCreate,
    request: Request,
    db: Scoped,
    identity: Identity,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TeachNURContributionDetail:
    owner_user_id, _ = identity
    try:
        row = await service.create_contribution(
            db,
            owner_user_id=owner_user_id,
            payload=payload,
            request_key=idempotency_key,
        )
        bundle = await service.get_contribution_bundle(
            db,
            owner_user_id=owner_user_id,
            contribution_id=row.id,
        )
    except Exception as exc:
        _raise_service_error(exc)
    output = _detail(bundle)
    record_counter(
        request,
        "nur_teach_nur_contributions_total",
        (("status", bundle.contribution.status.lower()),),
    )
    await db.commit()
    return output


@router.get(
    "/contributions",
    response_model=list[TeachNURContributionDetail],
)
async def list_teach_nur_contributions(
    db: Scoped,
    identity: Identity,
    status: str | None = Query(default=None, min_length=1, max_length=24),
    limit: int = Query(default=100, ge=1, le=100),
) -> list[TeachNURContributionDetail]:
    owner_user_id, _ = identity
    bundles = await service.list_contribution_bundles(
        db,
        owner_user_id=owner_user_id,
        status=status,
        limit=limit,
    )
    return [_detail(bundle) for bundle in bundles]


@router.get(
    "/contributions/{contribution_id}",
    response_model=TeachNURContributionDetail,
)
async def get_teach_nur_contribution(
    contribution_id: uuid.UUID,
    db: Scoped,
    identity: Identity,
) -> TeachNURContributionDetail:
    owner_user_id, _ = identity
    try:
        bundle = await service.get_contribution_bundle(
            db,
            owner_user_id=owner_user_id,
            contribution_id=contribution_id,
            record_view=True,
        )
    except Exception as exc:
        _raise_service_error(exc)
    output = _detail(bundle)
    await db.commit()
    return output


@router.post(
    "/contributions/{contribution_id}/review",
    response_model=TeachNURContributionDetail,
    dependencies=[Depends(require_csrf)],
)
async def review_teach_nur_contribution(
    contribution_id: uuid.UUID,
    payload: TeachNURReviewIn,
    request: Request,
    db: Scoped,
    identity: Identity,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
) -> TeachNURContributionDetail:
    owner_user_id, _ = identity
    try:
        bundle = await service.review_contribution(
            db,
            owner_user_id=owner_user_id,
            contribution_id=contribution_id,
            payload=payload,
            request_key=idempotency_key,
        )
    except service.TeachNURReviewBlockedError as exc:
        await db.commit()
        raise HTTPException(409, str(exc)) from exc
    except Exception as exc:
        _raise_service_error(exc)
    output = _detail(bundle)
    record_counter(
        request,
        "nur_teach_nur_reviews_total",
        (("action", payload.action.lower()),),
    )
    await db.commit()
    return output
