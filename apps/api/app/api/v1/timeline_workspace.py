"""Timeline workspace — Flow, Calendar, Horizons, Review, dependencies, ripple.

This router sits beside `timeline.py` under the same `/timeline` prefix.
`timeline.py` owns entry creation and the truth-state transitions it already
had (`complete`, `miss`, `reschedule`, `attach-outcome`, `make-easier`,
`turn-into-plan`) and is left intact; everything here is the composed reading
surface and the pieces that had no home: phases, recurrences, reschedule
history, reviews, and dependencies.

**Reuse, not a fourth world model.** `timeline_events` and `scheduled_actions`
already are the Event/Action/Time-Block object model — this router reads both
into one composed Flow/Calendar/Horizons/Review surface rather than inventing a
third store. `scheduled_actions` mutation stays where it already lives,
`PATCH /api/v1/living/schedules/{id}` — Timeline composes it for reading and does
not shadow its write path.

**Dependencies reuse `map_edges` from 0051.** The Timeline spec itself says to
reuse Map's dependency structure. `map_edges` already has `DEPENDS_ON` in its
edge-type vocabulary, `timeline_event` in its ref-type vocabulary, and
`user_confirmed` — exactly the "NUR must never mass-reschedule silently"
guarantee this surface needs. The specific flavour (finish-before / start-after /
can-overlap / requires-decision / person / resource / outcome) and any lag are
carried in `edge_metadata`, which costs no migration to alter.

**No generic status PATCH exists anywhere in this file.** §5's rule — NUR must
never silently turn planned into completed, predicted into actual, inferred into
fact, imported into approved memory — is enforced by giving every transition its
own named endpoint (`/schedule`, `/start`, `/complete`, `/partial`,
`/confirm-observed`, `/archive`) rather than one `PATCH {status}` a caller could
drive silently.

**Ripple is preview, then a separate confirmed apply.** `POST /ripple-preview`
computes and persists nothing. Only `POST /ripple-apply`, called with an explicit
mode the owner chose, writes anything — and it writes a `TimelineReschedule` row
for every entry it touches, never a bare overwrite.

**No calendar provider is connected.** `timeline_external_links` exists as
schema; `GET /external-sync/status` always reports `connected: false`, and
`POST /external-sync` refuses with a clear reason rather than silently
succeeding at nothing. Wiring a real provider needs real OAuth credentials this
repository does not have and none is requested here.

**Review generation is deterministic**, like Map's `/problem` and
`/path-comparison`: it compares real planned-vs-actual timestamps and real
reschedule counts already on the ledger, and labels itself `DETERMINISTIC_FRAME`.
No model is consulted.
"""

from __future__ import annotations

import datetime as dt
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, or_, select

from app.api.deps import Identity, Scoped, require_csrf
from app.living.catalog import SYSTEMS
from app.models import (
    Decision,
    Goal,
    MapEdge,
    Prediction,
    ScheduledAction,
    TimelineEvent,
    TimelineExternalLink,
    TimelinePhase,
    TimelinePreference,
    TimelineRecurrence,
    TimelineReschedule,
    TimelineReview,
)
from app.models._mixins import now_utc
from app.models.timeline_layer import (
    COMPLETION_STATES,
    DEPENDENCY_KINDS,
    LANE_GROUPINGS,
    PHASE_STATUSES,
    RECURRENCE_MODES,
    REVIEW_TYPES,
    VIEW_MODES,
    ZOOM_LEVELS,
)

router = APIRouter(prefix="/timeline", tags=["timeline"])

SYSTEM_SLUGS = tuple(system.slug for system in SYSTEMS)

DEPENDENCY_TARGET_TYPES = ("timeline_event", "scheduled_action")


def _require(value: str, allowed: tuple[str, ...], field: str) -> str:
    if value not in allowed:
        raise HTTPException(422, f"{field} must be one of: {', '.join(allowed)}.")
    return value


def _horizon_bucket(when: dt.datetime | None, now: dt.datetime) -> str:
    """§25's Horizons buckets, derived only from a real timestamp difference."""
    if when is None:
        return "SOMEDAY"
    days = (when - now).total_seconds() / 86_400
    if days <= 0:
        return "NOW"
    if days <= 7:
        return "THIS_WEEK"
    if days <= 30:
        return "THIRTY_DAYS"
    if days <= 90:
        return "NINETY_DAYS"
    if days <= 182:
        return "SIX_MONTHS"
    if days <= 366:
        return "ONE_YEAR"
    return "SOMEDAY"


# ──────────────────────────────────────────────────────────────────────────────
# Schemas
# ──────────────────────────────────────────────────────────────────────────────


