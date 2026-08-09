from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.safety import (
    analyze_contribution,
    offline_evaluation_checks,
    provenance_for_kind,
)
from app.learning.schemas import TeachNURContributionCreate, TeachNURReviewIn
from app.models import (
    Orbit,
    TeachNURCandidate,
    TeachNURConsentEvent,
    TeachNURContribution,
    TeachNUREvaluationRun,
    TeachNURKnowledgeAccessEvent,
    TeachNURKnowledgeVersion,
    TeachNURReview,
)
from app.models._mixins import now_utc
from app.services import audit_service
from app.services.domain_event_service import emit_domain_event

EVALUATION_SUITE_VERSION = "teach-nur-safety-v1"


class TeachNURNotFoundError(RuntimeError):
    pass


class TeachNURConflictError(RuntimeError):
    pass


class TeachNURConsentError(RuntimeError):
    pass


class TeachNURUnsafeContentError(RuntimeError):
    pass


class TeachNURReviewBlockedError(RuntimeError):
    pass


@dataclass
class ContributionBundle:
    contribution: TeachNURContribution
    candidate: TeachNURCandidate
    reviews: list[TeachNURReview]
    knowledge_versions: list[TeachNURKnowledgeVersion]
    evaluations: list[TeachNUREvaluationRun]


