"""Unit tests for Phase 1: ScopeEnvelope & Identity Privilege.

Tests:
1. ScopeEnvelope model construction and field defaults
2. Scope resolver: valid scope, missing orbit, revoked permission
3. ScopeEnvelope integration with CognitiveTaskPacket
4. Identity privileged instruction layer (not embedded as user content)
5. UncertaintyKind enum coverage
6. Regression: existing schemas still construct correctly
"""

import uuid

import pytest

from app.brain.schemas import (
    BrainProfileKey,
    CognitiveClaim,
    CognitiveResult,
    CognitiveTaskPacket,
    ContextManifest,
    IdentitySnapshot,
    ScopeEnvelope,
    SelfCapabilities,
    UncertaintyKind,
)
from app.brain.prompts import build_system_prompt, build_user_prompt
from app.mind.identity import load_identity
from app.mind.working_memory import build_context_manifest


# ── Helpers ────────────────────────────────────────────────────────────────

def _make_identity() -> IdentitySnapshot:
    return load_identity()


def _make_scope(
    owner_user_id: uuid.UUID | None = None,
    orbit_id: uuid.UUID | None = None,
    memory_mode: str = "EPHEMERAL",
    surface: str = "talk",
) -> ScopeEnvelope:
    return ScopeEnvelope(
        owner_user_id=owner_user_id or uuid.uuid4(),
        surface=surface,
        orbit_id=orbit_id,
        memory_write_policy=memory_mode,
    )


def _make_packet(
    scope_envelope: ScopeEnvelope | None = None,
    **kwargs,
) -> CognitiveTaskPacket:
    defaults = {
        "owner_user_id": uuid.uuid4(),
        "task_class": "talk",
        "user_input": "Hello NUR",
        "identity": _make_identity(),
        "self_capabilities": SelfCapabilities(
            provider_name="disabled", provider_available=False
        ),
        "context_manifest": ContextManifest(scope_statement="test"),
    }
    defaults.update(kwargs)
    if scope_envelope is not None:
        defaults["scope_envelope_id"] = scope_envelope.scope_id
    return CognitiveTaskPacket(**defaults)


# ── ScopeEnvelope model tests ─────────────────────────────────────────────

class TestScopeEnvelope:
    def test_construction_with_defaults(self):
        uid = uuid.uuid4()
        scope = ScopeEnvelope(owner_user_id=uid)
        assert scope.owner_user_id == uid
        assert scope.surface == "talk"
        assert scope.sharing_boundary == "PRIVATE"
        assert scope.memory_read_policy == "SCOPED"
        assert scope.memory_write_policy == "EPHEMERAL"
        assert scope.retention_policy == "DEFAULT"
        assert scope.sensitivity_ceiling == "NORMAL"
        assert scope.orbit_id is None
        assert scope.project_id is None
        assert scope.capsule_id is None
        assert scope.community_id is None
        assert scope.scope_id is not None

    def test_scope_id_unique_per_instance(self):
        uid = uuid.uuid4()
        s1 = ScopeEnvelope(owner_user_id=uid)
        s2 = ScopeEnvelope(owner_user_id=uid)
        assert s1.scope_id != s2.scope_id

    def test_orbit_scope(self):
        uid = uuid.uuid4()
        oid = uuid.uuid4()
        scope = ScopeEnvelope(
            owner_user_id=uid,
            orbit_id=oid,
            sharing_boundary="ORBIT",
        )
        assert scope.orbit_id == oid
        assert scope.sharing_boundary == "ORBIT"

    def test_review_memory_mode(self):
        scope = ScopeEnvelope(
            owner_user_id=uuid.uuid4(),
            memory_write_policy="REVIEW",
        )
        assert scope.memory_write_policy == "REVIEW"

    def test_serialization_roundtrip(self):
        scope = ScopeEnvelope(
            owner_user_id=uuid.uuid4(),
            orbit_id=uuid.uuid4(),
            surface="research",
            sharing_boundary="PROJECT",
            sensitivity_ceiling="ELEVATED",
            reason="Test scope",
            policy_versions={"scope_resolver": "1.0.0"},
        )
        data = scope.model_dump(mode="json")
        restored = ScopeEnvelope.model_validate(data)
        assert restored.scope_id == scope.scope_id
        assert restored.surface == "research"
        assert restored.sharing_boundary == "PROJECT"
        assert restored.sensitivity_ceiling == "ELEVATED"
        assert restored.policy_versions == {"scope_resolver": "1.0.0"}


