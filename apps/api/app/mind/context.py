"""NUR Mind Context — compiles CognitiveTaskPacket from Mind state.

Takes request parameters, retrieved evidence, workspace frame, identity, self-model,
and a resolved ``ScopeEnvelope``, and returns a frozen ``CognitiveTaskPacket`` ready
for the Brain provider boundary.

Directive §8.1: the ScopeEnvelope must be resolved before context construction.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import (
    BeliefSnapshot,
    CognitiveBudget,
    CognitiveTaskPacketV2,
    ContextLineage,
    ContextSource,
    GoalSnapshot,
    IntentionSnapshot,
    OwnerIdentitySnapshot,
    ProjectModelSnapshot,
    ScopeEnvelope,
    UserModelSnapshot,
    WorldModelSnapshot,
)
from app.mind.identity import load_identity
from app.mind.self_model import get_self_capabilities
from app.mind.working_memory import build_context_manifest

if TYPE_CHECKING:
    from app.mind.capabilities.hydrator import HydratedCapabilityContext


def _estimate_tokens(value: Any) -> int:
    return max(1, len(str(value)) // 4) if value else 0


def _owner_partition(
    items: list[dict[str, Any]], owner_user_id: uuid.UUID
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    owner = str(owner_user_id)
    included: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for item in items:
        if str(item.get("owner_user_id")) == owner:
            included.append(item)
        else:
            rejected.append(item)
    return included, rejected


def _workspace_snapshot(frame: Any | None) -> dict[str, Any]:
    if frame is None:
        return {}
    return {
        key: value
        for key in (
            "id",
            "active_goal",
            "active_question",
            "attention_items",
            "risk_flags",
            "scope_statement",
        )
        if (value := getattr(frame, key, None)) is not None
    }


async def load_semantic_hydration_inputs(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None = None,
    limit: int = 20,
) -> dict[str, list[dict[str, Any]]]:
    """Load only owner-scoped semantic families before Brain context assembly.

    Approved memories are the only memory family admitted. Candidates remain a
    review-plane output and are deliberately returned separately so the hydrator
    can record their exclusion rather than silently widening context.
    """
    from app.models.cognition import (
        ClaimEvidence,
        Hypothesis,
        ResearchDraft,
        SemanticClaim,
        UserCorrection,
    )
    from app.models.living import Goal
    from app.models.memory import PersonalMemory
    from app.models.orbit import Orbit
    from app.models.product import ResearchSourceNote
    from app.models.projects import AMProject

    bounded = max(1, min(int(limit), 100))
    memory_stmt = select(PersonalMemory).where(
        PersonalMemory.owner_user_id == owner_user_id,
        PersonalMemory.status == "APPROVED",
        PersonalMemory.deleted_at.is_(None),
    ).order_by(PersonalMemory.updated_at.desc()).limit(bounded)
    if orbit_id is not None:
        memory_stmt = memory_stmt.where(
            (PersonalMemory.orbit_id == orbit_id) | (PersonalMemory.orbit_id.is_(None))
        )
    memory_rows = (await db.execute(memory_stmt)).scalars().all()

    claims = (
        await db.execute(
            select(SemanticClaim)
            .where(SemanticClaim.owner_user_id == owner_user_id, SemanticClaim.status != "ARCHIVED")
            .order_by(SemanticClaim.created_at.desc())
            .limit(bounded)
        )
    ).scalars().all()
    claim_ids = [row.id for row in claims]
    evidence_rows = []
    if claim_ids:
        evidence_rows = (
            await db.execute(
                select(ClaimEvidence)
                .where(
                    ClaimEvidence.owner_user_id == owner_user_id,
                    ClaimEvidence.claim_id.in_(claim_ids),
                )
                .order_by(ClaimEvidence.created_at.desc())
                .limit(bounded * 4)
            )
        ).scalars().all()
    hypotheses_stmt = (
        select(Hypothesis)
        .where(Hypothesis.owner_user_id == owner_user_id, Hypothesis.status != "ARCHIVED")
        .order_by(Hypothesis.created_at.desc())
        .limit(bounded)
    )
    if orbit_id is not None:
        hypotheses_stmt = hypotheses_stmt.where(
            (Hypothesis.orbit_id == orbit_id) | (Hypothesis.orbit_id.is_(None))
        )
    hypotheses = (await db.execute(hypotheses_stmt)).scalars().all()
    goals_stmt = (
        select(Goal)
        .where(Goal.owner_user_id == owner_user_id, Goal.status == "ACTIVE")
        .order_by(Goal.updated_at.desc())
        .limit(bounded)
    )
    if orbit_id is not None:
        goals_stmt = goals_stmt.where((Goal.orbit_id == orbit_id) | (Goal.orbit_id.is_(None)))
    goals = (await db.execute(goals_stmt)).scalars().all()
    corrections = (
        await db.execute(
            select(UserCorrection)
            .where(UserCorrection.owner_user_id == owner_user_id)
            .order_by(UserCorrection.created_at.desc())
            .limit(bounded)
        )
    ).scalars().all()
    orbit_rows = []
    if orbit_id is not None:
        orbit_rows = (
            await db.execute(
                select(Orbit).where(
                    Orbit.owner_user_id == owner_user_id,
                    Orbit.id == orbit_id,
                )
            )
        ).scalars().all()
    project_stmt = (
        select(AMProject)
        .where(AMProject.owner_user_id == owner_user_id, AMProject.status == "ACTIVE")
        .order_by(AMProject.updated_at.desc())
        .limit(bounded)
    )
    if orbit_id is not None:
        project_stmt = project_stmt.where(AMProject.orbit_id == orbit_id)
    projects = (await db.execute(project_stmt)).scalars().all()
    drafts = (
        await db.execute(
            select(ResearchDraft)
            .where(ResearchDraft.owner_user_id == owner_user_id)
            .order_by(ResearchDraft.created_at.desc())
            .limit(bounded)
        )
    ).scalars().all()
    notes = (
        await db.execute(
            select(ResearchSourceNote)
            .where(ResearchSourceNote.owner_user_id == owner_user_id)
            .order_by(ResearchSourceNote.created_at.desc())
            .limit(bounded)
        )
    ).scalars().all()

    approved_memory = [
        {
            "id": str(row.id),
            "owner_user_id": str(row.owner_user_id),
            "status": row.status,
            "content": row.canonical_text,
            "provenance_label": row.provenance_label,
            "confidence": row.confidence,
        }
        for row in memory_rows
    ]
    evidence_by_claim: dict[uuid.UUID, list[dict[str, Any]]] = {}
    for evidence in evidence_rows:
        evidence_by_claim.setdefault(evidence.claim_id, []).append(
            {
                "id": str(evidence.id),
                "supports": evidence.supports,
                "weight": evidence.weight,
                "rationale": evidence.rationale,
                "event_id": str(evidence.event_id) if evidence.event_id else None,
                "outcome_id": str(evidence.outcome_id) if evidence.outcome_id else None,
            }
        )
    belief_rows = []
    for row in claims:
        claim_evidence = evidence_by_claim.get(row.id, [])
        belief_rows.append(
            {
                "id": str(row.id),
                "owner_user_id": str(row.owner_user_id),
                "claim": row.claim_text,
                "status": row.status,
                "confidence": row.confidence,
                "evidence_count": row.evidence_count,
                "counterevidence_count": row.counterevidence_count,
                "supporting_evidence": [item for item in claim_evidence if item["supports"]],
                "counterevidence": [item for item in claim_evidence if not item["supports"]],
            }
        )
    research_rows = [
        {
            "id": str(row.id),
            "owner_user_id": str(row.owner_user_id),
            "question": row.question,
            "notes": row.notes or "",
            "status": row.status,
        }
        for row in drafts
    ] + [
        {
            "id": str(row.id),
            "owner_user_id": str(row.owner_user_id),
            "title": row.title,
            "note": row.note,
            "citation": row.url,
        }
        for row in notes
    ]
    return {
        "approved_memory": approved_memory,
        "memory_candidates": [],
        "beliefs": belief_rows,
        "user_model_claims": belief_rows,
        "user_corrections": [
            {
                "id": str(row.id),
                "owner_user_id": str(row.owner_user_id),
                "correction": row.correction_text,
                "reason": row.reason,
            }
            for row in corrections
        ],
        "goals": [
            {
                "id": str(row.id),
                "owner_user_id": str(row.owner_user_id),
                "orbit_id": str(row.orbit_id) if row.orbit_id else None,
                "title": row.title,
                "why": row.why,
                "status": row.status,
            }
            for row in goals
        ],
        "hypotheses": [
            {
                "id": str(row.id),
                "owner_user_id": str(row.owner_user_id),
                "hypothesis": row.hypothesis_text,
                "status": row.status,
                "confidence": row.confidence,
            }
            for row in hypotheses
        ],
        "world_model": [
            {
                "id": str(row.id),
                "owner_user_id": str(row.owner_user_id),
                "title": row.title,
                "kind": str(row.kind),
                "description": row.description,
                "active_focus_area": row.active_focus_area,
                "system_slug": row.system_slug,
            }
            for row in orbit_rows
        ],
        "project_models": [
            {
                "id": str(row.id),
                "owner_user_id": str(row.owner_user_id),
                "orbit_id": str(row.orbit_id),
                "title": row.title,
                "objective": row.objective,
                "status": row.status,
                "deadline": row.deadline.isoformat() if row.deadline else None,
                "budget_cents": row.budget_cents,
            }
            for row in projects
        ],
        "research_results": research_rows,
        "semantic_context": [
            {"id": item["id"], "owner_user_id": str(owner_user_id), "kind": "semantic_claim"}
            for item in belief_rows
        ],
    }


async def build_cognitive_task_packet(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    user_input: str,
    task_class: str = "talk",
    orbit_id: uuid.UUID | None = None,
    locale: str = "en",
    writing_preference: str = "default",
    retrieved_refs: list[dict[str, Any]] | None = None,
    workspace_frame: Any | None = None,
    withheld_items: list[dict[str, Any]] | None = None,
    token_budget: int = 4096,
    scope_envelope: ScopeEnvelope | None = None,
    semantic_inputs: dict[str, list[dict[str, Any]]] | None = None,
    hydrated_context: HydratedCapabilityContext | None = None,
    max_output_tokens: int = 2_000,
    max_model_calls: int = 1,
    max_cost_cents: int = 0,
    deadline_seconds: float = 30.0,
) -> CognitiveTaskPacketV2:
    """Build a complete, frozen ``CognitiveTaskPacket`` for a Brain run.

    When a ``scope_envelope`` is provided, its ``scope_id`` is recorded in the
    packet for lineage tracing and its scope statement is used in the context manifest.
    """
    identity = load_identity()
    self_capabilities = await get_self_capabilities(db, owner_user_id)

    scope_statement = "Private orbit scope"
    omega_context: dict[str, Any] = {}
    semantic = semantic_inputs or {}
    if hydrated_context is not None:
        if hydrated_context.scope_envelope.owner_user_id != owner_user_id:
            raise PermissionError("Cross-owner hydrated context cannot enter a CognitiveTaskPacket.")
        semantic = {
            **semantic,
            "approved_memory": hydrated_context.approved_memory,
            "beliefs": hydrated_context.beliefs,
            "user_model_claims": hydrated_context.user_model_claims,
            "research_results": hydrated_context.research_results,
            "semantic_context": hydrated_context.semantic_context,
        }
    active_beliefs: list[str] = [
        str(item.get("claim") or item.get("claim_text"))
        for item in semantic.get("beliefs", [])
        if item.get("claim") or item.get("claim_text")
    ]
    active_hypotheses: list[str] = []
    risk_flags: list[str] = []

    # Use scope envelope's data when available
    if scope_envelope is not None:
        scope_statement = scope_envelope.reason or scope_statement

    if workspace_frame is not None:
        scope_statement = getattr(workspace_frame, "scope_statement", scope_statement)
        omega_context = {
            "workspace_frame_id": str(getattr(workspace_frame, "id", "")),
            "semantic_families": {
                key: len(value) for key, value in semantic.items()
            },
            "scope_statement": scope_statement,
            "attention_items": getattr(workspace_frame, "attention_items", {}),
            "risk_flags": getattr(workspace_frame, "risk_flags", []),
        }
        attention = getattr(workspace_frame, "attention_items", {})
        active_beliefs = attention.get("claim_summaries", [])
        risk_flags = getattr(workspace_frame, "risk_flags", [])

    if hydrated_context is not None:
        manifest = hydrated_context.manifest.model_copy(deep=True)
        filtered_evidence = list(hydrated_context.retrieved_evidence)
    else:
        manifest, filtered_evidence = build_context_manifest(
            retrieved_refs=retrieved_refs or [],
            withheld_items=withheld_items,
            scope_statement=scope_statement,
            token_budget=token_budget,
        )

    owner_semantic: dict[str, list[dict[str, Any]]] = {}
    rejected: list[tuple[str, dict[str, Any]]] = []
    for family in (
        "approved_memory",
        "beliefs",
        "user_model_claims",
        "user_corrections",
        "goals",
        "hypotheses",
        "world_model",
        "project_models",
        "research_results",
    ):
        owned, cross_owner = _owner_partition(list(semantic.get(family, [])), owner_user_id)
        owner_semantic[family] = owned
        rejected.extend((family, item) for item in cross_owner)

    excluded = list(manifest.excluded)
    excluded.extend(
        ContextSource(
            kind=family,
            id=str(item.get("id", "unknown")),
            reason="owner mismatch rejected during packet assembly",
            status="EXCLUDED",
            degraded=True,
        )
        for family, item in rejected
    )
    degraded = list(manifest.degraded)
    if hydrated_context is not None:
        for source_key, status in hydrated_context.source_statuses.items():
            if status not in {"DEGRADED", "TRUNCATED", "FAILED"}:
                continue
            source = ContextSource(
                kind=source_key,
                id=source_key,
                reason=f"hydration source status: {status}",
                status=status,
                degraded=True,
                truncated=status == "TRUNCATED",
            )
            degraded.append(source)
            if source not in excluded:
                excluded.append(source)

    # Any semantic families not already admitted by the capability hydrator
    # consume the same hard context budget. There is no unmetered V2 side door.
    prebudgeted = {
        "approved_memory",
        "beliefs",
        "user_model_claims",
        "research_results",
    } if hydrated_context is not None else set()
    included = list(manifest.included)
    token_used = manifest.token_used
    for family, items in list(owner_semantic.items()):
        if family in prebudgeted:
            continue
        fitted: list[dict[str, Any]] = []
        for item in items:
            cost = _estimate_tokens(item)
            source = ContextSource(
                kind=family,
                id=str(item.get("id", "unknown")),
                reason="owner-scoped V2 context source",
                owner_user_id=owner_user_id,
                token_estimate=cost,
                provenance=str(item.get("provenance_label") or family),
            )
            if token_used + cost <= manifest.token_budget:
                fitted.append(item)
                token_used += cost
                included.append(source)
                continue
            omitted = source.model_copy(
                update={
                    "reason": "hard context token budget exhausted",
                    "status": "TRUNCATED",
                    "truncated": True,
                    "degraded": True,
                }
            )
            excluded.append(omitted)
            degraded.append(omitted)
        owner_semantic[family] = fitted
    manifest = manifest.model_copy(
        update={
            "included": included,
            "excluded": excluded,
            "degraded": degraded,
            "token_used": token_used,
        }
    )

    beliefs = [
        BeliefSnapshot(
            id=str(item.get("id", "unknown")),
            claim=str(item.get("claim") or item.get("claim_text") or ""),
            status=str(item.get("status", "EMERGING")),
            confidence=float(item.get("confidence", 0.5)),
            supporting_evidence=list(item.get("supporting_evidence", [])),
            counterevidence=list(item.get("counterevidence", [])),
        )
        for item in owner_semantic["beliefs"]
        if item.get("claim") or item.get("claim_text")
    ]
    goals = [
        GoalSnapshot(
            id=str(item.get("id", "unknown")),
            title=str(item.get("title", "")),
            status=str(item.get("status", "ACTIVE")),
            why=item.get("why"),
            orbit_id=item.get("orbit_id"),
            project_id=item.get("project_id"),
        )
        for item in owner_semantic["goals"]
        if item.get("title")
    ]
    inferred_intentions = [goal.title for goal in goals]
    if hydrated_context is not None:
        inferred_intentions.extend(
            str(item.get("title"))
            for item in hydrated_context.active_plans
            if item.get("title")
        )
    world_orbit = (
        dict(hydrated_context.orbit_context or {})
        if hydrated_context is not None
        else dict(owner_semantic["world_model"][0]) if owner_semantic["world_model"] else {}
    )
    world_model = WorldModelSnapshot(
        orbit=world_orbit,
        today=dict(hydrated_context.today_state or {}) if hydrated_context is not None else {},
        workspace=_workspace_snapshot(workspace_frame),
    )
    active_hypotheses = [
        str(item.get("hypothesis"))
        for item in owner_semantic["hypotheses"]
        if item.get("hypothesis")
    ]
    active_beliefs = [belief.claim for belief in beliefs]
    source_ids = [source.id for source in manifest.included]
    excluded_source_ids = [source.id for source in manifest.excluded]

    return CognitiveTaskPacketV2(
        task_id=uuid.uuid4(),
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        scope_envelope_id=scope_envelope.scope_id if scope_envelope else None,
        task_class=task_class,
        user_input=user_input,
        locale=locale,
        writing_preference=writing_preference,
        identity=identity,
        self_capabilities=self_capabilities,
        context_manifest=manifest,
        evidence_refs=filtered_evidence,
        omega_context={
            **omega_context,
            "semantic_families": {key: len(value) for key, value in semantic.items()},
        },
        active_beliefs=active_beliefs,
        active_hypotheses=active_hypotheses,
        risk_flags=risk_flags,
        max_turns=1,
        owner_identity=OwnerIdentitySnapshot(
            owner_user_id=owner_user_id,
            orbit_id=orbit_id,
            scope_envelope_id=scope_envelope.scope_id if scope_envelope else None,
        ),
        user_model=UserModelSnapshot(
            claims=owner_semantic["user_model_claims"],
            corrections=owner_semantic["user_corrections"],
        ),
        world_model=world_model,
        project_model=ProjectModelSnapshot(projects=owner_semantic["project_models"]),
        beliefs=beliefs,
        goals=goals,
        intention=IntentionSnapshot(
            explicit_owner_intent=user_input,
            inferred_intentions=inferred_intentions,
            effective_intent=user_input,
            precedence="explicit_owner_intent",
        ),
        approved_memory=owner_semantic["approved_memory"],
        research_context=owner_semantic["research_results"],
        budget=CognitiveBudget(
            max_context_tokens=manifest.token_budget,
            max_output_tokens=max_output_tokens,
            max_model_calls=max_model_calls,
            max_cost_cents=max_cost_cents,
            deadline_seconds=deadline_seconds,
        ),
        context_lineage=ContextLineage(
            scope_envelope_id=scope_envelope.scope_id if scope_envelope else None,
            capability_id=hydrated_context.capability_id if hydrated_context is not None else None,
            source_ids=source_ids,
            excluded_source_ids=excluded_source_ids,
            degradation_reasons=[source.reason for source in manifest.degraded],
        ),
    )