def _digest_text(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _digest_payload(value: dict) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return _digest_text(encoded)


def normalize_request_key(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    if not value:
        return None
    if len(value) > 160 or any(ord(char) < 32 for char in value):
        raise TeachNURConflictError("Idempotency-Key is invalid.")
    return value


async def create_contribution(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    payload: TeachNURContributionCreate,
    request_key: str | None,
) -> TeachNURContribution:
    if not payload.consent_granted:
        raise TeachNURConsentError("Explicit Teach NUR consent is required.")
    request_key = normalize_request_key(request_key)
    source_refs = [item.model_dump(mode="json") for item in payload.source_refs]
    payload_digest = _digest_payload(payload.model_dump(mode="json"))
    if request_key:
        existing = (
            await db.execute(
                select(TeachNURContribution).where(
                    TeachNURContribution.owner_user_id == owner_user_id,
                    TeachNURContribution.request_key == request_key,
                )
            )
        ).scalar_one_or_none()
        if existing:
            if existing.payload_digest != payload_digest:
                raise TeachNURConflictError(
                    "Idempotency-Key was already used for a different contribution."
                )
            return existing

    await _assert_owned_orbit(
        db,
        owner_user_id=owner_user_id,
        orbit_id=payload.orbit_id,
    )
    safety = analyze_contribution(
        payload.content,
        contribution_kind=payload.contribution_kind,
        consent_scope=payload.consent_scope,
        requested_sensitivity=payload.sensitivity,
        source_refs=source_refs,
    )
    if safety.secret_detected:
        raise TeachNURUnsafeContentError(
            "Secrets and credentials cannot be submitted to Teach NUR."
        )
    status = "QUARANTINED" if safety.quarantined else "PENDING_REVIEW"
    provenance = provenance_for_kind(payload.contribution_kind)
    row = TeachNURContribution(
        owner_user_id=owner_user_id,
        orbit_id=payload.orbit_id,
        contribution_kind=payload.contribution_kind,
        content=safety.normalized_text,
        language_tag=payload.language_tag,
        consent_scope=payload.consent_scope,
        consent_policy_version=payload.consent_policy_version,
        consent_granted=True,
        provenance_label=provenance,
        sensitivity=safety.sensitivity,
        confidence=payload.confidence,
        source_refs=source_refs,
        risk_flags=safety.risk_flags,
        deidentification_status=safety.deidentification_status,
        verification_status=safety.verification_status,
        status=status,
        request_key=request_key,
        payload_digest=payload_digest,
    )
    db.add(row)
    await db.flush()
    candidate = TeachNURCandidate(
        owner_user_id=owner_user_id,
        contribution_id=row.id,
        candidate_text=safety.normalized_text,
        original_text_digest=_digest_text(safety.normalized_text),
        deidentified_text=safety.deidentified_text,
        provenance_label=provenance,
        sensitivity=safety.sensitivity,
        confidence=payload.confidence,
        source_refs=source_refs,
        risk_flags=safety.risk_flags,
        contradiction_refs=[],
        disagreement_map={
            "status": "UNASSESSED",
            "counter_source_search": "NOT_RUN",
        },
        status=status,
    )
    db.add_all(
        [
            candidate,
            TeachNURConsentEvent(
                owner_user_id=owner_user_id,
                contribution_id=row.id,
                action="GRANTED",
                consent_scope=row.consent_scope,
                policy_version=row.consent_policy_version,
            ),
        ]
    )
    await db.flush()
    await audit_service.record(
        db,
        event_type="TEACH_NUR_CONTRIBUTION_CREATED",
        object_type="teach_nur_contribution",
        actor_user_id=owner_user_id,
        object_id=row.id,
        metadata={
            "status": status,
            "consent_scope": row.consent_scope,
            "risk_flags": safety.risk_flags,
        },
    )
    await emit_domain_event(
        db,
        owner_user_id=owner_user_id,
        event_type="teach_nur.contribution.created",
        aggregate_type="teach_nur_contribution",
        aggregate_id=row.id,
        idempotency_key=f"teach-nur:{row.id}:created",
        payload={
            "status": status,
            "consent_scope": row.consent_scope,
            "candidate_id": str(candidate.id),
            "risk_flags": safety.risk_flags,
        },
    )
    return row


async def get_contribution_bundle(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    contribution_id: uuid.UUID,
    record_view: bool = False,
    lock: bool = False,
) -> ContributionBundle:
    query = select(TeachNURContribution).where(
        TeachNURContribution.id == contribution_id,
        TeachNURContribution.owner_user_id == owner_user_id,
    )
    if lock:
        query = query.with_for_update()
    contribution = (await db.execute(query)).scalar_one_or_none()
    if contribution is None:
        raise TeachNURNotFoundError("Teach NUR contribution not found.")
    candidate = (
        await db.execute(
            select(TeachNURCandidate).where(
                TeachNURCandidate.contribution_id == contribution.id,
                TeachNURCandidate.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one()
    reviews = list(
        (
            await db.execute(
                select(TeachNURReview)
                .where(
                    TeachNURReview.contribution_id == contribution.id,
                    TeachNURReview.owner_user_id == owner_user_id,
                )
                .order_by(TeachNURReview.created_at.asc())
            )
        ).scalars()
    )
    versions = list(
        (
            await db.execute(
                select(TeachNURKnowledgeVersion)
                .where(
                    TeachNURKnowledgeVersion.contribution_id == contribution.id,
                    TeachNURKnowledgeVersion.owner_user_id == owner_user_id,
                )
                .order_by(TeachNURKnowledgeVersion.version.asc())
            )
        ).scalars()
    )
    evaluations = list(
        (
            await db.execute(
                select(TeachNUREvaluationRun)
                .where(
                    TeachNUREvaluationRun.contribution_id == contribution.id,
                    TeachNUREvaluationRun.owner_user_id == owner_user_id,
                )
                .order_by(TeachNUREvaluationRun.created_at.asc())
            )
        ).scalars()
    )
    if record_view and candidate.current_knowledge_version_id:
        db.add(
            TeachNURKnowledgeAccessEvent(
                owner_user_id=owner_user_id,
                knowledge_version_id=candidate.current_knowledge_version_id,
                access_kind="VIEWED",
                purpose="OWNER_TEACH_NUR_REVIEW",
                context_ref=f"contribution:{contribution.id}",
            )
        )
    return ContributionBundle(
        contribution=contribution,
        candidate=candidate,
        reviews=reviews,
        knowledge_versions=versions,
        evaluations=evaluations,
    )


async def list_contribution_bundles(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    status: str | None = None,
    limit: int = 100,
) -> list[ContributionBundle]:
    query = select(TeachNURContribution).where(
        TeachNURContribution.owner_user_id == owner_user_id,
    )
    if status:
        query = query.where(TeachNURContribution.status == status.upper())
    contributions = list(
        (
            await db.execute(
                query.order_by(
                    TeachNURContribution.updated_at.desc(),
                    TeachNURContribution.created_at.desc(),
                    TeachNURContribution.id.desc(),
                ).limit(limit)
            )
        ).scalars()
    )
    if not contributions:
        return []

    contribution_ids = [row.id for row in contributions]
    candidates = list(
        (
            await db.execute(
                select(TeachNURCandidate).where(
                    TeachNURCandidate.owner_user_id == owner_user_id,
                    TeachNURCandidate.contribution_id.in_(contribution_ids),
                )
            )
        ).scalars()
    )
    reviews = list(
        (
            await db.execute(
                select(TeachNURReview)
                .where(
                    TeachNURReview.owner_user_id == owner_user_id,
                    TeachNURReview.contribution_id.in_(contribution_ids),
                )
                .order_by(TeachNURReview.created_at.asc())
            )
        ).scalars()
    )
    versions = list(
        (
            await db.execute(
                select(TeachNURKnowledgeVersion)
                .where(
                    TeachNURKnowledgeVersion.owner_user_id == owner_user_id,
                    TeachNURKnowledgeVersion.contribution_id.in_(contribution_ids),
                )
                .order_by(TeachNURKnowledgeVersion.version.asc())
            )
        ).scalars()
    )
    evaluations = list(
        (
            await db.execute(
                select(TeachNUREvaluationRun)
                .where(
                    TeachNUREvaluationRun.owner_user_id == owner_user_id,
                    TeachNUREvaluationRun.contribution_id.in_(contribution_ids),
                )
                .order_by(TeachNUREvaluationRun.created_at.asc())
            )
        ).scalars()
    )

    candidate_by_contribution = {row.contribution_id: row for row in candidates}
    reviews_by_contribution: defaultdict[uuid.UUID, list[TeachNURReview]] = defaultdict(list)
    versions_by_contribution: defaultdict[uuid.UUID, list[TeachNURKnowledgeVersion]] = defaultdict(list)
    evaluations_by_contribution: defaultdict[uuid.UUID, list[TeachNUREvaluationRun]] = defaultdict(list)
    for row in reviews:
        reviews_by_contribution[row.contribution_id].append(row)
    for row in versions:
        versions_by_contribution[row.contribution_id].append(row)
    for row in evaluations:
        evaluations_by_contribution[row.contribution_id].append(row)

    return [
        ContributionBundle(
            contribution=row,
            candidate=candidate_by_contribution[row.id],
            reviews=reviews_by_contribution[row.id],
            knowledge_versions=versions_by_contribution[row.id],
            evaluations=evaluations_by_contribution[row.id],
        )
        for row in contributions
    ]


async def review_contribution(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    contribution_id: uuid.UUID,
    payload: TeachNURReviewIn,
    request_key: str | None,
) -> ContributionBundle:
    request_key = normalize_request_key(request_key)
    payload_digest = _digest_payload(payload.model_dump(mode="json"))
    if request_key:
        prior_review = (
            await db.execute(
                select(TeachNURReview).where(
                    TeachNURReview.owner_user_id == owner_user_id,
                    TeachNURReview.contribution_id == contribution_id,
                    TeachNURReview.request_key == request_key,
                )
            )
        ).scalar_one_or_none()
        if prior_review:
            if prior_review.payload_digest != payload_digest:
                raise TeachNURConflictError(
                    "Idempotency-Key was already used for a different review."
                )
            return await get_contribution_bundle(
                db,
                owner_user_id=owner_user_id,
                contribution_id=contribution_id,
            )

    bundle = await get_contribution_bundle(
        db,
        owner_user_id=owner_user_id,
        contribution_id=contribution_id,
        lock=True,
    )
    row = bundle.contribution
    candidate = bundle.candidate
    if row.status == "WITHDRAWN":
        if payload.action == "WITHDRAW_CONSENT":
            return bundle
        raise TeachNURConflictError("Consent has been withdrawn for this contribution.")

    if payload.action == "EDIT":
        prior_status = candidate.status
        await _edit_candidate(
            db,
            row=row,
            candidate=candidate,
            edited_text=payload.edited_text or "",
        )
        await _append_review(
            db,
            row=row,
            candidate=candidate,
            reviewer_user_id=owner_user_id,
            action="EDIT",
            prior_status=prior_status,
            resulting_status=candidate.status,
            review_note=payload.review_note,
            request_key=request_key,
            payload_digest=payload_digest,
        )
        await _record_transition(
            db,
            row=row,
            candidate=candidate,
            event_type="teach_nur.candidate.edited",
            audit_type="TEACH_NUR_CANDIDATE_EDITED",
        )
    elif payload.action == "REJECT":
        if candidate.status not in {"PENDING_REVIEW", "QUARANTINED", "EDITED"}:
            raise TeachNURConflictError("Only an open Teach NUR candidate can be rejected.")
        prior_status = candidate.status
        candidate.status = row.status = "REJECTED"
        row.reviewed_at = row.updated_at = candidate.updated_at = now_utc()
        await _append_review(
            db,
            row=row,
            candidate=candidate,
            reviewer_user_id=owner_user_id,
            action="REJECT",
            prior_status=prior_status,
            resulting_status="REJECTED",
            review_note=payload.review_note,
            request_key=request_key,
            payload_digest=payload_digest,
        )
        await _record_transition(
            db,
            row=row,
            candidate=candidate,
            event_type="teach_nur.candidate.rejected",
            audit_type="TEACH_NUR_CANDIDATE_REJECTED",
        )
    elif payload.action == "APPROVE":
        await _approve_candidate(
            db,
            row=row,
            candidate=candidate,
            reviewer_user_id=owner_user_id,
            review_note=payload.review_note,
            request_key=request_key,
            payload_digest=payload_digest,
        )
    elif payload.action in {"START_CANARY", "ACTIVATE", "ROLLBACK"}:
        await _transition_knowledge(
            db,
            row=row,
            candidate=candidate,
            action=payload.action,
            reviewer_user_id=owner_user_id,
            review_note=payload.review_note,
            request_key=request_key,
            payload_digest=payload_digest,
        )
    elif payload.action == "WITHDRAW_CONSENT":
        await _withdraw_consent(
            db,
            row=row,
            candidate=candidate,
            reviewer_user_id=owner_user_id,
            review_note=payload.review_note,
            request_key=request_key,
            payload_digest=payload_digest,
        )
    else:  # pragma: no cover - constrained by the request schema
        raise TeachNURConflictError("Unknown Teach NUR review action.")
    await db.flush()
    return await get_contribution_bundle(
        db,
        owner_user_id=owner_user_id,
        contribution_id=contribution_id,
    )


async def _edit_candidate(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    edited_text: str,
) -> None:
    if candidate.status not in {"PENDING_REVIEW", "QUARANTINED", "EDITED"}:
        raise TeachNURConflictError("Only an open Teach NUR candidate can be edited.")
    safety = analyze_contribution(
        edited_text,
        contribution_kind=row.contribution_kind,
        consent_scope=row.consent_scope,
        requested_sensitivity=row.sensitivity,
        source_refs=row.source_refs,
    )
    if safety.secret_detected:
        raise TeachNURUnsafeContentError(
            "Secrets and credentials cannot be submitted to Teach NUR."
        )
    now = now_utc()
    candidate.candidate_text = safety.normalized_text
    candidate.deidentified_text = safety.deidentified_text
    candidate.provenance_label = "USER_CORRECTION"
    candidate.sensitivity = safety.sensitivity
    candidate.risk_flags = safety.risk_flags
    candidate.status = "QUARANTINED" if safety.quarantined else "EDITED"
    candidate.updated_at = now
    row.provenance_label = "USER_CORRECTION"
    row.sensitivity = safety.sensitivity
    row.risk_flags = safety.risk_flags
    row.deidentification_status = safety.deidentification_status
    row.verification_status = safety.verification_status
    row.status = candidate.status
    row.updated_at = now
    await db.flush()


async def _approve_candidate(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    reviewer_user_id: uuid.UUID,
    review_note: str | None,
    request_key: str | None,
    payload_digest: str,
) -> None:
    if candidate.status not in {"PENDING_REVIEW", "EDITED"}:
        raise TeachNURConflictError(
            "Only a non-quarantined open Teach NUR candidate can be approved."
        )
    prior_status = candidate.status
    checks = offline_evaluation_checks(
        contribution_kind=row.contribution_kind,
        consent_scope=row.consent_scope,
        consent_granted=row.consent_granted,
        risk_flags=candidate.risk_flags,
        deidentification_status=row.deidentification_status,
        verification_status=row.verification_status,
        provenance_label=candidate.provenance_label,
    )
    passed = all(checks.values())
    if not passed:
        db.add(
            TeachNUREvaluationRun(
                owner_user_id=row.owner_user_id,
                contribution_id=row.id,
                candidate_id=candidate.id,
                suite_version=EVALUATION_SUITE_VERSION,
                checks=checks,
                passed=False,
            )
        )
        candidate.status = row.status = "QUARANTINED"
        row.risk_flags = sorted(set([*row.risk_flags, "OFFLINE_EVALUATION_FAILED"]))
        candidate.risk_flags = row.risk_flags
        row.updated_at = candidate.updated_at = now_utc()
        await _append_review(
            db,
            row=row,
            candidate=candidate,
            reviewer_user_id=reviewer_user_id,
            action="APPROVE_BLOCKED",
            prior_status=prior_status,
            resulting_status="QUARANTINED",
            review_note=review_note,
            request_key=request_key,
            payload_digest=payload_digest,
        )
        await _record_transition(
            db,
            row=row,
            candidate=candidate,
            event_type="teach_nur.review.blocked",
            audit_type="TEACH_NUR_REVIEW_BLOCKED",
        )
        await db.flush()
        failed = [name for name, value in checks.items() if not value]
        raise TeachNURReviewBlockedError(
            "Teach NUR approval was blocked by: " + ", ".join(failed)
        )

    version_status = "ACTIVE" if row.consent_scope == "PRIVATE_OWNER" else "SHADOW"
    version = await _append_knowledge_version(
        db,
        row=row,
        candidate=candidate,
        reviewer_user_id=reviewer_user_id,
        status=version_status,
        checks=checks,
        why_changed="Owner review approved this candidate after the offline safety gate.",
    )
    db.add(
        TeachNUREvaluationRun(
            owner_user_id=row.owner_user_id,
            contribution_id=row.id,
            candidate_id=candidate.id,
            knowledge_version_id=version.id,
            suite_version=EVALUATION_SUITE_VERSION,
            checks=checks,
            passed=True,
        )
    )
    resulting_status = "ACTIVE" if version_status == "ACTIVE" else "APPROVED"
    candidate.status = row.status = resulting_status
    candidate.current_knowledge_version_id = version.id
    row.reviewed_at = row.updated_at = candidate.updated_at = now_utc()
    await _append_review(
        db,
        row=row,
        candidate=candidate,
        reviewer_user_id=reviewer_user_id,
        action="APPROVE",
        prior_status=prior_status,
        resulting_status=resulting_status,
        review_note=review_note,
        request_key=request_key,
        payload_digest=payload_digest,
    )
    await _record_transition(
        db,
        row=row,
        candidate=candidate,
        event_type=(
            "teach_nur.knowledge.activated"
            if version_status == "ACTIVE"
            else "teach_nur.knowledge.shadowed"
        ),
        audit_type="TEACH_NUR_CANDIDATE_APPROVED",
        knowledge_version_id=version.id,
    )


async def _transition_knowledge(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    action: str,
    reviewer_user_id: uuid.UUID,
    review_note: str | None,
    request_key: str | None,
    payload_digest: str,
) -> None:
    current = await _current_knowledge(db, row=row, candidate=candidate)
    expected = {
        "START_CANARY": "SHADOW",
        "ACTIVATE": "CANARY",
    }
    if action in expected and current.status != expected[action]:
        raise TeachNURConflictError(
            f"{action} requires current knowledge status {expected[action]}."
        )
    if action == "ROLLBACK" and current.status not in {"SHADOW", "CANARY", "ACTIVE"}:
        raise TeachNURConflictError("Only deployed knowledge can be rolled back.")

    checks = offline_evaluation_checks(
        contribution_kind=row.contribution_kind,
        consent_scope=row.consent_scope,
        consent_granted=row.consent_granted,
        risk_flags=candidate.risk_flags,
        deidentification_status=row.deidentification_status,
        verification_status=row.verification_status,
        provenance_label=candidate.provenance_label,
    )
    if action == "START_CANARY":
        checks["independent_verification_ready"] = row.verification_status in {
            "NOT_REQUIRED",
            "VERIFIED",
        }
    passed = all(checks.values())
    if action != "ROLLBACK" and not passed:
        raise TeachNURReviewBlockedError(
            "Knowledge promotion failed the offline or verification gate."
        )
    target = {
        "START_CANARY": "CANARY",
        "ACTIVATE": "ACTIVE",
        "ROLLBACK": "ROLLED_BACK",
    }[action]
    why = {
        "START_CANARY": "Approved shadow knowledge entered a bounded owner-scoped canary.",
        "ACTIVATE": "The bounded canary passed and the owner activated this knowledge version.",
        "ROLLBACK": "The owner rolled back the current knowledge version.",
    }[action]
    version = await _append_knowledge_version(
        db,
        row=row,
        candidate=candidate,
        reviewer_user_id=reviewer_user_id,
        status=target,
        checks=checks,
        why_changed=why,
        parent=current,
    )
    db.add(
        TeachNUREvaluationRun(
            owner_user_id=row.owner_user_id,
            contribution_id=row.id,
            candidate_id=candidate.id,
            knowledge_version_id=version.id,
            suite_version=EVALUATION_SUITE_VERSION,
            checks=checks,
            passed=passed,
        )
    )
    prior_status = candidate.status
    candidate.current_knowledge_version_id = version.id
    candidate.status = row.status = target
    row.reviewed_at = row.updated_at = candidate.updated_at = now_utc()
    await _append_review(
        db,
        row=row,
        candidate=candidate,
        reviewer_user_id=reviewer_user_id,
        action=action,
        prior_status=prior_status,
        resulting_status=target,
        review_note=review_note,
        request_key=request_key,
        payload_digest=payload_digest,
    )
    event = {
        "START_CANARY": "teach_nur.knowledge.canary_started",
        "ACTIVATE": "teach_nur.knowledge.activated",
        "ROLLBACK": "teach_nur.knowledge.rolled_back",
    }[action]
    await _record_transition(
        db,
        row=row,
        candidate=candidate,
        event_type=event,
        audit_type=f"TEACH_NUR_KNOWLEDGE_{target}",
        knowledge_version_id=version.id,
    )


async def _withdraw_consent(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    reviewer_user_id: uuid.UUID,
    review_note: str | None,
    request_key: str | None,
    payload_digest: str,
) -> None:
    prior_status = candidate.status
    now = now_utc()
    versions = list(
        (
            await db.execute(
                select(TeachNURKnowledgeVersion).where(
                    TeachNURKnowledgeVersion.owner_user_id == row.owner_user_id,
                    TeachNURKnowledgeVersion.contribution_id == row.id,
                )
            )
        ).scalars()
    )
    for version in versions:
        version.canonical_text = ""
        version.evaluation_result = {}
        version.why_changed = (
            "Consent withdrawn; retained lifecycle metadata contains no contribution text."
        )
        version.status = "ROLLED_BACK"
        version.rolled_back_at = now
    row.content = ""
    row.source_refs = []
    row.risk_flags = []
    row.consent_granted = False
    row.status = "WITHDRAWN"
    row.reviewed_at = row.updated_at = now
    candidate.candidate_text = ""
    candidate.deidentified_text = None
    candidate.source_refs = []
    candidate.risk_flags = []
    candidate.contradiction_refs = []
    candidate.disagreement_map = {}
    candidate.status = "WITHDRAWN"
    candidate.current_knowledge_version_id = None
    candidate.updated_at = now
    db.add(
        TeachNURConsentEvent(
            owner_user_id=row.owner_user_id,
            contribution_id=row.id,
            action="WITHDRAWN",
            consent_scope=row.consent_scope,
            policy_version=row.consent_policy_version,
        )
    )
    await _append_review(
        db,
        row=row,
        candidate=candidate,
        reviewer_user_id=reviewer_user_id,
        action="WITHDRAW_CONSENT",
        prior_status=prior_status,
        resulting_status="WITHDRAWN",
        review_note=review_note,
        request_key=request_key,
        payload_digest=payload_digest,
    )
    await _record_transition(
        db,
        row=row,
        candidate=candidate,
        event_type="teach_nur.consent.withdrawn",
        audit_type="TEACH_NUR_CONSENT_WITHDRAWN",
    )


async def _append_knowledge_version(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    reviewer_user_id: uuid.UUID,
    status: str,
    checks: dict,
    why_changed: str,
    parent: TeachNURKnowledgeVersion | None = None,
) -> TeachNURKnowledgeVersion:
    if parent is None and candidate.current_knowledge_version_id:
        parent = await _current_knowledge(db, row=row, candidate=candidate)
    latest_version = (
        await db.execute(
            select(func.max(TeachNURKnowledgeVersion.version)).where(
                TeachNURKnowledgeVersion.owner_user_id == row.owner_user_id,
                TeachNURKnowledgeVersion.candidate_id == candidate.id,
            )
        )
    ).scalar_one()
    canonical_text = (
        candidate.candidate_text
        if row.consent_scope == "PRIVATE_OWNER"
        else candidate.deidentified_text
    )
    if not canonical_text:
        raise TeachNURConflictError("No eligible retrieval text is available for promotion.")
    now = now_utc()
    version = TeachNURKnowledgeVersion(
        owner_user_id=row.owner_user_id,
        contribution_id=row.id,
        candidate_id=candidate.id,
        version=int(latest_version or 0) + 1,
        parent_version_id=parent.id if parent else None,
        canonical_text=canonical_text,
        retrieval_scope=row.consent_scope,
        provenance_label=candidate.provenance_label,
        verification_status=row.verification_status,
        status=status,
        evaluation_result=checks,
        why_changed=why_changed,
        created_by_user_id=reviewer_user_id,
        activated_at=now if status == "ACTIVE" else None,
        rolled_back_at=now if status == "ROLLED_BACK" else None,
    )
    db.add(version)
    await db.flush()
    return version


async def _current_knowledge(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
) -> TeachNURKnowledgeVersion:
    if candidate.current_knowledge_version_id is None:
        raise TeachNURConflictError("This contribution has no promoted knowledge version.")
    version = (
        await db.execute(
            select(TeachNURKnowledgeVersion).where(
                TeachNURKnowledgeVersion.id == candidate.current_knowledge_version_id,
                TeachNURKnowledgeVersion.owner_user_id == row.owner_user_id,
                TeachNURKnowledgeVersion.candidate_id == candidate.id,
            )
        )
    ).scalar_one_or_none()
    if version is None:
        raise TeachNURConflictError("Current Teach NUR knowledge version is unavailable.")
    return version


async def _append_review(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    reviewer_user_id: uuid.UUID,
    action: str,
    prior_status: str,
    resulting_status: str,
    review_note: str | None,
    request_key: str | None,
    payload_digest: str,
) -> TeachNURReview:
    review = TeachNURReview(
        owner_user_id=row.owner_user_id,
        contribution_id=row.id,
        candidate_id=candidate.id,
        reviewer_user_id=reviewer_user_id,
        action=action,
        prior_status=prior_status,
        resulting_status=resulting_status,
        note_digest=_digest_text(review_note) if review_note else None,
        request_key=request_key,
        payload_digest=payload_digest,
    )
    db.add(review)
    await db.flush()
    return review


async def _record_transition(
    db: AsyncSession,
    *,
    row: TeachNURContribution,
    candidate: TeachNURCandidate,
    event_type: str,
    audit_type: str,
    knowledge_version_id: uuid.UUID | None = None,
) -> None:
    await audit_service.record(
        db,
        event_type=audit_type,
        object_type="teach_nur_contribution",
        actor_user_id=row.owner_user_id,
        object_id=row.id,
        metadata={
            "status": row.status,
            "candidate_id": str(candidate.id),
            "knowledge_version_id": (
                str(knowledge_version_id) if knowledge_version_id else None
            ),
        },
    )
    transition_key = knowledge_version_id or uuid.uuid4()
    await emit_domain_event(
        db,
        owner_user_id=row.owner_user_id,
        event_type=event_type,
        aggregate_type="teach_nur_contribution",
        aggregate_id=row.id,
        idempotency_key=f"teach-nur:{row.id}:{event_type}:{transition_key}",
        payload={
            "status": row.status,
            "candidate_id": str(candidate.id),
            "knowledge_version_id": (
                str(knowledge_version_id) if knowledge_version_id else None
            ),
        },
    )


async def _assert_owned_orbit(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
) -> None:
    if orbit_id is None:
        return
    owned = (
        await db.execute(
            select(Orbit.id).where(
                Orbit.id == orbit_id,
                Orbit.owner_user_id == owner_user_id,
            )
        )
    ).scalar_one_or_none()
    if owned is None:
        raise TeachNURNotFoundError("Orbit not found.")
