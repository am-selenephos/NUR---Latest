from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import (
    BrainProfileKey,
    CognitiveResult,
    CognitiveTaskPacket,
    CognitiveTaskPacketV2,
    WorkflowProposalV2,
    WorkflowStepProposal,
)
from app.brain.critic import IndependentCritic
from app.brain.planner import BoundedSimulator, PlanBudget, TypedPlanner
from app.brain.specialists import SpecialistBudget, SpecialistContext, SpecialistWorker
from app.mind.capabilities.hydrator import HydratedCapabilityContext
from app.mind.capabilities.schemas import CapabilitySpec, ExecutionMode

# Registry for typed read-only workers (fail closed if unregistered)
ReadOnlyWorkerCallable = Callable[
    [CapabilitySpec, HydratedCapabilityContext, str, uuid.UUID],
    Awaitable[CognitiveResult],
]
_READ_ONLY_WORKERS: dict[str, ReadOnlyWorkerCallable] = {}


def register_read_only_worker(
    capability_id: str,
    worker: ReadOnlyWorkerCallable,
) -> None:
    """Register a typed read-only worker implementation."""
    _READ_ONLY_WORKERS[capability_id] = worker


class WorkerDispatcher:
    """Dispatches capability tasks to specialized workers or cognitive pipelines."""

    @staticmethod
    async def dispatch(
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        capability: CapabilitySpec,
        hydrated_context: HydratedCapabilityContext,
        query: str,
        task_id: uuid.UUID | None = None,
        extracted_parameters: dict[str, Any] | None = None,
        packet: CognitiveTaskPacket | None = None,
    ) -> CognitiveResult | None:
        """Execute the capability worker.

        Returns CognitiveResult for specialized workers, or None if the task should
        pass through the full interactive Brain synthesis loop (COGNITIVE_SYNTHESIS).
        """
        task_uuid = task_id or uuid.uuid4()
        params = extracted_parameters or {}

        if capability.execution_mode == ExecutionMode.COGNITIVE_SYNTHESIS:
            # Cognitive synthesis uses the standard Brain provider pipeline with hydrated context
            return None

        if capability.execution_mode == ExecutionMode.READ_ONLY_WORKER:
            return await WorkerDispatcher._execute_read_only_worker(
                capability=capability,
                hydrated_context=hydrated_context,
                query=query,
                task_id=task_uuid,
            )

        if capability.execution_mode == ExecutionMode.WORKFLOW_PROPOSAL:
            return await WorkerDispatcher._execute_workflow_proposal_worker(
                capability=capability,
                hydrated_context=hydrated_context,
                query=query,
                task_id=task_uuid,
                params=params,
                packet=packet,
            )

        return None

    @staticmethod
    async def _execute_read_only_worker(
        *,
        capability: CapabilitySpec,
        hydrated_context: HydratedCapabilityContext,
        query: str,
        task_id: uuid.UUID,
    ) -> CognitiveResult:
        """Execute a deterministic, read-only worker via registered implementation."""
        if capability.capability_id in _READ_ONLY_WORKERS:
            worker = _READ_ONLY_WORKERS[capability.capability_id]
            return await worker(capability, hydrated_context, query, task_id)

        # Fails closed if no typed worker is registered for this capability
        raise RuntimeError(
            f"No read-only worker registered for capability '{capability.capability_id}'. "
            "Zero generic fallback permitted."
        )

    @staticmethod
    async def _execute_workflow_proposal_worker(
        *,
        capability: CapabilitySpec,
        hydrated_context: HydratedCapabilityContext,
        query: str,
        task_id: uuid.UUID,
        params: dict[str, Any],
        packet: CognitiveTaskPacket | None = None,
    ) -> CognitiveResult:
        """Construct a preview or structured WorkflowProposal for Agency submission."""
        semantic_summary = WorkerDispatcher._bounded_plan_preflight(
            packet=packet,
            hydrated_context=hydrated_context,
        )
        # Derive clean plan title from first line
        lines = query.strip().splitlines()
        first_line = lines[0].strip() if lines else query.strip()
        raw_target = first_line
        for prefix in [
            "let's draft a plan to ",
            "draft a plan to ",
            "make a plan to ",
            "create a plan to ",
            "save a plan to ",
            "save draft plan to ",
            "draft a plan ",
            "make a plan ",
            "create a plan ",
            "save draft plan ",
            "save plan ",
            "plan to ",
        ]:
            if raw_target.lower().startswith(prefix):
                raw_target = raw_target[len(prefix):]
                break
        clean_target = raw_target.strip().capitalize() if raw_target.strip() else ""
        title = params.get("title") or (clean_target[:80] + "..." if len(clean_target) > 80 else clean_target)

        if not title:
            return CognitiveResult(
                task_id=task_id,
                profile_used=BrainProfileKey.BALANCED,
                direct_response="I can help you create a draft plan. What would you like to plan or achieve?",
                workflow_proposal=None,
                decision_summary="No title or actionable intent provided for draft plan proposal.",
                cost_estimate_cents=0,
            )

        # Extract steps from params or structured query lines
        steps: list[str] = []
        if params.get("steps") and isinstance(params["steps"], list):
            steps = [str(s) for s in params["steps"]]
        else:
            extracted_steps: list[str] = []
            for line in query.splitlines():
                line_clean = line.strip()
                if line_clean.startswith(("-", "*", "1.", "2.", "3.", "4.", "5.", "6.", "7.", "8.", "9.")):
                    step_text = line_clean.lstrip("-*0123456789. ")
                    if step_text:
                        extracted_steps.append(step_text)
            steps = extracted_steps

        # Preview vs Persist distinction (§9):
        # "plan this out", "show me a plan", "outline a plan" -> preview only (no workflow proposal persisted)
        # "draft a plan to ...", "create a plan", "save plan" -> governed workflow proposal
        q_lower = query.lower()
        persist_triggers = ("draft a plan", "create a plan", "make a plan", "save plan", "save draft", "create draft")
        has_persist_intent = any(trigger in q_lower for trigger in persist_triggers)
        is_preview_only = not has_persist_intent

        if is_preview_only:
            step_bullets = "\n".join(f"- {s}" for s in steps)
            preview_response = (
                f"### Plan Preview: {title}\n\n"
                f"Here is an outline of the proposed steps:\n"
                f"{step_bullets}\n\n"
                "*Note: This is a conversational preview. Say 'draft a plan to save this' to create an actionable draft.*"
            )
            return CognitiveResult(
                task_id=task_id,
                profile_used=BrainProfileKey.BALANCED,
                direct_response=preview_response,
                workflow_proposal=None,
                decision_summary=(
                    f"Plan preview outline generated for '{title}' (no workflow proposal created)."
                    f"{semantic_summary}"
                ),
                cost_estimate_cents=capability.estimated_cost_cents,
            )

        # Build valid arguments for create_draft_plan handler (title, optional orbit_id, optional steps)
        step_args: dict[str, Any] = {
            "title": title,
            "steps": steps,
        }
        if params.get("orbit_id"):
            step_args["orbit_id"] = str(params["orbit_id"])

        step_proposal = WorkflowStepProposal(
            key="step_1",
            title=f"Draft Plan: {title}",
            description=f"Create a draft plan for '{title}' based on user intent: {query}",
            tool_key="create_draft_plan",
            tool_version="1",
            risk_class="R1_PRIVATE_DRAFT",
            requires_approval=True,
            arguments=step_args,
            estimated_cost_cents=capability.estimated_cost_cents,
        )

        proposal = WorkflowProposalV2(
            task_id=task_id,
            title=f"Plan: {title}",
            rationale=f"Generated via capability '{capability.name}' from user request: {query}",
            steps=[step_proposal],
            total_estimated_cost_cents=capability.estimated_cost_cents,
            requires_owner_approval=True,
        )

        direct_response = (
            f"I have drafted a plan proposal **{title}** based on your conversation. "
            "It requires your review and approval before any actions take effect."
        )

        return CognitiveResult(
            task_id=task_id,
            profile_used=BrainProfileKey.BALANCED,
            direct_response=direct_response,
            workflow_proposal=proposal,
            decision_summary=(
                f"Proposed workflow via {capability.worker_role} ({capability.capability_id})."
                f"{semantic_summary}"
            ),
            cost_estimate_cents=capability.estimated_cost_cents,
        )

    @staticmethod
    def _bounded_plan_preflight(
        *,
        packet: CognitiveTaskPacket | None,
        hydrated_context: HydratedCapabilityContext,
    ) -> str:
        """Run planner, simulator, critic and specialist without tool authority."""
        if packet is None:
            return ""
        if isinstance(packet, CognitiveTaskPacketV2):
            max_cost = packet.budget.max_cost_cents
            deadline = packet.budget.deadline_seconds
            max_tokens = packet.budget.max_context_tokens
        else:
            max_cost = 1_000
            deadline = 300.0
            max_tokens = max(1, packet.context_manifest.token_budget)
        candidates = TypedPlanner().plan_candidates(
            packet,
            success_criteria=["the owner can review a reversible plan before any durable action"],
            capability_constraints={"retrieve", "summarize"},
            resource_constraints={
                "max_cost_cents": max_cost,
                "max_time_seconds": max(1, int(deadline)),
            },
            authority_constraints=["owner approval required before durable write"],
        )
        simulation = BoundedSimulator().simulate_candidates(
            candidates,
            budget=PlanBudget(
                max_steps=8,
                max_cost_cents=max_cost,
                max_time_seconds=max(1, int(deadline)),
            ),
        )
        evidence = [
            {
                "id": str(item.get("id", "unknown")),
                "supports": item.get("supports"),
                "text": item.get("excerpt") or item.get("text") or "scoped evidence",
            }
            for item in hydrated_context.retrieved_evidence
        ]
        critique = IndependentCritic().critique_plan(
            candidates[0],
            evidence=evidence,
            alternatives=candidates[1:],
        )
        specialist = SpecialistWorker("planning", allowed_capabilities={"compare"})
        try:
            specialist_result = specialist.run_reasoning(
                "compare",
                {"objective": packet.user_input, "record_class": "OWNER_CONTEXT"},
                SpecialistBudget(
                    max_calls=1,
                    max_tokens=max(1, max_tokens),
                    max_cost_cents=max(1, max_cost),
                ),
                context=SpecialistContext(
                    owner_user_id=packet.owner_user_id,
                    allowed_record_classes={"OWNER_CONTEXT"},
                    included_context={
                        str(item.get("id", "unknown")): str(item.get("excerpt") or "")
                        for item in hydrated_context.retrieved_evidence
                    },
                ),
                deadline_seconds=deadline,
            )
            specialist_status = f"completed={specialist_result.completed}"
        except RuntimeError as exc:
            # This role is a non-authoritative semantic enrichment. If the
            # packet cannot fund it, omit its output and keep the deterministic,
            # approval-gated proposal inside the declared budget.
            if "budget exhausted" not in str(exc).lower():
                raise
            specialist_status = f"skipped={str(exc).lower()}"
        if not simulation.allowed:
            raise RuntimeError("Bounded simulator refused the workflow proposal.")
        return (
            " Typed planner produced alternatives; bounded simulator admitted the selected budget;"
            f" independent critic verdict={critique.verdict};"
            f" planning specialist {specialist_status}."
        )
