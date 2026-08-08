"""Deterministic DryRunTrainer for Hardness plane."""
from __future__ import annotations

import datetime as dt

from app.learning.hardness.fingerprint import sha256_hex
from app.learning.hardness.schemas import CandidateArtifact, TrainerType
from app.learning.hardness.trainers.base import BaseTrainer
from app.models.hardness import CurriculumSnapshotRecord, TrainingExperimentRecord


class DryRunTrainer(BaseTrainer):
    """Safe, deterministic dry-run trainer producing verifiable candidate artifacts."""

    async def execute_training(
        self,
        experiment: TrainingExperimentRecord,
        curriculum: CurriculumSnapshotRecord,
    ) -> CandidateArtifact:
        """Execute deterministic dry-run training."""
        candidate_checkpoint_id = f"cand_{curriculum.dataset_hash[:16]}_dryrun"

        artifact_payload = {
            "base_checkpoint_id": experiment.base_checkpoint_id,
            "candidate_checkpoint_id": candidate_checkpoint_id,
            "curriculum_hash": curriculum.dataset_hash,
            "target_capabilities": experiment.target_capabilities,
            "intervention": experiment.intervention,
            "trainer_type": TrainerType.DRY_RUN.value,
        }
        artifact_hash = sha256_hex(artifact_payload)

        metrics_summary = {
            "simulated_training_loss": 0.124,
            "simulated_eval_loss": 0.145,
            "candidate_checkpoint_id": candidate_checkpoint_id,
            "curriculum_item_count": len(curriculum.ordered_candidate_ids),
        }

        return CandidateArtifact(
            candidate_checkpoint_id=candidate_checkpoint_id,
            base_checkpoint_id=experiment.base_checkpoint_id,
            experiment_id=experiment.id,
            curriculum_hash=curriculum.dataset_hash,
            trainer_type=TrainerType.DRY_RUN,
            artifact_hash=artifact_hash,
            metrics_summary=metrics_summary,
            spend_cents=0,
            real_training_performed=False,
            external_provider_invoked=False,
            created_at=dt.datetime.now(dt.UTC),
        )
