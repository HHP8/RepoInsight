from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import cast

import pytest

from repoinsight.acquisition import acquire_source, parse_source
from repoinsight.config import load_config
from repoinsight.errors import AcquisitionError, InvalidUsageError
from repoinsight.models import SourceKind


def _external_executable() -> str:
    name = "python.exe" if os.name == "nt" else "bin/python"
    return str((Path(sys.base_prefix) / name).resolve())


@pytest.mark.parametrize(
    ("raw", "canonical"),
    [
        ("https://github.com/owner/repo", "https://github.com/owner/repo"),
        ("https://github.com/owner/repo.git", "https://github.com/owner/repo"),
        ("https://github.com/owner/repo/", "https://github.com/owner/repo"),
    ],
)
def test_parse_source_accepts_only_canonical_public_github_urls(raw: str, canonical: str) -> None:
    source = parse_source(raw)
    assert source.kind is SourceKind.GITHUB
    assert source.canonical_identity == canonical
    assert source.local_path is None


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "http://github.com/o/r",
        "git@github.com:o/r.git",
        "ssh://git@github.com/o/r",
        "https://user:pass@github.com/o/r",
        "https://github.com:443/o/r",
        "https://github.com:not-a-port/o/r",
        "https://github.com/o/r?q=1",
        "https://github.com/o/r#frag",
        "https://github.com/o/r/extra",
        "https://github.com/o/%72",
        "https://github.com/o/../r",
        "https://github.com/o/.git",
        "https://github.com/o bad/r",
        "https://github.com/owner_name/repo",
        "https://gitlab.com/o/r",
        "github.com/o/r",
        "//github.com/o/r",
        "\\\\github.com\\o\\r",
    ],
)
def test_parse_source_rejects_malformed_or_non_allowlisted_sources(raw: str) -> None:
    with pytest.raises(InvalidUsageError):
        parse_source(raw)


def test_parse_source_resolves_relative_local_directory(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    repo.mkdir()
    source = parse_source("repo", cwd=tmp_path)
    assert source.kind is SourceKind.LOCAL
    assert source.local_path == repo.resolve()
    assert source.canonical_identity == str(repo.resolve())


def test_parse_source_rejects_missing_and_non_directory_local_paths(tmp_path: Path) -> None:
    file = tmp_path / "file.txt"
    file.write_text("x", encoding="utf-8")
    for raw in ("missing", "file.txt"):
        with pytest.raises(InvalidUsageError):
            parse_source(raw, cwd=tmp_path)


def test_remote_acquisition_uses_exact_hardened_boundary_and_cleans_up() -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        calls.append((argv, kwargs))
        Path(argv[-1]).mkdir()
        return subprocess.CompletedProcess(argv, 0, "", "")

    config = load_config(
        None, None, {"git.remote_history_depth": 7, "git.clone_timeout_seconds": 9}
    )
    source = parse_source("https://github.com/owner/repo.git")
    executable = _external_executable()
    with acquire_source(source, config, git_executable=executable, runner=runner) as acquired:
        clone_root = acquired.root
        assert clone_root.exists()
        assert acquired.temporary is True
        assert acquired.source.canonical_identity == "https://github.com/owner/repo"

    assert not clone_root.exists()
    argv, kwargs = calls[0]
    assert argv == [
        executable,
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "credential.helper=",
        "-c",
        "core.pager=cat",
        "-c",
        "diff.external=",
        "-c",
        "core.autocrlf=false",
        "clone",
        "--depth",
        "7",
        "--no-tags",
        "--single-branch",
        "--no-recurse-submodules",
        "https://github.com/owner/repo",
        argv[-1],
    ]
    assert Path(argv[-1]).parent != Path.cwd()
    assert kwargs["shell"] is False
    assert kwargs["timeout"] == 9
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["encoding"] == "utf-8"
    assert kwargs["errors"] == "replace"
    env = kwargs["env"]
    assert isinstance(env, dict)
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"
    assert env["GIT_CONFIG_GLOBAL"] == os.devnull
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GCM_INTERACTIVE"] == "Never"
    assert env["PATH"] == str(Path(executable).parent)


@pytest.mark.parametrize(
    "failure", [subprocess.TimeoutExpired(["git"], 1), OSError("token=secret")]
)
def test_remote_acquisition_redacts_failures_and_cleans_up(failure: BaseException) -> None:
    destinations: list[Path] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        destination = Path(argv[-1])
        destination.mkdir()
        destinations.append(destination)
        raise failure

    source = parse_source("https://github.com/owner/repo")
    with (
        pytest.raises(AcquisitionError) as captured,
        acquire_source(source, load_config(None, None, {}), runner=runner),
    ):
        pass
    assert "secret" not in str(captured.value)
    assert all(not path.exists() for path in destinations)


def test_acquisition_cleans_remote_clone_after_base_exception() -> None:
    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        Path(argv[-1]).mkdir()
        return subprocess.CompletedProcess(argv, 0, "", "")

    source = parse_source("https://github.com/owner/repo")
    with (
        pytest.raises(KeyboardInterrupt),
        acquire_source(source, load_config(None, None, {}), runner=runner) as acquired,
    ):
        clone_root = acquired.root
        raise KeyboardInterrupt
    assert not clone_root.exists()


def test_local_acquisition_uses_original_directory_without_cleanup(tmp_path: Path) -> None:
    source = parse_source(str(tmp_path))
    with acquire_source(source, load_config(None, None, {})) as acquired:
        assert acquired.root == tmp_path.resolve()
        assert acquired.temporary is False
    assert tmp_path.exists()


def test_acquisition_rejects_relative_or_current_repository_git(tmp_path: Path) -> None:
    source = parse_source("https://github.com/owner/repo")
    executable = tmp_path / "git.exe"
    executable.write_bytes(b"not executable repository content")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "", "")

    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        for candidate in ("git.exe", str(executable.resolve())):
            with (
                pytest.raises(AcquisitionError),
                acquire_source(
                    source,
                    load_config(None, None, {}),
                    git_executable=candidate,
                    runner=runner,
                ),
            ):
                pass
    finally:
        os.chdir(previous)
    assert calls == 0


