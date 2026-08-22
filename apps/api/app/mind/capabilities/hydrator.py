"""NUR Mind Progressive Context Hydrator.

Hydrates scoped, deterministic context tailored to the active CapabilitySpec's
ContextHydrationRecipe while strictly respecting owner ScopeEnvelope boundaries.
"""
from __future__ import annotations

import enum
import json
import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.schemas import EvidenceRef
from app.brain.schemas import ContextManifest, ContextSource, ScopeEnvelope
from app.cognition.hybrid_retrieval import retrieve_hybrid
from app.domain_reads.plans import read_plans
from app.domain_reads.timeline import read_timeline
from app.domain_reads.today import read_today_state
from app.mind.capabilities.schemas import (
    CapabilitySpec,
    HydrationFailurePolicy,
    HydrationIssue,
    HydrationReport,
    HydrationSourceResult,
    HydrationStatus,
)
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


class SemanticHydrationResult(BaseModel):
    """Owner-scoped semantic families included in a Brain context packet."""
    approved_memory: list[dict[str, Any]] = Field(default_factory=list)
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    beliefs: list[dict[str, Any]] = Field(default_factory=list)
    user_model_claims: list[dict[str, Any]] = Field(default_factory=list)
    research_results: list[dict[str, Any]] = Field(default_factory=list)
    semantic_context: list[dict[str, Any]] = Field(default_factory=list)
    manifest: ContextManifest
    estimated_tokens: int = 0


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
    approved_memory: list[dict[str, Any]] = Field(default_factory=list)
    memory_candidates: list[dict[str, Any]] = Field(default_factory=list)
    beliefs: list[dict[str, Any]] = Field(default_factory=list)
    user_model_claims: list[dict[str, Any]] = Field(default_factory=list)
    research_results: list[dict[str, Any]] = Field(default_factory=list)
    semantic_context: list[dict[str, Any]] = Field(default_factory=list)
    source_statuses: dict[str, str] = Field(default_factory=dict)
    hydration_report: HydrationReport | None = None
    estimated_tokens: int = 0

    model_config = ConfigDict(arbitrary_types_allowed=True)


ORDERED_SOURCE_KEYS: tuple[str, ...] = (
    "workspace_frame",
    "today_state",
    "active_plans",
    "orbit_context",
    "timeline",
    "hybrid_retrieval",
)


