from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from app.brain.schemas import CognitiveTaskPacket, WorkflowProposalV2, WorkflowStepProposal


class PlanBudget(BaseModel):
    max_steps: int = Field(default=8, ge=1, le=32)
    max_cost_cents: int = Field(default=1000, ge=0, le=1_000_000)
    max_time_seconds: int = Field(default=300, ge=1, le=86_400)


class PlanCandidate(BaseModel):
    """A typed, non-executing candidate path for Brain-side comparison."""

    candidate_id: str
    objective: str
    assumptions: list[str] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    required_capabilities: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    reversible: bool = True
    estimated_cost_cents: int = Field(default=0, ge=0)
    estimated_time_seconds: int = Field(default=0, ge=0)
    uncertainty: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    failure_modes: list[str] = Field(default_factory=list)
    owner_approval_required: bool = True


class TypedPlanner:
    """Builds typed candidate paths without executing tools or granting authority."""

    def plan(
        self,
        packet: CognitiveTaskPacket,
        *,
        tool_key: str,
        arguments: dict,
        budget: PlanBudget,
    ) -> WorkflowProposalV2:
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
        return WorkflowProposalV2(
            task_id=packet.task_id,
            title="Owner-requested workflow",
            rationale="Typed planner output from the frozen CognitiveTaskPacket.",
            steps=[step],
            total_estimated_cost_cents=0,
        )

    def plan_candidates(
        self,
        packet: CognitiveTaskPacket,
        *,
        success_criteria: list[str],
        capability_constraints: set[str] | frozenset[str],
        resource_constraints: dict[str, int] | None = None,
        authority_constraints: list[str] | None = None,
    ) -> list[PlanCandidate]:
        """Return more than one bounded path when the task admits alternatives.

        The planner only represents options. It does not retrieve, call a provider,
        invoke a tool, approve a write, or turn inferred content into owner truth.
        """
        resources = resource_constraints or {}
        capabilities = sorted(capability_constraints)
        authorities = list(authority_constraints or [])
        objective = packet.user_input.strip() or "Complete the owner request"
        evidence_count = len(packet.evidence_refs) + len(packet.context_manifest.included)
        evidence_gap = [] if evidence_count else ["no scoped evidence is available"]
        approval_required = any("approval" in item.lower() for item in authorities) or True
        max_cost = resources.get("max_cost_cents", 1000)
        max_time = resources.get("max_time_seconds", 300)

        evidence_first = PlanCandidate(
            candidate_id="evidence-first",
            objective=objective,
            assumptions=["permitted evidence can be retrieved within the resolved scope"],
            steps=["retrieve permitted evidence", "compare supported options", "present owner-visible result"],
            dependencies=["scope resolution", "permitted source access"],
            required_capabilities=[cap for cap in ("retrieve", "summarize") if cap in capabilities] or capabilities,
            constraints=authorities + ["no durable write before owner approval"],
            success_criteria=list(success_criteria),
            reversible=True,
            estimated_cost_cents=min(10, max_cost),
            estimated_time_seconds=min(60, max_time),
            uncertainty=["retrieval coverage may be incomplete"],
            evidence_gaps=list(evidence_gap),
            failure_modes=["permitted retrieval returns no current source", "sources contradict one another"],
            owner_approval_required=approval_required,
        )
        review_first = PlanCandidate(
            candidate_id="review-first",
            objective=objective,
            assumptions=["the owner can review a bounded draft before any durable action"],
            steps=["prepare a reversible draft", "surface assumptions and gaps", "request owner decision"],
            dependencies=["owner review"],
            required_capabilities=[cap for cap in ("summarize",) if cap in capabilities] or capabilities,
            constraints=authorities + ["draft-only", "no owner fact inferred from uncertainty"],
            success_criteria=list(success_criteria),
            reversible=True,
            estimated_cost_cents=min(5, max_cost),
            estimated_time_seconds=min(45, max_time),
            uncertainty=["owner preference is not yet explicit"],
            evidence_gaps=list(evidence_gap) or ["owner decision criteria are not yet explicit"],
            failure_modes=["draft does not satisfy the owner success criteria", "owner rejects the proposed framing"],
            owner_approval_required=approval_required,
        )
        return [evidence_first, review_first]


