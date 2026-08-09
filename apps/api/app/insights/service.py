"""Bounded, owner-scoped Agentic Insights projection and review service."""

from __future__ import annotations

import datetime as dt
import hashlib
import uuid
from dataclasses import dataclass

from sqlalchemy import func, select, text, tuple_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.cognition.correction_service import persist_user_correction
from app.core.config import get_settings
from app.insights.contracts import EvidenceCandidate, InsightDraft
from app.insights.quality import QUALITY_POLICY_VERSION, evaluate_quality, evidence_digest
from app.mind.why_changed import ChangeClass, EntityType, WhyChangedService
from app.models import (
    AMProject,
    AgentWorkflow,
    AuditEvent,
    CognitiveEvent,
    DomainEvent,
    Goal,
    Insight,
    InsightEvidenceRelation,
    InsightFeedback,
    InsightPattern,
    InsightProjectionCheckpoint,
    InsightProjectionRun,
    JournalEntry,
    OmegaExperience,
    Orbit,
    Outcome,
    Person,
    Plan,
    PlanStep,
    Prediction,
    ResearchSourceNote,
    SystemAction,
    TimelineEvent,
    UserCorrection,
)
from app.models._mixins import now_utc
from app.omega.experience_service import (
    ingest_from_cognitive_event,
    ingest_from_domain_event,
)


