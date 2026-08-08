"""End-to-end Slice 1 pipeline orchestrator for Hardness learning plane."""
from __future__ import annotations

import uuid

from pydantic import BaseModel
from sqlalchemy import select
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
    LearningScope,
    PromotionRecommendation,
    SelectionStatus,
    SelectorJudgment,
    SyntheticEvaluationFixture,
    TournamentEvaluationResult,
    TrainerType,
)
from app.learning.hardness.selector import CurriculumSelector
from app.learning.hardness.trainers.base import BaseTrainer
from app.learning.hardness.trainers.dry_run import DryRunTrainer
from app.mind.why_changed import ChangeClass, EntityType, WhyChangedService
from app.models.hardness import LearningSignalRecord


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


async def process_learning_signal(
    db: AsyncSession,
    *,
    signal: LearningSignalRecord | uuid.UUID,
    base_checkpoint_id: str = "base_v1",
    capability_id: str = "general_cognition",
    task_class: str = "owner_guidance",
    intervention: LearningIntervention = LearningIntervention.NO_CHANGE,
    trainer: BaseTrainer | None = None,
    evaluator: TournamentEvaluator | None = None,
    fixture: SyntheticEvaluationFixture | None = None,
) -> SliceExecutionResult:
    """Process a previously persisted canonical learning signal through the Hardness pipeline."""
    if isinstance(signal, uuid.UUID):
        signal_record = await db.get(LearningSignalRecord, signal)
        if signal_record is None:
            raise ValueError(f"LearningSignalRecord with id {signal} not found.")
    else:
        signal_record = signal

    if trainer is None:
        trainer = DryRunTrainer()
    if evaluator is None:
        evaluator = TournamentEvaluator()

    owner_user_id = signal_record.owner_user_id
    payload = signal_record.structured_payload or {}
    failure_signature = payload.get("reason") or signal_record.summary
    desired_behavior = payload.get("correction_text") or signal_record.summary

    # Step 1: Ingest and deduplicate candidate, then perform deterministic risk screening
    candidate = await ingest_candidate_from_signal(
        db,
        signal=signal_record,
        failure_signature=failure_signature,
        desired_behavior=desired_behavior,
        learning_scope=LearningScope.OWNER_LOCAL,
    )
    assess_candidate_risks(candidate)

    # Step 2: Curriculum judgment
    selector = CurriculumSelector()
    judgment = selector.evaluate_candidate(candidate)
    await apply_selector_judgment(db, candidate_id=candidate.id, judgment=judgment)

    if judgment.status != SelectionStatus.SELECTED:
        return SliceExecutionResult(
            signal_id=signal_record.id,
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

    # Step 3: Curriculum Snapshot creation with disjoint partitions
    curriculum = await CurriculumBuilder.create_and_persist(
        db,
        owner_user_id=owner_user_id,
        candidates=[candidate],
        target_capabilities=[capability_id],
        intervention=intervention,
    )

    # Step 4: Intervention gating — weights are not the default response
    if intervention not in (
        LearningIntervention.SFT,
        LearningIntervention.PREFERENCE_TRAINING,
        LearningIntervention.RL,
    ):
        why_record = await WhyChangedService.record_change(
            db,
            owner_user_id=owner_user_id,
            entity_type=EntityType.CURRICULUM,
            entity_id=str(curriculum.id),
            change_class=ChangeClass.CREATED,
            trigger=f"Curriculum snapshot {curriculum.id} created for signal {signal_record.id}",
            supporting_evidence=[f"candidate:{candidate.id}:status={candidate.status}"],
            counter_evidence=[],
            owner_correction=True,
            actor="hardness_pipeline",
            affected_future_behavior="no-op learning intervention selected; no training experiment or weight changes executed.",
            policy_version="hardness-selector-v1",
        )
        return SliceExecutionResult(
            signal_id=signal_record.id,
            candidate_id=candidate.id,
            candidate_fingerprint=candidate.fingerprint,
            judgment=judgment,
            curriculum_id=curriculum.id,
            dataset_hash=curriculum.dataset_hash,
            experiment_id=None,
            artifact=None,
            eval_result=None,
            proposal_id=None,
            recommendation=None,
            why_changed_ref=f"why_changed:{why_record.id}",
        )

    # Step 5: Plan falsifiable training experiment
    if intervention == LearningIntervention.PREFERENCE_TRAINING:
        hypothesis = f"Preference alignment (DPO/RLHF) on candidate {candidate.fingerprint[:8]} improves {capability_id}"
    elif intervention == LearningIntervention.RL:
        hypothesis = f"Reinforcement learning policy optimization on candidate {candidate.fingerprint[:8]} improves {capability_id}"
    else:
        hypothesis = f"Supervised fine-tuning on candidate {candidate.fingerprint[:8]} improves {capability_id}"

    experiment = await create_training_experiment(
        db,
        owner_user_id=owner_user_id,
        base_checkpoint_id=base_checkpoint_id,
        curriculum=curriculum,
        hypothesis=hypothesis,
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
        fixture=fixture,
    )

    # Step 8: Create immutable Promotion Proposal with WhyChanged lineage
    proposal = await create_promotion_proposal(
        db,
        owner_user_id=owner_user_id,
        experiment=experiment,
        eval_result=eval_result,
    )

    return SliceExecutionResult(
        signal_id=signal_record.id,
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
    fixture: SyntheticEvaluationFixture | None = None,
) -> SliceExecutionResult:
    """Execute the full owner correction hardness slice deterministically end-to-end via canonical user correction."""
    from app.cognition.correction_service import persist_user_correction

    # 1. Persist user correction and emit exactly 1 canonical LearningSignalRecord atomically
    user_corr = await persist_user_correction(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        target_event_id=target_event_id,
        correction_text=correction_text,
        reason=reason,
    )

    # 2. Query the exact canonical signal produced by persist_user_correction
    stmt = select(LearningSignalRecord).where(
        LearningSignalRecord.owner_user_id == owner_user_id,
        LearningSignalRecord.source_correction_id == user_corr.id,
    )
    signal = (await db.execute(stmt)).scalar_one()

    # 3. Process the canonical signal through the pipeline
    return await process_learning_signal(
        db,
        signal=signal,
        base_checkpoint_id=base_checkpoint_id,
        capability_id=capability_id,
        task_class=task_class,
        intervention=intervention,
        trainer=trainer,
        evaluator=evaluator,
        fixture=fixture,
    )
