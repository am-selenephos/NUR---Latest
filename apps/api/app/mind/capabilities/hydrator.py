"""NUR Mind Progressive Context Hydrator.

Hydrates scoped, deterministic context tailored to the active CapabilitySpec's
ContextHydrationRecipe while strictly respecting owner ScopeEnvelope boundaries.
"""
from __future__ import annotations

import enum
import uuid
from typing import Any
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import EvidenceRef
from app.brain.schemas import ContextManifest, ScopeEnvelope
from app.cognition.hybrid_retrieval import retrieve_hybrid
from app.mind.capabilities.schemas import CapabilitySpec, HydrationFailurePolicy
from app.mind.working_memory import build_context_manifest
from app.models.cognition import CognitiveEvent, Plan
from app.models import OmegaWorkspaceFrame
from app.omega.workspace_service import build_workspace_frame


class SourceStatus(enum.StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    SKIPPED = "SKIPPED"


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
    source_statuses: dict[str, str] = Field(default_factory=dict)
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
        source_statuses: dict[str, str] = {}

        def handle_source_failure(source_key: str, exc: Exception) -> None:
            is_required = source_key in recipe.required_source_keys
            if is_required or recipe.failure_policy == HydrationFailurePolicy.FAIL_ALL:
                raise RuntimeError(
                    f"Context hydration failed for required source '{source_key}': {exc}"
                ) from exc
            source_statuses[source_key] = SourceStatus.DEGRADED.value

        # 1. Workspace Frame
        frame: OmegaWorkspaceFrame | None = None
        should_fetch_frame = (
            "workspace_frame" in recipe.source_keys or recipe.include_workspace_frame
        )
        if should_fetch_frame:
            try:
                frame = await build_workspace_frame(
                    db,
                    owner_user_id=owner_user_id,
                    task_mode=scope_envelope.surface,
                    active_question=query,
                    orbit_id=orbit_id,
                    trigger_event_id=trigger_event_id,
                )
                source_statuses["workspace_frame"] = SourceStatus.INCLUDED.value
            except Exception as exc:
                frame = None
                handle_source_failure("workspace_frame", exc)
        else:
            source_statuses["workspace_frame"] = SourceStatus.SKIPPED.value

        # 2. Hybrid Retrieval
        retrieval_refs: list[EvidenceRef] = []
        retrieval_dicts: list[dict[str, Any]] = []
        should_fetch_retrieval = (
            "hybrid_retrieval" in recipe.source_keys or recipe.hybrid_retrieval_limit > 0
        )
        limit = recipe.hybrid_retrieval_limit if recipe.hybrid_retrieval_limit > 0 else 6
        if should_fetch_retrieval and recipe.hybrid_retrieval_limit > 0:
            try:
                retrieval_refs = await retrieve_hybrid(
                    db,
                    owner_user_id=owner_user_id,
                    query=query,
                    orbit_id=orbit_id,
                    limit=limit,
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
                source_statuses["hybrid_retrieval"] = SourceStatus.INCLUDED.value
            except Exception as exc:
                retrieval_refs = []
                retrieval_dicts = []
                handle_source_failure("hybrid_retrieval", exc)
        else:
            source_statuses["hybrid_retrieval"] = SourceStatus.SKIPPED.value

        # 3. Active Plans (Read-only direct domain query; no agentic handler imports)
        active_plans: list[dict[str, Any]] = []
        should_fetch_plans = "active_plans" in recipe.source_keys or recipe.fetch_active_plans
        if should_fetch_plans and recipe.fetch_active_plans:
            try:
                stmt = (
                    select(Plan)
                    .where(Plan.owner_user_id == owner_user_id, Plan.status == "ACTIVE")
                    .order_by(Plan.created_at.desc())
                    .limit(10)
                )
                res = await db.execute(stmt)
                plan_rows = res.scalars().all()
                active_plans = [
                    {"id": str(p.id), "title": p.title, "status": p.status}
                    for p in plan_rows
                ]
                source_statuses["active_plans"] = SourceStatus.INCLUDED.value
            except Exception as exc:
                active_plans = []
                handle_source_failure("active_plans", exc)
        else:
            source_statuses["active_plans"] = SourceStatus.SKIPPED.value

        # 4. Timeline window (Read-only direct domain query)
        timeline_events: list[dict[str, Any]] = []
        should_fetch_timeline = "timeline" in recipe.source_keys or recipe.fetch_timeline_window_days > 0
        if should_fetch_timeline and recipe.fetch_timeline_window_days > 0:
            try:
                stmt = (
                    select(CognitiveEvent)
                    .where(CognitiveEvent.owner_user_id == owner_user_id)
                    .order_by(CognitiveEvent.created_at.desc())
                    .limit(50)
                )
                res = await db.execute(stmt)
                event_rows = res.scalars().all()
                timeline_events = [
                    {"id": str(e.id), "kind": str(e.event_kind), "content": e.content_text}
                    for e in event_rows
                ]
                source_statuses["timeline"] = SourceStatus.INCLUDED.value
            except Exception as exc:
                timeline_events = []
                handle_source_failure("timeline", exc)
        else:
            source_statuses["timeline"] = SourceStatus.SKIPPED.value

        # 5. Today state
        today_state: dict[str, Any] | None = None
        should_fetch_today = "today_state" in recipe.source_keys
        if should_fetch_today:
            try:
                stmt = (
                    select(CognitiveEvent)
                    .where(CognitiveEvent.owner_user_id == owner_user_id)
                    .order_by(CognitiveEvent.created_at.desc())
                    .limit(1)
                )
                res = await db.execute(stmt)
                last_ev = res.scalars().first()
                today_state = {
                    "active": True,
                    "last_event": last_ev.content_text if last_ev else None,
                }
                source_statuses["today_state"] = SourceStatus.INCLUDED.value
            except Exception as exc:
                today_state = None
                handle_source_failure("today_state", exc)
        else:
            source_statuses["today_state"] = SourceStatus.SKIPPED.value

        # 6. Build Manifest & Token Budget enforcement
        budget = min(recipe.max_total_tokens, recipe.max_context_tokens) if recipe.max_context_tokens > 0 else recipe.max_total_tokens
        manifest, filtered_evidence = build_context_manifest(
            retrieved_refs=retrieval_dicts,
            scope_statement=f"Owner {scope_envelope.sharing_boundary} scope",
            token_budget=budget,
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
            source_statuses=source_statuses,
            estimated_tokens=manifest.token_used,
        )

