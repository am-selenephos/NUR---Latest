import datetime as dt
import uuid

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, or_, select

from app.api.deps import Identity, Scoped
from app.models import (
    CognitiveEvent,
    ContextCapsule,
    CommunityConsultationNote,
    Decision,
    FeasibilityAssessment,
    Insight,
    JournalEntry,
    OmegaClaim,
    OmegaConsolidationRun,
    OmegaContradiction,
    OmegaLearningProposal,
    OmegaPrediction,
    OmegaReviewQueue,
    Orbit,
    OrbitReference,
    OrbitSource,
    Outcome,
    ResearchBrief,
    ResearchDraft,
    ResearchSourceNote,
    ScheduledAction,
    TimelineEvent,
    WebSignalNote,
    WebSignalQuestion,
)
from app.universe.live_service import build_live_universe

router = APIRouter(prefix="/universe", tags=["universe"])


class UniverseCount(BaseModel):
    key: str
    label: str
    count: int


class MapNode(BaseModel):
    id: str
    title: str
    kind: str
    orbit_id: uuid.UUID | None
    active: bool
    counts: dict[str, int]


class MapSummary(BaseModel):
    provenance_label: str
    counts: list[UniverseCount]
    nodes: list[MapNode]


class OrbitSummaryRow(BaseModel):
    id: uuid.UUID
    title: str
    kind: str
    status: str
    description: str | None
    created_at: dt.datetime
    counts: dict[str, int]


class OrbitsSummary(BaseModel):
    provenance_label: str
    orbits: list[OrbitSummaryRow]


class TimelineItem(BaseModel):
    id: str
    kind: str
    title: str
    body: str
    created_at: dt.datetime
    provenance_label: str
    route: str
    lane: str = "past"
    due_at: dt.datetime | None = None


class TimelineOut(BaseModel):
    provenance_label: str
    items: list[TimelineItem]


class InsightsSummary(BaseModel):
    provenance_label: str
    counts: dict[str, int]
    dedicated_insights: list[dict]
    omega_claims: list[dict]
    claims: list[dict]
    contradictions: list[dict]
    predictions: list[dict]
    review_queue: list[dict]
    feasibility: list[dict]


class SearchHit(BaseModel):
    kind: str
    id: str
    label: str
    excerpt: str | None
    route: str
    created_at: dt.datetime
    provenance_label: str


async def _count(db: Scoped, stmt) -> int:
    return int((await db.execute(stmt)).scalar_one())


