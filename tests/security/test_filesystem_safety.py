from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, NoReturn, cast

import pytest
from pathspec import GitIgnoreSpec

from repoinsight.config import load_config
from repoinsight.inventory import build_inventory
from repoinsight.models import Completeness, Limitation, WarningRecord


def test_inventory_never_follows_external_or_internal_symlinks(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside.txt"
    outside.write_text("external-secret", encoding="utf-8")
    target = tmp_path / "target.txt"
    target.write_text("internal-secret", encoding="utf-8")
    external = tmp_path / "external-link.txt"
    internal = tmp_path / "internal-link.txt"
    outside_directory = tmp_path.parent / f"{tmp_path.name}-outside-directory"
    outside_directory.mkdir()
    (outside_directory / "secret.txt").write_text("external-directory-secret", encoding="utf-8")
    internal_directory = tmp_path / "target-directory"
    internal_directory.mkdir()
    (internal_directory / "inside.txt").write_text("inside", encoding="utf-8")
    external_directory_link = tmp_path / "external-directory-link"
    internal_directory_link = tmp_path / "internal-directory-link"
    try:
        external.symlink_to(outside)
        internal.symlink_to(target)
        external_directory_link.symlink_to(outside_directory, target_is_directory=True)
        internal_directory_link.symlink_to(internal_directory, target_is_directory=True)
    except OSError:
        pytest.skip("OS privilege genuinely forbids symlink creation")

    result = build_inventory(tmp_path, load_config(None, None, {}))
    assert {file.path for file in result.files} == {"target.txt", "target-directory/inside.txt"}
    assert {item.path for item in result.skipped_inputs} == {
        "external-directory-link",
        "external-link.txt",
        "internal-directory-link",
        "internal-link.txt",
    }
    assert all("secret" not in warning.message for warning in result.warnings)


def test_inventory_rejects_external_hard_link(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-outside-hardlink.txt"
    outside.write_text("external-hardlink-secret", encoding="utf-8")
    link = tmp_path / "hardlink.txt"
    try:
        link.hardlink_to(outside)
    except OSError:
        pytest.skip("Filesystem does not permit hard-link creation")

    result = build_inventory(tmp_path, load_config(None, None, {}))
    assert result.files == ()
    assert result.skipped_inputs[0].reason == "link-like entry is not followed"


def test_mocked_reparse_entry_is_rejected_without_opening(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "junction"
    candidate.mkdir()
    real_lstat = os.lstat

    def reparse_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        result = real_lstat(path)
        if Path(path).name != "junction":
            return result
        fake = SimpleNamespace(
            st_mode=result.st_mode,
            st_file_attributes=0x400,
            st_nlink=1,
            st_dev=result.st_dev,
            st_ino=result.st_ino,
            st_size=result.st_size,
        )
        return cast(os.stat_result, fake)

    monkeypatch.setattr(os, "lstat", reparse_lstat)
    result = build_inventory(tmp_path, load_config(None, None, {}))
    assert result.files == ()
    assert result.skipped_inputs[0].path == "junction"


def test_directory_identity_change_is_rejected_before_child_enumeration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    directory = tmp_path / "changing"
    directory.mkdir()
    (directory / "outside.py").write_text("x = 1\n", encoding="utf-8")
    real_lstat = os.lstat
    directory_calls = 0

    def changing_lstat(path: os.PathLike[str] | str) -> os.stat_result:
        nonlocal directory_calls
        result = real_lstat(path)
        if Path(path) == directory:
            directory_calls += 1
            if directory_calls > 1:
                values = list(result)
                values[1] = result.st_ino + 1
                return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "lstat", changing_lstat)
    result = build_inventory(tmp_path, load_config(None, None, {}))
    assert result.files == ()
    assert result.skipped_inputs[0].reason == "directory changed before enumeration"


def test_descriptor_reader_rejects_identity_change_race(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "race.txt"
    path.write_text("safe", encoding="utf-8")
    real_fstat = os.fstat
    calls = 0

    def changing_fstat(fd: int) -> os.stat_result:
        nonlocal calls
        calls += 1
        result = real_fstat(fd)
        if calls > 1:
            values = list(result)
            values[1] = result.st_ino + 1
            return os.stat_result(values)
        return result

    monkeypatch.setattr(os, "fstat", changing_fstat)
    result = build_inventory(tmp_path, load_config(None, None, {}))
    assert result.files == ()
    assert result.skipped_inputs[0].reason == "file changed during bounded read"


def test_inventory_normalizes_all_disclosed_paths(tmp_path: Path) -> None:
    nested = tmp_path / "folder" / "bad.txt"
    nested.parent.mkdir()
    nested.write_bytes(b"a\x00b")
    result = build_inventory(tmp_path, load_config(None, None, {}))
    returned = [file.path for file in result.files] + [item.path for item in result.skipped_inputs]
    assert returned == ["folder/bad.txt"]
    assert all(
        "\\" not in path and not path.startswith("/") and ".." not in path.split("/")
        for path in returned
    )


def test_root_becoming_unreadable_is_unavailable_without_raw_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def denied(_: os.PathLike[str] | str) -> NoReturn:
        raise PermissionError("repository-source-secret")

    monkeypatch.setattr(os, "scandir", denied)
    result = build_inventory(tmp_path, load_config(None, None, {}))
    assert result.completeness is Completeness.UNAVAILABLE
    assert result.limitations[0].code == "root-unreadable"
    assert "secret" not in result.limitations[0].message


def test_opened_handle_outside_root_is_rejected_before_content_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import repoinsight.inventory as inventory_module

    safe = tmp_path / "safe.txt"
    safe.write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-swap-back.txt"
    outside.write_text("external-content-must-not-be-read", encoding="utf-8")
    outside_metadata = os.lstat(outside)
    read_calls = 0
    real_open = os.open
    real_read = os.read

    def swapped_open(path: Path, flags: int, *, root: Path | None) -> Any:
        assert path == safe
        assert root == tmp_path
        return inventory_module._OpenedDescriptor(real_open(outside, flags), False)

    def counted_read(descriptor: int, amount: int) -> bytes:
        nonlocal read_calls
        read_calls += 1
        return real_read(descriptor, amount)

    monkeypatch.setattr(inventory_module, "_open_descriptor", swapped_open)
    monkeypatch.setattr(os, "read", counted_read)
    with pytest.raises(inventory_module._UnsafeRead) as captured:
        inventory_module._bounded_descriptor_read(
            safe,
            outside_metadata,
            1024,
            root=tmp_path,
        )
    assert captured.value.reason == "opened file is outside repository"
    assert read_calls == 0


def test_handle_check_uses_captured_root_without_reresolving_mutable_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import repoinsight.inventory as inventory_module

    safe = tmp_path / "safe.txt"
    safe.write_text("safe", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-root-swap.txt"
    outside.write_text("external", encoding="utf-8")
    outside_metadata = os.lstat(outside)
    real_open = os.open
    real_read = os.read
    real_resolve = Path.resolve
    reads = 0

    def swapped_open(path: Path, flags: int, *, root: Path | None) -> Any:
        return inventory_module._OpenedDescriptor(real_open(outside, flags), False)

    def mutable_resolve(path: Path, strict: bool = False) -> Path:
        if path == tmp_path:
            return outside.parent
        return real_resolve(path, strict=strict)

    def counted_read(descriptor: int, amount: int) -> bytes:
        nonlocal reads
        reads += 1
        return real_read(descriptor, amount)

    monkeypatch.setattr(inventory_module, "_open_descriptor", swapped_open)
    monkeypatch.setattr(inventory_module, "_final_handle_path", lambda _: outside)
    monkeypatch.setattr(Path, "resolve", mutable_resolve)
    monkeypatch.setattr(os, "read", counted_read)
    with pytest.raises(inventory_module._UnsafeRead):
        inventory_module._bounded_descriptor_read(safe, outside_metadata, 1024, root=tmp_path)
    assert reads == 0


def test_gitignore_external_descriptor_is_rejected_before_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import repoinsight.inventory as inventory_module

    ignore = tmp_path / ".gitignore"
    ignore.write_text("safe-pattern\n", encoding="utf-8")
    outside = tmp_path.parent / f"{tmp_path.name}-outside-ignore"
    outside.write_text("*.py\n", encoding="utf-8")
    outside_metadata = os.lstat(outside)
    real_open = os.open
    real_read = os.read
    reads = 0

    def swapped_open(path: Path, flags: int, *, root: Path | None) -> Any:
        assert path == ignore
        return inventory_module._OpenedDescriptor(real_open(outside, flags), False)

    def counted_read(descriptor: int, amount: int) -> bytes:
        nonlocal reads
        reads += 1
        return real_read(descriptor, amount)

    monkeypatch.setattr(inventory_module, "_open_descriptor", swapped_open)
    monkeypatch.setattr(inventory_module, "_final_handle_path", lambda _: outside)
    monkeypatch.setattr(os, "read", counted_read)
    specs: dict[str, GitIgnoreSpec] = {}
    warnings: list[WarningRecord] = []
    limitations: list[Limitation] = []
    inventory_module._load_directory_ignore(
        tmp_path,
        "",
        ignore,
        outside_metadata,
        1024,
        specs,
        warnings,
        limitations,
    )
    assert specs == {}
    assert reads == 0


def test_posix_atomic_open_does_not_require_procfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import repoinsight.inventory as inventory_module

    path = tmp_path / "safe.txt"
    path.write_bytes(b"safe")
    metadata = os.lstat(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    monkeypatch.setattr(
        inventory_module,
        "_open_descriptor",
        lambda *_args, **_kwargs: inventory_module._OpenedDescriptor(descriptor, True),
    )
    monkeypatch.setattr(inventory_module, "_WINDOWS_PLATFORM", False)
    monkeypatch.setattr(inventory_module, "_final_handle_path", lambda _: None)
    assert inventory_module._bounded_descriptor_read(path, metadata, 10, root=tmp_path) == b"safe"


def test_read_fails_closed_without_atomic_or_final_handle_proof(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import repoinsight.inventory as inventory_module

    path = tmp_path / "safe.txt"
    path.write_bytes(b"safe")
    metadata = os.lstat(path)
    descriptor = os.open(path, os.O_RDONLY | getattr(os, "O_BINARY", 0))
    monkeypatch.setattr(
        inventory_module,
        "_open_descriptor",
        lambda *_args, **_kwargs: inventory_module._OpenedDescriptor(descriptor, False),
    )
    monkeypatch.setattr(inventory_module, "_final_handle_path", lambda _: None)
    with pytest.raises(inventory_module._UnsafeRead):
        inventory_module._bounded_descriptor_read(path, metadata, 10, root=tmp_path)