class InsightRunBusy(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateResult:
    insight: Insight | None
    suppressed_reason: str | None = None
    suppressed_insight_id: uuid.UUID | None = None


async def consolidate_owner(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    run_kind: str = "MANUAL",
    max_observations: int | None = None,
    idempotency_key: str | None = None,
    worker_id: str = "api",
) -> InsightProjectionRun:
    """Project new canonical events and synthesize at most two governed Insights."""
    settings = get_settings()
    run_kind = run_kind.upper()
    if run_kind not in {"EVENT", "MANUAL", "DAILY", "WEEKLY"}:
        raise ValueError("Unknown Insight consolidation run kind.")
    if idempotency_key:
        existing = await _idempotent_run(
            db, owner_user_id=owner_user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            return existing
    limit = min(
        max(1, max_observations or settings.insights_max_observations_per_run),
        settings.insights_max_observations_per_run,
    )
    checkpoint, claim_token = await _claim_checkpoint(
        db,
        owner_user_id=owner_user_id,
        worker_id=worker_id,
        lease_seconds=settings.insights_lease_seconds,
        max_attempts=settings.insights_max_attempts,
    )
    if idempotency_key:
        existing = await _idempotent_run(
            db, owner_user_id=owner_user_id, idempotency_key=idempotency_key
        )
        if existing is not None:
            _drop_checkpoint_claim(checkpoint, claim_token=claim_token)
            await db.flush()
            return existing
    run = InsightProjectionRun(
        owner_user_id=owner_user_id,
        idempotency_key=idempotency_key or f"{run_kind.lower()}:{uuid.uuid4()}",
        run_kind=run_kind,
        status="STARTED",
        max_observations=limit,
        quality_policy_version=QUALITY_POLICY_VERSION,
    )
    db.add(run)
    await db.flush()

    try:
        processed, has_more = await _project_new_observations(
            db,
            owner_user_id=owner_user_id,
            checkpoint=checkpoint,
            max_observations=limit,
        )
        run.processed_observations = processed
        run.invalidated_relations = await reconcile_invalid_sources(
            db, owner_user_id=owner_user_id, limit=limit * 4
        )

        experiences = list(
            (
                await db.execute(
                    select(OmegaExperience)
                    .where(
                        OmegaExperience.owner_user_id == owner_user_id,
                        OmegaExperience.invalidated_at.is_(None),
                    )
                    .order_by(OmegaExperience.observed_at.desc(), OmegaExperience.id.desc())
                    .limit(limit)
                )
            ).scalars()
        )
        main = await _synthesize_execution_pattern(
            db,
            owner_user_id=owner_user_id,
            experiences=experiences,
            run_kind=run_kind,
        )
        if main.insight is not None:
            run.surfaced_insight_id = main.insight.id
            run.generated_candidates += 1
        else:
            run.suppressed_reason = main.suppressed_reason
            run.suppressed_insight_id = main.suppressed_insight_id

        self_result = await _synthesize_nur_blind_spot(
            db, owner_user_id=owner_user_id, run_kind=run_kind
        )
        if self_result.insight is not None:
            run.self_insight_id = self_result.insight.id
            run.generated_candidates += 1

        run.input_counts = {
            "normalized_observations": len(experiences),
            "processed_observations": processed,
            "has_more": has_more,
            "privacy": "counts_only",
        }
        run.status = "COMPLETED"
        run.completed_at = now_utc()
        _release_checkpoint(
            checkpoint,
            claim_token=claim_token,
            status="COMPLETED",
            has_more=has_more,
        )
        await db.flush()
        return run
    except Exception as exc:
        run.status = "FAILED"
        run.error_class = exc.__class__.__name__
        run.completed_at = now_utc()
        _fail_checkpoint(checkpoint, claim_token=claim_token, exc=exc)
        await db.flush()
        raise


async def review_insight(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    insight_id: uuid.UUID,
    action: str,
    correction_text: str | None = None,
) -> Insight:
    """Apply one owner review action through correction, Hardness and WhyChanged."""
    row = await owned_insight(
        db, owner_user_id=owner_user_id, insight_id=insight_id, for_update=True
    )
    action = action.upper()
    transitions = {
        "THIS_FITS": ("ACCEPTED", "OWNER_CONFIRMED"),
        "NOT_RIGHT": ("REJECTED", "OWNER_REJECTED"),
        "CORRECT_NUR": ("CORRECTED", "OWNER_CORRECTED"),
    }
    if action not in transitions:
        raise ValueError("Unknown Insight review action.")
    if action == "CORRECT_NUR" and not (correction_text or "").strip():
        raise ValueError("An owner correction is required.")

    prior_status = row.lifecycle_status
    prior_version = row.insight_version
    legacy_status, lifecycle_status = transitions[action]
    source_correction: UserCorrection | None = None
    if action == "CORRECT_NUR":
        target_event_id = (
            await db.execute(
                select(InsightEvidenceRelation.source_event_id)
                .where(
                    InsightEvidenceRelation.owner_user_id == owner_user_id,
                    InsightEvidenceRelation.insight_id == row.id,
                    InsightEvidenceRelation.source_event_id.is_not(None),
                )
                .limit(1)
            )
        ).scalar_one_or_none()
        source_correction = await persist_user_correction(
            db,
            owner_user_id=owner_user_id,
            orbit_id=row.orbit_id,
            target_event_id=target_event_id,
            correction_text=(correction_text or "").strip(),
            reason=f"Insight correction for {row.id}",
        )
        row.correction = (correction_text or "").strip()
        row.insight_version += 1
    row.status = legacy_status
    row.lifecycle_status = lifecycle_status
    row.reviewed_at = now_utc()
    row.updated_at = now_utc()

    feedback = InsightFeedback(
        owner_user_id=owner_user_id,
        insight_id=row.id,
        action=action,
        correction_text=(correction_text or "").strip() or None,
        prior_lifecycle_status=prior_status,
        next_lifecycle_status=lifecycle_status,
        evidence_digest=row.evidence_digest,
        insight_version=row.insight_version,
        source_correction_id=source_correction.id if source_correction else None,
    )
    db.add(feedback)
    await db.flush()
    change_class = {
        "THIS_FITS": ChangeClass.PROMOTED,
        "NOT_RIGHT": ChangeClass.DEMOTED,
        "CORRECT_NUR": ChangeClass.CORRECTED,
    }[action]
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.INSIGHT,
        entity_id=str(row.id),
        change_class=change_class,
        trigger=f"Owner selected {action.replace('_', ' ').title()}.",
        previous_version=str(prior_version),
        new_version=str(row.insight_version),
        supporting_evidence=[f"feedback:{feedback.id}"],
        owner_correction=action == "CORRECT_NUR",
        actor="owner",
        affected_future_behavior=(
            "Future Insight calibration must treat this owner correction as higher authority."
            if action == "CORRECT_NUR"
            else "This evidence version will not resurface without material change."
            if action == "NOT_RIGHT"
            else "The candidate may be used only through owner-confirmed transitions."
        ),
        policy_version=QUALITY_POLICY_VERSION,
    )
    _record_insight_event(
        db,
        owner_user_id=owner_user_id,
        insight=row,
        event_type=f"insight.{action.lower()}",
        description=f"Owner review changed Insight from {prior_status} to {lifecycle_status}.",
    )
    await db.flush()
    return row


async def owned_insight(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    insight_id: uuid.UUID,
    for_update: bool = False,
) -> Insight:
    query = select(Insight).where(
        Insight.id == insight_id, Insight.owner_user_id == owner_user_id
    )
    if for_update:
        query = query.with_for_update()
    row = (await db.execute(query)).scalar_one_or_none()
    if row is None:
        raise LookupError("Insight not found.")
    return row


async def insight_evidence(
    db: AsyncSession, *, owner_user_id: uuid.UUID, insight_id: uuid.UUID
) -> list[tuple[InsightEvidenceRelation, bool]]:
    await owned_insight(db, owner_user_id=owner_user_id, insight_id=insight_id)
    rows = list(
        (
            await db.execute(
                select(InsightEvidenceRelation)
                .where(
                    InsightEvidenceRelation.owner_user_id == owner_user_id,
                    InsightEvidenceRelation.insight_id == insight_id,
                )
                .order_by(
                    InsightEvidenceRelation.relation,
                    InsightEvidenceRelation.source_occurred_at,
                    InsightEvidenceRelation.id,
                )
            )
        ).scalars()
    )
    return [
        (row, row.invalidated_at is None and await _source_exists(db, owner_user_id, row))
        for row in rows
    ]


async def reconcile_invalid_sources(
    db: AsyncSession, *, owner_user_id: uuid.UUID, limit: int
) -> int:
    relations = list(
        (
            await db.execute(
                select(InsightEvidenceRelation)
                .where(
                    InsightEvidenceRelation.owner_user_id == owner_user_id,
                    InsightEvidenceRelation.invalidated_at.is_(None),
                )
                .order_by(InsightEvidenceRelation.created_at.asc())
                .limit(min(max(limit, 1), 4000))
            )
        ).scalars()
    )
    invalidated = 0
    impacted: dict[uuid.UUID, set[uuid.UUID]] = {}
    now = now_utc()
    for relation in relations:
        if await _source_exists(db, owner_user_id, relation):
            continue
        relation.invalidated_at = now
        relation.invalidation_reason = "CANONICAL_SOURCE_MISSING"
        relation.evidence_summary = None
        invalidated += 1
        impacted.setdefault(relation.insight_id, set()).add(relation.source_id)
        if relation.observation_id:
            observation = (
                await db.execute(
                    select(OmegaExperience).where(
                        OmegaExperience.owner_user_id == owner_user_id,
                        OmegaExperience.id == relation.observation_id,
                    )
                )
            ).scalar_one_or_none()
            if observation is not None:
                observation.invalidated_at = now
                observation.summary = "[canonical source invalidated]"
                observation.raw_ref = None
                observation.features = {"invalidated": True}
    await db.flush()

    for insight_id, removed_ids in impacted.items():
        insight = await owned_insight(
            db, owner_user_id=owner_user_id, insight_id=insight_id, for_update=True
        )
        remaining_support = (
            await db.execute(
                select(func.count())
                .select_from(InsightEvidenceRelation)
                .where(
                    InsightEvidenceRelation.owner_user_id == owner_user_id,
                    InsightEvidenceRelation.insight_id == insight_id,
                    InsightEvidenceRelation.relation == "SUPPORTS",
                    InsightEvidenceRelation.invalidated_at.is_(None),
                )
            )
        ).scalar_one()
        next_status = "RETRACTED" if remaining_support < 2 else "SUPERSEDED"
        prior = insight.lifecycle_status
        insight.lifecycle_status = next_status
        insight.status = "ARCHIVED"
        insight.source_invalidated_at = now
        insight.updated_at = now
        removed = {str(value) for value in removed_ids}
        insight.evidence = [
            item for item in (insight.evidence or []) if str(item.get("id")) not in removed
        ]
        insight.counter_evidence = [
            item
            for item in (insight.counter_evidence or [])
            if str(item.get("id")) not in removed
        ]
        await WhyChangedService.record_change(
            db,
            owner_user_id=owner_user_id,
            entity_type=EntityType.INSIGHT,
            entity_id=str(insight.id),
            change_class=(
                ChangeClass.RETRACTED if next_status == "RETRACTED" else ChangeClass.SUPERSEDED
            ),
            trigger="Canonical source evidence was deleted or became unavailable.",
            previous_version=str(insight.insight_version),
            new_version=str(insight.insight_version),
            counter_evidence=[f"removed-source:{value}" for value in sorted(removed)],
            actor="system",
            affected_future_behavior="Invalidated evidence is excluded from future synthesis.",
            policy_version=QUALITY_POLICY_VERSION,
        )
        _record_insight_event(
            db,
            owner_user_id=owner_user_id,
            insight=insight,
            event_type="insight.source_invalidated",
            description=f"Insight moved from {prior} to {next_status} after source invalidation.",
        )
    return invalidated


async def _claim_checkpoint(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    worker_id: str,
    lease_seconds: int,
    max_attempts: int,
) -> tuple[InsightProjectionCheckpoint, uuid.UUID]:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:owner, 0))"),
        {"owner": str(owner_user_id)},
    )
    checkpoint = (
        await db.execute(
            select(InsightProjectionCheckpoint)
            .where(InsightProjectionCheckpoint.owner_user_id == owner_user_id)
            .with_for_update()
        )
    ).scalar_one_or_none()
    if checkpoint is None:
        checkpoint = InsightProjectionCheckpoint(
            owner_user_id=owner_user_id, max_attempts=max_attempts
        )
        db.add(checkpoint)
        await db.flush()
    now = now_utc()
    if checkpoint.claim_token and checkpoint.lease_expires_at and checkpoint.lease_expires_at > now:
        raise InsightRunBusy("Insight consolidation is already running for this owner.")
    if checkpoint.attempt_count >= max_attempts:
        raise InsightRunBusy("Insight consolidation reached its bounded retry ceiling.")
    token = uuid.uuid4()
    checkpoint.claim_token = token
    checkpoint.claimed_by = worker_id[:160]
    checkpoint.lease_expires_at = now + dt.timedelta(seconds=lease_seconds)
    checkpoint.max_attempts = max_attempts
    checkpoint.updated_at = now
    await db.flush()
    return checkpoint, token


