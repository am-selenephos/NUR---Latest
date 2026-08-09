"""Evidence-linked owner insights with explicit review actions."""

import uuid
from collections import Counter
import datetime as dt

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Identity, Scoped, require_csrf
from app.insights.service import (
    InsightRunBusy,
    consolidate_owner,
    insight_evidence,
    owned_insight,
    review_insight,
)
from app.mind.why_changed import ChangeClass, EntityType, WhyChangedService
from app.models import (
    CognitiveEvent,
    Insight,
    MemoryCandidate,
    OmegaClaim,
    OmegaContradiction,
    Outcome,
    Plan,
    PlanStep,
    ResearchSourceNote,
    SystemAction,
    TimelineEvent,
)
from app.models._mixins import now_utc

router = APIRouter(prefix="/insights", tags=["insights"])


class InsightOut(BaseModel):
    id: uuid.UUID
    orbit_id: uuid.UUID | None
    insight_type: str
    title: str
    claim: str
    tone: str
    confidence: float
    valence: str
    source_event_ids: list
    source_memory_ids: list
    source_research_ids: list
    affected_system_slug: str | None
    affected_goal_id: uuid.UUID | None
    affected_project_id: uuid.UUID | None
    affected_person_id: uuid.UUID | None
    evidence: list
    counter_evidence: list
    what_nur_may_be_wrong_about: str
    positive_interpretation: str | None
    hard_interpretation: str | None
    suggested_action: str | None
    status: str
    correction: str | None
    provenance_label: str
    pattern_id: uuid.UUID | None
    parent_insight_id: uuid.UUID | None
    lifecycle_status: str
    epistemic_state: str
    insight_version: int
    pattern_fingerprint: str | None
    evidence_digest: str | None
    time_scale: str
    time_window_start: dt.datetime | None
    time_window_end: dt.datetime | None
    source_domains: list
    source_diversity: int
    alternative_explanations: list
    assumptions: list
    contradictions: list
    confidence_basis: dict
    quality_dimensions: dict
    quality_policy_version: str
    calibration_target: str | None
    surfaced_at: dt.datetime | None
    reviewed_at: dt.datetime | None
    cooldown_until: dt.datetime | None
    source_invalidated_at: dt.datetime | None
    canonical_links: dict = Field(default_factory=dict)
    created_at: object
    updated_at: object

    model_config = {"from_attributes": True}


class GenerateInsightIn(BaseModel):
    system_slug: str | None = None
    preferred_type: str | None = None


class CorrectInsightIn(BaseModel):
    correction: str = Field(min_length=1, max_length=4000)


class ConvertInsightIn(BaseModel):
    plan_title: str | None = None


class ConsolidateInsightIn(BaseModel):
    run_kind: str = "MANUAL"


class ConsolidationOut(BaseModel):
    id: uuid.UUID
    status: str
    run_kind: str
    max_observations: int
    processed_observations: int
    invalidated_relations: int
    generated_candidates: int
    surfaced_insight_id: uuid.UUID | None
    self_insight_id: uuid.UUID | None
    suppressed_insight_id: uuid.UUID | None
    suppressed_reason: str | None
    input_counts: dict

    model_config = {"from_attributes": True}


def _canonical_links(insight: Insight) -> dict:
    return {
        "timeline": "/universe/timeline",
        "map": "/universe/map",
        "orbit": f"/universe/orbits/{insight.orbit_id}" if insight.orbit_id else None,
        "goal": f"/goals/{insight.affected_goal_id}" if insight.affected_goal_id else None,
        "project": (
            f"/projects/{insight.affected_project_id}"
            if insight.affected_project_id
            else None
        ),
        "person": (
            f"/universe/orbits?person={insight.affected_person_id}"
            if insight.affected_person_id
            else None
        ),
        "evidence": f"/universe/insights/{insight.id}",
    }


def _insight_out(insight: Insight) -> InsightOut:
    out = InsightOut.model_validate(insight)
    out.canonical_links = _canonical_links(insight)
    return out


