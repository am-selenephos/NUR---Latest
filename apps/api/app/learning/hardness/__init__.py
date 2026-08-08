"""NUR Hardness / Self-Directed Learning Plane V1 package."""
from __future__ import annotations

from app.learning.hardness.candidates import (
    apply_selector_judgment,
    assess_candidate_risks,
    ingest_candidate_from_signal,
)
from app.learning.hardness.curriculum import (
    CurriculumBuilder,
    NoEligibleLearningCandidates,
    partition_candidate_ids,
)
from app.learning.hardness.evaluation import (
    DryRunEvaluationAdapter,
    TournamentEvaluator,
)
from app.learning.hardness.experiments import (
    complete_experiment_with_artifact,
    create_training_experiment,
)
from app.learning.hardness.fingerprint import (
    canonical_json_dumps,
    compute_candidate_fingerprint,
    compute_dataset_hash,
    sha256_hex,
)
from app.learning.hardness.pipeline import (
    SliceExecutionResult,
    process_learning_signal,
    run_owner_correction_hardness_slice,
)
from app.learning.hardness.promotion import create_promotion_proposal
from app.learning.hardness.schemas import (
    CandidateArtifact,
    CurriculumSnapshotCreate,
    CurriculumSnapshotOut,
    ExperimentStatus,
    HardnessSliceStatus,
    LearningCandidateCreate,
    LearningCandidateOut,
    LearningCandidateScores,
    LearningIntervention,
    LearningScope,
    LearningSignalCreate,
    LearningSignalKind,
    LearningSignalOut,
    PromotionProposalCreate,
    PromotionProposalOut,
    PromotionRecommendation,
    RiskAssessmentStatus,
    SelectionStatus,
    SelectorJudgment,
    SyntheticEvaluationFixture,
    TournamentEvaluationResult,
    TrainerType,
)
from app.learning.hardness.selector import (
    CurriculumSelector,
    SELECTOR_POLICY_VERSION,
)
from app.learning.hardness.signals import (
    create_signal_from_owner_correction,
    persist_learning_signal,
)
from app.learning.hardness.trainers.base import BaseTrainer
from app.learning.hardness.trainers.dry_run import DryRunTrainer

__all__ = [
    "BaseTrainer",
    "CandidateArtifact",
    "CurriculumBuilder",
    "CurriculumSelector",
    "CurriculumSnapshotCreate",
    "CurriculumSnapshotOut",
    "DryRunEvaluationAdapter",
    "DryRunTrainer",
    "ExperimentStatus",
    "HardnessSliceStatus",
    "LearningCandidateCreate",
    "LearningCandidateOut",
    "LearningCandidateScores",
    "LearningIntervention",
    "LearningScope",
    "LearningSignalCreate",
    "LearningSignalKind",
    "LearningSignalOut",
    "NoEligibleLearningCandidates",
    "PromotionProposalCreate",
    "PromotionProposalOut",
    "PromotionRecommendation",
    "RiskAssessmentStatus",
    "SELECTOR_POLICY_VERSION",
    "SelectionStatus",
    "SelectorJudgment",
    "SliceExecutionResult",
    "SyntheticEvaluationFixture",
    "TournamentEvaluationResult",
    "TournamentEvaluator",
    "TrainerType",
    "apply_selector_judgment",
    "assess_candidate_risks",
    "canonical_json_dumps",
    "complete_experiment_with_artifact",
    "compute_candidate_fingerprint",
    "compute_dataset_hash",
    "create_promotion_proposal",
    "create_signal_from_owner_correction",
    "create_training_experiment",
    "ingest_candidate_from_signal",
    "partition_candidate_ids",
    "persist_learning_signal",
    "process_learning_signal",
    "run_owner_correction_hardness_slice",
    "sha256_hex",
]
