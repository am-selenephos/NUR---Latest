"""NUR Mind Working Memory — deterministic context packing and manifest builder.

Applies token budget, privacy scope boundaries, and explicit source selection.
Produces a ``ContextManifest`` documenting included and excluded sources.
"""
from __future__ import annotations

from typing import Any

from app.brain.schemas import ContextManifest, ContextSource


def build_context_manifest(
    *,
    retrieved_refs: list[dict[str, Any]],
    withheld_items: list[dict[str, Any]] | None = None,
    scope_statement: str = "Private orbit scope",
    token_budget: int = 4096,
) -> tuple[ContextManifest, list[dict[str, Any]]]:
    """Assemble a ``ContextManifest`` and filtered evidence list for the Brain packet.

    Enforces token budget, explicit source attribution, and records why sources
    were included or excluded.
    """
    included_sources: list[ContextSource] = []
    excluded_sources: list[ContextSource] = []
    filtered_evidence: list[dict[str, Any]] = []

    current_tokens = 0
    token_limit = max(500, token_budget - 500)  # Reserve 500 tokens for system/user prompts

    for ref in retrieved_refs:
        kind = str(ref.get("kind", "unknown"))
        ref_id = str(ref.get("id", ""))
        excerpt = str(ref.get("excerpt", ""))
        # Rough token estimate: 1 word ~ 1.3 tokens
        estimated_tokens = max(10, int(len(excerpt.split()) * 1.3))

        if current_tokens + estimated_tokens <= token_limit:
            current_tokens += estimated_tokens
            included_sources.append(ContextSource(
                kind=kind,
                id=ref_id,
                reason=f"Relevant to query (salience rank {ref.get('rank', 0):.2f})"
            ))
            filtered_evidence.append(ref)
        else:
            excluded_sources.append(ContextSource(
                kind=kind,
                id=ref_id,
                reason="Exceeded token budget allocation"
            ))

    for item in withheld_items or []:
        excluded_sources.append(ContextSource(
            kind=str(item.get("kind", "withheld")),
            id=str(item.get("id", "")),
            reason=str(item.get("reason", "Privacy scope restriction"))
        ))

    manifest = ContextManifest(
        scope_statement=scope_statement,
        included=included_sources,
        excluded=excluded_sources,
        token_budget=token_budget,
        token_used=current_tokens,
    )

    return manifest, filtered_evidence
