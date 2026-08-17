"""Bounded, citation-first research reasoning over supplied sources only."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from pydantic import BaseModel, Field


class ResearchSource(BaseModel):
    id: str
    title: str
    text: str
    citation: str


class ResearchReport(BaseModel):
    question: str
    source_ids: list[str] = Field(default_factory=list)
    citations_valid: bool
    contradictions: list[tuple[str, str]] = Field(default_factory=list)
    answerable: bool
    notes: list[str] = Field(default_factory=list)


class ResearchBrain:
    """Research role that never fetches a URL or invents an uncited source."""

    def __init__(self, *, allowed_domains: set[str] | frozenset[str]) -> None:
        self.allowed_domains = frozenset(allowed_domains)

    def _citation_valid(self, citation: str) -> bool:
        parsed = urlparse(citation)
        return parsed.scheme in {"http", "https"} and parsed.hostname in self.allowed_domains

    @staticmethod
    def _contradiction_key(text: str) -> str:
        key = re.sub(r"\bnot\b|\bno\b|\bnever\b", "", text.lower())
        return re.sub(r"\s+", " ", key).strip()

    def analyze(self, question: str, sources: list[ResearchSource]) -> ResearchReport:
        citations_valid = all(self._citation_valid(source.citation) for source in sources)
        contradictions: list[tuple[str, str]] = []
        for index, left in enumerate(sources):
            for right in sources[index + 1 :]:
                if self._contradiction_key(left.text) == self._contradiction_key(right.text):
                    left_negative = bool(re.search(r"\bnot\b|\bno\b|\bnever\b", left.text.lower()))
                    right_negative = bool(re.search(r"\bnot\b|\bno\b|\bnever\b", right.text.lower()))
                    if left_negative != right_negative:
                        contradictions.append((left.id, right.id))
        notes = []
        if not citations_valid:
            notes.append("One or more sources failed the allowed-domain citation policy.")
        if contradictions:
            notes.append("Contradictory supplied sources require owner-visible review.")
        return ResearchReport(
            question=question,
            source_ids=[source.id for source in sources],
            citations_valid=citations_valid,
            contradictions=contradictions,
            answerable=bool(sources) and citations_valid,
            notes=notes,
        )
