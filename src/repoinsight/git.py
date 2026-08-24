"""Read-only Git history inspection."""

from __future__ import annotations

import os
import re
import stat as stat_module
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import cast

from .acquisition import GitRunner, _is_contained, _trusted_git_executable
from .models import Completeness, GitSummary

_REVISION = re.compile(r"^[0-9a-fA-F]{40,64}$")
_CONFIG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9-]*")
_TRUE_GIT_BOOLEANS = frozenset({"1", "on", "true", "yes"})
_FALSE_GIT_BOOLEANS = frozenset({"", "0", "off", "false", "no"})
_NUMERIC_GIT_BOOLEAN = re.compile(r"^[+-]?([0-9]+)(?:[kmg])?$", re.IGNORECASE)
_FORMAT = "%H%x1f%aI%x1f%an%x1f%ae%x1e"
_MAX_GIT_STORAGE_ROOTS = 128


@dataclass(frozen=True)
class GitCommit:
    revision: str
    authored_at: datetime
    author_identity: str


@dataclass(frozen=True)
class GitHistory:
    summary: GitSummary
    commits: tuple[GitCommit, ...]


@dataclass(frozen=True)
class _ConfigInspection:
    worktree_config_enabled: bool


def collect_git_history(
    root: Path,
    *,
    remote: bool,
    git_executable: str | None = None,
    timeout_seconds: int = 30,
    runner: GitRunner | None = None,
) -> GitHistory:
    """Collect bounded reachable HEAD metadata without diffs or repository execution."""
    executable = _trusted_git_executable(
        git_executable,
        forbidden_roots=(root, Path.cwd()),
    )
    if not executable:
        return _unavailable("Git executable is unavailable")
    if not _git_metadata_is_contained(root):
        return _unavailable("Git metadata is unavailable or outside the repository")
    metadata_snapshot = _git_metadata_snapshot(root)
    if metadata_snapshot is None:
        return _unavailable("Git metadata is unavailable or outside the repository")
    run = runner or subprocess.run
    base = [
        executable,
        "--no-replace-objects",
        "-c",
        f"safe.directory={root.resolve(strict=False)}",
        "-c",
        f"core.hooksPath={os.devnull}",
        "-c",
        "credential.helper=",
        "-c",
        "core.pager=cat",
        "-c",
        "diff.external=",
        "-c",
        "core.fsmonitor=false",
    ]

    metadata_changed = False

    def invoke(arguments: list[str]) -> subprocess.CompletedProcess[str] | None:
        nonlocal metadata_changed
        if _git_metadata_snapshot(root) != metadata_snapshot:
            metadata_changed = True
            return None
        try:
            result = run(
                [*base, *arguments],
                cwd=root,
                env=_git_environment(executable),
                shell=False,
                timeout=timeout_seconds,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="strict",
                check=False,
            )
        except (OSError, UnicodeError, subprocess.SubprocessError):
            return None
        if _git_metadata_snapshot(root) != metadata_snapshot:
            metadata_changed = True
            return None
        return cast(subprocess.CompletedProcess[str], result)

    shallow_result = invoke(["rev-parse", "--is-shallow-repository"])
    if metadata_changed:
        return _unavailable("Git metadata changed during history inspection")
    if shallow_result is None or shallow_result.returncode != 0:
        return _unavailable("Git metadata is unavailable")
    shallow_text = shallow_result.stdout.strip().casefold()
    if shallow_text not in {"true", "false"}:
        return _unavailable("Git metadata output was malformed")
    shallow = shallow_text == "true"

    branch_result = invoke(["symbolic-ref", "--quiet", "--short", "HEAD"])
    if metadata_changed:
        return _unavailable("Git metadata changed during history inspection")
    branch = None
    if branch_result is not None and branch_result.returncode == 0:
        candidate_branch = branch_result.stdout.strip()
        if candidate_branch and "\x00" not in candidate_branch and len(candidate_branch) <= 255:
            branch = candidate_branch

    log_result = invoke(
        [
            "log",
            "--no-show-signature",
            "--no-mailmap",
            "--no-textconv",
            f"--format={_FORMAT}",
            "HEAD",
        ]
    )
    if metadata_changed:
        return _unavailable("Git metadata changed during history inspection")
    if log_result is None or log_result.returncode != 0 or not log_result.stdout:
        return _unavailable("No readable reachable Git commits are available", branch=branch)
    try:
        commits = _parse_commits(log_result.stdout)
    except ValueError:
        return _unavailable("Git history output was malformed", branch=branch)
    if not commits:
        return _unavailable("No readable reachable Git commits are available", branch=branch)

    partial = remote or shallow
    limitations: tuple[str, ...] = ()
    if remote:
        limitations += ("Remote history is bounded and may omit older reachable commits",)
    if shallow:
        limitations += ("Git repository reports shallow history",)
    summary = GitSummary(
        available=True,
        completeness=Completeness.PARTIAL if partial else Completeness.AVAILABLE,
        head_revision=commits[0].revision,
        branch=branch,
        commits_considered=len(commits),
        contributor_count=len({commit.author_identity for commit in commits}),
        first_commit_at=min(commit.authored_at for commit in commits),
        latest_commit_at=max(commit.authored_at for commit in commits),
        limitations=limitations,
    )
    return GitHistory(summary=summary, commits=commits)


