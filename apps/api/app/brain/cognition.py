"""NUR Brain Cognition — single Brain step execution pipeline.

Takes a ``CognitiveTaskPacket``, selects a profile via ``router.route()``,
dispatches to ``BrainProviderAdapter.generate_structured()``, optionally runs
``BrainCritic`` for high-stakes runs, and returns the final ``CognitiveResult``.
"""
from __future__ import annotations

from typing import Any
from urllib.parse import urlparse

from app.ai.schemas import AIStreamSink
from app.brain.critic import BrainCritic, IndependentCritic
from app.brain.planner import BoundedSimulator, PlanBudget, TypedPlanner
from app.brain.profiles import get_profile
from app.brain.prompts import build_system_prompt, build_user_prompt
from app.brain.provider import BrainProviderAdapter
from app.brain.research import (
    InMemoryResearchAdapter,
    ResearchBrain,
    ResearchScope,
    ResearchSource,
)
from app.brain.router import route
from app.brain.schemas import (
    BrainProfileKey,
    CognitiveResult,
    CognitiveTaskPacket,
    CognitiveTaskPacketV2,
    SemanticRoutingSnapshot,
)
from app.brain.specialists import SpecialistBudget, SpecialistContext, SpecialistWorker
from app.brain.tracing import BrainTrace


def _research_sources(packet: CognitiveTaskPacketV2) -> tuple[list[ResearchSource], set[str]]:
    sources: list[ResearchSource] = []
    domains: set[str] = set()
    for ref in packet.evidence_refs:
        citation = str(ref.get("citation") or ref.get("url") or "")
        domain = urlparse(citation).hostname
        if not citation or domain is None:
            continue
        domains.add(domain)
        sources.append(
            ResearchSource(
                id=str(ref.get("id", "unknown")),
                title=str(ref.get("title") or ref.get("kind") or "Scoped evidence"),
                text=str(ref.get("excerpt") or ref.get("text") or ref.get("note") or ""),
                citation=citation,
                owner_user_id=packet.owner_user_id,
                record_class=str(ref.get("record_class") or "PUBLIC_EVIDENCE"),
            )
        )
    return sources, domains


