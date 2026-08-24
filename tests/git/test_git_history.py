from __future__ import annotations

import subprocess
import sys
from itertools import pairwise
from pathlib import Path

import pytest

from repoinsight.git import collect_git_history
from repoinsight.models import Completeness


def _external_executable() -> str:
    name = "python.exe" if __import__("os").name == "nt" else "bin/python"
    return str((Path(sys.base_prefix) / name).resolve())


def _make_git_metadata(root: Path) -> None:
    (root / ".git" / "objects").mkdir(parents=True)


def _make_linked_worktree_metadata(root: Path) -> tuple[Path, Path]:
    common_directory = root / "admin"
    git_directory = common_directory / "worktrees" / "linked"
    git_directory.mkdir(parents=True)
    (common_directory / "objects").mkdir()
    (git_directory / "commondir").write_text("../..\n", encoding="utf-8")
    (root / ".git").write_text(
        "gitdir: admin/worktrees/linked\n",
        encoding="utf-8",
    )
    return git_directory, common_directory


def _successful_history_result(argv: list[str]) -> subprocess.CompletedProcess[str]:
    if "--is-shallow-repository" in argv:
        return subprocess.CompletedProcess(argv, 0, "false\n", "")
    if "symbolic-ref" in argv:
        return subprocess.CompletedProcess(argv, 0, "main\n", "")
    return subprocess.CompletedProcess(
        argv,
        0,
        "a" * 40 + "\x1f2020-01-01T00:00:00+00:00\x1fAlice\x1fa@example.test\x1e",
        "",
    )


def _run_git(root: Path, *args: str) -> None:
    result = _git_result(root, *args)
    result.check_returncode()


def _git_result(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "safe.directory=*", *args],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={
            "PATH": __import__("os").environ.get("PATH", ""),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": __import__("os").devnull,
        },
    )


def _make_installed_git_linked_worktrees(tmp_path: Path) -> tuple[Path, Path, Path]:
    main = tmp_path / "main"
    linked = tmp_path / "linked"
    other = tmp_path / "other"
    main.mkdir()
    _run_git(main, "init", "-b", "main")
    _run_git(
        main,
        "-c",
        "user.name=RepoInsight Test",
        "-c",
        "user.email=repoinsight@example.test",
        "commit",
        "--allow-empty",
        "-m",
        "base",
    )
    _run_git(main, "worktree", "add", "--detach", str(linked))
    _run_git(main, "worktree", "add", "--detach", str(other))
    return main, linked, other


