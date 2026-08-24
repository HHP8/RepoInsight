from __future__ import annotations

import pytest
from benchmarks.run_benchmark import run_benchmark


def test_100000_line_target(request: pytest.FixtureRequest) -> None:
    if not request.config.getoption("--benchmark-target"):
        pytest.skip("use --benchmark-target to run the opt-in performance target")

    result = run_benchmark(enforce_target=True)

    assert result["python_lines"] == 100_000
    assert result["target_met"] is True