@router.get("/live")
async def live_universe(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    return await build_live_universe(db, owner_user_id=owner_user_id)


@router.get("/map-summary", response_model=MapSummary)
async def map_summary(db: Scoped, identity: Identity) -> MapSummary:
    user_id, _ = identity
    orbits = (await db.execute(
        select(Orbit).where(Orbit.owner_user_id == user_id).order_by(Orbit.created_at.asc())
    )).scalars().all()
    counts = [
        UniverseCount(key="orbits", label="owner-owned orbits", count=len(orbits)),
        UniverseCount(key="decisions", label="decisions", count=await _count(db, select(func.count(Decision.id)).where(Decision.owner_user_id == user_id))),
        UniverseCount(key="references", label="references and questions", count=await _count(db, select(func.count(OrbitReference.id)).where(OrbitReference.owner_user_id == user_id))),
        UniverseCount(key="outcomes", label="returned outcomes", count=await _count(db, select(func.count(Outcome.id)).where(Outcome.owner_user_id == user_id))),
        UniverseCount(key="capsules", label="context capsules", count=await _count(db, select(func.count(ContextCapsule.id)).where(ContextCapsule.owner_user_id == user_id))),
    ]
    nodes: list[MapNode] = []
    for orbit in orbits:
        orbit_counts = {
            "decisions": await _count(db, select(func.count(Decision.id)).where(Decision.owner_user_id == user_id, Decision.orbit_id == orbit.id)),
            "references": await _count(db, select(func.count(OrbitReference.id)).where(OrbitReference.owner_user_id == user_id, OrbitReference.orbit_id == orbit.id)),
            "sources": await _count(db, select(func.count(OrbitSource.id)).where(OrbitSource.owner_user_id == user_id, OrbitSource.orbit_id == orbit.id)),
            "capsules": await _count(db, select(func.count(ContextCapsule.id)).where(ContextCapsule.owner_user_id == user_id, ContextCapsule.orbit_id == orbit.id)),
        }
        nodes.append(MapNode(
            id=str(orbit.id),
            title=orbit.title,
            kind=orbit.kind,
            orbit_id=orbit.id,
            active=orbit.status == "ACTIVE",
            counts=orbit_counts,
        ))
    return MapSummary(provenance_label="owner_ledger", counts=counts, nodes=nodes)


@router.get("/orbits-summary", response_model=OrbitsSummary)
async def orbits_summary(db: Scoped, identity: Identity) -> OrbitsSummary:
    user_id, _ = identity
    orbits = (await db.execute(
        select(Orbit).where(Orbit.owner_user_id == user_id).order_by(Orbit.created_at.asc())
    )).scalars().all()
    rows: list[OrbitSummaryRow] = []
    for orbit in orbits:
        rows.append(OrbitSummaryRow(
            id=orbit.id,
            title=orbit.title,
            kind=orbit.kind,
            status=orbit.status,
            description=orbit.description,
            created_at=orbit.created_at,
            counts={
                "decisions": await _count(db, select(func.count(Decision.id)).where(Decision.owner_user_id == user_id, Decision.orbit_id == orbit.id)),
                "references": await _count(db, select(func.count(OrbitReference.id)).where(OrbitReference.owner_user_id == user_id, OrbitReference.orbit_id == orbit.id)),
                "sources": await _count(db, select(func.count(OrbitSource.id)).where(OrbitSource.owner_user_id == user_id, OrbitSource.orbit_id == orbit.id)),
                "capsules": await _count(db, select(func.count(ContextCapsule.id)).where(ContextCapsule.owner_user_id == user_id, ContextCapsule.orbit_id == orbit.id)),
            },
        ))
    return OrbitsSummary(provenance_label="owner_ledger", orbits=rows)


@router.get("/timeline", response_model=TimelineOut)
async def timeline(db: Scoped, identity: Identity, limit: int = 80) -> TimelineOut:
    user_id, _ = identity
    items: list[TimelineItem] = []
    events = (await db.execute(
        select(CognitiveEvent).where(CognitiveEvent.owner_user_id == user_id).order_by(CognitiveEvent.created_at.desc()).limit(min(limit, 120))
    )).scalars().all()
    for event in events:
        effective_kind = event.structured_payload.get(
            "timeline_kind", event.event_kind
        )
        label = effective_kind.replace("_", " ").title()
        items.append(TimelineItem(
            id=str(event.id),
            kind=effective_kind,
            title=label,
            body=event.content_text or str(event.structured_payload)[:220],
            created_at=event.created_at,
            provenance_label="cognitive_event",
            route=(
                "/talk" if event.event_kind in {"TALK_TURN", "MODEL_RESPONSE"}
                else "/universe/research" if event.event_kind in {"RESEARCH_BRIEF_CREATED", "RESEARCH_SOURCE_NOTE_ADDED"}
                else "/universe/community" if event.event_kind == "COMMUNITY_NOTE_CREATED"
                else "/universe/web-signals" if event.event_kind in {"WEB_SIGNAL_QUESTION_STAGED", "WEB_SIGNAL_NOTE_ADDED"}
                else "/universe/map" if effective_kind == "PREDICTION_MADE"
                else "/universe/insights" if effective_kind == "FEASIBILITY_CREATED"
                else "/systems" if effective_kind in {
                    "SYSTEM_DIAGNOSTIC_RECORDED",
                    "SYSTEM_ACTION_CREATED",
                    "SYSTEM_ACTION_COMPLETED",
                    "SYSTEM_ACTION_MISSED",
                    "ACTION_MADE_EASIER",
                    "OUTCOME_RETURNED",
                    "OUTCOME_CORRECTED",
                    "GOAL_CREATED",
                    "OBJECTIVE_CREATED",
                    "SCHEDULE_CREATED",
                }
                else "/today"
            ),
        ))
    now = dt.datetime.now(dt.UTC)
    scheduled = (await db.execute(
        select(ScheduledAction).where(
            ScheduledAction.owner_user_id == user_id,
        ).order_by(ScheduledAction.scheduled_for.asc()).limit(100)
    )).scalars().all()
    for row in scheduled:
        if row.status in {"COMPLETED", "MISSED", "CANCELLED"}:
            lane = "past"
        elif row.scheduled_for <= now + dt.timedelta(days=1):
            lane = "present"
        else:
            lane = "future"
        items.append(TimelineItem(
            id=str(row.id),
            kind="SCHEDULE_DUE" if row.status == "SCHEDULED" else f"SCHEDULE_{row.status}",
            title=row.title,
            body=f"{row.system_slug.replace('-', ' ').title()} · {row.status.lower()}",
            created_at=row.created_at,
            provenance_label="owner_schedule",
            route="/today",
            lane=lane,
            due_at=row.scheduled_for,
        ))
    explicit_timeline = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == user_id,
    ).order_by(
        TimelineEvent.scheduled_for.asc().nullslast(),
        TimelineEvent.created_at.desc(),
    ).limit(120))).scalars().all()
    for row in explicit_timeline:
        if row.status in {"COMPLETED", "CANCELLED"}:
            lane = "past"
        elif row.status == "DUE" or row.time_kind == "PRESENT":
            lane = "present"
        else:
            lane = "future" if row.time_kind != "PREDICTION" else "prediction"
        items.append(TimelineItem(
            id=str(row.id),
            kind=row.event_type,
            title=row.title,
            body=row.description or "Persisted owner Timeline event.",
            created_at=row.occurred_at or row.created_at,
            provenance_label="owner_timeline_ledger",
            route="/universe/timeline",
            lane=lane,
            due_at=row.scheduled_for,
        ))
    briefs = (await db.execute(
        select(ResearchBrief).where(ResearchBrief.owner_user_id == user_id).order_by(ResearchBrief.created_at.desc()).limit(30)
    )).scalars().all()
    for brief in briefs:
        items.append(TimelineItem(
            id=str(brief.id),
            kind="RESEARCH_BRIEF_CREATED",
            title="research brief",
            body=brief.question,
            created_at=brief.created_at,
            provenance_label=brief.provenance_label.lower(),
            route="/universe/research",
        ))
    source_notes = (await db.execute(
        select(ResearchSourceNote).where(ResearchSourceNote.owner_user_id == user_id).order_by(ResearchSourceNote.created_at.desc()).limit(30)
    )).scalars().all()
    for note in source_notes:
        items.append(TimelineItem(
            id=str(note.id),
            kind="RESEARCH_SOURCE_NOTE_ADDED",
            title="research source note",
            body=note.title,
            created_at=note.created_at,
            provenance_label=note.provenance_label.lower(),
            route="/universe/research",
        ))
    community_notes = (await db.execute(
        select(CommunityConsultationNote).where(CommunityConsultationNote.owner_user_id == user_id).order_by(CommunityConsultationNote.created_at.desc()).limit(30)
    )).scalars().all()
    for note in community_notes:
        items.append(TimelineItem(
            id=str(note.id),
            kind="COMMUNITY_NOTE_CREATED",
            title="community consultation note",
            body=note.title,
            created_at=note.created_at,
            provenance_label=note.provenance_label.lower(),
            route="/universe/community",
        ))
    web_questions = (await db.execute(
        select(WebSignalQuestion).where(WebSignalQuestion.owner_user_id == user_id).order_by(WebSignalQuestion.created_at.desc()).limit(30)
    )).scalars().all()
    for question in web_questions:
        items.append(TimelineItem(
            id=str(question.id),
            kind="WEB_SIGNAL_QUESTION_STAGED",
            title="web signal question",
            body=question.question,
            created_at=question.created_at,
            provenance_label=question.provenance_label.lower(),
            route="/universe/web-signals",
        ))
    web_notes = (await db.execute(
        select(WebSignalNote).where(WebSignalNote.owner_user_id == user_id).order_by(WebSignalNote.created_at.desc()).limit(30)
    )).scalars().all()
    for note in web_notes:
        items.append(TimelineItem(
            id=str(note.id),
            kind="WEB_SIGNAL_NOTE_ADDED",
            title="web signal note",
            body=note.title,
            created_at=note.created_at,
            provenance_label=note.provenance_label.lower(),
            route="/universe/web-signals",
        ))
    capsules = (await db.execute(
        select(ContextCapsule).where(ContextCapsule.owner_user_id == user_id).order_by(ContextCapsule.created_at.desc()).limit(40)
    )).scalars().all()
    for capsule in capsules:
        items.append(TimelineItem(
            id=str(capsule.id),
            kind="CAPSULE_REVOKED" if capsule.revoked_at else "CAPSULE_CREATED",
            title="capsule revoked" if capsule.revoked_at else "capsule created",
            body=capsule.purpose,
            created_at=capsule.revoked_at or capsule.created_at,
            provenance_label="context_capsule",
            route=f"/capsule/{capsule.id}",
        ))
    runs = (await db.execute(
        select(OmegaConsolidationRun).where(OmegaConsolidationRun.owner_user_id == user_id).order_by(OmegaConsolidationRun.created_at.desc()).limit(20)
    )).scalars().all()
    for run in runs:
        items.append(TimelineItem(
            id=str(run.id),
            kind="OMEGA_CONSOLIDATION",
            title=f"{run.run_kind.lower()} consolidation",
            body=f"{run.created_claims} claims, {run.contradictions_found} contradictions, {run.predictions_resolved} predictions resolved",
            created_at=run.created_at,
            provenance_label="omega",
            route="/universe/omega",
        ))
    items.sort(key=lambda row: row.created_at, reverse=True)
    return TimelineOut(provenance_label="owner_ledger", items=items[:min(limit, 200)])