def test_collect_git_history_reads_reachable_head_without_disclosing_identity(
    tmp_path: Path,
) -> None:
    _run_git(tmp_path, "init", "-b", "main")
    (tmp_path / "a.txt").write_text("one", encoding="utf-8")
    _run_git(tmp_path, "add", "a.txt")
    env = __import__("os").environ.copy()
    env.update(
        {
            "GIT_AUTHOR_NAME": "Alice",
            "GIT_AUTHOR_EMAIL": "alice@example.test",
            "GIT_COMMITTER_NAME": "Alice",
            "GIT_COMMITTER_EMAIL": "alice@example.test",
            "GIT_AUTHOR_DATE": "2020-01-01T00:00:00+00:00",
            "GIT_COMMITTER_DATE": "2020-01-01T00:00:00+00:00",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": __import__("os").devnull,
        }
    )
    subprocess.run(
        ["git", "-c", "safe.directory=*", "commit", "-m", "first"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        env=env,
    )
    history = collect_git_history(tmp_path, remote=False)
    assert history.summary.available is True
    assert history.summary.completeness is Completeness.AVAILABLE
    assert history.summary.branch == "main"
    assert history.summary.commits_considered == 1
    assert history.summary.contributor_count == 1
    assert history.summary.first_commit_at is not None
    assert history.summary.first_commit_at.isoformat() == "2020-01-01T00:00:00+00:00"
    assert history.commits[0].author_identity == "alice <alice@example.test>"
    assert "alice" not in history.summary.model_dump_json().lower()


def test_git_history_unavailable_for_missing_executable_metadata_and_no_commits(
    tmp_path: Path,
) -> None:
    missing = collect_git_history(
        tmp_path, remote=False, git_executable="definitely-not-a-git-executable"
    )
    assert missing.summary.completeness is Completeness.UNAVAILABLE
    assert missing.commits == ()

    _run_git(tmp_path, "init")
    empty = collect_git_history(tmp_path, remote=False)
    assert empty.summary.completeness is Completeness.UNAVAILABLE
    assert empty.commits == ()


def test_git_history_parses_detached_branch_and_stable_machine_output(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)
    log_command = (
        "log --no-show-signature --no-mailmap --no-textconv "
        "--format=%H%x1f%aI%x1f%an%x1f%ae%x1e HEAD"
    )
    outputs = {
        "rev-parse --is-shallow-repository": "false\n",
        "symbolic-ref --quiet --short HEAD": "",
        log_command: (
            "b" * 40
            + "\x1f2021-01-02T00:00:00+00:00\x1fBob\x1fb@example.test\x1e"
            + "a" * 40
            + "\x1f2020-01-01T00:00:00+00:00\x1fAlice\x1fa@example.test\x1e"
        ),
    }

    def runner(argv: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        expected_prefix = [
            _external_executable(),
            "--no-replace-objects",
            "-c",
            f"safe.directory={tmp_path.resolve()}",
            "-c",
            f"core.hooksPath={__import__('os').devnull}",
            "-c",
            "credential.helper=",
            "-c",
            "core.pager=cat",
            "-c",
            "diff.external=",
            "-c",
            "core.fsmonitor=false",
        ]
        assert argv[: len(expected_prefix)] == expected_prefix
        assert kwargs["shell"] is False
        assert kwargs["timeout"] == 30
        assert kwargs["encoding"] == "utf-8"
        assert kwargs["errors"] == "strict"
        assert kwargs["cwd"] == tmp_path
        env = kwargs["env"]
        assert isinstance(env, dict)
        assert env["GIT_CONFIG_NOSYSTEM"] == "1"
        assert env["GIT_CONFIG_GLOBAL"] == __import__("os").devnull
        assert env["GIT_TERMINAL_PROMPT"] == "0"
        assert env["GCM_INTERACTIVE"] == "Never"
        assert env["GIT_PAGER"] == "cat"
        assert env["GIT_EXTERNAL_DIFF"] == ""
        assert env["PATH"] == str(Path(_external_executable()).parent)
        tail = " ".join(
            argv[argv.index("rev-parse") :]
            if "rev-parse" in argv
            else argv[argv.index("symbolic-ref") :]
            if "symbolic-ref" in argv
            else argv[argv.index("log") :]
        )
        return subprocess.CompletedProcess(
            argv, 0 if "symbolic-ref" not in argv else 1, outputs[tail], ""
        )

    history = collect_git_history(
        tmp_path,
        remote=False,
        git_executable=_external_executable(),
        runner=runner,
    )
    assert history.summary.branch is None
    assert [commit.revision for commit in history.commits] == ["b" * 40, "a" * 40]
    assert history.summary.latest_commit_at == history.commits[0].authored_at
    assert history.summary.first_commit_at == history.commits[1].authored_at


def test_shallow_remote_history_is_partial_and_malformed_output_is_safe(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)

    def shallow_runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if "--is-shallow-repository" in argv:
            return subprocess.CompletedProcess(argv, 0, "true\n", "")
        if "symbolic-ref" in argv:
            return subprocess.CompletedProcess(argv, 0, "main\n", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            "a" * 40 + "\x1f2020-01-01T00:00:00+00:00\x1fAlice\x1fa@example.test\x1e",
            "",
        )

    partial = collect_git_history(tmp_path, remote=True, runner=shallow_runner)
    assert partial.summary.completeness is Completeness.PARTIAL
    assert partial.summary.limitations

    def malformed_runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        if "log" in argv:
            return subprocess.CompletedProcess(argv, 0, "raw-secret-malformed", "")
        return subprocess.CompletedProcess(argv, 0, "false\n", "")

    malformed = collect_git_history(tmp_path, remote=False, runner=malformed_runner)
    assert malformed.summary.completeness is Completeness.UNAVAILABLE
    assert "raw-secret" not in " ".join(malformed.summary.limitations)


def test_git_history_rejects_relative_and_repository_contained_executable(tmp_path: Path) -> None:
    executable = tmp_path / "git.exe"
    executable.write_bytes(b"untrusted repository executable")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "false\n", "")

    for candidate in ("git.exe", str(executable.resolve())):
        history = collect_git_history(
            tmp_path,
            remote=False,
            git_executable=candidate,
            runner=runner,
        )
        assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == 0


def test_git_history_rejects_external_gitdir_and_object_alternates(tmp_path: Path) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-external-git"
    outside.mkdir()
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "false\n", "")

    (tmp_path / ".git").write_text(f"gitdir: {outside}\n", encoding="utf-8")
    external_gitdir = collect_git_history(tmp_path, remote=False, runner=runner)
    assert external_gitdir.summary.completeness is Completeness.UNAVAILABLE
    assert calls == 0

    (tmp_path / ".git").unlink()
    alternates = tmp_path / ".git" / "objects" / "info" / "alternates"
    alternates.parent.mkdir(parents=True)
    alternates.write_text(str(outside), encoding="utf-8")
    external_alternates = collect_git_history(tmp_path, remote=False, runner=runner)
    assert external_alternates.summary.completeness is Completeness.UNAVAILABLE
    assert calls == 0


