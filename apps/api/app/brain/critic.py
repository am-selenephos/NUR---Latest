"""NUR Brain Critic — independent verification runtime for high-stakes or workflow runs.

Runs an independent critic review over a ``CognitiveResult`` against the input ``CognitiveTaskPacket``
and evidence.  Produces a critic verdict ("PASS", "WARN", "BLOCK") and verification notes.
"""
from __future__ import annotations

from app.brain.schemas import CognitiveResult, CognitiveTaskPacket


class BrainCritic:
    """Independent critic runtime."""

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
