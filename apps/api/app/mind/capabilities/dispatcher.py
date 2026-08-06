from __future__ import annotations

import re
import uuid
from collections.abc import Awaitable, Callable
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
    ) -> CognitiveResult:
        """Construct a preview or structured WorkflowProposal for Agency submission."""
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
        is_preview_only = False
        q_lower = query.lower()
        preview_triggers = ("plan this out", "show me a plan", "outline a plan", "how would you plan", "preview plan")
        persist_triggers = ("draft a plan", "create a plan", "make a plan", "save plan", "save draft", "create draft")
        if any(pt in q_lower for pt in preview_triggers) and not any(st in q_lower for st in persist_triggers):
            is_preview_only = True

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
                decision_summary=f"Plan preview outline generated for '{title}' (no workflow proposal created).",
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


