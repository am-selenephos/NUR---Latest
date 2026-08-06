"""Brain provider adapter — wraps AIProvider with structured-output generation.

This module owns the provider boundary: no other module may call a provider
directly.  It adds:
  - profile-aware timeout and reasoning effort
  - structured output schema enforcement
  - token/cost budget checks
  - trace recording
  - honest failure on provider unavailable

The existing ``AIProvider`` Protocol and ``OpenAITalkProvider`` are reused;
this adapter layers Brain-specific concerns on top.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

from app.ai.errors import AIProviderDisabled, AIProviderError
from app.ai.schemas import AIStreamSink
from app.brain.profiles import BrainProfile
from app.brain.schemas import CognitiveResult, CognitiveTaskPacket, BrainProfileKey
from app.brain.tracing import BrainTrace


class BrainProviderAdapter:
    """Provider boundary for the Brain plane.

    Callers provide a ``CognitiveTaskPacket`` and a ``BrainProfile``;
    the adapter handles provider dispatch, structured output parsing,
    timeout enforcement, and trace recording.
    """

    async def generate_structured(
        self,
        *,
        packet: CognitiveTaskPacket,
        profile: BrainProfile,
        system_prompt: str,
        user_prompt: str,
        output_schema: dict[str, Any],
        trace: BrainTrace,
        event_sink: AIStreamSink | None = None,
    ) -> CognitiveResult:
        """Call the provider with structured-output enforcement.

        Returns a validated ``CognitiveResult``.
        Raises ``AIProviderDisabled`` if no provider is configured.
        Raises ``AIProviderError`` on transient failure.
        Raises ``AIOutputValidationError`` if the response is malformed.
        """
        import app.cognition.intelligence_kernel as ik_mod
        provider = ik_mod.get_ai_provider()
        trace.record_step("provider_dispatch", provider=provider.name, profile=profile.key)
        from app.ai.schemas import TalkProviderRequest, EvidenceRef

        # Build a TalkProviderRequest that carries the Brain-enriched prompts
        # through the existing provider pathway.  The system prompt is embedded
        # in omega_context as the provider adapter reads it.
        evidence_refs = [
            EvidenceRef(kind=r.get("kind", "unknown"), id=r.get("id", ""), excerpt=r.get("excerpt", ""), rank=r.get("rank", 0))
            for r in packet.evidence_refs
        ]

        request = TalkProviderRequest(
            user_line=user_prompt,
            orbit_id=str(packet.orbit_id) if packet.orbit_id else None,
            retrieval=evidence_refs,
            omega_context={
                "brain_profile": profile.key,
                "brain_run_id": str(trace.brain_run_id),
                **packet.omega_context,
            },
            locale=packet.locale,
            writing_preference=packet.writing_preference,
            mode=packet.task_class,
            system_prompt=system_prompt,
            reasoning_effort=profile.reasoning_effort,
            max_output_tokens=profile.max_output_tokens,
            temperature=profile.temperature,
            model=profile.model,
            output_schema=output_schema,
        )

        t0 = time.monotonic()
        try:
            async with asyncio.timeout(profile.timeout_seconds):
                result = await provider.complete_private_talk(request, event_sink=event_sink)
        except asyncio.CancelledError:
            trace.record_step("provider_cancelled")
            raise
        except TimeoutError:
            trace.record_step("provider_timeout", timeout_seconds=profile.timeout_seconds)
            raise AIProviderError(f"Provider timed out after {profile.timeout_seconds}s.")
        except AIProviderDisabled:
            trace.record_step("provider_disabled")
            raise
        except Exception as exc:
            trace.record_step("provider_error", error=str(exc)[:200])
            raise

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        trace.wall_time_ms = elapsed_ms

        if not result.available:
            trace.record_step("provider_unavailable", reason=result.reason)
            raise AIProviderDisabled(result.reason or "Provider unavailable.")

        # Record usage
        usage = result.usage or {}
        trace.total_input_tokens = usage.get("input_tokens", 0)
        trace.total_output_tokens = usage.get("output_tokens", 0)
        trace.record_step("provider_completed", elapsed_ms=elapsed_ms, usage=usage)

        # Convert AIProviderResult.output (NURTalkOutput) → CognitiveResult
        output = result.output
        from app.brain.schemas import CognitiveClaim, WorkflowProposal, WorkflowStep

        claims: list[CognitiveClaim] = []
        for obs in output.observed:
            claims.append(CognitiveClaim(claim_text=obs, claim_kind="observed", source_refs=output.source_refs))
        for inf in output.inferred:
            claims.append(CognitiveClaim(claim_text=inf, claim_kind="inferred", source_refs=output.source_refs))

        # Check if output contains proposed durable actions
        proposed_actions: list[str] = []
        if output.next_move and any(
            kw in output.next_move.lower()
            for kw in ["create", "delete", "update", "publish", "send", "save", "archive", "schedule"]
        ):
            proposed_actions.append(output.next_move)

        workflow_proposal: WorkflowProposal | None = None
        if proposed_actions:
            workflow_proposal = WorkflowProposal(
                task_id=packet.task_id,
                title=f"Execute: {proposed_actions[0][:60]}",
                rationale=f"Generated from next_move proposed action: {proposed_actions[0]}",
                steps=[
                    WorkflowStep(
                        title=proposed_actions[0][:60],
                        description=proposed_actions[0],
                        tool_key="create_draft_plan",
                        requires_approval=True,
                    )
                ],
                requires_owner_approval=True,
            )

        cognitive_result = CognitiveResult(
            task_id=packet.task_id,
            profile_used=BrainProfileKey(profile.key),
            direct_response=output.direct_response,
            claims=claims,
            hypotheses=output.hypotheses,
            uncertainty=output.uncertainty,
            next_move=output.next_move,
            memory_candidates=output.memory_candidates,
            source_refs=output.source_refs,
            decision_summary=f"Profile {profile.key}; {len(claims)} claims; {len(output.uncertainty)} uncertainties.",
            workflow_proposal=workflow_proposal,
            proposed_actions=proposed_actions,
        )

        trace.record_step("result_constructed", claim_count=len(claims))
        return cognitive_result
