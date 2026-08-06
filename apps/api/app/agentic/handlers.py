"""Read-only tool handlers, bound to the services that already exist.

Every handler here delegates to the same function the HTTP route uses. That
import direction — agentic reaching into `api.v1` — is not the tidiest layering,
and it is deliberate. The alternative is a second implementation of the same
query, and a second implementation drifts from the first silently: the route and
the tool would answer the same question differently, and nothing would fail.
Sharing one function makes drift impossible rather than merely unlikely.

Only R0 tools are bound in this module. Every handler takes an already
RLS-scoped session and an owner id and returns plain data. None of them writes,
which is asserted structurally by the tests rather than promised here.

Tools without a handler stay unbound on purpose. `registry.handler` raises
`UnboundToolError` for those, so an unimplemented tool fails loudly instead of
returning an empty result a planner would treat as a completed step.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agentic import registry


async def get_map_neighbourhood(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    node_id: str | None = None,
    depth: int = 1,
) -> dict[str, Any]:
    """The graph around one node, or the whole owner graph when none is named.

    Delegates to the map endpoint's own assembly so the tool and the Map lens
    can never disagree about what the owner's graph contains.
    """
    from app.api.v1.map import _map_snapshot

    snapshot = await _map_snapshot(db, owner_user_id)
    if not node_id:
        return snapshot

    nodes = {node["id"]: node for node in snapshot["nodes"]}
    if node_id not in nodes:
        # An unknown node is not an empty neighbourhood — saying "nothing is
        # connected to this" when the node does not exist would be a false
        # answer rather than a null one.
        return {
            "found": False,
            "node_id": node_id,
            "provenance_label": snapshot["provenance_label"],
        }

    keep = {node_id}
    frontier = {node_id}
    for _ in range(max(0, depth)):
        nxt: set[str] = set()
        for edge in snapshot["edges"]:
            if edge["source"] in frontier:
                nxt.add(edge["target"])
            elif edge["target"] in frontier:
                nxt.add(edge["source"])
        nxt -= keep
        if not nxt:
            break
        keep |= nxt
        frontier = nxt

    return {
        "found": True,
        "node_id": node_id,
        "depth": depth,
        "nodes": [nodes[key] for key in keep if key in nodes],
        "edges": [
            edge
            for edge in snapshot["edges"]
            if edge["source"] in keep and edge["target"] in keep
        ],
        "provenance_label": snapshot["provenance_label"],
    }


async def get_timeline(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    limit: int = 50,
) -> dict[str, Any]:
    """Timeline events in a bounded window."""
    from app.domain_reads.timeline import read_timeline

    bounded_limit = min(max(1, limit), 200)
    return await read_timeline(db, owner_user_id=owner_user_id, limit=bounded_limit)


async def search_approved_memory(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    query: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    """Approved personal memory only — never candidates.

    The filter is the entire point of the tool. A candidate is something NUR
    proposed and the owner has not accepted; returning one here would let model
    output re-enter a later run wearing the authority of owner truth.
    """
    from app.models.memory import PersonalMemory

    bounded = max(1, min(int(limit), 100))
    statement = select(PersonalMemory).where(
        PersonalMemory.owner_user_id == owner_user_id
    )
    if hasattr(PersonalMemory, "status"):
        statement = statement.where(PersonalMemory.status == "APPROVED")
    if query:
        statement = statement.where(PersonalMemory.content.ilike(f"%{query}%"))

    rows = (await db.execute(statement.limit(bounded))).scalars().all()
    return {
        "count": len(rows),
        "query": query,
        "memories": [{"id": str(row.id), "content": row.content} for row in rows],
        "provenance_label": "Owner-approved memory only; candidates are excluded",
    }


def _owned(statement, model, owner_user_id):
    """Add an explicit owner filter when the model carries one.

    RLS already confines the session, so this is defence in depth rather than
    the primary control. It costs nothing and means a handler run against a
    session whose context was never set returns nothing instead of everything.
    """
    column = getattr(model, "owner_user_id", None)
    return statement.where(column == owner_user_id) if column is not None else statement


async def get_today_state(db: AsyncSession, owner_user_id: uuid.UUID) -> dict[str, Any]:
    """The owner's current day. Delegates to canonical today domain read service."""
    from app.domain_reads.today import read_today_state

    return await read_today_state(db, owner_user_id=owner_user_id)