def _parse_commits(output: str) -> tuple[GitCommit, ...]:
    commits: list[GitCommit] = []
    for raw_record in output.split("\x1e"):
        record = raw_record.strip("\r\n")
        if not record:
            continue
        fields = record.split("\x1f")
        if len(fields) != 4:
            raise ValueError("malformed Git record")
        revision, raw_date, author_name, author_email = fields
        if not _REVISION.fullmatch(revision):
            raise ValueError("malformed Git revision")
        try:
            authored_at = datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
        except ValueError:
            raise ValueError("malformed Git date") from None
        if authored_at.tzinfo is None or authored_at.utcoffset() is None:
            raise ValueError("Git date lacks timezone")
        identity = _normalize_identity(author_name, author_email)
        commits.append(GitCommit(revision.casefold(), authored_at, identity))
    return tuple(commits)


def _normalize_identity(name: str, email: str) -> str:
    normalized_name = " ".join(name.split()).casefold()
    normalized_email = " ".join(email.split()).casefold()
    if not normalized_name and not normalized_email:
        return "unknown"
    return f"{normalized_name} <{normalized_email}>"


def _unavailable(message: str, *, branch: str | None = None) -> GitHistory:
    return GitHistory(
        summary=GitSummary(
            available=False,
            completeness=Completeness.UNAVAILABLE,
            head_revision=None,
            branch=branch,
            commits_considered=0,
            contributor_count=0,
            first_commit_at=None,
            latest_commit_at=None,
            limitations=(message,),
        ),
        commits=(),
    )


def _git_environment(executable: str) -> dict[str, str]:
    allowed = ("SYSTEMROOT", "WINDIR", "TEMP", "TMP")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["PATH"] = str(Path(executable).parent)
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "Never",
            "GIT_PAGER": "cat",
            "GIT_EXTERNAL_DIFF": "",
        }
    )
    return env


def _git_metadata_is_contained(root: Path) -> bool:
    resolved_root = root.resolve(strict=False)
    return _git_storage_roots(resolved_root) is not None


def _git_storage_roots(resolved_root: Path) -> tuple[Path, ...] | None:
    metadata_roots = _git_metadata_roots(resolved_root)
    if metadata_roots is None:
        return None
    if any(not _metadata_tree_is_contained(resolved_root, item) for item in metadata_roots):
        return None
    git_directory = metadata_roots[0]
    common_directory = metadata_roots[-1]
    common_config = _inspect_config(
        common_directory / "config",
        read_worktree_config=True,
    )
    if common_config is None:
        return None
    if common_config.worktree_config_enabled and _config_has_include(
        git_directory / "config.worktree"
    ):
        return None
    object_roots: list[Path] = []
    pending = [item / "objects" for item in metadata_roots if (item / "objects").exists()]
    seen: set[Path] = set()
    while pending:
        object_root = pending.pop()
        try:
            resolved_object_root = object_root.resolve(strict=True)
        except OSError:
            return None
        if resolved_object_root in seen:
            continue
        seen.add(resolved_object_root)
        if len(seen) > _MAX_GIT_STORAGE_ROOTS:
            return None
        if not _is_contained(resolved_root, resolved_object_root) or not _safe_directory_chain(
            resolved_root, resolved_object_root
        ):
            return None
        if not _metadata_tree_is_contained(resolved_root, resolved_object_root):
            return None
        object_roots.append(resolved_object_root)
        alternates = _alternate_object_roots(resolved_root, resolved_object_root)
        if alternates is None:
            return None
        pending.extend(alternates)
    return (*metadata_roots, *object_roots)


