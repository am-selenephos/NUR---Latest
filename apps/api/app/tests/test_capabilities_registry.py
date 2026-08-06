"""Tests for CapabilityRegistry and CapabilitySpec contracts."""
import pytest

from app.mind.capabilities.schemas import CapabilitySpec, ExecutionMode
from app.mind.capabilities.registry import (
    CapabilityRegistry,
    DuplicateCapabilityError,
    InvalidCapabilitySpecError,
    get_default_registry,
)
from app.agentic.tools import ALL_TOOLS
from app.agentic.registry import spec as get_tool_spec
from app.mind.capabilities.definitions.contextual_answer import CONTEXTUAL_ANSWER_SPEC
from app.mind.capabilities.definitions.plan_from_conversation import PLAN_FROM_CONVERSATION_SPEC


def test_registry_valid_capability():
    reg = CapabilityRegistry()
    spec = CapabilitySpec(
        capability_id="capability:custom_test",
        name="Custom Test",
        description="A test capability",
        intent_signatures=["test intent", "run custom test"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.READ_ONLY_WORKER,
        required_tools=["get_plan"],  # Valid R0 tool from app.agentic.tools
        worker_role="SPECIALIST",
    )
    reg.register(spec)
    assert reg.get("capability:custom_test") == spec
    assert spec in reg.all()


def test_registry_rejects_unknown_tool():
    reg = CapabilityRegistry()
    spec = CapabilitySpec(
        capability_id="capability:malicious_tool",
        name="Malicious Tool",
        description="Attempts to invoke undeclared tool",
        intent_signatures=["steal secrets"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.READ_ONLY_WORKER,
        required_tools=["shell_exec_nonexistent"],
        worker_role="SPECIALIST",
    )
    with pytest.raises(InvalidCapabilitySpecError) as exc_info:
        reg.register(spec)
    assert "references unknown tool 'shell_exec_nonexistent'" in str(exc_info.value)


def test_registry_rejects_duplicate_id():
    reg = CapabilityRegistry()
    spec1 = CapabilitySpec(
        capability_id="capability:dup",
        name="Dup 1",
        description="First instance",
        intent_signatures=["intent 1"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        required_tools=[],
    )
    spec2 = CapabilitySpec(
        capability_id="capability:dup",
        name="Dup 2",
        description="Second instance",
        intent_signatures=["intent 2"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        required_tools=[],
    )
    reg.register(spec1)
    with pytest.raises(DuplicateCapabilityError) as exc_info:
        reg.register(spec2)
    assert "Duplicate capability registered: capability:dup" in str(exc_info.value)


def test_registry_missing_key():
    reg = CapabilityRegistry()
    with pytest.raises(KeyError):
        reg.get("capability:nonexistent")


def test_registry_surface_and_sensitivity_filtering():
    reg = CapabilityRegistry()
    spec_talk_normal = CapabilitySpec(
        capability_id="capability:talk_normal",
        name="Talk Normal",
        description="",
        intent_signatures=["talk"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        required_tools=[],
    )
    spec_talk_high = CapabilitySpec(
        capability_id="capability:talk_high",
        name="Talk High",
        description="",
        intent_signatures=["talk high"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="HIGH",
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        required_tools=[],
    )
    spec_today_only = CapabilitySpec(
        capability_id="capability:today_only",
        name="Today Only",
        description="",
        intent_signatures=["today"],
        allowed_surfaces=["today"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.READ_ONLY_WORKER,
        required_tools=["get_today_state"],
    )

    reg.register(spec_talk_normal)
    reg.register(spec_talk_high)
    reg.register(spec_today_only)

    # Surface "talk", Sensitivity "NORMAL" -> should get talk_normal and talk_high
    talk_normal = reg.filter_by_surface_and_scope("talk", "NORMAL")
    assert len(talk_normal) == 2
    assert {c.capability_id for c in talk_normal} == {"capability:talk_normal", "capability:talk_high"}

    # Surface "talk", Sensitivity "ELEVATED" -> talk_normal ceiling (NORMAL) cannot handle ELEVATED, only talk_high can
    talk_elevated = reg.filter_by_surface_and_scope("talk", "ELEVATED")
    assert len(talk_elevated) == 1
    assert talk_elevated[0].capability_id == "capability:talk_high"

    # Surface "today", Sensitivity "NORMAL" -> should get today_only
    today_res = reg.filter_by_surface_and_scope("today", "NORMAL")
    assert len(today_res) == 1
    assert today_res[0].capability_id == "capability:today_only"


def test_registry_disabled_capability_not_returned():
    reg = CapabilityRegistry()
    disabled_spec = CapabilitySpec(
        capability_id="capability:disabled_test",
        name="Disabled Test",
        description="",
        intent_signatures=["disabled"],
        allowed_surfaces=["talk"],
        sensitivity_ceiling="NORMAL",
        execution_mode=ExecutionMode.COGNITIVE_SYNTHESIS,
        required_tools=[],
        enabled=False,
    )
    reg.register(disabled_spec)
    assert reg.get("capability:disabled_test") == disabled_spec
    filtered = reg.filter_by_surface_and_scope("talk", "NORMAL")
    assert "capability:disabled_test" not in {c.capability_id for c in filtered}


def test_default_registry_initialized():
    reg = get_default_registry()
    caps = reg.all()
    cap_ids = {c.capability_id for c in caps}
    assert "capability:contextual_answer" in cap_ids
    assert "capability:plan_from_conversation" in cap_ids
    assert "capability:summarize_day" not in cap_ids
    assert len(cap_ids) == 2


def test_structural_registry_separation():
    """Prove CapabilityRegistry and Agency Registry maintain distinct, non-overlapping boundaries."""
    reg = get_default_registry()
    agency_tool_keys = {tool.contract.key for tool in ALL_TOOLS}
    for cap in reg.all():
        # CapabilityRegistry entries are cognitive specs, never Agency tool keys
        assert cap.capability_id not in agency_tool_keys
        # Declared required tools MUST be valid registered Agency tool keys
        for tool_key in cap.required_tools:
            assert tool_key in agency_tool_keys
            # Must resolve through get_tool_spec without error
            assert get_tool_spec(tool_key) is not None


def test_contextual_answer_spec_contract():
    assert CONTEXTUAL_ANSWER_SPEC.capability_id == "capability:contextual_answer"
    assert CONTEXTUAL_ANSWER_SPEC.execution_mode == ExecutionMode.COGNITIVE_SYNTHESIS
    assert CONTEXTUAL_ANSWER_SPEC.required_tools == []
    assert CONTEXTUAL_ANSWER_SPEC.min_confidence_threshold >= 0.82
    assert CONTEXTUAL_ANSWER_SPEC.enabled is True


def test_plan_from_conversation_spec_contract():
    assert PLAN_FROM_CONVERSATION_SPEC.capability_id == "capability:plan_from_conversation"
    assert PLAN_FROM_CONVERSATION_SPEC.execution_mode == ExecutionMode.WORKFLOW_PROPOSAL
    assert "create_draft_plan" in PLAN_FROM_CONVERSATION_SPEC.required_tools
    assert PLAN_FROM_CONVERSATION_SPEC.min_confidence_threshold >= 0.82
    assert PLAN_FROM_CONVERSATION_SPEC.enabled is True
