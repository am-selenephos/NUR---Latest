"""Unit tests for NUR Mind Progressive ContextHydrator."""
import uuid
import pytest
from unittest.mock import AsyncMock, patch

from app.brain.schemas import ScopeEnvelope
from app.mind.capabilities.hydrator import ContextHydrator
from app.mind.capabilities.schemas import CapabilitySpec, ContextHydrationRecipe, ExecutionMode
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

    from unittest.mock import MagicMock
    from types import SimpleNamespace

    plan_mock = SimpleNamespace(
        id=uuid.uuid4(),
        title="Launch Project",
        status="ACTIVE",
        orbit_id=None,
        target_date=None,
        steps=[],
    )
    event_mock = SimpleNamespace(
        id=uuid.uuid4(),
        event_kind="NOTE_CREATED",
        content_text="Completed task 1",
        created_at=None,
        orbit_id=None,
    )

    def mock_execute_side_effect(stmt, *args, **kwargs):
        res = MagicMock()
        stmt_str = str(stmt)
        if "plans" in stmt_str.lower():
            res.scalars.return_value.all.return_value = [plan_mock]
        elif "cognitive_events" in stmt_str.lower():
            res.scalars.return_value.all.return_value = [event_mock]
        else:
            res.scalars.return_value.all.return_value = []
        return res

    db_mock.execute = AsyncMock(side_effect=mock_execute_side_effect)

    with patch("app.mind.capabilities.hydrator.retrieve_hybrid", new=AsyncMock(return_value=mock_evidence)):
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
        assert hydrated.manifest.token_budget == 1000
        assert hydrated.estimated_tokens > 0



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
async def test_context_hydrator_zero_limits():
    owner_id = uuid.uuid4()
    scope = ScopeEnvelope(
        owner_user_id=owner_id,
        surface="talk",
        sensitivity_ceiling="NORMAL",
        sharing_boundary="PRIVATE",
    )

    recipe = ContextHydrationRecipe(
        include_workspace_frame=False,
        hybrid_retrieval_limit=0,
        fetch_active_plans=False,
        fetch_timeline_window_days=0,
        max_context_tokens=500,
    )

    spec = CapabilitySpec(
        capability_id="test:minimal_capability",
        name="Minimal Test",
        description="Test minimal hydration",
        intent_signatures=["minimal"],
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        hydration_recipe=recipe,
    )

    db_mock = AsyncMock()

    hydrated = await ContextHydrator.hydrate(
        db_mock,
        owner_user_id=owner_id,
        scope_envelope=scope,
        capability=spec,
        query="Minimal query",
    )

    assert hydrated.workspace_frame is None
    assert len(hydrated.retrieval_refs) == 0
    assert len(hydrated.active_plans) == 0
    assert len(hydrated.timeline_events) == 0
    assert hydrated.today_state is None
    assert hydrated.manifest.token_used == 0
