"""Hypotheses + experiments + outcomes (mandate E1/F3/F4): the honest
science loop — prediction, intervention, observed outcome, deterministic
revision with provenance."""
import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select

from app.api.deps import Identity, Scoped, require_csrf
from app.cognition.provenance import prediction_error, revise_hypothesis_from_outcome
from app.models import CognitiveEvent, Experiment, Hypothesis, Outcome, Plan, PlanStep
from app.observability.metrics import record_counter
from app.services.glow_service import award_glow_if_eligible
from app.services.timeline_service import record_observed_outcome

router = APIRouter(tags=["hypotheses"])


class HypothesisIn(BaseModel):
    question: str
    hypothesis_text: str
    prediction: dict = Field(default_factory=dict)
    alternative_hypotheses: list = Field(default_factory=list)
    orbit_id: uuid.UUID | None = None
    confidence: float = 0.5


class HypothesisOut(HypothesisIn):
    id: uuid.UUID
    status: str
    linked_refs: list
    created_at: dt.datetime
    model_config = {"from_attributes": True}


@router.post("/hypotheses", response_model=HypothesisOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_hypothesis(payload: HypothesisIn, db: Scoped, identity: Identity) -> HypothesisOut:
    user_id, _ = identity
    h = Hypothesis(owner_user_id=user_id, **payload.model_dump())
    db.add(h)
    await db.commit()
    return HypothesisOut.model_validate(h)


@router.get("/hypotheses", response_model=list[HypothesisOut])
async def list_hypotheses(db: Scoped, identity: Identity, status: str | None = None) -> list[HypothesisOut]:
    user_id, _ = identity
    q = select(Hypothesis).where(Hypothesis.owner_user_id == user_id).order_by(Hypothesis.created_at.desc()).limit(100)
    if status:
        q = q.where(Hypothesis.status == status)
    return [HypothesisOut.model_validate(h) for h in (await db.execute(q)).scalars()]


class HypothesisPatch(BaseModel):
    status: str | None = None
    confidence: float | None = None


@router.patch("/hypotheses/{hyp_id}", response_model=HypothesisOut, dependencies=[Depends(require_csrf)])
async def patch_hypothesis(hyp_id: uuid.UUID, payload: HypothesisPatch, db: Scoped, identity: Identity) -> HypothesisOut:
    user_id, _ = identity
    h = (await db.execute(select(Hypothesis).where(Hypothesis.id == hyp_id, Hypothesis.owner_user_id == user_id))).scalar_one_or_none()
    if not h:
        raise HTTPException(404, "Hypothesis not found.")
    if payload.status:
        h.status = payload.status
    if payload.confidence is not None:
        h.confidence = payload.confidence
    h.updated_at = dt.datetime.now(dt.timezone.utc)
    await db.commit()
    return HypothesisOut.model_validate(h)


class ExperimentIn(BaseModel):
    title: str
    intervention: str
    hypothesis_id: uuid.UUID | None = None
    orbit_id: uuid.UUID | None = None
    success_criteria: dict = Field(default_factory=dict)
    failure_criteria: dict = Field(default_factory=dict)


class ExperimentOut(ExperimentIn):
    id: uuid.UUID
    status: str
    created_at: dt.datetime
    model_config = {"from_attributes": True}


@router.post("/experiments", response_model=ExperimentOut, status_code=201, dependencies=[Depends(require_csrf)])
async def create_experiment(payload: ExperimentIn, db: Scoped, identity: Identity) -> ExperimentOut:
    user_id, _ = identity
    # F3: an experiment is only honest with a prediction and criteria
    if payload.hypothesis_id:
        h = (await db.execute(select(Hypothesis).where(Hypothesis.id == payload.hypothesis_id, Hypothesis.owner_user_id == user_id))).scalar_one_or_none()
        if not h:
            raise HTTPException(404, "Hypothesis not found.")
        if not h.prediction:
            raise HTTPException(422, "Linked hypothesis has no prediction; state one before experimenting.")
    if not payload.success_criteria:
        raise HTTPException(422, "success_criteria required: say what success would look like.")
    e = Experiment(owner_user_id=user_id, status="ACTIVE", **payload.model_dump())
    db.add(e)
    await db.commit()
    return ExperimentOut.model_validate(e)


@router.get("/experiments", response_model=list[ExperimentOut])
async def list_experiments(db: Scoped, identity: Identity) -> list[ExperimentOut]:
    user_id, _ = identity
    rows = (await db.execute(select(Experiment).where(Experiment.owner_user_id == user_id).order_by(Experiment.created_at.desc()).limit(100))).scalars()
    return [ExperimentOut.model_validate(e) for e in rows]


class OutcomeIn(BaseModel):
    observed_result: str
    structured_measurements: dict = Field(default_factory=dict)
    supports: bool | None = None
    rationale: str | None = None
    plan_step_id: uuid.UUID | None = None
    confidence: float | None = None


class OutcomeOut(BaseModel):
    id: uuid.UUID
    observed_result: str
    structured_measurements: dict
    difference_from_prediction: dict
    experiment_id: uuid.UUID | None
    plan_step_id: uuid.UUID | None
    created_at: dt.datetime
    hypothesis_confidence: float | None = None
    claim_status: str | None = None
    model_config = {"from_attributes": True}


@router.post("/experiments/{exp_id}/outcomes", response_model=OutcomeOut, status_code=201, dependencies=[Depends(require_csrf)])
async def report_outcome(exp_id: uuid.UUID, payload: OutcomeIn, request: Request, db: Scoped, identity: Identity) -> OutcomeOut:
    user_id, _ = identity
    e = (await db.execute(select(Experiment).where(Experiment.id == exp_id, Experiment.owner_user_id == user_id))).scalar_one_or_none()
    if not e:
        raise HTTPException(404, "Experiment not found.")
    h = None
    if e.hypothesis_id:
        h = (await db.execute(select(Hypothesis).where(Hypothesis.id == e.hypothesis_id))).scalar_one_or_none()
    diff = prediction_error(h.prediction if h else {}, payload.structured_measurements)
    o = Outcome(owner_user_id=user_id, experiment_id=e.id, plan_step_id=payload.plan_step_id,
                observed_result=payload.observed_result, structured_measurements=payload.structured_measurements,
                confidence=payload.confidence, difference_from_prediction=diff)
    db.add(o)
    await db.flush()
    claim = None
    if h is not None and payload.supports is not None:
        claim = await revise_hypothesis_from_outcome(
            db, owner_user_id=user_id, hypothesis=h, outcome=o,
            supports=payload.supports, rationale=payload.rationale or payload.observed_result[:200])
    db.add(CognitiveEvent(owner_user_id=user_id, event_kind="OUTCOME_REPORTED",
                          content_text=payload.observed_result[:400], source_ref=f"outcome:{o.id}",
                          structured_payload={"experiment_id": str(e.id), "difference_from_prediction": diff}))
    await record_observed_outcome(
        db,
        owner_user_id=user_id,
        outcome_id=o.id,
        observed_result=o.observed_result,
        occurred_at=o.created_at,
        orbit_id=e.orbit_id,
        provenance={
            "experiment_id": str(e.id),
            **({"hypothesis_id": str(e.hypothesis_id)} if e.hypothesis_id else {}),
        },
    )
    e.status = "COMPLETED"
    await award_glow_if_eligible(
        db,
        owner_user_id=user_id,
        event_type="outcome_returned",
        source_kind="OUTCOME",
        source_id=o.id,
        orbit_id=None,
        idempotency_key=f"outcome:{o.id}:returned",
    )
    record_counter(request, "nur_outcomes_total", (("source", "experiment"),))
    await db.commit()
    out = OutcomeOut.model_validate(o)
    out.hypothesis_confidence = h.confidence if h else None
    out.claim_status = claim.status if claim else None
    return out


@router.post("/outcomes", response_model=OutcomeOut, status_code=201, dependencies=[Depends(require_csrf)])
async def report_step_outcome(payload: OutcomeIn, request: Request, db: Scoped, identity: Identity) -> OutcomeOut:
    """F4 minimal loop: a finished plan step returns an observed outcome."""
    user_id, _ = identity
    if not payload.plan_step_id:
        raise HTTPException(422, "plan_step_id required for a step outcome.")
    step = (await db.execute(select(PlanStep).where(PlanStep.id == payload.plan_step_id, PlanStep.owner_user_id == user_id))).scalar_one_or_none()
    if not step:
        raise HTTPException(404, "Plan step not found.")
    o = Outcome(owner_user_id=user_id, plan_step_id=step.id, observed_result=payload.observed_result,
                structured_measurements=payload.structured_measurements, confidence=payload.confidence,
                difference_from_prediction={})
    db.add(o)
    db.add(CognitiveEvent(owner_user_id=user_id, event_kind="OUTCOME_REPORTED",
                          content_text=payload.observed_result[:400], source_ref=f"outcome_step:{step.id}"))
    await db.flush()
    plan = (await db.execute(select(Plan).where(
        Plan.id == step.plan_id,
        Plan.owner_user_id == user_id,
    ))).scalar_one()
    await record_observed_outcome(
        db,
        owner_user_id=user_id,
        outcome_id=o.id,
        observed_result=o.observed_result,
        occurred_at=o.created_at,
        orbit_id=plan.orbit_id,
        plan_id=plan.id,
        provenance={"plan_step_id": str(step.id)},
    )
    await award_glow_if_eligible(
        db,
        owner_user_id=user_id,
        event_type="outcome_returned",
        source_kind="OUTCOME",
        source_id=o.id,
        orbit_id=None,
        idempotency_key=f"outcome:{o.id}:returned",
    )
    record_counter(request, "nur_outcomes_total", (("source", "plan_step"),))
    await db.commit()
    return OutcomeOut.model_validate(o)
