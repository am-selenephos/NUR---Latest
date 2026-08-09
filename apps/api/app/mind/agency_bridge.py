"""NUR Mind to Agency Bridge — handoff from CognitiveResult / WorkflowProposal into existing Agency Spine.

Maps a ``WorkflowProposal`` into Agency ``ProposedStep`` items, evaluates owner policy via ``load_policy``,
compiles via ``compile_plan()``, and persists durable ``AgentWorkflow``, ``AgentStep``, and ``AgentApproval`` rows.
Ensures durable execution never occurs before required approval.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.compiler import CompileResult, ProposedStep, compile_plan
from app.agentic.enums import StepState, WorkflowState
from app.agentic.input_schemas import validate_arguments
from app.agentic.orchestrator import record_event
from app.agentic.policy_store import load_policy
from app.agentic.redaction import contains_secret
from app.agentic.registry import UnknownToolError, spec as get_tool_spec
from app.agentic.runtime import _ensure_approval_row
from app.brain.schemas import WorkflowProposal
from app.models.agentic import AgentStep, AgentWorkflow


class AgencyBridgeError(ValueError):
    """Raised when a WorkflowProposal fails structural, tool, or argument contract validation."""


SAFE_REFUSAL_CODES: frozenset[str] = frozenset({
    "POLICY_DENIED",
    "UNKNOWN_TOOL",
    "RISK_EXCEEDS_POLICY",
    "INVALID_DEPENDENCY",
    "INVALID_ARGUMENTS",
    "COMPILATION_REFUSED",
})


def map_compile_error_to_safe_code(code: str) -> str:
    """Map Agency compiler error codes into bounded, safe refusal reason codes."""
    mapping = {
        "POLICY_DENIED": "POLICY_DENIED",
        "UNKNOWN_TOOL": "UNKNOWN_TOOL",
        "RISK_EXCEEDS_POLICY": "RISK_EXCEEDS_POLICY",
        "DANGLING_DEPENDENCY": "INVALID_DEPENDENCY",
        "SELF_DEPENDENCY": "INVALID_DEPENDENCY",
        "CYCLIC_PLAN": "INVALID_DEPENDENCY",
        "VERIFIER_WITHOUT_SUBJECT": "INVALID_DEPENDENCY",
        "EMPTY_PLAN": "INVALID_ARGUMENTS",
        "DUPLICATE_STEP_KEY": "INVALID_ARGUMENTS",
        "INVALID_ARGUMENTS": "INVALID_ARGUMENTS",
        "VERIFIER_MUTATES": "POLICY_DENIED",
        "SELF_VERIFICATION": "POLICY_DENIED",
    }
    safe_code = mapping.get(code, "COMPILATION_REFUSED")
    return safe_code if safe_code in SAFE_REFUSAL_CODES else "COMPILATION_REFUSED"


_RISK_RANK = {
    "R0_READ_ONLY": 0,
    "R1_PRIVATE_DRAFT": 1,
    "R2_DURABLE_PRIVATE": 2,
    "R3_EXTERNAL": 3,
    "R4_IRREVERSIBLE": 4,
}


async def submit_workflow_proposal(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    proposal: WorkflowProposal,
    orbit_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
) -> tuple[AgentWorkflow | None, CompileResult]:
    """Compile a ``WorkflowProposal`` through existing Agency compiler and persist rows."""
    proposed_steps: list[ProposedStep] = []
    for idx, step in enumerate(proposal.steps):
        step_key = getattr(step, "key", None)
        if not step_key or not str(step_key).strip():
            raise AgencyBridgeError(
                f"Workflow step at index {idx} is missing required explicit 'key'. Keys cannot be fabricated."
            )
        step_key = str(step_key).strip()

        tool_key = getattr(step, "tool_key", None)
        if not tool_key or not str(tool_key).strip():
            raise AgencyBridgeError(f"Workflow step '{step_key}' is missing required 'tool_key'. Zero silent fallback.")
        tool_key = str(tool_key).strip()

        # 1. Validate tool registration in Agency registry
        try:
            tool_spec = get_tool_spec(tool_key)
        except UnknownToolError:
            raise AgencyBridgeError(f"Unregistered Agency tool '{tool_key}' in step '{step_key}'.")

        tool_version = getattr(step, "tool_version", None)
        if not tool_version or not str(tool_version).strip():
            raise AgencyBridgeError(
                f"Workflow step '{step_key}' is missing required 'tool_version'. Zero silent fallback."
            )
        if str(tool_version) != str(tool_spec.contract.version):
            raise AgencyBridgeError(
                f"Tool version mismatch for '{tool_key}' in step '{step_key}': "
                f"expected {tool_spec.contract.version}, got {tool_version}"
            )

        # 2. Build and validate input_refs against authoritative Agency input schemas
        if step.arguments is None:
            raise AgencyBridgeError(
                f"Workflow step '{step_key}' is missing required 'arguments'. Arguments cannot be fabricated."
            )
        input_refs = dict(step.arguments)

        # Reject secrets
        if contains_secret(input_refs):
            raise AgencyBridgeError(f"Step '{step_key}' arguments contain forbidden secret keys.")

        # Authoritative schema validation (rejects extra keys like 'objective', missing required, bad types)
        problems = validate_arguments(tool_key, input_refs)
        if problems:
            raise AgencyBridgeError(
                f"Argument validation failed for tool '{tool_key}' in step '{step_key}': {', '.join(problems)}"
            )

        dependencies = tuple(getattr(step, "dependencies", ()) or ())
        rationale = getattr(step, "description", "") or getattr(step, "title", "")

        proposed_steps.append(
            ProposedStep(
                key=step_key,
                role="SPECIALIST",
                tool_key=tool_key,
                depends_on=dependencies,
                input_refs=input_refs,
                rationale=rationale,
            )
        )

    policy = await load_policy(db, owner_user_id=owner_user_id, orbit_id=orbit_id, project_id=project_id)
    compile_result = compile_plan(tuple(proposed_steps), policy)

    if not compile_result.ok or not compile_result.steps:
        return None, compile_result

    # Derive truthful max_risk_class from compiled steps
    highest_risk = "R0_READ_ONLY"
    max_rank = 0
    for s in compile_result.steps:
        r = s.risk_class
        rank = _RISK_RANK.get(r, 0)
        if rank > max_rank:
            max_rank = rank
            highest_risk = r

    workflow = AgentWorkflow(
        owner_user_id=owner_user_id,
        kind="COGNITIVE_WORKFLOW",
        title=proposal.title,
        objective=proposal.rationale,
        state=WorkflowState.PLAN_READY.value,
        plan_version=1,
        trigger_kind="MIND_COGNITIVE_RESULT",
        trigger_ref=proposal.task_id,
        initiative_level="SUGGEST",
        scope="PRIVATE",
        orbit_id=orbit_id,
        project_id=project_id,
        budget_cents=proposal.total_estimated_cost_cents,
        cost_cents=0,
        max_risk_class=highest_risk,
    )
    db.add(workflow)
    await db.flush()

    persisted_steps: list[tuple[AgentStep, ProposedStep]] = []
    proposed_by_key = {step.key: step for step in proposed_steps}
    for compiled_step in compile_result.steps:
        state = compiled_step.state
        if compiled_step.approval_required and state is StepState.READY:
            state = StepState.WAITING_APPROVAL
        db_step = AgentStep(
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            ordinal=compiled_step.ordinal,
            key=compiled_step.key,
            role=compiled_step.role,
            tool_key=compiled_step.tool_key,
            tool_version=compiled_step.tool_version,
            risk_class=compiled_step.risk_class,
            requested_capabilities=list(compiled_step.requested_capabilities),
            approval_required=compiled_step.approval_required,
            depends_on=list(compiled_step.depends_on),
            state=state.value,
            input_refs=compiled_step.input_refs,
            timeout_seconds=compiled_step.timeout_seconds,
            idempotency_key=(
                f"mind-workflow:{workflow.id}:{workflow.plan_version}:{compiled_step.key}"
            ),
        )
        db.add(db_step)
        persisted_steps.append((db_step, proposed_by_key[compiled_step.key]))

    await db.flush()
    for db_step, proposed_step in persisted_steps:
        if db_step.state != StepState.WAITING_APPROVAL.value:
            continue
        contract = get_tool_spec(db_step.tool_key or "").contract
        await _ensure_approval_row(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            step_id=db_step.id,
            tool_key=contract.key,
            tool_version=contract.version,
            arguments=dict(db_step.input_refs or {}),
            rationale=proposed_step.rationale,
            risk_class=contract.risk_class.value,
            reversible=contract.reversible,
            cost_ceiling_cents=contract.estimated_cost_cents,
            expected_result=proposal.rationale,
            scope_summary=(
                f"orbit={orbit_id or 'account'}; project={project_id or 'none'}"
            ),
        )
        await record_event(
            db,
            owner_user_id=owner_user_id,
            workflow_id=workflow.id,
            step_id=db_step.id,
            event_type="STEP_AWAITING_APPROVAL",
            summary="current owner policy requires approval before dispatch",
            from_state=StepState.READY.value,
            to_state=StepState.WAITING_APPROVAL.value,
            actor="SYSTEM",
        )
    await db.flush()
    return workflow, compile_result
