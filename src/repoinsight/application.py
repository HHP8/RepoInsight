"""Application service orchestrating safe static repository analysis."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, datetime
from typing import TypeVar

from .acquisition import acquire_source, parse_source
from .analyzers.base import AnalysisContext, Analyzer, run_analyzers
from .analyzers.catalog import RULE_CATALOG
from .analyzers.registry import BUILTIN_ANALYZERS
from .config import configuration_fingerprint, load_config
from .exit_codes import ExitCode
from .git import collect_git_history
from .inventory import build_inventory
from .models import (
    AnalysisOutcome,
    AnalysisReport,
    AnalysisRequest,
    AnalyzerState,
    Completeness,
    RunMetadata,
    SourceKind,
    SourceMetadata,
    ToolMetadata,
)
from .normalization import normalize_results
from .python_index import build_python_index
from .reporting.writers import write_reports
from .scoring import score_evidence

_T = TypeVar("_T")


def _deduplicate(
    items: Iterable[_T],
    key: Callable[[_T], tuple[object, ...]],
) -> tuple[_T, ...]:
    unique = {key(item): item for item in items}
    return tuple(unique[item_key] for item_key in sorted(unique, key=repr))


class AnalyzeService:
    """Build one validated in-memory report without writing repository content."""

    def __init__(
        self,
        *,
        analyzers: Sequence[Analyzer] = BUILTIN_ANALYZERS,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
        monotonic: Callable[[], float] = time.monotonic,
        git_executable: str | None = None,
    ) -> None:
        self._analyzers = tuple(analyzers)
        self._now = now
        self._monotonic = monotonic
        self._git_executable = git_executable

    def analyze(self, request: AnalysisRequest) -> AnalysisOutcome:
        started = self._monotonic()
        source = parse_source(request.source)
        if source.kind is SourceKind.LOCAL:
            config = load_config(source.local_path, request.explicit_config, request.cli_overrides)
        else:
            config = load_config(None, request.explicit_config, request.cli_overrides)

        with acquire_source(
            source,
            config,
            git_executable=self._git_executable,
        ) as acquired:
            if source.kind is SourceKind.GITHUB and request.explicit_config is None:
                config = load_config(acquired.root, None, request.cli_overrides)
            inventory = build_inventory(acquired.root, config, monotonic=self._monotonic)
            python_index = build_python_index(inventory)
            git_history = collect_git_history(
                acquired.root,
                remote=source.kind is SourceKind.GITHUB,
                git_executable=self._git_executable,
                timeout_seconds=min(config.analysis.timeout_seconds, 30),
            )
            observed_at = self._now()
            if observed_at.tzinfo is None or observed_at.utcoffset() is None:
                raise ValueError("injected current time must be timezone-aware")
            context = AnalysisContext(
                inventory=inventory,
                python_index=python_index,
                git_history=git_history,
                config=config,
                source_kind=source.kind,
                observed_at=observed_at,
            )
            analyzer_results = run_analyzers(
                context,
                self._analyzers,
                monotonic=self._monotonic,
                deadline=started + config.analysis.timeout_seconds,
            )
            normalized = normalize_results(analyzer_results, RULE_CATALOG, config)
            scorecard = score_evidence(normalized, config)

            skipped_inputs = _deduplicate(
                (
                    *inventory.skipped_inputs,
                    *python_index.skipped_inputs,
                    *normalized.skipped_inputs,
                ),
                lambda item: (item.path, item.reason, item.analyzer_id or ""),
            )
            warnings = _deduplicate(
                (*inventory.warnings, *python_index.warnings, *normalized.warnings),
                lambda item: (
                    item.code,
                    item.message,
                    item.analyzer_id or "",
                    item.location.path if item.location else "",
                    item.location.start_line if item.location else 0,
                ),
            )
            limitations = _deduplicate(
                (*inventory.limitations, *normalized.limitations),
                lambda item: (
                    item.code,
                    item.message,
                    item.category.value if item.category else "",
                    item.analyzer_id or "",
                ),
            )
            partial = inventory.completeness is not Completeness.AVAILABLE or any(
                status.state is not AnalyzerState.SUCCEEDED
                or status.completeness is not Completeness.AVAILABLE
                for status in normalized.analyzer_status
            )
            elapsed = max(self._monotonic() - started, 0.0)
            report = AnalysisReport(
                schema_version="1.0",
                score_contract_version="1.0",
                tool=ToolMetadata(
                    name="RepoInsight",
                    version="1.0.0",
                    schema_version="1.0",
                    score_contract_version="1.0",
                ),
                run=RunMetadata(generated_at=observed_at, elapsed_seconds=elapsed),
                source=SourceMetadata(
                    kind=source.kind,
                    identity=source.canonical_identity,
                    revision=git_history.summary.head_revision,
                    history_completeness=git_history.summary.completeness,
                ),
                configuration_fingerprint=configuration_fingerprint(config),
                completeness=Completeness.PARTIAL if partial else Completeness.AVAILABLE,
                inventory=inventory.summary,
                metrics=normalized.metrics,
                findings=normalized.findings,
                scorecard=scorecard,
                git=git_history.summary,
                skipped_inputs=skipped_inputs,
                warnings=warnings,
                analyzer_status=normalized.analyzer_status,
                limitations=limitations,
            )
            exit_code = ExitCode.SUCCESS
            if (
                report.scorecard.overall_score is not None
                and report.scorecard.overall_score < config.ci.fail_under
            ):
                exit_code = ExitCode.THRESHOLD_FAILED
        output_paths = write_reports(report, request.output_directory, request.formats)
        return AnalysisOutcome(report=report, output_paths=output_paths, exit_code=exit_code)


__all__ = ["AnalyzeService"]
