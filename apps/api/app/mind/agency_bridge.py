"""NUR Mind to Agency Bridge — handoff from CognitiveResult / WorkflowProposal into existing Agency Spine.

Maps a ``WorkflowProposal`` into Agency ``ProposedStep`` items, evaluates owner policy via ``load_policy``,
compiles via ``compile_plan()``, and persists durable ``AgentWorkflow``, ``AgentStep``, and ``AgentApproval`` rows.
Ensures durable execution never occurs before required approval.
"""
from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic.compiler import ProposedStep, compile_plan, CompileResult
from app.agentic.input_schemas import validate_arguments
from app.agentic.orchestrator import argument_digest
from app.agentic.policy_store import load_policy
from app.agentic.redaction import contains_secret, redact_arguments
from app.agentic.registry import UnknownToolError, spec as get_tool_spec
from app.brain.schemas import WorkflowProposal
from app.models.agentic import AgentWorkflow, AgentStep, AgentApproval


class AgencyBridgeError(ValueError):
    """Raised when a WorkflowProposal fails structural, tool, or argument contract validation."""


_RISK_RANK = {
    "R0_READ_ONLY": 0,
    "R1_PRIVATE_DRAFT": 1,
    "R2_DURABLE_ACTION": 2,
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

        tool_version = getattr(step, "tool_version", None) or tool_spec.contract.version
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

    # Determine workflow status based on whether any step requires approval
    requires_approval = any(s.approval_required for s in compile_result.steps)
    initial_state = "BLOCKED_ON_APPROVAL" if requires_approval else "READY"

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
        state=initial_state,
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

    for compiled_step in compile_result.steps:
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
            depends_on=list(compiled_step.depends_on),
            state=compiled_step.state.value,
            input_refs=compiled_step.input_refs,
            timeout_seconds=compiled_step.timeout_seconds,
        )
        db.add(db_step)
        await db.flush()

        if compiled_step.approval_required:
            redacted_arguments = redact_arguments(compiled_step.input_refs, drop_private_text=False)
            digest_str = argument_digest(
                compiled_step.tool_key,
                compiled_step.tool_version,
                redacted_arguments,
            )
            step_rationale = (
                compiled_step.input_refs.get("title")
                or compiled_step.input_refs.get("description")
                or compiled_step.key
            )
            db_approval = AgentApproval(
                owner_user_id=owner_user_id,
                workflow_id=workflow.id,
                step_id=db_step.id,
                tool_key=compiled_step.tool_key,
                tool_version=compiled_step.tool_version,
                argument_digest=digest_str,
                plan_version=1,
                call_version="1",
                redacted_arguments=redacted_arguments,
                rationale=str(step_rationale),
                risk_class=compiled_step.risk_class,
                decision="PENDING",
            )
            db.add(db_approval)

    await db.flush()
    return workflow, compile_result

