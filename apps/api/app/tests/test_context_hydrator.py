"""Unit tests for NUR Mind Progressive ContextHydrator."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.brain.schemas import ScopeEnvelope
from app.mind.capabilities.hydrator import ContextHydrator
from app.mind.capabilities.schemas import (
    CapabilitySpec,
    ContextHydrationRecipe,
    ExecutionMode,
    HydrationFailurePolicy,
    HydrationStatus,
)
from app.ai.schemas import EvidenceRef


@pytest.mark.asyncio
async def test_context_hydrator_honors_recipe():
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )

    recipe = ContextHydrationRecipe(
        include_workspace_frame=False,
        hybrid_retrieval_limit=2,
        fetch_active_plans=True,
        fetch_timeline_window_days=7,
        max_context_tokens=1000,
    )

    spec = CapabilitySpec(
        capability_id="test:recipe_capability",
        name="Recipe Test",
        description="Test hydration recipe",
        intent_signatures=["test hydration recipe"],
        execution_mode=ExecutionMode.READ_ONLY_WORKER,
        required_tools=["get_today_state"],
        hydration_recipe=recipe,
    )

    db_mock = AsyncMock()

    mock_evidence = [
        EvidenceRef(kind="note", id="note-1", excerpt="Important note excerpt", rank=0.9),
    ]

    with patch("app.mind.capabilities.hydrator.retrieve_hybrid", new=AsyncMock(return_value=mock_evidence)), \
         patch("app.mind.capabilities.hydrator.read_plans", new=AsyncMock(return_value={"found": True, "plans": [{"title": "Launch Project"}]})), \
         patch("app.mind.capabilities.hydrator.read_timeline", new=AsyncMock(return_value={"count": 1, "events": [{"title": "Completed task 1"}]})):
        hydrated = await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec,
            query="Summarize my day and plans",
        )

        assert hydrated.capability_id == "test:recipe_capability"
        assert len(hydrated.retrieval_refs) == 1
        assert len(hydrated.active_plans) == 1
        assert hydrated.active_plans[0]["title"] == "Launch Project"
        assert len(hydrated.timeline_events) == 1
        assert hydrated.workspace_frame is None
        assert hydrated.manifest.token_budget <= 1000
        assert hydrated.estimated_tokens > 0
        assert hydrated.hydration_report is not None
        assert hydrated.hydration_report.status == HydrationStatus.SUCCESS


@pytest.mark.asyncio
async def test_context_hydrator_rejects_missing_scope():
    owner_id = uuid.uuid4()
    spec = CapabilitySpec(
        capability_id="test:scope_test",
        name="Scope Test",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
    )
    db_mock = AsyncMock()
    with pytest.raises(ValueError) as exc_info:
        await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=None,  # type: ignore
            capability=spec,
            query="hello",
        )
    assert "Missing ScopeEnvelope" in str(exc_info.value)


@pytest.mark.asyncio
async def test_context_hydrator_rejects_cross_owner_scope():
    owner_id = uuid.uuid4()
    cross_owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=cross_owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    spec = CapabilitySpec(
        capability_id="test:cross_owner",
        name="Cross Owner",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
    )
    db_mock = AsyncMock()
    with pytest.raises(PermissionError) as exc_info:
        await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec,
            query="hello",
        )
    assert "Cross-owner scope violation" in str(exc_info.value)


@pytest.mark.asyncio
async def test_context_hydrator_rejects_orbit_id_mismatch():
    owner_id = uuid.uuid4()
    scope_orbit = uuid.uuid4()
    req_orbit = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        orbit_id=scope_orbit,
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    spec = CapabilitySpec(
        capability_id="test:orbit_mismatch",
        name="Orbit Mismatch",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
    )
    db_mock = AsyncMock()
    with pytest.raises(ValueError) as exc_info:
        await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec,
            query="hello",
            orbit_id=req_orbit,
        )
    assert "Orbit ID mismatch" in str(exc_info.value)


@pytest.mark.asyncio
async def test_context_hydrator_deduplicates_sources():
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    recipe = ContextHydrationRecipe(
        include_workspace_frame=False,
        hybrid_retrieval_limit=4,
        max_context_tokens=2000,
    )
    spec = CapabilitySpec(
        capability_id="test:dedup",
        name="Dedup Test",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        hydration_recipe=recipe,
    )
    db_mock = AsyncMock()
    duplicate_refs = [
        EvidenceRef(kind="note", id="dup-1", excerpt="Text 1", rank=0.9),
        EvidenceRef(kind="note", id="dup-1", excerpt="Text 1 duplicate", rank=0.8),
        EvidenceRef(kind="note", id="dup-2", excerpt="Text 2", rank=0.7),
    ]

    with patch("app.mind.capabilities.hydrator.retrieve_hybrid", new=AsyncMock(return_value=duplicate_refs)):
        hydrated = await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec,
            query="test query",
        )
        assert len(hydrated.retrieval_refs) == 2
        assert [r.id for r in hydrated.retrieval_refs] == ["dup-1", "dup-2"]


@pytest.mark.asyncio
async def test_context_hydrator_filters_record_classes_and_entities():
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )
    recipe = ContextHydrationRecipe(
        include_workspace_frame=False,
        hybrid_retrieval_limit=4,
        required_record_classes=("note",),
        excluded_record_classes=("chat",),
        allowed_entity_ids=("entity-1",),
        max_context_tokens=2000,
    )
    spec = CapabilitySpec(
        capability_id="test:filters",
        name="Filters Test",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        hydration_recipe=recipe,
    )
    db_mock = AsyncMock()
    refs = [
        EvidenceRef(kind="note", id="entity-1", excerpt="Allowed note", rank=0.9),
        EvidenceRef(kind="note", id="entity-2", excerpt="Disallowed entity id", rank=0.8),
        EvidenceRef(kind="chat", id="entity-1", excerpt="Excluded record class", rank=0.7),
        EvidenceRef(kind="plan", id="entity-1", excerpt="Non-required record class", rank=0.6),
    ]

    with patch("app.mind.capabilities.hydrator.retrieve_hybrid", new=AsyncMock(return_value=refs)):
        hydrated = await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec,
            query="test query",
        )
        assert len(hydrated.retrieval_refs) == 1
        assert hydrated.retrieval_refs[0].id == "entity-1"
        assert hydrated.retrieval_refs[0].kind == "note"


@pytest.mark.asyncio
async def test_context_hydrator_failure_policy_enforcement():
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )

    # 1. Optional failure -> DEGRADED
    recipe_optional = ContextHydrationRecipe(
        source_keys=("active_plans", "timeline"),
        required_source_keys=(),
        optional_source_keys=("active_plans", "timeline"),
        failure_policy=HydrationFailurePolicy.FAIL_REQUIRED_DEGRADE_OPTIONAL,
        include_workspace_frame=False,
        hybrid_retrieval_limit=0,
    )
    spec_optional = CapabilitySpec(
        capability_id="test:optional_failure",
        name="Optional Failure",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        hydration_recipe=recipe_optional,
    )

    db_mock = AsyncMock()
    with patch("app.mind.capabilities.hydrator.read_plans", side_effect=Exception("Database lock")), \
         patch("app.mind.capabilities.hydrator.read_timeline", new=AsyncMock(return_value={"count": 0, "events": []})):
        hydrated = await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec_optional,
            query="test query",
        )
        assert hydrated.hydration_report is not None
        assert hydrated.hydration_report.status == HydrationStatus.DEGRADED
        assert "active_plans" in hydrated.hydration_report.degraded_sources

    # 2. Required failure -> raises RuntimeError
    recipe_required = ContextHydrationRecipe(
        source_keys=("active_plans",),
        required_source_keys=("active_plans",),
        failure_policy=HydrationFailurePolicy.FAIL_REQUIRED_DEGRADE_OPTIONAL,
        include_workspace_frame=False,
        hybrid_retrieval_limit=0,
    )
    spec_required = CapabilitySpec(
        capability_id="test:required_failure",
        name="Required Failure",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        hydration_recipe=recipe_required,
    )

    with patch("app.mind.capabilities.hydrator.read_plans", side_effect=Exception("Unrecoverable failure")):
        with pytest.raises(RuntimeError) as exc_info:
            await ContextHydrator.hydrate(
                db_mock,
                owner_user_id=owner_id,
                scope_envelope=scope,
                capability=spec_required,
                query="test query",
            )
        assert "Context hydration failed for required source 'active_plans'" in str(exc_info.value)


@pytest.mark.asyncio
async def test_context_hydrator_strict_hard_token_budget():
    """Verify total_tokens_used <= max_context_tokens invariant and truncation behavior."""
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )

    # Budget of 50 tokens: enough for first item, but second will exceed
    recipe = ContextHydrationRecipe(
        source_keys=("hybrid_retrieval",),
        optional_source_keys=("hybrid_retrieval",),
        include_workspace_frame=False,
        hybrid_retrieval_limit=10,
        max_context_tokens=50,
        max_total_tokens=50,
    )
    spec = CapabilitySpec(
        capability_id="test:hard_budget",
        name="Hard Budget Test",
        description="",
        intent_signatures=["test"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        hydration_recipe=recipe,
    )

    db_mock = AsyncMock()
    refs = [
        EvidenceRef(kind="note", id="note-1", excerpt="Short text 123", rank=0.9),  # ~4 tokens
        EvidenceRef(kind="note", id="note-2", excerpt="Very long excerpt " * 50, rank=0.8),  # ~225 tokens
    ]

    with patch("app.mind.capabilities.hydrator.retrieve_hybrid", new=AsyncMock(return_value=refs)):
        hydrated = await ContextHydrator.hydrate(
            db_mock,
            owner_user_id=owner_id,
            scope_envelope=scope,
            capability=spec,
            query="test query",
        )
        assert hydrated.hydration_report is not None
        assert hydrated.hydration_report.total_tokens_used <= 50
        assert "hybrid_retrieval" in hydrated.hydration_report.truncated_sources