def test_git_history_rejects_external_alternates_in_contained_common_directory(
    tmp_path: Path,
) -> None:
    outside = tmp_path.parent / f"{tmp_path.name}-external-objects"
    outside.mkdir()
    administrative = tmp_path / "admin"
    git_directory = administrative / "worktree-git"
    common = administrative / "common"
    git_directory.mkdir(parents=True)
    alternates = common / "objects" / "info" / "alternates"
    alternates.parent.mkdir(parents=True)
    alternates.write_text(str(outside), encoding="utf-8")
    (git_directory / "commondir").write_text("../common\n", encoding="utf-8")
    (tmp_path / ".git").write_text("gitdir: admin/worktree-git\n", encoding="utf-8")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "false\n", "")

    history = collect_git_history(tmp_path, remote=False, runner=runner)
    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == 0


def test_git_history_detects_metadata_mutation_during_invocation(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)
    head = tmp_path / ".git" / "HEAD"
    head.write_text("ref: refs/heads/main\n", encoding="utf-8")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            head.write_text("ref: refs/heads/other\n", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "false\n", "")
        if "symbolic-ref" in argv:
            return subprocess.CompletedProcess(argv, 0, "main\n", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            "a" * 40 + "\x1f2020-01-01T00:00:00+00:00\x1fAlice\x1fa@example.test\x1e",
            "",
        )

    history = collect_git_history(tmp_path, remote=False, runner=runner)
    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert "changed" in " ".join(history.summary.limitations).casefold()


