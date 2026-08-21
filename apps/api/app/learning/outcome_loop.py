"""Governed feedback closure for observed outcomes and owner corrections.

This module connects already-canonical evidence to NUR's existing learning,
memory, belief, and WhyChanged stores.  It deliberately stops before promotion:
Hardness candidates are screened and selected for review, while durable memory
still requires explicit owner approval and model weights are never changed here.
"""
from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.candidates import (
    apply_selector_judgment,
    assess_candidate_risks,
    ingest_candidate_from_signal,
)
from app.learning.hardness.schemas import LearningSignalKind
from app.learning.hardness.selector import CurriculumSelector
from app.learning.hardness.signals import persist_learning_signal
from app.mind.why_changed import ChangeClass, EntityType, WhyChangedService
from app.models import (
    ClaimEvidence,
    CognitiveEvent,
    LearningCandidateRecord,
    LearningSignalRecord,
    MemoryCandidate,
    MemoryEdge,
    MemoryVersion,
    Outcome,
    PersonalMemory,
    Prediction,
    SemanticClaim,
    UserCorrection,
    WhyChangedRecordRow,
)


@dataclass(frozen=True, slots=True)
class LearningFeedbackResult:
    event_id: uuid.UUID
    signal_id: uuid.UUID | None
    learning_candidate_id: uuid.UUID | None
    memory_candidate_id: uuid.UUID
    claim_id: uuid.UUID


def _claim_status(evidence: int, counterevidence: int) -> str:
    if counterevidence > evidence:
        return "DISPUTED"
    if evidence and counterevidence:
        return "MIXED"
    if evidence >= 2:
        return "SUPPORTED"
    return "EMERGING"


async def _lock_feedback(db: AsyncSession, owner_user_id: uuid.UUID, key: str) -> None:
    await db.execute(
        text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
        {"key": f"{owner_user_id}:{key}"},
    )


async def _record_change_once(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    entity_type: EntityType,
    entity_id: str,
    change_class: ChangeClass,
    trigger: str,
    evidence: list[str],
    counterevidence: list[str] | None = None,
    owner_correction: bool = False,
    actor: str = "system",
    affected_future_behavior: str,
    previous_version: str | None = None,
    new_version: str | None = None,
) -> None:
    existing = await db.scalar(
        select(WhyChangedRecordRow.id).where(
            WhyChangedRecordRow.owner_user_id == owner_user_id,
            WhyChangedRecordRow.entity_type == entity_type.value,
            WhyChangedRecordRow.entity_id == entity_id,
            WhyChangedRecordRow.trigger == trigger,
        )
    )
    if existing is not None:
        return
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=entity_type,
        entity_id=entity_id,
        change_class=change_class,
        trigger=trigger,
        previous_version=previous_version,
        new_version=new_version,
        supporting_evidence=evidence,
        counter_evidence=counterevidence or [],
        owner_correction=owner_correction,
        actor=actor,
        affected_future_behavior=affected_future_behavior,
    )


async def _stage_hardness_candidate(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    source_event_id: uuid.UUID,
    signal_kind: LearningSignalKind,
    idempotency_key: str,
    task_class: str,
    summary: str,
    desired_behavior: str,
    failure_signature: str | None,
    structured_payload: dict,
    source_correction_id: uuid.UUID | None = None,
) -> tuple[LearningSignalRecord, LearningCandidateRecord]:
    signal = await persist_learning_signal(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        source_event_id=source_event_id,
        source_correction_id=source_correction_id,
        idempotency_key=idempotency_key,
        signal_kind=signal_kind,
        task_class=task_class,
        summary=summary,
        structured_payload=structured_payload,
    )
    candidate = await ingest_candidate_from_signal(
        db,
        signal=signal,
        failure_signature=failure_signature,
        desired_behavior=desired_behavior,
    )
    assess_candidate_risks(candidate)
    await db.flush()
    candidate = (
        await apply_selector_judgment(
            db,
            candidate_id=candidate.id,
            judgment=CurriculumSelector().evaluate_candidate(candidate),
        )
        or candidate
    )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.LEARNING_CANDIDATE,
        entity_id=str(candidate.id),
        change_class=ChangeClass.CREATED,
        trigger=idempotency_key,
        evidence=[f"learning_signal:{signal.id}"],
        affected_future_behavior=(
            "The candidate is available to governed curriculum review only; "
            "no checkpoint, policy, or production behavior changed."
        ),
    )
    return signal, candidate