def _timeline_and_audit(
    db: Scoped,
    *,
    owner_user_id: uuid.UUID,
    insight: Insight,
    event_kind: str,
    description: str,
) -> None:
    db.add(CognitiveEvent(
        owner_user_id=owner_user_id,
        orbit_id=insight.orbit_id,
        event_kind="SYSTEM_EVENT",
        content_text=description,
        source_ref=f"insight:{insight.id}",
        structured_payload={
            "timeline_kind": event_kind,
            "insight_id": str(insight.id),
            "provenance_label": insight.provenance_label,
        },
    ))
    db.add(TimelineEvent(
        owner_user_id=owner_user_id,
        event_type=event_kind,
        title=insight.title,
        description=description,
        time_kind="PAST",
        occurred_at=now_utc(),
        source_type="INSIGHT",
        source_id=insight.id,
        system_slug=insight.affected_system_slug,
        orbit_id=insight.orbit_id,
        status="COMPLETED",
        importance=70,
        event_payload={"insight_type": insight.insight_type, "status": insight.status},
    ))


async def _owned_insight(db: Scoped, owner_user_id: uuid.UUID, insight_id: uuid.UUID) -> Insight:
    try:
        return await owned_insight(
            db, owner_user_id=owner_user_id, insight_id=insight_id
        )
    except LookupError:
        raise HTTPException(404, "Insight not found.")


@router.get("", response_model=list[InsightOut])
async def list_insights(
    db: Scoped,
    identity: Identity,
    status: str | None = None,
    limit: int = 80,
) -> list[InsightOut]:
    owner_user_id, _ = identity
    query = select(Insight).where(Insight.owner_user_id == owner_user_id)
    if status:
        query = query.where(Insight.status == status.upper())
    rows = (await db.execute(
        query.order_by(Insight.updated_at.desc()).limit(min(limit, 200))
    )).scalars().all()
    return [_insight_out(row) for row in rows]


