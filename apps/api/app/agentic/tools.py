"""First-party NUR tool contracts.

This module is the join between the abstract risk classes the policy engine
reasons about and the real capabilities NUR has. It declares *contracts* — key,
version, risk class, required capabilities, idempotency and cost. Handlers are
bound separately in `registry.py`, and a contract without a bound handler is
never callable; the registry refuses to resolve it rather than returning
something empty that a planner would treat as success.

Two deliberate absences, both load-bearing:

There is no tool here for shell, filesystem, network, repository writes,
messaging, publish, deploy, payments, booking, security changes or secret
access. Not disabled — absent. A denied-but-present tool is one config edit away
from being live; a tool that does not exist has to be written, reviewed and
merged. The existing AM Projects capability catalog already denies these, and
this registry does not reintroduce them by the back door.

There is no `write_memory`. `create_memory_candidate` proposes; nothing here
promotes a candidate to owner truth. Model output never becomes OWNER_WRITTEN,
so the tool that would do it is not offered to a model.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.agentic.enums import RiskClass
from app.agentic.policy import ToolContract


@dataclass(frozen=True)
class ToolSpec:
    """A contract plus the metadata the runtime and audit trail need."""

    contract: ToolContract
    summary: str
    # What the owner is told this touches, in their words, for the approval card.
    reads: tuple[str, ...] = ()
    writes: tuple[str, ...] = ()
    idempotent: bool = True
    timeout_seconds: int = 30
    # Typed output references: result key -> entity kind. Declared by the tool
    # rather than inferred from the key's shape. Suffix matching on "_id"
    # classified every identifier as an artifact, so a plan id and a research
    # brief id were indistinguishable in the ledger — and neither was an
    # artifact at all.
    entity_refs: tuple[tuple[str, str], ...] = ()
    artifact_ref_keys: tuple[str, ...] = ()
    evidence_ref_keys: tuple[str, ...] = ()


def _tool(
    key: str,
    risk: RiskClass,
    summary: str,
    *,
    capabilities: tuple[str, ...] = (),
    reads: tuple[str, ...] = (),
    writes: tuple[str, ...] = (),
    idempotent: bool = True,
    cost_cents: int = 0,
    reversible: bool = True,
    timeout_seconds: int = 30,
    entity_refs: tuple[tuple[str, str], ...] = (),
    artifact_ref_keys: tuple[str, ...] = (),
    evidence_ref_keys: tuple[str, ...] = (),
) -> ToolSpec:
    return ToolSpec(
        contract=ToolContract(
            key=key,
            version="1",
            risk_class=risk,
            required_capabilities=frozenset(capabilities),
            estimated_cost_cents=cost_cents,
            reversible=reversible,
        ),
        summary=summary,
        reads=reads,
        writes=writes,
        idempotent=idempotent,
        timeout_seconds=timeout_seconds,
        entity_refs=entity_refs,
        artifact_ref_keys=artifact_ref_keys,
        evidence_ref_keys=evidence_ref_keys,
    )


R0 = RiskClass.R0_READ_ONLY
R1 = RiskClass.R1_PRIVATE_DRAFT
R2 = RiskClass.R2_DURABLE_PRIVATE


# ── Read-only. Nothing here may mutate; the tests assert it structurally. ────
READ_ONLY: tuple[ToolSpec, ...] = (
    _tool("get_today_state", R0, "The owner's current day state and next move.",
          capabilities=("read_today",), reads=("Today",)),
    _tool("get_system_snapshot", R0, "One Star System's current standing.",
          capabilities=("read_systems",), reads=("Systems",)),
    _tool("get_plan", R0, "A Plan and its steps.",
          capabilities=("read_plans",), reads=("Plans",)),
    _tool("get_timeline", R0, "Timeline events in a bounded window.",
          capabilities=("read_timeline",), reads=("Timeline",)),
    _tool("get_map_neighbourhood", R0, "The graph around one Map node.",
          capabilities=("read_map",), reads=("Map",)),
    _tool("get_orbit", R0, "An Orbit's context, members and open threads.",
          capabilities=("read_orbits",), reads=("Orbits",)),
    _tool("get_project", R0, "An AM Project and its task counts.",
          capabilities=("read_projects",), reads=("Projects",)),
    _tool("get_project_evidence", R0, "Verified evidence attached to a Project.",
          capabilities=("read_projects",), reads=("Project evidence",)),
    _tool("get_insight", R0, "One candidate or accepted Insight with its evidence.",
          capabilities=("read_insights",), reads=("Insights",)),
    # Named `approved` rather than `memory` on purpose: it cannot reach
    # candidates, and the name should not imply that it can.
    _tool("search_approved_memory", R0, "Search only owner-approved personal memory.",
          capabilities=("read_memory",), reads=("Approved memory",)),
    _tool("get_omega_workspace_frame", R0, "The current Omega consolidation frame.",
          capabilities=("read_omega",), reads=("Omega workspace",)),
)

# ── Private drafts. Reversible, owner-visible, never durable owner truth. ────
PRIVATE_DRAFT: tuple[ToolSpec, ...] = (
    _tool("create_draft_plan", R1, "Draft a Plan for the owner to review.",
          capabilities=("draft_plans",), writes=("Draft Plan",), idempotent=False, entity_refs=(("plan_id", "PLAN"),)),
    _tool("create_research_brief", R1, "Draft a research brief.",
          capabilities=("draft_research",), writes=("Research brief",), idempotent=False, entity_refs=(("brief_id", "RESEARCH_BRIEF"),)),
    # Proposes only. Promotion to owner truth is not a tool.
    _tool("create_memory_candidate", R1, "Propose a memory candidate for owner review.",
          capabilities=("propose_memory",), writes=("Memory candidate",), idempotent=False, entity_refs=(("candidate_id", "MEMORY_CANDIDATE"),)),
    _tool("create_project_task_draft", R1, "Draft a Project task.",
          capabilities=("draft_projects",), writes=("Draft task",), idempotent=False),
    _tool("create_timeline_draft", R1, "Draft a Timeline event, unscheduled.",
          capabilities=("draft_timeline",), writes=("Draft Timeline event",), idempotent=False, entity_refs=(("event_id", "TIMELINE_EVENT"),)),
    _tool("create_insight_candidate", R1, "Propose a candidate Insight with evidence.",
          capabilities=("propose_insights",), writes=("Candidate Insight",), idempotent=False, entity_refs=(("insight_id", "INSIGHT"),)),
    _tool("save_private_artifact", R1, "Store a private artifact for the owner.",
          capabilities=("write_artifacts",), writes=("Private artifact",), idempotent=False,
          artifact_ref_keys=("artifact_id",)),
)

# ── Durable private mutations. Owner approval by default via the policy engine. ─
DURABLE: tuple[ToolSpec, ...] = (
    _tool("activate_plan", R2, "Activate a drafted Plan.",
          capabilities=("write_plans",), writes=("Plan",), idempotent=False, entity_refs=(("plan_id", "PLAN"),)),
    _tool("schedule_timeline_event", R2, "Schedule a Timeline event.",
          capabilities=("write_timeline",), writes=("Timeline event",), idempotent=False, entity_refs=(("event_id", "TIMELINE_EVENT"),)),
    _tool("complete_task", R2, "Mark a task complete.",
          capabilities=("write_projects",), writes=("Project task",), idempotent=False),
    _tool("accept_or_correct_insight", R2, "Record the owner's decision on an Insight.",
          capabilities=("write_insights",), writes=("Insight status",), idempotent=False, entity_refs=(("insight_id", "INSIGHT"),)),
    # Capsules leave the owner's private boundary in a bounded way, so this is
    # the highest-consequence tool in the set even though it stays internal.
    _tool("create_capsule", R2, "Create a Context Capsule from explicitly chosen sources.",
          capabilities=("write_capsules",), writes=("Capsule",), idempotent=False,
          reversible=False),
    _tool("queue_project_run", R2, "Queue an approved Project run.",
          capabilities=("write_projects", "queue_runs"), writes=("Project run",),
          idempotent=False),
)

ALL_TOOLS: tuple[ToolSpec, ...] = READ_ONLY + PRIVATE_DRAFT + DURABLE

# Capability names a tool may legitimately require. A tool asking for anything
# outside this set is a typo or an escalation attempt, and the test suite treats
# both the same way.
KNOWN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "read_today", "read_systems", "read_plans", "read_timeline", "read_map",
        "read_orbits", "read_projects", "read_insights", "read_memory", "read_omega",
        "draft_plans", "draft_research", "propose_memory", "draft_projects",
        "draft_timeline", "propose_insights", "write_artifacts",
        "write_plans", "write_timeline", "write_projects", "write_insights",
        "write_capsules", "queue_runs",
    }
)

# Capabilities that must never appear in a first-party contract. Kept explicit
# so a future addition trips a test rather than a review's attention span.
FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "shell", "filesystem", "network", "repo_write", "publish", "deploy",
        "spend", "payments", "messaging", "secrets", "delete_owner_data",
        "write_memory",
    }
)