def _git_metadata_roots(resolved_root: Path) -> tuple[Path, ...] | None:
    marker = resolved_root / ".git"
    try:
        metadata = os.lstat(marker)
    except OSError:
        return None
    if _linklike(marker, metadata):
        return None
    if stat_module.S_ISREG(metadata.st_mode):
        raw = _read_small_regular(marker, metadata, 4096)
        if raw is None:
            return None
        try:
            line = raw.decode("utf-8", errors="strict").strip()
        except UnicodeDecodeError:
            return None
        if not line.casefold().startswith("gitdir:"):
            return None
        raw_target = line.split(":", 1)[1].strip()
        if not raw_target:
            return None
        target = Path(raw_target)
        if not target.is_absolute():
            target = resolved_root / target
        try:
            git_directory = target.resolve(strict=True)
        except OSError:
            return None
        if not _is_contained(resolved_root, git_directory) or not _safe_directory_chain(
            resolved_root, git_directory
        ):
            return None
    elif stat_module.S_ISDIR(metadata.st_mode):
        try:
            git_directory = marker.resolve(strict=True)
        except OSError:
            return None
        if not _is_contained(resolved_root, git_directory):
            return None
    else:
        return None

    common_directory = _contained_pointer(git_directory / "commondir", git_directory, resolved_root)
    if common_directory is False:
        return None
    metadata_roots = [git_directory]
    if isinstance(common_directory, Path) and common_directory != git_directory:
        metadata_roots.append(common_directory)
    return tuple(metadata_roots)


def _alternate_object_roots(resolved_root: Path, objects: Path) -> tuple[Path, ...] | None:
    alternates = objects / "info" / "alternates"
    try:
        alternate_metadata = os.lstat(alternates)
    except FileNotFoundError:
        return ()
    except OSError:
        return None
    if _linklike(alternates, alternate_metadata) or not stat_module.S_ISREG(
        alternate_metadata.st_mode
    ):
        return None
    raw_alternates = _read_small_regular(alternates, alternate_metadata, 16_384)
    if raw_alternates is None:
        return None
    try:
        lines = raw_alternates.decode("utf-8", errors="strict").splitlines()
    except UnicodeDecodeError:
        return None
    roots: list[Path] = []
    for line in lines:
        if not line.strip():
            continue
        target = Path(line.strip())
        if not target.is_absolute():
            target = objects / target
        try:
            resolved_target = target.resolve(strict=True)
        except OSError:
            return None
        if not _is_contained(resolved_root, resolved_target):
            return None
        roots.append(resolved_target)
    return tuple(roots)


def _config_has_include(path: Path) -> bool:
    return _inspect_config(path, read_worktree_config=False) is None


def _inspect_config(path: Path, *, read_worktree_config: bool) -> _ConfigInspection | None:
    try:
        metadata = os.lstat(path)
    except FileNotFoundError:
        return _ConfigInspection(worktree_config_enabled=False)
    except OSError:
        return None
    if _linklike(path, metadata) or not stat_module.S_ISREG(metadata.st_mode):
        return None
    raw = _read_small_regular(path, metadata, 1_048_576)
    if raw is None:
        return None
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError:
        return None
    try:
        worktree_config_enabled = _inspect_config_text(
            text,
            read_worktree_config=read_worktree_config,
        )
    except ValueError:
        return None
    return _ConfigInspection(worktree_config_enabled=worktree_config_enabled)


def _inspect_config_text(text: str, *, read_worktree_config: bool) -> bool:
    try:
        lines = _logical_config_lines(text)
    except ValueError as error:
        raise ValueError("unsafe Git config") from error
    current_section: tuple[str, bool] | None = None
    worktree_values: set[bool] = set()
    for line in lines:
        stripped = line.lstrip(" \t")
        if not stripped or stripped.startswith(("#", ";")):
            continue
        if stripped.startswith("["):
            try:
                section_name, has_subsection = _config_section(stripped)
            except ValueError as error:
                raise ValueError("unsafe Git config section") from error
            if section_name.casefold() in {"include", "includeif"}:
                raise ValueError("Git config include surface")
            current_section = (section_name.casefold(), has_subsection)
            continue
        if current_section is None:
            raise ValueError("Git config variable outside section")
        try:
            variable_name, value = _config_variable(stripped)
        except ValueError as error:
            raise ValueError("unsafe Git config variable") from error
        if (
            read_worktree_config
            and current_section == ("extensions", False)
            and variable_name.casefold() == "worktreeconfig"
        ):
            worktree_values.add(_git_boolean(value))
            if len(worktree_values) > 1:
                raise ValueError("conflicting extensions.worktreeConfig values")
    return next(iter(worktree_values), False)