@router.post(
    "/consolidate",
    response_model=ConsolidationOut,
    dependencies=[Depends(require_csrf)],
)
async def consolidate_insights(
    payload: ConsolidateInsightIn, db: Scoped, identity: Identity
) -> ConsolidationOut:
    owner_user_id, _ = identity
    try:
        run = await consolidate_owner(
            db,
            owner_user_id=owner_user_id,
            run_kind=payload.run_kind,
            worker_id="owner-api",
        )
    except InsightRunBusy as exc:
        raise HTTPException(409, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.commit()
    return ConsolidationOut.model_validate(run)


@router.get("/{insight_id}", response_model=InsightOut)
async def get_insight(insight_id: uuid.UUID, db: Scoped, identity: Identity) -> InsightOut:
    owner_user_id, _ = identity
    return _insight_out(await _owned_insight(db, owner_user_id, insight_id))


@router.get("/{insight_id}/evidence")
async def get_insight_evidence(
    insight_id: uuid.UUID, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    try:
        rows = await insight_evidence(
            db, owner_user_id=owner_user_id, insight_id=insight_id
        )
    except LookupError as exc:
        raise HTTPException(404, "Insight not found.") from exc
    relations = []
    for row, source_exists in rows:
        relations.append(
            {
                "id": row.id,
                "source_kind": row.source_kind,
                "source_id": row.source_id,
                "source_domain": row.source_domain,
                "relation": row.relation,
                "provenance_label": row.provenance_label,
                "explicitness": row.explicitness,
                "confidence": row.confidence,
                "evidence_summary": row.evidence_summary,
                "source_occurred_at": row.source_occurred_at,
                "insight_version": row.insight_version,
                "invalidated_at": row.invalidated_at,
                "invalidation_reason": row.invalidation_reason,
                "source_exists": source_exists,
                "canonical_route": _evidence_route(row.source_kind, row.source_id),
            }
        )
    return {"insight_id": insight_id, "relations": relations}


@router.get("/{insight_id}/why-changed")
async def get_insight_why_changed(
    insight_id: uuid.UUID, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    await _owned_insight(db, owner_user_id, insight_id)
    rows = await WhyChangedService.get_change_history(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.INSIGHT.value,
        entity_id=str(insight_id),
    )
    return {
        "insight_id": insight_id,
        "changes": [row.model_dump(mode="json") for row in rows],
        "governance": "Inspectable state transitions only; no chain-of-thought is stored.",
    }


def _evidence_route(source_kind: str, source_id: uuid.UUID) -> str:
    routes = {
        "AM_PROJECT": f"/projects/{source_id}",
        "COGNITIVE_EVENT": "/universe/timeline",
        "DOMAIN_EVENT": "/universe/timeline",
        "GOAL": f"/goals/{source_id}",
        "INSIGHT": f"/universe/insights/{source_id}",
        "INSIGHT_FEEDBACK": "/universe/insights",
        "JOURNAL_ENTRY": f"/journal?entry={source_id}",
        "ORBIT": f"/universe/orbits/{source_id}",
        "OUTCOME": f"/universe/timeline?outcome={source_id}",
        "PERSON": f"/universe/orbits?person={source_id}",
        "PLAN": f"/plan?plan={source_id}",
        "PLAN_STEP": f"/plan?step={source_id}",
        "PREDICTION": f"/universe/timeline?prediction={source_id}",
        "RESEARCH_SOURCE_NOTE": f"/research?source={source_id}",
        "SYSTEM_ACTION": f"/systems?action={source_id}",
        "TIMELINE_EVENT": f"/universe/timeline?event={source_id}",
        "USER_CORRECTION": "/universe/insights",
    }
    return routes.get(source_kind, "/universe/insights")


@router.post("/generate", response_model=InsightOut, status_code=201, dependencies=[Depends(require_csrf)])
async def generate_insight(payload: GenerateInsightIn, db: Scoped, identity: Identity) -> InsightOut:
    owner_user_id, _ = identity
    contradiction = (await db.execute(select(OmegaContradiction).where(
        OmegaContradiction.owner_user_id == owner_user_id,
        OmegaContradiction.status == "OPEN",
    ).order_by(OmegaContradiction.created_at.desc()).limit(1))).scalar_one_or_none()
    claim = (await db.execute(select(OmegaClaim).where(
        OmegaClaim.owner_user_id == owner_user_id,
        OmegaClaim.truth_status.notin_(["RETIRED", "SUPERSEDED"]),
    ).order_by(OmegaClaim.updated_at.desc()).limit(1))).scalar_one_or_none()
    actions = (await db.execute(select(SystemAction).where(
        SystemAction.owner_user_id == owner_user_id,
        *([SystemAction.system_slug == payload.system_slug] if payload.system_slug else []),
    ).order_by(SystemAction.updated_at.desc()).limit(30))).scalars().all()
    outcomes = (await db.execute(select(Outcome).where(
        Outcome.owner_user_id == owner_user_id,
    ).order_by(Outcome.created_at.desc()).limit(6))).scalars().all()
    research = (await db.execute(select(ResearchSourceNote).where(
        ResearchSourceNote.owner_user_id == owner_user_id,
    ).order_by(ResearchSourceNote.updated_at.desc()).limit(3))).scalars().all()

    evidence: list[dict] = []
    counter_evidence: list[dict] = []
    source_event_ids: list[str] = []
    source_memory_ids: list[str] = []
    source_research_ids = [str(row.id) for row in research]
    system_slug = payload.system_slug

    if contradiction is not None:
        insight_type = "CONTRADICTION"
        title = "Two persisted truths are pulling in different directions"
        insight_claim = contradiction.description
        confidence = 0.78
        valence = "HARD"
        evidence.append({
            "kind": "OMEGA_CONTRADICTION",
            "id": str(contradiction.id),
            "excerpt": contradiction.description,
            "provenance_label": "OMEGA_OWNER_LEDGER",
        })
        source_memory_ids.extend([str(contradiction.claim_a_id), str(contradiction.claim_b_id)])
        wrong_about = "The two claims may apply in different contexts rather than truly conflict."
        positive = "The tension can identify a boundary that was previously implicit."
        hard = "Avoiding the conflict may keep both goals stalled."
        action = contradiction.proposed_resolution or "Name which claim should govern the next move."
    elif claim is not None:
        insight_type = payload.preferred_type or "CANDIDATE_INSIGHT"
        title = claim.claim_text[:160]
        insight_claim = claim.claim_text
        confidence = claim.confidence
        valence = "MIXED"
        evidence.append({
            "kind": "OMEGA_CLAIM",
            "id": str(claim.id),
            "excerpt": claim.claim_text,
            "support_count": claim.support_count,
            "provenance_label": f"OMEGA_{claim.truth_status}",
        })
        source_memory_ids.append(str(claim.id))
        wrong_about = "This is a candidate claim; its supporting experiences may be incomplete or context-specific."
        positive = "The pattern may reveal a strength or preference worth protecting."
        hard = "Treating an inferred pattern as settled truth could narrow future choices."
        action = "Accept, reject, or correct this claim before it becomes durable memory."
    elif actions:
        counts = Counter(row.status for row in actions)
        missed = counts.get("MISSED", 0)
        completed = counts.get("COMPLETED", 0)
        insight_type = "RISK" if missed > completed else "GOOD_INSIGHT"
        title = "Your action ledger shows a repeated execution pattern"
        insight_claim = (
            f"{missed} missed actions currently outweigh {completed} completed actions."
            if missed > completed
            else f"{completed} completed actions match or exceed {missed} missed actions."
        )
        confidence = min(0.9, 0.45 + len(actions) / 60)
        valence = "HARD" if missed > completed else "POSITIVE"
        system_slug = system_slug or actions[0].system_slug
        for row in actions[:8]:
            evidence.append({
                "kind": "SYSTEM_ACTION",
                "id": str(row.id),
                "excerpt": f"{row.status}: {row.title}",
                "provenance_label": "OWNER_LEDGER",
            })
        wrong_about = "Action status does not capture every reason, invisible effort, or external constraint."
        positive = "The pattern can be changed by matching effort to current capacity."
        hard = "Repeatedly carrying oversized actions may be protecting ambition at the cost of continuity."
        action = "Make the oldest open action small enough to finish today."
    elif outcomes:
        insight_type = "GOOD_INSIGHT"
        title = "You returned evidence instead of disappearing"
        insight_claim = outcomes[0].observed_result
        confidence = 0.72
        valence = "POSITIVE"
        evidence.append({
            "kind": "OUTCOME",
            "id": str(outcomes[0].id),
            "excerpt": outcomes[0].observed_result,
            "provenance_label": "OBSERVED_OUTCOME",
        })
        wrong_about = "One returned outcome may not represent a stable pattern yet."
        positive = "Returning evidence is itself a repeatable continuity behavior."
        hard = "The next test is whether the return happens again under friction."
        action = "Choose the next smallest outcome that can be returned."
    else:
        raise HTTPException(409, "Not enough owner evidence exists to generate a non-generic insight.")

    for row in research:
        counter_evidence.append({
            "kind": "RESEARCH_SOURCE_NOTE",
            "id": str(row.id),
            "title": row.title,
            "url": row.url,
            "trust_state": row.trust_state,
            "note": "Saved context only; this source does not independently prove the personal claim.",
        })

    insight = Insight(
        owner_user_id=owner_user_id,
        orbit_id=None,
        insight_type=insight_type.upper(),
        title=title,
        claim=insight_claim,
        tone="DIRECT",
        confidence=confidence,
        valence=valence,
        source_event_ids=source_event_ids,
        source_memory_ids=source_memory_ids,
        source_research_ids=source_research_ids,
        affected_system_slug=system_slug,
        evidence=evidence,
        counter_evidence=counter_evidence,
        what_nur_may_be_wrong_about=wrong_about,
        positive_interpretation=positive,
        hard_interpretation=hard,
        suggested_action=action,
        provenance_label="INFERRED_OWNER_LEDGER",
        lifecycle_status="CANDIDATE",
        epistemic_state="NEEDS_OWNER_CONFIRMATION",
        source_domains=sorted(
            {
                "OMEGA" if row.get("kind", "").startswith("OMEGA") else "LIVING"
                for row in evidence
            }
        ),
        source_diversity=len(
            {
                "OMEGA" if row.get("kind", "").startswith("OMEGA") else "LIVING"
                for row in evidence
            }
        ),
        alternative_explanations=[wrong_about],
        assumptions=["This manually requested legacy candidate may be single-source."],
        quality_dimensions={
            "passes": False,
            "reason_codes": ["LEGACY_SINGLE_SOURCE_CANDIDATE"],
        },
    )
    db.add(insight)
    await db.flush()
    _timeline_and_audit(
        db,
        owner_user_id=owner_user_id,
        insight=insight,
        event_kind="INSIGHT_CREATED",
        description=f"Candidate insight created from {len(evidence)} owner evidence records.",
    )
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.INSIGHT,
        entity_id=str(insight.id),
        change_class=ChangeClass.CREATED,
        trigger="Owner explicitly requested a legacy single-source candidate.",
        new_version="1",
        supporting_evidence=[f"{row['kind']}:{row['id']}" for row in evidence],
        counter_evidence=[
            f"{row['kind']}:{row['id']}" for row in counter_evidence if row.get("id")
        ],
        actor="owner",
        affected_future_behavior="Candidate requires owner review and is not surfaced truth.",
        policy_version=insight.quality_policy_version,
    )
    await db.commit()
    return _insight_out(insight)


async def _set_status(
    insight_id: uuid.UUID,
    status: str,
    db: Scoped,
    identity: Identity,
) -> InsightOut:
    owner_user_id, _ = identity
    action = {"ACCEPTED": "THIS_FITS", "REJECTED": "NOT_RIGHT"}[status]
    try:
        row = await review_insight(
            db,
            owner_user_id=owner_user_id,
            insight_id=insight_id,
            action=action,
        )
    except LookupError as exc:
        raise HTTPException(404, "Insight not found.") from exc
    await db.commit()
    return _insight_out(row)


@router.post("/{insight_id}/accept", response_model=InsightOut, dependencies=[Depends(require_csrf)])
async def accept_insight(insight_id: uuid.UUID, db: Scoped, identity: Identity) -> InsightOut:
    return await _set_status(insight_id, "ACCEPTED", db, identity)


@router.post("/{insight_id}/reject", response_model=InsightOut, dependencies=[Depends(require_csrf)])
async def reject_insight(insight_id: uuid.UUID, db: Scoped, identity: Identity) -> InsightOut:
    return await _set_status(insight_id, "REJECTED", db, identity)


@router.post("/{insight_id}/correct", response_model=InsightOut, dependencies=[Depends(require_csrf)])
async def correct_insight(
    insight_id: uuid.UUID, payload: CorrectInsightIn, db: Scoped, identity: Identity
) -> InsightOut:
    owner_user_id, _ = identity
    try:
        row = await review_insight(
            db,
            owner_user_id=owner_user_id,
            insight_id=insight_id,
            action="CORRECT_NUR",
            correction_text=payload.correction,
        )
    except LookupError as exc:
        raise HTTPException(404, "Insight not found.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    await db.commit()
    return _insight_out(row)


@router.post("/{insight_id}/save-to-memory", dependencies=[Depends(require_csrf)])
async def save_insight_to_memory(insight_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = await _owned_insight(db, owner_user_id, insight_id)
    if row.status != "ACCEPTED":
        raise HTTPException(409, "Only an owner-accepted insight can become a memory candidate.")
    memory = MemoryCandidate(
        owner_user_id=owner_user_id,
        orbit_id=row.orbit_id,
        candidate_text=row.claim,
        original_text=row.claim,
        scope="LEARNING_CANDIDATE",
        memory_type="SEMANTIC",
        provenance_label="MODEL_GENERATED",
        confidence=row.confidence,
        sensitivity="PRIVATE",
        created_by="MODEL",
        source_object_ids={
            "insight_id": str(row.id),
            "source_event_ids": row.source_event_ids,
            "originating_system": "INSIGHTS",
        },
        status="CANDIDATE",
    )
    db.add(memory)
    await db.commit()
    return {"id": memory.id, "status": memory.status, "scope": memory.scope}


@router.post("/{insight_id}/convert-to-plan", dependencies=[Depends(require_csrf)])
async def convert_insight_to_plan(
    insight_id: uuid.UUID, payload: ConvertInsightIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_insight(db, owner_user_id, insight_id)
    if row.status != "ACCEPTED" or row.lifecycle_status != "OWNER_CONFIRMED":
        raise HTTPException(409, "Only an owner-confirmed insight can become a plan.")
    plan = Plan(
        owner_user_id=owner_user_id,
        orbit_id=row.orbit_id,
        title=payload.plan_title or f"Act on insight: {row.title[:120]}",
    )
    db.add(plan)
    await db.flush()
    step = PlanStep(
        owner_user_id=owner_user_id,
        plan_id=plan.id,
        title=row.suggested_action or "Choose one evidence-linked next move.",
        body=f"Source insight: {row.claim}",
        position=0,
    )
    db.add(step)
    await db.commit()
    return {"plan_id": plan.id, "plan_step_id": step.id, "route": "/plan"}


@router.post("/{insight_id}/add-to-timeline", dependencies=[Depends(require_csrf)])
async def add_insight_to_timeline(insight_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = await _owned_insight(db, owner_user_id, insight_id)
    timeline = TimelineEvent(
        owner_user_id=owner_user_id,
        event_type="INSIGHT_REVIEW_DUE",
        title=row.title,
        description=row.suggested_action or row.claim,
        time_kind="PRESENT",
        scheduled_for=now_utc(),
        source_type="INSIGHT",
        source_id=row.id,
        system_slug=row.affected_system_slug,
        orbit_id=row.orbit_id,
        status="DUE",
        importance=75,
        event_payload={"insight_status": row.status},
    )
    db.add(timeline)
    await db.commit()
    return {"timeline_event_id": timeline.id, "route": "/universe/timeline"}
