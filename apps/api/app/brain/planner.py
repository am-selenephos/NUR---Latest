"""Typed, deterministic planning and bounded simulation primitives."""
from __future__ import annotations

from pydantic import BaseModel, Field

from app.brain.schemas import CognitiveTaskPacket, WorkflowProposalV2, WorkflowStepProposal


class PlanBudget(BaseModel):
    max_steps: int = Field(default=8, ge=1, le=32)
    max_cost_cents: int = Field(default=1000, ge=0, le=1_000_000)


class TypedPlanner:
    def plan(self, packet: CognitiveTaskPacket, *, tool_key: str, arguments: dict, budget: PlanBudget) -> WorkflowProposalV2:
        if budget.max_steps < 1:
            raise ValueError("Planner requires at least one step.")
        step = WorkflowStepProposal(
            key="owner-request",
            title="Owner-requested action",
            description=packet.user_input,
            tool_key=tool_key,
            tool_version="1",
            arguments=dict(arguments),
            estimated_cost_cents=0,
        )
        proposal = WorkflowProposalV2(
            task_id=packet.task_id,
            title="Owner-requested workflow",
            rationale="Typed planner output from the frozen CognitiveTaskPacket.",
            steps=[step],
            total_estimated_cost_cents=0,
        )
        return proposal


class SimulationResult(BaseModel):
    allowed: bool
    comparisons: list[str] = Field(default_factory=list)
    estimated_cost_cents: int = 0


class BoundedSimulator:
    def simulate(self, proposal: WorkflowProposalV2, *, budget: PlanBudget) -> SimulationResult:
        if len(proposal.steps) > budget.max_steps:
            return SimulationResult(allowed=False, comparisons=["step_width_exceeded"])
        total = sum(step.estimated_cost_cents for step in proposal.steps)
        if total > budget.max_cost_cents:
            return SimulationResult(allowed=False, comparisons=["cost_ceiling_exceeded"], estimated_cost_cents=total)
        return SimulationResult(
            allowed=True,
            comparisons=[f"steps={len(proposal.steps)}", f"cost={total}"],
            estimated_cost_cents=total,
        )
