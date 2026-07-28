"""Trace correlation across the queue boundary.

The chain from an owner's click to the row a worker wrote breaks at exactly one
place by default — the queue — because a Celery payload is JSON and ambient
context does not survive it. These test that the id survives explicitly.
"""

import pytest

from app.agentic.observability import (
    TraceContext,
    continue_or_start,
    new_trace,
    parse_traceparent,
    worker_id,
)


def test_new_trace_has_w3c_shaped_ids():
    trace = new_trace()
    assert len(trace.trace_id) == 32
    assert len(trace.span_id) == 16
    int(trace.trace_id, 16)  # raises if not hex
    int(trace.span_id, 16)


def test_traceparent_round_trips():
    original = new_trace()
    restored = parse_traceparent(original.traceparent())
    assert restored == original


def test_a_child_span_keeps_the_trace_but_changes_the_span():
    """Crossing into a worker is a new span under the same trace."""
    parent = new_trace()
    child = parent.child()
    assert child.trace_id == parent.trace_id
    assert child.span_id != parent.span_id


@pytest.mark.parametrize(
    "bad",
    [
        None, "", "garbage", "00-short-0000000000000000-01",
        "01-" + "a" * 32 + "-" + "b" * 16 + "-01",          # unsupported version
        "00-" + "0" * 32 + "-" + "b" * 16 + "-01",          # all-zero trace id
        "00-" + "a" * 32 + "-" + "0" * 16 + "-01",          # all-zero span id
    ],
)
def test_malformed_traceparent_returns_none_rather_than_raising(bad):
    assert parse_traceparent(bad) is None


def test_continue_or_start_never_fails_a_request():
    """A bad header from upstream loses correlation, not the request."""
    assert isinstance(continue_or_start("garbage"), TraceContext)
    assert isinstance(continue_or_start(None), TraceContext)


def test_continue_preserves_an_upstream_trace():
    upstream = new_trace()
    assert continue_or_start(upstream.traceparent()).trace_id == upstream.trace_id


def test_worker_id_changes_across_processes():
    """A restarted worker must not be able to heartbeat its predecessor's lease,
    which `heartbeat_step` relies on by matching worker_id."""
    assert ":" in worker_id()
    assert worker_id().endswith(str(__import__("os").getpid()))
