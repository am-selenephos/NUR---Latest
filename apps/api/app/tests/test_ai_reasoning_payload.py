"""The Responses API rejects `reasoning.effort` on non-reasoning models.

`gpt-4.1` — the model the local installer configures — answers a payload
carrying `reasoning` with 400 `unsupported_parameter`, which takes down the
whole live Talk path. The provider therefore sends that field only to
reasoning-capable families.

The guard existed with no test behind it, so nothing would catch a future edit
that sent `reasoning` unconditionally again, and the failure only appears
against a real provider. These tests pin both directions.
"""

from app.ai.openai_provider import _supports_reasoning_effort


def test_configured_default_model_gets_no_reasoning_field():
    """gpt-4.1 is what infra/scripts/configure-openai-local.sh writes."""
    assert _supports_reasoning_effort("gpt-4.1") is False


def test_non_reasoning_families_get_no_reasoning_field():
    for model in ("gpt-4.1", "gpt-4.1-mini", "gpt-4o", "gpt-4o-mini", "gpt-4-turbo"):
        assert _supports_reasoning_effort(model) is False, model


def test_reasoning_families_do_get_the_field():
    for model in ("o1", "o1-mini", "o3", "o3-mini", "o4-mini", "gpt-5", "gpt-5-mini"):
        assert _supports_reasoning_effort(model) is True, model


def test_match_is_case_insensitive():
    assert _supports_reasoning_effort("O3-MINI") is True
    assert _supports_reasoning_effort("GPT-4.1") is False


def test_unknown_model_fails_closed_to_no_reasoning():
    """An unrecognised model must not be sent `reasoning`. Omitting it costs a
    little quality on a model that would have accepted it; sending it to one
    that will not is a 400 that breaks Talk entirely."""
    for model in ("some-future-model", "", "llama-3", "claude-x"):
        assert _supports_reasoning_effort(model) is False, model
