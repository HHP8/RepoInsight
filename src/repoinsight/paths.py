"""Repository path normalization at the public-report boundary."""

from __future__ import annotations

from pathlib import Path


def normalize_relative_path(root: Path, candidate: Path) -> str:
    """Return a contained candidate as a nonempty repository-relative POSIX path."""
    resolved_root = root.resolve(strict=False)
    unresolved_candidate = candidate if candidate.is_absolute() else resolved_root / candidate
    resolved_candidate = unresolved_candidate.resolve(strict=False)
    try:
        relative = resolved_candidate.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("Path is outside the repository root") from error
    if relative == Path("."):
        raise ValueError("Path must identify an entry inside the repository root")
    normalized = relative.as_posix()
    if not normalized or normalized.startswith("../") or "/../" in normalized:
        raise ValueError("Path is not a safe repository-relative path")
    return normalized
