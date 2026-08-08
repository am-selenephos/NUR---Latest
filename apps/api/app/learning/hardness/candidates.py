"""Candidate management and deduplication service for Hardness plane."""
from __future__ import annotations

import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.fingerprint import compute_candidate_fingerprint
from app.learning.hardness.schemas import (
    LearningCandidateScores,
    LearningScope,
    LearningSignalKind,
    RiskAssessmentStatus,
    SelectionStatus,
    SelectorJudgment,
)
from app.models.hardness import LearningCandidateRecord, LearningSignalRecord


def assess_candidate_risks(
    candidate: LearningCandidateRecord,
    *,
    force_reassess: bool = False,
) -> None:
    """Perform deterministic safety, privacy, and contamination screening on a candidate.

    Computes bounded basis-point risks based on explicit structural rules (no heuristic LLM calls)
    and transitions risk_status from UNASSESSED to ASSESSED.
    """
    if candidate.risk_status == RiskAssessmentStatus.ASSESSED.value and not force_reassess:
        return

    text_to_scan = f"{candidate.failure_signature or ''} {candidate.desired_behavior or ''}"
    lowered = text_to_scan.lower()

    # 1. Deterministic Poisoning / Injection Screening
    p_risk = 500  # Baseline safe risk for verified owner interaction
    suspicious_patterns = [
        "ignore previous instructions",
        "system prompt",
        "exfiltrate",
        "<script>",
        "javascript:",
        "drop table",
        "select * from users",
        "rm -rf /",
        "--format-leak",
        "eval(",
        "exec(",
    ]
    for pat in suspicious_patterns:
        if pat in lowered:
            p_risk += 3000

    # 2. Deterministic Privacy / PII Screening
    priv_risk = 500
    import re

    if re.search(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", text_to_scan):
        priv_risk += 1500
    if re.search(r"\b(sk-[a-zA-Z0-9]{20,}|ghp_[a-zA-Z0-9]{20,}|bearer\s+[a-zA-Z0-9._-]{20,})\b", text_to_scan, re.IGNORECASE):
        priv_risk += 4000
    if re.search(r"\b\d{3}-\d{2}-\d{4}\b|\b(?:\d{4}-){3}\d{4}\b", text_to_scan):
        priv_risk += 4000

    # 3. Deterministic Contamination Screening
    c_risk = 200
    if "heldout_test_set" in lowered or "benchmark_gold_standard" in lowered:
        c_risk += 5000

    candidate.poisoning_risk = min(10000, p_risk)
    candidate.privacy_risk = min(10000, priv_risk)
    candidate.contamination_risk = min(10000, c_risk)
    candidate.risk_status = RiskAssessmentStatus.ASSESSED.value


async def ingest_candidate_from_signal(
    db: AsyncSession,
    *,
    signal: LearningSignalRecord,
    failure_signature: str | None = None,
    desired_behavior: str | None = None,
    scores: LearningCandidateScores | None = None,
    learning_scope: LearningScope = LearningScope.OWNER_LOCAL,
) -> LearningCandidateRecord:
    """Ingest a learning candidate from a signal with fingerprint deduplication and recurrence tracking."""
    fingerprint = compute_candidate_fingerprint(
        owner_user_id=signal.owner_user_id,
        signal_kind=signal.signal_kind,
        task_class=signal.task_class,
        failure_signature=failure_signature,
        desired_behavior=desired_behavior,
    )

    stmt = select(LearningCandidateRecord).where(
        LearningCandidateRecord.owner_user_id == signal.owner_user_id,
        LearningCandidateRecord.fingerprint == fingerprint,
    )
    res = await db.execute(stmt)
    existing = res.scalars().first()

    now = dt.datetime.now(dt.UTC)
    source_ref = f"signal:{signal.id}"

    if existing:
        # Retry/redelivery of identical signal does not increment recurrence
        if source_ref not in existing.source_refs:
            existing.recurrence_count += 1
            existing.last_seen_at = now
            existing.updated_at = now
            # Recompute recurrence score proportionally up to 10000 bp
            existing.recurrence_score = min(10000, 2000 + existing.recurrence_count * 1500)
            existing.recency_score = 9000  # Refreshed recency
            existing.source_refs = list(existing.source_refs) + [source_ref]
            await db.flush()
        return existing

    # Default scores for owner correction if not specified
    if scores is None:
        if signal.signal_kind == LearningSignalKind.OWNER_CORRECTION.value:
            scores = LearningCandidateScores(
                novelty_score=6000,
                recurrence_score=2000,
                impact_score=7500,
                uncertainty_score=2500,
                counterexample_value=8000,
                transferability_score=5000,
                recency_score=9500,
                poisoning_risk=0,
                privacy_risk=0,
                contamination_risk=0,
            )
        else:
            scores = LearningCandidateScores(
                novelty_score=5000,
                recurrence_score=2000,
                impact_score=5000,
                uncertainty_score=5000,
                counterexample_value=5000,
                transferability_score=5000,
                recency_score=9000,
                poisoning_risk=0,
                privacy_risk=0,
                contamination_risk=0,
            )

    record = LearningCandidateRecord(
        owner_user_id=signal.owner_user_id,
        fingerprint=fingerprint,
        signal_kind=signal.signal_kind,
        capability_id=signal.capability_id,
        task_class=signal.task_class,
        failure_signature=failure_signature,
        desired_behavior=desired_behavior,
        novelty_score=scores.novelty_score,
        recurrence_score=scores.recurrence_score,
        impact_score=scores.impact_score,
        uncertainty_score=scores.uncertainty_score,
        counterexample_value=scores.counterexample_value,
        transferability_score=scores.transferability_score,
        recency_score=scores.recency_score,
        poisoning_risk=scores.poisoning_risk,
        privacy_risk=scores.privacy_risk,
        contamination_risk=scores.contamination_risk,
        learning_scope=learning_scope.value,
        status=SelectionStatus.CANDIDATE.value,
        risk_status=RiskAssessmentStatus.UNASSESSED.value,
        source_refs=[source_ref],
        recurrence_count=1,
        last_seen_at=now,
    )
    db.add(record)
    await db.flush()
    return record


async def apply_selector_judgment(
    db: AsyncSession,
    *,
    candidate_id: uuid.UUID,
    judgment: SelectorJudgment,
) -> LearningCandidateRecord | None:
    """Apply a curriculum selector judgment to a candidate record."""
    stmt = select(LearningCandidateRecord).where(LearningCandidateRecord.id == candidate_id)
    res = await db.execute(stmt)
    cand = res.scalars().first()
    if not cand:
        return None

    cand.status = judgment.status.value
    cand.selection_score = judgment.selection_score
    cand.learning_value = judgment.learning_value
    cand.risk_penalty = judgment.risk_penalty
    cand.redundancy_penalty = judgment.redundancy_penalty
    cand.selection_policy_version = judgment.policy_version
    cand.selection_rationale = judgment.rationale
    cand.reason_codes = judgment.reason_codes
    cand.updated_at = dt.datetime.now(dt.UTC)

    await db.flush()
    return cand