async def _memory_candidate(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    event_id: uuid.UUID,
    feedback_key: str,
    candidate_text: str,
    provenance_label: str,
    created_by: str,
    source_object_ids: dict,
) -> MemoryCandidate:
    row = await db.scalar(
        select(MemoryCandidate).where(
            MemoryCandidate.owner_user_id == owner_user_id,
            MemoryCandidate.source_event_id == event_id,
            MemoryCandidate.source_object_ids["feedback_key"].astext == feedback_key,
        )
    )
    if row is not None:
        return row
    row = MemoryCandidate(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        source_event_id=event_id,
        candidate_text=candidate_text,
        original_text=candidate_text,
        scope="LEARNING_CANDIDATE",
        memory_type="SEMANTIC",
        provenance_label=provenance_label,
        confidence=0.9 if created_by == "OWNER" else 0.7,
        sensitivity="PRIVATE",
        created_by=created_by,
        source_object_ids={"feedback_key": feedback_key, **source_object_ids},
        status="CANDIDATE",
        review_note="Owner review is required before this can become durable memory.",
    )
    db.add(row)
    await db.flush()
    return row


async def _upsert_claim_evidence(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    subject_ref: str,
    claim_text: str,
    event_id: uuid.UUID,
    supports: bool | None,
    rationale: str,
    outcome_id: uuid.UUID | None = None,
    existing_claim: SemanticClaim | None = None,
    mixed_evidence: bool = False,
) -> SemanticClaim:
    claim = existing_claim or await db.scalar(
        select(SemanticClaim).where(
            SemanticClaim.owner_user_id == owner_user_id,
            SemanticClaim.subject_ref == subject_ref,
        )
    )
    if claim is None:
        claim = SemanticClaim(
            owner_user_id=owner_user_id,
            claim_text=claim_text,
            subject_ref=subject_ref,
            predicate="revised_by_observed_evidence",
            confidence=0.5,
        )
        db.add(claim)
        await db.flush()

    desired = [True, False] if mixed_evidence else ([] if supports is None else [supports])
    # An explicitly partial comparison carries both supporting and counter
    # evidence. An omitted classification carries neither: absence is not proof.
    for verdict in desired:
        filters = [
            ClaimEvidence.owner_user_id == owner_user_id,
            ClaimEvidence.claim_id == claim.id,
            ClaimEvidence.supports.is_(verdict),
        ]
        if outcome_id is not None:
            filters.append(ClaimEvidence.outcome_id == outcome_id)
        else:
            filters.append(ClaimEvidence.event_id == event_id)
        if await db.scalar(select(ClaimEvidence.id).where(*filters)) is not None:
            continue
        db.add(
            ClaimEvidence(
                owner_user_id=owner_user_id,
                claim_id=claim.id,
                event_id=event_id if outcome_id is None else None,
                outcome_id=outcome_id,
                supports=verdict,
                rationale=rationale,
            )
        )
        if verdict:
            claim.evidence_count += 1
        else:
            claim.counterevidence_count += 1

    claim.status = _claim_status(claim.evidence_count, claim.counterevidence_count)
    claim.confidence = max(
        0.05,
        min(
            0.95,
            0.5 + 0.1 * claim.evidence_count - 0.15 * claim.counterevidence_count,
        ),
    )
    claim.last_evaluated_at = dt.datetime.now(dt.UTC)
    return claim