@router.get("/insights-summary", response_model=InsightsSummary)
async def insights_summary(db: Scoped, identity: Identity) -> InsightsSummary:
    user_id, _ = identity
    dedicated = (await db.execute(
        select(Insight).where(
            Insight.owner_user_id == user_id,
            Insight.lifecycle_status.notin_(["OWNER_REJECTED", "SUPERSEDED", "RETRACTED"]),
        ).order_by(Insight.updated_at.desc()).limit(16)
    )).scalars().all()
    claims = (await db.execute(
        select(OmegaClaim).where(OmegaClaim.owner_user_id == user_id).order_by(OmegaClaim.updated_at.desc()).limit(12)
    )).scalars().all()
    contradictions = (await db.execute(
        select(OmegaContradiction).where(OmegaContradiction.owner_user_id == user_id, OmegaContradiction.status == "OPEN").order_by(OmegaContradiction.created_at.desc()).limit(8)
    )).scalars().all()
    predictions = (await db.execute(
        select(OmegaPrediction).where(OmegaPrediction.owner_user_id == user_id).order_by(OmegaPrediction.created_at.desc()).limit(8)
    )).scalars().all()
    reviews = (await db.execute(
        select(OmegaReviewQueue).where(OmegaReviewQueue.owner_user_id == user_id, OmegaReviewQueue.status == "PENDING_REVIEW").order_by(OmegaReviewQueue.created_at.desc()).limit(8)
    )).scalars().all()
    feasibility = (await db.execute(
        select(FeasibilityAssessment).where(
            FeasibilityAssessment.owner_user_id == user_id,
        ).order_by(FeasibilityAssessment.created_at.desc()).limit(8)
    )).scalars().all()
    dedicated_rows = [{
        "record_kind": "DEDICATED_INSIGHT",
        "id": str(row.id),
        "title": row.title,
        "claim_text": row.claim,
        "insight_type": row.insight_type,
        "truth_status": row.status,
        "lifecycle_status": row.lifecycle_status,
        "epistemic_state": row.epistemic_state,
        "insight_version": row.insight_version,
        "time_scale": row.time_scale,
        "source_domains": row.source_domains,
        "source_diversity": row.source_diversity,
        "confidence": row.confidence,
        "evidence": row.evidence,
        "counter_evidence": row.counter_evidence,
        "alternative_explanations": row.alternative_explanations,
        "what_nur_may_be_wrong_about": row.what_nur_may_be_wrong_about,
        "positive_interpretation": row.positive_interpretation,
        "hard_interpretation": row.hard_interpretation,
        "suggested_action": row.suggested_action,
        "provenance_label": row.provenance_label,
        "detail_route": f"/universe/insights/{row.id}",
    } for row in dedicated]
    omega_rows = [{
        "record_kind": "OMEGA_CLAIM",
        "id": str(row.id),
        "claim_text": row.claim_text,
        "truth_status": row.truth_status,
        "confidence": row.confidence,
        "provenance_label": f"OMEGA_{row.truth_status}",
        "detail_route": f"/universe/omega/why-changed/{row.id}",
    } for row in claims]
    return InsightsSummary(
        provenance_label="owner_ledger",
        counts={
            "claims": len(dedicated_rows) + len(omega_rows),
            "dedicated_insights": len(dedicated_rows),
            "omega_claims": len(omega_rows),
            "open_contradictions": len(contradictions),
            "predictions": len(predictions),
            "review_queue": len(reviews),
            "learning_proposals": await _count(db, select(func.count(OmegaLearningProposal.id)).where(OmegaLearningProposal.owner_user_id == user_id)),
            "feasibility_assessments": len(feasibility),
        },
        dedicated_insights=dedicated_rows,
        omega_claims=omega_rows,
        claims=dedicated_rows + omega_rows,
        contradictions=[{"id": str(c.id), "description": c.description, "severity": c.severity, "status": c.status} for c in contradictions],
        predictions=[{"id": str(p.id), "prediction_text": p.prediction_text, "status": p.status, "confidence": p.confidence} for p in predictions],
        review_queue=[{"id": str(r.id), "candidate_claim_text": r.candidate_claim_text, "sensitivity": r.sensitivity, "status": r.status} for r in reviews],
        feasibility=[{
            "id": str(row.id),
            "title": row.title,
            "system_slug": row.system_slug,
            "result": row.result,
            "rationale": row.rationale,
            "suggestions": row.suggestions,
            "provenance_label": "deterministic_owner_ledger_assessment",
        } for row in feasibility],
    )


