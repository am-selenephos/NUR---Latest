"""NUR Mind Cognitive Loop — 22-step cognitive loop orchestrator.

Integrates Mind plane continuity and Brain plane provider cognition above the existing
Agency Spine and database RLS model.
"""
from __future__ import annotations

import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.audit import model_run_metadata, safe_error_metadata
from app.ai.budget import assert_daily_ai_budget
from app.ai.errors import AIOutputValidationError, AIProviderDisabled
from app.ai.schemas import AIProviderResult, AIStreamSink, EvidenceRef, TalkProviderRequest
from app.brain.cognition import run_brain_step
from app.brain.schemas import CognitiveResult
from app.brain.synthesizer import synthesize_talk_output
from app.cognition.evaluation_service import persist_model_evaluation
from app.cognition.evidence_packet import build_evidence_packet
from app.cognition.hybrid_retrieval import retrieve_hybrid
from app.cognition.memory_candidate_service import persist_memory_candidates
from app.cognition.prediction_service import persist_predictions
from app.cognition.retrieval_policy import assert_owned_orbit
from app.cognition.schemas import EvidencePacket, TalkKernelResult, VerificationResult
from app.cognition.verifier import verify_talk_output
from app.core.config import get_settings
from app.mind.context import build_cognitive_task_packet
from app.mind.metacognition import run_metacognitive_review
from app.models import CognitiveEvent, ModelRun, ModelRunSource
from app.omega.schemas import OmegaTalkSummary
from app.omega.workspace_service import build_workspace_frame, mark_frame_used, talk_summary
from app.services.glow_service import award_glow_if_eligible


