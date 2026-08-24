from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from repoinsight.config import load_config
from repoinsight.inventory import FileRole, build_inventory
from repoinsight.models import Completeness, EffectiveConfig


def _config(**analysis: object) -> EffectiveConfig:
    return load_config(None, None, {f"analysis.{key}": value for key, value in analysis.items()})


def test_inventory_classifies_roles_and_counts_source_test_lines(tmp_path: Path) -> None:
    files = {
        "src/app.py": "print('source')\n",
        "tests/test_app.py": "def test_it():\n    pass\n",
        "README.md": "# Readme\n",
        "docs/guide.md": "guide\n",
        "CONTRIBUTING.md": "contribute\n",
        "CHANGELOG.md": "changes\n",
        "examples/demo.py": "print('demo')\n",
        "requirements.txt": "pathspec==1.1.1\n",
        "pyproject.toml": "[project]\nname='x'\n",
        ".github/workflows/ci.yml": "name: ci\n",
        "Dockerfile": "FROM scratch\n",
        ".dockerignore": "build\n",
        "LICENSE": "MIT\n",
        ".gitignore": "*.pyc\n",
        ".github/ISSUE_TEMPLATE/bug.md": "bug\n",
        ".github/pull_request_template.md": "pr\n",
        "CODE_OF_CONDUCT.md": "conduct\n",
        "SECURITY.md": "security\n",
        "notes.txt": "notes\n",
    }
    for name, text in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text.encode("utf-8"))

    result = build_inventory(tmp_path, _config())
    by_path = {file.path: file for file in result.files}
    observed = frozenset(role for file in result.files for role in file.roles)
    assert observed == frozenset(FileRole)
    assert {FileRole.PYTHON_SOURCE, FileRole.EXAMPLE} <= by_path["examples/demo.py"].roles
    assert result.summary.total_files == len(files)
    assert result.summary.python_files == 3
    assert result.summary.test_files == 1
    assert result.summary.python_lines == 4
    assert result.summary.source_bytes == sum(len(text.encode("utf-8")) for text in files.values())
    assert result.completeness is Completeness.AVAILABLE


def test_inventory_is_deterministic_and_applies_nested_ignores_and_config_excludes(
    tmp_path: Path,
) -> None:
    for name in ("z.py", "a.py", "ignored.py", "nested/drop.py", "nested/keep.py", "config.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.py\nnested/*.py\n", encoding="utf-8")
    (tmp_path / "nested/.gitignore").write_text("!keep.py\n", encoding="utf-8")

    result = build_inventory(tmp_path, _config(exclude=["config.py"]))
    paths = tuple(file.path for file in result.files)
    assert paths == tuple(sorted(paths))
    assert "ignored.py" not in paths
    assert "nested/drop.py" not in paths
    assert "nested/keep.py" in paths
    assert "config.py" not in paths