async def get_plan(
    db: AsyncSession, owner_user_id: uuid.UUID, *, plan_id: str | None = None
) -> dict[str, Any]:
    """Owner-scoped plan reader. Delegates to canonical plans domain read service."""
    from app.domain_reads.plans import read_plans

    return await read_plans(db, owner_user_id=owner_user_id, plan_id=plan_id)


async def get_system_snapshot(
    db: AsyncSession, owner_user_id: uuid.UUID, *, system_slug: str
) -> dict[str, Any]:
    """One Star System's standing: its founder-locked definition plus the
    owner's goals inside it. The definition comes from the catalog rather than
    the database because it is not owner data and must not drift per owner."""
    from app.living.catalog import SYSTEMS
    from app.models.living import Goal

    definition = next((s for s in SYSTEMS if s.slug == system_slug), None)
    if definition is None:
        return {"found": False, "system_slug": system_slug}

    goals = (
        await db.execute(
            _owned(select(Goal), Goal, owner_user_id).where(Goal.system_slug == system_slug)
        )
    ).scalars().all()
    return {
        "found": True,
        "system_slug": system_slug,
        "title": definition.title,
        "definition": definition.definition,
        "goals": [
            {
                "id": str(g.id),
                "title": g.title,
                "status": g.status,
                "progress_percent": g.progress_percent,
            }
            for g in goals
        ],
    }


async def get_orbit(
    db: AsyncSession, owner_user_id: uuid.UUID, *, orbit_id: str | None = None
) -> dict[str, Any]:
    from app.models.orbit import Orbit

    statement = _owned(select(Orbit), Orbit, owner_user_id)
    if orbit_id:
        statement = statement.where(Orbit.id == uuid.UUID(orbit_id))
    rows = (await db.execute(statement.limit(50))).scalars().all()
    if orbit_id and not rows:
        return {"found": False, "orbit_id": orbit_id}
    return {
        "found": True,
        "count": len(rows),
        "orbits": [
            {
                "id": str(r.id),
                "title": r.title,
                "kind": str(r.kind),
                "status": str(r.status),
                "system_slug": r.system_slug,
                # privacy_scope is included because a tool result that omits it
                # would let a later step treat a shared Orbit as private.
                "privacy_scope": str(r.privacy_scope),
            }
            for r in rows
        ],
    }


async def get_project(
    db: AsyncSession, owner_user_id: uuid.UUID, *, project_id: str | None = None
) -> dict[str, Any]:
    from app.models.projects import AMProject

    statement = _owned(select(AMProject), AMProject, owner_user_id)
    if project_id:
        statement = statement.where(AMProject.id == uuid.UUID(project_id))
    rows = (await db.execute(statement.limit(50))).scalars().all()
    if project_id and not rows:
        return {"found": False, "project_id": project_id}
    return {
        "found": True,
        "count": len(rows),
        "projects": [
            {
                "id": str(r.id),
                "title": r.title,
                "objective": r.objective,
                "status": str(r.status),
                "system_slug": r.system_slug,
            }
            for r in rows
        ],
    }


async def get_project_evidence(
    db: AsyncSession, owner_user_id: uuid.UUID, *, project_id: str
) -> dict[str, Any]:
    """Evidence attached to a Project, with its verification status.

    `verification_status` is returned on every row and never filtered away: an
    unverified piece of evidence is still evidence, and hiding the distinction
    would let a later step cite it as though it had been checked.
    """
    from app.models.projects import AMProjectEvidence

    rows = (
        await db.execute(
            _owned(select(AMProjectEvidence), AMProjectEvidence, owner_user_id)
            .where(AMProjectEvidence.project_id == uuid.UUID(project_id))
            .limit(100)
        )
    ).scalars().all()
    return {
        "project_id": project_id,
        "count": len(rows),
        "evidence": [
            {
                "id": str(r.id),
                "kind": r.evidence_kind,
                "summary": r.summary,
                "verification_status": r.verification_status,
                "verifier": r.verifier,
            }
            for r in rows
        ],
    }


