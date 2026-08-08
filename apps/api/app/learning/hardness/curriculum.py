"""Curriculum snapshot builder with disjoint dataset partitioning and cryptographic hashing."""
from __future__ import annotations

import math
import uuid
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession

from app.learning.hardness.fingerprint import compute_dataset_hash, sha256_hex
from app.learning.hardness.schemas import (
    CurriculumSnapshotCreate,
    LearningIntervention,
    SelectionStatus,
)
from app.learning.hardness.selector import SELECTOR_POLICY_VERSION
from app.models.hardness import CurriculumSnapshotRecord, LearningCandidateRecord


class NoEligibleLearningCandidates(Exception):
    """Raised when attempting to build a curriculum snapshot without any SELECTED candidates."""


def partition_candidate_ids(candidate_ids: Sequence[str]) -> tuple[list[str], list[str], list[str]]:
    """Partition a list of unique candidate IDs deterministically into train (70%), validation (15%), and heldout (15%).

    Enforces strict disjointness.
    """
    sorted_ids = sorted(list(set(candidate_ids)))
    n = len(sorted_ids)
    if n == 0:
        return [], [], []
    if n == 1:
        return [sorted_ids[0]], [], []
    if n == 2:
        return [sorted_ids[0]], [sorted_ids[1]], []

    n_val = max(1, math.floor(n * 0.15))
    n_heldout = max(1, math.floor(n * 0.15))
    n_train = n - n_val - n_heldout
    if n_train < 1:
        n_train = 1
        n_val = max(0, n - n_train - n_heldout)

    train_ids = sorted_ids[:n_train]
    val_ids = sorted_ids[n_train : n_train + n_val]
    heldout_ids = sorted_ids[n_train + n_val :]

    # Strict disjointness invariant assertions
    s_train, s_val, s_heldout = set(train_ids), set(val_ids), set(heldout_ids)
    assert s_train.isdisjoint(s_val), "Train and Validation sets must be disjoint"
    assert s_train.isdisjoint(s_heldout), "Train and Heldout sets must be disjoint"
    assert s_val.isdisjoint(s_heldout), "Validation and Heldout sets must be disjoint"
    assert len(s_train | s_val | s_heldout) == n, "All candidates must be partitioned"

    return train_ids, val_ids, heldout_ids


class CurriculumBuilder:
    """Builds and persists immutable curriculum snapshots."""

    @staticmethod
    def construct_snapshot_manifest(
        *,
        owner_user_id: uuid.UUID,
        candidates: Sequence[LearningCandidateRecord],
        target_capabilities: list[str],
        intervention: LearningIntervention = LearningIntervention.NO_CHANGE,
        selector_policy_version: str = SELECTOR_POLICY_VERSION,
    ) -> CurriculumSnapshotCreate:
        """Construct the immutable curriculum snapshot payload with cryptographic hashes."""
        # Enforce owner isolation across all candidates
        for c in candidates:
            if c.owner_user_id != owner_user_id:
                raise ValueError(
                    f"Cross-owner candidate {c.id} (owner={c.owner_user_id}) cannot be included in curriculum for owner {owner_user_id}."
                )

        # Strictly filter for SELECTED candidates only
        valid_candidates = [
            c for c in candidates
            if c.status == SelectionStatus.SELECTED.value
        ]
        if not valid_candidates:
            raise NoEligibleLearningCandidates(
                "No candidates with status=SELECTED are available for curriculum construction."
            )

        # Deterministic sorting by fingerprint
        sorted_candidates = sorted(valid_candidates, key=lambda c: c.fingerprint)
        ordered_ids = [str(c.id) for c in sorted_candidates]

        train_ids, val_ids, heldout_ids = partition_candidate_ids(ordered_ids)

        dataset_manifest_items = [
            {
                "id": str(c.id),
                "fingerprint": c.fingerprint,
                "signal_kind": c.signal_kind,
                "task_class": c.task_class,
                "learning_scope": c.learning_scope,
                "failure_signature": c.failure_signature,
                "desired_behavior": c.desired_behavior,
                "selection_score": c.selection_score,
                "source_refs": c.source_refs,
            }
            for c in sorted_candidates
        ]

        dataset_hash = compute_dataset_hash(dataset_manifest_items)

        privacy_manifest = {
            "owner_user_id": str(owner_user_id),
            "scope": "OWNER_LOCAL",
            "candidate_count": len(sorted_candidates),
            "max_privacy_risk": max((c.privacy_risk for c in sorted_candidates), default=0),
            "max_poisoning_risk": max((c.poisoning_risk for c in sorted_candidates), default=0),
        }
        privacy_manifest_hash = sha256_hex(privacy_manifest)

        provenance_manifest = {
            "owner_user_id": str(owner_user_id),
            "selector_policy_version": selector_policy_version,
            "target_capabilities": sorted(target_capabilities),
            "candidate_fingerprints": [c.fingerprint for c in sorted_candidates],
        }
        provenance_manifest_hash = sha256_hex(provenance_manifest)

        dataset_manifest = {
            "version": "1.0",
            "candidate_count": len(sorted_candidates),
            "target_capabilities": target_capabilities,
            "intervention": intervention.value,
            "items": dataset_manifest_items,
        }

        return CurriculumSnapshotCreate(
            owner_user_id=owner_user_id,
            selector_policy_version=selector_policy_version,
            target_capabilities=target_capabilities,
            intervention=intervention,
            dataset_hash=dataset_hash,
            dataset_manifest=dataset_manifest,
            ordered_candidate_ids=ordered_ids,
            train_ids=train_ids,
            validation_ids=val_ids,
            heldout_ids=heldout_ids,
            privacy_manifest_hash=privacy_manifest_hash,
            provenance_manifest_hash=provenance_manifest_hash,
        )

    @classmethod
    async def create_and_persist(
        cls,
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        candidates: Sequence[LearningCandidateRecord],
        target_capabilities: list[str],
        intervention: LearningIntervention = LearningIntervention.NO_CHANGE,
        selector_policy_version: str = SELECTOR_POLICY_VERSION,
    ) -> CurriculumSnapshotRecord:
        """Construct and persist a curriculum snapshot to the database."""
        create_payload = cls.construct_snapshot_manifest(
            owner_user_id=owner_user_id,
            candidates=candidates,
            target_capabilities=target_capabilities,
            intervention=intervention,
            selector_policy_version=selector_policy_version,
        )
        record = CurriculumSnapshotRecord(
            owner_user_id=create_payload.owner_user_id,
            selector_policy_version=create_payload.selector_policy_version,
            target_capabilities=create_payload.target_capabilities,
            intervention=create_payload.intervention.value,
            dataset_hash=create_payload.dataset_hash,
            dataset_manifest=create_payload.dataset_manifest,
            ordered_candidate_ids=create_payload.ordered_candidate_ids,
            train_ids=create_payload.train_ids,
            validation_ids=create_payload.validation_ids,
            heldout_ids=create_payload.heldout_ids,
            privacy_manifest_hash=create_payload.privacy_manifest_hash,
            provenance_manifest_hash=create_payload.provenance_manifest_hash,
        )
        db.add(record)
        await db.flush()
        return record
