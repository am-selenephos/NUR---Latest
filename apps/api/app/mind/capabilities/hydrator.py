"""NUR Mind Progressive Context Hydrator.

Hydrates scoped, deterministic context tailored to the active CapabilitySpec's
ContextHydrationRecipe while strictly respecting owner ScopeEnvelope boundaries.
"""
from __future__ import annotations

import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import EvidenceRef
from app.brain.schemas import ContextManifest, ScopeEnvelope
from app.cognition.hybrid_retrieval import retrieve_hybrid
from app.mind.capabilities.schemas import CapabilitySpec
from app.mind.working_memory import build_context_manifest
from app.models import OmegaWorkspaceFrame
from app.omega.workspace_service import build_workspace_frame


class HydratedCapabilityContext(BaseModel):
    """Container for progressively hydrated context bound to a capability run."""
    capability_id: str
    scope_envelope: ScopeEnvelope
    manifest: ContextManifest
    retrieval_refs: list[EvidenceRef] = Field(default_factory=list)
    retrieved_evidence: list[dict[str, Any]] = Field(default_factory=list)
    workspace_frame: Any | None = None
    active_plans: list[dict[str, Any]] = Field(default_factory=list)
    timeline_events: list[dict[str, Any]] = Field(default_factory=list)
    today_state: dict[str, Any] | None = None
    estimated_tokens: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)


class ContextHydrator:
    """Progressive context hydration engine tailored by CapabilitySpec recipes."""

    @staticmethod
    async def hydrate(
        db: AsyncSession,
        *,
        owner_user_id: uuid.UUID,
        scope_envelope: ScopeEnvelope,
        capability: CapabilitySpec,
        query: str,
        orbit_id: uuid.UUID | None = None,
        trigger_event_id: uuid.UUID | None = None,
    ) -> HydratedCapabilityContext:
        """Execute the capability's recipe to collect only necessary context sections."""
        if scope_envelope is None:
            raise ValueError("Missing ScopeEnvelope: progressive hydration requires an explicit ScopeEnvelope.")
        if scope_envelope.owner_user_id != owner_user_id:
            raise PermissionError("Cross-owner scope violation: ScopeEnvelope owner does not match caller.")

        recipe = capability.hydration_recipe

        # 1. Workspace Frame
        frame: OmegaWorkspaceFrame | None = None
        if recipe.include_workspace_frame:
            frame = await build_workspace_frame(
                db,
                owner_user_id=owner_user_id,
                task_mode=scope_envelope.surface,
                active_question=query,
                orbit_id=orbit_id,
                trigger_event_id=trigger_event_id,
            )

        # 2. Hybrid Retrieval
        retrieval_refs: list[EvidenceRef] = []
        retrieval_dicts: list[dict[str, Any]] = []
        if recipe.hybrid_retrieval_limit > 0:
            retrieval_refs = await retrieve_hybrid(
                db,
                owner_user_id=owner_user_id,
                query=query,
                orbit_id=orbit_id,
                limit=recipe.hybrid_retrieval_limit,
            )
            # Deduplicate references by kind + id
            seen_refs: set[str] = set()
            deduped_refs: list[EvidenceRef] = []
            for r in retrieval_refs:
                ref_key = f"{r.kind}:{r.id}"
                if ref_key not in seen_refs:
                    seen_refs.add(ref_key)
                    deduped_refs.append(r)
            retrieval_refs = deduped_refs
            retrieval_dicts = [r.model_dump() for r in retrieval_refs]

        # 3. Active Plans
        active_plans: list[dict[str, Any]] = []
        if recipe.fetch_active_plans:
            try:
                from app.agentic.handlers import get_plan
                plan_res = await get_plan(db, owner_user_id=owner_user_id)
                if isinstance(plan_res, dict) and plan_res.get("found"):
                    active_plans = plan_res.get("plans", [])
            except Exception:
                active_plans = []

        # 4. Timeline window
        timeline_events: list[dict[str, Any]] = []
        if recipe.fetch_timeline_window_days > 0:
            try:
                from app.agentic.handlers import get_timeline
                t_res = await get_timeline(db, owner_user_id=owner_user_id, limit=50)
                if isinstance(t_res, dict):
                    timeline_events = t_res.get("events", [])
            except Exception:
                timeline_events = []

        # 5. Today state if required by tool
        today_state: dict[str, Any] | None = None
        if "get_today_state" in capability.required_tools:
            try:
                from app.agentic.handlers import get_today_state
                today_state = await get_today_state(db, owner_user_id=owner_user_id)
            except Exception:
                today_state = None

        # 6. Build Manifest & Token Budget enforcement
        manifest, filtered_evidence = build_context_manifest(
            retrieved_refs=retrieval_dicts,
            scope_statement=f"Owner {scope_envelope.sharing_boundary} scope",
            token_budget=recipe.max_context_tokens,
        )

        return HydratedCapabilityContext(
            capability_id=capability.capability_id,
            scope_envelope=scope_envelope,
            manifest=manifest,
            retrieval_refs=retrieval_refs,
            retrieved_evidence=filtered_evidence,
            workspace_frame=frame,
            active_plans=active_plans,
            timeline_events=timeline_events,
            today_state=today_state,
            estimated_tokens=manifest.token_used,
        )
