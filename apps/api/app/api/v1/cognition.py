"""Cognition routes (mandate E1): the event ledger + the honest cycle, plus
journal/plans/research content routes the F-slice pages persist through."""
import datetime as dt
import json
import uuid
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select

from app.api.deps import Identity, Scoped, require_csrf
from app.ai.schemas import NURTalkOutput
from app.cognition.cycle import CycleResult, run_cognitive_cycle
from app.cognition.correction_service import (
    CorrectionTargetNotFound,
    persist_user_correction,
)
from app.ai.errors import AIRequestBudgetExceeded
from app.cognition.intelligence_kernel import TalkProviderFailure, TalkRunConflict, run_talk_kernel
from app.cognition.schemas import EvidencePacket, VerificationResult
from app.cognition.streaming import TalkStreamEnvelope, TalkStreamSpec, talk_stream_coordinator
from app.models import (
    CognitiveEvent,
    Decision,
    JournalEntry,
    ModelEvaluation,
    ModelRun,
    ModelRunSource,
    Orbit,
    OrbitReference,
    OrbitSource,
    Plan,
    PlanStep,
    ResearchDraft,
)
from app.observability.metrics import record_counter
from app.omega.schemas import OmegaTalkSummary
from app.services.glow_service import award_glow_if_eligible, reverse_source_glow

router = APIRouter(prefix="/cognition", tags=["cognition"])
content = APIRouter(tags=["cognition-content"])


class EventIn(BaseModel):
    event_kind: str
    content_text: str | None = None
    structured_payload: dict = Field(default_factory=dict)
    orbit_id: uuid.UUID | None = None
    source_ref: str | None = None
    scope: str = "PRIVATE_ORBIT"
    run_cycle: bool = False


class EventOut(BaseModel):
    id: uuid.UUID
    event_kind: str
    content_text: str | None
    structured_payload: dict
    orbit_id: uuid.UUID | None
    scope: str
    parent_event_id: uuid.UUID | None
    created_at: dt.datetime
    model_config = {"from_attributes": True}


class EventWithCycle(BaseModel):
    event: EventOut
    cycle: dict | None


