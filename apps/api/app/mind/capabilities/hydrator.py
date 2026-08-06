"""NUR Mind Progressive Context Hydrator.

Hydrates scoped, deterministic context tailored to the active CapabilitySpec's
ContextHydrationRecipe while strictly respecting owner ScopeEnvelope boundaries.
"""
from __future__ import annotations

import datetime as dt
import enum
import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import EvidenceRef
from app.brain.schemas import ContextManifest, ScopeEnvelope
from app.cognition.hybrid_retrieval import retrieve_hybrid
from app.domain_reads.plans import read_plans
from app.domain_reads.timeline import read_timeline
from app.domain_reads.today import read_today_state
from app.mind.capabilities.schemas import (
    CapabilitySpec,
    ContextHydrationRecipe,
    HydrationFailurePolicy,
    HydrationIssue,
    HydrationReport,
    HydrationSourceResult,
    HydrationStatus,
)
from app.mind.working_memory import build_context_manifest
from app.models import OmegaWorkspaceFrame
from app.omega.workspace_service import build_workspace_frame


def _estimate_tokens(data: Any) -> int:
    if data is None:
        return 0
    if isinstance(data, str):
        return max(1, len(data) // 4)
    if isinstance(data, (dict, list, tuple)):
        text_repr = json.dumps(data, default=str)
        return max(1, len(text_repr) // 4)
    return max(1, len(str(data)) // 4)


class SourceStatus(enum.StrEnum):
    INCLUDED = "INCLUDED"
    EXCLUDED = "EXCLUDED"
    FAILED = "FAILED"
    DEGRADED = "DEGRADED"
    SKIPPED = "SKIPPED"
    TRUNCATED = "TRUNCATED"


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
    orbit_context: dict[str, Any] | None = None
    source_statuses: dict[str, str] = Field(default_factory=dict)
    hydration_report: HydrationReport | None = None
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

        # Orbit agreement check
        if orbit_id is not None and scope_envelope.orbit_id is not None:
            if str(orbit_id) != str(scope_envelope.orbit_id):
                raise ValueError(
                    f"Orbit ID mismatch: request orbit_id ({orbit_id}) does not agree with ScopeEnvelope.orbit_id ({scope_envelope.orbit_id})."
                )

        effective_orbit_id = orbit_id or scope_envelope.orbit_id
        recipe = capability.hydration_recipe

        source_results: dict[str, HydrationSourceResult] = {}
        issues: list[HydrationIssue] = []
        source_statuses: dict[str, str] = {}
        max_items_map = recipe.items_per_source_map

        def record_failure(source_key: str, exc: Exception) -> None:
            is_required = (
                source_key in recipe.required_source_keys
                or (source_key in recipe.source_keys and not recipe.optional_source_keys)
            )
            fatal = is_required or recipe.failure_policy == HydrationFailurePolicy.FAIL_ANY
            issue = HydrationIssue(
                issue_type="SOURCE_FAILURE",
                source_key=source_key,
                message=str(exc),
                fatal=fatal,
            )
            issues.append(issue)
            if fatal:
                source_statuses[source_key] = SourceStatus.FAILED.value
                source_results[source_key] = HydrationSourceResult(
                    source_key=source_key,
                    status=SourceStatus.FAILED.value,
                    count=0,
                    estimated_tokens=0,
                    error_message=str(exc),
                )
                raise RuntimeError(
                    f"Context hydration failed for required source '{source_key}': {exc}"
                ) from exc
            source_statuses[source_key] = SourceStatus.DEGRADED.value
            source_results[source_key] = HydrationSourceResult(
                source_key=source_key,
                status=SourceStatus.DEGRADED.value,
                count=0,
                estimated_tokens=0,
                error_message=str(exc),
            )

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
                    orbit_id=effective_orbit_id,
                    trigger_event_id=trigger_event_id,
                )
                tok = _estimate_tokens(frame.summary_digest if frame else None)
                source_statuses["workspace_frame"] = SourceStatus.INCLUDED.value
                source_results["workspace_frame"] = HydrationSourceResult(
                    source_key="workspace_frame",
                    status=SourceStatus.INCLUDED.value,
                    count=1 if frame else 0,
                    estimated_tokens=tok,
                )
            except Exception as exc:
                frame = None
                record_failure("workspace_frame", exc)
        else:
            source_statuses["workspace_frame"] = SourceStatus.SKIPPED.value
            source_results["workspace_frame"] = HydrationSourceResult(
                source_key="workspace_frame",
                status=SourceStatus.SKIPPED.value,
                count=0,
                estimated_tokens=0,
            )

        # 2. Hybrid Retrieval
        retrieval_refs: list[EvidenceRef] = []
        retrieval_dicts: list[dict[str, Any]] = []
        should_fetch_retrieval = (
            "hybrid_retrieval" in recipe.source_keys or recipe.hybrid_retrieval_limit > 0
        )
        limit = max_items_map.get("hybrid_retrieval", recipe.hybrid_retrieval_limit or 6)
        if should_fetch_retrieval and limit > 0:
            try:
                raw_refs = await retrieve_hybrid(
                    db,
                    owner_user_id=owner_user_id,
                    query=query,
                    orbit_id=effective_orbit_id,
                    limit=limit,
                )
                # Filter by required_record_classes, excluded_record_classes, required_entity_types, allowed_entity_ids
                seen_refs: set[str] = set()
                deduped_refs: list[EvidenceRef] = []
                for r in raw_refs:
                    ref_key = f"{r.kind}:{r.id}"
                    if ref_key in seen_refs:
                        continue
                    if recipe.required_record_classes and r.kind not in recipe.required_record_classes:
                        continue
                    if recipe.excluded_record_classes and r.kind in recipe.excluded_record_classes:
                        continue
                    if recipe.allowed_entity_ids and str(r.id) not in recipe.allowed_entity_ids:
                        continue
                    seen_refs.add(ref_key)
                    deduped_refs.append(r)

                retrieval_refs = deduped_refs
                retrieval_dicts = [r.model_dump() for r in retrieval_refs]
                tok = sum(_estimate_tokens(r.excerpt) for r in retrieval_refs)
                source_statuses["hybrid_retrieval"] = SourceStatus.INCLUDED.value
                source_results["hybrid_retrieval"] = HydrationSourceResult(
                    source_key="hybrid_retrieval",
                    status=SourceStatus.INCLUDED.value,
                    count=len(retrieval_refs),
                    estimated_tokens=tok,
                )
            except Exception as exc:
                retrieval_refs = []
                retrieval_dicts = []
                record_failure("hybrid_retrieval", exc)
        else:
            source_statuses["hybrid_retrieval"] = SourceStatus.SKIPPED.value
            source_results["hybrid_retrieval"] = HydrationSourceResult(
                source_key="hybrid_retrieval",
                status=SourceStatus.SKIPPED.value,
                count=0,
                estimated_tokens=0,
            )

        # 3. Active Plans
        active_plans: list[dict[str, Any]] = []
        should_fetch_plans = "active_plans" in recipe.source_keys or recipe.fetch_active_plans
        plans_limit = max_items_map.get("active_plans", 10)
        if should_fetch_plans and (recipe.fetch_active_plans or "active_plans" in recipe.source_keys):
            try:
                plans_res = await read_plans(
                    db,
                    owner_user_id=owner_user_id,
                    status="ACTIVE",
                    orbit_id=effective_orbit_id,
                    limit=plans_limit,
                )
                active_plans = plans_res.get("plans", [])
                tok = _estimate_tokens(active_plans)
                source_statuses["active_plans"] = SourceStatus.INCLUDED.value
                source_results["active_plans"] = HydrationSourceResult(
                    source_key="active_plans",
                    status=SourceStatus.INCLUDED.value,
                    count=len(active_plans),
                    estimated_tokens=tok,
                )
            except Exception as exc:
                active_plans = []
                record_failure("active_plans", exc)
        else:
            source_statuses["active_plans"] = SourceStatus.SKIPPED.value
            source_results["active_plans"] = HydrationSourceResult(
                source_key="active_plans",
                status=SourceStatus.SKIPPED.value,
                count=0,
                estimated_tokens=0,
            )

        # 4. Timeline window (canonical domain read service)
        timeline_events: list[dict[str, Any]] = []
        should_fetch_timeline = "timeline" in recipe.source_keys or recipe.fetch_timeline_window_days > 0
        timeline_limit = max_items_map.get("timeline", 50)
        if should_fetch_timeline and (recipe.fetch_timeline_window_days > 0 or "timeline" in recipe.source_keys):
            try:
                timeline_res = await read_timeline(
                    db,
                    owner_user_id=owner_user_id,
                    limit=timeline_limit,
                    window_days=recipe.fetch_timeline_window_days if recipe.fetch_timeline_window_days > 0 else None,
                    orbit_id=effective_orbit_id,
                )
                timeline_events = timeline_res.get("events", [])
                tok = _estimate_tokens(timeline_events)
                source_statuses["timeline"] = SourceStatus.INCLUDED.value
                source_results["timeline"] = HydrationSourceResult(
                    source_key="timeline",
                    status=SourceStatus.INCLUDED.value,
                    count=len(timeline_events),
                    estimated_tokens=tok,
                )
            except Exception as exc:
                timeline_events = []
                record_failure("timeline", exc)
        else:
            source_statuses["timeline"] = SourceStatus.SKIPPED.value
            source_results["timeline"] = HydrationSourceResult(
                source_key="timeline",
                status=SourceStatus.SKIPPED.value,
                count=0,
                estimated_tokens=0,
            )

        # 5. Today state (canonical domain read service)
        today_state: dict[str, Any] | None = None
        should_fetch_today = "today_state" in recipe.source_keys
        if should_fetch_today:
            try:
                today_state = await read_today_state(db, owner_user_id=owner_user_id)
                tok = _estimate_tokens(today_state)
                source_statuses["today_state"] = SourceStatus.INCLUDED.value
                source_results["today_state"] = HydrationSourceResult(
                    source_key="today_state",
                    status=SourceStatus.INCLUDED.value,
                    count=1 if today_state else 0,
                    estimated_tokens=tok,
                )
            except Exception as exc:
                today_state = None
                record_failure("today_state", exc)
        else:
            source_statuses["today_state"] = SourceStatus.SKIPPED.value
            source_results["today_state"] = HydrationSourceResult(
                source_key="today_state",
                status=SourceStatus.SKIPPED.value,
                count=0,
                estimated_tokens=0,
            )

        # 6. Orbit context
        orbit_context: dict[str, Any] | None = None
        should_fetch_orbit = "orbit_context" in recipe.source_keys or recipe.fetch_orbit_context
        if should_fetch_orbit and effective_orbit_id:
            try:
                from app.models.orbit import Orbit
                from sqlalchemy import select
                stmt = select(Orbit).where(Orbit.owner_user_id == owner_user_id, Orbit.id == effective_orbit_id)
                orb = (await db.execute(stmt)).scalars().first()
                if orb:
                    orbit_context = {
                        "id": str(orb.id),
                        "title": orb.title,
                        "kind": str(orb.kind),
                        "system_slug": orb.system_slug,
                        "privacy_scope": str(orb.privacy_scope),
                    }
                tok = _estimate_tokens(orbit_context)
                source_statuses["orbit_context"] = SourceStatus.INCLUDED.value
                source_results["orbit_context"] = HydrationSourceResult(
                    source_key="orbit_context",
                    status=SourceStatus.INCLUDED.value,
                    count=1 if orbit_context else 0,
                    estimated_tokens=tok,
                )
            except Exception as exc:
                orbit_context = None
                record_failure("orbit_context", exc)
        elif should_fetch_orbit:
            source_statuses["orbit_context"] = SourceStatus.SKIPPED.value
            source_results["orbit_context"] = HydrationSourceResult(
                source_key="orbit_context",
                status=SourceStatus.SKIPPED.value,
                count=0,
                estimated_tokens=0,
            )

        # 7. Global Token Accounting & Manifest Assembly
        total_token_budget = min(recipe.max_total_tokens, recipe.max_context_tokens) if recipe.max_context_tokens > 0 else recipe.max_total_tokens
        
        # Calculate non-evidence token overhead
        non_evidence_tokens = sum(
            res.estimated_tokens
            for key, res in source_results.items()
            if key != "hybrid_retrieval" and res.status == SourceStatus.INCLUDED.value
        )
        remaining_evidence_budget = max(200, total_token_budget - non_evidence_tokens)

        manifest, filtered_evidence = build_context_manifest(
            retrieved_refs=retrieval_dicts,
            scope_statement=f"Owner {scope_envelope.sharing_boundary} scope",
            token_budget=remaining_evidence_budget,
        )

        total_tokens_used = non_evidence_tokens + manifest.token_used
        
        # Check if truncated
        truncated_sources: list[str] = []
        if len(filtered_evidence) < len(retrieval_dicts):
            truncated_sources.append("hybrid_retrieval")

        included_sources = [k for k, v in source_statuses.items() if v == SourceStatus.INCLUDED.value]
        excluded_sources = [k for k, v in source_statuses.items() if v == SourceStatus.SKIPPED.value]
        degraded_sources = [k for k, v in source_statuses.items() if v == SourceStatus.DEGRADED.value]

        overall_status = HydrationStatus.SUCCESS
        if degraded_sources:
            overall_status = HydrationStatus.DEGRADED

        report = HydrationReport(
            status=overall_status,
            total_tokens_used=total_tokens_used,
            per_source=tuple(source_results.values()),
            issues=tuple(issues),
            included_sources=tuple(included_sources),
            excluded_sources=tuple(excluded_sources),
            degraded_sources=tuple(degraded_sources),
            truncated_sources=tuple(truncated_sources),
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
            orbit_context=orbit_context,
            source_statuses=source_statuses,
            hydration_report=report,
            estimated_tokens=total_tokens_used,
        )
