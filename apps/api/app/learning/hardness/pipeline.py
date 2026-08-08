"""End-to-end Slice 1 pipeline orchestrator for Hardness learning plane."""
from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.candidates import (
    apply_selector_judgment,
    assess_candidate_risks,
    ingest_candidate_from_signal,
)
from app.learning.hardness.curriculum import CurriculumBuilder
from app.learning.hardness.evaluation import TournamentEvaluator
from app.learning.hardness.experiments import (
    complete_experiment_with_artifact,
    create_training_experiment,
)
from app.learning.hardness.promotion import create_promotion_proposal
from app.learning.hardness.schemas import (
    CandidateArtifact,
    LearningIntervention,
    PromotionRecommendation,
    SelectionStatus,
    SelectorJudgment,
    TournamentEvaluationResult,
    TrainerType,
)
from app.learning.hardness.selector import CurriculumSelector
from app.learning.hardness.signals import create_signal_from_owner_correction
from app.learning.hardness.trainers.base import BaseTrainer
from app.learning.hardness.trainers.dry_run import DryRunTrainer


class SliceExecutionResult(BaseModel):
    signal_id: uuid.UUID
    candidate_id: uuid.UUID
    candidate_fingerprint: str
    judgment: SelectorJudgment
    curriculum_id: uuid.UUID | None = None
    dataset_hash: str | None = None
    experiment_id: uuid.UUID | None = None
    artifact: CandidateArtifact | None = None
    eval_result: TournamentEvaluationResult | None = None
    proposal_id: uuid.UUID | None = None
    recommendation: PromotionRecommendation | None = None
    why_changed_ref: str | None = None


async def run_owner_correction_hardness_slice(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    correction_text: str,
    reason: str | None = None,
    target_event_id: uuid.UUID | None = None,
    orbit_id: uuid.UUID | None = None,
    base_checkpoint_id: str = "base_v1",
    capability_id: str = "general_cognition",
    task_class: str = "owner_guidance",
    intervention: LearningIntervention = LearningIntervention.NO_CHANGE,
    trainer: BaseTrainer | None = None,
    evaluator: TournamentEvaluator | None = None,
) -> SliceExecutionResult:
    """Execute the full owner correction hardness slice deterministically end-to-end."""
    if trainer is None:
        trainer = DryRunTrainer()
    if evaluator is None:
        evaluator = TournamentEvaluator()

    # Step 1: Capture typed learning signal
    signal = await create_signal_from_owner_correction(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        correction_text=correction_text,
        reason=reason,
        target_event_id=target_event_id,
        capability_id=capability_id,
        task_class=task_class,
    )

    # Step 2: Ingest and deduplicate candidate, then perform deterministic risk screening
    candidate = await ingest_candidate_from_signal(
        db,
        signal=signal,
        failure_signature=reason or "Owner corrected response",
        desired_behavior=correction_text,
    )
    assess_candidate_risks(candidate)

    # Step 3: Curriculum judgment
    selector = CurriculumSelector()
    judgment = selector.evaluate_candidate(candidate)
    await apply_selector_judgment(db, candidate_id=candidate.id, judgment=judgment)

    if judgment.status != SelectionStatus.SELECTED:
        return SliceExecutionResult(
            signal_id=signal.id,
            candidate_id=candidate.id,
            candidate_fingerprint=candidate.fingerprint,
            judgment=judgment,
            curriculum_id=None,
            dataset_hash=None,
            experiment_id=None,
            artifact=None,
            eval_result=None,
            proposal_id=None,
            recommendation=PromotionRecommendation.REJECTED if judgment.status == SelectionStatus.REJECTED else None,
            why_changed_ref=None,
        )

    # Step 4: Curriculum Snapshot creation with disjoint partitions
    curriculum = await CurriculumBuilder.create_and_persist(
        db,
        owner_user_id=owner_user_id,
        candidates=[candidate],
        target_capabilities=[capability_id],
        intervention=intervention,
    )

    # Step 5: Plan falsifiable training experiment
    experiment = await create_training_experiment(
        db,
        owner_user_id=owner_user_id,
        base_checkpoint_id=base_checkpoint_id,
        curriculum=curriculum,
        hypothesis=f"Fine-tuning on owner correction {candidate.fingerprint[:8]} improves {capability_id}",
        trainer_type=TrainerType.DRY_RUN,
    )

    # Step 6: Execute training
    artifact = await trainer.execute_training(experiment, curriculum)
    await complete_experiment_with_artifact(db, experiment_id=experiment.id, artifact=artifact)

    # Step 7: Tournament Evaluation against Base Checkpoint
    eval_result = evaluator.evaluate(
        experiment=experiment,
        curriculum=curriculum,
        artifact=artifact,
    )

    # Step 8: Create immutable Promotion Proposal with WhyChanged lineage
    proposal = await create_promotion_proposal(
        db,
        owner_user_id=owner_user_id,
        experiment=experiment,
        eval_result=eval_result,
    )

    return SliceExecutionResult(
        signal_id=signal.id,
        candidate_id=candidate.id,
        candidate_fingerprint=candidate.fingerprint,
        judgment=judgment,
        curriculum_id=curriculum.id,
        dataset_hash=curriculum.dataset_hash,
        experiment_id=experiment.id,
        artifact=artifact,
        eval_result=eval_result,
        proposal_id=proposal.id,
        recommendation=PromotionRecommendation(proposal.recommendation),
        why_changed_ref=proposal.why_changed_ref,
    )