async def get_insight(
    db: AsyncSession, owner_user_id: uuid.UUID, *, insight_id: str | None = None
) -> dict[str, Any]:
    """An Insight with its doubt attached.

    `what_nur_may_be_wrong_about` and `counter_evidence` are returned alongside
    the claim, never separately. An Insight quoted without its own account of
    where it might be wrong is exactly the unlabelled certainty this product is
    built to refuse.
    """
    from app.models.intelligence import Insight

    statement = _owned(select(Insight), Insight, owner_user_id)
    if insight_id:
        statement = statement.where(Insight.id == uuid.UUID(insight_id))
    rows = (await db.execute(statement.limit(25))).scalars().all()
    if insight_id and not rows:
        return {"found": False, "insight_id": insight_id}
    return {
        "found": True,
        "count": len(rows),
        "insights": [
            {
                "id": str(r.id),
                "title": r.title,
                "claim": r.claim,
                "status": r.status,
                "confidence": r.confidence,
                "confidence_meaning": "Source coverage and evidence strength, not guaranteed truth",
                "evidence": r.evidence,
                "counter_evidence": r.counter_evidence,
                "what_nur_may_be_wrong_about": r.what_nur_may_be_wrong_about,
                "provenance_label": r.provenance_label,
            }
            for r in rows
        ],
    }


def bind_read_only_handlers() -> tuple[str, ...]:
    """Attach the handlers above. Returns the keys that are now callable.

    Called explicitly rather than at import time so a test can assert what is
    bound and what deliberately is not.
    """
    registry.bind("get_map_neighbourhood", get_map_neighbourhood)
    registry.bind("get_timeline", get_timeline)
    registry.bind("search_approved_memory", search_approved_memory)
    registry.bind("get_today_state", get_today_state)
    registry.bind("get_plan", get_plan)
    registry.bind("get_system_snapshot", get_system_snapshot)
    registry.bind("get_orbit", get_orbit)
    registry.bind("get_project", get_project)
    registry.bind("get_project_evidence", get_project_evidence)
    registry.bind("get_insight", get_insight)
    return registry.bound_keys()


# ── R1: private drafts ───────────────────────────────────────────────────────
#
# The first writes in this spine. Three rules hold for every one of them and are
# asserted by the tests rather than trusted here:
#
#   Nothing created by a tool is OWNER_WRITTEN. Provenance is MODEL_GENERATED,
#   always, because the owner did not write it — NUR proposed it. That label is
#   what lets every later surface show the difference, and a draft that lied
#   about its origin would poison the record permanently.
#
#   Nothing is created in an accepted or active state. A draft Plan is DRAFT, a
#   candidate Insight is CANDIDATE, a memory candidate is PENDING. Promotion is
#   an owner action and there is no tool for it.
#
#   Everything is reversible. These are R1 precisely because the owner can throw
#   them away without consequence.

MODEL_PROVENANCE = "MODEL_GENERATED"


async def create_draft_plan(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    title: str,
    orbit_id: str | None = None,
    steps: list[str] | None = None,
) -> dict[str, Any]:
    """Draft a Plan in DRAFT status. Activation is a separate, approval-gated tool."""
    from app.models.cognition import Plan, PlanStep

    plan = Plan(owner_user_id=owner_user_id, title=title.strip(), status="DRAFT")
    if orbit_id:
        plan.orbit_id = uuid.UUID(orbit_id)
    db.add(plan)
    await db.flush()

    created = []
    for position, step_title in enumerate(steps or [], start=1):
        step = PlanStep(
            owner_user_id=owner_user_id,
            plan_id=plan.id,
            title=step_title.strip(),
            position=position,
            done=False,
        )
        db.add(step)
        created.append(step_title.strip())

    await db.flush()
    return {
        "created": True,
        "plan_id": str(plan.id),
        "status": "DRAFT",
        "steps": created,
        "provenance_label": MODEL_PROVENANCE,
        "reversible": True,
        "note": "A draft Plan does nothing until the owner activates it.",
    }


