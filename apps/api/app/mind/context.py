"""NUR Mind Context — compiles CognitiveTaskPacket from Mind state.

Takes request parameters, retrieved evidence, workspace frame, identity, and self-model,
and returns a frozen ``CognitiveTaskPacket`` ready for the Brain provider boundary.
"""
from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import CognitiveTaskPacket
from app.mind.identity import load_identity
from app.mind.self_model import get_self_capabilities
from app.mind.working_memory import build_context_manifest


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
) -> CognitiveTaskPacket:
    """Build a complete, frozen ``CognitiveTaskPacket`` for a Brain run."""
    identity = load_identity()
    self_capabilities = await get_self_capabilities(db, owner_user_id)

    scope_statement = "Private orbit scope"
    omega_context: dict[str, Any] = {}
    active_beliefs: list[str] = []
    active_hypotheses: list[str] = []
    risk_flags: list[str] = []

    if workspace_frame is not None:
        scope_statement = getattr(workspace_frame, "scope_statement", scope_statement)
        omega_context = {
            "workspace_frame_id": str(getattr(workspace_frame, "id", "")),
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
        task_class=task_class,
        user_input=user_input,
        locale=locale,
        writing_preference=writing_preference,
        identity=identity,
        self_capabilities=self_capabilities,
        context_manifest=manifest,
        evidence_refs=filtered_evidence,
        omega_context=omega_context,
        active_beliefs=active_beliefs,
        active_hypotheses=active_hypotheses,
        risk_flags=risk_flags,
        max_turns=1,
    )
