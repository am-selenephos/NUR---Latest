"""
Deterministic evidence validation and an independent reasoning challenge role.

The validator checks contracts and references. The IndependentCritic challenges
whether a structurally valid result or plan is actually supported and feasible.
Neither role can approve execution or mutate durable owner truth.
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.brain.planner import PlanCandidate
from app.brain.schemas import CognitiveResult, CognitiveTaskPacket


class CritiqueResult(BaseModel):
    role: str = "independent_critic"
    verdict: str
    notes: list[str] = Field(default_factory=list)
    unsupported_claims: list[str] = Field(default_factory=list)
    counter_evidence: list[str] = Field(default_factory=list)
    missed_alternatives: list[str] = Field(default_factory=list)
    logical_gaps: list[str] = Field(default_factory=list)
    feasibility_issues: list[str] = Field(default_factory=list)
    uncertainty_calibration: list[str] = Field(default_factory=list)
    authority_mismatch: list[str] = Field(default_factory=list)


class DeterministicEvidenceValidator:
    """Deterministic evidence validation runtime."""

    def verify_result(
        self,
        packet: CognitiveTaskPacket,
        result: CognitiveResult,
    ) -> CognitiveResult:
        """Evaluate a CognitiveResult for evidence grounding and claim coverage."""
        available_refs = {f"{r.get('kind')}:{r.get('id')}" for r in packet.evidence_refs}
        missing_refs = [ref for ref in result.source_refs if ref not in available_refs and ":" in ref]

        notes: list[str] = []
        if missing_refs:
            notes.append(f"Cited refs missing from context: {missing_refs}")

        unsupported_claims = [
            c.claim_text
            for c in result.claims
            if c.claim_kind in ("observed", "inferred") and not c.source_refs
        ]
        if unsupported_claims and packet.evidence_refs:
            notes.append(f"{len(unsupported_claims)} claim(s) lack source citation.")

        if missing_refs:
            verdict = "BLOCK"
        elif notes:
            verdict = "WARN"
        else:
            verdict = "PASS"

        return result.model_copy(update={"critic_verdict": verdict, "critic_notes": notes})


class IndependentCritic:
    """A separate, non-mutating challenge role for reasoning quality."""

    role = "independent_critic"

    def critique(self, packet: CognitiveTaskPacket, result: CognitiveResult) -> CritiqueResult:
        notes: list[str] = []
        if packet.context_manifest.included and any(
            claim.claim_kind in ("observed", "inferred") and not claim.source_refs
            for claim in result.claims
        ):
            notes.append("At least one grounded claim lacks a source reference.")
        if result.workflow_proposal and not result.workflow_proposal.steps:
            notes.append("The proposed workflow has no executable steps.")
        if result.next_move is not None and not result.next_move.strip():
            notes.append("The next move is empty despite being present.")
        return CritiqueResult(
            role=self.role,
            verdict="REVISE" if notes else "PASS",
            notes=notes,
            unsupported_claims=[note for note in notes if "claim" in note.lower()],
            logical_gaps=[note for note in notes if "workflow" in note.lower()],
        )

    def critique_plan(
        self,
        candidate: PlanCandidate,
        *,
        evidence: list[dict[str, Any]],
        alternatives: list[PlanCandidate] | None = None,
    ) -> CritiqueResult:
        notes: list[str] = []
        unsupported_claims: list[str] = []
        counter_evidence: list[str] = []
        missed_alternatives: list[str] = []
        logical_gaps: list[str] = []
        feasibility_issues: list[str] = []
        uncertainty_calibration: list[str] = []
        authority_mismatch: list[str] = []

        positive_evidence = [item for item in evidence if item.get("supports") is True]
        for assumption in candidate.assumptions:
            if not positive_evidence:
                unsupported_claims.append(assumption)
        for item in evidence:
            if item.get("supports") is False:
                counter_evidence.append(str(item.get("text") or item.get("id") or "counter-evidence"))
        if not alternatives:
            missed_alternatives.append("No alternative path was supplied for comparison.")
        if candidate.steps and not candidate.dependencies:
            logical_gaps.append("The plan has steps but declares no dependencies or preconditions.")
        if not candidate.required_capabilities:
            feasibility_issues.append("The plan does not identify required capabilities.")
        if not candidate.uncertainty:
            uncertainty_calibration.append("The plan reports no uncertainty despite incomplete reasoning evidence.")
        if not candidate.owner_approval_required and not candidate.reversible:
            authority_mismatch.append("An irreversible path does not require explicit owner approval.")
        if any("approval" in constraint.lower() for constraint in candidate.constraints) and not candidate.owner_approval_required:
            authority_mismatch.append("The plan declares an approval constraint but does not enforce approval.")

        for group, label in (
            (unsupported_claims, "unsupported claims"),
            (counter_evidence, "counter-evidence"),
            (missed_alternatives, "missed alternatives"),
            (logical_gaps, "logical gaps"),
            (feasibility_issues, "feasibility issues"),
            (uncertainty_calibration, "uncertainty calibration"),
            (authority_mismatch, "policy/authority mismatch"),
        ):
            if group:
                notes.append(f"Independent challenge found {label}.")

        if authority_mismatch or logical_gaps:
            verdict = "REJECT"
        elif counter_evidence or unsupported_claims or feasibility_issues:
            verdict = "REVISE"
        elif uncertainty_calibration or missed_alternatives:
            verdict = "RESEARCH_MORE"
        else:
            verdict = "PASS"
        return CritiqueResult(
            role=self.role,
            verdict=verdict,
            notes=notes,
            unsupported_claims=unsupported_claims,
            counter_evidence=counter_evidence,
            missed_alternatives=missed_alternatives,
            logical_gaps=logical_gaps,
            feasibility_issues=feasibility_issues,
            uncertainty_calibration=uncertainty_calibration,
            authority_mismatch=authority_mismatch,
        )


BrainCritic = DeterministicEvidenceValidator