async def create_memory_candidate(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    candidate_text: str,
    orbit_id: str | None = None,
    memory_type: str = "SEMANTIC",
) -> dict[str, Any]:
    """Propose a memory. Never approve one.

    `status` is PENDING and `approved_memory_id` stays null. There is no tool
    that promotes a candidate, so model output cannot become owner truth by any
    path the runtime can reach on its own.
    """
    from app.models.cognition import MemoryCandidate

    candidate = MemoryCandidate(
        owner_user_id=owner_user_id,
        candidate_text=candidate_text.strip(),
        memory_type=memory_type,
        provenance_label=MODEL_PROVENANCE,
        created_by="AGENT",
        status="PENDING",
    )
    if orbit_id:
        candidate.orbit_id = uuid.UUID(orbit_id)
    db.add(candidate)
    await db.flush()
    return {
        "created": True,
        "candidate_id": str(candidate.id),
        "status": "PENDING",
        "provenance_label": MODEL_PROVENANCE,
        "reversible": True,
        "note": "A candidate is a proposal. Only the owner can make it memory.",
    }


async def create_research_brief(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    question: str,
    notes: str = "",
    orbit_id: str | None = None,
) -> dict[str, Any]:
    from app.models.cognition import ResearchDraft

    draft = ResearchDraft(
        owner_user_id=owner_user_id,
        question=question.strip(),
        notes=notes.strip(),
        status="DRAFT",
    )
    if orbit_id:
        draft.orbit_id = uuid.UUID(orbit_id)
    db.add(draft)
    await db.flush()
    return {
        "created": True,
        "brief_id": str(draft.id),
        "status": "DRAFT",
        "provenance_label": MODEL_PROVENANCE,
        "reversible": True,
    }


async def create_insight_candidate(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    title: str,
    claim: str,
    what_nur_may_be_wrong_about: str,
    evidence: list | None = None,
    counter_evidence: list | None = None,
    confidence: float = 0.5,
    affected_system_slug: str | None = None,
) -> dict[str, Any]:
    """Propose an Insight. Doubt is a required argument, not an option.

    `what_nur_may_be_wrong_about` is NOT NULL in the schema, and it is a required
    keyword here for the same reason: an Insight that cannot say where it might
    be wrong should not be creatable at all. A default value would let a caller
    skip the hardest sentence in the product.
    """
    from app.models.intelligence import Insight

    doubt = (what_nur_may_be_wrong_about or "").strip()
    if not doubt:
        raise ValueError(
            "an Insight must state where NUR may be wrong; an empty doubt is not acceptable"
        )

    insight = Insight(
        owner_user_id=owner_user_id,
        insight_type="PATTERN",
        title=title.strip(),
        claim=claim.strip(),
        confidence=max(0.0, min(float(confidence), 1.0)),
        evidence=list(evidence or []),
        counter_evidence=list(counter_evidence or []),
        what_nur_may_be_wrong_about=doubt,
        affected_system_slug=affected_system_slug,
        status="CANDIDATE",
        provenance_label=MODEL_PROVENANCE,
    )
    db.add(insight)
    await db.flush()
    return {
        "created": True,
        "insight_id": str(insight.id),
        "status": "CANDIDATE",
        "confidence_meaning": "Source coverage and evidence strength, not guaranteed truth",
        "provenance_label": MODEL_PROVENANCE,
        "reversible": True,
        "note": "A candidate Insight is challengeable until the owner accepts or corrects it.",
    }


