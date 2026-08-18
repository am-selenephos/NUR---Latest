from __future__ import annotations

from collections.abc import Callable

from pydantic import BaseModel, Field


class EvaluationCase(BaseModel):
    case_id: str
    split: str
    expected: str
    category: str = "general"
    input: dict[str, str] = Field(default_factory=dict)


class EvaluationCorpus(BaseModel):
    version: str
    cases: list[EvaluationCase] = Field(default_factory=list)

    def by_split(self, split: str) -> list[EvaluationCase]:
        return [case for case in self.cases if case.split == split]


class EvaluationSplitStats(BaseModel):
    split: str
    total: int
    passed: int
    failed: int
    pass_rate: float
    failures: list[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    corpus_version: str
    development: EvaluationSplitStats
    held_out: EvaluationSplitStats
    shadow: EvaluationSplitStats
    observed: dict[str, str] = Field(default_factory=dict)


class PromotionDecision(BaseModel):
    promote: bool
    corpus_version: str
    held_out_pass_rate: float
    shadow_pass_rate: float
    failures: list[str] = Field(default_factory=list)
    reason: str


class EvaluationRunner:
    """Runs a deterministic evaluator over all corpus splits without self-promotion."""

    def __init__(self, corpus: EvaluationCorpus) -> None:
        self.corpus = corpus

    def run(self, evaluator: Callable[[EvaluationCase], str]) -> EvaluationReport:
        observed: dict[str, str] = {}
        for case in self.corpus.cases:
            try:
                observed[case.case_id] = str(evaluator(case))
            except Exception:
                observed[case.case_id] = "ERROR"

        stats: dict[str, EvaluationSplitStats] = {}
        for split in ("development", "held_out", "shadow"):
            cases = self.corpus.by_split(split)
            failures = [case.case_id for case in cases if observed.get(case.case_id) != case.expected]
            passed = len(cases) - len(failures)
            stats[split] = EvaluationSplitStats(
                split=split,
                total=len(cases),
                passed=passed,
                failed=len(failures),
                pass_rate=(passed / len(cases)) if cases else 0.0,
                failures=failures,
            )
        return EvaluationReport(
            corpus_version=self.corpus.version,
            development=stats["development"],
            held_out=stats["held_out"],
            shadow=stats["shadow"],
            observed=observed,
        )


def build_default_evaluation_corpus() -> EvaluationCorpus:
    categories = (
        "planner",
        "simulator",
        "critic",
        "router",
        "research",
        "specialist",
        "memory_learning",
    )
    cases: list[EvaluationCase] = []
    for split in ("development", "held_out", "shadow"):
        for category in categories:
            case_id = f"{split}.{category}.bounded"
            cases.append(
                EvaluationCase(
                    case_id=case_id,
                    split=split,
                    category=category,
                    expected="PASS",
                    input={"category": category, "split": split},
                )
            )
    return EvaluationCorpus(version="brain-agentend-semantic-v1", cases=cases)


class EvaluationGate(BaseModel):
    cases: list[EvaluationCase] = Field(default_factory=list)
    shadow_pass_rate: float = 0.0
    min_held_out_pass_rate: float = 1.0
    min_shadow_pass_rate: float = 1.0
    corpus_version: str = "legacy"

    @classmethod
    def from_corpus(
        cls,
        corpus: EvaluationCorpus,
        *,
        shadow_pass_rate: float | None = None,
        min_held_out_pass_rate: float = 1.0,
        min_shadow_pass_rate: float = 1.0,
    ) -> "EvaluationGate":
        return cls(
            cases=list(corpus.cases),
            shadow_pass_rate=(shadow_pass_rate if shadow_pass_rate is not None else 0.0),
            min_held_out_pass_rate=min_held_out_pass_rate,
            min_shadow_pass_rate=min_shadow_pass_rate,
            corpus_version=corpus.version,
        )

    def evaluate(self, report: EvaluationReport) -> PromotionDecision:
        failures = list(report.held_out.failures) + list(report.shadow.failures)
        shadow_rate = report.shadow.pass_rate
        held_out_rate = report.held_out.pass_rate
        if self.shadow_pass_rate:
            shadow_rate = min(shadow_rate, self.shadow_pass_rate)
        promote = bool(
            report.corpus_version == self.corpus_version
            and report.held_out.total > 0
            and report.shadow.total > 0
            and held_out_rate >= self.min_held_out_pass_rate
            and shadow_rate >= self.min_shadow_pass_rate
            and not failures
        )
        reason = "held-out and shadow empirical thresholds passed" if promote else "empirical promotion thresholds failed"
        return PromotionDecision(
            promote=promote,
            corpus_version=report.corpus_version,
            held_out_pass_rate=held_out_rate,
            shadow_pass_rate=shadow_rate,
            failures=failures,
            reason=reason,
        )

    def can_promote(self, observed: dict[str, str]) -> bool:
        """Compatibility boundary for legacy callers; still requires held-out data."""
        held_out = [case for case in self.cases if case.split == "held_out"]
        if not held_out or self.shadow_pass_rate < self.min_shadow_pass_rate:
            return False
        return all(observed.get(case.case_id) == case.expected for case in held_out)