# ── UncertaintyKind tests ─────────────────────────────────────────────────

class TestUncertaintyKind:
    def test_all_kinds_exist(self):
        expected = {
            "unknown", "insufficient_evidence", "stale_evidence",
            "disagreement", "model_limitation", "conflicting_owner_state",
        }
        actual = {k.value for k in UncertaintyKind}
        assert actual == expected

    def test_claim_with_uncertainty_kind(self):
        claim = CognitiveClaim(
            claim_text="Test claim",
            claim_kind="inferred",
            confidence=0.3,
            uncertainty_kind=UncertaintyKind.INSUFFICIENT_EVIDENCE,
        )
        assert claim.uncertainty_kind == UncertaintyKind.INSUFFICIENT_EVIDENCE

    def test_claim_without_uncertainty_kind(self):
        claim = CognitiveClaim(claim_text="Test claim")
        assert claim.uncertainty_kind is None

    def test_str_enum_behavior(self):
        assert str(UncertaintyKind.UNKNOWN) == "unknown"
        assert UncertaintyKind("stale_evidence") == UncertaintyKind.STALE_EVIDENCE


# ── CognitiveTaskPacket scope_envelope_id tests ───────────────────────────

class TestPacketScopeIntegration:
    def test_packet_without_scope(self):
        packet = _make_packet()
        assert packet.scope_envelope_id is None

    def test_packet_with_scope(self):
        scope = _make_scope()
        packet = _make_packet(scope_envelope=scope)
        assert packet.scope_envelope_id == scope.scope_id

    def test_scope_id_persists_in_serialization(self):
        scope = _make_scope()
        packet = _make_packet(scope_envelope=scope)
        data = packet.model_dump(mode="json")
        assert data["scope_envelope_id"] == str(scope.scope_id)


# ── Scope Resolver tests ──────────────────────────────────────────────────

