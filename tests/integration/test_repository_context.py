from __future__ import annotations

import hashlib
import os
import subprocess
from pathlib import Path

import pytest

from repoinsight.acquisition import acquire_source, parse_source
from repoinsight.config import load_config
from repoinsight.git import collect_git_history
from repoinsight.inventory import build_inventory
from repoinsight.models import Completeness
from repoinsight.python_index import build_python_index


def _snapshot(root: Path) -> tuple[tuple[str, str, int, int], ...]:
    records = []
    for path in sorted(root.rglob("*")):
        stat = path.lstat()
        digest = hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else ""
        records.append((path.relative_to(root).as_posix(), digest, stat.st_mtime_ns, stat.st_mode))
    return tuple(records)


def test_local_repository_pipeline_is_read_only_and_handles_malformed_no_git(
    tmp_path: Path,
) -> None:
    (tmp_path / "good.py").write_text("value = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("def bad(:\n", encoding="utf-8")
    before = _snapshot(tmp_path)
    source = parse_source(str(tmp_path))
    with acquire_source(source, load_config(None, None, {})) as acquired:
        inventory = build_inventory(acquired.root, load_config(None, None, {}))
        index = build_python_index(inventory)
        history = collect_git_history(acquired.root, remote=False)
    assert index.completeness is Completeness.PARTIAL
    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert _snapshot(tmp_path) == before


def test_oversized_local_repository_completes_safely(tmp_path: Path) -> None:
    (tmp_path / "large.py").write_bytes(b"x" * 11)
    config = load_config(None, None, {"analysis.max_file_bytes": 10})
    result = build_inventory(tmp_path, config)
    assert result.files == ()
    assert result.completeness is Completeness.PARTIAL
    assert result.skipped_inputs[0].path == "large.py"


def test_successful_git_history_inspection_preserves_repository_metadata(tmp_path: Path) -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "GIT_AUTHOR_NAME": "Fixed Author",
            "GIT_AUTHOR_EMAIL": "fixed@example.test",
            "GIT_COMMITTER_NAME": "Fixed Author",
            "GIT_COMMITTER_EMAIL": "fixed@example.test",
            "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
        }
    )
    subprocess.run(
        ["git", "-c", "safe.directory=*", "init", "-b", "main"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=environment,
    )
    (tmp_path / "tracked.txt").write_text("tracked", encoding="utf-8")
    subprocess.run(
        ["git", "-c", "safe.directory=*", "add", "tracked.txt"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=environment,
    )
    subprocess.run(
        ["git", "-c", "safe.directory=*", "commit", "-m", "fixed"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=environment,
    )
    before = _snapshot(tmp_path)

    history = collect_git_history(tmp_path, remote=False)

    assert history.summary.available is True
    assert _snapshot(tmp_path) == before


def test_remote_clone_is_cleaned_after_downstream_base_exception() -> None:
    roots: list[Path] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        root = Path(argv[-1])
        root.mkdir()
        (root / "ok.py").write_text("x = 1\n", encoding="utf-8")
        roots.append(root)
        return subprocess.CompletedProcess(argv, 0, "", "")

    with (
        pytest.raises(RuntimeError),
        acquire_source(
            parse_source("https://github.com/owner/repo"),
            load_config(None, None, {}),
            runner=runner,
        ) as acquired,
    ):
        assert build_inventory(acquired.root, load_config(None, None, {})).files
        raise RuntimeError("downstream")
    assert roots and all(not root.exists() for root in roots)
