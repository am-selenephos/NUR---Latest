"""NUR Mind Scope Resolver — first-class scope contract before retrieval.

Implements directive §8.1: scope resolution occurs before retrieval and
before provider invocation.  No memory, research, connector, project, or
social context is fetched until an explicit ``ScopeEnvelope`` exists.

Failure behavior: if scope cannot be resolved, BLOCK — do not retrieve,
do not invoke provider, persist safe failure reason.
"""
from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.brain.schemas import ScopeEnvelope
from app.models import Orbit


class ScopeResolutionError(Exception):
    """Raised when scope cannot be resolved — retrieval and provider are blocked."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


# ── Default record classes per surface ──────────────────────────────────────

_SURFACE_RECORD_CLASSES: dict[str, list[str]] = {
    "talk": [
        "TALK_TURN", "MODEL_RESPONSE", "JOURNAL_ENTRY", "PLAN_CREATED",
        "PLAN_STEP", "OUTCOME_REPORTED", "RESEARCH_DRAFT", "USER_CORRECTION",
    ],
    "journal": ["JOURNAL_ENTRY", "USER_CORRECTION"],
    "plan": ["PLAN_CREATED", "PLAN_STEP", "OUTCOME_REPORTED", "USER_CORRECTION"],
    "research": [
        "RESEARCH_DRAFT", "RESEARCH_BRIEF_CREATED", "RESEARCH_SOURCE_NOTE_ADDED",
        "WEB_SIGNAL_QUESTION_STAGED", "WEB_SIGNAL_NOTE_ADDED",
    ],
    "today": [
        "PLAN_CREATED", "PLAN_STEP", "OUTCOME_REPORTED", "TALK_TURN",
    ],
    "systems": ["TALK_TURN", "MODEL_RESPONSE", "OUTCOME_REPORTED"],
    "challenge": [
        "TALK_TURN", "MODEL_RESPONSE", "JOURNAL_ENTRY", "PLAN_CREATED",
        "PLAN_STEP", "OUTCOME_REPORTED", "RESEARCH_DRAFT", "USER_CORRECTION",
    ],
    "reflect": [
        "TALK_TURN", "MODEL_RESPONSE", "JOURNAL_ENTRY", "USER_CORRECTION",
    ],
    "summarize": [
        "TALK_TURN", "MODEL_RESPONSE", "JOURNAL_ENTRY", "PLAN_CREATED",
        "PLAN_STEP", "OUTCOME_REPORTED", "RESEARCH_DRAFT",
    ],
}


async def resolve_scope(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    surface: str = "talk",
    orbit_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    capsule_id: uuid.UUID | None = None,
    community_id: uuid.UUID | None = None,
    memory_mode: str = "EPHEMERAL",
    connector_identity: str | None = None,
) -> ScopeEnvelope:
    """Resolve a ``ScopeEnvelope`` before retrieval and provider invocation.

    Raises ``ScopeResolutionError`` if the scope cannot be established.
    """
    # 1. Validate orbit ownership if specified
    if orbit_id is not None:
        row = (
            await db.execute(
                select(Orbit.id).where(
                    Orbit.id == orbit_id,
                    Orbit.owner_user_id == owner_user_id,
                )
            )
        ).scalar_one_or_none()
        if row is None:
            raise ScopeResolutionError(
                f"Orbit {orbit_id} is not owned by user {owner_user_id}. "
                "Retrieval and provider invocation are blocked."
            )

    # 2. Determine sharing boundary
    if community_id is not None:
        sharing_boundary = "COMMUNITY"
    elif capsule_id is not None:
        sharing_boundary = "CAPSULE"
    elif project_id is not None:
        sharing_boundary = "PROJECT"
    elif orbit_id is not None:
        sharing_boundary = "ORBIT"
    else:
        sharing_boundary = "PRIVATE"

    # 3. Map memory mode to read/write policies
    memory_write_policy = memory_mode  # "EPHEMERAL" or "REVIEW"
    memory_read_policy = "SCOPED"
    if memory_mode == "EPHEMERAL":
        # Ephemeral mode: read existing memories but don't write new ones
        memory_read_policy = "SCOPED"
    elif memory_mode == "REVIEW":
        # Review mode: full read, write candidates for owner review
        memory_read_policy = "SCOPED"

    # 4. Determine sensitivity ceiling
    sensitivity_ceiling = "NORMAL"
    if surface in ("journal", "reflect"):
        sensitivity_ceiling = "ELEVATED"

    # 5. Get allowed record classes for this surface
    task_class = surface if surface in _SURFACE_RECORD_CLASSES else "talk"
    allowed_record_classes = _SURFACE_RECORD_CLASSES.get(task_class, _SURFACE_RECORD_CLASSES["talk"])

    # 6. Build the envelope
    reason = f"Scope resolved for surface={surface}"
    if orbit_id:
        reason += f", orbit={orbit_id}"
    if project_id:
        reason += f", project={project_id}"

    return ScopeEnvelope(
        owner_user_id=owner_user_id,
        surface=surface,
        allowed_record_classes=allowed_record_classes,
        excluded_record_classes=[],
        sharing_boundary=sharing_boundary,
        connector_boundary=connector_identity,
        memory_read_policy=memory_read_policy,
        memory_write_policy=memory_write_policy,
        retention_policy="DEFAULT",
        sensitivity_ceiling=sensitivity_ceiling,
        orbit_id=orbit_id,
        project_id=project_id,
        capsule_id=capsule_id,
        community_id=community_id,
        reason=reason,
        policy_versions={"scope_resolver": "1.0.0"},
    )