def test_git_history_detects_contained_alternate_mutation_during_invocation(
    tmp_path: Path,
) -> None:
    _make_git_metadata(tmp_path)
    alternate = tmp_path / "alternate-objects"
    alternate.mkdir()
    object_file = alternate / "object-data"
    object_file.write_text("before", encoding="utf-8")
    info = tmp_path / ".git" / "objects" / "info"
    info.mkdir()
    (info / "alternates").write_text(str(alternate), encoding="utf-8")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        if calls == 1:
            object_file.write_text("after-change", encoding="utf-8")
            return subprocess.CompletedProcess(argv, 0, "false\n", "")
        if "symbolic-ref" in argv:
            return subprocess.CompletedProcess(argv, 0, "main\n", "")
        return subprocess.CompletedProcess(
            argv,
            0,
            "a" * 40 + "\x1f2020-01-01T00:00:00+00:00\x1fAlice\x1fa@example.test\x1e",
            "",
        )

    history = collect_git_history(tmp_path, remote=False, runner=runner)
    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert "changed" in " ".join(history.summary.limitations).casefold()


@pytest.mark.parametrize(
    "section",
    [
        '[include]\npath = "../external-config"\n',
        '[includeIf "gitdir:../outside/"]\npath = "../external-config"\n',
    ],
)
def test_git_history_rejects_local_config_include_surfaces(tmp_path: Path, section: str) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(section, encoding="utf-8")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "false\n", "")

    history = collect_git_history(tmp_path, remote=False, runner=runner)
    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == 0


