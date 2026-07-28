"""Trace correlation across the API/queue boundary.

The value of a trace here is being able to answer "why did NUR do that?" by
following one id from the owner's click, through planning and policy, into a
queue, out into a worker, down to a tool call and the row it wrote. That chain
breaks at exactly one place by default: the queue. A Celery payload is JSON, so
whatever ambient trace context the API had does not survive into the worker
unless it is carried explicitly.

So the trace id travels as an ordinary field in the ID-only payload. No
dependency on an OpenTelemetry SDK being installed, no context propagator to
configure wrongly, and it still works when the collector is off — which is the
common case in development, where an unreadable trace is most costly.

W3C traceparent format is used rather than a bare uuid so that when a real OTel
exporter is added, the ids already line up instead of needing a migration.
"""

from __future__ import annotations

import os
import re
import secrets
from dataclasses import dataclass

_TRACEPARENT = re.compile(r"^00-([0-9a-f]{32})-([0-9a-f]{16})-[0-9a-f]{2}$")


@dataclass(frozen=True)
class TraceContext:
    trace_id: str  # 32 hex
    span_id: str  # 16 hex

    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-01"

    def child(self) -> "TraceContext":
        """A new span under the same trace — what crossing into a worker means."""
        return TraceContext(self.trace_id, secrets.token_hex(8))


def new_trace() -> TraceContext:
    return TraceContext(secrets.token_hex(16), secrets.token_hex(8))


def parse_traceparent(value: str | None) -> TraceContext | None:
    """Parse an inbound header. Returns None rather than raising.

    A malformed traceparent from outside is not worth failing a request over;
    starting a fresh trace loses correlation with an upstream system but keeps
    the request working, and the alternative punishes the owner for someone
    else's header.
    """
    if not value:
        return None
    match = _TRACEPARENT.match(value.strip())
    if not match:
        return None
    trace_id, span_id = match.groups()
    # All-zero ids are the spec's "invalid" sentinel.
    if trace_id == "0" * 32 or span_id == "0" * 16:
        return None
    return TraceContext(trace_id, span_id)


def continue_or_start(traceparent: str | None) -> TraceContext:
    return parse_traceparent(traceparent) or new_trace()


def worker_id() -> str:
    """Stable-enough identity for lease ownership.

    Host plus pid: a restarted worker gets a new pid and therefore cannot
    heartbeat a lease its dead predecessor was holding, which is the behaviour
    `heartbeat_step` relies on to refuse a reclaimed worker.
    """
    return f"{os.uname().nodename}:{os.getpid()}"
