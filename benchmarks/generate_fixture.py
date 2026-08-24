"""Generate a deterministic 100,000-line Python repository benchmark."""

from __future__ import annotations

from pathlib import Path

MODULE_COUNT = 100
LINES_PER_MODULE = 1_000
TOTAL_LINES = MODULE_COUNT * LINES_PER_MODULE


def generate_fixture(root: Path) -> Path:
    """Create a fresh deterministic benchmark fixture and return its root."""
    if root.exists() and any(root.iterdir()):
        raise ValueError("benchmark fixture directory must be empty")
    package = root / "benchmark_project"
    package.mkdir(parents=True, exist_ok=True)
    for module_index in range(MODULE_COUNT):
        lines = [f'"""Generated benchmark module {module_index:03d}."""']
        lines.extend(
            f"value_{line_index:04d} = {module_index * LINES_PER_MODULE + line_index}"
            for line_index in range(1, LINES_PER_MODULE)
        )
        (package / f"module_{module_index:03d}.py").write_text(
            "\n".join(lines) + "\n",
            encoding="utf-8",
            newline="\n",
        )
    return root


__all__ = ["TOTAL_LINES", "generate_fixture"]
