from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import uuid
from dataclasses import dataclass, field
from typing import Any

from app.ai.errors import AIRequestBudgetExceeded
from app.cognition.intelligence_kernel import (
    TalkProviderFailure,
    TalkRunCancelled,
    TalkRunConflict,
    run_talk_kernel,
)
from app.db.rls import set_user_context
from app.db.session import get_sessionmaker


@dataclass(frozen=True)
class TalkStreamSpec:
    request_id: uuid.UUID
    message: str
    orbit_id: uuid.UUID | None
    locale: str
    writing_preference: str
    mode: str | None
    memory_mode: str
    capability_id: str | None = None

    @property
    def fingerprint(self) -> str:
        raw = json.dumps(
            {
                "message": self.message,
                "orbit_id": str(self.orbit_id) if self.orbit_id else None,
                "locale": self.locale,
                "writing_preference": self.writing_preference,
                "mode": self.mode,
                "capability_id": self.capability_id,
                "memory_mode": self.memory_mode,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(raw.encode()).hexdigest()


@dataclass(frozen=True)
class TalkStreamEnvelope:
    sequence: int
    event: str
    data: dict[str, Any]


@dataclass
class TalkStreamJob:
    owner_user_id: uuid.UUID
    spec: TalkStreamSpec
    events: list[TalkStreamEnvelope] = field(default_factory=list)
    done: bool = False
    task: asyncio.Task[None] | None = None
    _sequence: int = 0
    _condition: asyncio.Condition = field(default_factory=asyncio.Condition)

    async def publish(self, event: str, data: dict[str, Any]) -> TalkStreamEnvelope:
        async with self._condition:
            self._sequence += 1
            envelope = TalkStreamEnvelope(self._sequence, event, data)
            self.events.append(envelope)
            self._condition.notify_all()
            return envelope

    async def finish(self) -> None:
        async with self._condition:
            self.done = True
            self._condition.notify_all()

    async def next_after(self, sequence: int, timeout_seconds: float = 5.0) -> TalkStreamEnvelope | None:
        async with self._condition:
            while True:
                event = next((item for item in self.events if item.sequence > sequence), None)
                if event is not None:
                    return event
                if self.done:
                    return None
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=timeout_seconds)
                except TimeoutError:
                    return None


class TalkStreamCoordinator:
    """Process-local fan-out around durable, idempotent model runs.

    The provider task owns its database session and survives a dropped browser
    stream. A reconnect with the same request ID receives buffered events; after
    process restart the kernel replays the durable completed model run.
    """

    def __init__(self) -> None:
        self._jobs: dict[tuple[uuid.UUID, uuid.UUID], TalkStreamJob] = {}
        self._lock = asyncio.Lock()

    async def start_or_get(self, owner_user_id: uuid.UUID, spec: TalkStreamSpec) -> TalkStreamJob:
        key = (owner_user_id, spec.request_id)
        async with self._lock:
            existing = self._jobs.get(key)
            if existing is not None:
                if existing.spec.fingerprint != spec.fingerprint:
                    raise TalkRunConflict("The request ID is already bound to a different Talk payload.")
                return existing
            job = TalkStreamJob(owner_user_id=owner_user_id, spec=spec)
            self._jobs[key] = job
            await job.publish(
                "stream.open",
                {"request_id": str(spec.request_id), "reconnectable": True},
            )
            job.task = asyncio.create_task(self._run(job), name=f"nur-talk-{spec.request_id}")
            return job

    async def cancel(self, owner_user_id: uuid.UUID, request_id: uuid.UUID) -> bool:
        async with self._lock:
            job = self._jobs.get((owner_user_id, request_id))
            if job is None or job.task is None or job.task.done():
                return False
            job.task.cancel()
            return True

    async def _run(self, job: TalkStreamJob) -> None:
        try:
            async with get_sessionmaker()() as db:
                await set_user_context(db, job.owner_user_id)
                try:
                    result = await run_talk_kernel(
                        db,
                        owner_user_id=job.owner_user_id,
                        user_line=job.spec.message,
                        orbit_id=job.spec.orbit_id,
                        locale=job.spec.locale,
                        writing_preference=job.spec.writing_preference,
                        memory_mode=job.spec.memory_mode,
                        requested_mode=job.spec.mode,
                        requested_capability_id=job.spec.capability_id,
                        request_id=job.spec.request_id,
                        event_sink=job.publish,
                    )
                    await db.commit()
                    await job.publish(
                        "talk.completed",
                        {
                            "request_id": str(job.spec.request_id),
                            "durable": True,
                            "result": result.model_dump(mode="json"),
                        },
                    )
                except asyncio.CancelledError:
                    with contextlib.suppress(Exception):
                        await job.publish(
                            "talk.cancelled",
                            {"request_id": str(job.spec.request_id), "durable": True},
                        )
                    raise
                except TalkProviderFailure as exc:
                    await db.commit()
                    await job.publish(
                        "talk.error",
                        {
                            "request_id": str(job.spec.request_id),
                            "model_run_id": str(exc.model_run_id),
                            "code": exc.code,
                            "message": exc.public_message,
                            "retryable": exc.retryable,
                            "durable": True,
                        },
                    )
                except TalkRunCancelled as exc:
                    await db.rollback()
                    await job.publish(
                        "talk.cancelled",
                        {
                            "request_id": str(job.spec.request_id),
                            "model_run_id": str(exc.model_run_id),
                            "durable": True,
                        },
                    )
                except AIRequestBudgetExceeded as exc:
                    await db.rollback()
                    await job.publish(
                        "talk.error",
                        {
                            "request_id": str(job.spec.request_id),
                            "code": exc.code,
                            "message": exc.public_message,
                            "retryable": exc.retryable,
                            "durable": False,
                        },
                    )
                except TalkRunConflict as exc:
                    await db.rollback()
                    await job.publish(
                        "talk.conflict",
                        {"request_id": str(job.spec.request_id), "detail": str(exc)},
                    )
                except Exception:
                    await db.rollback()
                    await job.publish(
                        "talk.error",
                        {
                            "request_id": str(job.spec.request_id),
                            "detail": "The Talk run failed closed before a durable response was available.",
                        },
                    )
        finally:
            await job.finish()
            asyncio.create_task(self._expire(job), name=f"nur-talk-expire-{job.spec.request_id}")

    async def _expire(self, job: TalkStreamJob) -> None:
        await asyncio.sleep(600)
        key = (job.owner_user_id, job.spec.request_id)
        async with self._lock:
            if self._jobs.get(key) is job:
                self._jobs.pop(key, None)


talk_stream_coordinator = TalkStreamCoordinator()
