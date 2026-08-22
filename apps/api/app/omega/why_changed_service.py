import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.mind.why_changed import EntityType, WhyChangedRecord, WhyChangedService
from app.models import OmegaClaim, OmegaEvidenceEdge
from app.omega.schemas import OmegaWhyChanged


async def explain_why_claim_changed(
    db: AsyncSession,
    *,
    owner_user_id: uuid.UUID,
    claim_id: uuid.UUID,
) -> OmegaWhyChanged:
    claim = (await db.execute(select(OmegaClaim).where(
        OmegaClaim.id == claim_id,
        OmegaClaim.owner_user_id == owner_user_id,
    ))).scalar_one_or_none()
    if not claim:
        raise PermissionError("Claim not found.")
    edges = list((await db.execute(select(OmegaEvidenceEdge).where(
        OmegaEvidenceEdge.owner_user_id == owner_user_id,
        OmegaEvidenceEdge.claim_id == claim_id,
    ).order_by(OmegaEvidenceEdge.created_at.desc()).limit(25))).scalars())
    supports = [_edge_summary(e) for e in edges if e.relation == "SUPPORTS"]
    contradicts = [_edge_summary(e) for e in edges if e.relation == "CONTRADICTS"]
    history = await WhyChangedService.get_change_history(
        db,
        owner_user_id=owner_user_id,
        entity_type=EntityType.OMEGA_CLAIM.value,
        entity_id=str(claim_id),
        limit=25,
    )
    changed = [
        _change_summary(record)
        for record in history
        if record.trigger
    ]
    if not changed:
        changed.append(
            "No canonical WhyChanged transition is recorded for this legacy claim; "
            "evidence edges remain visible but do not invent an explanation."
        )
    return OmegaWhyChanged(
        claim_id=claim.id,
        claim_text=claim.claim_text,
        current_truth_status=claim.truth_status,
        current_confidence=float(claim.confidence or 0.0),
        changed_because=changed,
        supporting_edges=supports,
        contradicting_edges=contradicts,
        unresolved_note=None if edges else "No evidence edge has been recorded for this claim yet.",
    )


def _edge_summary(edge: OmegaEvidenceEdge) -> str:
    note = f" · {edge.note}" if edge.note else ""
    return f"{edge.relation} via {edge.evidence_kind} ({edge.evidence_id}) strength {float(edge.strength or 0):.2f}{note}"


def _change_summary(record: WhyChangedRecord) -> str:
    if record.previous_version is None and record.new_version is None:
        return record.trigger
    previous = record.previous_version or "none"
    current = record.new_version or "none"
    return f"{record.trigger} [{previous} -> {current}]"