async def reconcile_prediction_resolution(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    prediction: Prediction,
) -> LearningFeedbackResult:
    """Close a prediction against observed evidence without auto-promoting it."""
    feedback_key = f"prediction:{prediction.id}:resolution"
    await _lock_feedback(db, owner_user_id, feedback_key)
    event = await db.scalar(
        select(CognitiveEvent).where(
            CognitiveEvent.owner_user_id == owner_user_id,
            CognitiveEvent.source_ref == f"prediction_resolution:{prediction.id}",
        )
    )
    if event is None:
        event = CognitiveEvent(
            owner_user_id=owner_user_id,
            orbit_id=prediction.orbit_id,
            event_kind="OUTCOME_REPORTED",
            content_text=(prediction.learning or f"Prediction resolved: {prediction.resolution}"),
            source_ref=f"prediction_resolution:{prediction.id}",
            structured_payload={
                "prediction_id": str(prediction.id),
                "resolution": prediction.resolution,
                "assumptions": prediction.assumptions,
            },
        )
        db.add(event)
        await db.flush()
    prediction.outcome_event_id = event.id

    kind = {
        "CONFIRMED": LearningSignalKind.SUCCESSFUL_NOVEL_SOLUTION,
        "PARTIALLY_CONFIRMED": LearningSignalKind.CALIBRATION_ERROR,
        "CONTRADICTED": LearningSignalKind.OUTCOME_MISS,
    }[prediction.resolution or "PARTIALLY_CONFIRMED"]
    learning = (prediction.learning or f"Review prediction: {prediction.statement}").strip()
    signal, learning_candidate = await _stage_hardness_candidate(
        db,
        owner_user_id=owner_user_id,
        orbit_id=prediction.orbit_id,
        source_event_id=event.id,
        signal_kind=kind,
        idempotency_key=feedback_key,
        task_class="prediction_calibration",
        summary=f"{prediction.resolution}: {prediction.statement[:240]}",
        desired_behavior=learning,
        failure_signature=(
            prediction.statement if prediction.resolution != "CONFIRMED" else None
        ),
        structured_payload={
            "prediction_id": str(prediction.id),
            "resolution": prediction.resolution,
            "provenance": "OBSERVED_OUTCOME",
        },
    )
    memory = await _memory_candidate(
        db,
        owner_user_id=owner_user_id,
        orbit_id=prediction.orbit_id,
        event_id=event.id,
        feedback_key=feedback_key,
        candidate_text=learning,
        provenance_label="OBSERVED_OUTCOME",
        created_by="SYSTEM",
        source_object_ids={
            "prediction_id": str(prediction.id),
            "source_refs": [f"cognitive_event:{event.id}"],
        },
    )
    support = {
        "CONFIRMED": True,
        "PARTIALLY_CONFIRMED": None,
        "CONTRADICTED": False,
    }[prediction.resolution or "PARTIALLY_CONFIRMED"]
    claim = await _upsert_claim_evidence(
        db,
        owner_user_id=owner_user_id,
        subject_ref=f"prediction:{prediction.id}",
        claim_text=prediction.statement,
        event_id=event.id,
        supports=support,
        rationale=learning,
        mixed_evidence=prediction.resolution == "PARTIALLY_CONFIRMED",
    )
    changed = (
        ChangeClass.CONTRADICTED
        if prediction.resolution == "CONTRADICTED"
        else ChangeClass.UPDATED
    )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.PREDICTION,
        entity_id=str(prediction.id),
        change_class=changed,
        trigger=feedback_key,
        evidence=[f"cognitive_event:{event.id}"],
        counterevidence=[learning] if prediction.resolution == "CONTRADICTED" else [],
        affected_future_behavior="The resolved prediction is calibration evidence for future planning.",
    )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.BELIEF,
        entity_id=str(claim.id),
        change_class=changed,
        trigger=feedback_key,
        evidence=[f"prediction:{prediction.id}", f"cognitive_event:{event.id}"],
        affected_future_behavior="Future context exposes the revised claim with its evidence status.",
    )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.MEMORY,
        entity_id=str(memory.id),
        change_class=ChangeClass.CREATED,
        trigger=feedback_key,
        evidence=[f"cognitive_event:{event.id}"],
        affected_future_behavior="No durable memory changes until the owner approves this candidate.",
    )
    return LearningFeedbackResult(
        event.id, signal.id, learning_candidate.id, memory.id, claim.id
    )


