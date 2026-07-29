"""Run one Celery task's coroutine, then drop the connection pool.

`asyncio.run` creates a fresh event loop and closes it on return. The database
engine is a process-level singleton, so its pooled asyncpg connections stay
bound to the loop that opened them — and a Celery worker executes many tasks in
one process. The *second* task in that process therefore reaches for a
connection attached to a loop that no longer exists and fails with "Event loop
is closed", verified directly against this codebase's own engine.

That made every `asyncio.run`-based task in the worker a one-shot: the first
invocation succeeded and every later one raised. It is invisible to a test suite
that calls each task's coroutine once, and it is fatal to anything Beat drives
repeatedly — the Agency Plane dispatcher runs every five seconds.

Disposing the engine in a `finally` means each invocation builds its own pool on
its own loop and closes it cleanly. The cost is one connection setup per task
rather than per process, which for a five-second scheduler is irrelevant next to
not working at all.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import TypeVar

from app.db.session import dispose_engine

T = TypeVar("T")


def run_task(factory: Callable[[], Awaitable[T]]) -> T:
    """Execute `factory()` in a fresh loop and leave no pool behind.

    Takes a zero-argument callable rather than a coroutine object so the
    coroutine is created *inside* the new loop. Creating it outside and awaiting
    it here would bind it to whatever loop happened to be current at call time.
    """

    async def main() -> T:
        try:
            return await factory()
        finally:
            # Even on failure: a half-open pool bound to this loop would poison
            # the next invocation exactly as the shared singleton did.
            await dispose_engine()

    return asyncio.run(main())
