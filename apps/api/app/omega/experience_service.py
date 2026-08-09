import hashlib
import json
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    CognitiveEvent,
    DomainEvent,
    JournalEntry,
    OmegaExperience,
    PlanStep,
    SystemAction,
)
from app.models._mixins import now_utc
from app.omega.safety_law import redact_secrets, sensitivity_for_summary
from app.omega.schemas import OmegaExperienceIn


async def ingest_experience(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    payload: OmegaExperienceIn,
) -> OmegaExperience:
    summary, secret_found = redact_secrets(payload.summary)
    sensitivity = "SECRET_EXCLUDED" if secret_found else sensitivity_for_summary(summary, payload.sensitivity)
    row = OmegaExperience(
        owner_user_id=owner_user_id,
        source_kind=payload.source_kind,
        source_id=payload.source_id,
        orbit_id=payload.orbit_id,
        event_kind=payload.event_kind,
        scope=payload.scope,
        language_tag=payload.language_tag,
        summary=summary,
        raw_ref=payload.raw_ref,
        provenance_label=payload.provenance_label,
        sensitivity=sensitivity,
        confidence=payload.confidence,
        source_domain=payload.source_domain,
        features=payload.features,
        explicitness=payload.explicitness,
        retention_policy=payload.retention_policy,
        observed_at=payload.observed_at or now_utc(),
        source_fingerprint=payload.source_fingerprint,
    )
    db.add(row)
    await db.flush()
    return row


async def ingest_from_cognitive_event(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    event: CognitiveEvent,
    provenance_label: str | None = None,
) -> OmegaExperience:
    label = provenance_label or {
        "TALK_TURN": "OWNER_WRITTEN",
        "JOURNAL_ENTRY": "OWNER_WRITTEN",
        "PLAN_CREATED": "OWNER_WRITTEN",
        "PLAN_STEP": "SYSTEM_MEASURED",
        "OUTCOME_REPORTED": "OBSERVED_OUTCOME",
        "USER_CORRECTION": "USER_CORRECTION",
        "MODEL_RESPONSE": "MODEL_GENERATED",
        "EVALUATION_EVENT": "SYSTEM_MEASURED",
    }.get(event.event_kind, "SYSTEM_MEASURED")
    source_kind, source_id = await _canonical_cognitive_source(db, event)
    features = await _cognitive_features(
        db, event=event, source_kind=source_kind, source_id=source_id
    )
    explicitness = (
        "OWNER_EXPLICIT"
        if label in {"OWNER_WRITTEN", "OBSERVED_OUTCOME", "USER_CORRECTION"}
        else "MODEL_INFERRED" if label == "MODEL_GENERATED" else "SYSTEM_OBSERVED"
    )
    source_domain = _cognitive_domain(event)
    fingerprint = _fingerprint(
        {
            "event_id": str(event.id),
            "event_kind": event.event_kind,
            "source_kind": source_kind,
            "source_id": str(source_id),
            "features": features,
            "content_hash": hashlib.sha256(
                (event.content_text or "").encode("utf-8")
            ).hexdigest(),
        }
    )
    return await ingest_experience(
        db,
        owner_user_id=owner_user_id,
        payload=OmegaExperienceIn(
            source_kind="COGNITIVE_EVENT",
            source_id=event.id,
            orbit_id=event.orbit_id,
            event_kind=event.event_kind,
            scope=event.scope,
            summary=event.content_text or str(event.structured_payload)[:900],
            raw_ref={"table": "cognitive_events", "id": str(event.id)},
            provenance_label=label,
            source_domain=source_domain,
            features={
                **features,
                "canonical_source_kind": source_kind,
                "canonical_source_id": str(source_id),
            },
            explicitness=explicitness,
            retention_policy=(
                "EPHEMERAL" if event.scope == "EPHEMERAL" else "SOURCE_BOUND"
            ),
            observed_at=event.created_at,
            source_fingerprint=fingerprint,
        ),
    )