async def reconcile_observed_outcome(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    outcome: Outcome,
    event: CognitiveEvent,
    subject_ref: str,
    claim_text: str,
    supports: bool | None,
    rationale: str,
    orbit_id: uuid.UUID | None,
    existing_claim: SemanticClaim | None = None,
) -> LearningFeedbackResult:
    """Project a persisted outcome into reviewable memory and belief evidence."""
    feedback_key = f"outcome:{outcome.id}:learning"
    await _lock_feedback(db, owner_user_id, feedback_key)
    memory = await _memory_candidate(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_id=event.id,
        feedback_key=feedback_key,
        candidate_text=rationale.strip() or outcome.observed_result,
        provenance_label="OBSERVED_OUTCOME",
        created_by="SYSTEM",
        source_object_ids={
            "outcome_id": str(outcome.id),
            "source_refs": [f"cognitive_event:{event.id}"],
        },
    )
    claim = await _upsert_claim_evidence(
        db,
        owner_user_id=owner_user_id,
        subject_ref=subject_ref,
        claim_text=claim_text,
        event_id=event.id,
        outcome_id=outcome.id,
        supports=supports,
        rationale=rationale,
        existing_claim=existing_claim,
    )

    signal = None
    learning_candidate = None
    if supports is not None:
        signal_kind = (
            LearningSignalKind.SUCCESSFUL_NOVEL_SOLUTION
            if supports
            else LearningSignalKind.OUTCOME_MISS
        )
        signal, learning_candidate = await _stage_hardness_candidate(
            db,
            owner_user_id=owner_user_id,
            orbit_id=orbit_id,
            source_event_id=event.id,
            signal_kind=signal_kind,
            idempotency_key=feedback_key,
            task_class="hypothesis_outcome",
            summary=f"Observed outcome: {outcome.observed_result[:240]}",
            desired_behavior=rationale,
            failure_signature=None if supports else claim_text,
            structured_payload={
                "outcome_id": str(outcome.id),
                "supports": supports,
                "provenance": "OBSERVED_OUTCOME",
            },
        )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OUTCOME,
        entity_id=str(outcome.id),
        change_class=ChangeClass.CREATED,
        trigger=feedback_key,
        evidence=[f"cognitive_event:{event.id}"],
        affected_future_behavior=(
            "The outcome is available as evidence; durable memory remains owner-reviewed."
        ),
    )
    return LearningFeedbackResult(
        event.id,
        signal.id if signal else None,
        learning_candidate.id if learning_candidate else None,
        memory.id,
        claim.id,
    )


