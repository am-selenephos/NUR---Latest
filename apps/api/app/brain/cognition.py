"""NUR Brain Cognition — single Brain step execution pipeline.

Takes a ``CognitiveTaskPacket``, selects a profile via ``router.route()``,
dispatches to ``BrainProviderAdapter.generate_structured()``, optionally runs
``BrainCritic`` for high-stakes runs, and returns the final ``CognitiveResult``.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.ai.schemas import AIStreamSink
from app.brain.critic import BrainCritic
from app.brain.profiles import get_profile
from app.brain.prompts import build_system_prompt, build_user_prompt
from app.brain.provider import BrainProviderAdapter
from app.brain.router import route
from app.brain.schemas import CognitiveResult, CognitiveTaskPacket, BrainProfileKey
from app.brain.tracing import BrainTrace


async def run_brain_step(
    packet: CognitiveTaskPacket,
    event_sink: AIStreamSink | None = None,
) -> tuple[CognitiveResult, BrainTrace]:
    """Execute one provider-backed Brain cognition step.

    Returns the validated ``CognitiveResult`` and its ``BrainTrace``.
    """
    trace = BrainTrace(
        task_id=packet.task_id,
        request_id=packet.task_id,
    )

    # 1. Select profile
    decision = route(packet)
    profile = get_profile(decision.selected_profile)
    trace.profile_key = profile.key
    trace.route_reason = decision.reason
    trace.record_step("route_selected", profile=profile.key, stakes=decision.stakes_level, reason=decision.reason)

    # 2. Build prompts
    system_prompt = build_system_prompt(packet, profile.key)
    user_prompt = build_user_prompt(packet)
    trace.record_step("prompts_built", system_prompt_len=len(system_prompt), user_prompt_len=len(user_prompt))

    # 3. Provider boundary call
    adapter = BrainProviderAdapter()
    output_schema: dict[str, Any] = {}  # Handled via NURTalkOutput schema inside provider

    result = await adapter.generate_structured(
        packet=packet,
        profile=profile,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=output_schema,
        trace=trace,
        event_sink=event_sink,
    )

    # 4. Optional independent critic for DEEP profile or high stakes
    if profile.key in (BrainProfileKey.DEEP, BrainProfileKey.CRITIC) or decision.stakes_level in ("high", "critical"):
        critic = BrainCritic()
        result = critic.verify_result(packet, result)
        trace.record_step("critic_evaluated", verdict=result.critic_verdict, notes=result.critic_notes)

    return result, trace
