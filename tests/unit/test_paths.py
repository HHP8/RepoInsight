from __future__ import annotations

import importlib
from pathlib import Path

import pytest


def test_normalize_relative_path_returns_posix_path(tmp_path: Path) -> None:
    paths = importlib.import_module("repoinsight.paths")
    candidate = tmp_path / "src" / "package" / "module.py"

    assert paths.normalize_relative_path(tmp_path, candidate) == "src/package/module.py"
    assert paths.normalize_relative_path(tmp_path, Path("src/package/module.py")) == (
        "src/package/module.py"
    )


@pytest.mark.parametrize("candidate", [Path("..") / "secret.py", Path("."), Path("../other")])
def test_normalize_relative_path_rejects_traversal_and_root(
    tmp_path: Path, candidate: Path
) -> None:
    paths = importlib.import_module("repoinsight.paths")

    with pytest.raises(ValueError):
        paths.normalize_relative_path(tmp_path, candidate)


def test_normalize_relative_path_rejects_symlink_escape(tmp_path: Path) -> None:
    paths = importlib.import_module("repoinsight.paths")
    outside = tmp_path.parent / f"{tmp_path.name}-outside"
    outside.mkdir()
    link = tmp_path / "escape"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Symlink creation is not available")

    with pytest.raises(ValueError):
        paths.normalize_relative_path(tmp_path, link / "secret.py")