async def reconcile_agent_verification(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    step_id: uuid.UUID,
    orbit_id: uuid.UUID | None,
    tool_key: str,
    verdict: str,
    reasons: list[str],
    result_digest: str,
) -> LearningFeedbackResult:
    """Feed deterministic verifier evidence back without copying private results."""
    feedback_key = f"agent_step:{step_id}:verification"
    await _lock_feedback(db, owner_user_id, feedback_key)
    event = await db.scalar(
        select(CognitiveEvent).where(
            CognitiveEvent.owner_user_id == owner_user_id,
            CognitiveEvent.source_ref == feedback_key,
        )
    )
    if event is None:
        event = CognitiveEvent(
            owner_user_id=owner_user_id,
            orbit_id=orbit_id,
            event_kind="EVALUATION_EVENT",
            content_text=f"Agent step {tool_key} verification: {verdict}",
            source_ref=feedback_key,
            structured_payload={
                "agent_step_id": str(step_id),
                "tool_key": tool_key,
                "verdict": verdict,
                "reasons": reasons,
                "result_digest": result_digest,
            },
        )
        db.add(event)
        await db.flush()
    kind = {
        "PASS": LearningSignalKind.SUCCESSFUL_NOVEL_SOLUTION,
        "REVISE": LearningSignalKind.CALIBRATION_ERROR,
        "FAIL": LearningSignalKind.VERIFIED_FAILURE,
    }[verdict]
    signal, learning_candidate = await _stage_hardness_candidate(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        source_event_id=event.id,
        signal_kind=kind,
        idempotency_key=feedback_key,
        task_class="agent_verification",
        summary=f"{tool_key} verifier verdict: {verdict}",
        desired_behavior=(
            f"Preserve verified {tool_key} behavior."
            if verdict == "PASS"
            else f"Revise {tool_key}: {'; '.join(reasons) or verdict}."
        ),
        failure_signature=None if verdict == "PASS" else f"{tool_key}:{verdict}",
        structured_payload={
            "agent_step_id": str(step_id),
            "tool_key": tool_key,
            "verdict": verdict,
            "result_digest": result_digest,
        },
    )
    statement = f"Agent step {tool_key} passed deterministic verification."
    if verdict != "PASS":
        statement = f"Agent step {tool_key} requires review after {verdict.lower()}."
    memory = await _memory_candidate(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_id=event.id,
        feedback_key=feedback_key,
        candidate_text=statement,
        provenance_label="SYSTEM_MEASURED",
        created_by="SYSTEM",
        source_object_ids={
            "agent_step_id": str(step_id),
            "result_digest": result_digest,
            "source_refs": [f"cognitive_event:{event.id}"],
        },
    )
    support = True if verdict == "PASS" else None if verdict == "REVISE" else False
    claim = await _upsert_claim_evidence(
        db,
        owner_user_id=owner_user_id,
        subject_ref=f"agent_step:{step_id}",
        claim_text=statement,
        event_id=event.id,
        supports=support,
        rationale="; ".join(reasons) or "Deterministic contract checks passed.",
        mixed_evidence=verdict == "REVISE",
    )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OUTCOME,
        entity_id=str(step_id),
        change_class=(
            ChangeClass.CREATED if verdict == "PASS" else ChangeClass.UPDATED
        ),
        trigger=feedback_key,
        evidence=[f"cognitive_event:{event.id}", f"learning_signal:{signal.id}"],
        affected_future_behavior=(
            "The verifier result becomes owner-scoped review evidence; it grants no new agency."
        ),
    )
    return LearningFeedbackResult(
        event.id, signal.id, learning_candidate.id, memory.id, claim.id
    )