def _bounded_semantic_preflight(
    packet: CognitiveTaskPacket,
    trace: BrainTrace,
) -> CognitiveTaskPacket:
    """Run non-mutating semantic roles and return a copied V2 packet.

    These roles can compare and challenge context. They cannot resolve Agency
    tools, write owner state, call a provider, or authorize execution.
    """
    if not isinstance(packet, CognitiveTaskPacketV2):
        return packet

    semantic_tasks = {"plan", "research", "challenge", "reflect", "summarize"}
    if packet.task_class.lower() not in semantic_tasks:
        return packet

    max_cost = packet.budget.max_cost_cents
    plan_budget = PlanBudget(
        max_steps=8,
        max_cost_cents=max_cost,
        max_time_seconds=max(1, int(packet.budget.deadline_seconds)),
    )
    candidates = TypedPlanner().plan_candidates(
        packet,
        success_criteria=["answer the explicit owner intent with scoped evidence and visible uncertainty"],
        capability_constraints={"retrieve", "summarize"},
        resource_constraints={
            "max_cost_cents": max_cost,
            "max_time_seconds": max(1, int(packet.budget.deadline_seconds)),
        },
        authority_constraints=["owner approval required before any durable write"],
    )
    trace.record_step("typed_planner_bounded", candidates=len(candidates), executed_tools=0)
    simulation = BoundedSimulator().simulate_candidates(candidates, budget=plan_budget)
    trace.record_step(
        "bounded_simulator_evaluated",
        allowed=simulation.allowed,
        candidates=len(simulation.candidates),
        executed_tools=0,
    )

    research_payload: dict[str, Any] = {}
    specialist_payloads: list[dict[str, Any]] = []
    included_context = {
        str(ref.get("id", "unknown")): str(ref.get("excerpt") or ref.get("text") or "")
        for ref in packet.evidence_refs
    }
    if packet.task_class.lower() == "research":
        sources, domains = _research_sources(packet)
        research = ResearchBrain(
            allowed_domains=domains,
            adapters=[InMemoryResearchAdapter(sources)],
        ).research(
            packet.user_input,
            scope=ResearchScope(
                owner_user_id=packet.owner_user_id,
                allowed_domains=domains,
                allowed_source_ids={source.id for source in sources},
                allowed_source_adapters={source.id: "in_memory" for source in sources},
                record_classes={source.record_class for source in sources},
            ),
        )
        research_payload = research.model_dump(mode="json")
        trace.record_step(
            "research_brain_evaluated",
            sources=len(research.source_ids),
            citations_valid=research.citations_valid,
            executed_tools=0,
        )
        specialist = SpecialistWorker("research", allowed_capabilities={"retrieve"})
        result = specialist.run_reasoning(
            "retrieve",
            {"query": packet.user_input, "record_class": "PUBLIC_EVIDENCE"},
            SpecialistBudget(
                max_calls=1,
                max_tokens=max(1, packet.budget.max_context_tokens),
                max_cost_cents=max(1, packet.budget.max_cost_cents),
            ),
            context=SpecialistContext(
                owner_user_id=packet.owner_user_id,
                allowed_record_classes={"PUBLIC_EVIDENCE"},
                included_context=included_context,
            ),
            deadline_seconds=packet.budget.deadline_seconds,
        )
        specialist_payloads.append(result.model_dump(mode="json"))
        trace.record_step(
            "specialist_reasoning_evaluated",
            role=result.role,
            completed=result.completed,
            executed_tools=0,
        )
    else:
        specialist = SpecialistWorker("planning", allowed_capabilities={"compare"})
        result = specialist.run_reasoning(
            "compare",
            {"objective": packet.user_input, "record_class": "OWNER_CONTEXT"},
            SpecialistBudget(
                max_calls=1,
                max_tokens=max(1, packet.budget.max_context_tokens),
                max_cost_cents=max(1, packet.budget.max_cost_cents),
            ),
            context=SpecialistContext(
                owner_user_id=packet.owner_user_id,
                allowed_record_classes={"OWNER_CONTEXT"},
                included_context=included_context,
            ),
            deadline_seconds=packet.budget.deadline_seconds,
        )
        specialist_payloads.append(result.model_dump(mode="json"))
        trace.record_step(
            "specialist_reasoning_evaluated",
            role=result.role,
            completed=result.completed,
            executed_tools=0,
        )

    routing = SemanticRoutingSnapshot(
        planner_candidates=[candidate.model_dump(mode="json") for candidate in candidates],
        simulation=simulation.model_dump(mode="json"),
        research=research_payload,
        specialists=specialist_payloads,
    )
    return packet.model_copy(update={"semantic_routing": routing}, deep=True)


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
        scope_envelope_id=packet.scope_envelope_id,
        cognitive_task_id=packet.task_id,
    )

    # 1. Select profile
    decision = route(packet)
    profile = get_profile(decision.selected_profile)
    trace.profile_key = profile.key
    trace.route_reason = decision.reason
    trace.record_step("route_selected", profile=profile.key, stakes=decision.stakes_level, reason=decision.reason)

    # 2. Run bounded, non-mutating semantic roles and build prompts.
    routed_packet = _bounded_semantic_preflight(packet, trace)
    system_prompt = build_system_prompt(routed_packet, profile.key)
    user_prompt = build_user_prompt(routed_packet)
    trace.record_step("prompts_built", system_prompt_len=len(system_prompt), user_prompt_len=len(user_prompt))

    # 3. Provider boundary call
    adapter = BrainProviderAdapter()
    output_schema: dict[str, Any] = {}  # Handled via NURTalkOutput schema inside provider

    result = await adapter.generate_structured(
        packet=routed_packet,
        profile=profile,
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        output_schema=output_schema,
        trace=trace,
        event_sink=event_sink,
    )

    # 4. Optional independent critic for DEEP profile or high stakes
    if profile.key in (BrainProfileKey.DEEP, BrainProfileKey.CRITIC) or decision.stakes_level in ("high", "critical"):
        validator = BrainCritic()
        result = validator.verify_result(routed_packet, result)
        trace.record_step(
            "deterministic_validator_evaluated",
            verdict=result.critic_verdict,
            notes=result.critic_notes,
        )
        independent = IndependentCritic().critique(routed_packet, result)
        notes = list(result.critic_notes)
        notes.extend(note for note in independent.notes if note not in notes)
        verdict = (
            independent.verdict
            if independent.verdict != "PASS"
            else result.critic_verdict or independent.verdict
        )
        result = result.model_copy(update={"critic_verdict": verdict, "critic_notes": notes})
        trace.record_step(
            "independent_critic_evaluated",
            role=independent.role,
            verdict=independent.verdict,
            notes=independent.notes,
            executed_tools=0,
        )

    return result, trace