def test_nested_negation_cannot_reinclude_file_beneath_excluded_parent(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    (tmp_path / ".gitignore").write_text("nested/\n", encoding="utf-8")
    (nested / ".gitignore").write_text("!keep.py\n", encoding="utf-8")
    (nested / "keep.py").write_text("x = 1\n", encoding="utf-8")

    result = build_inventory(tmp_path, _config())
    assert {file.path for file in result.files} == {".gitignore"}
    assert {item.path for item in result.skipped_inputs} == {"nested"}


def test_safety_exclusions_cannot_be_reincluded_and_are_disclosed(tmp_path: Path) -> None:
    for name in (".git/config", ".venv/lib.py", "node_modules/x.js", "vendor/pkg.py", "src/ok.py"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "never-read-secret\n" if name != "src/ok.py" else "ok = 1\n", encoding="utf-8"
        )
    (tmp_path / ".gitignore").write_text(
        "!.git/config\n!.venv/lib.py\n!vendor/pkg.py\n", encoding="utf-8"
    )
    result = build_inventory(tmp_path, _config())
    assert {file.path for file in result.files} == {".gitignore", "src/ok.py"}
    assert any(item.code == "safety-excluded" for item in result.limitations)
    assert result.completeness is Completeness.PARTIAL


def test_inventory_enforces_exact_size_file_total_and_timeout_limits(tmp_path: Path) -> None:
    (tmp_path / "a.txt").write_bytes(b"1234")
    (tmp_path / "b.txt").write_bytes(b"12345")
    exact = build_inventory(tmp_path, _config(max_file_bytes=4))
    assert [file.path for file in exact.files] == ["a.txt"]
    assert any(
        item.path == "b.txt" and item.reason == "file exceeds 4-byte limit"
        for item in exact.skipped_inputs
    )

    file_limited = build_inventory(tmp_path, _config(max_file_bytes=9, max_files=1))
    assert [file.path for file in file_limited.files] == ["a.txt"]
    assert any(item.reason == "file-count limit reached" for item in file_limited.skipped_inputs)

    byte_limited = build_inventory(tmp_path, _config(max_file_bytes=9, max_source_bytes=4))
    assert [file.path for file in byte_limited.files] == ["a.txt"]
    assert any(item.reason == "source-byte limit reached" for item in byte_limited.skipped_inputs)

    ticks = iter([0.0, 0.0, 2.0, 2.0, 2.0])
    timed = build_inventory(tmp_path, _config(timeout_seconds=1), monotonic=lambda: next(ticks))
    assert timed.completeness is Completeness.PARTIAL
    assert any(item.code == "inventory-timeout" for item in timed.limitations)


def test_traversal_timeout_discloses_already_discovered_pending_directories(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ticks = iter([0.0, 0.0, 2.0])

    result = build_inventory(
        tmp_path,
        _config(timeout_seconds=1),
        monotonic=lambda: next(ticks),
    )

    assert {(item.path, item.reason) for item in result.skipped_inputs} == {
        ("a", "inventory time limit reached"),
        ("b", "inventory time limit reached"),
    }


def test_inventory_timeout_at_exact_deadline_while_root_is_pending(tmp_path: Path) -> None:
    ticks = iter([0.0, 1.0])

    result = build_inventory(
        tmp_path,
        _config(timeout_seconds=1),
        monotonic=lambda: next(ticks),
    )

    assert result.files == ()
    assert result.skipped_inputs == ()
    assert result.completeness is Completeness.PARTIAL
    assert [(item.code, item.message) for item in result.limitations] == [
        ("inventory-timeout", "Repository inventory time limit reached")
    ]


def test_max_files_bounds_retained_files(tmp_path: Path) -> None:
    for index in range(50):
        (tmp_path / f"file-{index:02}.txt").write_text("x", encoding="utf-8")
    result = build_inventory(tmp_path, _config(max_files=2))
    assert [file.path for file in result.files] == ["file-00.txt", "file-01.txt"]
    assert any(item.code == "file-discovery-limit" for item in result.limitations)


def test_ignored_directory_is_pruned_before_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    ignored = tmp_path / "ignored"
    ignored.mkdir()
    for index in range(10):
        (ignored / f"file-{index}.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored/\n", encoding="utf-8")
    real_scandir = os.scandir

    def guarded_scandir(path: os.PathLike[str] | str) -> Any:
        if Path(path) == ignored:
            raise AssertionError("ignored directory was enumerated")
        return real_scandir(path)

    monkeypatch.setattr(os, "scandir", guarded_scandir)
    result = build_inventory(tmp_path, _config())
    assert {file.path for file in result.files} == {".gitignore"}
    assert any(item.path == "ignored" for item in result.skipped_inputs)


def test_malformed_repository_ignore_is_disclosed_without_aborting(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("!\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("x = 1\n", encoding="utf-8")
    result = build_inventory(tmp_path, _config())
    assert {file.path for file in result.files} == {".gitignore", "ok.py"}
    assert any(item.code == "invalid-ignore-pattern" for item in result.limitations)


def test_max_files_uses_global_lexicographic_file_order_without_counting_directories(
    tmp_path: Path,
) -> None:
    nested = tmp_path / "a"
    nested.mkdir()
    (nested / "first.py").write_text("first = 1\n", encoding="utf-8")
    (tmp_path / "z.py").write_text("last = 1\n", encoding="utf-8")

    one = build_inventory(tmp_path, _config(max_files=1))
    exact = build_inventory(tmp_path, _config(max_files=2))

    assert [file.path for file in one.files] == ["a/first.py"]
    assert [file.path for file in exact.files] == ["a/first.py", "z.py"]
    assert not any(item.code == "file-discovery-limit" for item in exact.limitations)


def test_directory_entry_overflow_skips_whole_directory_with_bounded_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import repoinsight.inventory as inventory_module

    overflow = tmp_path / "overflow"
    overflow.mkdir()
    for index in range(10):
        (overflow / f"file-{index}.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "z.py").write_text("z = 1\n", encoding="utf-8")
    monkeypatch.setattr(inventory_module, "_MAX_DIRECTORY_ENTRIES", 3)
    real_scandir = os.scandir
    yielded = 0

    class CountingScandir:
        def __enter__(self) -> CountingScandir:
            self._stream = real_scandir(overflow)
            return self

        def __exit__(self, *_: object) -> None:
            self._stream.close()

        def __iter__(self) -> CountingScandir:
            return self

        def __next__(self) -> os.DirEntry[str]:
            nonlocal yielded
            yielded += 1
            return next(self._stream)

    def bounded_scandir(path: os.PathLike[str] | str) -> Any:
        return CountingScandir() if Path(path) == overflow else real_scandir(path)

    monkeypatch.setattr(os, "scandir", bounded_scandir)
    result = build_inventory(tmp_path, _config(max_files=5))
    assert [file.path for file in result.files] == ["z.py"]
    assert any(
        item.path == "overflow" and item.reason == "directory-entry limit reached"
        for item in result.skipped_inputs
    )
    assert any(item.code == "directory-entry-limit" for item in result.limitations)
    assert yielded <= 4


def test_inventory_decodes_utf8_bom_latin1_and_discloses_invalid_inputs(tmp_path: Path) -> None:
    (tmp_path / "utf8.py").write_text("name = 'ok'\n", encoding="utf-8")
    (tmp_path / "bom.py").write_bytes(b"\xef\xbb\xbfvalue = 1\n")
    (tmp_path / "latin.py").write_bytes("# coding: latin-1\nname = 'caf\xe9'\n".encode("latin-1"))
    (tmp_path / "unknown.py").write_bytes(b"# coding: unknown-xyz\nx = 1\n")
    (tmp_path / "invalid.txt").write_bytes(b"\xff")
    (tmp_path / "binary.txt").write_bytes(b"a\x00b")

    result = build_inventory(tmp_path, _config())
    by_path = {file.path: file for file in result.files}
    assert by_path["bom.py"].encoding == "utf-8-sig"
    assert by_path["latin.py"].encoding == "iso-8859-1"
    assert by_path["latin.py"].text.endswith("'café'\n")
    skipped = {item.path: item.reason for item in result.skipped_inputs}
    assert skipped["unknown.py"] == "unsupported or invalid text encoding"
    assert skipped["invalid.txt"] == "unsupported or invalid text encoding"
    assert skipped["binary.txt"] == "binary content is not analyzed"
    assert all("café" not in warning.message for warning in result.warnings)


def test_empty_and_python_free_repositories_are_available(tmp_path: Path) -> None:
    empty = build_inventory(tmp_path, _config())
    assert empty.summary.total_files == 0
    assert empty.completeness is Completeness.AVAILABLE
    (tmp_path / "README.md").write_text("hello\n", encoding="utf-8")
    text_only = build_inventory(tmp_path, _config())
    assert text_only.summary.python_files == 0
    assert text_only.completeness is Completeness.AVAILABLE