async def reconcile_owner_correction(
    db: AsyncSession,
    *,
    correction: UserCorrection,
    correction_event: CognitiveEvent,
    signal: LearningSignalRecord,
) -> LearningFeedbackResult:
    """Invalidate state derived from corrected evidence and stage the replacement."""
    owner_user_id = correction.owner_user_id
    feedback_key = f"user_correction:{correction.id}"
    await _lock_feedback(db, owner_user_id, feedback_key)
    learning_candidate = await ingest_candidate_from_signal(
        db,
        signal=signal,
        # Match the canonical Hardness pipeline fingerprint exactly, so a later
        # explicit pipeline run reuses this candidate rather than forking it.
        failure_signature=(signal.structured_payload or {}).get("reason")
        or signal.summary,
        desired_behavior=correction.correction_text,
    )
    assess_candidate_risks(learning_candidate)
    await db.flush()
    learning_candidate = (
        await apply_selector_judgment(
            db,
            candidate_id=learning_candidate.id,
            judgment=CurriculumSelector().evaluate_candidate(learning_candidate),
        )
        or learning_candidate
    )

    target_event_id = correction.target_event_id
    if target_event_id is not None:
        candidates = list(
            await db.scalars(
                select(MemoryCandidate).where(
                    MemoryCandidate.owner_user_id == owner_user_id,
                    MemoryCandidate.source_event_id == target_event_id,
                    MemoryCandidate.status != "REJECTED",
                )
            )
        )
        for candidate in candidates:
            candidate.status = "REJECTED"
            candidate.review_note = "Superseded by an explicit owner correction."
            candidate.reviewed_at = dt.datetime.now(dt.UTC)
            candidate.updated_at = candidate.reviewed_at

        memories = list(
            await db.scalars(
                select(PersonalMemory)
                .join(MemoryEdge, MemoryEdge.memory_id == PersonalMemory.id)
                .where(
                    PersonalMemory.owner_user_id == owner_user_id,
                    PersonalMemory.status == "APPROVED",
                    MemoryEdge.owner_user_id == owner_user_id,
                    MemoryEdge.source_kind == "COGNITIVE_EVENT",
                    MemoryEdge.source_id == target_event_id,
                )
                .with_for_update()
            )
        )
        for memory in {row.id: row for row in memories}.values():
            previous = memory.version
            memory.version += 1
            memory.status = "RETIRED"
            memory.updated_at = dt.datetime.now(dt.UTC)
            db.add(
                MemoryVersion(
                    owner_user_id=owner_user_id,
                    memory_id=memory.id,
                    version=memory.version,
                    canonical_text=memory.canonical_text,
                    structured_value=memory.structured_value,
                    provenance_label="USER_CORRECTION",
                    change_kind="CORRECTED",
                    correction_reason=correction.reason or correction.correction_text,
                    changed_by="OWNER",
                )
            )
            await _record_change_once(
                db,
                owner_user_id=owner_user_id,
                entity_type=EntityType.MEMORY,
                entity_id=str(memory.id),
                change_class=ChangeClass.CORRECTED,
                trigger=feedback_key,
                evidence=[f"user_correction:{correction.id}"],
                owner_correction=True,
                actor="owner",
                previous_version=str(previous),
                new_version=str(memory.version),
                affected_future_behavior="The corrected memory is retired from future hydration.",
            )

        claims = list(
            await db.scalars(
                select(SemanticClaim)
                .join(ClaimEvidence, ClaimEvidence.claim_id == SemanticClaim.id)
                .where(
                    SemanticClaim.owner_user_id == owner_user_id,
                    ClaimEvidence.owner_user_id == owner_user_id,
                    ClaimEvidence.event_id == target_event_id,
                )
            )
        )
        for claim in {row.id: row for row in claims}.values():
            exists = await db.scalar(
                select(ClaimEvidence.id).where(
                    ClaimEvidence.owner_user_id == owner_user_id,
                    ClaimEvidence.claim_id == claim.id,
                    ClaimEvidence.event_id == correction_event.id,
                    ClaimEvidence.supports.is_(False),
                )
            )
            if exists is None:
                db.add(
                    ClaimEvidence(
                        owner_user_id=owner_user_id,
                        claim_id=claim.id,
                        event_id=correction_event.id,
                        supports=False,
                        rationale=correction.reason or correction.correction_text,
                    )
                )
                claim.counterevidence_count += 1
            claim.status = "DISPUTED"
            claim.last_evaluated_at = dt.datetime.now(dt.UTC)
            await _record_change_once(
                db,
                owner_user_id=owner_user_id,
                entity_type=EntityType.BELIEF,
                entity_id=str(claim.id),
                change_class=ChangeClass.CORRECTED,
                trigger=feedback_key,
                evidence=[f"user_correction:{correction.id}"],
                counterevidence=[f"cognitive_event:{correction_event.id}"],
                owner_correction=True,
                actor="owner",
                affected_future_behavior="Future retrieval exposes this claim as disputed.",
            )

    correction_claim = await _upsert_claim_evidence(
        db,
        owner_user_id=owner_user_id,
        subject_ref=f"correction:{correction.id}",
        claim_text=correction.correction_text,
        event_id=correction_event.id,
        supports=True,
        rationale=correction.reason or "Explicit owner correction.",
    )
    memory = await _memory_candidate(
        db,
        owner_user_id=owner_user_id,
        orbit_id=correction.orbit_id,
        event_id=correction_event.id,
        feedback_key=feedback_key,
        candidate_text=correction.correction_text,
        provenance_label="USER_CORRECTION",
        created_by="OWNER",
        source_object_ids={
            "source_correction_id": str(correction.id),
            "source_refs": [f"cognitive_event:{correction_event.id}"],
        },
    )
    await _record_change_once(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.LEARNING_CANDIDATE,
        entity_id=str(learning_candidate.id),
        change_class=ChangeClass.CREATED,
        trigger=feedback_key,
        evidence=[f"learning_signal:{signal.id}"],
        owner_correction=True,
        actor="owner",
        affected_future_behavior=(
            "The correction is staged for governed curriculum review; no model weights changed."
        ),
    )
    return LearningFeedbackResult(
        correction_event.id,
        signal.id,
        learning_candidate.id,
        memory.id,
        correction_claim.id,
    )