class TestScopeResolver:
    @pytest.mark.asyncio
    async def test_resolve_basic_talk_scope(self):
        from app.mind.scope import resolve_scope

        # Mock a database session that doesn't hit a real DB
        # For unit testing the resolver logic, we test without orbit
        class FakeDB:
            async def execute(self, *a, **kw):
                raise AssertionError("Should not query DB without orbit_id")

        scope = await resolve_scope(
            FakeDB(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            surface="talk",
            memory_mode="EPHEMERAL",
        )
        assert scope.surface == "talk"
        assert scope.sharing_boundary == "PRIVATE"
        assert scope.memory_write_policy == "EPHEMERAL"
        assert scope.memory_read_policy == "SCOPED"
        assert "TALK_TURN" in scope.allowed_record_classes
        assert "MODEL_RESPONSE" in scope.allowed_record_classes

    @pytest.mark.asyncio
    async def test_resolve_journal_scope(self):
        from app.mind.scope import resolve_scope

        class FakeDB:
            async def execute(self, *a, **kw):
                raise AssertionError("Should not query DB without orbit_id")

        scope = await resolve_scope(
            FakeDB(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            surface="journal",
            memory_mode="EPHEMERAL",
        )
        assert scope.surface == "journal"
        assert scope.sensitivity_ceiling == "ELEVATED"
        assert "JOURNAL_ENTRY" in scope.allowed_record_classes

    @pytest.mark.asyncio
    async def test_resolve_review_memory_mode(self):
        from app.mind.scope import resolve_scope

        class FakeDB:
            async def execute(self, *a, **kw):
                raise AssertionError("Should not query DB without orbit_id")

        scope = await resolve_scope(
            FakeDB(),  # type: ignore[arg-type]
            owner_user_id=uuid.uuid4(),
            surface="talk",
            memory_mode="REVIEW",
        )
        assert scope.memory_write_policy == "REVIEW"

    @pytest.mark.asyncio
    async def test_missing_orbit_blocks_scope(self):
        """Directive §8.1: unowned orbit → BLOCK."""
        from app.mind.scope import ScopeResolutionError, resolve_scope

        class FakeResult:
            def scalar_one_or_none(self):
                return None  # orbit not found

        class FakeDB:
            async def execute(self, *a, **kw):
                return FakeResult()

        with pytest.raises(ScopeResolutionError, match="not owned"):
            await resolve_scope(
                FakeDB(),  # type: ignore[arg-type]
                owner_user_id=uuid.uuid4(),
                surface="talk",
                orbit_id=uuid.uuid4(),
            )


# ── Identity privilege tests ──────────────────────────────────────────────

class TestPrivilegedIdentity:
    def test_system_prompt_contains_privileged_header(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "NUR Privileged Identity Envelope" in prompt
        assert "privileged instruction layer" in prompt

    def test_system_prompt_contains_identity_version(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "v1.0.0-20260802" in prompt

    def test_system_prompt_contains_override_protection(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "cannot be overridden" in prompt

    def test_system_prompt_contains_forbidden_claims(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "NEVER:" in prompt
        assert "sentience" in prompt.lower()

    def test_system_prompt_contains_universal_laws(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "Universal laws" in prompt
        assert "External content" in prompt

    def test_system_prompt_includes_initiative_rules(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "Initiative rules" in prompt

    def test_system_prompt_includes_language_behaviour(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.BALANCED)
        assert "Language behaviour" in prompt

    def test_user_prompt_does_not_contain_identity(self):
        """Identity must NOT be embedded in user content."""
        packet = _make_packet()
        user_prompt = build_user_prompt(packet)
        assert "Privileged" not in user_prompt
        assert "constitution" not in user_prompt.lower()
        assert "forbidden" not in user_prompt.lower()
        assert "identity envelope" not in user_prompt.lower()

    def test_user_prompt_contains_owner_message(self):
        packet = _make_packet(user_input="What is the meaning of life?")
        user_prompt = build_user_prompt(packet)
        assert "What is the meaning of life?" in user_prompt

    def test_critic_profile_system_prompt(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.CRITIC)
        assert "Critic role" in prompt
        assert "independent verification" in prompt

    def test_deep_profile_system_prompt(self):
        packet = _make_packet()
        prompt = build_system_prompt(packet, BrainProfileKey.DEEP)
        assert "Deep reasoning" in prompt


# ── Regression tests ──────────────────────────────────────────────────────

class TestRegression:
    def test_cognitive_result_still_constructs(self):
        """Ensure CognitiveResult works with the new uncertainty_kind field."""
        result = CognitiveResult(
            task_id=uuid.uuid4(),
            profile_used=BrainProfileKey.BALANCED,
            direct_response="Test response.",
            claims=[
                CognitiveClaim(
                    claim_text="Claim 1",
                    claim_kind="inferred",
                    source_refs=["journal:123"],
                ),
                CognitiveClaim(
                    claim_text="Uncertain claim",
                    claim_kind="inferred",
                    confidence=0.2,
                    uncertainty_kind=UncertaintyKind.STALE_EVIDENCE,
                ),
            ],
            source_refs=["journal:123"],
        )
        assert len(result.claims) == 2
        assert result.claims[0].uncertainty_kind is None
        assert result.claims[1].uncertainty_kind == UncertaintyKind.STALE_EVIDENCE

    def test_context_manifest_still_works(self):
        refs = [
            {"kind": "JOURNAL", "id": "j1", "excerpt": "Note one", "rank": 0.9},
        ]
        manifest, filtered = build_context_manifest(
            retrieved_refs=refs,
            scope_statement="test",
            token_budget=1000,
        )
        assert len(manifest.included) == 1
        assert len(filtered) == 1

    def test_identity_loading_still_works(self):
        identity = load_identity()
        assert identity.version == "v1.0.0-20260802"
        assert identity.name == "NUR"
