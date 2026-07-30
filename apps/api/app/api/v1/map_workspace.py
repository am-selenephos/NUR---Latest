"""Map workspace — saved views, layout, semantic edges, candidates, evidence.

This router sits beside `map.py` under the same `/map` prefix. `map.py` owns the
composed graph and the existing focus/prediction routes and is left intact;
everything here is the part of Map that needs its own persistence.

Two boundaries are deliberate:

**Canonical writes stay canonical.** Adding a goal is `POST /api/v1/goals`.
Creating a decision is `POST /api/v1/orbits/{orbit_id}/decisions`. Recording an
outcome is `POST /api/v1/outcomes`. Map does not shadow any of them — it adds
only the option rows, blockers, edges, notes and layout that had no home.

**Nothing NUR proposes is applied by proposing it.** `/suggestions/generate`
writes rows with `status='PENDING'`, and only `/accept` turns one into a
confirmed edge or blocker. The graph carries candidates in `suggested_changes`,
never in `edges`, so a proposal cannot be mistaken for structure on the way to
the canvas.

One honest limitation, stated here because it shapes three endpoints: there is no
model provider wired into this repository, so `/problem`, `/path-comparison` and
`/decision-analysis` are **deterministic** — they frame, sequence and compare what
the owner's own ledger already contains, and label themselves
`DETERMINISTIC_FRAME`. They do not reason. Where a recommendation appears it is
derived from a priority the caller states, and the priority is returned as the
governing assumption so it can be disagreed with.
"""

from __future__ import annotations

import datetime as dt
import re
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select

from app.api.deps import Identity, Scoped, require_csrf
from app.api.v1.map import _map_snapshot
from app.living.catalog import SYSTEMS
from app.living.service import all_system_snapshots
from app.models import (
    Decision,
    Goal,
    MapAnnotation,
    MapBlocker,
    MapDecisionOption,
    MapEdge,
    MapLayout,
    MapSuggestion,
    MapView,
    Objective,
    Outcome,
    Plan,
    PlanStep,
    Prediction,
    ResearchSourceNote,
    ScheduledAction,
    TimelineEvent,
    WebSignalNote,
)
from app.models.map_layer import (
    ANNOTATION_SCOPES,
    BLOCKER_BASES,
    BLOCKER_CATEGORIES,
    BLOCKER_STATUSES,
    EDGE_DIRECTIONS,
    EDGE_TYPES,
    REF_TYPES,
    REVERSIBILITY,
    SENSITIVE_BLOCKER_CATEGORIES,
    VIEW_TYPES,
)

router = APIRouter(prefix="/map", tags=["map"])

SYSTEM_SLUGS = tuple(system.slug for system in SYSTEMS)


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────