class ContextHydrator:
    """Progressive context hydration engine tailored by CapabilitySpec recipes."""

    @staticmethod
    def hydrate_semantic_sources(
        scope_envelope: ScopeEnvelope,
        *,
        approved_memory: list[dict[str, Any]],
        memory_candidates: list[dict[str, Any]],
        beliefs: list[dict[str, Any]],
        user_model_claims: list[dict[str, Any]],
        research_results: list[dict[str, Any]],
        semantic_context: list[dict[str, Any]],
        token_budget: int,
    ) -> SemanticHydrationResult:
        owner = str(scope_envelope.owner_user_id)

        rejected_owner_items: list[tuple[str, dict[str, Any]]] = []

        def owned(key: str, items: list[dict[str, Any]]) -> list[dict[str, Any]]:
            accepted: list[dict[str, Any]] = []
            for item in items:
                if str(item.get("owner_user_id")) == owner:
                    accepted.append(item)
                else:
                    rejected_owner_items.append((key, item))
            return accepted

        approved = [
            item for item in owned("approved_memory", approved_memory)
            if str(item.get("status", "APPROVED")).upper() in {"APPROVED", "OWNER_APPROVED"}
        ]
        # Candidates are always excluded from Brain context even when owner-scoped.
        excluded_candidate = owned("memory_candidates", memory_candidates)
        families = {
            "approved_memory": approved,
            "beliefs": owned("beliefs", beliefs),
            "user_model": owned("user_model", user_model_claims),
            "research": owned("research", research_results),
            "semantic_context": owned("semantic_context", semantic_context),
        }
        included: list[ContextSource] = []
        excluded: list[ContextSource] = []
        degraded: list[ContextSource] = []
        used = 0
        output: dict[str, list[dict[str, Any]]] = {key: [] for key in families}
        for key, items in families.items():
            for item in items:
                cost = _estimate_tokens(item)
                if used + cost > max(0, token_budget):
                    source = ContextSource(
                        kind=key,
                        id=str(item.get("id", "unknown")),
                        reason="hard context token budget exhausted",
                        status="TRUNCATED",
                        owner_user_id=scope_envelope.owner_user_id,
                        token_estimate=cost,
                        truncated=True,
                        degraded=True,
                        provenance=str(item.get("provenance_label") or "owner-scoped semantic source"),
                    )
                    excluded.append(source)
                    degraded.append(source)
                    continue
                output[key].append(item)
                used += cost
                included.append(
                    ContextSource(
                        kind=key,
                        id=str(item.get("id", "unknown")),
                        reason="owner-scoped semantic source",
                        owner_user_id=scope_envelope.owner_user_id,
                        token_estimate=cost,
                        provenance=str(item.get("provenance_label") or "owner-scoped semantic source"),
                    )
                )
        for item in excluded_candidate:
            excluded.append(
                ContextSource(
                    kind="memory_candidates",
                    id=str(item.get("id", "unknown")),
                    reason="unapproved candidate excluded",
                    status="EXCLUDED",
                    owner_user_id=scope_envelope.owner_user_id,
                )
            )
        for key, item in rejected_owner_items:
            excluded.append(
                ContextSource(
                    kind=key,
                    id=str(item.get("id", "unknown")),
                    reason="owner mismatch excluded",
                    status="EXCLUDED",
                    degraded=True,
                )
            )
        for key, items in families.items():
            if not items:
                excluded.append(
                    ContextSource(
                        kind=key,
                        id="none",
                        reason="no source supplied",
                        status="EXCLUDED",
                    )
                )
        return SemanticHydrationResult(
            approved_memory=output["approved_memory"],
            memory_candidates=[],
            beliefs=output["beliefs"],
            user_model_claims=output["user_model"],
            research_results=output["research"],
            semantic_context=output["semantic_context"],
            manifest=ContextManifest(
                scope_statement=scope_envelope.reason or "owner-scoped semantic context",
                included=included,
                excluded=excluded,
                degraded=degraded,
                token_budget=max(0, token_budget),
                token_used=used,
            ),
            estimated_tokens=used,
        )

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
        semantic_inputs: dict[str, list[dict[str, Any]]] | None = None,
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

        # Semantic and runtime sources share one hard budget; semantic hydration
        # must initialize first so it cannot bypass max_context_tokens.
        effective_total_budget = (
            min(recipe.max_total_tokens, recipe.max_context_tokens)
            if recipe.max_context_tokens > 0
            else recipe.max_total_tokens
        )
        effective_total_budget = max(0, effective_total_budget)
        remaining_budget = effective_total_budget

        semantic = ContextHydrator.hydrate_semantic_sources(
            scope_envelope,
            approved_memory=(semantic_inputs or {}).get("approved_memory", []),
            memory_candidates=(semantic_inputs or {}).get("memory_candidates", []),
            beliefs=(semantic_inputs or {}).get("beliefs", []),
            user_model_claims=(semantic_inputs or {}).get("user_model_claims", []),
            research_results=(semantic_inputs or {}).get("research_results", []),
            semantic_context=(semantic_inputs or {}).get("semantic_context", []),
            token_budget=remaining_budget,
        )
        remaining_budget = max(0, remaining_budget - semantic.estimated_tokens)
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

        # Determine required vs optional sources respecting deterministic priority
        required_sources = [s for s in ORDERED_SOURCE_KEYS if s in recipe.required_source_keys]
        optional_sources = [
            s for s in ORDERED_SOURCE_KEYS
            if s not in recipe.required_source_keys and (
                s in recipe.optional_source_keys
                or s in recipe.source_keys
                or (s == "workspace_frame" and recipe.include_workspace_frame)
                or (s == "active_plans" and recipe.fetch_active_plans)
                or (s == "timeline" and recipe.fetch_timeline_window_days > 0)
                or (s == "orbit_context" and recipe.fetch_orbit_context)
                or (s == "hybrid_retrieval" and recipe.hybrid_retrieval_limit > 0)
            )
        ]
        execution_order = required_sources + optional_sources

        # Mark all unrequested sources as SKIPPED
        for s in ORDERED_SOURCE_KEYS:
            if s not in execution_order:
                source_statuses[s] = SourceStatus.SKIPPED.value
                source_results[s] = HydrationSourceResult(
                    source_key=s,
                    status=SourceStatus.SKIPPED.value,
                    count=0,
                    estimated_tokens=0,
                )

        frame: OmegaWorkspaceFrame | None = None
        today_state: dict[str, Any] | None = None
        active_plans: list[dict[str, Any]] = []
        orbit_context: dict[str, Any] | None = None
        timeline_events: list[dict[str, Any]] = []
        retrieval_refs: list[EvidenceRef] = []
        retrieval_dicts: list[dict[str, Any]] = []

        for source_key in execution_order:
            is_required = source_key in recipe.required_source_keys

            # 1. Workspace Frame
            if source_key == "workspace_frame":
                try:
                    raw_frame = await build_workspace_frame(
                        db,
                        owner_user_id=owner_user_id,
                        task_mode=scope_envelope.surface,
                        active_question=query,
                        orbit_id=effective_orbit_id,
                        trigger_event_id=trigger_event_id,
                    )
                    tok = _estimate_tokens(raw_frame.summary_digest if raw_frame else None)
                    if tok <= remaining_budget:
                        frame = raw_frame
                        remaining_budget -= tok
                        source_statuses["workspace_frame"] = SourceStatus.INCLUDED.value
                        source_results["workspace_frame"] = HydrationSourceResult(
                            source_key="workspace_frame",
                            status=SourceStatus.INCLUDED.value,
                            count=1 if frame else 0,
                            estimated_tokens=tok,
                        )
                    else:
                        if is_required:
                            raise RuntimeError(
                                f"Context hydration failed: required source 'workspace_frame' exceeds token budget ({tok} > {remaining_budget})"
                            )
                        frame = None
                        source_statuses["workspace_frame"] = SourceStatus.SKIPPED.value
                        source_results["workspace_frame"] = HydrationSourceResult(
                            source_key="workspace_frame",
                            status=SourceStatus.SKIPPED.value,
                            count=0,
                            estimated_tokens=0,
                        )
                except Exception as exc:
                    frame = None
                    record_failure("workspace_frame", exc)

            # 2. Today state
            elif source_key == "today_state":
                try:
                    raw_today = await read_today_state(db, owner_user_id=owner_user_id)
                    tok = _estimate_tokens(raw_today)
                    if tok <= remaining_budget:
                        today_state = raw_today
                        remaining_budget -= tok
                        source_statuses["today_state"] = SourceStatus.INCLUDED.value
                        source_results["today_state"] = HydrationSourceResult(
                            source_key="today_state",
                            status=SourceStatus.INCLUDED.value,
                            count=1 if today_state else 0,
                            estimated_tokens=tok,
                        )
                    else:
                        if is_required:
                            raise RuntimeError(
                                f"Context hydration failed: required source 'today_state' exceeds token budget ({tok} > {remaining_budget})"
                            )
                        today_state = None
                        source_statuses["today_state"] = SourceStatus.SKIPPED.value
                        source_results["today_state"] = HydrationSourceResult(
                            source_key="today_state",
                            status=SourceStatus.SKIPPED.value,
                            count=0,
                            estimated_tokens=0,
                        )
                except Exception as exc:
                    today_state = None
                    record_failure("today_state", exc)

            # 3. Active Plans
            elif source_key == "active_plans":
                plans_limit = max_items_map.get("active_plans", 10)
                try:
                    plans_res = await read_plans(
                        db,
                        owner_user_id=owner_user_id,
                        status="ACTIVE",
                        orbit_id=effective_orbit_id,
                        limit=plans_limit,
                    )
                    raw_plans = plans_res.get("plans", [])
                    fitted_plans: list[dict[str, Any]] = []
                    used_tok = 0
                    for p in raw_plans:
                        p_tok = _estimate_tokens([p])
                        if used_tok + p_tok <= remaining_budget:
                            fitted_plans.append(p)
                            used_tok += p_tok
                        else:
                            break

                    if len(fitted_plans) == len(raw_plans):
                        active_plans = fitted_plans
                        remaining_budget -= used_tok
                        source_statuses["active_plans"] = SourceStatus.INCLUDED.value
                        source_results["active_plans"] = HydrationSourceResult(
                            source_key="active_plans",
                            status=SourceStatus.INCLUDED.value,
                            count=len(active_plans),
                            estimated_tokens=used_tok,
                        )
                    elif len(fitted_plans) > 0:
                        active_plans = fitted_plans
                        remaining_budget -= used_tok
                        source_statuses["active_plans"] = SourceStatus.TRUNCATED.value
                        source_results["active_plans"] = HydrationSourceResult(
                            source_key="active_plans",
                            status=SourceStatus.TRUNCATED.value,
                            count=len(active_plans),
                            estimated_tokens=used_tok,
                        )
                    else:
                        if is_required and raw_plans:
                            raise RuntimeError(
                                f"Context hydration failed: required source 'active_plans' cannot fit in token budget ({remaining_budget} tokens remaining)"
                            )
                        active_plans = []
                        status = SourceStatus.INCLUDED.value if not raw_plans else SourceStatus.SKIPPED.value
                        source_statuses["active_plans"] = status
                        source_results["active_plans"] = HydrationSourceResult(
                            source_key="active_plans",
                            status=status,
                            count=0,
                            estimated_tokens=0,
                        )
                except Exception as exc:
                    active_plans = []
                    record_failure("active_plans", exc)

            # 4. Orbit context
            elif source_key == "orbit_context":
                if effective_orbit_id:
                    try:
                        from app.models.orbit import Orbit
                        from sqlalchemy import select
                        stmt = select(Orbit).where(Orbit.owner_user_id == owner_user_id, Orbit.id == effective_orbit_id)
                        orb = (await db.execute(stmt)).scalars().first()
                        raw_orb = None
                        if orb:
                            raw_orb = {
                                "id": str(orb.id),
                                "title": orb.title,
                                "kind": str(orb.kind),
                                "system_slug": orb.system_slug,
                                "privacy_scope": str(orb.privacy_scope),
                            }
                        tok = _estimate_tokens(raw_orb)
                        if tok <= remaining_budget:
                            orbit_context = raw_orb
                            remaining_budget -= tok
                            source_statuses["orbit_context"] = SourceStatus.INCLUDED.value
                            source_results["orbit_context"] = HydrationSourceResult(
                                source_key="orbit_context",
                                status=SourceStatus.INCLUDED.value,
                                count=1 if orbit_context else 0,
                                estimated_tokens=tok,
                            )
                        else:
                            if is_required:
                                raise RuntimeError(
                                    f"Context hydration failed: required source 'orbit_context' exceeds token budget ({tok} > {remaining_budget})"
                                )
                            orbit_context = None
                            source_statuses["orbit_context"] = SourceStatus.SKIPPED.value
                            source_results["orbit_context"] = HydrationSourceResult(
                                source_key="orbit_context",
                                status=SourceStatus.SKIPPED.value,
                                count=0,
                                estimated_tokens=0,
                            )
                    except Exception as exc:
                        orbit_context = None
                        record_failure("orbit_context", exc)
                else:
                    source_statuses["orbit_context"] = SourceStatus.SKIPPED.value
                    source_results["orbit_context"] = HydrationSourceResult(
                        source_key="orbit_context",
                        status=SourceStatus.SKIPPED.value,
                        count=0,
                        estimated_tokens=0,
                    )

            # 5. Timeline window
            elif source_key == "timeline":
                timeline_limit = max_items_map.get("timeline", 50)
                try:
                    timeline_res = await read_timeline(
                        db,
                        owner_user_id=owner_user_id,
                        limit=timeline_limit,
                        window_days=recipe.fetch_timeline_window_days if recipe.fetch_timeline_window_days > 0 else None,
                        orbit_id=effective_orbit_id,
                    )
                    raw_events = timeline_res.get("events", [])
                    fitted_events: list[dict[str, Any]] = []
                    used_tok = 0
                    for evt in raw_events:
                        e_tok = _estimate_tokens([evt])
                        if used_tok + e_tok <= remaining_budget:
                            fitted_events.append(evt)
                            used_tok += e_tok
                        else:
                            break

                    if len(fitted_events) == len(raw_events):
                        timeline_events = fitted_events
                        remaining_budget -= used_tok
                        source_statuses["timeline"] = SourceStatus.INCLUDED.value
                        source_results["timeline"] = HydrationSourceResult(
                            source_key="timeline",
                            status=SourceStatus.INCLUDED.value,
                            count=len(timeline_events),
                            estimated_tokens=used_tok,
                        )
                    elif len(fitted_events) > 0:
                        timeline_events = fitted_events
                        remaining_budget -= used_tok
                        source_statuses["timeline"] = SourceStatus.TRUNCATED.value
                        source_results["timeline"] = HydrationSourceResult(
                            source_key="timeline",
                            status=SourceStatus.TRUNCATED.value,
                            count=len(timeline_events),
                            estimated_tokens=used_tok,
                        )
                    else:
                        if is_required and raw_events:
                            raise RuntimeError(
                                f"Context hydration failed: required source 'timeline' cannot fit in token budget ({remaining_budget} tokens remaining)"
                            )
                        timeline_events = []
                        status = SourceStatus.INCLUDED.value if not raw_events else SourceStatus.SKIPPED.value
                        source_statuses["timeline"] = status
                        source_results["timeline"] = HydrationSourceResult(
                            source_key="timeline",
                            status=status,
                            count=0,
                            estimated_tokens=0,
                        )
                except Exception as exc:
                    timeline_events = []
                    record_failure("timeline", exc)

            # 6. Hybrid Retrieval
            elif source_key == "hybrid_retrieval":
                retrieval_limit = max_items_map.get("hybrid_retrieval", recipe.hybrid_retrieval_limit or 6)
                if retrieval_limit > 0:
                    try:
                        raw_refs = await retrieve_hybrid(
                            db,
                            owner_user_id=owner_user_id,
                            query=query,
                            orbit_id=effective_orbit_id,
                            limit=retrieval_limit,
                        )
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

                        fitted_refs: list[EvidenceRef] = []
                        fitted_dicts: list[dict[str, Any]] = []
                        used_tok = 0
                        for r in deduped_refs:
                            r_tok = _estimate_tokens(r.excerpt)
                            if used_tok + r_tok <= remaining_budget:
                                fitted_refs.append(r)
                                fitted_dicts.append(r.model_dump())
                                used_tok += r_tok
                            else:
                                break

                        if len(fitted_refs) == len(deduped_refs):
                            retrieval_refs = fitted_refs
                            retrieval_dicts = fitted_dicts
                            remaining_budget -= used_tok
                            source_statuses["hybrid_retrieval"] = SourceStatus.INCLUDED.value
                            source_results["hybrid_retrieval"] = HydrationSourceResult(
                                source_key="hybrid_retrieval",
                                status=SourceStatus.INCLUDED.value,
                                count=len(retrieval_refs),
                                estimated_tokens=used_tok,
                            )
                        elif len(fitted_refs) > 0:
                            retrieval_refs = fitted_refs
                            retrieval_dicts = fitted_dicts
                            remaining_budget -= used_tok
                            source_statuses["hybrid_retrieval"] = SourceStatus.TRUNCATED.value
                            source_results["hybrid_retrieval"] = HydrationSourceResult(
                                source_key="hybrid_retrieval",
                                status=SourceStatus.TRUNCATED.value,
                                count=len(retrieval_refs),
                                estimated_tokens=used_tok,
                            )
                        else:
                            if is_required and deduped_refs:
                                raise RuntimeError(
                                    f"Context hydration failed: required source 'hybrid_retrieval' cannot fit in token budget ({remaining_budget} tokens remaining)"
                                )
                            retrieval_refs = []
                            retrieval_dicts = []
                            status = SourceStatus.INCLUDED.value if not deduped_refs else SourceStatus.SKIPPED.value
                            source_statuses["hybrid_retrieval"] = status
                            source_results["hybrid_retrieval"] = HydrationSourceResult(
                                source_key="hybrid_retrieval",
                                status=status,
                                count=0,
                                estimated_tokens=0,
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

        # Build context manifest reflecting exact runtime source outcomes.
        inc_sources = [
            ContextSource(
                kind=str(r.get("kind", "unknown")),
                id=str(r.get("id", "")),
                reason=f"Relevant to query (salience rank {r.get('rank', 0):.2f})",
                owner_user_id=owner_user_id,
                token_estimate=_estimate_tokens(r.get("excerpt")),
                provenance="hybrid_retrieval",
            )
            for r in retrieval_dicts
        ]
        runtime_tokens_used = sum(
            res.estimated_tokens
            for res in source_results.values()
            if res.status in (SourceStatus.INCLUDED.value, SourceStatus.TRUNCATED.value)
        )
        total_tokens_used = runtime_tokens_used + semantic.estimated_tokens

        # STRICT HARD BUDGET RUNTIME GUARD
        if total_tokens_used > effective_total_budget:
            raise RuntimeError(
                f"Context hydration failed: total tokens used exceeds effective budget ({total_tokens_used} > {effective_total_budget})"
            )

        included_sources = [k for k, v in source_statuses.items() if v in (SourceStatus.INCLUDED.value, SourceStatus.TRUNCATED.value)]
        excluded_sources = [k for k, v in source_statuses.items() if v == SourceStatus.SKIPPED.value]
        degraded_sources = [k for k, v in source_statuses.items() if v == SourceStatus.DEGRADED.value]
        truncated_sources = [k for k, v in source_statuses.items() if v == SourceStatus.TRUNCATED.value]

        excluded_manifest_sources: list[ContextSource] = []
        degraded_manifest_sources: list[ContextSource] = []
        for source_key, result in source_results.items():
            if result.status == SourceStatus.INCLUDED.value:
                if source_key != "hybrid_retrieval":
                    inc_sources.append(
                        ContextSource(
                            kind=source_key,
                            id=source_key,
                            reason="runtime source included by hydration recipe",
                            owner_user_id=owner_user_id,
                            token_estimate=result.estimated_tokens,
                        )
                    )
                continue
            source = ContextSource(
                kind=source_key,
                id=source_key,
                reason=result.error_message or f"runtime source status: {result.status}",
                status=result.status,
                owner_user_id=owner_user_id,
                token_estimate=result.estimated_tokens,
                truncated=result.status == SourceStatus.TRUNCATED.value,
                degraded=result.status in {
                    SourceStatus.DEGRADED.value,
                    SourceStatus.FAILED.value,
                    SourceStatus.TRUNCATED.value,
                },
                provenance="capability hydration recipe",
            )
            if result.status == SourceStatus.TRUNCATED.value:
                inc_sources.append(source)
            else:
                excluded_manifest_sources.append(source)
            if source.degraded:
                degraded_manifest_sources.append(source)

        manifest = ContextManifest(
            scope_statement=f"Owner {scope_envelope.sharing_boundary} scope",
            included=inc_sources + semantic.manifest.included,
            excluded=excluded_manifest_sources + semantic.manifest.excluded,
            degraded=degraded_manifest_sources + semantic.manifest.degraded,
            token_budget=effective_total_budget,
            token_used=total_tokens_used,
        )

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
            retrieved_evidence=retrieval_dicts,
            workspace_frame=frame,
            active_plans=active_plans,
            timeline_events=timeline_events,
            today_state=today_state,
            orbit_context=orbit_context,
            approved_memory=semantic.approved_memory,
            memory_candidates=semantic.memory_candidates,
            beliefs=semantic.beliefs,
            user_model_claims=semantic.user_model_claims,
            research_results=semantic.research_results,
            semantic_context=semantic.semantic_context,
            source_statuses=source_statuses,
            hydration_report=report,
            estimated_tokens=total_tokens_used,
        )