async def ingest_from_domain_event(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    event: DomainEvent,
) -> OmegaExperience:
    features = {
        "event_type": event.event_type,
        "aggregate_type": event.aggregate_type,
        "aggregate_id": str(event.aggregate_id),
        **_selected_features(event.event_payload or {}),
    }
    return await ingest_experience(
        db,
        owner_user_id=owner_user_id,
        payload=OmegaExperienceIn(
            source_kind="DOMAIN_EVENT",
            source_id=event.id,
            event_kind=event.event_type.upper().replace(".", "_")[:96],
            summary=f"{event.event_type} on {event.aggregate_type}",
            raw_ref={"table": "domain_events", "id": str(event.id)},
            provenance_label="SYSTEM_MEASURED",
            source_domain=_domain_event_domain(event.aggregate_type, event.event_type),
            features=features,
            explicitness="SYSTEM_OBSERVED",
            retention_policy="SOURCE_BOUND",
            observed_at=event.occurred_at,
            source_fingerprint=_fingerprint(
                {
                    "event_id": str(event.id),
                    "event_type": event.event_type,
                    "aggregate_type": event.aggregate_type,
                    "aggregate_id": str(event.aggregate_id),
                    "features": features,
                }
            ),
        ),
    )


_OBJECT_SOURCE_KINDS = {
    "am_project": "AM_PROJECT",
    "goal": "GOAL",
    "outcome": "OUTCOME",
    "plan": "PLAN",
    "plan_step": "PLAN_STEP",
    "system_action": "SYSTEM_ACTION",
    "timeline_event": "TIMELINE_EVENT",
    "orbit": "ORBIT",
    "person": "PERSON",
}

_SOURCE_PREFIX_KINDS = {
    "am_project": "AM_PROJECT",
    "goal": "GOAL",
    "outcome": "OUTCOME",
    "plan": "PLAN",
    "plan_step": "PLAN_STEP",
    "system_action": "SYSTEM_ACTION",
    "timeline_event": "TIMELINE_EVENT",
    "orbit": "ORBIT",
}

_FEATURE_KEYS = {
    "action",
    "goal_id",
    "object_id",
    "object_type",
    "outcome_id",
    "person_id",
    "plan_id",
    "project_id",
    "status",
    "system_action_id",
    "system_slug",
    "timeline_kind",
    "workflow_id",
}


async def _canonical_cognitive_source(
    db: AsyncSession, event: CognitiveEvent
) -> tuple[str, uuid.UUID]:
    payload = event.structured_payload or {}
    object_type = str(payload.get("object_type") or "").lower()
    object_id = _as_uuid(payload.get("object_id"))
    if object_type in _OBJECT_SOURCE_KINDS and object_id is not None:
        return _OBJECT_SOURCE_KINDS[object_type], object_id

    source_ref = event.source_ref or ""
    if ":" in source_ref:
        prefix, raw_id = source_ref.split(":", 1)
        parsed_id = _as_uuid(raw_id)
        if parsed_id is not None and prefix in _SOURCE_PREFIX_KINDS:
            return _SOURCE_PREFIX_KINDS[prefix], parsed_id

    if event.event_kind == "JOURNAL_ENTRY":
        journal_id = (
            await db.execute(
                select(JournalEntry.id).where(
                    JournalEntry.owner_user_id == event.owner_user_id,
                    JournalEntry.event_id == event.id,
                )
            )
        ).scalar_one_or_none()
        if journal_id is not None:
            return "JOURNAL_ENTRY", journal_id
    return "COGNITIVE_EVENT", event.id