async def run_mind_cognitive_loop(
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
    """Execute the full 22-step Mind + Brain cognitive loop."""

    # 1. Assert owner orbit & privacy boundary
    await assert_owned_orbit(db, owner_user_id=owner_user_id, orbit_id=orbit_id)
    await assert_daily_ai_budget(db, owner_user_id=owner_user_id)

    task_class = requested_mode or "talk"

    # 2. Persist turn event
    turn = CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_kind="TALK_TURN",
        content_text=user_line,
        structured_payload={
            "mode": task_class,
            "locale": locale,
            "writing_preference": writing_preference,
            "memory_mode": memory_mode,
        },
        source_ref="talk",
    )
    db.add(turn)
    await db.flush()

    # 3. Build workspace frame
    frame = await build_workspace_frame(
        db,
        owner_user_id=owner_user_id,
        task_mode=task_class,
        active_question=user_line,
        orbit_id=orbit_id,
        trigger_event_id=turn.id,
    )

    # 4. Scoped hybrid retrieval
    retrieval = await retrieve_hybrid(
        db,
        owner_user_id=owner_user_id,
        query=user_line,
        orbit_id=orbit_id,
        limit=6,
    )
    evidence = build_evidence_packet(orbit_id=orbit_id, retrieval=retrieval)
    retrieval_dicts = [r.model_dump() for r in retrieval]

    # 5. Assemble CognitiveTaskPacket (Mind context)
    packet = await build_cognitive_task_packet(
        db,
        owner_user_id=owner_user_id,
        user_input=user_line,
        task_class=task_class,
        orbit_id=orbit_id,
        locale=locale,
        writing_preference=writing_preference,
        retrieved_refs=retrieval_dicts,
        workspace_frame=frame,
    )

    # 6. Initialize ModelRun trace record
    s = get_settings()
    evidence_payload = evidence.model_dump(mode="json")
    evidence_digest = hashlib.sha256(
        json.dumps(evidence_payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    run_metadata = model_run_metadata(
        provider=s.ai_provider,
        model=s.openai_model or None,
        mode=task_class,
        locale=locale,
        prompt_logging=s.ai_log_prompts,
    )
    run_metadata["task_packet_id"] = str(packet.task_id)
    run_metadata["identity_version"] = packet.identity.version
    run_metadata["evidence_digest"] = evidence_digest

    model_run = ModelRun(
        owner_user_id=owner_user_id,
        request_id=request_id,
        orbit_id=orbit_id,
        provider=s.ai_provider,
        model=s.openai_model or None,
        mode=task_class,
        status="RUNNING",
        input_event_id=turn.id,
        run_metadata=run_metadata,
        response_metadata={"available": False, "reason": "Provider response pending."},
    )
    db.add(model_run)
    await db.flush()

    for ref in retrieval:
        db.add(
            ModelRunSource(
                owner_user_id=owner_user_id,
                model_run_id=model_run.id,
                source_kind=ref.kind,
                source_id=uuid.UUID(ref.id) if _is_uuid(ref.id) else None,
                excerpt=ref.excerpt,
                rank=ref.rank,
            )
        )

    if event_sink is not None:
        await event_sink(
            "talk.accepted",
            {
                "request_id": str(request_id) if request_id else None,
                "turn_event_id": str(turn.id),
                "model_run_id": str(model_run.id),
            },
        )

    # 7-8. Brain Cognition Step & Critic
    try:
        cognitive_result, brain_trace = await run_brain_step(packet, event_sink=event_sink)
    except AIProviderDisabled as exc:
        model_run.status = "ERROR"
        model_run.error = {"kind": "disabled", "detail": str(exc)}
        await db.flush()
        raise
    except Exception as exc:
        error = safe_error_metadata(exc)
        model_run.status = "ERROR"
        model_run.error = error
        await db.flush()
        raise

    # 9. Metacognitive review checkpoint
    metacog_review = run_metacognitive_review(packet, cognitive_result, depth=1)

    # 10. Synthesize owner-facing Talk output
    talk_output = synthesize_talk_output(cognitive_result)

    # 11. Verify Talk output
    verification = verify_talk_output(talk_output, evidence, provider_available=True)
    if metacog_review.verdict == "BLOCK" or verification.verdict == "BLOCK":
        raise AIOutputValidationError("Output failed Mind/Brain verification checkpoint.")

    # 12-15. Persistence & trace completion
    model_run.status = "COMPLETED"
    model_run.run_metadata.update(brain_trace.to_metadata())
    model_run.run_metadata["metacognitive_review"] = {
        "verdict": metacog_review.verdict,
        "summary": metacog_review.decision_summary,
    }
    model_run.response_metadata = {
        "available": True,
        "reason": None,
        "brain_profile": brain_trace.profile_key,
    }

    omega = await talk_summary(db, owner_user_id=owner_user_id, workspace_frame_id=frame.id)
    response_event = CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        event_kind="MODEL_RESPONSE",
        content_text=talk_output.direct_response,
        structured_payload={
            "talk_output": talk_output.model_dump(),
            "provider": s.ai_provider,
            "provider_available": True,
            "model_run_id": str(model_run.id),
            "memory_mode": memory_mode,
            "verification": verification.model_dump(),
            "metacognition": metacog_review.decision_summary,
            "omega": omega.model_dump(mode="json"),
        },
        source_ref=f"model_run:{model_run.id}",
        parent_event_id=turn.id,
    )
    db.add(response_event)
    await db.flush()
    model_run.output_event_id = response_event.id
    await mark_frame_used(db, frame)

    await persist_model_evaluation(db, owner_user_id=owner_user_id, model_run_id=model_run.id, verification=verification)

    if memory_mode == "REVIEW":
        await persist_memory_candidates(
            db,
            owner_user_id=owner_user_id,
            orbit_id=orbit_id,
            source_event_id=response_event.id,
            user_message_event_id=turn.id,
            model_run_id=model_run.id,
            request_id=request_id,
            evidence_digest=evidence_digest,
            evidence_sources=[{"kind": ref.kind, "id": ref.id, "rank": ref.rank} for ref in retrieval],
            output=talk_output,
        )

    await persist_predictions(
        db,
        owner_user_id=owner_user_id,
        orbit_id=orbit_id,
        source_event_id=response_event.id,
        output=talk_output,
    )

    if talk_output.next_move and verification.verdict in {"PASS", "WARN"}:
        await award_glow_if_eligible(
            db,
            owner_user_id=owner_user_id,
            event_type="talk_meaningful",
            source_kind="COGNITIVE_EVENT",
            source_id=turn.id,
            orbit_id=orbit_id,
            idempotency_key=f"talk-turn:{turn.id}:meaningful",
        )

    if event_sink is not None:
        await event_sink(
            "talk.validated",
            {
                "request_id": str(request_id) if request_id else None,
                "model_run_id": str(model_run.id),
                "response_event_id": str(response_event.id),
                "schema_valid": True,
                "verification_verdict": verification.verdict,
            },
        )

    return TalkKernelResult(
        turn_event_id=turn.id,
        response_event_id=response_event.id,
        model_run_id=model_run.id,
        provider=s.ai_provider,
        provider_available=True,
        provider_reason=None,
        output=talk_output,
        evidence=evidence,
        verification=verification,
        omega=omega,
        idempotent_replay=False,
    )


def _is_uuid(val: str) -> bool:
    try:
        uuid.UUID(val)
        return True
    except ValueError:
        return False
