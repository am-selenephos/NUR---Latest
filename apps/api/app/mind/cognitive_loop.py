"""NUR Mind Cognitive Loop — 22-step cognitive loop orchestrator.

Integrates Mind plane continuity and Brain plane provider cognition above the existing
Agency Spine and database RLS model.

Directive §8.1: scope resolution occurs before retrieval and before provider invocation.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.audit import model_run_metadata, safe_error_metadata
from app.ai.budget import assert_daily_ai_budget
from app.ai.errors import AIOutputValidationError
from app.ai.schemas import AIStreamSink
from app.brain.cognition import run_brain_step
from app.brain.synthesizer import synthesize_talk_output
from app.brain.tracing import BrainTrace
from app.cognition.evaluation_service import persist_model_evaluation
from app.cognition.evidence_packet import build_evidence_packet
from app.cognition.hybrid_retrieval import retrieve_hybrid
from app.cognition.memory_candidate_service import persist_memory_candidates
from app.cognition.prediction_service import persist_predictions
from app.cognition.schemas import TalkKernelResult
from app.cognition.verifier import verify_talk_output
from app.core.config import get_settings
from app.mind.capabilities.dispatcher import WorkerDispatcher
from app.mind.capabilities.hydrator import ContextHydrator
from app.mind.capabilities.resolver import CapabilityResolver, ResolutionFallbackMode
from app.mind.context import build_cognitive_task_packet
from app.mind.metacognition import run_metacognitive_review
from app.mind.scope import ScopeResolutionError, resolve_scope
from app.models import CognitiveEvent, ModelRun, ModelRunSource
from app.omega.workspace_service import build_workspace_frame, mark_frame_used, talk_summary
from app.services.glow_service import award_glow_if_eligible


async def run_mind_cognitive_loop(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    user_line: str,
    orbit_id: uuid.UUID | None = None,
    locale: str = "en",
    writing_preference: str = "default",
    memory_mode: str = "EPHEMERAL",
    requested_mode: str | None = None,
    request_id: uuid.UUID | None = None,
    event_sink: AIStreamSink | None = None,
) -> TalkKernelResult:
    """Execute the full 22-step Mind + Brain cognitive loop."""

    # 1. Resolve scope BEFORE retrieval (§8.1)
    task_class = requested_mode or "talk"
    try:
        scope_envelope = await resolve_scope(
            db,
            owner_user_id=owner_user_id,
            surface=task_class,
            orbit_id=orbit_id,
            memory_mode=memory_mode,
        )
    except ScopeResolutionError as exc:
        if event_sink is not None:
            await event_sink(
                "talk.failed",
                {
                    "request_id": str(request_id) if request_id else None,
                    "code": "scope_resolution_failed",
                    "retryable": False,
                    "reason": exc.reason,
                },
            )
        raise PermissionError(exc.reason) from exc

    if event_sink is not None:
        await event_sink(
            "talk.scope.resolved",
            {
                "request_id": str(request_id) if request_id else None,
                "scope_id": str(scope_envelope.scope_id),
                "sharing_boundary": scope_envelope.sharing_boundary,
            },
        )

    # 2. Assert daily AI budget
    await assert_daily_ai_budget(db, owner_user_id=owner_user_id)

    # 3. Persist turn event
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
            "scope_envelope_id": str(scope_envelope.scope_id),
        },
        source_ref="talk",
    )
    db.add(turn)
    await db.flush()

    # 3.1 Resolve capability & intent routing
    resolver = CapabilityResolver()
    resolution = resolver.resolve(
        user_line,
        surface=scope_envelope.surface,
        sensitivity=scope_envelope.sensitivity_ceiling,
        mode_hint=requested_mode,
    )

    if resolution.fallback_mode == ResolutionFallbackMode.REFUSE_SCOPE:
        if event_sink is not None:
            await event_sink(
                "talk.failed",
                {
                    "request_id": str(request_id) if request_id else None,
                    "code": "scope_refusal",
                    "retryable": False,
                    "reason": resolution.abstention_reason or "Prohibited scope operation.",
                },
            )
        raise PermissionError(resolution.abstention_reason or "Prohibited scope operation.")

    if event_sink is not None:
        await event_sink(
            "talk.capability.resolved",
            {
                "request_id": str(request_id) if request_id else None,
                "capability_id": resolution.selected_capability.capability_id if resolution.selected_capability else None,
                "confidence_score": resolution.confidence_score,
                "abstained": resolution.abstained,
                "reason": resolution.abstention_reason,
            },
        )

    # 4 & 5. Progressive Context Hydration (recipe-driven)
    if resolution.selected_capability is not None:
        hydrated_ctx = await ContextHydrator.hydrate(
            db,
            owner_user_id=owner_user_id,
            scope_envelope=scope_envelope,
            capability=resolution.selected_capability,
            query=user_line,
            orbit_id=orbit_id,
            trigger_event_id=turn.id,
        )
        frame = hydrated_ctx.workspace_frame or await build_workspace_frame(
            db,
            owner_user_id=owner_user_id,
            task_mode=task_class,
            active_question=user_line,
            orbit_id=orbit_id,
            trigger_event_id=turn.id,
        )
        retrieval_refs = hydrated_ctx.retrieval_refs
        retrieval_dicts = hydrated_ctx.retrieved_evidence
    else:
        hydrated_ctx = None
        frame = await build_workspace_frame(
            db,
            owner_user_id=owner_user_id,
            task_mode=task_class,
            active_question=user_line,
            orbit_id=orbit_id,
            trigger_event_id=turn.id,
        )
        retrieval_refs = await retrieve_hybrid(
            db,
            owner_user_id=owner_user_id,
            query=user_line,
            orbit_id=orbit_id,
            limit=6,
        )
        retrieval_dicts = [r.model_dump() for r in retrieval_refs]

    evidence = build_evidence_packet(orbit_id=orbit_id, retrieval=retrieval_refs)

    # 6. Assemble CognitiveTaskPacket (Mind context) — with scope envelope
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
        scope_envelope=scope_envelope,
    )

    # 7. Initialize ModelRun trace record
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
    run_metadata["scope_envelope_id"] = str(scope_envelope.scope_id)
    if resolution.selected_capability is not None:
        run_metadata["capability_id"] = resolution.selected_capability.capability_id

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

    for ref in retrieval_refs:
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

    # 8-12. Brain Cognition Step, Critic, Metacognition & Verification
    try:
        # Check if specialized capability worker handles execution
        worker_result = None
        if resolution.selected_capability is not None and hydrated_ctx is not None:
            worker_result = await WorkerDispatcher.dispatch(
                db,
                owner_user_id=owner_user_id,
                capability=resolution.selected_capability,
                hydrated_context=hydrated_ctx,
                query=user_line,
                task_id=packet.task_id,
                extracted_parameters=resolution.extracted_parameters,
            )

        is_deterministic_worker = worker_result is not None
        if worker_result is not None:
            cognitive_result = worker_result
            model_run.provider = "DETERMINISTIC_WORKER"
            model_run.model = None
            brain_trace = BrainTrace(
                brain_run_id=uuid.uuid4(),
                task_id=packet.task_id,
                model_run_id=model_run.id,
                request_id=request_id,
                scope_envelope_id=scope_envelope.scope_id,
                turn_event_id=turn.id,
                cognitive_task_id=packet.task_id,
                profile_key=str(worker_result.profile_used.value),
                route_reason=worker_result.decision_summary,
            )
        else:
            cognitive_result, brain_trace = await run_brain_step(packet, event_sink=event_sink)

        # If the CognitiveResult contains a workflow proposal, submit to Agency
        agency_refusal_reasons: list[str] | None = None
        if cognitive_result.workflow_proposal is not None:
            from app.mind.agency_bridge import submit_workflow_proposal
            workflow, compile_res = await submit_workflow_proposal(
                db,
                owner_user_id=owner_user_id,
                proposal=cognitive_result.workflow_proposal,
                orbit_id=orbit_id,
            )
            if workflow is not None and event_sink is not None:
                await event_sink(
                    "workflow.proposed",
                    {
                        "workflow_id": str(workflow.id),
                        "state": workflow.state,
                        "requires_approval": workflow.state == "BLOCKED_ON_APPROVAL",
                    },
                )
            elif workflow is None:
                agency_refusal_reasons = (
                    [err.message for err in compile_res.errors]
                    if compile_res.errors
                    else ["Agency compiler refused workflow proposal."]
                )
                if event_sink is not None:
                    await event_sink(
                        "workflow.refused",
                        {
                            "task_id": str(packet.task_id),
                            "reasons": agency_refusal_reasons,
                        },
                    )

        # 10. Synthesize owner-facing Talk output
        talk_output = synthesize_talk_output(cognitive_result)
        if agency_refusal_reasons:
            talk_output.direct_response = (
                f"A workflow was proposed for '{cognitive_result.workflow_proposal.title}', "
                f"but Agency policy refused compilation: {'; '.join(agency_refusal_reasons)}"
            )

    # 11. Metacognitive review checkpoint
        metacog_review = run_metacognitive_review(packet, cognitive_result, depth=1)

        # Provider truth semantics
        provider_configured = (s.ai_provider != "disabled") and (s.openai_api_key is not None)
        provider_available = provider_configured
        provider_invoked = not is_deterministic_worker
        provider_degraded = False
        provider_fallback = False
        provider_latency_ms = brain_trace.wall_time_ms if not is_deterministic_worker else 0
        provider_model_used = s.openai_model if (not is_deterministic_worker and s.openai_model) else ("deterministic_worker" if is_deterministic_worker else "none")
        provider_tokens_used = (brain_trace.total_input_tokens + brain_trace.total_output_tokens) if not is_deterministic_worker else 0

        # 12. Verify final Talk output
        verification = verify_talk_output(
            talk_output, evidence, provider_available=provider_available
        )
        if metacog_review.verdict == "BLOCK" or verification.verdict == "BLOCK":
            raise AIOutputValidationError("Output failed Mind/Brain verification checkpoint.")
    except asyncio.CancelledError:
        model_run.status = "CANCELLED"
        model_run.error = {"kind": "cancelled", "detail": "The owner cancelled this model run."}
        model_run.response_metadata = {"available": False, "reason": "Cancelled by owner."}
        await db.commit()
        raise
    except Exception as exc:
        from app.cognition.intelligence_kernel import TalkProviderFailure
        error = safe_error_metadata(exc)
        model_run.provider = s.ai_provider
        model_run.status = "ERROR"
        model_run.response_metadata = {
            "available": False,
            "reason": error["public_message"],
            "raw_response_id": None,
        }
        model_run.error = error
        await db.flush()
        if event_sink is not None:
            await event_sink(
                "talk.failed",
                {
                    "request_id": str(request_id) if request_id else None,
                    "model_run_id": str(model_run.id),
                    "code": error["code"],
                    "retryable": error["retryable"],
                },
            )
        raise TalkProviderFailure.from_model_run(model_run) from exc

    # 13-16. Persistence & trace completion
    model_run.status = "COMPLETED"
    updated_run_meta = dict(model_run.run_metadata or {})
    updated_run_meta.update(brain_trace.to_metadata())
    updated_run_meta["provider_configured"] = provider_configured
    updated_run_meta["provider_available"] = provider_available
    updated_run_meta["provider_invoked"] = provider_invoked
    updated_run_meta["provider_degraded"] = provider_degraded
    updated_run_meta["provider_fallback"] = provider_fallback
    updated_run_meta["provider_latency_ms"] = provider_latency_ms
    updated_run_meta["provider_model_used"] = provider_model_used
    updated_run_meta["provider_tokens_used"] = provider_tokens_used
    updated_run_meta["execution_provenance"] = "DETERMINISTIC_WORKER" if is_deterministic_worker else "MODEL_PROVIDER"
    updated_run_meta["metacognitive_review"] = {
        "verdict": metacog_review.verdict,
        "summary": metacog_review.decision_summary,
    }
    model_run.run_metadata = updated_run_meta
    model_run.response_metadata = {
        "available": provider_available,
        "reason": None if not is_deterministic_worker else "Executed via deterministic Mind capability worker.",
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
            "provider": "DETERMINISTIC_WORKER" if is_deterministic_worker else s.ai_provider,
            "provider_configured": provider_configured,
            "provider_available": provider_available,
            "provider_invoked": provider_invoked,
            "provider_degraded": provider_degraded,
            "provider_fallback": provider_fallback,
            "provider_latency_ms": provider_latency_ms,
            "provider_model_used": provider_model_used,
            "provider_tokens_used": provider_tokens_used,
            "model_run_id": str(model_run.id),
            "memory_mode": memory_mode,
            "verification": verification.model_dump(),
            "metacognition": metacog_review.decision_summary,
            "omega": omega.model_dump(mode="json"),
            "scope_envelope_id": str(scope_envelope.scope_id),
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
        memory_candidates = await persist_memory_candidates(
            db,
            owner_user_id=owner_user_id,
            orbit_id=orbit_id,
            source_event_id=response_event.id,
            user_message_event_id=turn.id,
            model_run_id=model_run.id,
            request_id=request_id,
            evidence_digest=evidence_digest,
            evidence_sources=[{"kind": ref.kind, "id": ref.id, "rank": ref.rank} for ref in retrieval_refs],
            output=talk_output,
        )
        if event_sink is not None:
            for candidate in memory_candidates:
                await event_sink(
                    "memory.candidate",
                    {
                        "candidate_id": str(candidate.id),
                        "status": candidate.status,
                        "requires_owner_approval": True,
                    },
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
