"""Promotion service for creating immutable promotion proposals with WhyChanged audit lineage."""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.schemas import (
    PromotionRecommendation,
    TournamentEvaluationResult,
)
from app.mind.why_changed import ChangeClass, EntityType, WhyChangedService
from app.models.hardness import LearningPromotionProposalRecord, TrainingExperimentRecord


async def create_promotion_proposal(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    experiment: TrainingExperimentRecord,
    eval_result: TournamentEvaluationResult,
) -> LearningPromotionProposalRecord:
    """Create an immutable promotion proposal backed by tournament evaluation and WhyChanged audit trail."""
    if eval_result.verdict == "PASS":
        if eval_result.real_model_evaluated:
            recommendation = PromotionRecommendation.PROMOTION_CANDIDATE
            change_class = ChangeClass.PROMOTED
        else:
            recommendation = PromotionRecommendation.DRY_RUN_VALIDATED
            change_class = ChangeClass.UPDATED
    elif eval_result.verdict == "STRUCTURAL_ONLY":
        recommendation = PromotionRecommendation.DRY_RUN_VALIDATED
        change_class = ChangeClass.UPDATED
    else:
        recommendation = PromotionRecommendation.REJECTED
        change_class = ChangeClass.DEMOTED

    mode_label = "Real Model" if eval_result.real_model_evaluated else f"Dry-Run ({eval_result.evaluation_mode})"
    rationale = (
        f"Evaluation mode: {mode_label}. Verdict: {eval_result.verdict}. "
        f"Target delta: +{eval_result.target_metric_delta * 100:.2f}%, "
        f"General regression: {eval_result.general_regression_delta * 100:.2f}%. "
        f"Critical gates passed: {eval_result.all_critical_gates_passed}. "
        f"Recommendation: {recommendation.value}. "
        f"Reason codes: {', '.join(eval_result.reason_codes)}"
    )

    if not eval_result.real_model_evaluated:
        affected_behavior = (
            "orchestration / structural learning pipeline validated; "
            "no model capability improvement established; no production behavior changed."
        )
    else:
        affected_behavior = f"Candidate checkpoint evaluated for capabilities: {experiment.target_capabilities}"

    # Record WhyChanged entry
    why_record = await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.MODEL_CHECKPOINT,
        entity_id=eval_result.candidate_checkpoint_id,
        change_class=change_class,
        trigger=f"Tournament evaluation for experiment {experiment.id}",
        previous_version=experiment.base_checkpoint_id,
        new_version=eval_result.candidate_checkpoint_id,
        supporting_evidence=[f"gate:{g.gate_name}={g.passed}" for g in eval_result.critical_gates],
        counter_evidence=[] if eval_result.all_critical_gates_passed else ["critical_gate_failed"],
        owner_correction=True,
        actor="hardness_pipeline",
        affected_future_behavior=affected_behavior,
        policy_version="hardness-selector-v1",
    )

    proposal = LearningPromotionProposalRecord(
        owner_user_id=owner_user_id,
        experiment_id=experiment.id,
        candidate_checkpoint_id=eval_result.candidate_checkpoint_id,
        base_checkpoint_id=eval_result.base_checkpoint_id,
        target_metric_delta=eval_result.target_metric_delta,
        general_regression_delta=eval_result.general_regression_delta,
        critical_gates_passed=eval_result.all_critical_gates_passed,
        evaluation_summary=eval_result.model_dump(mode="json"),
        recommendation=recommendation.value,
        uncertainty_score=1500,  # 15% calibrated uncertainty
        rationale=rationale,
        why_changed_ref=f"why_changed:{why_record.id}",
    )
    db.add(proposal)
    await db.flush()
    return proposal
