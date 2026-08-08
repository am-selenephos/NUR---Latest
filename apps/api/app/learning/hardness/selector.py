"""Deterministic curriculum judgment engine implementing hardness-selector-v1 policy."""
from __future__ import annotations

from app.learning.hardness.schemas import (
    LearningCandidateOut,
    LearningScope,
    RiskAssessmentStatus,
    SelectionStatus,
    SelectorJudgment,
)
from app.models.hardness import LearningCandidateRecord

SELECTOR_POLICY_VERSION = "hardness-selector-v1"

# Hard Gate Thresholds (Basis points: 0 - 10000)
MAX_POISONING_RISK_BP = 5000
MAX_PRIVACY_RISK_BP = 4000
MAX_CONTAMINATION_RISK_BP = 6000

# Selection Score Thresholds
SELECT_THRESHOLD_BP = 4000
DEFER_THRESHOLD_BP = 2000


class CurriculumSelector:
    """Evaluates candidates using bounded basis points and hard safety gates."""

    def __init__(self, policy_version: str = SELECTOR_POLICY_VERSION):
        self.policy_version = policy_version

    def evaluate_candidate(self, candidate: LearningCandidateRecord | LearningCandidateOut) -> SelectorJudgment:
        """Run hardness-selector-v1 evaluation against a candidate."""
        reason_codes: list[str] = []
        hard_gates_passed = True

        risk_status = getattr(candidate, "risk_status", RiskAssessmentStatus.UNASSESSED.value)
        if isinstance(risk_status, RiskAssessmentStatus):
            risk_status = risk_status.value

        # Candidates with UNASSESSED risk status cannot be selected; they are deferred for deterministic screening
        if risk_status == RiskAssessmentStatus.UNASSESSED.value:
            return SelectorJudgment(
                candidate_id=candidate.id,
                fingerprint=candidate.fingerprint,
                status=SelectionStatus.DEFERRED,
                selection_score=0,
                learning_value=0,
                risk_penalty=0,
                redundancy_penalty=0,
                policy_version=self.policy_version,
                rationale="Candidate deferred pending deterministic risk assessment (risk_status=UNASSESSED)",
                reason_codes=["RISK_UNASSESSED_DEFERRED"],
                hard_gates_passed=True,
            )

        scope = getattr(candidate, "learning_scope", LearningScope.OWNER_LOCAL.value)
        p_risk = getattr(candidate, "poisoning_risk", 0) or 0
        priv_risk = getattr(candidate, "privacy_risk", 0) or 0
        c_risk = getattr(candidate, "contamination_risk", 0) or 0
        rec_count = getattr(candidate, "recurrence_count", 1) or 1

        # ── 1. Hard Safety & Policy Gates ──
        if scope != LearningScope.OWNER_LOCAL.value:
            hard_gates_passed = False
            reason_codes.append("GATE_SCOPE_NOT_LOCAL")

        if p_risk > MAX_POISONING_RISK_BP:
            hard_gates_passed = False
            reason_codes.append("GATE_POISONING_RISK_EXCEEDED")

        if priv_risk > MAX_PRIVACY_RISK_BP:
            hard_gates_passed = False
            reason_codes.append("GATE_PRIVACY_RISK_EXCEEDED")

        if c_risk > MAX_CONTAMINATION_RISK_BP:
            hard_gates_passed = False
            reason_codes.append("GATE_CONTAMINATION_RISK_EXCEEDED")

        # ── 2. Bounded Scoring in Basis Points ──
        rec_score = getattr(candidate, "recurrence_score", 0) or 0
        imp_score = getattr(candidate, "impact_score", 0) or 0
        nov_score = getattr(candidate, "novelty_score", 0) or 0
        unc_score = getattr(candidate, "uncertainty_score", 0) or 0
        cnt_score = getattr(candidate, "counterexample_value", 0) or 0
        trn_score = getattr(candidate, "transferability_score", 0) or 0
        rcn_score = getattr(candidate, "recency_score", 0) or 0

        # Learning Value: Weights sum to 10000
        learning_value = (
            2200 * rec_score
            + 1800 * imp_score
            + 1600 * nov_score
            + 1400 * unc_score
            + 1400 * cnt_score
            + 1000 * trn_score
            + 600 * rcn_score
        ) // 10000

        # Risk Penalty: Weights sum to 10000
        risk_penalty = (
            4500 * p_risk
            + 3500 * priv_risk
            + 2000 * c_risk
        ) // 10000

        # Redundancy Penalty: Damps highly repeated candidates beyond usefulness
        redundancy_penalty = min(500 * max(0, rec_count - 1), 2000)

        # Net selection score
        raw_score = learning_value - risk_penalty - redundancy_penalty
        selection_score = max(0, min(10000, raw_score))

        # ── 3. Status Determination ──
        if not hard_gates_passed:
            status = SelectionStatus.REJECTED
            rationale = f"Candidate rejected due to safety gate failure: {', '.join(reason_codes)}"
        elif selection_score >= SELECT_THRESHOLD_BP:
            status = SelectionStatus.SELECTED
            reason_codes.append("SCORE_SELECTED")
            rationale = (
                f"Candidate selected with score {selection_score} bp "
                f"(learning_value={learning_value}, risk_penalty={risk_penalty}, redundancy_penalty={redundancy_penalty})"
            )
        elif selection_score >= DEFER_THRESHOLD_BP:
            status = SelectionStatus.DEFERRED
            reason_codes.append("SCORE_DEFERRED")
            rationale = (
                f"Candidate deferred with score {selection_score} bp below selection threshold {SELECT_THRESHOLD_BP} bp"
            )
        else:
            status = SelectionStatus.REJECTED
            reason_codes.append("SCORE_REJECTED")
            rationale = (
                f"Candidate rejected with low score {selection_score} bp below minimum {DEFER_THRESHOLD_BP} bp"
            )

        return SelectorJudgment(
            candidate_id=candidate.id,
            fingerprint=candidate.fingerprint,
            status=status,
            selection_score=selection_score,
            learning_value=learning_value,
            risk_penalty=risk_penalty,
            redundancy_penalty=redundancy_penalty,
            policy_version=self.policy_version,
            rationale=rationale,
            reason_codes=reason_codes,
            hard_gates_passed=hard_gates_passed,
        )