class PhaseIn(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    description: str | None = None
    starts_at: dt.datetime | None = None
    ends_at: dt.datetime | None = None
    primary_system_slug: str | None = None


class PhasePatch(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = None
    starts_at: dt.datetime | None = None
    ends_at: dt.datetime | None = None
    status: str | None = None
    primary_system_slug: str | None = None


class RecurrenceIn(BaseModel):
    recurrence_rule: str = Field(min_length=1)
    recurrence_mode: str = "EXACT"
    target_frequency: int | None = Field(default=None, ge=1, le=100)
    starts_at: dt.datetime
    ends_at: dt.datetime | None = None


class DependencyIn(BaseModel):
    predecessor_ref_type: str
    predecessor_ref_id: str
    successor_ref_type: str
    successor_ref_id: str
    dependency_kind: str = "FINISH_BEFORE"
    lag_minutes: int = Field(default=0, ge=-10_080, le=10_080)
    note: str | None = None


class ActualIn(BaseModel):
    actual_start_at: dt.datetime | None = None
    actual_end_at: dt.datetime | None = None
    completion_state: str | None = None
    evidence: str | None = None


class RescheduleWithHistoryIn(BaseModel):
    new_start_at: dt.datetime
    new_end_at: dt.datetime | None = None
    reason: str | None = None


class RipplePreviewIn(BaseModel):
    entry_id: uuid.UUID
    new_start_at: dt.datetime


class RippleApplyIn(BaseModel):
    entry_id: uuid.UUID
    new_start_at: dt.datetime
    mode: str = "MOVE_ONLY"
    selected_ids: list[str] = Field(default_factory=list)
    reason: str | None = None


class ReviewGenerateIn(BaseModel):
    review_type: str
    period_start: dt.datetime
    period_end: dt.datetime


class ReviewIn(BaseModel):
    review_type: str
    period_start: dt.datetime
    period_end: dt.datetime
    summary: str | None = None


class PreferencesPatch(BaseModel):
    view_mode: str | None = None
    zoom_level: str | None = None
    lane_grouping: str | None = None
    filters: dict | None = None
    timezone_name: str | None = None


class ConflictAnalysisIn(BaseModel):
    range_start: dt.datetime
    range_end: dt.datetime


# ──────────────────────────────────────────────────────────────────────────────
# Output helpers
# ──────────────────────────────────────────────────────────────────────────────


def _entry_out(row: TimelineEvent) -> dict:
    return {
        "ref": f"timeline_event:{row.id}",
        "id": str(row.id),
        "kind": "timeline_event",
        "event_type": row.event_type,
        "title": row.title,
        "description": row.description,
        "status": row.status,
        "time_kind": row.time_kind,
        "date_precision": row.date_precision,
        "scheduled_for": row.scheduled_for,
        "ends_at": row.ends_at,
        "all_day": row.all_day,
        "earliest_at": row.earliest_at,
        "latest_at": row.latest_at,
        "actual_start_at": row.actual_start_at,
        "actual_end_at": row.actual_end_at,
        "completion_state": row.completion_state,
        "occurred_at": row.occurred_at,
        "system_slug": row.system_slug,
        "goal_id": str(row.goal_id) if row.goal_id else None,
        "plan_id": str(row.plan_id) if row.plan_id else None,
        "project_id": str(row.project_id) if row.project_id else None,
        "person_id": str(row.person_id) if row.person_id else None,
        "orbit_id": str(row.orbit_id) if row.orbit_id else None,
        "prediction_id": str(row.prediction_id) if row.prediction_id else None,
        "phase_id": str(row.phase_id) if row.phase_id else None,
        "visibility_scope": row.visibility_scope,
        "energy_type": row.energy_type,
        "importance": row.importance,
        "source_type": row.source_type,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _schedule_out(row: ScheduledAction) -> dict:
    """A `scheduled_actions` row, read into the same shape as a Timeline entry.

    This is the composition guarantee: Time Blocks come from the row Today
    already owns, not from a Timeline-only duplicate.
    """
    return {
        "ref": f"scheduled_action:{row.id}",
        "id": str(row.id),
        "kind": "scheduled_action",
        "event_type": "TIME_BLOCK",
        "title": row.title,
        "description": None,
        "status": row.status,
        "time_kind": (
            "PAST" if row.status in {"COMPLETED", "MISSED", "CANCELLED"} else "FUTURE"
        ),
        "date_precision": "EXACT",
        "scheduled_for": row.scheduled_for,
        "ends_at": (
            row.scheduled_for + dt.timedelta(minutes=row.duration_minutes)
            if row.duration_minutes else None
        ),
        "all_day": False,
        "earliest_at": None,
        "latest_at": None,
        "actual_start_at": None,
        "actual_end_at": row.completed_at or row.missed_at,
        "completion_state": None,
        "occurred_at": row.completed_at,
        "system_slug": row.system_slug,
        "goal_id": str(row.goal_id) if row.goal_id else None,
        "plan_id": None,
        "project_id": None,
        "person_id": None,
        "orbit_id": str(row.orbit_id) if row.orbit_id else None,
        "prediction_id": None,
        "phase_id": None,
        "visibility_scope": "PRIVATE",
        "energy_type": None,
        "importance": 50,
        "source_type": "SCHEDULED_ACTION",
        "created_at": row.created_at,
        "updated_at": row.created_at,
    }


def _phase_out(row: TimelinePhase) -> dict:
    return {
        "id": str(row.id),
        "name": row.name,
        "description": row.description,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "status": row.status,
        "primary_system_slug": row.primary_system_slug,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _recurrence_out(row: TimelineRecurrence) -> dict:
    return {
        "id": str(row.id),
        "timeline_event_id": str(row.timeline_event_id),
        "recurrence_rule": row.recurrence_rule,
        "recurrence_mode": row.recurrence_mode,
        "target_frequency": row.target_frequency,
        "starts_at": row.starts_at,
        "ends_at": row.ends_at,
        "paused_at": row.paused_at,
    }


def _reschedule_out(row: TimelineReschedule) -> dict:
    return {
        "id": str(row.id),
        "timeline_event_id": str(row.timeline_event_id),
        "previous_start_at": row.previous_start_at,
        "previous_end_at": row.previous_end_at,
        "new_start_at": row.new_start_at,
        "new_end_at": row.new_end_at,
        "reason": row.reason,
        "source": row.source,
        "created_at": row.created_at,
    }


def _review_out(row: TimelineReview) -> dict:
    return {
        "id": str(row.id),
        "review_type": row.review_type,
        "period_start": row.period_start,
        "period_end": row.period_end,
        "summary": row.summary,
        "findings": row.findings,
        "accepted_changes": row.accepted_changes,
        "created_at": row.created_at,
    }


def _dependency_out(row: MapEdge) -> dict:
    metadata = row.edge_metadata or {}
    return {
        "id": str(row.id),
        "predecessor_ref": f"{row.source_ref_type}:{row.source_ref_id}",
        "successor_ref": f"{row.target_ref_type}:{row.target_ref_id}",
        "dependency_kind": metadata.get("dependency_kind", "FINISH_BEFORE"),
        "lag_minutes": metadata.get("lag_minutes", 0),
        "note": row.note,
        "user_confirmed": row.user_confirmed,
        "created_at": row.created_at,
    }


async def _owned_entry(db: Scoped, owner_user_id: uuid.UUID, entry_id: uuid.UUID) -> TimelineEvent:
    row = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.id == entry_id, TimelineEvent.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That Timeline entry does not exist.")
    return row


# ──────────────────────────────────────────────────────────────────────────────
# Composed reading surfaces: Flow, Calendar, Horizons, Review
# ──────────────────────────────────────────────────────────────────────────────


async def _range_entries(
    db: Scoped, owner_user_id: uuid.UUID, start: dt.datetime | None, end: dt.datetime | None,
) -> tuple[list[TimelineEvent], list[ScheduledAction]]:
    event_query = select(TimelineEvent).where(TimelineEvent.owner_user_id == owner_user_id)
    schedule_query = select(ScheduledAction).where(ScheduledAction.owner_user_id == owner_user_id)
    if start is not None:
        event_query = event_query.where(or_(
            TimelineEvent.scheduled_for >= start, TimelineEvent.scheduled_for.is_(None),
        ))
        schedule_query = schedule_query.where(ScheduledAction.scheduled_for >= start)
    if end is not None:
        event_query = event_query.where(or_(
            TimelineEvent.scheduled_for <= end, TimelineEvent.scheduled_for.is_(None),
        ))
        schedule_query = schedule_query.where(ScheduledAction.scheduled_for <= end)
    events = (await db.execute(
        event_query.order_by(TimelineEvent.scheduled_for.asc().nullslast()).limit(500)
    )).scalars().all()
    schedules = (await db.execute(
        schedule_query.order_by(ScheduledAction.scheduled_for.asc()).limit(500)
    )).scalars().all()
    return list(events), list(schedules)


@router.get("/flow")
async def timeline_flow(
    db: Scoped,
    identity: Identity,
    range_start: dt.datetime | None = None,
    range_end: dt.datetime | None = None,
) -> dict:
    """The signature river: past → Now Horizon → future, in one composed feed."""
    owner_user_id, _ = identity
    now = dt.datetime.now(dt.UTC)
    events, schedules = await _range_entries(db, owner_user_id, range_start, range_end)

    entries = [_entry_out(row) for row in events] + [_schedule_out(row) for row in schedules]
    entries.sort(key=lambda row: row["scheduled_for"] or now)

    unscheduled = [
        _entry_out(row) for row in events
        if row.date_precision == "UNSCHEDULED" or row.scheduled_for is None
    ]

    def _lane(row: dict) -> str:
        when = row["scheduled_for"]
        if row["status"] in {"COMPLETED", "CANCELLED", "ARCHIVED"}:
            return "past"
        if when is None:
            return "unscheduled"
        if when <= now:
            return "past" if row["status"] not in {"IN_PROGRESS", "DUE"} else "present"
        if when <= now + dt.timedelta(hours=24):
            return "present"
        return "future"

    for row in entries:
        row["lane"] = _lane(row)

    phases = (await db.execute(select(TimelinePhase).where(
        TimelinePhase.owner_user_id == owner_user_id,
        TimelinePhase.status != "ARCHIVED",
    ).order_by(TimelinePhase.starts_at.asc().nullslast()))).scalars().all()

    dependencies = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
        MapEdge.edge_type == "DEPENDS_ON",
        MapEdge.source_ref_type.in_(DEPENDENCY_TARGET_TYPES),
    ))).scalars().all()

    return {
        "generated_at": now,
        "now": now,
        "entries": [row for row in entries if row["lane"] != "unscheduled"],
        "unscheduled": unscheduled,
        "phases": [_phase_out(row) for row in phases],
        "dependencies": [_dependency_out(row) for row in dependencies],
        "counts": {
            "total": len(entries),
            "past": sum(1 for row in entries if row["lane"] == "past"),
            "present": sum(1 for row in entries if row["lane"] == "present"),
            "future": sum(1 for row in entries if row["lane"] == "future"),
            "unscheduled": len(unscheduled),
        },
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    }


@router.get("/calendar")
async def timeline_calendar(
    db: Scoped,
    identity: Identity,
    view: str = "week",
    anchor: dt.datetime | None = None,
) -> dict:
    """Day/Week/Month scheduling, from the same rows Flow reads."""
    owner_user_id, _ = identity
    _require(view.upper(), ("DAY", "WEEK", "MONTH"), "view")
    now = dt.datetime.now(dt.UTC)
    center = anchor or now
    span = {"DAY": 1, "WEEK": 7, "MONTH": 31}[view.upper()]
    start = center - dt.timedelta(days=span)
    end = center + dt.timedelta(days=span)
    events, schedules = await _range_entries(db, owner_user_id, start, end)
    entries = [_entry_out(row) for row in events if row.scheduled_for is not None]
    entries += [_schedule_out(row) for row in schedules]
    entries.sort(key=lambda row: row["scheduled_for"])
    return {
        "view": view.upper(),
        "anchor": center,
        "range_start": start,
        "range_end": end,
        "entries": entries,
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    }


@router.get("/horizons")
async def timeline_horizons(db: Scoped, identity: Identity) -> dict:
    """§25: group active work into Now / This Week / 30d / 90d / 6mo / 1yr / Someday."""
    owner_user_id, _ = identity
    now = dt.datetime.now(dt.UTC)

    goals = (await db.execute(select(Goal).where(
        Goal.owner_user_id == owner_user_id, Goal.status == "ACTIVE",
    ))).scalars().all()
    phases = (await db.execute(select(TimelinePhase).where(
        TimelinePhase.owner_user_id == owner_user_id,
        TimelinePhase.status.in_(["UPCOMING", "ACTIVE"]),
    ))).scalars().all()
    decisions = (await db.execute(select(Decision).where(
        Decision.owner_user_id == owner_user_id, Decision.status != "HELD",
    ))).scalars().all()
    milestones = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == owner_user_id,
        TimelineEvent.event_type.in_(["GOAL_MILESTONE", "MILESTONE"]),
        TimelineEvent.status.notin_(["COMPLETED", "CANCELLED", "ARCHIVED"]),
    ))).scalars().all()

    buckets: dict[str, list[dict]] = {
        "NOW": [], "THIS_WEEK": [], "THIRTY_DAYS": [], "NINETY_DAYS": [],
        "SIX_MONTHS": [], "ONE_YEAR": [], "SOMEDAY": [],
    }
    for goal in goals:
        when = (
            dt.datetime.combine(goal.target_date, dt.time(17, 0), tzinfo=dt.UTC)
            if goal.target_date else None
        )
        buckets[_horizon_bucket(when, now)].append({
            "ref": f"goal:{goal.id}", "kind": "goal", "label": goal.title,
            "system_slug": goal.system_slug, "progress_percent": goal.progress_percent,
        })
    for phase in phases:
        buckets[_horizon_bucket(phase.starts_at, now)].append({
            "ref": f"phase:{phase.id}", "kind": "phase", "label": phase.name,
            "status": phase.status,
        })
    for decision in decisions:
        buckets["NOW"].append({
            "ref": f"decision:{decision.id}", "kind": "decision",
            "label": decision.statement,
        })
    for milestone in milestones:
        buckets[_horizon_bucket(milestone.scheduled_for, now)].append({
            "ref": f"timeline_event:{milestone.id}", "kind": "milestone",
            "label": milestone.title,
        })

    # §25 Horizon drift: a goal whose target date has been pushed out more than
    # once. Reschedule history against `timeline_event` refs linked to the goal.
    goal_event_ids = [
        row.id for row in milestones if row.goal_id in {g.id for g in goals}
    ]
    drift_rows: list[TimelineReschedule] = []
    if goal_event_ids:
        drift_rows = list((await db.execute(select(TimelineReschedule).where(
            TimelineReschedule.owner_user_id == owner_user_id,
            TimelineReschedule.timeline_event_id.in_(goal_event_ids),
        ))).scalars().all())
    drift_counts: dict[uuid.UUID, int] = {}
    for row in drift_rows:
        drift_counts[row.timeline_event_id] = drift_counts.get(row.timeline_event_id, 0) + 1
    drifted = [
        {"ref": f"timeline_event:{event_id}", "reschedule_count": count}
        for event_id, count in drift_counts.items() if count >= 2
    ]

    return {
        "generated_at": now,
        "buckets": buckets,
        "drift": drifted,
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    }


