"""Base abstract trainer contract for Hardness learning plane."""
from __future__ import annotations

from abc import ABC, abstractmethod

from app.learning.hardness.schemas import CandidateArtifact
from app.models.hardness import CurriculumSnapshotRecord, TrainingExperimentRecord


class BaseTrainer(ABC):
    """Abstract interface for all training execution backends in NUR."""

    @abstractmethod
    async def execute_training(
        self,
        experiment: TrainingExperimentRecord,
        curriculum: CurriculumSnapshotRecord,
    ) -> CandidateArtifact:
        """Execute training against a curriculum and return the candidate artifact."""
        raise NotImplementedError
