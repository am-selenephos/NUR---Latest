from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.provider import get_ai_provider
from app.ai.schemas import AIStreamSink, EvidenceRef, NURTalkOutput
from app.cognition.schemas import EvidencePacket, TalkKernelResult, VerificationResult
from app.mind.cognitive_loop import run_mind_cognitive_loop
from app.models import CognitiveEvent, ModelRun, ModelRunSource
from app.omega.schemas import OmegaTalkSummary

__all__ = [
    "get_ai_provider",
    "run_talk_kernel",
    "TalkProviderFailure",
    "TalkRunCancelled",
    "TalkRunConflict",
]


async def run_talk_kernel(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    user_line: str,
    orbit_id: uuid.UUID | None,
    locale: str,
    writing_preference: str = "default",
    memory_mode: str = "EPHEMERAL",
    requested_mode: str | None = None,
    request_id: uuid.UUID | None = None,
    event_sink: AIStreamSink | None = None,
) -> TalkKernelResult:
    if request_id is not None:
        existing = (
            await db.execute(
                select(ModelRun).where(
                    ModelRun.owner_user_id == owner_user_id,
                    ModelRun.request_id == request_id,
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            if existing.output_event_id is None:
                if existing.status == "ERROR":
                    raise TalkProviderFailure.from_model_run(existing)
                if existing.status == "CANCELLED":
                    raise TalkRunCancelled(existing.id)
                raise TalkRunConflict(f"Talk request {request_id} is already {existing.status.lower()}.")
            replay = await _replay_talk_result(db, existing)
            if event_sink is not None:
                await event_sink(
                    "talk.replayed",
                    {
                        "request_id": str(request_id),
                        "model_run_id": str(replay.model_run_id),
                        "response_event_id": str(replay.response_event_id),
                    },
                )
            return replay

    return await run_mind_cognitive_loop(
        db,
        owner_user_id=owner_user_id,
        user_line=user_line,
        orbit_id=orbit_id,
        locale=locale,
        writing_preference=writing_preference,
        memory_mode=memory_mode,
        requested_mode=requested_mode,
        request_id=request_id,
        event_sink=event_sink,
    )


class TalkRunConflict(RuntimeError):
    pass


class TalkRunCancelled(RuntimeError):
    def __init__(self, model_run_id: uuid.UUID):
        super().__init__("The Talk run was cancelled by its owner.")
        self.model_run_id = model_run_id


class TalkProviderFailure(RuntimeError):
    def __init__(
        self,
        *,
        model_run_id: uuid.UUID,
        provider: str,
        code: str,
        public_message: str,
        http_status: int,
        retryable: bool,
    ) -> None:
        super().__init__(public_message)
        self.model_run_id = model_run_id
        self.provider = provider
        self.code = code
        self.public_message = public_message
        self.http_status = http_status
        self.retryable = retryable

    @classmethod
    def from_model_run(cls, model_run: ModelRun) -> "TalkProviderFailure":
        error = model_run.error or {}
        return cls(
            model_run_id=model_run.id,
            provider=model_run.provider,
            code=str(error.get("code") or "provider_error"),
            public_message=str(error.get("public_message") or "Live AI could not complete this request."),
            http_status=int(error.get("http_status") or 503),
            retryable=bool(error.get("retryable")),
        )


async def _replay_talk_result(db: AsyncSession, model_run: ModelRun) -> TalkKernelResult:
    if model_run.input_event_id is None or model_run.output_event_id is None:
        raise TalkRunConflict("The existing Talk request has no durable completed response.")
    response_event = (
        await db.execute(
            select(CognitiveEvent).where(
                CognitiveEvent.owner_user_id == model_run.owner_user_id,
                CognitiveEvent.id == model_run.output_event_id,
            )
        )
    ).scalar_one_or_none()
    if response_event is None:
        raise TalkRunConflict("The existing Talk response is no longer available.")
    sources = (
        await db.execute(
            select(ModelRunSource)
            .where(
                ModelRunSource.owner_user_id == model_run.owner_user_id,
                ModelRunSource.model_run_id == model_run.id,
            )
            .order_by(ModelRunSource.rank.desc(), ModelRunSource.created_at.asc())
        )
    ).scalars().all()
    payload = response_event.structured_payload or {}
    output = NURTalkOutput.model_validate(payload.get("talk_output") or {})
    verification = VerificationResult.model_validate(payload.get("verification") or {"verdict": "WARN", "checks": {}})
    omega_payload = payload.get("omega")
    omega = OmegaTalkSummary.model_validate(omega_payload) if omega_payload else None
    evidence = EvidencePacket(
        orbit_id=model_run.orbit_id,
        retrieval=[
            EvidenceRef(
                kind=row.source_kind,
                id=str(row.source_id or row.id),
                excerpt=row.excerpt or "",
                rank=row.rank,
            )
            for row in sources
        ],
    )
    return TalkKernelResult(
        turn_event_id=model_run.input_event_id,
        response_event_id=model_run.output_event_id,
        model_run_id=model_run.id,
        provider=str(payload.get("provider") or model_run.provider),
        provider_available=bool(payload.get("provider_available")),
        provider_reason=payload.get("provider_reason"),
        output=output,
        evidence=evidence,
        verification=verification,
        omega=omega,
        idempotent_replay=True,
    )


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
        return True
    except ValueError:
        return False
