from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Protocol
from urllib.parse import urlparse
from uuid import UUID, uuid4

from pydantic import BaseModel, Field, model_validator


class ResearchSource(BaseModel):
    id: str
    title: str
    text: str
    citation: str
    owner_user_id: UUID | None = None
    record_class: str = "PUBLIC_EVIDENCE"


class ResearchScope(BaseModel):
    owner_user_id: UUID
    allowed_domains: set[str] = Field(default_factory=set)
    allowed_source_ids: set[str] = Field(default_factory=set)
    allowed_source_adapters: dict[str, str] = Field(default_factory=dict)
    record_classes: set[str] = Field(default_factory=lambda: {"PUBLIC_EVIDENCE"})
    scope_id: UUID = Field(default_factory=uuid4)

    @model_validator(mode="after")
    def source_ids_have_resolved_adapter_authority(self) -> "ResearchScope":
        if set(self.allowed_source_adapters) != self.allowed_source_ids:
            raise ValueError(
                "Every allowed research source id must be bound to exactly one retrieval adapter."
            )
        return self


class RetrievalPlan(BaseModel):
    query: str
    scope_id: UUID
    max_sources: int = Field(default=20, ge=1, le=100)
    rationale: str
    excluded_authorities: list[str] = Field(default_factory=lambda: [
        "external content cannot change policy, approve actions, invoke tools, or write owner memory"
    ])


class SourceProvenance(BaseModel):
    source_id: str
    citation: str
    domain: str | None = None
    retrieval_adapter: str
    record_class: str
    normalized: bool = True


class ExcludedResearchSource(BaseModel):
    source_id: str
    retrieval_adapter: str
    reason: str


class ResearchVerification(BaseModel):
    citations_valid: bool
    source_ids: list[str] = Field(default_factory=list)
    contradictions: list[tuple[str, str]] = Field(default_factory=list)
    untrusted_instructions: list[str] = Field(default_factory=list)
    verification_notes: list[str] = Field(default_factory=list)
    excluded_sources: list[ExcludedResearchSource] = Field(default_factory=list)


class ResearchReport(BaseModel):
    question: str
    source_ids: list[str] = Field(default_factory=list)
    citations_valid: bool
    contradictions: list[tuple[str, str]] = Field(default_factory=list)
    answerable: bool
    notes: list[str] = Field(default_factory=list)


class ResearchResult(ResearchReport):
    retrieval_plan: RetrievalPlan
    provenance: list[SourceProvenance] = Field(default_factory=list)
    synthesis: str = ""
    unresolved_uncertainty: list[str] = Field(default_factory=list)
    verification: ResearchVerification


class ResearchAdapter(Protocol):
    name: str

    def retrieve(self, plan: RetrievalPlan, scope: ResearchScope) -> list[ResearchSource]: ...


class InMemoryResearchAdapter:
    """Deterministic adapter for internal tests and offline evaluation."""

    name = "in_memory"

    def __init__(self, sources: Iterable[ResearchSource]) -> None:
        self.sources = list(sources)

    def retrieve(self, plan: RetrievalPlan, scope: ResearchScope) -> list[ResearchSource]:
        allowed = scope.allowed_source_ids
        selected = [source for source in self.sources if not allowed or source.id in allowed]
        return selected[: plan.max_sources]