def _logical_config_lines(text: str) -> tuple[str, ...]:
    if "\x00" in text or "\ufeff" in text:
        raise ValueError("invalid Git config text")
    lines: list[str] = []
    pending: str | None = None
    for raw_line in text.split("\n"):
        if raw_line.endswith("\r"):
            raw_line = raw_line[:-1]
        if "\r" in raw_line:
            raise ValueError("invalid Git config newline")
        line = raw_line if pending is None else pending + raw_line.lstrip(" \t")
        if _config_line_continues(line):
            pending = line[:-1]
        else:
            lines.append(line)
            pending = None
    if pending is not None:
        raise ValueError("unterminated Git config continuation")
    return tuple(lines)


def _config_line_continues(line: str) -> bool:
    quoted = False
    escaped = False
    content = line
    for index, character in enumerate(line):
        if escaped:
            escaped = False
            continue
        if character == "\\":
            escaped = True
            continue
        if character == '"':
            quoted = not quoted
        elif not quoted and character in "#;":
            content = line[:index]
            break
    backslashes = len(content) - len(content.rstrip("\\"))
    return backslashes % 2 == 1


def _config_section(line: str) -> tuple[str, bool]:
    match = _CONFIG_NAME.match(line, 1)
    if match is None:
        raise ValueError("malformed Git config section")
    section_name = match.group()
    position = match.end()
    if position >= len(line):
        raise ValueError("unterminated Git config section")

    has_subsection = False
    if line[position] == ".":
        has_subsection = True
        position += 1
        subsection_start = position
        while position < len(line) and line[position] != "]":
            character = line[position]
            if character.isspace() or character in {'"', "\\"}:
                raise ValueError("malformed Git config subsection")
            position += 1
        if position == subsection_start:
            raise ValueError("empty Git config subsection")
    else:
        while position < len(line) and line[position] in " \t":
            position += 1
        if position < len(line) and line[position] == '"':
            has_subsection = True
            position = _quoted_subsection_end(line, position + 1)
            while position < len(line) and line[position] in " \t":
                position += 1

    if position >= len(line) or line[position] != "]":
        raise ValueError("malformed Git config section")
    remainder = line[position + 1 :].lstrip(" \t")
    if remainder and not remainder.startswith(("#", ";")):
        raise ValueError("ambiguous Git config section")
    return section_name, has_subsection


def _quoted_subsection_end(line: str, position: int) -> int:
    while position < len(line):
        character = line[position]
        if character == '"':
            return position + 1
        if character == "\\":
            position += 1
            if position >= len(line) or line[position] not in {'"', "\\"}:
                raise ValueError("malformed Git config subsection escape")
        elif ord(character) < 32:
            raise ValueError("malformed Git config subsection")
        position += 1
    raise ValueError("unterminated Git config subsection")


def _config_variable(line: str) -> tuple[str, str | None]:
    match = _CONFIG_NAME.match(line)
    if match is None:
        raise ValueError("malformed Git config variable")
    variable_name = match.group()
    remainder = line[match.end() :].lstrip(" \t")
    if not remainder or remainder.startswith(("#", ";")):
        return variable_name, None
    if not remainder.startswith("="):
        raise ValueError("malformed Git config assignment")
    return variable_name, _config_value(remainder[1:])


def _config_value(value: str) -> str:
    parsed: list[tuple[str, bool]] = []
    quoted = False
    position = 0
    while position < len(value):
        character = value[position]
        if character == "\\":
            position += 1
            if position >= len(value) or value[position] not in {'"', "\\", "n", "t", "b"}:
                raise ValueError("malformed Git config value escape")
            escaped = value[position]
            parsed.append(
                (
                    {"n": "\n", "t": "\t", "b": "\b"}.get(escaped, escaped),
                    quoted,
                )
            )
        elif character == '"':
            quoted = not quoted
        elif not quoted and character in "#;":
            break
        elif ord(character) < 32 and character != "\t":
            raise ValueError("malformed Git config value")
        else:
            parsed.append((character, quoted))
        position += 1
    if quoted:
        raise ValueError("unterminated Git config value")
    start = 0
    end = len(parsed)
    while start < end and parsed[start][0] in " \t" and not parsed[start][1]:
        start += 1
    while end > start and parsed[end - 1][0] in " \t" and not parsed[end - 1][1]:
        end -= 1
    return "".join(character for character, _ in parsed[start:end])


def _git_boolean(value: str | None) -> bool:
    if value is None:
        return True
    normalized = value.casefold()
    if normalized in _TRUE_GIT_BOOLEANS:
        return True
    if normalized in _FALSE_GIT_BOOLEANS:
        return False
    numeric = _NUMERIC_GIT_BOOLEAN.fullmatch(normalized)
    if numeric is not None:
        return any(digit != "0" for digit in numeric.group(1))
    raise ValueError("invalid Git boolean")