@router.get("/search", response_model=list[SearchHit])
async def search(db: Scoped, identity: Identity, q: str, limit: int = 12) -> list[SearchHit]:
    user_id, _ = identity
    needle = f"%{q.strip()}%"
    if len(q.strip()) < 2:
        return []
    max_rows = min(limit, 25)
    hits: list[SearchHit] = []
    orbit_rows = (await db.execute(
        select(Orbit).where(Orbit.owner_user_id == user_id, Orbit.title.ilike(needle)).order_by(Orbit.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in orbit_rows:
        hits.append(SearchHit(kind="orbit", id=str(row.id), label=row.title, excerpt=row.description, route="/universe/orbits", created_at=row.created_at, provenance_label="owner_ledger"))
    decision_rows = (await db.execute(
        select(Decision).where(Decision.owner_user_id == user_id, or_(Decision.statement.ilike(needle), Decision.rationale.ilike(needle))).order_by(Decision.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in decision_rows:
        hits.append(SearchHit(kind="decision", id=str(row.id), label=row.statement, excerpt=row.rationale, route="/universe/orbits", created_at=row.created_at, provenance_label="owner_ledger"))
    reference_rows = (await db.execute(
        select(OrbitReference).where(OrbitReference.owner_user_id == user_id, or_(OrbitReference.title.ilike(needle), OrbitReference.body.ilike(needle))).order_by(OrbitReference.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in reference_rows:
        hits.append(SearchHit(kind=row.kind.lower(), id=str(row.id), label=row.title, excerpt=row.body, route="/universe/research", created_at=row.created_at, provenance_label="owner_ledger"))
    journal_rows = (await db.execute(
        select(JournalEntry).where(JournalEntry.owner_user_id == user_id, JournalEntry.body.ilike(needle)).order_by(JournalEntry.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in journal_rows:
        hits.append(SearchHit(kind="journal", id=str(row.id), label=row.body[:90], excerpt=row.body, route="/journal", created_at=row.created_at, provenance_label="owner_ledger"))
    research_rows = (await db.execute(
        select(ResearchDraft).where(ResearchDraft.owner_user_id == user_id, or_(ResearchDraft.question.ilike(needle), ResearchDraft.notes.ilike(needle))).order_by(ResearchDraft.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in research_rows:
        hits.append(SearchHit(kind="research", id=str(row.id), label=row.question, excerpt=row.notes, route="/universe/research", created_at=row.created_at, provenance_label="owner_ledger"))
    brief_rows = (await db.execute(
        select(ResearchBrief).where(ResearchBrief.owner_user_id == user_id, or_(ResearchBrief.question.ilike(needle), ResearchBrief.summary.ilike(needle))).order_by(ResearchBrief.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in brief_rows:
        hits.append(SearchHit(kind="research_brief", id=str(row.id), label=row.question, excerpt=row.summary, route="/universe/research", created_at=row.created_at, provenance_label=row.provenance_label.lower()))
    source_note_rows = (await db.execute(
        select(ResearchSourceNote).where(ResearchSourceNote.owner_user_id == user_id, or_(ResearchSourceNote.title.ilike(needle), ResearchSourceNote.note.ilike(needle))).order_by(ResearchSourceNote.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in source_note_rows:
        hits.append(SearchHit(kind="research_source_note", id=str(row.id), label=row.title, excerpt=row.note, route="/universe/research", created_at=row.created_at, provenance_label=row.provenance_label.lower()))
    community_rows = (await db.execute(
        select(CommunityConsultationNote).where(CommunityConsultationNote.owner_user_id == user_id, or_(CommunityConsultationNote.title.ilike(needle), CommunityConsultationNote.note.ilike(needle))).order_by(CommunityConsultationNote.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in community_rows:
        hits.append(SearchHit(kind="community_note", id=str(row.id), label=row.title, excerpt=row.note, route="/universe/community", created_at=row.created_at, provenance_label=row.provenance_label.lower()))
    web_question_rows = (await db.execute(
        select(WebSignalQuestion).where(WebSignalQuestion.owner_user_id == user_id, WebSignalQuestion.question.ilike(needle)).order_by(WebSignalQuestion.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in web_question_rows:
        hits.append(SearchHit(kind="web_signal_question", id=str(row.id), label=row.question, excerpt=row.provider_status, route="/universe/web-signals", created_at=row.created_at, provenance_label=row.provenance_label.lower()))
    web_note_rows = (await db.execute(
        select(WebSignalNote).where(WebSignalNote.owner_user_id == user_id, or_(WebSignalNote.title.ilike(needle), WebSignalNote.note.ilike(needle))).order_by(WebSignalNote.created_at.desc()).limit(max_rows)
    )).scalars().all()
    for row in web_note_rows:
        hits.append(SearchHit(kind="web_signal_note", id=str(row.id), label=row.title, excerpt=row.note, route="/universe/web-signals", created_at=row.created_at, provenance_label=row.provenance_label.lower()))
    hits.sort(key=lambda row: row.created_at, reverse=True)
    return hits[:max_rows]
