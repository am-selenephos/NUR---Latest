"""NUR Mind Context — compiles CognitiveTaskPacket from Mind state.

Takes request parameters, retrieved evidence, workspace frame, identity, self-model,
and a resolved ``ScopeEnvelope``, and returns a frozen ``CognitiveTaskPacket`` ready
for the Brain provider boundary.

Directive §8.1: the ScopeEnvelope must be resolved before context construction.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import CognitiveTaskPacket, ScopeEnvelope
from app.mind.identity import load_identity
from app.mind.self_model import get_self_capabilities
from app.mind.working_memory import build_context_manifest


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
    from app.models.cognition import ResearchDraft, SemanticClaim
    from app.models.memory import PersonalMemory
    from app.models.product import ResearchSourceNote

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
    belief_rows = [
        {
            "id": str(row.id),
            "owner_user_id": str(row.owner_user_id),
            "claim": row.claim_text,
            "status": row.status,
            "confidence": row.confidence,
            "evidence_count": row.evidence_count,
            "counterevidence_count": row.counterevidence_count,
        }
        for row in claims
    ]
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
) -> CognitiveTaskPacket:
    """Build a complete, frozen ``CognitiveTaskPacket`` for a Brain run.

    When a ``scope_envelope`` is provided, its ``scope_id`` is recorded in the
    packet for lineage tracing and its scope statement is used in the context manifest.
    """
    identity = load_identity()
    self_capabilities = await get_self_capabilities(db, owner_user_id)

    scope_statement = "Private orbit scope"
    omega_context: dict[str, Any] = {}
    semantic = semantic_inputs or {}
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

    manifest, filtered_evidence = build_context_manifest(
        retrieved_refs=retrieved_refs or [],
        withheld_items=withheld_items,
        scope_statement=scope_statement,
        token_budget=token_budget,
    )

    return CognitiveTaskPacket(
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
    )