def _git_metadata_snapshot(root: Path) -> tuple[tuple[object, ...], ...] | None:
    resolved_root = root.resolve(strict=False)
    storage_roots = _git_storage_roots(resolved_root)
    if storage_roots is None:
        return None
    records: list[tuple[object, ...]] = []
    marker = resolved_root / ".git"
    try:
        marker_metadata = os.lstat(marker)
    except OSError:
        return None
    records.append(_metadata_record(resolved_root, marker, marker_metadata))
    inspected = 0
    for metadata_root in storage_roots:
        pending = [metadata_root]
        while pending:
            directory = pending.pop()
            try:
                directory_metadata = os.lstat(directory)
                records.append(_metadata_record(resolved_root, directory, directory_metadata))
                with os.scandir(directory) as stream:
                    for entry in stream:
                        inspected += 1
                        if inspected > 100_000:
                            return None
                        path = Path(entry.path)
                        try:
                            metadata = os.lstat(path)
                        except OSError:
                            return None
                        records.append(_metadata_record(resolved_root, path, metadata))
                        if stat_module.S_ISDIR(metadata.st_mode):
                            pending.append(path)
            except OSError:
                return None
    return tuple(sorted(set(records), key=lambda item: str(item[0])))


def _metadata_record(root: Path, path: Path, metadata: os.stat_result) -> tuple[object, ...]:
    try:
        identity = path.relative_to(root).as_posix()
    except ValueError:
        identity = str(path)
    return (
        identity,
        metadata.st_dev,
        metadata.st_ino,
        stat_module.S_IFMT(metadata.st_mode),
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _contained_pointer(
    pointer: Path,
    base: Path,
    root: Path,
) -> Path | bool | None:
    try:
        metadata = os.lstat(pointer)
    except FileNotFoundError:
        return None
    except OSError:
        return False
    if _linklike(pointer, metadata) or not stat_module.S_ISREG(metadata.st_mode):
        return False
    raw = _read_small_regular(pointer, metadata, 4096)
    if raw is None:
        return False
    try:
        text = raw.decode("utf-8", errors="strict").strip()
    except UnicodeDecodeError:
        return False
    target = Path(text)
    if not target.is_absolute():
        target = base / target
    try:
        resolved = target.resolve(strict=True)
    except OSError:
        return False
    if not _is_contained(root, resolved) or not _safe_directory_chain(root, resolved):
        return False
    return resolved


def _metadata_tree_is_contained(root: Path, metadata_root: Path) -> bool:
    pending = [metadata_root]
    inspected = 0
    while pending:
        directory = pending.pop()
        try:
            with os.scandir(directory) as stream:
                for entry in stream:
                    inspected += 1
                    if inspected > 100_000:
                        return False
                    path = Path(entry.path)
                    try:
                        metadata = os.lstat(path)
                        resolved = path.resolve(strict=True)
                    except OSError:
                        return False
                    if _linklike(path, metadata) or not _is_contained(root, resolved):
                        return False
                    if stat_module.S_ISDIR(metadata.st_mode):
                        pending.append(path)
                    elif not stat_module.S_ISREG(metadata.st_mode):
                        return False
        except OSError:
            return False
    return True


def _safe_directory_chain(root: Path, target: Path) -> bool:
    try:
        relative = target.relative_to(root)
    except ValueError:
        return False
    current = root
    for part in relative.parts:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            return False
        if _linklike(current, metadata) or not stat_module.S_ISDIR(metadata.st_mode):
            return False
    return True


def _linklike(path: Path, metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    return (
        stat_module.S_ISLNK(metadata.st_mode)
        or bool(attributes & 0x400)
        or (stat_module.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1)
        or os.path.ismount(path)
    )


def _read_small_regular(path: Path, before: os.stat_result, maximum: int) -> bytes | None:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError:
        return None
    try:
        opened = os.fstat(descriptor)
        if not stat_module.S_ISREG(opened.st_mode) or not _same_identity(before, opened):
            return None
        raw = os.read(descriptor, maximum + 1)
        after = os.fstat(descriptor)
        if len(raw) > maximum or not _same_identity(opened, after):
            return None
        return raw
    except OSError:
        return None
    finally:
        os.close(descriptor)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        stat_module.S_IFMT(left.st_mode),
        left.st_size,
    ) == (
        right.st_dev,
        right.st_ino,
        stat_module.S_IFMT(right.st_mode),
        right.st_size,
    )


__all__ = ["GitCommit", "GitHistory", "collect_git_history"]