@pytest.mark.parametrize(
    ("section", "encoding"),
    [
        pytest.param("[include]", "utf-8-sig", id="bom-include"),
        pytest.param(
            '[includeIf\t"gitdir:**"]',
            "utf-8",
            id="tab-include-if",
        ),
    ],
)
def test_installed_git_accepts_hostile_canonical_include_headers(
    tmp_path: Path,
    section: str,
    encoding: str,
) -> None:
    _run_git(tmp_path, "init")
    included = tmp_path.parent / f"{tmp_path.name}-external-config"
    included.write_text("[repoinsight]\nprobe = accepted\n", encoding="utf-8")
    (tmp_path / ".git" / "config").write_text(
        f'{section}\npath = "{included.as_posix()}"\n',
        encoding=encoding,
    )

    result = subprocess.run(
        [
            "git",
            "-c",
            "safe.directory=*",
            "config",
            "--local",
            "--includes",
            "--get",
            "repoinsight.probe",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={
            "PATH": __import__("os").environ.get("PATH", ""),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": __import__("os").devnull,
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "accepted"


def test_installed_git_reads_applicable_config_worktree_include(tmp_path: Path) -> None:
    _run_git(tmp_path, "init")
    _run_git(tmp_path, "config", "extensions.worktreeConfig", "true")
    included = tmp_path.parent / f"{tmp_path.name}-external-worktree-config"
    included.write_text("[repoinsight]\nprobe = worktree\n", encoding="utf-8")
    (tmp_path / ".git" / "config.worktree").write_text(
        f'[include]\npath = "{included.as_posix()}"\n',
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            "git",
            "-c",
            "safe.directory=*",
            "config",
            "--includes",
            "--get",
            "repoinsight.probe",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="strict",
        env={
            "PATH": __import__("os").environ.get("PATH", ""),
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": __import__("os").devnull,
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "worktree"


@pytest.mark.parametrize(
    ("extension_value", "expected_probe"),
    [
        pytest.param(None, None, id="extension-absent"),
        pytest.param("false", None, id="extension-false"),
        pytest.param("000", None, id="numeric-zero"),
        pytest.param("true", "current", id="extension-true"),
        pytest.param("2", "current", id="numeric-positive"),
        pytest.param("-1", "current", id="numeric-negative"),
        pytest.param("+1", "current", id="numeric-signed-positive"),
        pytest.param("2K", "current", id="numeric-uppercase-suffix"),
    ],
)
def test_installed_git_reads_config_worktree_only_when_extension_is_enabled(
    tmp_path: Path,
    extension_value: str | None,
    expected_probe: str | None,
) -> None:
    _run_git(tmp_path, "init")
    if extension_value is not None:
        _run_git(tmp_path, "config", "extensions.worktreeConfig", extension_value)
    (tmp_path / ".git" / "config.worktree").write_text(
        "[repoinsight]\nprobe = current\n",
        encoding="utf-8",
    )

    result = _git_result(tmp_path, "config", "--get", "repoinsight.probe")

    if expected_probe is None:
        assert result.returncode == 1, result.stderr
        assert result.stdout == ""
    else:
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == expected_probe


@pytest.mark.parametrize(
    ("extension_value", "current_is_active"),
    [
        pytest.param(None, False, id="extension-absent"),
        pytest.param("false", False, id="extension-false"),
        pytest.param("true", True, id="extension-true"),
    ],
)
def test_installed_git_linked_worktree_reads_only_common_and_current_configs(
    tmp_path: Path,
    extension_value: str | None,
    current_is_active: bool,
) -> None:
    main, linked, other = _make_installed_git_linked_worktrees(tmp_path)
    _run_git(main, "config", "repoinsight.common", "common")
    if extension_value is not None:
        _run_git(main, "config", "extensions.worktreeConfig", extension_value)
    common_directory = main / ".git"
    linked_git_directory = Path(
        _git_result(linked, "rev-parse", "--absolute-git-dir").stdout.strip()
    )
    other_git_directory = Path(_git_result(other, "rev-parse", "--absolute-git-dir").stdout.strip())
    (common_directory / "config.worktree").write_text(
        "[repoinsight]\ncommonWorktree = ignored\n",
        encoding="utf-8",
    )
    (linked_git_directory / "config").write_text(
        "[repoinsight]\nlinkedConfig = ignored\n",
        encoding="utf-8",
    )
    (linked_git_directory / "config.worktree").write_text(
        "[repoinsight]\ncurrent = current\n",
        encoding="utf-8",
    )
    (other_git_directory / "config.worktree").write_text(
        "[repoinsight]\nother = ignored\n",
        encoding="utf-8",
    )

    result = _git_result(linked, "config", "--get-regexp", r"^repoinsight\.")

    assert result.returncode == 0, result.stderr
    expected = {("repoinsight.common", "common")}
    if current_is_active:
        expected.add(("repoinsight.current", "current"))
    assert {tuple(line.split(maxsplit=1)) for line in result.stdout.splitlines()} == expected


def test_git_history_accepts_bom_prefixed_config_without_include(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(
        "[core]\nrepositoryformatversion = 0\n",
        encoding="utf-8-sig",
    )

    history = collect_git_history(
        tmp_path,
        remote=False,
        runner=lambda argv, **_: _successful_history_result(argv),
    )

    assert history.summary.completeness is Completeness.AVAILABLE


def test_git_history_rejects_bom_prefixed_local_config_include(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-external-config"
    outside.write_text("[repoinsight]\nprobe = external\n", encoding="utf-8")
    (tmp_path / ".git" / "config").write_text(
        f'[include]\npath = "{outside.as_posix()}"\n',
        encoding="utf-8-sig",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


def test_git_history_rejects_tab_separated_include_if(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)
    outside = tmp_path.parent / f"{tmp_path.name}-external-config"
    outside.write_text("[repoinsight]\nprobe = external\n", encoding="utf-8")
    (tmp_path / ".git" / "config").write_text(
        f'[includeIf\t"gitdir:**"]\npath = "{outside.as_posix()}"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


def test_git_history_rejects_mixed_case_include_section_with_subsection(
    tmp_path: Path,
) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(
        '[InClUdE "ambiguous subsection"]\npath = "unused"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


def test_git_history_rejects_include_in_common_directory_config(tmp_path: Path) -> None:
    _, common_directory = _make_linked_worktree_metadata(tmp_path)
    (common_directory / "config").write_text(
        '[InClUdE "ambiguous subsection"]\npath = "unused"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


def test_git_history_rejects_applicable_config_worktree_include(tmp_path: Path) -> None:
    git_directory, common_directory = _make_linked_worktree_metadata(tmp_path)
    (common_directory / "config").write_text(
        "[extensions]\nworktreeConfig = true\n",
        encoding="utf-8",
    )
    (git_directory / "config.worktree").write_text(
        '[include]\npath = "unused"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


@pytest.mark.parametrize(
    "assignment",
    [
        pytest.param(None, id="extension-absent"),
        pytest.param("worktreeConfig = false", id="false"),
        pytest.param("worktreeConfig = no", id="no"),
        pytest.param("worktreeConfig = off", id="off"),
        pytest.param("worktreeConfig = 0", id="zero"),
        pytest.param("worktreeConfig = 000", id="numeric-zero"),
        pytest.param("worktreeConfig =", id="empty"),
    ],
)
def test_git_history_ignores_inactive_config_worktree_for_false_boolean_forms(
    tmp_path: Path,
    assignment: str | None,
) -> None:
    _make_git_metadata(tmp_path)
    if assignment is not None:
        (tmp_path / ".git" / "config").write_text(
            f"[extensions]\n{assignment}\n",
            encoding="utf-8",
        )
    (tmp_path / ".git" / "config.worktree").write_text(
        '[include]\npath = "ignored-while-inactive"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.AVAILABLE
    assert len(calls) == 3


@pytest.mark.parametrize(
    "assignment",
    [
        pytest.param("worktreeConfig", id="implicit"),
        pytest.param("worktreeConfig = true", id="true"),
        pytest.param("worktreeConfig = yes", id="yes"),
        pytest.param("worktreeConfig = on", id="on"),
        pytest.param("worktreeConfig = 1", id="one"),
        pytest.param("worktreeConfig = 2", id="numeric-positive"),
        pytest.param("worktreeConfig = -1", id="numeric-negative"),
        pytest.param("worktreeConfig = +1", id="numeric-signed-positive"),
        pytest.param("worktreeConfig = 2k", id="numeric-k-suffix"),
        pytest.param("worktreeConfig = 2M", id="numeric-m-suffix-uppercase"),
        pytest.param("worktreeConfig = -3g", id="numeric-g-suffix"),
    ],
)
def test_git_history_rejects_current_config_worktree_for_true_boolean_forms(
    tmp_path: Path,
    assignment: str,
) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(
        f"[extensions]\n{assignment}\n",
        encoding="utf-8",
    )
    (tmp_path / ".git" / "config.worktree").write_text(
        '[include]\npath = "active-include"\n',
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


@pytest.mark.parametrize(
    "value",
    [
        pytest.param("2", id="positive"),
        pytest.param("-1", id="negative"),
        pytest.param("+1", id="signed-positive"),
        pytest.param("2k", id="k-suffix"),
        pytest.param("2M", id="uppercase-m-suffix"),
        pytest.param("-3g", id="signed-g-suffix"),
    ],
)
def test_git_history_accepts_nonzero_numeric_worktree_config_values(
    tmp_path: Path,
    value: str,
) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(
        f"[extensions]\nworktreeConfig = {value}\n",
        encoding="utf-8",
    )
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.AVAILABLE
    assert len(calls) == 3


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            "[extensions]\nworktreeConfig = true\nworktreeConfig = false\n",
            id="conflicting-values",
        ),
        pytest.param(
            "[extensions]\nworktreeConfig = sometimes\n",
            id="invalid-value",
        ),
    ],
)
def test_git_history_fails_closed_on_ambiguous_worktree_config_activation(
    tmp_path: Path,
    content: str,
) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(content, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


@pytest.mark.parametrize(
    "content",
    [
        pytest.param(
            "[extensions]\nworktreeConfig = true\nworktreeConfig = yes\n",
            id="repeated-true",
        ),
        pytest.param(
            "[extensions]\nworktreeConfig = false\nworktreeConfig = off\n",
            id="repeated-false",
        ),
    ],
)
def test_git_history_accepts_consistent_repeated_worktree_config_values(
    tmp_path: Path,
    content: str,
) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(content, encoding="utf-8")

    history = collect_git_history(
        tmp_path,
        remote=False,
        runner=lambda argv, **_: _successful_history_result(argv),
    )

    assert history.summary.completeness is Completeness.AVAILABLE


@pytest.mark.parametrize(
    "common_config",
    [
        pytest.param("[core]\nrepositoryformatversion = 0\n", id="extension-absent"),
        pytest.param("[extensions]\nworktreeConfig = false\n", id="extension-false"),
    ],
)
def test_git_history_ignores_linked_worktree_config_when_not_enabled(
    tmp_path: Path,
    common_config: str,
) -> None:
    git_directory, common_directory = _make_linked_worktree_metadata(tmp_path)
    (common_directory / "config").write_text(common_config, encoding="utf-8")
    (git_directory / "config.worktree").write_text(
        '[include]\npath = "inactive-linked-include"\n',
        encoding="utf-8",
    )

    history = collect_git_history(
        tmp_path,
        remote=False,
        runner=lambda argv, **_: _successful_history_result(argv),
    )

    assert history.summary.completeness is Completeness.AVAILABLE


@pytest.mark.parametrize(
    "surface",
    [
        pytest.param("linked-git-config", id="linked-git-config"),
        pytest.param("common-config-worktree", id="common-config-worktree"),
        pytest.param("non-current-config-worktree", id="non-current-config-worktree"),
    ],
)
def test_git_history_ignores_linked_config_surfaces_git_does_not_read(
    tmp_path: Path,
    surface: str,
) -> None:
    git_directory, common_directory = _make_linked_worktree_metadata(tmp_path)
    (common_directory / "config").write_text(
        "[extensions]\nworktreeConfig = true\n",
        encoding="utf-8",
    )
    if surface == "linked-git-config":
        ignored = git_directory / "config"
    elif surface == "common-config-worktree":
        ignored = common_directory / "config.worktree"
    else:
        ignored = common_directory / "worktrees" / "other" / "config.worktree"
        ignored.parent.mkdir()
    ignored.write_text(
        '[include]\npath = "ignored-surface"\n',
        encoding="utf-8",
    )

    history = collect_git_history(
        tmp_path,
        remote=False,
        runner=lambda argv, **_: _successful_history_result(argv),
    )

    assert history.summary.completeness is Completeness.AVAILABLE


@pytest.mark.parametrize(
    "content",
    [
        "[core\nrepositoryformatversion = 0\n",
        '[core "unterminated]\nrepositoryformatversion = 0\n',
    ],
)
def test_git_history_fails_closed_on_malformed_config(tmp_path: Path, content: str) -> None:
    _make_git_metadata(tmp_path)
    (tmp_path / ".git" / "config").write_text(content, encoding="utf-8")
    calls: list[list[str]] = []

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        calls.append(argv)
        return _successful_history_result(argv)

    history = collect_git_history(tmp_path, remote=False, runner=runner)

    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == []


def test_git_history_rejects_alternate_chain_beyond_cycle_cap(tmp_path: Path) -> None:
    _make_git_metadata(tmp_path)
    stores = [tmp_path / f"alternate-{index:03}" for index in range(130)]
    for store in stores:
        (store / "info").mkdir(parents=True)
    (tmp_path / ".git" / "objects" / "info").mkdir()
    (tmp_path / ".git" / "objects" / "info" / "alternates").write_text(
        str(stores[0]), encoding="utf-8"
    )
    for current, following in pairwise(stores):
        (current / "info" / "alternates").write_text(str(following), encoding="utf-8")
    calls = 0

    def runner(argv: list[str], **_: object) -> subprocess.CompletedProcess[str]:
        nonlocal calls
        calls += 1
        return subprocess.CompletedProcess(argv, 0, "false\n", "")

    history = collect_git_history(tmp_path, remote=False, runner=runner)
    assert history.summary.completeness is Completeness.UNAVAILABLE
    assert calls == 0