def test_existing_github_backslash_path_is_not_accepted_as_local(tmp_path: Path) -> None:
    malformed = "github.com\\owner\\repo"
    path = tmp_path / malformed
    path.mkdir(parents=True)

    with pytest.raises(InvalidUsageError):
        parse_source(malformed, cwd=tmp_path)


def test_default_git_discovery_rejects_reparse_parent_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    binary_directory = tmp_path / "trusted-looking-bin"
    binary_directory.mkdir()
    executable = binary_directory / "git.exe"
    executable.write_bytes(b"repository-controlled executable")
    real_lstat = os.lstat

    def reparse_parent(path: os.PathLike[str] | str) -> os.stat_result:
        result = real_lstat(path)
        if Path(path) != binary_directory:
            return result
        return cast(
            os.stat_result,
            SimpleNamespace(
                st_mode=result.st_mode,
                st_file_attributes=0x400,
                st_nlink=result.st_nlink,
                st_dev=result.st_dev,
                st_ino=result.st_ino,
                st_size=result.st_size,
            ),
        )

    monkeypatch.setattr(os, "lstat", reparse_parent)
    monkeypatch.setenv("PATH", str(binary_directory))
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "", "")

    with (
        pytest.raises(AcquisitionError),
        acquire_source(
            parse_source("https://github.com/owner/repo"),
            load_config(None, None, {}),
            runner=runner,
        ),
    ):
        pass
    assert calls == 0


def test_git_environment_does_not_forward_repository_helper_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_helpers = tmp_path / "repository-helpers"
    repository_helpers.mkdir()
    (repository_helpers / "git-remote-https.exe").write_bytes(b"untrusted helper")
    monkeypatch.setenv("PATH", str(repository_helpers))
    captured_environment: dict[str, str] = {}

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        environment = kwargs["env"]
        assert isinstance(environment, dict)
        captured_environment.update(environment)
        Path(argv[-1]).mkdir()
        return subprocess.CompletedProcess(argv, 0, "", "")

    executable = _external_executable()
    with acquire_source(
        parse_source("https://github.com/owner/repo"),
        load_config(None, None, {}),
        git_executable=executable,
        runner=runner,
    ):
        pass
    assert captured_environment["PATH"] == str(Path(executable).parent)
    assert str(repository_helpers) not in captured_environment["PATH"]
