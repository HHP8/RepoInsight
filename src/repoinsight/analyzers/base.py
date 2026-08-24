"""Typed, deterministic execution boundary for built-in analyzers."""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..git import GitHistory
from ..inventory import InventoryResult
from ..models import (
    AnalyzerMetadata,
    AnalyzerResult,
    AnalyzerState,
    AnalyzerStatus,
    Completeness,
    EffectiveConfig,
    Limitation,
    SourceKind,
)
from ..python_index import PythonIndex


@dataclass(frozen=True)
class AnalysisContext:
    """Read-only-by-protocol evidence supplied to every analyzer."""

    inventory: InventoryResult
    python_index: PythonIndex
    git_history: GitHistory
    config: EffectiveConfig
    source_kind: SourceKind
    observed_at: datetime


@dataclass(frozen=True)
class Applicability:
    applies: bool
    completeness: Completeness
    limitations: tuple[str, ...] = ()


class Analyzer(Protocol):
    metadata: AnalyzerMetadata

    def applies(self, context: AnalysisContext) -> Applicability: ...

    def analyze(self, context: AnalysisContext) -> AnalyzerResult: ...


def _elapsed(monotonic: Callable[[], float], started: float) -> float:
    return max(monotonic() - started, 0.0)


def run_analyzers(
    context: AnalysisContext,
    analyzers: Sequence[Analyzer] | None = None,
    *,
    monotonic: Callable[[], float] = time.monotonic,
    deadline: float | None = None,
) -> tuple[AnalyzerResult, ...]:
    """Run the explicit analyzer registry sequentially with failure isolation."""
    if context.observed_at.tzinfo is None or context.observed_at.utcoffset() is None:
        raise ValueError("observed_at must be timezone-aware")

    from .registry import BUILTIN_ANALYZERS, validate_registry

    selected = BUILTIN_ANALYZERS if analyzers is None else tuple(analyzers)
    validate_registry(selected)
    results: list[AnalyzerResult] = []
    for analyzer in selected:
        if deadline is not None and monotonic() >= deadline:
            results.append(
                AnalyzerResult(
                    metadata=analyzer.metadata,
                    status=AnalyzerStatus(
                        analyzer_id=analyzer.metadata.id,
                        state=AnalyzerState.SKIPPED,
                        completeness=Completeness.SKIPPED,
                        elapsed_seconds=0.0,
                        message="Analysis deadline reached",
                    ),
                    limitations=(
                        Limitation(
                            code="analysis-timeout",
                            message=(
                                "Analyzer was skipped because the analysis deadline was reached"
                            ),
                            category=analyzer.metadata.category,
                            analyzer_id=analyzer.metadata.id,
                        ),
                    ),
                )
            )
            continue
        started = monotonic()
        try:
            applicability = analyzer.applies(context)
            if not applicability.applies:
                messages = applicability.limitations or (
                    "Analyzer is not applicable to the available evidence",
                )
                result = AnalyzerResult(
                    metadata=analyzer.metadata,
                    status=AnalyzerStatus(
                        analyzer_id=analyzer.metadata.id,
                        state=AnalyzerState.SKIPPED,
                        completeness=applicability.completeness,
                        elapsed_seconds=0.0,
                        message="Analyzer not applicable",
                    ),
                    limitations=tuple(
                        Limitation(
                            code="analyzer-not-applicable",
                            message=message,
                            category=analyzer.metadata.category,
                            analyzer_id=analyzer.metadata.id,
                        )
                        for message in messages
                    ),
                )
            else:
                result = analyzer.analyze(context)
        except Exception:
            result = AnalyzerResult(
                metadata=analyzer.metadata,
                status=AnalyzerStatus(
                    analyzer_id=analyzer.metadata.id,
                    state=AnalyzerState.FAILED,
                    completeness=Completeness.UNAVAILABLE,
                    elapsed_seconds=0.0,
                    message="Analyzer failed during static analysis",
                ),
                limitations=(
                    Limitation(
                        code="analyzer-failure",
                        message="Analyzer failed during static analysis",
                        category=analyzer.metadata.category,
                        analyzer_id=analyzer.metadata.id,
                    ),
                ),
            )
        elapsed = _elapsed(monotonic, started)
        results.append(
            result.model_copy(
                update={"status": result.status.model_copy(update={"elapsed_seconds": elapsed})}
            )
        )
    return tuple(results)


__all__ = ["AnalysisContext", "Analyzer", "Applicability", "run_analyzers"]