async def _idempotent_run(
    db: AsyncSession, *, owner_user_id: uuid.UUID, idempotency_key: str
) -> InsightProjectionRun | None:
    return (
        await db.execute(
            select(InsightProjectionRun).where(
                InsightProjectionRun.owner_user_id == owner_user_id,
                InsightProjectionRun.idempotency_key == idempotency_key,
            )
        )
    ).scalar_one_or_none()


def _drop_checkpoint_claim(
    checkpoint: InsightProjectionCheckpoint, *, claim_token: uuid.UUID
) -> None:
    if checkpoint.claim_token != claim_token:
        raise InsightRunBusy("Insight checkpoint lease was lost.")
    checkpoint.claim_token = None
    checkpoint.claimed_by = None
    checkpoint.lease_expires_at = None
    checkpoint.updated_at = now_utc()


def _release_checkpoint(
    checkpoint: InsightProjectionCheckpoint,
    *,
    claim_token: uuid.UUID,
    status: str,
    has_more: bool,
) -> None:
    if checkpoint.claim_token != claim_token:
        raise InsightRunBusy("Insight checkpoint lease was lost.")
    now = now_utc()
    checkpoint.claim_token = None
    checkpoint.claimed_by = None
    checkpoint.lease_expires_at = None
    checkpoint.last_run_at = now
    checkpoint.last_run_status = status
    checkpoint.last_error_class = None
    checkpoint.attempt_count = 0
    checkpoint.pending_event_count = 1 if has_more else 0
    checkpoint.pending_since = now if has_more else None
    checkpoint.next_eligible_at = now if has_more else None
    checkpoint.updated_at = now


