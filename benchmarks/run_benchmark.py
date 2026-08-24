"""Run the opt-in RepoInsight performance target with environment evidence."""

from __future__ import annotations

import argparse
import json
import os
import platform
import tempfile
import time
from pathlib import Path

from benchmarks.generate_fixture import TOTAL_LINES, generate_fixture
from repoinsight.application import AnalyzeService
from repoinsight.models import AnalysisRequest

TARGET_SECONDS = 30.0


def run_benchmark(*, enforce_target: bool = False) -> dict[str, object]:
    """Generate, analyze, and describe the benchmark without network access."""
    with tempfile.TemporaryDirectory(prefix="repoinsight-benchmark-") as raw_directory:
        root = generate_fixture(Path(raw_directory) / "repository")
        started = time.perf_counter()
        outcome = AnalyzeService().analyze(
            AnalysisRequest(
                source=str(root),
                output_directory=Path(raw_directory) / "unused",
                formats=(),
                cli_overrides={},
            )
        )
        elapsed = time.perf_counter() - started
    result: dict[str, object] = {
        "python": platform.python_version(),
        "implementation": platform.python_implementation(),
        "platform": platform.platform(),
        "processor": platform.processor() or "unreported",
        "logical_cpus": os.cpu_count(),
        "python_lines": TOTAL_LINES,
        "elapsed_seconds": round(elapsed, 3),
        "target_seconds": TARGET_SECONDS,
        "target_met": elapsed < TARGET_SECONDS,
        "report_completeness": outcome.report.completeness.value,
    }
    if enforce_target and elapsed >= TARGET_SECONDS:
        raise RuntimeError(
            f"benchmark took {elapsed:.3f}s, exceeding the {TARGET_SECONDS:.1f}s target"
        )
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--enforce-target", action="store_true")
    arguments = parser.parse_args()
    print(json.dumps(run_benchmark(enforce_target=arguments.enforce_target), sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