async def _cognitive_features(
    db: AsyncSession,
    *,
    event: CognitiveEvent,
    source_kind: str,
    source_id: uuid.UUID,
) -> dict:
    payload = event.structured_payload or {}
    timeline_kind = str(payload.get("timeline_kind") or "").upper()
    features = {
        "event_kind": event.event_kind,
        "signal": _signal_for(event.event_kind, timeline_kind, event.content_text or ""),
        **_selected_features(payload),
    }
    if source_kind == "SYSTEM_ACTION":
        action = (
            await db.execute(
                select(SystemAction).where(
                    SystemAction.owner_user_id == event.owner_user_id,
                    SystemAction.id == source_id,
                )
            )
        ).scalar_one_or_none()
        if action is not None:
            features.update(
                {
                    "status": action.status,
                    "effort_minutes": action.effort_minutes,
                    "goal_id": str(action.goal_id) if action.goal_id else None,
                    "system_slug": action.system_slug,
                }
            )
    elif source_kind == "PLAN_STEP":
        step = (
            await db.execute(
                select(PlanStep).where(
                    PlanStep.owner_user_id == event.owner_user_id,
                    PlanStep.id == source_id,
                )
            )
        ).scalar_one_or_none()
        if step is not None:
            features.update(
                {
                    "status": "COMPLETED" if step.done else "OPEN",
                    "plan_id": str(step.plan_id),
                }
            )
    return {key: value for key, value in features.items() if value is not None}


def _cognitive_domain(event: CognitiveEvent) -> str:
    payload = event.structured_payload or {}
    object_type = str(payload.get("object_type") or "").lower()
    timeline_kind = str(payload.get("timeline_kind") or "").upper()
    if event.event_kind == "TALK_TURN":
        return "TALK"
    if event.event_kind == "JOURNAL_ENTRY":
        return "JOURNAL"
    if event.event_kind in {"PLAN_CREATED", "PLAN_STEP"}:
        return "PLAN"
    if event.event_kind == "OUTCOME_REPORTED" or object_type == "outcome":
        return "OUTCOME"
    if event.event_kind == "USER_CORRECTION":
        return "CORRECTION"
    if event.event_kind.startswith("RESEARCH") or "RESEARCH" in timeline_kind:
        return "RESEARCH"
    if object_type.startswith("am_project"):
        return "PROJECTS"
    if object_type in {"goal", "objective", "system_action", "system_diagnostic"}:
        return "LIVING"
    if object_type in {"person", "orbit"}:
        return "ORBITS"
    if object_type == "timeline_event":
        return "TIMELINE"
    if event.source_ref and event.source_ref.startswith("insight:"):
        return "INSIGHTS"
    return "SYSTEM"


def _domain_event_domain(aggregate_type: str, event_type: str) -> str:
    token = f"{aggregate_type} {event_type}".lower()
    for needle, domain in (
        ("memory", "MEMORY"),
        ("learning", "LEARNING"),
        ("project", "PROJECTS"),
        ("workflow", "AGENCY"),
        ("billing", "BILLING"),
        ("community", "COMMUNITY"),
        ("research", "RESEARCH"),
        ("orbit", "ORBITS"),
        ("insight", "INSIGHTS"),
    ):
        if needle in token:
            return domain
    return "SYSTEM"


def _signal_for(event_kind: str, timeline_kind: str, content: str) -> str:
    token = f"{event_kind} {timeline_kind} {content[:80]}".upper()
    if any(word in token for word in ("MISSED", "FAILED", "REJECTED", "BLOCKED", "REOPENED")):
        return "COUNTER"
    if event_kind == "OUTCOME_REPORTED" or any(
        word in token for word in ("COMPLETED", "OUTCOME_RETURNED", "RESOLVED", "DONE:")
    ):
        return "SUPPORT"
    return "CONTEXT"


def _selected_features(payload: dict) -> dict:
    return {
        key: payload[key]
        for key in sorted(_FEATURE_KEYS)
        if key in payload and isinstance(payload[key], (str, int, float, bool, type(None)))
    }


def _as_uuid(value: object) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError):
        return None


def _fingerprint(payload: dict) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


async def list_experiences(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None = None,
    kind: str | None = None,
    limit: int = 50,
) -> list[OmegaExperience]:
    q = (
        select(OmegaExperience)
        .where(OmegaExperience.owner_user_id == owner_user_id)
        .order_by(OmegaExperience.created_at.desc())
        .limit(min(limit, 200))
    )
    if orbit_id:
        q = q.where(OmegaExperience.orbit_id == orbit_id)
    if kind:
        q = q.where(OmegaExperience.event_kind == kind)
    return list((await db.execute(q)).scalars())