class TalkIn(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    orbit_id: uuid.UUID | None = None
    locale: str = "en"
    writing_preference: str = "default"
    mode: str | None = None
    capability_id: str | None = Field(
        default=None,
        max_length=128,
        pattern=r"^capability:[a-z0-9_]+$",
    )
    memory_mode: Literal["EPHEMERAL", "REVIEW"] = "EPHEMERAL"


class TalkStreamIn(TalkIn):
    request_id: uuid.UUID


class TalkTurnOut(BaseModel):
    turn_event_id: uuid.UUID
    response_event_id: uuid.UUID
    model_run_id: uuid.UUID
    provider: str
    provider_available: bool
    provider_reason: str | None
    output: NURTalkOutput
    evidence: EvidencePacket
    verification: VerificationResult
    omega: OmegaTalkSummary | None = None
    idempotent_replay: bool = False


class TalkThreadRow(BaseModel):
    id: uuid.UUID
    who: str
    text: str | None
    structured_payload: dict
    created_at: dt.datetime


class CorrectionIn(BaseModel):
    correction_text: str = Field(min_length=1, max_length=4000)
    target_event_id: uuid.UUID | None = None
    orbit_id: uuid.UUID | None = None
    reason: str | None = None


@router.post("/talk", response_model=TalkTurnOut, dependencies=[Depends(require_csrf)])
async def talk(payload: TalkIn, request: Request, db: Scoped, identity: Identity) -> TalkTurnOut:
    user_id, _ = identity
    try:
        result = await run_talk_kernel(
            db,
            owner_user_id=user_id,
            user_line=payload.message.strip(),
            orbit_id=payload.orbit_id,
            locale=payload.locale,
            writing_preference=payload.writing_preference,
            memory_mode=payload.memory_mode,
            requested_mode=payload.mode,
            requested_capability_id=payload.capability_id,
        )
    except PermissionError as exc:
        raise HTTPException(404, str(exc)) from exc
    except AIRequestBudgetExceeded as exc:
        record_counter(request, "nur_ai_budget_rejections_total")
        raise HTTPException(exc.http_status, {"code": exc.code, "message": exc.public_message}) from exc
    except TalkProviderFailure as exc:
        await db.commit()
        record_counter(request, "nur_model_runs_total", (("provider", exc.provider), ("status", "error")))
        record_counter(request, "nur_provider_errors_total", (("provider", exc.provider), ("code", exc.code)))
        raise HTTPException(
            exc.http_status,
            {
                "code": exc.code,
                "message": exc.public_message,
                "model_run_id": str(exc.model_run_id),
                "retryable": exc.retryable,
            },
        ) from exc
    mode = payload.mode or "talk"
    record_counter(request, "nur_talk_turns_total", (("mode", mode),))
    record_counter(request, "nur_model_runs_total", (("provider", result.provider), ("status", "available" if result.provider_available else "unavailable")))
    if not result.provider_available:
        record_counter(request, "nur_provider_errors_total", (("provider", result.provider),))
    if result.verification.verdict == "BLOCK":
        record_counter(request, "nur_verification_blocked_total")
    record_counter(request, "nur_retrieval_snippets_total", (("mode", mode),), len(result.evidence.retrieval))
    await db.commit()
    return TalkTurnOut.model_validate(result.model_dump())


def _sse(envelope: TalkStreamEnvelope) -> str:
    data = json.dumps(envelope.data, ensure_ascii=False, separators=(",", ":"))
    return f"id: {envelope.sequence}\nevent: {envelope.event}\ndata: {data}\n\n"


@router.post("/talk/stream", dependencies=[Depends(require_csrf)])
async def talk_stream(payload: TalkStreamIn, request: Request, identity: Identity) -> StreamingResponse:
    user_id, _ = identity
    spec = TalkStreamSpec(
        request_id=payload.request_id,
        message=payload.message.strip(),
        orbit_id=payload.orbit_id,
        locale=payload.locale,
        writing_preference=payload.writing_preference,
        memory_mode=payload.memory_mode,
        mode=payload.mode,
        capability_id=payload.capability_id,
    )
    try:
        job = await talk_stream_coordinator.start_or_get(user_id, spec)
    except TalkRunConflict as exc:
        raise HTTPException(409, str(exc)) from exc

    raw_last = request.headers.get("last-event-id", "0")
    try:
        last_sequence = max(0, int(raw_last))
    except ValueError:
        raise HTTPException(400, "Last-Event-ID must be an integer.") from None

    async def events():
        sequence = last_sequence
        while True:
            envelope = await job.next_after(sequence)
            if envelope is not None:
                sequence = envelope.sequence
                yield _sse(envelope)
                continue
            if job.done:
                break
            yield ": keepalive\n\n"

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.get("/talk-runs/{request_id}")
async def talk_run_status(request_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    user_id, _ = identity
    row = (
        await db.execute(
            select(ModelRun).where(
                ModelRun.owner_user_id == user_id,
                ModelRun.request_id == request_id,
            )
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Talk run not found.")
    source_count = (
        await db.execute(
            select(func.count(ModelRunSource.id)).where(
                ModelRunSource.owner_user_id == user_id,
                ModelRunSource.model_run_id == row.id,
            )
        )
    ).scalar_one()
    evaluation = (
        await db.execute(
            select(ModelEvaluation)
            .where(
                ModelEvaluation.owner_user_id == user_id,
                ModelEvaluation.model_run_id == row.id,
            )
            .order_by(ModelEvaluation.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    return {
        "request_id": str(request_id),
        "model_run_id": str(row.id),
        "status": row.status,
        "input_event_id": str(row.input_event_id) if row.input_event_id else None,
        "response_event_id": str(row.output_event_id) if row.output_event_id else None,
        "provider": row.provider,
        "model": row.model,
        "available": bool((row.response_metadata or {}).get("available")),
        "provider_response_id_present": bool((row.response_metadata or {}).get("raw_response_id")),
        "usage_recorded": bool(row.usage),
        "failure_code": (row.error or {}).get("code"),
        "retryable": bool((row.error or {}).get("retryable")),
        "evidence_digest": (row.run_metadata or {}).get("evidence_digest"),
        "evidence_source_count": source_count,
        "verification_verdict": evaluation.verdict if evaluation else None,
        "schema_valid": row.status == "COMPLETED" and row.output_event_id is not None and evaluation is not None,
    }


@router.post("/talk-runs/{request_id}/cancel", status_code=202, dependencies=[Depends(require_csrf)])
async def cancel_talk_run(request_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    user_id, _ = identity
    cancelled = await talk_stream_coordinator.cancel(user_id, request_id)
    if not cancelled:
        row = (
            await db.execute(
                select(ModelRun).where(
                    ModelRun.owner_user_id == user_id,
                    ModelRun.request_id == request_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise HTTPException(404, "Talk run not found.")
        cancelled = row.status == "CANCELLED"
    return {"request_id": str(request_id), "cancel_requested": cancelled}


@router.get("/talk-thread", response_model=list[TalkThreadRow])
async def talk_thread(db: Scoped, identity: Identity, orbit_id: uuid.UUID | None = None, limit: int = 80) -> list[TalkThreadRow]:
    user_id, _ = identity
    # Ordering ascending and then limiting returns the OLDEST turns, so once a
    # thread passed the limit the owner could never see recent messages — the
    # transcript silently froze at the beginning of the conversation. Take the
    # most recent rows, then restore chronological order for display.
    q = (
        select(CognitiveEvent)
        .where(
            CognitiveEvent.owner_user_id == user_id,
            or_(CognitiveEvent.event_kind == "TALK_TURN", CognitiveEvent.event_kind == "MODEL_RESPONSE"),
        )
        .order_by(CognitiveEvent.created_at.desc())
        .limit(min(limit, 200))
    )
    if orbit_id:
        q = q.where(CognitiveEvent.orbit_id == orbit_id)
    rows = list(reversed((await db.execute(q)).scalars().all()))
    return [
        TalkThreadRow(
            id=e.id,
            who="nur" if e.event_kind == "MODEL_RESPONSE" else "user",
            text=e.content_text,
            structured_payload=e.structured_payload,
            created_at=e.created_at,
        )
        for e in rows
    ]


@router.post("/corrections", status_code=201, dependencies=[Depends(require_csrf)])
async def correct(payload: CorrectionIn, request: Request, db: Scoped, identity: Identity) -> dict:
    user_id, _ = identity
    try:
        row = await persist_user_correction(
            db,
            owner_user_id=user_id,
            orbit_id=payload.orbit_id,
            target_event_id=payload.target_event_id,
            correction_text=payload.correction_text,
            reason=payload.reason,
        )
    except CorrectionTargetNotFound as exc:
        raise HTTPException(404, str(exc)) from exc
    record_counter(request, "nur_corrections_total")
    await db.commit()
    return {"id": str(row.id)}


@router.post("/events", response_model=EventWithCycle, status_code=201, dependencies=[Depends(require_csrf)])
async def create_event(payload: EventIn, db: Scoped, identity: Identity) -> EventWithCycle:
    user_id, _ = identity
    ev = CognitiveEvent(
        owner_user_id=user_id, event_kind=payload.event_kind, content_text=payload.content_text,
        structured_payload=payload.structured_payload, orbit_id=payload.orbit_id,
        source_ref=payload.source_ref, scope=payload.scope,
    )
    db.add(ev)
    await db.flush()
    cycle: CycleResult | None = None
    if payload.run_cycle or payload.event_kind == "TALK_TURN":
        cycle = await run_cognitive_cycle(db, owner_user_id=user_id, trigger_event_id=ev.id)
    await db.commit()
    return EventWithCycle(event=EventOut.model_validate(ev), cycle=cycle.__dict__ if cycle else None)


@router.get("/events", response_model=list[EventOut])
async def list_events(db: Scoped, identity: Identity, kind: str | None = None, orbit_id: uuid.UUID | None = None, limit: int = 50) -> list[EventOut]:
    user_id, _ = identity
    q = select(CognitiveEvent).where(CognitiveEvent.owner_user_id == user_id).order_by(CognitiveEvent.created_at.desc()).limit(min(limit, 200))
    if kind:
        q = q.where(CognitiveEvent.event_kind == kind)
    if orbit_id:
        q = q.where(CognitiveEvent.orbit_id == orbit_id)
    return [EventOut.model_validate(e) for e in (await db.execute(q)).scalars()]


@router.get("/events/{event_id}", response_model=EventOut)
async def get_event(event_id: uuid.UUID, db: Scoped, identity: Identity) -> EventOut:
    user_id, _ = identity
    ev = (await db.execute(select(CognitiveEvent).where(CognitiveEvent.id == event_id, CognitiveEvent.owner_user_id == user_id))).scalar_one_or_none()
    if not ev:
        raise HTTPException(404, "Event not found.")
    return EventOut.model_validate(ev)


# ------------------------------- journal ---------------------------------
class JournalIn(BaseModel):
    body: str
    orbit_id: uuid.UUID | None = None


class JournalOut(BaseModel):
    id: uuid.UUID
    body: str
    orbit_id: uuid.UUID | None
    event_id: uuid.UUID | None
    created_at: dt.datetime
    model_config = {"from_attributes": True}


@content.post("/journal", response_model=JournalOut, status_code=201, dependencies=[Depends(require_csrf)])
async def keep_entry(payload: JournalIn, db: Scoped, identity: Identity) -> JournalOut:
    user_id, _ = identity
    ev = CognitiveEvent(owner_user_id=user_id, orbit_id=payload.orbit_id, event_kind="JOURNAL_ENTRY",
                        content_text=payload.body, source_ref="journal")
    db.add(ev)
    await db.flush()
    row = JournalEntry(owner_user_id=user_id, orbit_id=payload.orbit_id, body=payload.body, event_id=ev.id)
    db.add(row)
    await db.flush()
    await award_glow_if_eligible(
        db,
        owner_user_id=user_id,
        event_type="journal_saved",
        source_kind="JOURNAL_ENTRY",
        source_id=row.id,
        orbit_id=payload.orbit_id,
        idempotency_key=f"journal:{row.id}:saved",
    )
    await db.commit()
    return JournalOut.model_validate(row)


@content.get("/journal", response_model=list[JournalOut])
async def list_entries(db: Scoped, identity: Identity, limit: int = 50) -> list[JournalOut]:
    user_id, _ = identity
    rows = (await db.execute(select(JournalEntry).where(JournalEntry.owner_user_id == user_id).order_by(JournalEntry.created_at.desc()).limit(min(limit, 200)))).scalars()
    return [JournalOut.model_validate(r) for r in rows]


class ConvertIn(BaseModel):
    orbit_id: uuid.UUID | None = None
    kind: str = "REFERENCE"
    title: str | None = None
    inclusion_mode: str = "FULL"


class ConvertOut(BaseModel):
    source_kind: str
    source_id: uuid.UUID
    target_kind: str
    target_id: uuid.UUID
    orbit_id: uuid.UUID
    orbit_source_id: uuid.UUID


async def _owned_orbit_for_convert(db: Scoped, user_id: uuid.UUID, orbit_id: uuid.UUID | None) -> Orbit:
    stmt = select(Orbit).where(Orbit.owner_user_id == user_id)
    if orbit_id is not None:
        stmt = stmt.where(Orbit.id == orbit_id)
    else:
        stmt = stmt.where(Orbit.kind != "PERSONAL_BRIDGE", Orbit.status == "ACTIVE").order_by(Orbit.created_at.asc())
    orbit = (await db.execute(stmt.limit(1))).scalar_one_or_none()
    if not orbit:
        raise HTTPException(404, "Orbit not found.")
    return orbit


def _normalize_convert_kind(kind: str) -> str:
    k = kind.upper().strip()
    if k not in {"DECISION", "REFERENCE", "CONSTRAINT", "OPEN_QUESTION"}:
        raise HTTPException(422, "kind must be DECISION, REFERENCE, CONSTRAINT, or OPEN_QUESTION.")
    return k


@content.post("/journal/{entry_id}/convert", response_model=ConvertOut, dependencies=[Depends(require_csrf)])
async def convert_journal(entry_id: uuid.UUID, payload: ConvertIn, db: Scoped, identity: Identity) -> ConvertOut:
    user_id, _ = identity
    entry = (await db.execute(select(JournalEntry).where(
        JournalEntry.id == entry_id,
        JournalEntry.owner_user_id == user_id,
    ))).scalar_one_or_none()
    if not entry:
        raise HTTPException(404, "Journal entry not found.")
    orbit = await _owned_orbit_for_convert(db, user_id, payload.orbit_id or entry.orbit_id)
    kind = _normalize_convert_kind(payload.kind)
    if kind == "DECISION":
        target = Decision(
            owner_user_id=user_id,
            orbit_id=orbit.id,
            statement=payload.title or entry.body[:160],
            rationale=entry.body,
        )
        target_source_kind = "DECISION"
    else:
        target = OrbitReference(
            owner_user_id=user_id,
            orbit_id=orbit.id,
            kind=kind,
            title=payload.title or entry.body[:160],
            body=entry.body,
        )
        target_source_kind = "REFERENCE"
    db.add(target)
    await db.flush()
    source = OrbitSource(
        orbit_id=orbit.id,
        owner_user_id=user_id,
        source_kind=target_source_kind,
        source_id=target.id,
        inclusion_mode=payload.inclusion_mode,
    )
    db.add(source)
    db.add(CognitiveEvent(
        owner_user_id=user_id,
        orbit_id=orbit.id,
        event_kind="SYSTEM_EVENT",
        content_text=f"Journal converted to {kind.lower()}: {payload.title or entry.body[:120]}",
        source_ref=f"journal:{entry.id}",
        structured_payload={"source": "journal_convert", "target_kind": kind, "target_id": str(target.id)},
    ))
    await db.commit()
    return ConvertOut(
        source_kind="JOURNAL_ENTRY",
        source_id=entry.id,
        target_kind=kind,
        target_id=target.id,
        orbit_id=orbit.id,
        orbit_source_id=source.id,
    )


# --------------------------------- plans ---------------------------------
class StepIn(BaseModel):
    title: str
    body: str | None = None
    position: int = 0


class StepOut(StepIn):
    id: uuid.UUID
    done: bool
    done_at: dt.datetime | None
    experiment_id: uuid.UUID | None
    model_config = {"from_attributes": True}


class PlanIn(BaseModel):
    title: str
    orbit_id: uuid.UUID | None = None
    steps: list[StepIn] = Field(default_factory=list)


class PlanOut(BaseModel):
    id: uuid.UUID
    title: str
    status: str
    orbit_id: uuid.UUID | None
    steps: list[StepOut]
    model_config = {"from_attributes": True}


async def _plan_out(db: Scoped, plan: Plan) -> PlanOut:
    steps = (await db.execute(select(PlanStep).where(PlanStep.plan_id == plan.id).order_by(PlanStep.position))).scalars()
    return PlanOut(id=plan.id, title=plan.title, status=plan.status, orbit_id=plan.orbit_id,
                   steps=[StepOut.model_validate(s) for s in steps])


@content.post("/plans", response_model=PlanOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_plan(payload: PlanIn, db: Scoped, identity: Identity) -> PlanOut:
    user_id, _ = identity
    plan = Plan(owner_user_id=user_id, title=payload.title, orbit_id=payload.orbit_id)
    db.add(plan)
    await db.flush()
    for i, s in enumerate(payload.steps):
        db.add(PlanStep(owner_user_id=user_id, plan_id=plan.id, title=s.title, body=s.body, position=s.position or i))
    db.add(CognitiveEvent(owner_user_id=user_id, orbit_id=payload.orbit_id, event_kind="PLAN_CREATED",
                          content_text=payload.title, source_ref=f"plan:{plan.id}"))
    await db.flush()
    await award_glow_if_eligible(
        db,
        owner_user_id=user_id,
        event_type="plan_created",
        source_kind="PLAN",
        source_id=plan.id,
        orbit_id=payload.orbit_id,
        idempotency_key=f"plan:{plan.id}:created",
    )
    out = await _plan_out(db, plan)   # read inside the armed transaction
    await db.commit()
    return out


@content.get("/plans", response_model=list[PlanOut])
async def list_plans(db: Scoped, identity: Identity) -> list[PlanOut]:
    user_id, _ = identity
    plans = (await db.execute(select(Plan).where(Plan.owner_user_id == user_id).order_by(Plan.created_at.desc()).limit(20))).scalars().all()
    return [await _plan_out(db, p) for p in plans]


@content.post("/plans/{plan_id}/steps", response_model=StepOut, status_code=201, dependencies=[Depends(require_csrf)])
async def add_step(plan_id: uuid.UUID, payload: StepIn, db: Scoped, identity: Identity) -> StepOut:
    user_id, _ = identity
    plan = (await db.execute(select(Plan).where(Plan.id == plan_id, Plan.owner_user_id == user_id))).scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found.")
    step = PlanStep(owner_user_id=user_id, plan_id=plan.id, title=payload.title, body=payload.body, position=payload.position)
    db.add(step)
    await db.commit()
    return StepOut.model_validate(step)


class StepPatch(BaseModel):
    done: bool | None = None
    title: str | None = None


@content.patch("/plan-steps/{step_id}", response_model=StepOut, dependencies=[Depends(require_csrf)])
async def patch_step(step_id: uuid.UUID, payload: StepPatch, db: Scoped, identity: Identity) -> StepOut:
    user_id, _ = identity
    step = (await db.execute(select(PlanStep).where(PlanStep.id == step_id, PlanStep.owner_user_id == user_id))).scalar_one_or_none()
    if not step:
        raise HTTPException(404, "Step not found.")
    was_done = step.done
    if payload.title is not None:
        step.title = payload.title
    if payload.done is not None:
        step.done = payload.done
        step.done_at = dt.datetime.now(dt.timezone.utc) if payload.done else None
        db.add(CognitiveEvent(owner_user_id=user_id, event_kind="PLAN_STEP",
                              content_text=("done: " if payload.done else "reopened: ") + step.title,
                              source_ref=f"plan_step:{step.id}"))
        await db.flush()
        if payload.done:
            await award_glow_if_eligible(
                db,
                owner_user_id=user_id,
                event_type="plan_step_completed",
                source_kind="PLAN_STEP",
                source_id=step.id,
                orbit_id=None,
                idempotency_key=f"plan-step:{step.id}:completed",
            )
        elif was_done:
            await reverse_source_glow(
                db,
                owner_user_id=user_id,
                event_type="plan_step_completed",
                source_kind="PLAN_STEP",
                source_id=step.id,
                reason="The owner reopened the completed Plan step.",
            )
    await db.commit()
    return StepOut.model_validate(step)


# ----------------------------- research drafts ---------------------------
class ResearchIn(BaseModel):
    question: str
    notes: str | None = None
    orbit_id: uuid.UUID | None = None


class ResearchOut(ResearchIn):
    id: uuid.UUID
    status: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


@content.post("/research-drafts", response_model=ResearchOut, status_code=201, dependencies=[Depends(require_csrf)])
async def stage_research(payload: ResearchIn, db: Scoped, identity: Identity) -> ResearchOut:
    user_id, _ = identity
    row = ResearchDraft(owner_user_id=user_id, question=payload.question, notes=payload.notes, orbit_id=payload.orbit_id)
    db.add(row)
    db.add(CognitiveEvent(owner_user_id=user_id, orbit_id=payload.orbit_id, event_kind="RESEARCH_DRAFT",
                          content_text=payload.question, source_ref="research"))
    await db.commit()
    return ResearchOut.model_validate(row)


@content.get("/research-drafts", response_model=list[ResearchOut])
async def list_research(db: Scoped, identity: Identity) -> list[ResearchOut]:
    user_id, _ = identity
    rows = (await db.execute(select(ResearchDraft).where(ResearchDraft.owner_user_id == user_id).order_by(ResearchDraft.created_at.desc()).limit(50))).scalars()
    return [ResearchOut.model_validate(r) for r in rows]


@content.post("/research-drafts/{draft_id}/convert", response_model=ConvertOut, dependencies=[Depends(require_csrf)])
async def convert_research(draft_id: uuid.UUID, payload: ConvertIn, db: Scoped, identity: Identity) -> ConvertOut:
    user_id, _ = identity
    draft = (await db.execute(select(ResearchDraft).where(
        ResearchDraft.id == draft_id,
        ResearchDraft.owner_user_id == user_id,
    ))).scalar_one_or_none()
    if not draft:
        raise HTTPException(404, "Research draft not found.")
    orbit = await _owned_orbit_for_convert(db, user_id, payload.orbit_id or draft.orbit_id)
    kind = _normalize_convert_kind(payload.kind)
    if kind == "DECISION":
        target = Decision(
            owner_user_id=user_id,
            orbit_id=orbit.id,
            statement=payload.title or draft.question,
            rationale=draft.notes,
        )
        target_source_kind = "DECISION"
    else:
        ref_kind = "OPEN_QUESTION" if kind == "REFERENCE" else kind
        target = OrbitReference(
            owner_user_id=user_id,
            orbit_id=orbit.id,
            kind=ref_kind,
            title=payload.title or draft.question,
            body=draft.notes,
        )
        target_source_kind = "REFERENCE"
    db.add(target)
    draft.status = "CONVERTED"
    await db.flush()
    source = OrbitSource(
        orbit_id=orbit.id,
        owner_user_id=user_id,
        source_kind=target_source_kind,
        source_id=target.id,
        inclusion_mode=payload.inclusion_mode,
    )
    db.add(source)
    db.add(CognitiveEvent(
        owner_user_id=user_id,
        orbit_id=orbit.id,
        event_kind="SYSTEM_EVENT",
        content_text=f"Research draft converted to {kind.lower()}: {draft.question}",
        source_ref=f"research:{draft.id}",
        structured_payload={"source": "research_convert", "target_kind": kind, "target_id": str(target.id)},
    ))
    await db.commit()
    return ConvertOut(
        source_kind="RESEARCH_DRAFT",
        source_id=draft.id,
        target_kind=kind,
        target_id=target.id,
        orbit_id=orbit.id,
        orbit_source_id=source.id,
    )
