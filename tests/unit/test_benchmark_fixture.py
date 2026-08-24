from __future__ import annotations

from pathlib import Path

from benchmarks.generate_fixture import generate_fixture


def test_benchmark_fixture_is_exactly_100000_lines_and_deterministic(tmp_path: Path) -> None:
    first = generate_fixture(tmp_path / "first")
    second = generate_fixture(tmp_path / "second")

    first_files = sorted(path.relative_to(first) for path in first.rglob("*.py"))
    second_files = sorted(path.relative_to(second) for path in second.rglob("*.py"))
    assert first_files == second_files
    assert (
        sum(len((first / path).read_text(encoding="utf-8").splitlines()) for path in first_files)
        == 100_000
    )
    assert all((first / path).read_bytes() == (second / path).read_bytes() for path in first_files)