async def create_timeline_draft(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    title: str,
    description: str = "",
    system_slug: str | None = None,
    importance: int = 50,
) -> dict[str, Any]:
    """Draft a Timeline event with no schedule.

    `scheduled_for` is deliberately left null: scheduling is the durable,
    approval-gated action. A draft that quietly carried a date would be a
    reminder the owner never agreed to.
    """
    from app.models.intelligence import TimelineEvent

    event = TimelineEvent(
        owner_user_id=owner_user_id,
        event_type="AGENT_DRAFT",
        title=title.strip(),
        description=description.strip(),
        time_kind="FUTURE",
        source_type="AGENT",
        status="PLANNED",
        importance=max(0, min(int(importance), 100)),
        system_slug=system_slug,
    )
    db.add(event)
    await db.flush()
    return {
        "created": True,
        "event_id": str(event.id),
        "status": "PLANNED",
        "scheduled_for": None,
        "provenance_label": MODEL_PROVENANCE,
        "reversible": True,
        "note": "Unscheduled. Scheduling requires owner approval.",
    }


def bind_draft_handlers() -> tuple[str, ...]:
    """Attach the R1 handlers. Separate from the read-only binding so a caller —
    or a test — can enable reads without enabling any write at all."""
    registry.bind("create_draft_plan", create_draft_plan)
    registry.bind("create_memory_candidate", create_memory_candidate)
    registry.bind("create_research_brief", create_research_brief)
    registry.bind("create_insight_candidate", create_insight_candidate)
    registry.bind("create_timeline_draft", create_timeline_draft)
    return registry.bound_keys()


# ── R2: durable owner mutations ──────────────────────────────────────────────
#
# These change what is true for the owner, so each one refuses to execute
# without proof that this exact call was approved.
#
# The policy engine already requires approval for R2, and the orchestrator
# already checks it. Re-checking inside the handler is deliberate duplication:
# a guard that lives only in the caller is one refactor away from being skipped,
# and the thing it protects is a mutation of someone's record. Defence in depth
# is cheap here and the failure it prevents is not recoverable by an apology.


class ApprovalMissing(PermissionError):
    """Raised when a durable tool is called without a matching approval."""


def _require_approval(tool_key: str, tool_version: str, arguments: dict, proof) -> None:
    """Verify the caller holds an approval bound to exactly this call.

    `proof` is the StoredApproval the owner decided on. The digest is recomputed
    from the arguments about to execute, so an approval obtained for one payload
    cannot be replayed against another.
    """
    from app.agentic.approvals import evaluate_resume
    import datetime as _dt

    if proof is None:
        raise ApprovalMissing(
            f"{tool_key} changes owner records and cannot run without an owner approval"
        )
    verdict = evaluate_resume(
        proof,
        tool_key=tool_key,
        tool_version=tool_version,
        arguments=arguments,
        now=_dt.datetime.now(_dt.timezone.utc),
    )
    if not verdict.allowed:
        raise ApprovalMissing(f"{tool_key} refused: {verdict.refusal} — {verdict.message}")


async def activate_plan(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    plan_id: str,
    approval=None,
) -> dict[str, Any]:
    """Move a drafted Plan to ACTIVE. Requires an approval for this exact plan."""
    from app.models.cognition import Plan

    _require_approval("activate_plan", "1", {"plan_id": plan_id}, approval)

    plan = (
        await db.execute(
            _owned(select(Plan), Plan, owner_user_id).where(Plan.id == uuid.UUID(plan_id))
        )
    ).scalar_one_or_none()
    if plan is None:
        return {"found": False, "plan_id": plan_id}
    # Only a draft may be activated. Re-activating an active Plan would be a
    # silent no-op that reports success, which is how a duplicate delivery looks
    # like it worked.
    if plan.status != "DRAFT":
        return {"changed": False, "plan_id": plan_id, "status": plan.status,
                "reason": "only a DRAFT plan can be activated"}
    plan.status = "ACTIVE"
    await db.flush()
    return {"changed": True, "plan_id": plan_id, "status": "ACTIVE", "reversible": True}