class ViewIn(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    view_type: str
    root_entity_type: str | None = None
    root_entity_id: uuid.UUID | None = None
    filters: dict = Field(default_factory=dict)


class ViewPatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    filters: dict | None = None
    root_entity_type: str | None = None
    root_entity_id: uuid.UUID | None = None


class LayoutNodeIn(BaseModel):
    node_ref_type: str
    node_ref_id: str = Field(min_length=1, max_length=64)
    x: float
    y: float
    pinned: bool = False
    collapsed: bool = False
    layer: int = 0


class LayoutIn(BaseModel):
    viewport_key: str = Field(default="desktop", max_length=32)
    nodes: list[LayoutNodeIn]


class EdgeIn(BaseModel):
    source_ref_type: str
    source_ref_id: str = Field(min_length=1, max_length=64)
    target_ref_type: str
    target_ref_id: str = Field(min_length=1, max_length=64)
    edge_type: str
    direction: str = "DIRECTED"
    note: str | None = None


class EdgePatch(BaseModel):
    edge_type: str | None = None
    direction: str | None = None
    note: str | None = None
    user_confirmed: bool | None = None


class BlockerIn(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    description: str | None = None
    system_slug: str | None = None
    category: str = "PRACTICAL"
    basis: str = "USER_STATED"
    evidence: list[dict] = Field(default_factory=list)
    affects: list[dict] = Field(default_factory=list)
    possible_responses: list[str] = Field(default_factory=list)


class BlockerPatch(BaseModel):
    status: str | None = None
    confirmed_by_owner: bool | None = None
    resolution_note: str | None = None
    possible_responses: list[str] | None = None


class OptionIn(BaseModel):
    label: str = Field(min_length=1, max_length=300)
    summary: str | None = None
    benefits: list[str] = Field(default_factory=list)
    costs: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)
    predicted_consequences: str | None = None
    reversibility: str = "EASY"
    time_horizon: str | None = None
    effort: str | None = None


class AnnotationIn(BaseModel):
    entity_ref_type: str
    entity_ref_id: str = Field(min_length=1, max_length=64)
    body: str = Field(min_length=1)
    visibility_scope: str = "PRIVATE"


class ProblemIn(BaseModel):
    situation: str = Field(min_length=1)
    desired_outcome: str | None = None
    constraints: list[str] = Field(default_factory=list)
    resources: list[str] = Field(default_factory=list)
    unknowns: list[str] = Field(default_factory=list)
    system_slug: str | None = None


class PathComparisonIn(BaseModel):
    goal_id: uuid.UUID


class DecisionAnalysisIn(BaseModel):
    decision_id: uuid.UUID
    stated_priority: str | None = None


class PredictionResolveIn(BaseModel):
    resolution: str
    learning: str | None = None


class SuggestionRejectIn(BaseModel):
    suppress_kind: bool = False


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _require(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise HTTPException(
            422, f"{field} must be one of: {', '.join(allowed)}."
        )
    return value


def _view_out(row: MapView) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "view_type": row.view_type,
        "root_entity_type": row.root_entity_type,
        "root_entity_id": str(row.root_entity_id) if row.root_entity_id else None,
        "filters": row.filters,
        "is_default": row.is_default,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _edge_out(row: MapEdge) -> dict:
    return {
        "id": str(row.id),
        "source_ref_type": row.source_ref_type,
        "source_ref_id": row.source_ref_id,
        "target_ref_type": row.target_ref_type,
        "target_ref_id": row.target_ref_id,
        "edge_type": row.edge_type,
        "direction": row.direction,
        "user_confirmed": row.user_confirmed,
        "inference_source": row.inference_source,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "note": row.note,
        "created_at": row.created_at,
    }


def _blocker_out(row: MapBlocker) -> dict:
    return {
        "id": str(row.id),
        "title": row.title,
        "description": row.description,
        "system_slug": row.system_slug,
        "category": row.category,
        "basis": row.basis,
        "evidence": row.evidence,
        "affects": row.affects,
        "possible_responses": row.possible_responses,
        "status": row.status,
        "confirmed_by_owner": row.confirmed_by_owner,
        "resolved_at": row.resolved_at,
        "resolution_note": row.resolution_note,
        # The panel never presents an inferred sensitive blocker as established.
        "asserted_as_fact": row.basis != "NUR_INFERRED" or row.confirmed_by_owner,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _option_out(row: MapDecisionOption) -> dict:
    return {
        "id": str(row.id),
        "decision_id": str(row.decision_id),
        "label": row.label,
        "summary": row.summary,
        "benefits": row.benefits,
        "costs": row.costs,
        "risks": row.risks,
        "dependencies": row.dependencies,
        "evidence": row.evidence,
        "predicted_consequences": row.predicted_consequences,
        "reversibility": row.reversibility,
        "time_horizon": row.time_horizon,
        "effort": row.effort,
        "position": row.position,
        "chosen_at": row.chosen_at,
    }


def _suggestion_out(row: MapSuggestion) -> dict:
    return {
        "id": str(row.id),
        "suggestion_type": row.suggestion_type,
        "source_refs": row.source_refs,
        "proposed_payload": row.proposed_payload,
        "explanation": row.explanation,
        "may_be_wrong_about": row.may_be_wrong_about,
        "confidence": float(row.confidence) if row.confidence is not None else None,
        "status": row.status,
        "created_at": row.created_at,
        "reviewed_at": row.reviewed_at,
        "requires_acceptance": row.status == "PENDING",
    }


async def _owned_view(db: Scoped, owner_user_id: uuid.UUID, view_id: uuid.UUID) -> MapView:
    row = (await db.execute(select(MapView).where(
        MapView.id == view_id, MapView.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That Map view does not exist.")
    return row


async def _default_view(db: Scoped, owner_user_id: uuid.UUID) -> MapView:
    """The owner's Universe view, created on first use.

    Layout rows belong to a view, so a persisted position needs one to hang from.
    Creating it lazily keeps a fresh account from carrying furniture it never
    asked for.
    """
    row = (await db.execute(select(MapView).where(
        MapView.owner_user_id == owner_user_id, MapView.is_default.is_(True),
    ))).scalar_one_or_none()
    if row is not None:
        return row
    row = MapView(
        owner_user_id=owner_user_id,
        name="Universe",
        view_type="UNIVERSE",
        is_default=True,
    )
    db.add(row)
    await db.flush()
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Views
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/views")
async def list_views(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    default = await _default_view(db, owner_user_id)
    rows = (await db.execute(select(MapView).where(
        MapView.owner_user_id == owner_user_id,
    ).order_by(MapView.is_default.desc(), MapView.updated_at.desc()))).scalars().all()
    await db.commit()
    return {"items": [_view_out(row) for row in rows], "default_view_id": str(default.id)}


@router.post("/views", status_code=201, dependencies=[Depends(require_csrf)])
async def create_view(payload: ViewIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    _require(payload.view_type, VIEW_TYPES, "view_type")
    if payload.root_entity_type is not None:
        _require(payload.root_entity_type, REF_TYPES, "root_entity_type")
    if payload.view_type == "FOCUS" and (
        payload.root_entity_type is None or payload.root_entity_id is None
    ):
        raise HTTPException(
            422,
            "A Focus view needs the entity it is focused on: "
            "supply root_entity_type and root_entity_id.",
        )
    row = MapView(owner_user_id=owner_user_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = _view_out(row)
    await db.commit()
    return out


@router.get("/views/{view_id}")
async def get_view(view_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    return _view_out(await _owned_view(db, owner_user_id, view_id))


@router.patch("/views/{view_id}", dependencies=[Depends(require_csrf)])
async def patch_view(
    view_id: uuid.UUID, payload: ViewPatch, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_view(db, owner_user_id, view_id)
    data = payload.model_dump(exclude_unset=True)
    if "root_entity_type" in data and data["root_entity_type"] is not None:
        _require(data["root_entity_type"], REF_TYPES, "root_entity_type")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = dt.datetime.now(dt.UTC)
    await db.flush()
    out = _view_out(row)
    await db.commit()
    return out


@router.delete("/views/{view_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_view(view_id: uuid.UUID, db: Scoped, identity: Identity) -> None:
    owner_user_id, _ = identity
    row = await _owned_view(db, owner_user_id, view_id)
    if row.is_default:
        raise HTTPException(
            409,
            "The default Universe view cannot be deleted; it is where layout for "
            "the whole map is stored.",
        )
    await db.delete(row)
    await db.commit()


@router.get("/views/{view_id}/graph")
async def view_graph(view_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    """The composed graph, with this view's saved layout applied."""
    owner_user_id, _ = identity
    view = await _owned_view(db, owner_user_id, view_id)
    snapshot = await _map_snapshot(db, owner_user_id, view=view)
    snapshot["view"] = _view_out(view)
    return snapshot


@router.put("/views/{view_id}/layout", dependencies=[Depends(require_csrf)])
async def put_layout(
    view_id: uuid.UUID, payload: LayoutIn, db: Scoped, identity: Identity
) -> dict:
    """Persist node positions.

    Position is presentation. This writes x/y/pinned/collapsed/layer and nothing
    else, so dragging a goal next to Money cannot make it a Money goal — that
    stays an explicit change the owner is asked to confirm.
    """
    owner_user_id, _ = identity
    view = await _owned_view(db, owner_user_id, view_id)
    for node in payload.nodes:
        _require(node.node_ref_type, REF_TYPES, "node_ref_type")
    existing = {
        (row.node_ref_type, row.node_ref_id): row
        for row in (await db.execute(select(MapLayout).where(
            MapLayout.owner_user_id == owner_user_id,
            MapLayout.map_view_id == view.id,
            MapLayout.viewport_key == payload.viewport_key,
        ))).scalars().all()
    }
    written = 0
    for node in payload.nodes:
        key = (node.node_ref_type, node.node_ref_id)
        row = existing.get(key)
        if row is None:
            row = MapLayout(
                owner_user_id=owner_user_id,
                map_view_id=view.id,
                viewport_key=payload.viewport_key,
                node_ref_type=node.node_ref_type,
                node_ref_id=node.node_ref_id,
                x=node.x,
                y=node.y,
                pinned=node.pinned,
                collapsed=node.collapsed,
                layer=node.layer,
            )
            db.add(row)
        else:
            row.x, row.y = node.x, node.y
            row.pinned, row.collapsed, row.layer = (
                node.pinned, node.collapsed, node.layer
            )
            row.updated_at = dt.datetime.now(dt.UTC)
        written += 1
    await db.commit()
    return {
        "view_id": str(view.id),
        "viewport_key": payload.viewport_key,
        "nodes_written": written,
        "semantics_changed": False,
        "note": "Layout only. No System membership or relationship was altered.",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Semantic edges
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/edges", status_code=201, dependencies=[Depends(require_csrf)])
async def create_edge(payload: EdgeIn, db: Scoped, identity: Identity) -> dict:
    """An edge the owner drew. Owner-drawn means confirmed on arrival."""
    owner_user_id, _ = identity
    _require(payload.source_ref_type, REF_TYPES, "source_ref_type")
    _require(payload.target_ref_type, REF_TYPES, "target_ref_type")
    _require(payload.edge_type, EDGE_TYPES, "edge_type")
    _require(payload.direction, EDGE_DIRECTIONS, "direction")
    if (payload.source_ref_type, payload.source_ref_id) == (
        payload.target_ref_type, payload.target_ref_id
    ):
        raise HTTPException(422, "An object cannot be connected to itself.")
    existing = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
        MapEdge.source_ref_type == payload.source_ref_type,
        MapEdge.source_ref_id == payload.source_ref_id,
        MapEdge.target_ref_type == payload.target_ref_type,
        MapEdge.target_ref_id == payload.target_ref_id,
        MapEdge.edge_type == payload.edge_type,
    ))).scalar_one_or_none()
    if existing is not None:
        raise HTTPException(409, "That connection already exists on the Map.")
    row = MapEdge(
        owner_user_id=owner_user_id, user_confirmed=True, **payload.model_dump()
    )
    db.add(row)
    await db.flush()
    out = _edge_out(row)
    await db.commit()
    return out


@router.patch("/edges/{edge_id}", dependencies=[Depends(require_csrf)])
async def patch_edge(
    edge_id: uuid.UUID, payload: EdgePatch, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(MapEdge).where(
        MapEdge.id == edge_id, MapEdge.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That connection does not exist.")
    data = payload.model_dump(exclude_unset=True)
    if "edge_type" in data:
        _require(data["edge_type"], EDGE_TYPES, "edge_type")
    if "direction" in data:
        _require(data["direction"], EDGE_DIRECTIONS, "direction")
    if data.get("user_confirmed") is False and row.inference_source is None:
        raise HTTPException(
            422,
            "An owner-drawn connection cannot be un-confirmed: it has no "
            "inference to fall back to.",
        )
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = dt.datetime.now(dt.UTC)
    await db.flush()
    out = _edge_out(row)
    await db.commit()
    return out


@router.delete("/edges/{edge_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_edge(edge_id: uuid.UUID, db: Scoped, identity: Identity) -> None:
    owner_user_id, _ = identity
    row = (await db.execute(select(MapEdge).where(
        MapEdge.id == edge_id, MapEdge.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That connection does not exist.")
    await db.delete(row)
    await db.commit()


@router.get("/edges")
async def list_edges(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
    ).order_by(MapEdge.created_at.desc()))).scalars().all()
    return {
        "items": [_edge_out(row) for row in rows],
        "confirmed": sum(1 for row in rows if row.user_confirmed),
        "candidates": sum(1 for row in rows if not row.user_confirmed),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Blockers
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/blockers", status_code=201, dependencies=[Depends(require_csrf)])
async def create_blocker(payload: BlockerIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    _require(payload.category, BLOCKER_CATEGORIES, "category")
    _require(payload.basis, BLOCKER_BASES, "basis")
    if payload.system_slug is not None and payload.system_slug not in SYSTEM_SLUGS:
        raise HTTPException(404, f"No System named '{payload.system_slug}'.")
    if payload.basis == "NUR_INFERRED" and not payload.evidence:
        raise HTTPException(
            422,
            "An inferred blocker must carry the evidence it was inferred from.",
        )
    # §20. NUR may propose that something emotional is in the way; it may not
    # record it as established. The row stays PROPOSED until the owner agrees.
    sensitive = (
        payload.basis == "NUR_INFERRED"
        and payload.category in SENSITIVE_BLOCKER_CATEGORIES
    )
    status = "PROPOSED" if sensitive or payload.basis == "NUR_INFERRED" else "OPEN"
    row = MapBlocker(
        owner_user_id=owner_user_id,
        status=status,
        confirmed_by_owner=payload.basis == "USER_STATED",
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    out = _blocker_out(row)
    await db.commit()
    return out


@router.get("/blockers")
async def list_blockers(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = (await db.execute(select(MapBlocker).where(
        MapBlocker.owner_user_id == owner_user_id,
    ).order_by(MapBlocker.updated_at.desc()))).scalars().all()
    return {"items": [_blocker_out(row) for row in rows]}


@router.patch("/blockers/{blocker_id}", dependencies=[Depends(require_csrf)])
async def patch_blocker(
    blocker_id: uuid.UUID, payload: BlockerPatch, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(MapBlocker).where(
        MapBlocker.id == blocker_id, MapBlocker.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That blocker does not exist.")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        _require(data["status"], BLOCKER_STATUSES, "status")
    if data.get("confirmed_by_owner") is True:
        row.confirmed_by_owner = True
    if data.get("status") == "RESOLVED":
        row.resolved_at = dt.datetime.now(dt.UTC)
    # Confirming a sensitive inferred blocker is the owner's act, so promoting it
    # out of PROPOSED requires that confirmation to have happened.
    if (
        data.get("status") == "OPEN"
        and row.basis == "NUR_INFERRED"
        and row.category in SENSITIVE_BLOCKER_CATEGORIES
        and not row.confirmed_by_owner
    ):
        raise HTTPException(
            422,
            "NUR inferred this and it concerns how you feel or relate. Confirm it "
            "is real before it is treated as a blocker.",
        )
    for key, value in data.items():
        if key == "confirmed_by_owner":
            continue
        setattr(row, key, value)
    row.updated_at = dt.datetime.now(dt.UTC)
    await db.flush()
    out = _blocker_out(row)
    await db.commit()
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Decision options
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/decisions")
async def list_decisions(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    decisions = (await db.execute(select(Decision).where(
        Decision.owner_user_id == owner_user_id,
    ).order_by(Decision.created_at.desc()))).scalars().all()
    ids = [row.id for row in decisions]
    options = (await db.execute(select(MapDecisionOption).where(
        MapDecisionOption.owner_user_id == owner_user_id,
        MapDecisionOption.decision_id.in_(ids),
    ).order_by(MapDecisionOption.position))).scalars().all() if ids else []
    grouped: dict[uuid.UUID, list[dict]] = {}
    for option in options:
        grouped.setdefault(option.decision_id, []).append(_option_out(option))
    return {
        "items": [
            {
                "id": str(row.id),
                "statement": row.statement,
                "rationale": row.rationale,
                "status": row.status,
                "options": grouped.get(row.id, []),
                "resolved": any(
                    option["chosen_at"] for option in grouped.get(row.id, [])
                ),
                "created_at": row.created_at,
            }
            for row in decisions
        ]
    }


@router.post(
    "/decisions/{decision_id}/options",
    status_code=201,
    dependencies=[Depends(require_csrf)],
)
async def add_option(
    decision_id: uuid.UUID, payload: OptionIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    _require(payload.reversibility, REVERSIBILITY, "reversibility")
    decision = (await db.execute(select(Decision).where(
        Decision.id == decision_id, Decision.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if decision is None:
        raise HTTPException(404, "That decision does not exist.")
    position = int((await db.execute(select(
        func.coalesce(func.max(MapDecisionOption.position), -1)
    ).where(MapDecisionOption.decision_id == decision_id))).scalar_one()) + 1
    row = MapDecisionOption(
        owner_user_id=owner_user_id,
        decision_id=decision_id,
        position=position,
        **payload.model_dump(),
    )
    db.add(row)
    await db.flush()
    out = _option_out(row)
    await db.commit()
    return out


@router.post(
    "/decisions/{decision_id}/choose/{option_id}",
    dependencies=[Depends(require_csrf)],
)
async def choose_option(
    decision_id: uuid.UUID,
    option_id: uuid.UUID,
    db: Scoped,
    identity: Identity,
) -> dict:
    """The owner resolves the fork. NUR never writes this."""
    owner_user_id, _ = identity
    options = (await db.execute(select(MapDecisionOption).where(
        MapDecisionOption.owner_user_id == owner_user_id,
        MapDecisionOption.decision_id == decision_id,
    ))).scalars().all()
    if not options:
        raise HTTPException(404, "That decision has no options to choose between.")
    target = next((row for row in options if row.id == option_id), None)
    if target is None:
        raise HTTPException(404, "That option does not belong to this decision.")
    already = next(
        (row for row in options if row.chosen_at is not None and row.id != option_id),
        None,
    )
    if already is not None:
        raise HTTPException(
            409,
            f"This decision was already resolved as '{already.label}'. "
            "Clear that choice before choosing again.",
        )
    now = dt.datetime.now(dt.UTC)
    target.chosen_at = now
    decision = (await db.execute(select(Decision).where(
        Decision.id == decision_id, Decision.owner_user_id == owner_user_id,
    ))).scalar_one()
    decision.status = "HELD"
    decision.decided_at = now
    await db.flush()
    out = _option_out(target)
    await db.commit()
    return {"option": out, "decision_id": str(decision_id), "resolved": True}


# ──────────────────────────────────────────────────────────────────────────────
# Annotations
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/annotations", status_code=201, dependencies=[Depends(require_csrf)])
async def create_annotation(
    payload: AnnotationIn, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    _require(payload.entity_ref_type, REF_TYPES, "entity_ref_type")
    _require(payload.visibility_scope, ANNOTATION_SCOPES, "visibility_scope")
    row = MapAnnotation(owner_user_id=owner_user_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = {
        "id": str(row.id),
        "entity_ref_type": row.entity_ref_type,
        "entity_ref_id": row.entity_ref_id,
        "body": row.body,
        "visibility_scope": row.visibility_scope,
        "created_at": row.created_at,
    }
    await db.commit()
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Suggestions — proposals, never applied by proposing
# ──────────────────────────────────────────────────────────────────────────────


def _normalise(title: str) -> str:
    return re.sub(r"\s+", " ", title.strip().lower())


async def _derive_suggestions(
    db: Scoped, owner_user_id: uuid.UUID
) -> list[dict]:
    """Derive candidates from the owner's own rows, deterministically.

    Every candidate here is reproducible: it names the exact rows it was read
    from, so "Why?" can be answered without a model and without invention. This
    is not analysis — it is pattern-matching over the ledger, and each candidate
    carries what it might be wrong about because a duplicate title or a shared
    deadline has innocent explanations.
    """
    found: list[dict] = []

    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id, Goal.status == "ACTIVE",
    ))).scalars().all()
    plans = (await db.execute(select(Plan).where(
        Plan.owner_user_id == owner_user_id,
    ))).scalars().all()

    # Two active goals in one System with target dates inside a week of each
    # other are competing for the same attention.
    by_system: dict[str, list[Goal]] = {}
    for goal in goals:
        by_system.setdefault(goal.system_slug, []).append(goal)
    for slug, rows in by_system.items():
        dated = [row for row in rows if row.target_date is not None]
        for i, first in enumerate(dated):
            for second in dated[i + 1:]:
                gap = abs((first.target_date - second.target_date).days)
                if gap > 7:
                    continue
                found.append({
                    "suggestion_type": "CONFLICTING_GOAL",
                    "source_refs": [
                        {"type": "goal", "id": str(first.id)},
                        {"type": "goal", "id": str(second.id)},
                    ],
                    "proposed_payload": {
                        "system_slug": slug,
                        "goal_ids": [str(first.id), str(second.id)],
                        "days_apart": gap,
                    },
                    "explanation": (
                        f"'{first.title}' and '{second.title}' are both active in "
                        f"{slug} and their target dates are {gap} day"
                        f"{'s' if gap != 1 else ''} apart. Finishing both to that "
                        "standard may not be possible at once."
                    ),
                    "may_be_wrong_about": (
                        "These may be genuinely independent, or one date may be "
                        "soft. A shared deadline is not proof of conflict."
                    ),
                    "confidence": 0.5,
                })

    # Two plans with the same normalised title are probably one plan twice.
    seen: dict[str, Plan] = {}
    for plan in plans:
        key = _normalise(plan.title)
        if key in seen:
            found.append({
                "suggestion_type": "DUPLICATE_PLAN",
                "source_refs": [
                    {"type": "plan", "id": str(seen[key].id)},
                    {"type": "plan", "id": str(plan.id)},
                ],
                "proposed_payload": {
                    "plan_ids": [str(seen[key].id), str(plan.id)],
                    "title": plan.title,
                },
                "explanation": (
                    f"Two plans are titled '{plan.title}'. One of them may be a "
                    "leftover that is quietly splitting your progress."
                ),
                "may_be_wrong_about": (
                    "They may be deliberately separate runs of the same plan for "
                    "different periods."
                ),
                "confidence": 0.6,
            })
        else:
            seen[key] = plan

    # An open prediction past its review date is an assumption nobody checked.
    now = dt.datetime.now(dt.UTC)
    stale = (await db.execute(select(Prediction).where(
        Prediction.owner_user_id == owner_user_id,
        Prediction.status == "OPEN",
        Prediction.review_by.isnot(None),
        Prediction.review_by < now,
    ))).scalars().all()
    for row in stale:
        overdue = (now - row.review_by).days
        found.append({
            "suggestion_type": "STALE_ASSUMPTION",
            "source_refs": [{"type": "prediction", "id": str(row.id)}],
            "proposed_payload": {"prediction_id": str(row.id), "days_overdue": overdue},
            "explanation": (
                f"This prediction was due for review {overdue} day"
                f"{'s' if overdue != 1 else ''} ago and is still open: "
                f"'{row.statement}'. Until it is reviewed, anything resting on it "
                "is resting on an unchecked assumption."
            ),
            "may_be_wrong_about": (
                "The review date may have been optimistic rather than meaningful."
            ),
            "confidence": 0.7,
        })

    # A System carrying active goals but no returned outcome, while another has
    # returned several, is an imbalance worth seeing — not a verdict.
    systems = await all_system_snapshots(db, owner_user_id=owner_user_id)
    moving = [
        row for row in systems if row["progress_sources"]["outcomes_returned"] > 0
    ]
    if moving:
        for row in systems:
            if row["active_goal_count"] == 0:
                continue
            if row["progress_sources"]["outcomes_returned"] > 0:
                continue
            found.append({
                "suggestion_type": "SYSTEM_IMBALANCE",
                "source_refs": [
                    {"type": "system", "id": row["slug"]},
                    *[{"type": "system", "id": other["slug"]} for other in moving[:2]],
                ],
                "proposed_payload": {
                    "stalled_system": row["slug"],
                    "moving_systems": [other["slug"] for other in moving[:2]],
                },
                "explanation": (
                    f"{row['title']} holds {row['active_goal_count']} active goal"
                    f"{'s' if row['active_goal_count'] != 1 else ''} and has "
                    "returned no outcome, while "
                    + ", ".join(other["title"] for other in moving[:2])
                    + " has. Attention may have moved without the goals moving with it."
                ),
                "may_be_wrong_about": (
                    "This may be a deliberate season of focus elsewhere, which is "
                    "a choice rather than an imbalance."
                ),
                "confidence": 0.45,
            })

    return found


@router.get("/suggestions")
async def list_suggestions(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = (await db.execute(select(MapSuggestion).where(
        MapSuggestion.owner_user_id == owner_user_id,
    ).order_by(MapSuggestion.created_at.desc()).limit(200))).scalars().all()
    return {
        "items": [_suggestion_out(row) for row in rows],
        "pending": sum(1 for row in rows if row.status == "PENDING"),
        "provenance_label": "DETERMINISTIC_LEDGER_DERIVED",
        "note": (
            "Every suggestion names the rows it was read from and states what it "
            "may be wrong about. None is applied until accepted."
        ),
    }


@router.post("/suggestions/generate", dependencies=[Depends(require_csrf)])
async def generate_suggestions(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    derived = await _derive_suggestions(db, owner_user_id)
    existing = (await db.execute(select(MapSuggestion).where(
        MapSuggestion.owner_user_id == owner_user_id,
    ))).scalars().all()
    # A kind the owner asked never to see again stays unasked.
    suppressed = {row.suggestion_type for row in existing if row.suppressed_kind}
    live = {
        (row.suggestion_type, str(sorted(
            (ref.get("id") for ref in row.source_refs if isinstance(ref, dict)),
            key=lambda value: value or "",
        )))
        for row in existing
        if row.status in {"PENDING", "REJECTED", "ACCEPTED"}
    }
    created = 0
    for candidate in derived:
        if candidate["suggestion_type"] in suppressed:
            continue
        key = (candidate["suggestion_type"], str(sorted(
            (ref.get("id") for ref in candidate["source_refs"]),
            key=lambda value: value or "",
        )))
        if key in live:
            continue
        db.add(MapSuggestion(owner_user_id=owner_user_id, **candidate))
        created += 1
    # Read back before committing, not after. `app.current_user_id` is set with
    # `set_config(..., true)` and is therefore transaction-local: committing here
    # would drop the RLS context and the reload would return zero rows under
    # FORCE ROW LEVEL SECURITY — the response would report `created: 1` beside an
    # empty list, which is how this was caught.
    await db.flush()
    rows = (await db.execute(select(MapSuggestion).where(
        MapSuggestion.owner_user_id == owner_user_id,
        MapSuggestion.status == "PENDING",
    ).order_by(MapSuggestion.created_at.desc()))).scalars().all()
    items = [_suggestion_out(row) for row in rows]
    await db.commit()
    return {
        "created": created,
        "suppressed_kinds": sorted(suppressed),
        "items": items,
        "provenance_label": "DETERMINISTIC_LEDGER_DERIVED",
        "requires_acceptance": True,
        "note": (
            "Derived by pattern-matching the owner's own rows. No model was "
            "consulted and nothing was applied."
        ),
    }


@router.post("/suggestions/{suggestion_id}/accept", dependencies=[Depends(require_csrf)])
async def accept_suggestion(
    suggestion_id: uuid.UUID, db: Scoped, identity: Identity
) -> dict:
    """Accepting is the only thing that turns a proposal into part of the Map."""
    owner_user_id, _ = identity
    row = (await db.execute(select(MapSuggestion).where(
        MapSuggestion.id == suggestion_id,
        MapSuggestion.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That suggestion does not exist.")
    if row.status != "PENDING":
        raise HTTPException(409, f"That suggestion was already {row.status.lower()}.")
    created: dict | None = None
    if row.suggestion_type in {"CONNECTION", "DEPENDENCY"}:
        payload = row.proposed_payload or {}
        required = {
            "source_ref_type", "source_ref_id", "target_ref_type", "target_ref_id",
        }
        if not required <= set(payload):
            raise HTTPException(
                422,
                "This suggestion does not describe a connection precisely enough "
                "to create; open it and draw the connection instead.",
            )
        edge = MapEdge(
            owner_user_id=owner_user_id,
            source_ref_type=payload["source_ref_type"],
            source_ref_id=str(payload["source_ref_id"]),
            target_ref_type=payload["target_ref_type"],
            target_ref_id=str(payload["target_ref_id"]),
            edge_type=payload.get("edge_type", "DEPENDS_ON"),
            user_confirmed=True,
            inference_source=f"map_suggestion:{row.id}",
            confidence=row.confidence,
        )
        db.add(edge)
        await db.flush()
        created = {"kind": "edge", "id": str(edge.id)}
    row.status = "ACCEPTED"
    row.reviewed_at = dt.datetime.now(dt.UTC)
    await db.flush()
    out = _suggestion_out(row)
    await db.commit()
    return {
        "suggestion": out,
        "created": created,
        "note": (
            "Accepted. Suggestions of other kinds record your agreement without "
            "creating an object, because what to change is yours to decide."
        ),
    }


@router.post("/suggestions/{suggestion_id}/reject", dependencies=[Depends(require_csrf)])
async def reject_suggestion(
    suggestion_id: uuid.UUID,
    payload: SuggestionRejectIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(MapSuggestion).where(
        MapSuggestion.id == suggestion_id,
        MapSuggestion.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That suggestion does not exist.")
    if row.status != "PENDING":
        raise HTTPException(409, f"That suggestion was already {row.status.lower()}.")
    row.status = "REJECTED"
    row.reviewed_at = dt.datetime.now(dt.UTC)
    row.suppressed_kind = payload.suppress_kind
    await db.flush()
    out = _suggestion_out(row)
    await db.commit()
    return {
        "suggestion": out,
        "kind_suppressed": payload.suppress_kind,
        "note": (
            "This kind of suggestion will not be raised again."
            if payload.suppress_kind
            else "Rejected. The evidence stays on record."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Map a Problem — deterministic framing, not model reasoning
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/problem", status_code=201, dependencies=[Depends(require_csrf)])
async def map_problem(payload: ProblemIn, db: Scoped, identity: Identity) -> dict:
    """Turn a described situation into a structured, reviewable fork.

    What this does honestly: it records the situation, the outcome that matters,
    the constraints and the resources, then creates a canonical `decisions` row
    with option rows generated from **structural** responses to a constraint —
    reduce the scope, defer, substitute the missing resource, proceed with a
    fallback. Each option is a frame the owner edits or deletes.

    What it does not do: reason about the specific problem. There is no provider
    wired in, so no route in this repository produces model-authored paths, and
    labelling a template as analysis would be the lie this whole surface exists
    to avoid. `provenance_label` says so on every response.
    """
    owner_user_id, _ = identity
    slug = payload.system_slug
    if slug is not None and slug not in SYSTEM_SLUGS:
        raise HTTPException(404, f"No System named '{slug}'.")

    from app.living.catalog import require_system
    from app.living.service import owned_system_orbit

    definition = require_system(slug or SYSTEM_SLUGS[0])
    orbit = await owned_system_orbit(
        db, owner_user_id=owner_user_id, system=definition
    )
    outcome = payload.desired_outcome or "Not yet stated"
    decision = Decision(
        owner_user_id=owner_user_id,
        orbit_id=orbit.id,
        statement=payload.situation,
        rationale=(
            f"Desired outcome: {outcome}. "
            f"Constraints: {'; '.join(payload.constraints) or 'none stated'}. "
            f"Resources: {'; '.join(payload.resources) or 'none stated'}. "
            f"Unknowns: {'; '.join(payload.unknowns) or 'none stated'}."
        ),
        status="HELD",
    )
    db.add(decision)
    await db.flush()

    frames: list[tuple[str, str, str, str]] = [
        (
            "Reduce the scope",
            "Deliver a smaller version that still reaches the outcome.",
            "EASY",
            "Less is finished, and the smaller result may not satisfy the outcome.",
        ),
        (
            "Defer until a constraint lifts",
            "Wait for the binding constraint to change before spending anything.",
            "EASY",
            "Nothing moves meanwhile, and the constraint may not lift on its own.",
        ),
    ]
    if payload.resources:
        frames.append((
            "Substitute a resource you already have",
            "Use "
            + ", ".join(payload.resources[:3])
            + " in place of what is missing.",
            "COSTLY",
            "The substitute may cost more elsewhere than the original would have.",
        ))
    if payload.constraints:
        frames.append((
            "Proceed with a fallback",
            "Accept the constraint and commit to a route that survives it: "
            + payload.constraints[0],
            "COSTLY",
            "Committing under the constraint can be expensive to unwind.",
        ))

    created = []
    for position, (label, summary, reversibility, risk) in enumerate(frames):
        option = MapDecisionOption(
            owner_user_id=owner_user_id,
            decision_id=decision.id,
            label=label,
            summary=summary,
            reversibility=reversibility,
            risks=[risk],
            dependencies=list(payload.constraints[:3]),
            position=position,
        )
        db.add(option)
        created.append(option)
    await db.flush()
    options = [_option_out(row) for row in created]
    decision_id = str(decision.id)
    await db.commit()
    return {
        "decision_id": decision_id,
        "situation": payload.situation,
        "desired_outcome": payload.desired_outcome,
        "constraints": payload.constraints,
        "resources": payload.resources,
        "unknowns": payload.unknowns,
        "options": options,
        "provenance_label": "DETERMINISTIC_FRAME",
        "is_model_generated": False,
        "note": (
            "These are structural frames, not NUR's analysis of your situation. "
            "No model produced them. Edit or delete any of them; nothing here is "
            "canonical until you choose one."
        ),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Path comparison and decision analysis
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/path-comparison", dependencies=[Depends(require_csrf)])
async def path_comparison(
    payload: PathComparisonIn, db: Scoped, identity: Identity
) -> dict:
    """Compare the real routes toward one goal.

    A "path" here is an actual `plans` row associated with the goal's System, and
    its milestones are that plan's real steps. Effort and time are reported as
    counts and horizons the ledger holds — step counts, scheduled dates — never as
    invented scores, because §19 says avoid fake numerical precision and a
    confidence decimal on a route nobody has walked is exactly that.
    """
    owner_user_id, _ = identity
    goal = (await db.execute(select(Goal).where(
        Goal.id == payload.goal_id, Goal.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if goal is None:
        raise HTTPException(404, "That goal does not exist.")

    objectives = (await db.execute(select(Objective).where(
        Objective.owner_user_id == owner_user_id, Objective.goal_id == goal.id,
    ).order_by(Objective.created_at))).scalars().all()
    plans = (await db.execute(select(Plan).where(
        Plan.owner_user_id == owner_user_id, Plan.orbit_id == goal.orbit_id,
    ).order_by(Plan.created_at))).scalars().all()
    plan_ids = [row.id for row in plans]
    steps = (await db.execute(select(PlanStep).where(
        PlanStep.owner_user_id == owner_user_id, PlanStep.plan_id.in_(plan_ids),
    ).order_by(PlanStep.position))).scalars().all() if plan_ids else []
    steps_by_plan: dict[uuid.UUID, list[PlanStep]] = {}
    for step in steps:
        steps_by_plan.setdefault(step.plan_id, []).append(step)

    blockers = (await db.execute(select(MapBlocker).where(
        MapBlocker.owner_user_id == owner_user_id,
        MapBlocker.status.in_(["OPEN", "PROPOSED"]),
    ))).scalars().all()
    goal_ref = f"goal:{goal.id}"
    relevant = [
        row for row in blockers
        if row.system_slug == goal.system_slug
        or any(
            isinstance(ref, dict) and f"{ref.get('type')}:{ref.get('id')}" == goal_ref
            for ref in (row.affects or [])
        )
    ]
    scheduled = (await db.execute(select(ScheduledAction).where(
        ScheduledAction.owner_user_id == owner_user_id,
        ScheduledAction.goal_id == goal.id,
    ).order_by(ScheduledAction.scheduled_for))).scalars().all()
    dependencies = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
        MapEdge.edge_type.in_(["DEPENDS_ON", "BLOCKS"]),
        MapEdge.user_confirmed.is_(True),
    ))).scalars().all()

    lanes = []
    for plan in plans:
        own = steps_by_plan.get(plan.id, [])
        done = sum(1 for row in own if row.done)
        first_open = next((row for row in own if not row.done), None)
        lanes.append({
            "path_id": f"plan:{plan.id}",
            "name": plan.title,
            "strategy": f"Plan '{plan.title}' ({plan.status.lower()})",
            "first_step": first_open.title if first_open else None,
            "milestones": [
                {"title": row.title, "done": row.done, "done_at": row.done_at}
                for row in own
            ],
            "step_count": len(own),
            "steps_done": done,
            "effort": (
                "Not assessed" if not own
                else f"{len(own) - done} step{'s' if len(own) - done != 1 else ''} remaining"
            ),
            "time_horizon": (
                goal.target_date.isoformat() if goal.target_date else "No target date"
            ),
            "blockers": [
                {"id": str(row.id), "title": row.title, "status": row.status}
                for row in relevant
            ],
            "dependencies": [
                {
                    "edge_type": row.edge_type,
                    "source": f"{row.source_ref_type}:{row.source_ref_id}",
                    "target": f"{row.target_ref_type}:{row.target_ref_id}",
                }
                for row in dependencies
                if f"{row.target_ref_type}:{row.target_ref_id}" == f"plan:{plan.id}"
                or f"{row.source_ref_type}:{row.source_ref_id}" == f"plan:{plan.id}"
            ],
            "uncertainty": (
                "No step has been completed yet, so nothing about this route has "
                "been tested." if done == 0
                else f"{done} of {len(own)} steps completed, so the early part of "
                "this route is evidenced and the rest is not."
            ),
            # Reversibility is a judgement; it is only reported where the owner
            # actually recorded one against a decision option.
            "reversibility": "Not assessed",
            "expected_outcome": None,
            "fallback": None,
            "exit_points": [
                {"after_step": row.title}
                for row in own if row.done
            ][-1:],
            "evidence_strength": (
                "Weak — no completed step" if done == 0
                else "Partial — completed steps only"
            ),
        })

    return {
        "goal": {
            "id": str(goal.id),
            "title": goal.title,
            "system_slug": goal.system_slug,
            "progress_percent": goal.progress_percent,
            "target_date": goal.target_date,
            "objective_count": len(objectives),
        },
        "paths": lanes,
        "path_count": len(lanes),
        "shared_blockers": [
            {
                "id": str(row.id),
                "title": row.title,
                "status": row.status,
                "basis": row.basis,
                "asserted_as_fact": (
                    row.basis != "NUR_INFERRED" or row.confirmed_by_owner
                ),
            }
            for row in relevant
        ],
        "scheduled": [
            {"title": row.title, "scheduled_for": row.scheduled_for, "status": row.status}
            for row in scheduled
        ],
        "provenance_label": "DETERMINISTIC_FRAME",
        "is_model_generated": False,
        # Stated because it is a real limitation of the data model, not a choice:
        # nothing in NUR links a plan to a goal directly.
        "association_basis": (
            "Plans are treated as routes toward this goal because they belong to "
            "the same System. There is no plan-to-goal link in NUR to read."
        ),
        "note": (
            "Routes are the plans that already exist in this goal's System. Where "
            "a dimension has not been measured it says so rather than showing a "
            "number."
            if lanes
            else "No plan exists in this goal's System yet, so there is no route "
            "to compare. Create a plan to compare routes."
        ),
    }


@router.post("/decision-analysis", dependencies=[Depends(require_csrf)])
async def decision_analysis(
    payload: DecisionAnalysisIn, db: Scoped, identity: Identity
) -> dict:
    """Lay out a decision's options side by side, and expose the assumption.

    A recommendation only appears when the caller states the priority it should
    be judged against, and the priority is returned as `governing_assumption` so
    the recommendation can be rejected by rejecting the assumption. With no
    priority stated there is no recommendation — silence is the honest output.
    """
    owner_user_id, _ = identity
    decision = (await db.execute(select(Decision).where(
        Decision.id == payload.decision_id, Decision.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if decision is None:
        raise HTTPException(404, "That decision does not exist.")
    options = (await db.execute(select(MapDecisionOption).where(
        MapDecisionOption.owner_user_id == owner_user_id,
        MapDecisionOption.decision_id == decision.id,
    ).order_by(MapDecisionOption.position))).scalars().all()

    dimensions = [
        ("Reversibility", lambda row: row.reversibility.replace("_", " ").title()),
        ("Time horizon", lambda row: row.time_horizon or "Not stated"),
        ("Effort", lambda row: row.effort or "Not stated"),
        ("Benefits recorded", lambda row: str(len(row.benefits or []))),
        ("Costs recorded", lambda row: str(len(row.costs or []))),
        ("Risks recorded", lambda row: str(len(row.risks or []))),
        ("Evidence attached", lambda row: str(len(row.evidence or []))),
    ]
    matrix = [
        {
            "dimension": name,
            "values": {str(row.id): read(row) for row in options},
        }
        for name, read in dimensions
    ]

    recommendation: dict | None = None
    if payload.stated_priority and options:
        priority = payload.stated_priority.strip().lower()
        if priority in {"reversibility", "safety", "reversible"}:
            order = {"EASY": 0, "COSTLY": 1, "MOSTLY_IRREVERSIBLE": 2}
            pick = min(options, key=lambda row: order[row.reversibility])
            because = (
                f"'{pick.label}' is the easiest of these to walk back "
                f"({pick.reversibility.replace('_', ' ').lower()})."
            )
        elif priority in {"evidence", "proof", "certainty"}:
            pick = max(options, key=lambda row: len(row.evidence or []))
            because = (
                f"'{pick.label}' has the most evidence attached "
                f"({len(pick.evidence or [])} item"
                f"{'s' if len(pick.evidence or []) != 1 else ''})."
            )
        elif priority in {"speed", "fast", "time"}:
            pick = next(
                (row for row in options if row.time_horizon), options[0]
            )
            because = (
                f"'{pick.label}' is the only option with a stated time horizon."
                if pick.time_horizon
                else "No option states a time horizon, so this is the first option "
                "rather than the fastest."
            )
        else:
            pick = None
            because = ""
        if pick is not None:
            recommendation = {
                "option_id": str(pick.id),
                "label": pick.label,
                "because": because,
                "changes_if": (
                    "This recommendation changes if your priority is not "
                    f"'{payload.stated_priority}'."
                ),
            }

    return {
        "decision": {
            "id": str(decision.id),
            "statement": decision.statement,
            "rationale": decision.rationale,
            "status": decision.status,
            "resolved": any(row.chosen_at for row in options),
        },
        "options": [_option_out(row) for row in options],
        "comparison_matrix": matrix,
        "recommendation": recommendation,
        "governing_assumption": payload.stated_priority,
        "provenance_label": "DETERMINISTIC_FRAME",
        "is_model_generated": False,
        "note": (
            "The matrix counts what you recorded against each option. Nothing is "
            "scored."
            if payload.stated_priority
            else "No priority was stated, so no option is recommended. Say what "
            "matters most and the comparison can be ordered against it."
        ),
        "decides_for_you": False,
    }


# ──────────────────────────────────────────────────────────────────────────────
# Per-entity evidence, activity and predictions
# ──────────────────────────────────────────────────────────────────────────────

#: How a piece of evidence should be read. §23 requires these to stay separable:
#: a direct fact and a model inference must never render identically.
EVIDENCE_CLASSES = {
    "DIRECT_FACT",
    "USER_INTERPRETATION",
    "MODEL_INFERENCE",
    "EXTERNAL_SOURCE",
    "PREDICTION",
    "UNRESOLVED_CLAIM",
}


@router.get("/entities/{entity_type}/{entity_id}/evidence")
async def entity_evidence(
    entity_type: str, entity_id: str, db: Scoped, identity: Identity
) -> dict:
    """What supports, and what contradicts, a claim about this entity."""
    owner_user_id, _ = identity
    _require(entity_type, REF_TYPES, "entity_type")
    ref = f"{entity_type}:{entity_id}"

    supporting: list[dict] = []
    contradicting: list[dict] = []

    notes = (await db.execute(select(MapAnnotation).where(
        MapAnnotation.owner_user_id == owner_user_id,
        MapAnnotation.entity_ref_type == entity_type,
        MapAnnotation.entity_ref_id == entity_id,
    ).order_by(MapAnnotation.created_at.desc()))).scalars().all()
    for row in notes:
        supporting.append({
            "source": "Your note",
            "origin": "manual_entry",
            "evidence_class": "USER_INTERPRETATION",
            "body": row.body,
            "recorded_at": row.created_at,
        })

    edges = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
    ))).scalars().all()
    for row in edges:
        source = f"{row.source_ref_type}:{row.source_ref_id}"
        target = f"{row.target_ref_type}:{row.target_ref_id}"
        if ref not in {source, target}:
            continue
        entry = {
            "source": "Map connection",
            "origin": row.inference_source or "owner_drawn",
            "evidence_class": (
                "USER_INTERPRETATION" if row.user_confirmed else "MODEL_INFERENCE"
            ),
            "body": (
                f"{source} {row.edge_type.replace('_', ' ').lower()} {target}"
                + (f" — {row.note}" if row.note else "")
            ),
            "confirmed": row.user_confirmed,
            "recorded_at": row.created_at,
        }
        if row.edge_type == "CONTRADICTS":
            contradicting.append(entry)
        else:
            supporting.append(entry)

    blockers = (await db.execute(select(MapBlocker).where(
        MapBlocker.owner_user_id == owner_user_id,
        MapBlocker.status.in_(["OPEN", "PROPOSED", "CHALLENGED"]),
    ))).scalars().all()
    for row in blockers:
        if not any(
            isinstance(item, dict) and f"{item.get('type')}:{item.get('id')}" == ref
            for item in (row.affects or [])
        ):
            continue
        contradicting.append({
            "source": "Blocker",
            "origin": row.basis.lower(),
            "evidence_class": (
                "MODEL_INFERENCE" if row.basis == "NUR_INFERRED"
                else "DIRECT_FACT" if row.basis == "OBSERVED"
                else "USER_INTERPRETATION"
            ),
            "body": row.title,
            "confirmed": row.confirmed_by_owner,
            "recorded_at": row.created_at,
        })

    # Only entities the timeline actually anchors to have events; for the rest an
    # empty list is the truthful answer rather than a broad guess.
    for row in await _timeline_for(db, owner_user_id, entity_type, entity_id):
        supporting.append({
            "source": "Timeline",
            "origin": row.event_type,
            "evidence_class": "DIRECT_FACT",
            "body": row.title,
            "recorded_at": row.created_at,
        })

    research = (await db.execute(select(ResearchSourceNote).where(
        ResearchSourceNote.owner_user_id == owner_user_id,
    ).order_by(ResearchSourceNote.updated_at.desc()).limit(20))).scalars().all()
    signals = (await db.execute(select(WebSignalNote).where(
        WebSignalNote.owner_user_id == owner_user_id,
    ).order_by(WebSignalNote.updated_at.desc()).limit(20))).scalars().all()

    return {
        "entity": {"type": entity_type, "id": entity_id, "ref": ref},
        "supporting": supporting,
        "contradicting": contradicting,
        # Naming what is absent is part of the evidence picture, not a gap in it.
        "missing_information": [
            item for item in [
                "No note has been written against this object."
                if not notes else None,
                "No Map connection records why this matters."
                if not any(
                    ref in {
                        f"{row.source_ref_type}:{row.source_ref_id}",
                        f"{row.target_ref_type}:{row.target_ref_id}",
                    } for row in edges
                ) else None,
            ] if item
        ],
        "available_external_sources": {
            "research": [
                {"title": row.title, "url": row.url, "trust_state": row.trust_state}
                for row in research
            ],
            "web_signals": [
                {"title": row.title, "url": row.url} for row in signals
            ],
        },
        "evidence_classes": sorted(EVIDENCE_CLASSES),
        "confidence": None,
        "note": (
            "Supporting and contradicting evidence are listed separately, and each "
            "item says whether it is a fact, your interpretation, or an inference."
        ),
    }


def _is_uuid(value: str) -> bool:
    try:
        uuid.UUID(value)
    except (ValueError, AttributeError, TypeError):
        return False
    return True


#: `timeline_events` anchors to entities through typed foreign keys rather than a
#: generic (type, id) pair, so the column has to be chosen per kind. Anything not
#: listed here genuinely has no timeline anchor, and returning nothing for it is
#: more honest than matching on `source_type` and hoping.
_TIMELINE_COLUMN = {
    "goal": TimelineEvent.goal_id,
    "objective": TimelineEvent.objective_id,
    "plan": TimelineEvent.plan_id,
    "project": TimelineEvent.project_id,
    "person": TimelineEvent.person_id,
    "prediction": TimelineEvent.prediction_id,
    "orbit": TimelineEvent.orbit_id,
    "group": TimelineEvent.group_id,
}


async def _timeline_for(
    db: Scoped, owner_user_id: uuid.UUID, entity_type: str, entity_id: str
) -> list[TimelineEvent]:
    if entity_type == "system":
        return list((await db.execute(select(TimelineEvent).where(
            TimelineEvent.owner_user_id == owner_user_id,
            TimelineEvent.system_slug == entity_id,
        ).order_by(TimelineEvent.created_at.desc()).limit(80))).scalars().all())
    column = _TIMELINE_COLUMN.get(entity_type)
    if column is None or not _is_uuid(entity_id):
        return []
    return list((await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == owner_user_id,
        column == uuid.UUID(entity_id),
    ).order_by(TimelineEvent.created_at.desc()).limit(80))).scalars().all())


@router.get("/entities/{entity_type}/{entity_id}/activity")
async def entity_activity(
    entity_type: str, entity_id: str, db: Scoped, identity: Identity
) -> dict:
    owner_user_id, _ = identity
    _require(entity_type, REF_TYPES, "entity_type")
    items: list[dict] = []

    items.extend(
        {
            "at": row.created_at,
            "kind": row.event_type,
            "title": row.title,
            "status": row.status,
            "source": "timeline",
        }
        for row in await _timeline_for(db, owner_user_id, entity_type, entity_id)
    )

    notes = (await db.execute(select(MapAnnotation).where(
        MapAnnotation.owner_user_id == owner_user_id,
        MapAnnotation.entity_ref_type == entity_type,
        MapAnnotation.entity_ref_id == entity_id,
    ).order_by(MapAnnotation.created_at.desc()))).scalars().all()
    items.extend(
        {
            "at": row.created_at,
            "kind": "NOTE_ADDED",
            "title": row.body[:200],
            "status": None,
            "source": "annotation",
        }
        for row in notes
    )
    items.sort(key=lambda row: row["at"], reverse=True)
    return {
        "entity": {"type": entity_type, "id": entity_id},
        "items": items,
        "count": len(items),
    }


@router.get("/entities/{entity_type}/{entity_id}/predictions")
async def entity_predictions(
    entity_type: str, entity_id: str, db: Scoped, identity: Identity
) -> dict:
    """Open and resolved predictions, with their assumptions and their verdict."""
    owner_user_id, _ = identity
    _require(entity_type, REF_TYPES, "entity_type")
    rows = (await db.execute(select(Prediction).where(
        Prediction.owner_user_id == owner_user_id,
    ).order_by(Prediction.created_at.desc()).limit(80))).scalars().all()
    matched = [
        row for row in rows
        if str((row.expected_observation or {}).get("goal_id", "")) == entity_id
        or (row.expected_observation or {}).get("system_slug") == entity_id
    ]
    now = dt.datetime.now(dt.UTC)
    return {
        "entity": {"type": entity_type, "id": entity_id},
        "items": [
            {
                "id": str(row.id),
                "statement": row.statement,
                "status": row.status,
                "assumptions": row.assumptions,
                "confidence": (
                    float(row.confidence) if row.confidence is not None else None
                ),
                "horizon_days": row.horizon_days,
                "review_by": row.review_by,
                "overdue_for_review": bool(
                    row.review_by and row.status == "OPEN" and row.review_by < now
                ),
                "resolution": row.resolution,
                "learning": row.learning,
                "resolved_at": row.resolved_at,
                "expected_observation": row.expected_observation,
                # The schema forbids a stored confidence of 1, so a prediction can
                # never arrive here claiming certainty.
                "is_certain": False,
            }
            for row in matched
        ],
        "count": len(matched),
        "note": (
            "A prediction is a possible future with assumptions attached, never a "
            "guarantee."
        ),
    }


@router.post(
    "/predictions/{prediction_id}/resolve", dependencies=[Depends(require_csrf)]
)
async def resolve_prediction(
    prediction_id: uuid.UUID,
    payload: PredictionResolveIn,
    db: Scoped,
    identity: Identity,
) -> dict:
    """Close the loop: what actually happened, and what it changes.

    This is the step that makes a prediction worth having. Recording that an
    outcome contradicted the prediction is as ordinary a result as confirming it,
    which is why `learning` is prompted for on every verdict.
    """
    owner_user_id, _ = identity
    _require(
        payload.resolution,
        ("CONFIRMED", "PARTIALLY_CONFIRMED", "CONTRADICTED"),
        "resolution",
    )
    row = (await db.execute(select(Prediction).where(
        Prediction.id == prediction_id, Prediction.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That prediction does not exist.")
    if row.resolution is not None:
        raise HTTPException(
            409, f"That prediction was already resolved as {row.resolution}."
        )
    row.resolution = payload.resolution
    row.learning = payload.learning
    row.resolved_at = dt.datetime.now(dt.UTC)
    row.status = "RESOLVED"
    await db.flush()
    out = {
        "id": str(row.id),
        "statement": row.statement,
        "status": row.status,
        "resolution": row.resolution,
        "learning": row.learning,
        "resolved_at": row.resolved_at,
        "assumptions": row.assumptions,
    }
    await db.commit()
    return out


@router.get("/smart-sections")
async def smart_sections(db: Scoped, identity: Identity) -> dict:
    """§13.7 — the navigator's derived groupings, each from real rows."""
    owner_user_id, _ = identity
    now = dt.datetime.now(dt.UTC)

    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id, Goal.status == "ACTIVE",
    ).order_by(Goal.updated_at.desc()))).scalars().all()
    blockers = (await db.execute(select(MapBlocker).where(
        MapBlocker.owner_user_id == owner_user_id,
        MapBlocker.status.in_(["OPEN", "PROPOSED"]),
    ))).scalars().all()
    decisions = (await db.execute(select(Decision).where(
        Decision.owner_user_id == owner_user_id,
    ))).scalars().all()
    chosen = {
        row.decision_id
        for row in (await db.execute(select(MapDecisionOption).where(
            MapDecisionOption.owner_user_id == owner_user_id,
            MapDecisionOption.chosen_at.isnot(None),
        ))).scalars().all()
    }
    outcomes = (await db.execute(select(Outcome).where(
        Outcome.owner_user_id == owner_user_id,
    ).order_by(Outcome.created_at.desc()).limit(40))).scalars().all()
    stale_predictions = (await db.execute(select(Prediction).where(
        Prediction.owner_user_id == owner_user_id,
        Prediction.status == "OPEN",
        Prediction.review_by.isnot(None),
        Prediction.review_by < now,
    ))).scalars().all()

    blocked_refs = {
        f"{item.get('type')}:{item.get('id')}"
        for row in blockers
        for item in (row.affects or [])
        if isinstance(item, dict)
    }
    cutoff = now - dt.timedelta(days=14)

    return {
        "current_focus": [
            {"ref": f"goal:{row.id}", "label": row.title, "system_slug": row.system_slug}
            for row in goals[:5]
        ],
        "needs_decision": [
            {"ref": f"decision:{row.id}", "label": row.statement}
            for row in decisions if row.id not in chosen
        ],
        "blocked": [
            {"ref": f"goal:{row.id}", "label": row.title}
            for row in goals if f"goal:{row.id}" in blocked_refs
        ],
        "momentum": [
            {
                "ref": f"outcome:{row.id}",
                "label": row.observed_result[:160],
                "at": row.created_at,
            }
            for row in outcomes if row.created_at and row.created_at >= cutoff
        ],
        "fragile_paths": [
            {
                "ref": f"prediction:{row.id}",
                "label": row.statement,
                "reason": "Past its review date and still open.",
            }
            for row in stale_predictions
        ],
        "recently_changed": [
            {"ref": f"goal:{row.id}", "label": row.title, "at": row.updated_at}
            for row in goals[:8]
        ],
        "provenance_label": "OWNER_LEDGER_DERIVED",
    }
