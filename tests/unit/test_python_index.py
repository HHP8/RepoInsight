from __future__ import annotations

import ast
from dataclasses import replace
from pathlib import Path

import pytest

from repoinsight.config import load_config
from repoinsight.inventory import build_inventory
from repoinsight.models import Completeness
from repoinsight.python_index import build_python_index


def test_python_index_builds_stable_ast_without_importing_code(tmp_path: Path) -> None:
    marker = tmp_path / "executed"
    (tmp_path / "b.py").write_bytes(f"open({str(marker)!r}, 'w').write('bad')\n".encode())
    (tmp_path / "a.py").write_bytes(b"x: int = 1  # type: ignore\n")
    inventory = build_inventory(tmp_path, load_config(None, None, {}))
    index = build_python_index(inventory)
    assert [parsed.file.path for parsed in index.files] == ["a.py", "b.py"]
    assert all(isinstance(parsed.tree, ast.Module) for parsed in index.files)
    assert index.files[0].source_lines == ("x: int = 1  # type: ignore\n",)
    assert not marker.exists()
    assert index.completeness is Completeness.AVAILABLE


def test_python_index_discloses_malformed_python_without_source_text(tmp_path: Path) -> None:
    secret = "do-not-leak-this-token"
    (tmp_path / "bad.py").write_text(f"def broken(\n    {secret}\n", encoding="utf-8")
    inventory = build_inventory(tmp_path, load_config(None, None, {}))
    index = build_python_index(inventory)
    assert index.files == ()
    assert index.completeness is Completeness.UNAVAILABLE
    assert index.skipped_inputs[0].reason == "Python syntax error"
    warning = index.warnings[0]
    assert warning.code == "python-syntax-error"
    assert warning.location is not None
    assert secret not in warning.message


def test_python_index_is_partial_when_some_python_files_are_valid(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "bad.py").write_text("if:\n", encoding="utf-8")
    index = build_python_index(build_inventory(tmp_path, load_config(None, None, {})))
    assert [parsed.file.path for parsed in index.files] == ["good.py"]
    assert index.completeness is Completeness.PARTIAL


@pytest.mark.parametrize("completeness", [Completeness.UNAVAILABLE, Completeness.SKIPPED])
def test_python_index_preserves_unavailable_inventory_state_with_retained_records(
    tmp_path: Path,
    completeness: Completeness,
) -> None:
    (tmp_path / "retained.py").write_text("value = 1\n", encoding="utf-8")
    inventory = build_inventory(tmp_path, load_config(None, None, {}))

    index = build_python_index(replace(inventory, completeness=completeness))

    assert [parsed.file.path for parsed in index.files] == ["retained.py"]
    assert index.completeness is completeness