async def schedule_timeline_event(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    event_id: str,
    scheduled_for: str,
    approval=None,
) -> dict[str, Any]:
    """Attach a real date to a drafted Timeline event."""
    import datetime as _dt

    from app.models.intelligence import TimelineEvent

    _require_approval(
        "schedule_timeline_event", "1",
        {"event_id": event_id, "scheduled_for": scheduled_for}, approval,
    )

    event = (
        await db.execute(
            _owned(select(TimelineEvent), TimelineEvent, owner_user_id)
            .where(TimelineEvent.id == uuid.UUID(event_id))
        )
    ).scalar_one_or_none()
    if event is None:
        return {"found": False, "event_id": event_id}

    event.scheduled_for = _dt.datetime.fromisoformat(scheduled_for)
    event.time_kind = "FUTURE"
    await db.flush()
    return {
        "changed": True,
        "event_id": event_id,
        "scheduled_for": event.scheduled_for.isoformat(),
        "reversible": True,
    }


async def accept_or_correct_insight(
    db: AsyncSession,
    owner_user_id: uuid.UUID,
    *,
    insight_id: str,
    decision: str,
    correction: str | None = None,
    approval=None,
) -> dict[str, Any]:
    """Record the owner's verdict on a candidate Insight.

    A correction is stored rather than overwriting the claim. The original stays
    on the record because an Insight NUR got wrong, and the owner's correction of
    it, are both evidence — replacing the claim would erase what NUR believed and
    make its mistakes unauditable.
    """
    from app.models.intelligence import Insight

    _require_approval(
        "accept_or_correct_insight", "1",
        {"insight_id": insight_id, "decision": decision, "correction": correction}, approval,
    )

    verdict = decision.upper()
    if verdict not in {"ACCEPTED", "REJECTED", "CORRECTED"}:
        raise ValueError("decision must be ACCEPTED, REJECTED or CORRECTED")

    insight = (
        await db.execute(
            _owned(select(Insight), Insight, owner_user_id)
            .where(Insight.id == uuid.UUID(insight_id))
        )
    ).scalar_one_or_none()
    if insight is None:
        return {"found": False, "insight_id": insight_id}

    insight.status = verdict
    if verdict == "CORRECTED":
        if not (correction or "").strip():
            raise ValueError("a correction must say what is actually true")
        insight.correction = correction.strip()
    await db.flush()
    return {
        "changed": True,
        "insight_id": insight_id,
        "status": verdict,
        "original_claim_preserved": True,
        "note": "Owner correction outranks model inference and is kept as the record.",
    }


def bind_durable_handlers() -> tuple[str, ...]:
    """Attach the R2 handlers.

    Kept separate from reads and drafts so a deployment can run this spine with
    mutations disabled entirely. `create_capsule` and `queue_project_run` are
    deliberately not bound: a Capsule crosses the owner's private boundary and a
    project run spends budget, and neither has an end-to-end owner-reviewed flow
    yet. Declaring them while leaving them unbound is the honest state — they
    raise rather than half-working.
    """
    registry.bind("activate_plan", activate_plan)
    registry.bind("schedule_timeline_event", schedule_timeline_event)
    registry.bind("accept_or_correct_insight", accept_or_correct_insight)
    return registry.bound_keys()


def bind_all_handlers() -> tuple[str, ...]:
    """Bind every implemented handler. The Agency Plane's composition root.

    Nothing outside the test suite used to call the three `bind_*` functions, so
    in production the registry was empty: a real Celery worker that received
    `nur.agentic.execute_step` raised `UnboundToolError` for every tool, and
    `GET /agentic/tools` reported all 24 as `bound: false`. Every in-process test
    bound handlers itself in a fixture, so the whole tool layer could be inert in
    production while the suite stayed green — it took a real worker consuming a
    real broker message to surface it.

    Both long-lived processes call this at startup: the API (so the catalog it
    serves is truthful) and the worker (so a step can actually execute).

    `create_capsule`, `queue_project_run` and `complete_task` stay unbound on
    purpose — a Capsule crosses the owner's privacy boundary and a project run
    spends budget, and neither has an owner-reviewed flow yet. Declared and
    unbound is the honest state: they raise rather than half-working.
    """
    bind_read_only_handlers()
    bind_draft_handlers()
    bind_durable_handlers()
    return registry.bound_keys()