class SimulationCandidate(BaseModel):
    candidate_id: str
    allowed: bool
    reversible: bool
    estimated_cost_cents: int
    estimated_time_seconds: int
    failure_modes: list[str] = Field(default_factory=list)
    uncertainty: list[str] = Field(default_factory=list)
    evidence_gaps: list[str] = Field(default_factory=list)
    violations: list[str] = Field(default_factory=list)


class SimulationResult(BaseModel):
    allowed: bool
    comparisons: list[str] = Field(default_factory=list)
    estimated_cost_cents: int = 0
    candidates: list[SimulationCandidate] = Field(default_factory=list)
    comparison_summary: str = ""
    uncertainty_preserved: bool = True


class BoundedSimulator:
    """Performs bounded counterfactual comparison without fabricating probabilities."""

    def simulate(self, proposal: WorkflowProposalV2, *, budget: PlanBudget) -> SimulationResult:
        if len(proposal.steps) > budget.max_steps:
            return SimulationResult(allowed=False, comparisons=["step_width_exceeded"])
        total = sum(step.estimated_cost_cents for step in proposal.steps)
        if total > budget.max_cost_cents:
            return SimulationResult(
                allowed=False,
                comparisons=["cost_ceiling_exceeded"],
                estimated_cost_cents=total,
            )
        return SimulationResult(
            allowed=True,
            comparisons=[f"steps={len(proposal.steps)}", f"cost={total}"],
            estimated_cost_cents=total,
            candidates=[
                SimulationCandidate(
                    candidate_id=proposal.proposal_id.hex,
                    allowed=True,
                    reversible=all(step.risk_class != "R3_EXTERNAL_SIDE_EFFECT" for step in proposal.steps),
                    estimated_cost_cents=total,
                    estimated_time_seconds=sum(step.timeout_seconds for step in proposal.steps),
                    failure_modes=["tool execution may fail after Agency approval"],
                    uncertainty=["simulation is not an execution result"],
                )
            ],
            comparison_summary="Single proposal bounded for steps and cost; no tool was executed.",
        )

    def simulate_candidates(
        self,
        candidates: list[PlanCandidate],
        *,
        budget: PlanBudget,
    ) -> SimulationResult:
        if not candidates:
            return SimulationResult(allowed=False, comparisons=["no_candidates"])
        simulated: list[SimulationCandidate] = []
        violations: list[str] = []
        total = 0
        for candidate in candidates:
            candidate_violations: list[str] = []
            if len(candidate.steps) > budget.max_steps:
                candidate_violations.append("step_width_exceeded")
            if candidate.estimated_cost_cents > budget.max_cost_cents:
                candidate_violations.append("cost_ceiling_exceeded")
            if candidate.estimated_time_seconds > budget.max_time_seconds:
                candidate_violations.append("deadline_exceeded")
            total += candidate.estimated_cost_cents
            violations.extend(f"{candidate.candidate_id}:{item}" for item in candidate_violations)
            simulated.append(
                SimulationCandidate(
                    candidate_id=candidate.candidate_id,
                    allowed=not candidate_violations,
                    reversible=candidate.reversible,
                    estimated_cost_cents=candidate.estimated_cost_cents,
                    estimated_time_seconds=candidate.estimated_time_seconds,
                    failure_modes=list(candidate.failure_modes),
                    uncertainty=list(candidate.uncertainty),
                    evidence_gaps=list(candidate.evidence_gaps),
                    violations=candidate_violations,
                )
            )
        return SimulationResult(
            allowed=not violations,
            comparisons=[
                f"candidates={len(candidates)}",
                "reversibility_preserved",
                "failure_modes_preserved",
                "evidence_gaps_preserved",
            ] + violations,
            estimated_cost_cents=total,
            candidates=simulated,
            comparison_summary=(
                "Compared candidate assumptions, dependencies, outcomes, failure modes, "
                "reversibility, cost, time, uncertainty, and evidence gaps without numerical probabilities."
            ),
            uncertainty_preserved=True,
        )
