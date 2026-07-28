"""The approval digest is what binds a decision to one exact call.

If the digest were sensitive to key order, an approval would be invalidated by
nothing more than a dict being rebuilt. If it were insensitive to values, an
approved action could be replayed with different arguments — which is the whole
attack this column exists to prevent.
"""

from app.agentic.orchestrator import argument_digest


def test_key_order_does_not_change_the_digest():
    a = argument_digest("schedule_timeline_event", "1", {"title": "Review", "when": "Friday"})
    b = argument_digest("schedule_timeline_event", "1", {"when": "Friday", "title": "Review"})
    assert a == b


def test_any_value_change_changes_the_digest():
    base = argument_digest("schedule_timeline_event", "1", {"title": "Review", "when": "Friday"})
    changed = argument_digest("schedule_timeline_event", "1", {"title": "Review", "when": "Monday"})
    assert base != changed, "swapping an argument must invalidate the approval"


def test_added_argument_changes_the_digest():
    base = argument_digest("create_capsule", "1", {"recipient": "a@example.com"})
    widened = argument_digest(
        "create_capsule", "1", {"recipient": "a@example.com", "include_journal": True}
    )
    assert base != widened, "widening scope must not reuse an existing approval"


def test_tool_and_version_are_part_of_the_binding():
    args = {"title": "Review"}
    assert argument_digest("tool_a", "1", args) != argument_digest("tool_b", "1", args)
    assert argument_digest("tool_a", "1", args) != argument_digest("tool_a", "2", args)


def test_digest_is_stable_across_calls():
    args = {"nested": {"b": 2, "a": 1}, "list": [3, 1, 2]}
    assert argument_digest("t", "1", args) == argument_digest("t", "1", args)


def test_digest_shape_fits_the_column():
    # varchar(71): "sha256:" + 64 hex chars.
    digest = argument_digest("t", "1", {})
    assert digest.startswith("sha256:")
    assert len(digest) == 71


def test_nested_reordering_is_also_stable():
    """Reordering a nested object must not invalidate an approval either."""
    a = argument_digest("t", "1", {"outer": {"x": 1, "y": 2}})
    b = argument_digest("t", "1", {"outer": {"y": 2, "x": 1}})
    assert a == b