def _fail_checkpoint(
    checkpoint: InsightProjectionCheckpoint, *, claim_token: uuid.UUID, exc: Exception
) -> None:
    if checkpoint.claim_token != claim_token:
        return
    checkpoint.claim_token = None
    checkpoint.claimed_by = None
    checkpoint.lease_expires_at = None
    checkpoint.attempt_count += 1
    checkpoint.last_run_status = "FAILED"
    checkpoint.last_error_class = exc.__class__.__name__[:120]
    checkpoint.next_eligible_at = now_utc() + dt.timedelta(
        minutes=min(60, 2 ** min(checkpoint.attempt_count, 5))
    )
    checkpoint.updated_at = now_utc()


async def _project_new_observations(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    checkpoint: InsightProjectionCheckpoint,
    max_observations: int,
) -> tuple[int, bool]:
    processed = 0
    cognitive_query = select(CognitiveEvent).where(
        CognitiveEvent.owner_user_id == owner_user_id
    )
    if checkpoint.last_cognitive_event_at and checkpoint.last_cognitive_event_id:
        cognitive_query = cognitive_query.where(
            tuple_(CognitiveEvent.created_at, CognitiveEvent.id)
            > tuple_(checkpoint.last_cognitive_event_at, checkpoint.last_cognitive_event_id)
        )
    cognitive_rows = list(
        (
            await db.execute(
                cognitive_query.order_by(CognitiveEvent.created_at, CognitiveEvent.id).limit(
                    max_observations + 1
                )
            )
        ).scalars()
    )
    cognitive_more = len(cognitive_rows) > max_observations
    for event in cognitive_rows[:max_observations]:
        await _ingest_cognitive_once(db, owner_user_id=owner_user_id, event=event)
        checkpoint.last_cognitive_event_at = event.created_at
        checkpoint.last_cognitive_event_id = event.id
        processed += 1
    if cognitive_more or processed >= max_observations:
        return processed, True

    remaining = max_observations - processed
    domain_query = select(DomainEvent).where(DomainEvent.owner_user_id == owner_user_id)
    if checkpoint.last_domain_event_at and checkpoint.last_domain_event_id:
        domain_query = domain_query.where(
            tuple_(DomainEvent.occurred_at, DomainEvent.id)
            > tuple_(checkpoint.last_domain_event_at, checkpoint.last_domain_event_id)
        )
    domain_rows = list(
        (
            await db.execute(
                domain_query.order_by(DomainEvent.occurred_at, DomainEvent.id).limit(
                    remaining + 1
                )
            )
        ).scalars()
    )
    domain_more = len(domain_rows) > remaining
    for event in domain_rows[:remaining]:
        await _ingest_domain_once(db, owner_user_id=owner_user_id, event=event)
        checkpoint.last_domain_event_at = event.occurred_at
        checkpoint.last_domain_event_id = event.id
        processed += 1
    return processed, domain_more


