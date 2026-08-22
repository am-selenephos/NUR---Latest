import datetime as dt
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mind.why_changed import ChangeClass, EntityType, WhyChangedService
from app.models import OmegaClaim
from app.omega.evidence_graph import link_evidence
from app.omega.safety_law import allowed_truth_status_for_provenance, redact_secrets
from app.omega.schemas import OmegaClaimIn


async def create_claim(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    payload: OmegaClaimIn,
) -> OmegaClaim:
    text, secret_found = redact_secrets(payload.claim_text, max_len=1600)
    truth_status = allowed_truth_status_for_provenance(payload.provenance_label, payload.truth_status)
    if secret_found:
        truth_status = "HYPOTHESIS"
    row = OmegaClaim(
        owner_user_id=owner_user_id,
        orbit_id=payload.orbit_id,
        claim_text=text,
        claim_type=payload.claim_type,
        truth_status=truth_status,
        confidence=payload.confidence,
    )
    db.add(row)
    await db.flush()
    if payload.evidence_id:
        await link_evidence(
            db,
            owner_user_id=owner_user_id,
            claim_id=row.id,
            evidence_kind=payload.evidence_kind,
            evidence_id=payload.evidence_id,
            relation="SUPPORTS",
            note=f"created from {payload.provenance_label}",
        )
    supporting_evidence = (
        [f"{payload.evidence_kind}:{payload.evidence_id}"]
        if payload.evidence_id
        else []
    )
    evidence_note = (
        " Supporting evidence was linked."
        if supporting_evidence
        else ""
    )
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OMEGA_CLAIM,
        entity_id=str(row.id),
        change_class=ChangeClass.CREATED,
        trigger=(
            "Claim created as a held owner-visible record; this ledger exposes "
            f"state transitions, not hidden reasoning.{evidence_note}"
        ),
        new_version=row.truth_status,
        supporting_evidence=supporting_evidence,
        actor=("owner" if payload.provenance_label.startswith("OWNER_") else "system"),
        affected_future_behavior="The claim may inform Insights only within its governed truth status.",
    )
    return row


async def list_claims(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    orbit_id: uuid.UUID | None = None,
    status: str | None = None,
    claim_type: str | None = None,
    limit: int = 50,
) -> list[OmegaClaim]:
    q = (
        select(OmegaClaim)
        .where(OmegaClaim.owner_user_id == owner_user_id)
        .order_by(OmegaClaim.updated_at.desc(), OmegaClaim.created_at.desc())
        .limit(min(limit, 200))
    )
    if orbit_id:
        q = q.where(OmegaClaim.orbit_id == orbit_id)
    if status:
        q = q.where(OmegaClaim.truth_status == status)
    if claim_type:
        q = q.where(OmegaClaim.claim_type == claim_type)
    return list((await db.execute(q)).scalars())


async def confirm_claim(db: AsyncSession, *, owner_user_id: uuid.UUID, claim_id: uuid.UUID) -> OmegaClaim:
    row = await _claim(db, owner_user_id=owner_user_id, claim_id=claim_id)
    previous_status = row.truth_status
    row.truth_status = "OBSERVED"
    row.confidence = max(float(row.confidence or 0.5), 0.8)
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OMEGA_CLAIM,
        entity_id=str(row.id),
        change_class=ChangeClass.PROMOTED,
        trigger="Owner confirmed the held claim as observed.",
        previous_version=previous_status,
        new_version=row.truth_status,
        owner_correction=True,
        actor="owner",
        affected_future_behavior="The confirmed claim may be shown as owner-observed evidence.",
    )
    await db.flush()
    return row


async def retire_claim(db: AsyncSession, *, owner_user_id: uuid.UUID, claim_id: uuid.UUID) -> OmegaClaim:
    row = await _claim(db, owner_user_id=owner_user_id, claim_id=claim_id)
    previous_status = row.truth_status
    row.truth_status = "RETIRED"
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OMEGA_CLAIM,
        entity_id=str(row.id),
        change_class=ChangeClass.RETRACTED,
        trigger="Owner retired the claim from active interpretation.",
        previous_version=previous_status,
        new_version=row.truth_status,
        owner_correction=True,
        actor="owner",
        affected_future_behavior="The retired claim is excluded from active interpretation.",
    )
    await db.flush()
    return row


async def weaken_claim_for_correction(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    claim_id: uuid.UUID,
    correction_event_id: uuid.UUID,
    note: str,
) -> OmegaClaim:
    row = await _claim(db, owner_user_id=owner_user_id, claim_id=claim_id)
    previous_status = row.truth_status
    previous_confidence = float(row.confidence or 0.5)
    await link_evidence(
        db,
        owner_user_id=owner_user_id,
        claim_id=row.id,
        evidence_kind="CORRECTION",
        evidence_id=correction_event_id,
        relation="CONTRADICTS",
        strength=1.0,
        note=note,
    )
    row.confidence = max(0.05, float(row.confidence or 0.5) - 0.25)
    row.updated_at = dt.datetime.now(dt.timezone.utc)
    await WhyChangedService.record_change(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OMEGA_CLAIM,
        entity_id=str(row.id),
        change_class=ChangeClass.CONTRADICTED,
        trigger="Owner correction linked counter-evidence and weakened the claim.",
        previous_version=f"{previous_status}:{previous_confidence:.4f}",
        new_version=f"{row.truth_status}:{float(row.confidence):.4f}",
        counter_evidence=[f"CORRECTION:{correction_event_id}"],
        owner_correction=True,
        actor="owner",
        affected_future_behavior="Later interpretation must account for the owner correction.",
    )
    await db.flush()
    return row


async def _claim(db: AsyncSession, *, owner_user_id: uuid.UUID, claim_id: uuid.UUID) -> OmegaClaim:
    row = (await db.execute(select(OmegaClaim).where(
        OmegaClaim.id == claim_id,
        OmegaClaim.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if not row:
        raise PermissionError("Claim not found.")
    return row