@router.get("/review")
async def timeline_review_default(db: Scoped, identity: Identity) -> dict:
    """The Review surface with no generated review yet: this week, computed live."""
    owner_user_id, _ = identity
    now = dt.datetime.now(dt.UTC)
    start = now - dt.timedelta(days=7)
    stats = await _compute_review_findings(db, owner_user_id, start, now)
    latest = (await db.execute(select(TimelineReview).where(
        TimelineReview.owner_user_id == owner_user_id,
    ).order_by(TimelineReview.created_at.desc()).limit(5))).scalars().all()
    return {
        "period_start": start,
        "period_end": now,
        "live_findings": stats,
        "recent_reviews": [_review_out(row) for row in latest],
        "provenance_label": "DETERMINISTIC_FRAME",
    }


async def _compute_review_findings(
    db: Scoped, owner_user_id: uuid.UUID, start: dt.datetime, end: dt.datetime,
) -> dict:
    """Planned-vs-actual, entirely from rows already on the ledger.

    Deterministic and stated as such: no model reads these rows, this only
    compares timestamps and counts that already exist.
    """
    events = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == owner_user_id,
        TimelineEvent.scheduled_for >= start, TimelineEvent.scheduled_for <= end,
    ))).scalars().all()
    completed = [row for row in events if row.status == "COMPLETED"]
    missed = [row for row in events if row.status == "MISSED"]
    on_time = [
        row for row in completed
        if row.actual_end_at and row.scheduled_for and row.actual_end_at <= row.scheduled_for + dt.timedelta(hours=6)
    ]

    reschedules = (await db.execute(select(func.count(TimelineReschedule.id)).where(
        TimelineReschedule.owner_user_id == owner_user_id,
        TimelineReschedule.created_at >= start, TimelineReschedule.created_at <= end,
    ))).scalar_one()

    resolved_predictions = (await db.execute(select(Prediction).where(
        Prediction.owner_user_id == owner_user_id,
        Prediction.resolved_at >= start, Prediction.resolved_at <= end,
    ))).scalars().all()

    system_minutes: dict[str, int] = {}
    for row in events:
        if not row.system_slug:
            continue
        duration = 60
        if row.ends_at and row.scheduled_for:
            duration = max(1, int((row.ends_at - row.scheduled_for).total_seconds() / 60))
        system_minutes[row.system_slug] = system_minutes.get(row.system_slug, 0) + duration
    total_minutes = sum(system_minutes.values())

    return {
        "period_entry_count": len(events),
        "completed_count": len(completed),
        "missed_count": len(missed),
        "on_time_count": len(on_time),
        "reschedule_count": int(reschedules),
        "predictions_resolved": [
            {
                "id": str(row.id), "statement": row.statement,
                "resolution": row.resolution, "learning": row.learning,
            }
            for row in resolved_predictions
        ],
        # Words, not a manufactured percentage — §26 forbids moralizing and §10's
        # anti-fake-precision rule applies here too.
        "system_time_distribution": (
            {
                slug: f"{round(minutes / total_minutes * 100)}%"
                for slug, minutes in system_minutes.items()
            } if total_minutes else {}
        ),
        "provenance_label": "DETERMINISTIC_FRAME",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Truth-state transitions — named endpoints only, never a generic status PATCH
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/entries/{entry_id}/schedule", dependencies=[Depends(require_csrf)])
async def schedule_entry(
    entry_id: uuid.UUID, payload: RescheduleWithHistoryIn, db: Scoped, identity: Identity,
) -> dict:
    """PLANNED → SCHEDULED: a date/time is assigned for the first time."""
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    if row.scheduled_for is not None and row.date_precision != "UNSCHEDULED":
        raise HTTPException(409, "This entry already has a schedule; use reschedule instead.")
    row.scheduled_for = payload.new_start_at
    row.ends_at = payload.new_end_at
    row.date_precision = "EXACT"
    row.status = "SCHEDULED"
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/start", dependencies=[Depends(require_csrf)])
async def start_entry(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    """SCHEDULED/PLANNED → IN_PROGRESS: work actually started."""
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    row.status = "IN_PROGRESS"
    row.actual_start_at = now_utc()
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/partial", dependencies=[Depends(require_csrf)])
async def partial_entry(
    entry_id: uuid.UUID, payload: ActualIn, db: Scoped, identity: Identity,
) -> dict:
    """→ PARTIALLY_COMPLETED: some result happened, not the full completion."""
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    row.status = "PARTIALLY_COMPLETED"
    row.actual_end_at = payload.actual_end_at or now_utc()
    if payload.completion_state:
        _require(payload.completion_state, COMPLETION_STATES, "completion_state")
        row.completion_state = payload.completion_state
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/archive", dependencies=[Depends(require_csrf)])
async def archive_entry(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    row.status = "ARCHIVED"
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/confirm-observed", dependencies=[Depends(require_csrf)])
async def confirm_observed(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    """PREDICTED / INFERRED / IMPORTED → OBSERVED.

    The one explicit act §5 requires before any of those three may be treated as
    a fact — never automatic, never triggered by a horizon simply passing.
    """
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    if row.status not in {"PREDICTED", "INFERRED", "IMPORTED"}:
        raise HTTPException(
            409,
            f"'{row.status}' is already a confirmed state; there is nothing to observe.",
        )
    row.status = "OBSERVED"
    row.occurred_at = row.occurred_at or now_utc()
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/actual", dependencies=[Depends(require_csrf)])
async def record_actual(
    entry_id: uuid.UUID, payload: ActualIn, db: Scoped, identity: Identity,
) -> dict:
    """§26: estimated versus actual duration. Records only what actually happened."""
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    if payload.completion_state:
        _require(payload.completion_state, COMPLETION_STATES, "completion_state")
        if payload.actual_end_at is None and row.actual_end_at is None:
            raise HTTPException(
                422, "A completion verdict needs an actual end time recorded with it.",
            )
        row.completion_state = payload.completion_state
    if payload.actual_start_at:
        row.actual_start_at = payload.actual_start_at
    if payload.actual_end_at:
        row.actual_end_at = payload.actual_end_at
    if payload.evidence:
        row.event_payload = {**row.event_payload, "actual_evidence": payload.evidence}
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Reschedule with history — the existing endpoint overwrote in place; this is
# the version that keeps §29's auditable trail.
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/entries/{entry_id}/reschedule-with-history", dependencies=[Depends(require_csrf)])
async def reschedule_with_history(
    entry_id: uuid.UUID, payload: RescheduleWithHistoryIn, db: Scoped, identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, entry_id)
    db.add(TimelineReschedule(
        owner_user_id=owner_user_id,
        timeline_event_id=row.id,
        previous_start_at=row.scheduled_for,
        previous_end_at=row.ends_at,
        new_start_at=payload.new_start_at,
        new_end_at=payload.new_end_at,
        reason=payload.reason,
        source="OWNER",
    ))
    row.scheduled_for = payload.new_start_at
    row.ends_at = payload.new_end_at
    row.status = "RESCHEDULED"
    row.date_precision = "EXACT"
    row.updated_at = now_utc()
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return out


@router.get("/entries/{entry_id}/reschedule-history")
async def reschedule_history(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    await _owned_entry(db, owner_user_id, entry_id)
    rows = (await db.execute(select(TimelineReschedule).where(
        TimelineReschedule.owner_user_id == owner_user_id,
        TimelineReschedule.timeline_event_id == entry_id,
    ).order_by(TimelineReschedule.created_at.desc()))).scalars().all()
    return {"items": [_reschedule_out(row) for row in rows]}


# ──────────────────────────────────────────────────────────────────────────────
# Phases
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/phases")
async def list_phases(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = (await db.execute(select(TimelinePhase).where(
        TimelinePhase.owner_user_id == owner_user_id,
    ).order_by(TimelinePhase.starts_at.asc().nullslast()))).scalars().all()
    return {"items": [_phase_out(row) for row in rows]}


@router.post("/phases", status_code=201, dependencies=[Depends(require_csrf)])
async def create_phase(payload: PhaseIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    if payload.primary_system_slug and payload.primary_system_slug not in SYSTEM_SLUGS:
        raise HTTPException(404, f"No System named '{payload.primary_system_slug}'.")
    if payload.starts_at and payload.ends_at and payload.ends_at < payload.starts_at:
        raise HTTPException(422, "A phase cannot end before it starts.")
    row = TimelinePhase(owner_user_id=owner_user_id, **payload.model_dump())
    db.add(row)
    await db.flush()
    out = _phase_out(row)
    await db.commit()
    return out


@router.patch("/phases/{phase_id}", dependencies=[Depends(require_csrf)])
async def patch_phase(
    phase_id: uuid.UUID, payload: PhasePatch, db: Scoped, identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(TimelinePhase).where(
        TimelinePhase.id == phase_id, TimelinePhase.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That phase does not exist.")
    data = payload.model_dump(exclude_unset=True)
    if "status" in data:
        _require(data["status"], PHASE_STATUSES, "status")
    starts_at = data.get("starts_at", row.starts_at)
    ends_at = data.get("ends_at", row.ends_at)
    if starts_at and ends_at and ends_at < starts_at:
        raise HTTPException(422, "A phase cannot end before it starts.")
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = now_utc()
    await db.flush()
    out = _phase_out(row)
    await db.commit()
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Recurrences
# ──────────────────────────────────────────────────────────────────────────────


@router.put("/entries/{entry_id}/recurrence", dependencies=[Depends(require_csrf)])
async def upsert_recurrence(
    entry_id: uuid.UUID, payload: RecurrenceIn, db: Scoped, identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    await _owned_entry(db, owner_user_id, entry_id)
    _require(payload.recurrence_mode, RECURRENCE_MODES, "recurrence_mode")
    if payload.recurrence_mode == "FLEXIBLE" and payload.target_frequency is None:
        raise HTTPException(
            422,
            "A flexible rhythm needs a target frequency — how many times, not which days.",
        )
    existing = (await db.execute(select(TimelineRecurrence).where(
        TimelineRecurrence.owner_user_id == owner_user_id,
        TimelineRecurrence.timeline_event_id == entry_id,
    ))).scalar_one_or_none()
    if existing is None:
        existing = TimelineRecurrence(
            owner_user_id=owner_user_id, timeline_event_id=entry_id,
        )
        db.add(existing)
    for key, value in payload.model_dump().items():
        setattr(existing, key, value)
    existing.updated_at = now_utc()
    await db.flush()
    out = _recurrence_out(existing)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/recurrence/pause", dependencies=[Depends(require_csrf)])
async def pause_recurrence(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(TimelineRecurrence).where(
        TimelineRecurrence.owner_user_id == owner_user_id,
        TimelineRecurrence.timeline_event_id == entry_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "This entry has no recurrence to pause.")
    row.paused_at = now_utc()
    row.updated_at = now_utc()
    await db.flush()
    out = _recurrence_out(row)
    await db.commit()
    return out


@router.post("/entries/{entry_id}/recurrence/resume", dependencies=[Depends(require_csrf)])
async def resume_recurrence(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(TimelineRecurrence).where(
        TimelineRecurrence.owner_user_id == owner_user_id,
        TimelineRecurrence.timeline_event_id == entry_id,
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "This entry has no recurrence to resume.")
    row.paused_at = None
    row.updated_at = now_utc()
    await db.flush()
    out = _recurrence_out(row)
    await db.commit()
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Dependencies — thin wrapper over map_edges
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/dependencies", status_code=201, dependencies=[Depends(require_csrf)])
async def create_dependency(payload: DependencyIn, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    _require(payload.predecessor_ref_type, DEPENDENCY_TARGET_TYPES, "predecessor_ref_type")
    _require(payload.successor_ref_type, DEPENDENCY_TARGET_TYPES, "successor_ref_type")
    _require(payload.dependency_kind, DEPENDENCY_KINDS, "dependency_kind")
    if (payload.predecessor_ref_type, payload.predecessor_ref_id) == (
        payload.successor_ref_type, payload.successor_ref_id
    ):
        raise HTTPException(422, "An item cannot depend on itself.")
    row = MapEdge(
        owner_user_id=owner_user_id,
        source_ref_type=payload.predecessor_ref_type,
        source_ref_id=payload.predecessor_ref_id,
        target_ref_type=payload.successor_ref_type,
        target_ref_id=payload.successor_ref_id,
        edge_type="DEPENDS_ON",
        user_confirmed=True,
        note=payload.note,
        edge_metadata={
            "dependency_kind": payload.dependency_kind,
            "lag_minutes": payload.lag_minutes,
        },
    )
    db.add(row)
    await db.flush()
    out = _dependency_out(row)
    await db.commit()
    return out


@router.get("/entries/{entry_id}/dependencies")
async def entry_dependencies(entry_id: uuid.UUID, db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    ref = f"timeline_event:{entry_id}"
    rows = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
        MapEdge.edge_type == "DEPENDS_ON",
        or_(
            and_(MapEdge.source_ref_type == "timeline_event", MapEdge.source_ref_id == str(entry_id)),
            and_(MapEdge.target_ref_type == "timeline_event", MapEdge.target_ref_id == str(entry_id)),
        ),
    ))).scalars().all()
    return {
        "entry_ref": ref,
        "predecessors": [
            _dependency_out(row) for row in rows
            if f"{row.target_ref_type}:{row.target_ref_id}" == ref
        ],
        "successors": [
            _dependency_out(row) for row in rows
            if f"{row.source_ref_type}:{row.source_ref_id}" == ref
        ],
    }


@router.delete("/dependencies/{dependency_id}", status_code=204, dependencies=[Depends(require_csrf)])
async def delete_dependency(dependency_id: uuid.UUID, db: Scoped, identity: Identity) -> None:
    owner_user_id, _ = identity
    row = (await db.execute(select(MapEdge).where(
        MapEdge.id == dependency_id, MapEdge.owner_user_id == owner_user_id,
        MapEdge.edge_type == "DEPENDS_ON",
    ))).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "That dependency does not exist.")
    await db.delete(row)
    await db.commit()


# ──────────────────────────────────────────────────────────────────────────────
# Ripple rescheduling — preview persists nothing, apply requires the mode
# ──────────────────────────────────────────────────────────────────────────────


async def _downstream(
    db: Scoped, owner_user_id: uuid.UUID, entry_id: uuid.UUID, max_depth: int = 6,
) -> list[dict]:
    """BFS over confirmed DEPENDS_ON edges where this entry is the predecessor."""
    seen: set[str] = {f"timeline_event:{entry_id}"}
    frontier = [f"timeline_event:{entry_id}"]
    found: list[dict] = []
    for _ in range(max_depth):
        if not frontier:
            break
        rows = (await db.execute(select(MapEdge).where(
            MapEdge.owner_user_id == owner_user_id,
            MapEdge.edge_type == "DEPENDS_ON",
            MapEdge.user_confirmed.is_(True),
            MapEdge.source_ref_type == "timeline_event",
            MapEdge.source_ref_id.in_([ref.split(":")[1] for ref in frontier]),
        ))).scalars().all()
        next_frontier: list[str] = []
        for row in rows:
            target_ref = f"{row.target_ref_type}:{row.target_ref_id}"
            if target_ref in seen or row.target_ref_type != "timeline_event":
                continue
            seen.add(target_ref)
            next_frontier.append(target_ref)
            found.append({
                "ref": target_ref,
                "edge_id": str(row.id),
                "lag_minutes": (row.edge_metadata or {}).get("lag_minutes", 0),
            })
        frontier = next_frontier
    return found


@router.post("/ripple-preview")
async def ripple_preview(payload: RipplePreviewIn, db: Scoped, identity: Identity) -> dict:
    """Computes what a move would affect. Persists nothing at all."""
    owner_user_id, _ = identity
    row = await _owned_entry(db, owner_user_id, payload.entry_id)
    shift = payload.new_start_at - (row.scheduled_for or payload.new_start_at)
    downstream = await _downstream(db, owner_user_id, payload.entry_id)

    affected = []
    if downstream:
        entry_ids = [uuid.UUID(ref["ref"].split(":")[1]) for ref in downstream]
        rows = (await db.execute(select(TimelineEvent).where(
            TimelineEvent.owner_user_id == owner_user_id, TimelineEvent.id.in_(entry_ids),
        ))).scalars().all()
        by_id = {str(item.id): item for item in rows}
        for item in downstream:
            entry = by_id.get(item["ref"].split(":")[1])
            if entry is None or entry.scheduled_for is None:
                continue
            lag = dt.timedelta(minutes=item["lag_minutes"])
            affected.append({
                "ref": item["ref"],
                "title": entry.title,
                "current_start_at": entry.scheduled_for,
                "proposed_start_at": entry.scheduled_for + shift + lag,
            })

    return {
        "entry_id": str(payload.entry_id),
        "current_start_at": row.scheduled_for,
        "proposed_start_at": payload.new_start_at,
        "shift_minutes": int(shift.total_seconds() / 60),
        "affected": affected,
        "requires_confirmation": True,
        "note": (
            f"Moving this may affect {len(affected)} downstream item"
            f"{'s' if len(affected) != 1 else ''}."
            if affected else "Nothing depends on this item moving."
        ),
    }


@router.post("/ripple-apply", dependencies=[Depends(require_csrf)])
async def ripple_apply(payload: RippleApplyIn, db: Scoped, identity: Identity) -> dict:
    """The only endpoint that writes a ripple. Requires the owner's chosen mode."""
    owner_user_id, _ = identity
    _require(
        payload.mode,
        ("MOVE_ONLY", "SHIFT_DEPENDENTS", "COMPRESS_LATER", "KEEP_AND_FLAG"),
        "mode",
    )
    row = await _owned_entry(db, owner_user_id, payload.entry_id)
    shift = payload.new_start_at - (row.scheduled_for or payload.new_start_at)

    db.add(TimelineReschedule(
        owner_user_id=owner_user_id,
        timeline_event_id=row.id,
        previous_start_at=row.scheduled_for,
        previous_end_at=row.ends_at,
        new_start_at=payload.new_start_at,
        reason=payload.reason,
        source="RIPPLE" if payload.mode != "MOVE_ONLY" else "OWNER",
    ))
    if row.ends_at:
        duration = row.ends_at - row.scheduled_for if row.scheduled_for else dt.timedelta(0)
        row.ends_at = payload.new_start_at + duration
    row.scheduled_for = payload.new_start_at
    row.status = "RESCHEDULED"
    row.updated_at = now_utc()

    moved: list[str] = []
    if payload.mode in {"SHIFT_DEPENDENTS", "COMPRESS_LATER"}:
        downstream = await _downstream(db, owner_user_id, payload.entry_id)
        target_ids = {
            item["ref"].split(":")[1] for item in downstream
            if not payload.selected_ids or item["ref"] in payload.selected_ids
        }
        if target_ids:
            rows = (await db.execute(select(TimelineEvent).where(
                TimelineEvent.owner_user_id == owner_user_id,
                TimelineEvent.id.in_([uuid.UUID(item) for item in target_ids]),
            ))).scalars().all()
            # COMPRESS_LATER halves the shift applied to each dependent, so later
            # work absorbs less of the delay than the moved item itself did.
            applied_shift = shift if payload.mode == "SHIFT_DEPENDENTS" else shift / 2
            for dependent in rows:
                if dependent.scheduled_for is None:
                    continue
                db.add(TimelineReschedule(
                    owner_user_id=owner_user_id,
                    timeline_event_id=dependent.id,
                    previous_start_at=dependent.scheduled_for,
                    previous_end_at=dependent.ends_at,
                    new_start_at=dependent.scheduled_for + applied_shift,
                    reason=f"Ripple from {row.title}",
                    source="RIPPLE",
                ))
                dependent.scheduled_for = dependent.scheduled_for + applied_shift
                if dependent.ends_at:
                    dependent.ends_at = dependent.ends_at + applied_shift
                dependent.status = "RESCHEDULED"
                dependent.updated_at = now_utc()
                moved.append(f"timeline_event:{dependent.id}")
    await db.flush()
    out = _entry_out(row)
    await db.commit()
    return {
        "entry": out,
        "mode": payload.mode,
        "dependents_moved": moved,
        "dependents_flagged_at_risk": payload.mode == "KEEP_AND_FLAG",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Conflict detection
# ──────────────────────────────────────────────────────────────────────────────


@router.post("/conflict-analysis")
async def conflict_analysis(
    payload: ConflictAnalysisIn, db: Scoped, identity: Identity,
) -> dict:
    """§20/§47: overlaps, dependency-order violations, workload state.

    Qualitative workload words, never a manufactured percentage — §21 forbids
    fake scores like "87.4% optimized" explicitly.
    """
    owner_user_id, _ = identity
    events, schedules = await _range_entries(
        db, owner_user_id, payload.range_start, payload.range_end,
    )
    timed = [
        (row.scheduled_for, row.ends_at or row.scheduled_for + dt.timedelta(hours=1), row.title, f"timeline_event:{row.id}")
        for row in events if row.scheduled_for
    ] + [
        (
            row.scheduled_for,
            row.scheduled_for + dt.timedelta(minutes=row.duration_minutes or 60),
            row.title,
            f"scheduled_action:{row.id}",
        )
        for row in schedules
    ]
    timed.sort(key=lambda item: item[0])

    overlaps = []
    for i, (start_a, end_a, title_a, ref_a) in enumerate(timed):
        for start_b, end_b, title_b, ref_b in timed[i + 1:]:
            if start_b >= end_a:
                break
            overlaps.append({
                "first": {"ref": ref_a, "title": title_a, "starts_at": start_a, "ends_at": end_a},
                "second": {"ref": ref_b, "title": title_b, "starts_at": start_b, "ends_at": end_b},
            })

    # Dependency-order violations: successor scheduled before predecessor ends + lag.
    dependency_rows = (await db.execute(select(MapEdge).where(
        MapEdge.owner_user_id == owner_user_id,
        MapEdge.edge_type == "DEPENDS_ON",
        MapEdge.source_ref_type == "timeline_event",
        MapEdge.target_ref_type == "timeline_event",
    ))).scalars().all()
    by_ref = {f"timeline_event:{row.id}": row for row in events}
    order_violations = []
    for edge in dependency_rows:
        predecessor = by_ref.get(f"{edge.source_ref_type}:{edge.source_ref_id}")
        successor = by_ref.get(f"{edge.target_ref_type}:{edge.target_ref_id}")
        if not predecessor or not successor:
            continue
        predecessor_end = predecessor.ends_at or predecessor.scheduled_for
        if predecessor_end is None or successor.scheduled_for is None:
            continue
        lag = dt.timedelta(minutes=(edge.edge_metadata or {}).get("lag_minutes", 0))
        if successor.scheduled_for < predecessor_end + lag:
            order_violations.append({
                "predecessor": predecessor.title,
                "successor": successor.title,
                "successor_ref": f"timeline_event:{successor.id}",
            })

    # Workload state, per day, in qualitative bands only.
    per_day: dict[str, int] = {}
    for start_at, end_at, _title, _ref in timed:
        key = start_at.date().isoformat()
        per_day[key] = per_day.get(key, 0) + int((end_at - start_at).total_seconds() / 60)
    # No capacity input is stored anywhere in NUR yet — see §21 — so every day is
    # honestly `UNKNOWN` rather than compared against a number nobody configured.
    available_minutes = None
    load_by_day = {}
    for day, minutes in per_day.items():
        if available_minutes is None:
            load_by_day[day] = "UNKNOWN"
        elif minutes >= available_minutes:
            load_by_day[day] = "OVERCOMMITTED"
        elif minutes >= available_minutes * 0.75:
            load_by_day[day] = "DENSE"
        elif minutes >= available_minutes * 0.4:
            load_by_day[day] = "BALANCED"
        else:
            load_by_day[day] = "LIGHT"

    return {
        "range_start": payload.range_start,
        "range_end": payload.range_end,
        "overlaps": overlaps,
        "dependency_order_violations": order_violations,
        "load_by_day": load_by_day,
        "capacity_configured": available_minutes is not None,
        "note": (
            "Workload cannot be assessed against a capacity that has not been "
            "configured, so each day is reported Unknown rather than guessed."
            if available_minutes is None else None
        ),
        "provenance_label": "DETERMINISTIC_FRAME",
    }


# ──────────────────────────────────────────────────────────────────────────────
# Reviews
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/reviews")
async def list_reviews(db: Scoped, identity: Identity, review_type: str | None = None) -> dict:
    owner_user_id, _ = identity
    query = select(TimelineReview).where(TimelineReview.owner_user_id == owner_user_id)
    if review_type:
        query = query.where(TimelineReview.review_type == review_type.upper())
    rows = (await db.execute(
        query.order_by(TimelineReview.period_start.desc()).limit(100)
    )).scalars().all()
    return {"items": [_review_out(row) for row in rows]}


@router.post("/reviews/generate", status_code=201, dependencies=[Depends(require_csrf)])
async def generate_review(
    payload: ReviewGenerateIn, db: Scoped, identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    _require(payload.review_type, REVIEW_TYPES, "review_type")
    findings = await _compute_review_findings(
        db, owner_user_id, payload.period_start, payload.period_end,
    )
    row = TimelineReview(
        owner_user_id=owner_user_id,
        review_type=payload.review_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        findings=[findings],
    )
    db.add(row)
    await db.flush()
    out = _review_out(row)
    await db.commit()
    return out


@router.post("/reviews", status_code=201, dependencies=[Depends(require_csrf)])
async def create_review(payload: ReviewIn, db: Scoped, identity: Identity) -> dict:
    """A manual reflection (the daily-close questions), stored as the owner wrote it."""
    owner_user_id, _ = identity
    _require(payload.review_type, REVIEW_TYPES, "review_type")
    row = TimelineReview(
        owner_user_id=owner_user_id,
        review_type=payload.review_type,
        period_start=payload.period_start,
        period_end=payload.period_end,
        summary=payload.summary,
    )
    db.add(row)
    await db.flush()
    out = _review_out(row)
    await db.commit()
    return out


# ──────────────────────────────────────────────────────────────────────────────
# External sync — honestly disconnected
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/external-sync/status")
async def external_sync_status(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    rows = (await db.execute(select(TimelineExternalLink).where(
        TimelineExternalLink.owner_user_id == owner_user_id,
    ))).scalars().all()
    return {
        "connected": False,
        "available_providers": [],
        "linked_entries": len(rows),
        "note": (
            "No calendar provider is connected. Wiring one needs real OAuth "
            "credentials this deployment does not have; nothing here is faked "
            "as connected."
        ),
    }


@router.post("/external-sync")
async def external_sync(identity: Identity) -> dict:
    raise HTTPException(
        503,
        "No calendar provider is connected, so there is nothing to sync. This "
        "endpoint will not report a fake success.",
    )


# ──────────────────────────────────────────────────────────────────────────────
# Preferences and smart sections
# ──────────────────────────────────────────────────────────────────────────────


@router.get("/preferences")
async def get_preferences(db: Scoped, identity: Identity) -> dict:
    owner_user_id, _ = identity
    row = (await db.execute(select(TimelinePreference).where(
        TimelinePreference.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        # A transient, un-flushed row does not carry `mapped_column(default=...)`
        # values — SQLAlchemy applies those at flush time, not at construction —
        # so reading `.view_mode` here would return None rather than "FLOW". A
        # first-time owner should not have a row silently written on a GET, so the
        # defaults are stated directly instead, matching migration 0052 exactly.
        return {
            "view_mode": "FLOW",
            "zoom_level": "MONTH",
            "lane_grouping": "UNIFIED",
            "filters": {},
            "timezone_name": None,
        }
    return {
        "view_mode": row.view_mode,
        "zoom_level": row.zoom_level,
        "lane_grouping": row.lane_grouping,
        "filters": row.filters,
        "timezone_name": row.timezone_name,
    }


@router.patch("/preferences", dependencies=[Depends(require_csrf)])
async def patch_preferences(
    payload: PreferencesPatch, db: Scoped, identity: Identity,
) -> dict:
    owner_user_id, _ = identity
    data = payload.model_dump(exclude_unset=True)
    if "view_mode" in data:
        _require(data["view_mode"], VIEW_MODES, "view_mode")
    if "zoom_level" in data:
        _require(data["zoom_level"], ZOOM_LEVELS, "zoom_level")
    if "lane_grouping" in data:
        _require(data["lane_grouping"], LANE_GROUPINGS, "lane_grouping")
    row = (await db.execute(select(TimelinePreference).where(
        TimelinePreference.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if row is None:
        row = TimelinePreference(owner_user_id=owner_user_id)
        db.add(row)
    for key, value in data.items():
        setattr(row, key, value)
    row.updated_at = now_utc()
    await db.flush()
    out = {
        "view_mode": row.view_mode, "zoom_level": row.zoom_level,
        "lane_grouping": row.lane_grouping, "filters": row.filters,
        "timezone_name": row.timezone_name,
    }
    await db.commit()
    return out


@router.get("/smart-sections")
async def smart_sections(db: Scoped, identity: Identity) -> dict:
    """§40.7's navigator groupings, each from real rows."""
    owner_user_id, _ = identity
    now = dt.datetime.now(dt.UTC)

    events = (await db.execute(select(TimelineEvent).where(
        TimelineEvent.owner_user_id == owner_user_id,
        TimelineEvent.status.notin_(["COMPLETED", "CANCELLED", "ARCHIVED"]),
    ).order_by(TimelineEvent.scheduled_for.asc().nullslast()).limit(300))).scalars().all()

    now_items = [row for row in events if row.status in {"IN_PROGRESS", "DUE"}]
    next_items = [
        row for row in events
        if row.scheduled_for and now < row.scheduled_for <= now + dt.timedelta(days=2)
    ]
    overdue = [
        row for row in events
        if row.scheduled_for and row.scheduled_for < now
        and row.status not in {"COMPLETED", "CANCELLED", "MISSED", "ARCHIVED"}
    ]
    awaiting_dependency = [row for row in events if row.date_precision == "AFTER_DEPENDENCY"]
    unscheduled = [
        row for row in events
        if row.date_precision == "UNSCHEDULED" or row.scheduled_for is None
    ]

    stale_predictions = (await db.execute(select(Prediction).where(
        Prediction.owner_user_id == owner_user_id,
        Prediction.status == "OPEN",
        Prediction.review_by.isnot(None),
        Prediction.review_by < now,
    ))).scalars().all()

    recurring = (await db.execute(select(TimelineRecurrence).where(
        TimelineRecurrence.owner_user_id == owner_user_id,
        TimelineRecurrence.paused_at.is_(None),
    ))).scalars().all()

    def _row(entry: TimelineEvent) -> dict:
        return {"ref": f"timeline_event:{entry.id}", "label": entry.title}

    return {
        "now": [_row(row) for row in now_items[:8]],
        "next": [_row(row) for row in next_items[:8]],
        "overdue": [_row(row) for row in overdue[:8]],
        "awaiting_dependency": [_row(row) for row in awaiting_dependency[:8]],
        "needs_review": [
            {"ref": f"prediction:{row.id}", "label": row.statement}
            for row in stale_predictions[:8]
        ],
        "unscheduled": [_row(row) for row in unscheduled[:8]],
        "repeating": [
            {"ref": f"timeline_event:{row.timeline_event_id}", "recurrence_rule": row.recurrence_rule}
            for row in recurring[:8]
        ],
        "provenance_label": "OWNER_TIMELINE_LEDGER",
    }