async def _ingest_cognitive_once(
    db: AsyncSession, *, owner_user_id: uuid.UUID, event: CognitiveEvent
) -> None:
    existing = (
        await db.execute(
            select(OmegaExperience.id).where(
                OmegaExperience.owner_user_id == owner_user_id,
                OmegaExperience.source_kind == "COGNITIVE_EVENT",
                OmegaExperience.source_id == event.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    try:
        async with db.begin_nested():
            await ingest_from_cognitive_event(
                db, owner_user_id=owner_user_id, event=event
            )
    except IntegrityError:
        return


async def _ingest_domain_once(
    db: AsyncSession, *, owner_user_id: uuid.UUID, event: DomainEvent
) -> None:
    existing = (
        await db.execute(
            select(OmegaExperience.id).where(
                OmegaExperience.owner_user_id == owner_user_id,
                OmegaExperience.source_kind == "DOMAIN_EVENT",
                OmegaExperience.source_id == event.id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        return
    try:
        async with db.begin_nested():
            await ingest_from_domain_event(db, owner_user_id=owner_user_id, event=event)
    except IntegrityError:
        return


async def _synthesize_execution_pattern(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    experiences: list[OmegaExperience],
    run_kind: str,
) -> CandidateResult:
    evidence = _pattern_evidence(experiences)
    support = tuple(row for row in evidence if row.relation == "SUPPORTS")
    counter = tuple(row for row in evidence if row.relation == "CONTRADICTS")
    if len(support) < 2 or not counter:
        return CandidateResult(None, "INSUFFICIENT_RELIABLE_EVIDENCE")
    domains = tuple(sorted({row.source_domain for row in support + counter}))
    start, end = _evidence_window(support + counter)
    draft = InsightDraft(
        insight_type="EXECUTION_PATTERN",
        title="Bounded proof appears more returnable than oversized action",
        claim=(
            f"Across {len(support)} returned or completed records in {len(domains)} "
            f"canonical domains, bounded execution is associated with return. "
            f"{len(counter)} missed or reopened record(s) show that the association is "
            "conditional; this does not establish motive or causation."
        ),
        epistemic_state="INFERRED",
        time_scale=_time_scale(start, end),
        source_domains=domains,
        supporting_evidence=support,
        counter_evidence=counter,
        assumptions=(
            "Recorded completions and misses represent only NUR-visible activity.",
            "Action size and return are associated here; no causal mechanism is established.",
        ),
        alternative_explanations=(
            "External support or a changed dependency may explain the returned outcomes.",
            "Large actions may have been correctly deprioritized after new information.",
            "Unrecorded work may change the apparent completion balance.",
        ),
        uncertainty=(
            "NUR may be over-weighting recorded action size and under-weighting external "
            "support, changed priority, or activity that was never entered into NUR."
        ),
        positive_interpretation=(
            "The owner has repeatedly produced inspectable outcomes across distinct domains."
        ),
        hard_interpretation=(
            "The missed record suggests continuity weakens when the next unit remains too large."
        ),
        suggested_action="Choose one next proof that can be returned in a single bounded session.",
        affected_system_slug=_first_feature(experiences, "system_slug"),
        affected_goal_id=_first_uuid_feature(experiences, "goal_id", "GOAL"),
        affected_project_id=_first_uuid_feature(experiences, "project_id", "AM_PROJECT"),
        orbit_id=next((row.orbit_id for row in experiences if row.orbit_id), None),
        window_start_iso=start.isoformat() if start else None,
        window_end_iso=end.isoformat() if end else None,
    )
    return await _persist_candidate(
        db,
        owner_user_id=owner_user_id,
        pattern_type="EXECUTION_PATTERN",
        pattern_key="execution-return-v1",
        draft=draft,
        run_kind=run_kind,
    )


async def _synthesize_nur_blind_spot(
    db: AsyncSession, *, owner_user_id: uuid.UUID, run_kind: str
) -> CandidateResult:
    feedback = list(
        (
            await db.execute(
                select(InsightFeedback)
                .where(
                    InsightFeedback.owner_user_id == owner_user_id,
                    InsightFeedback.action.in_(["NOT_RIGHT", "CORRECT_NUR"]),
                )
                .order_by(InsightFeedback.created_at.desc())
                .limit(20)
            )
        ).scalars()
    )
    if len({row.insight_id for row in feedback}) < 2:
        return CandidateResult(None, "INSUFFICIENT_CALIBRATION_FEEDBACK")
    support = tuple(
        EvidenceCandidate(
            source_kind="INSIGHT_FEEDBACK",
            source_id=row.id,
            source_domain="CORRECTION" if row.action == "CORRECT_NUR" else "INSIGHTS",
            relation="SUPPORTS",
            provenance_label="OWNER_REVIEW",
            explicitness="OWNER_EXPLICIT",
            confidence=1.0,
            source_feedback_id=row.id,
            evidence_summary=f"Owner selected {row.action.replace('_', ' ').title()}.",
            occurred_at_iso=row.created_at.isoformat(),
        )
        for row in feedback[:6]
    )
    first_source = feedback[0].insight_id
    source_insight = await owned_insight(
        db, owner_user_id=owner_user_id, insight_id=first_source
    )
    counter = (
        EvidenceCandidate(
            source_kind="INSIGHT",
            source_id=source_insight.id,
            source_domain="INSIGHTS",
            relation="CONTRADICTS",
            provenance_label="DETERMINISTIC_QUALITY_GATE",
            explicitness="SYSTEM_OBSERVED",
            confidence=max(0.0, min(1.0, source_insight.confidence)),
            source_insight_id=source_insight.id,
            evidence_summary=(
                "The source candidate passed the evidence gate, so the recurring issue may "
                "concern interpretation rather than absent evidence."
            ),
            occurred_at_iso=source_insight.created_at.isoformat(),
        ),
    )
    start, end = _evidence_window(support + counter)
    draft = InsightDraft(
        insight_type="NUR_BLIND_SPOT",
        title="NUR may be repeating an inference calibration error",
        claim=(
            f"The owner rejected or corrected {len(support)} recent Insight interpretations "
            "across more than one review context. NUR should lower authority for this "
            "inference class and request owner confirmation; it must not silently alter policy."
        ),
        epistemic_state="INFERRED",
        time_scale=_time_scale(start, end),
        source_domains=tuple(sorted({row.source_domain for row in support + counter})),
        supporting_evidence=support,
        counter_evidence=counter,
        assumptions=("Repeated owner review actions concern a related inference class.",),
        alternative_explanations=(
            "The individual Insights may have failed for different reasons.",
            "The deterministic evidence gate may be sound while language synthesis is too broad.",
        ),
        uncertainty=(
            "The feedback sample is still small and does not show that every NUR inference in "
            "this domain is unreliable."
        ),
        positive_interpretation="Owner correction is actively improving NUR's calibration ledger.",
        hard_interpretation="Repeating the same inference after correction would violate owner authority.",
        suggested_action="Review the shared assumption before promoting any related learning change.",
        calibration_target="NUR_INFERENCE",
        window_start_iso=start.isoformat() if start else None,
        window_end_iso=end.isoformat() if end else None,
    )
    return await _persist_candidate(
        db,
        owner_user_id=owner_user_id,
        pattern_type="NUR_BLIND_SPOT",
        pattern_key="nur-owner-correction-calibration-v1",
        draft=draft,
        run_kind=run_kind,
    )


async def _persist_candidate(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    pattern_type: str,
    pattern_key: str,
    draft: InsightDraft,
    run_kind: str,
) -> CandidateResult:
    verdict = evaluate_quality(draft)
    if not verdict.passes:
        return CandidateResult(None, "QUALITY_GATE:" + ",".join(verdict.reason_codes))
    all_evidence = draft.supporting_evidence + draft.counter_evidence
    digest = evidence_digest(all_evidence)
    fingerprint = hashlib.sha256(pattern_key.encode("ascii")).hexdigest()
    exact = (
        await db.execute(
            select(Insight).where(
                Insight.owner_user_id == owner_user_id,
                Insight.pattern_fingerprint == fingerprint,
                Insight.evidence_digest == digest,
            )
        )
    ).scalar_one_or_none()
    if exact is not None:
        reason = (
            "UNCHANGED_REJECTED_EVIDENCE"
            if exact.lifecycle_status == "OWNER_REJECTED"
            else "UNCHANGED_EVIDENCE"
        )
        return CandidateResult(None, reason, exact.id)

    pattern = (
        await db.execute(
            select(InsightPattern)
            .where(
                InsightPattern.owner_user_id == owner_user_id,
                InsightPattern.fingerprint == fingerprint,
            )
            .with_for_update()
        )
    ).scalar_one_or_none()
    start = _as_datetime(draft.window_start_iso)
    end = _as_datetime(draft.window_end_iso)
    if pattern is None:
        pattern = InsightPattern(
            owner_user_id=owner_user_id,
            fingerprint=fingerprint,
            pattern_type=pattern_type,
            time_scale=draft.time_scale,
        )
        db.add(pattern)
    elif (pattern.feature_summary or {}).get("evidence_digest") != digest:
        pattern.version += 1
    pattern.time_scale = draft.time_scale
    pattern.source_domains = list(draft.source_domains)
    pattern.feature_summary = {
        "evidence_digest": digest,
        "quality_policy_version": QUALITY_POLICY_VERSION,
    }
    pattern.support_count = len(draft.supporting_evidence)
    pattern.counter_count = len(draft.counter_evidence)
    pattern.source_diversity = verdict.source_diversity
    pattern.first_observed_at = start
    pattern.last_observed_at = end
    pattern.status = "ACTIVE"
    pattern.updated_at = now_utc()
    await db.flush()

    prior = (
        await db.execute(
            select(Insight)
            .where(
                Insight.owner_user_id == owner_user_id,
                Insight.pattern_fingerprint == fingerprint,
            )
            .order_by(Insight.insight_version.desc())
            .limit(1)
            .with_for_update()
        )
    ).scalar_one_or_none()
    version = (prior.insight_version + 1) if prior else 1
    lifecycle = (
        "REVIEW_REQUIRED"
        if prior and prior.lifecycle_status in {"OWNER_CONFIRMED", "OWNER_CORRECTED"}
        else "SURFACED"
    )
    if prior and lifecycle == "SURFACED":
        prior.lifecycle_status = "SUPERSEDED"
        prior.status = "ARCHIVED"
        prior.updated_at = now_utc()

    insight = Insight(
        owner_user_id=owner_user_id,
        orbit_id=draft.orbit_id,
        insight_type=draft.insight_type,
        title=draft.title,
        claim=draft.claim,
        tone="DIRECT",
        confidence=verdict.quality_score / 10_000,
        valence="MIXED",
        source_event_ids=[
            str(row.source_event_id) for row in all_evidence if row.source_event_id
        ],
        source_memory_ids=[],
        source_research_ids=[
            str(row.source_id)
            for row in all_evidence
            if row.source_kind == "RESEARCH_SOURCE_NOTE"
        ],
        affected_system_slug=draft.affected_system_slug,
        affected_goal_id=draft.affected_goal_id,
        affected_project_id=draft.affected_project_id,
        affected_person_id=draft.affected_person_id,
        evidence=[_legacy_evidence(row) for row in draft.supporting_evidence],
        counter_evidence=[_legacy_evidence(row) for row in draft.counter_evidence],
        what_nur_may_be_wrong_about=draft.uncertainty,
        positive_interpretation=draft.positive_interpretation,
        hard_interpretation=draft.hard_interpretation,
        suggested_action=draft.suggested_action,
        status="CANDIDATE",
        provenance_label="INFERRED_CROSS_DOMAIN_OWNER_LEDGER",
        pattern_id=pattern.id,
        parent_insight_id=prior.id if prior else None,
        lifecycle_status=lifecycle,
        epistemic_state=draft.epistemic_state,
        insight_version=version,
        pattern_fingerprint=fingerprint,
        evidence_digest=digest,
        time_scale=draft.time_scale,
        time_window_start=start,
        time_window_end=end,
        source_domains=list(draft.source_domains),
        source_diversity=verdict.source_diversity,
        alternative_explanations=list(draft.alternative_explanations),
        assumptions=list(draft.assumptions),
        contradictions=[
            row.evidence_summary for row in draft.counter_evidence if row.evidence_summary
        ],
        confidence_basis={
            "support_score": verdict.support_score,
            "counter_score": verdict.counter_score,
            "source_diversity": verdict.source_diversity,
            "deterministic": True,
        },
        quality_dimensions={
            "passes": verdict.passes,
            "quality_score": verdict.quality_score,
            "reason_codes": list(verdict.reason_codes),
        },
        quality_policy_version=QUALITY_POLICY_VERSION,
        calibration_target=draft.calibration_target,
        surfaced_at=now_utc() if lifecycle == "SURFACED" else None,
        cooldown_until=now_utc()
        + dt.timedelta(hours=get_settings().insights_cooldown_hours),
    )
    db.add(insight)
    await db.flush()
    for evidence in all_evidence:
        db.add(
            InsightEvidenceRelation(
                owner_user_id=owner_user_id,
                insight_id=insight.id,
                observation_id=evidence.observation_id,
                source_event_id=evidence.source_event_id,
                source_domain_event_id=evidence.source_domain_event_id,
                source_insight_id=evidence.source_insight_id,
                source_feedback_id=evidence.source_feedback_id,
                source_kind=evidence.source_kind,
                source_id=evidence.source_id,
                source_domain=evidence.source_domain,
                relation=evidence.relation,
                provenance_label=evidence.provenance_label,
                explicitness=evidence.explicitness,
                confidence=evidence.confidence,
                source_fingerprint=evidence.source_fingerprint,
                evidence_summary=(evidence.evidence_summary or "")[:1000] or None,
                source_occurred_at=_as_datetime(evidence.occurred_at_iso),
                insight_version=version,
            )
        )
    await db.flush()
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.INSIGHT,
        entity_id=str(insight.id),
        change_class=ChangeClass.CREATED,
        trigger=(
            "Materially new cross-domain evidence passed the versioned quality gate."
            if prior
            else "Cross-domain evidence passed the versioned quality gate."
        ),
        previous_version=str(prior.insight_version) if prior else None,
        new_version=str(version),
        supporting_evidence=[
            f"{row.source_kind}:{row.source_id}" for row in draft.supporting_evidence
        ],
        counter_evidence=[
            f"{row.source_kind}:{row.source_id}" for row in draft.counter_evidence
        ],
        actor="scheduler" if run_kind != "MANUAL" else "owner",
        affected_future_behavior="Candidate is reviewable; it is not persistent owner truth.",
        rollback_target=str(prior.id) if prior else None,
        policy_version=QUALITY_POLICY_VERSION,
    )
    if prior and lifecycle == "SURFACED":
        await WhyChangedService.record_change(
            db,
            owner_user_id=owner_user_id,
            entity_type=EntityType.INSIGHT,
            entity_id=str(prior.id),
            change_class=ChangeClass.SUPERSEDED,
            trigger="A materially changed evidence digest produced a new candidate version.",
            previous_version=str(prior.insight_version),
            new_version=str(version),
            supporting_evidence=[f"insight:{insight.id}"],
            actor="system",
            rollback_target=str(prior.id),
            policy_version=QUALITY_POLICY_VERSION,
        )
    _record_insight_event(
        db,
        owner_user_id=owner_user_id,
        insight=insight,
        event_type="insight.surfaced",
        description=(
            f"Cross-domain {draft.epistemic_state.lower()} Insight version {version} "
            "passed deterministic review."
        ),
    )
    await db.flush()
    return CandidateResult(insight)


def _pattern_evidence(
    experiences: list[OmegaExperience],
) -> tuple[EvidenceCandidate, ...]:
    selected: dict[tuple[str, uuid.UUID], EvidenceCandidate] = {}
    for experience in experiences:
        if experience.source_domain in {"INSIGHTS", "CORRECTION"}:
            continue
        signal = str((experience.features or {}).get("signal") or "CONTEXT")
        if signal not in {"SUPPORT", "COUNTER"}:
            continue
        source_kind, source_id = _experience_source(experience)
        if source_id is None:
            continue
        relation = "SUPPORTS" if signal == "SUPPORT" else "CONTRADICTS"
        key = (source_kind, source_id)
        if key in selected:
            continue
        selected[key] = EvidenceCandidate(
            source_kind=source_kind,
            source_id=source_id,
            source_domain=experience.source_domain,
            relation=relation,
            provenance_label=experience.provenance_label,
            explicitness=experience.explicitness,
            confidence=experience.confidence,
            observation_id=experience.id,
            source_event_id=(
                experience.source_id
                if experience.source_kind == "COGNITIVE_EVENT"
                else None
            ),
            source_domain_event_id=(
                experience.source_id if experience.source_kind == "DOMAIN_EVENT" else None
            ),
            source_fingerprint=experience.source_fingerprint,
            evidence_summary=experience.summary[:500],
            occurred_at_iso=experience.observed_at.isoformat(),
        )
    return tuple(selected.values())


def _experience_source(experience: OmegaExperience) -> tuple[str, uuid.UUID | None]:
    features = experience.features or {}
    source_kind = str(features.get("canonical_source_kind") or experience.source_kind)
    raw_id = features.get("canonical_source_id") or experience.source_id
    try:
        return source_kind, uuid.UUID(str(raw_id))
    except (TypeError, ValueError, AttributeError):
        return source_kind, None


def _record_insight_event(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    insight: Insight,
    event_type: str,
    description: str,
) -> None:
    now = now_utc()
    db.add(
        CognitiveEvent(
            owner_user_id=owner_user_id,
            orbit_id=insight.orbit_id,
            event_kind="SYSTEM_EVENT",
            content_text=description,
            source_ref=f"insight:{insight.id}",
            structured_payload={
                "timeline_kind": event_type.upper().replace(".", "_"),
                "insight_id": str(insight.id),
                "insight_version": insight.insight_version,
                "lifecycle_status": insight.lifecycle_status,
                "provenance_label": insight.provenance_label,
            },
        )
    )
    db.add(
        TimelineEvent(
            owner_user_id=owner_user_id,
            event_type=event_type.upper().replace(".", "_")[:64],
            title=insight.title,
            description=description,
            time_kind="PAST",
            occurred_at=now,
            source_type="INSIGHT",
            source_id=insight.id,
            system_slug=insight.affected_system_slug,
            orbit_id=insight.orbit_id,
            status="COMPLETED",
            importance=75,
            event_payload={
                "insight_type": insight.insight_type,
                "lifecycle_status": insight.lifecycle_status,
                "insight_version": insight.insight_version,
            },
        )
    )
    db.add(
        DomainEvent(
            owner_user_id=owner_user_id,
            event_type=event_type,
            aggregate_type="insight",
            aggregate_id=insight.id,
            event_payload={
                "lifecycle_status": insight.lifecycle_status,
                "insight_version": insight.insight_version,
            },
            idempotency_key=(
                f"{event_type}:{insight.id}:{insight.insight_version}:"
                f"{insight.lifecycle_status}"
            ),
        )
    )
    db.add(
        AuditEvent(
            actor_user_id=owner_user_id,
            event_type=event_type[:64],
            object_type="insight",
            object_id=insight.id,
            event_metadata={
                "lifecycle_status": insight.lifecycle_status,
                "insight_version": insight.insight_version,
                "no_chain_of_thought": True,
            },
        )
    )


_SOURCE_MODELS = {
    "AGENT_WORKFLOW": AgentWorkflow,
    "AM_PROJECT": AMProject,
    "COGNITIVE_EVENT": CognitiveEvent,
    "DOMAIN_EVENT": DomainEvent,
    "GOAL": Goal,
    "INSIGHT": Insight,
    "INSIGHT_FEEDBACK": InsightFeedback,
    "JOURNAL_ENTRY": JournalEntry,
    "ORBIT": Orbit,
    "OUTCOME": Outcome,
    "PERSON": Person,
    "PLAN": Plan,
    "PLAN_STEP": PlanStep,
    "PREDICTION": Prediction,
    "RESEARCH_SOURCE_NOTE": ResearchSourceNote,
    "SYSTEM_ACTION": SystemAction,
    "TIMELINE_EVENT": TimelineEvent,
    "USER_CORRECTION": UserCorrection,
}


async def _source_exists(
    db: AsyncSession, owner_user_id: uuid.UUID, relation: InsightEvidenceRelation
) -> bool:
    model = _SOURCE_MODELS.get(relation.source_kind)
    if model is None:
        return False
    return (
        await db.execute(
            select(model.id).where(
                model.id == relation.source_id,
                _owner_column(model) == owner_user_id,
            )
        )
    ).scalar_one_or_none() is not None


def _owner_column(model):
    return model.actor_user_id if model is AuditEvent else model.owner_user_id


def _legacy_evidence(row: EvidenceCandidate) -> dict:
    return {
        "kind": row.source_kind,
        "id": str(row.source_id),
        "domain": row.source_domain,
        "relation": row.relation,
        "excerpt": (row.evidence_summary or "")[:280],
        "provenance_label": row.provenance_label,
        "explicitness": row.explicitness,
    }


def _evidence_window(
    evidence: tuple[EvidenceCandidate, ...]
) -> tuple[dt.datetime | None, dt.datetime | None]:
    values = [
        value
        for value in (_as_datetime(row.occurred_at_iso) for row in evidence)
        if value is not None
    ]
    return (min(values), max(values)) if values else (None, None)


def _time_scale(start: dt.datetime | None, end: dt.datetime | None) -> str:
    if start is None or end is None:
        return "FAST"
    span = end - start
    if span >= dt.timedelta(days=28):
        return "LONGITUDINAL"
    if span >= dt.timedelta(days=1):
        return "DAILY_WEEKLY"
    return "FAST"


def _as_datetime(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(value)


def _first_feature(experiences: list[OmegaExperience], key: str) -> str | None:
    for experience in experiences:
        value = (experience.features or {}).get(key)
        if value:
            return str(value)
    return None


def _first_uuid_feature(
    experiences: list[OmegaExperience], key: str, source_kind: str
) -> uuid.UUID | None:
    for experience in experiences:
        value = (experience.features or {}).get(key)
        if value:
            try:
                return uuid.UUID(str(value))
            except ValueError:
                pass
        kind, source_id = _experience_source(experience)
        if kind == source_kind and source_id:
            return source_id
    return None