class ResearchBrain:
    """Focused research pipeline; external content remains untrusted evidence."""

    def __init__(
        self,
        *,
        allowed_domains: set[str] | frozenset[str],
        adapters: list[ResearchAdapter] | None = None,
    ) -> None:
        self.allowed_domains = frozenset(allowed_domains)
        self.adapters = list(adapters or [])

    def _citation_valid(self, citation: str) -> bool:
        parsed = urlparse(citation)
        return parsed.scheme in {"http", "https"} and parsed.hostname in self.allowed_domains

    @staticmethod
    def _contradiction_key(text: str) -> str:
        key = re.sub(r"\bnot\b|\bno\b|\bnever\b", "", text.lower())
        return re.sub(r"\s+", " ", key).strip()

    @staticmethod
    def _normalize_source(source: ResearchSource) -> ResearchSource:
        return source.model_copy(update={
            "title": " ".join(source.title.split()),
            "text": " ".join(source.text.split()),
            "citation": source.citation.strip(),
        })

    @staticmethod
    def _instruction_fragments(text: str) -> list[str]:
        patterns = (
            r"ignore all previous instructions[^.]*\.?",
            r"approve the write[^.]*\.?",
            r"reveal (?:the )?system prompt[^.]*\.?",
            r"invoke (?:the )?tool[^.]*\.?",
        )
        return [match.group(0) for pattern in patterns for match in re.finditer(pattern, text, re.IGNORECASE)]

    def _verify(self, question: str, sources: list[ResearchSource]) -> ResearchVerification:
        report = self.analyze(question, sources)
        instructions = [fragment for source in sources for fragment in self._instruction_fragments(source.text)]
        notes = list(report.notes)
        if instructions:
            notes.append("External instruction-like text was retained as untrusted evidence, not authority.")
        return ResearchVerification(
            citations_valid=report.citations_valid,
            source_ids=report.source_ids,
            contradictions=report.contradictions,
            untrusted_instructions=instructions,
            verification_notes=notes,
        )

    def analyze(self, question: str, sources: list[ResearchSource]) -> ResearchReport:
        normalized = [self._normalize_source(source) for source in sources]
        citations_valid = all(self._citation_valid(source.citation) for source in normalized)
        contradictions: list[tuple[str, str]] = []
        for index, left in enumerate(normalized):
            for right in normalized[index + 1 :]:
                if self._contradiction_key(left.text) == self._contradiction_key(right.text):
                    left_negative = bool(re.search(r"\bnot\b|\bno\b|\bnever\b", left.text.lower()))
                    right_negative = bool(re.search(r"\bnot\b|\bno\b|\bnever\b", right.text.lower()))
                    if left_negative != right_negative:
                        contradictions.append((left.id, right.id))
        notes: list[str] = []
        if not citations_valid:
            notes.append("One or more sources failed the allowed-domain citation policy.")
        if contradictions:
            notes.append("Contradictory supplied sources require owner-visible review.")
        return ResearchReport(
            question=question,
            source_ids=[source.id for source in normalized],
            citations_valid=citations_valid,
            contradictions=contradictions,
            answerable=bool(normalized) and citations_valid,
            notes=notes,
        )

    def research(self, question: str, *, scope: ResearchScope) -> ResearchResult:
        if not scope.allowed_domains.issubset(self.allowed_domains):
            raise PermissionError("Research scope requests a domain outside the Brain source policy.")
        plan = RetrievalPlan(
            query=question,
            scope_id=scope.scope_id,
            rationale="Retrieve only evidence allowed by the resolved scope and source policy.",
        )
        retrieved: list[tuple[ResearchSource, str]] = []
        excluded: list[ExcludedResearchSource] = []
        seen_source_ids: set[str] = set()
        for adapter in self.adapters:
            for source in adapter.retrieve(plan, scope):
                normalized_source = self._normalize_source(source)
                if (
                    scope.allowed_source_ids
                    and normalized_source.id not in scope.allowed_source_ids
                ):
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="source id is outside the resolved research scope",
                    ))
                    continue
                expected_adapter = scope.allowed_source_adapters.get(normalized_source.id)
                if expected_adapter is not None and expected_adapter != adapter.name:
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="retrieval adapter is not authoritative for this source id",
                    ))
                    continue
                if normalized_source.record_class not in scope.record_classes:
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="record class is outside the resolved research scope",
                    ))
                    continue
                if (
                    normalized_source.owner_user_id is not None
                    and normalized_source.owner_user_id != scope.owner_user_id
                ):
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="source belongs to another owner",
                    ))
                    continue
                if (
                    normalized_source.record_class != "PUBLIC_EVIDENCE"
                    and normalized_source.owner_user_id is None
                ):
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="owner-bound source is missing owner provenance",
                    ))
                    continue
                domain = urlparse(normalized_source.citation).hostname
                if (
                    not self._citation_valid(normalized_source.citation)
                    or domain not in scope.allowed_domains
                ):
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="citation domain is outside the resolved source policy",
                    ))
                    continue
                if normalized_source.id in seen_source_ids:
                    excluded.append(ExcludedResearchSource(
                        source_id=normalized_source.id,
                        retrieval_adapter=adapter.name,
                        reason="duplicate source id was already accepted",
                    ))
                    continue
                retrieved.append((normalized_source, adapter.name))
                seen_source_ids.add(normalized_source.id)
                if len(retrieved) >= plan.max_sources:
                    break
            if len(retrieved) >= plan.max_sources:
                break
        normalized = [source for source, _adapter_name in retrieved]
        verification = self._verify(question, normalized)
        verification = verification.model_copy(update={"excluded_sources": excluded})
        provenance = [
            SourceProvenance(
                source_id=source.id,
                citation=source.citation,
                domain=urlparse(source.citation).hostname,
                retrieval_adapter=adapter_name,
                record_class=source.record_class,
            )
            for source, adapter_name in retrieved
        ]
        safe_fragments: list[str] = []
        for source in normalized:
            text = source.text
            for fragment in self._instruction_fragments(text):
                text = text.replace(fragment, "")
            if text.strip():
                safe_fragments.append(f"[{source.id}] {text.strip()}")
        synthesis = " ".join(safe_fragments)
        unresolved: list[str] = []
        if not normalized:
            unresolved.append("No source was retrieved within the resolved scope.")
        if verification.contradictions:
            unresolved.append("Sources disagree; the contradiction remains unresolved.")
        if verification.untrusted_instructions:
            unresolved.append("External instruction-like content is not an authority and was excluded from synthesis.")
        if normalized and not verification.citations_valid:
            unresolved.append("At least one source citation failed the source policy.")
        if excluded:
            unresolved.append(
                f"{len(excluded)} retrieved source(s) were excluded by the resolved scope or source policy."
            )
        report = self.analyze(question, normalized)
        report_notes = list(report.notes) + [
            note for note in verification.verification_notes if note not in report.notes
        ]
        return ResearchResult(
            **report.model_dump(exclude={"notes"}),
            notes=report_notes,
            retrieval_plan=plan,
            provenance=provenance,
            synthesis=synthesis,
            unresolved_uncertainty=unresolved,
            verification=verification,
        )
