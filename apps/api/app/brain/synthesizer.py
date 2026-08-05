"""NUR Brain Synthesizer — composes final owner-facing output from CognitiveResult.

Maps CognitiveResult to ``NURTalkOutput`` for backward compatibility with existing
Talk handlers and V197 bridge interfaces.
"""
from __future__ import annotations

from app.ai.schemas import NURTalkOutput
from app.brain.schemas import CognitiveResult


def synthesize_talk_output(result: CognitiveResult) -> NURTalkOutput:
    """Map a ``CognitiveResult`` into a canonical ``NURTalkOutput`` struct."""
    observed = [c.claim_text for c in result.claims if c.claim_kind == "observed"]
    inferred = [c.claim_text for c in result.claims if c.claim_kind == "inferred"]

    return NURTalkOutput(
        direct_response=result.direct_response,
        observed=observed,
        inferred=inferred,
        hypotheses=result.hypotheses,
        uncertainty=result.uncertainty,
        next_move=result.next_move,
        memory_candidates=result.memory_candidates,
        source_refs=result.source_refs,
    )
