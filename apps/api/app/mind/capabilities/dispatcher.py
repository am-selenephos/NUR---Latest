"""NUR Mind Worker Dispatcher.

Orchestrates capability execution according to its declared ExecutionMode:
- COGNITIVE_SYNTHESIS: Routes through primary Brain cognitive pipeline
- READ_ONLY_WORKER: Executes read-only analysis and state summarization
- WORKFLOW_PROPOSAL: Constructs structured WorkflowProposal for Agency approval
"""
from __future__ import annotations

import uuid
from typing import Any
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import (
    BrainProfileKey,
    CognitiveClaim,
    CognitiveResult,
    WorkflowProposal,
    WorkflowStepProposal,
)
from app.mind.capabilities.hydrator import HydratedCapabilityContext
from app.mind.capabilities.schemas import CapabilitySpec, ExecutionMode


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
        """Execute a deterministic, read-only analysis without durable side effects."""
        # For summarize_day:
        today_state = hydrated_context.today_state or {}
        timeline_events = hydrated_context.timeline_events or []
        active_plans = hydrated_context.active_plans or []

        lines: list[str] = ["### Daily Summary\n"]
        if today_state:
            phase = today_state.get("phase", "Active")
            focus = today_state.get("focus") or "General focus"
            lines.append(f"- **Current Phase**: {phase}")
            lines.append(f"- **Primary Focus**: {focus}")
        
        if active_plans:
            lines.append(f"- **Active Plans**: {len(active_plans)} plan(s) in progress")
            for plan in active_plans[:3]:
                lines.append(f"  - {plan.get('title', 'Untitled Plan')}")

        if timeline_events:
            lines.append(f"- **Timeline Events**: {len(timeline_events)} event(s) recorded")
            for ev in timeline_events[:3]:
                ev_title = ev.get("title") or ev.get("headline") or "Event"
                lines.append(f"  - {ev_title}")
        else:
            lines.append("- **Timeline**: No urgent events scheduled.")

        direct_response = "\n".join(lines)

        source_refs = [f"{r.kind}:{r.id}" for r in hydrated_context.retrieval_refs[:6]]
        claims: list[CognitiveClaim] = []
        if source_refs:
            claims.append(
                CognitiveClaim(
                    claim_text=f"Owner has {len(active_plans)} active plan(s) and {len(timeline_events)} recent timeline event(s).",
                    claim_kind="observed",
                    confidence=1.0,
                )
            )

        return CognitiveResult(
            task_id=task_id,
            profile_used=BrainProfileKey.FAST,
            direct_response=direct_response,
            claims=claims,
            source_refs=source_refs,
            decision_summary=f"Read-only synthesis by {capability.worker_role} ({capability.capability_id}).",
            cost_estimate_cents=capability.estimated_cost_cents,
        )

    @staticmethod
    async def _execute_workflow_proposal_worker(
        *,
        capability: CapabilitySpec,
        hydrated_context: HydratedCapabilityContext,
        query: str,
        task_id: uuid.UUID,
        params: dict[str, Any],
    ) -> CognitiveResult:
        """Construct a structured WorkflowProposal for Agency submission and owner review."""
        # Derive clean plan title
        raw_target = query.strip()
        for prefix in [
            "let's draft a plan to ",
            "draft a plan to ",
            "make a plan to ",
            "create a plan to ",
            "draft a plan ",
            "make a plan ",
            "plan to ",
        ]:
            if raw_target.lower().startswith(prefix):
                raw_target = raw_target[len(prefix):]
                break
        clean_target = raw_target.strip().capitalize() if raw_target.strip() else "New Plan"
        title = params.get("title") or (clean_target[:80] + "..." if len(clean_target) > 80 else clean_target)

        step_proposal = WorkflowStepProposal(
            key="step_1",
            title=f"Draft Plan: {title}",
            description=f"Create a draft plan for '{title}' based on user intent: {query}",
            tool_key="create_draft_plan",
            tool_version="1",
            risk_class="R1_PRIVATE_DRAFT",
            requires_approval=True,
            arguments={"title": title, "objective": query},
            estimated_cost_cents=capability.estimated_cost_cents,
        )

        proposal = WorkflowProposal(
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
            decision_summary=f"Proposed workflow via {capability.worker_role} ({capability.capability_id}).",
            cost_estimate_cents=capability.estimated_cost_cents,
        )
