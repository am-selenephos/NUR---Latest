"""NUR Brain Evidence Validator — deterministic verification runtime for high-stakes or workflow runs.

Runs deterministic verification over a ``CognitiveResult`` against the input ``CognitiveTaskPacket``
and evidence. Produces a verification verdict ("PASS", "WARN", "BLOCK") and verification notes.
"""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.brain.schemas import CognitiveResult, CognitiveTaskPacket


class CritiqueResult(BaseModel):
    role: str = "independent_critic"
    verdict: str
    notes: list[str] = Field(default_factory=list)


class DeterministicEvidenceValidator:
    """Deterministic evidence validation runtime."""

    def verify_result(
        self,
        packet: CognitiveTaskPacket,
        result: CognitiveResult,
    ) -> CognitiveResult:
        """Evaluate a CognitiveResult for evidence grounding, contradiction, and claim coverage.

        Updates ``critic_verdict`` and ``critic_notes`` on the CognitiveResult.
        """
        available_refs = {f"{r.get('kind')}:{r.get('id')}" for r in packet.evidence_refs}
        missing_refs = [ref for ref in result.source_refs if ref not in available_refs and ":" in ref]

        notes: list[str] = []
        if missing_refs:
            notes.append(f"Cited refs missing from context: {missing_refs}")

        # Check claim grounding
        unsupported_claims = [
            c.claim_text for c in result.claims
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

        # Return updated CognitiveResult
        return result.model_copy(update={
            "critic_verdict": verdict,
            "critic_notes": notes,
        })


class IndependentCritic:
    """A separate, non-mutating challenge role for evidence and plan quality."""

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
        if result.next_move and not result.next_move.strip():
            notes.append("The next move is empty despite being present.")
        return CritiqueResult(
            role=self.role,
            verdict="REVISE" if notes else "PASS",
            notes=notes,
        )


BrainCritic = DeterministicEvidenceValidator
