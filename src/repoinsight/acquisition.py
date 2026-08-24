"""Safe source parsing and acquisition boundary."""

from __future__ import annotations

import os
import re
import stat as stat_module
import subprocess
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import urlsplit

from .errors import AcquisitionError, InvalidUsageError
from .models import EffectiveConfig, SourceKind

_GITHUB_OWNER = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_GITHUB_REPOSITORY = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,99})$")
_DIAGNOSTIC_LIMIT = 512


class GitRunner(Protocol):
    def __call__(self, argv: list[str], **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class SourceReference:
    kind: SourceKind
    canonical_identity: str
    local_path: Path | None


@dataclass(frozen=True)
class AcquiredRepository:
    root: Path
    source: SourceReference
    temporary: bool


def parse_source(source: str, *, cwd: Path | None = None) -> SourceReference:
    """Validate and normalize a local directory or public GitHub HTTPS URL."""
    if not source:
        raise InvalidUsageError("Source must not be empty")

    url_like = source.replace("\\", "/")
    looks_remote = (
        "://" in source
        or source.startswith(("git@", "github.com/"))
        or source.lower().startswith(("http:", "https:", "ssh:"))
        or url_like.lstrip("/").casefold().startswith("github.com/")
    )
    if looks_remote:
        return _parse_github_source(source)

    base = (cwd or Path.cwd()).resolve(strict=False)
    candidate = Path(source)
    if not candidate.is_absolute():
        candidate = base / candidate
    try:
        resolved = candidate.resolve(strict=True)
        if not resolved.is_dir():
            raise InvalidUsageError("Local source must be an accessible directory")
        # Opening a directory is not portable; scandir is a read-only access probe.
        with os.scandir(resolved):
            pass
    except InvalidUsageError:
        raise
    except OSError:
        raise InvalidUsageError("Local source must be an accessible directory") from None
    return SourceReference(SourceKind.LOCAL, str(resolved), resolved)


def _parse_github_source(source: str) -> SourceReference:
    if "%" in source:
        raise InvalidUsageError("GitHub source URL is not allowlisted")
    try:
        parsed = urlsplit(source)
    except ValueError:
        raise InvalidUsageError("GitHub source URL is not allowlisted") from None
    if (
        parsed.scheme != "https"
        or parsed.hostname != "github.com"
        or parsed.netloc != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or parsed.port is not None
        or parsed.query
        or parsed.fragment
    ):
        raise InvalidUsageError("GitHub source URL is not allowlisted")
    raw_path = parsed.path
    if raw_path.endswith("/"):
        raw_path = raw_path[:-1]
    parts = raw_path.split("/")
    if len(parts) != 3 or parts[0] != "":
        raise InvalidUsageError("GitHub source URL is not allowlisted")
    owner, repository = parts[1], parts[2]
    if repository.endswith(".git"):
        repository = repository[:-4]
    if (
        not _GITHUB_OWNER.fullmatch(owner)
        or not _GITHUB_REPOSITORY.fullmatch(repository)
        or repository in {".", "..", ".git"}
        or owner in {".", ".."}
    ):
        raise InvalidUsageError("GitHub source URL is not allowlisted")
    canonical = f"https://github.com/{owner}/{repository}"
    return SourceReference(SourceKind.GITHUB, canonical, None)


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


def _trusted_git_executable(
    requested: str | None,
    *,
    forbidden_roots: tuple[Path, ...],
) -> str | None:
    candidates: list[Path] = []
    if requested is not None:
        raw = Path(requested)
        if not raw.is_absolute():
            return None
        candidates.append(raw)
    else:
        names = ("git.exe", "git") if os.name == "nt" else ("git",)
        for raw_directory in os.environ.get("PATH", "").split(os.pathsep):
            if not raw_directory:
                continue
            directory = Path(raw_directory)
            if not directory.is_absolute():
                continue
            candidates.extend(directory / name for name in names)

    resolved_forbidden = tuple(root.resolve(strict=False) for root in forbidden_roots)
    for candidate in candidates:
        try:
            metadata = os.lstat(candidate)
            resolved = candidate.resolve(strict=True)
        except OSError:
            continue
        attributes = getattr(metadata, "st_file_attributes", 0)
        if (
            not stat_module.S_ISREG(metadata.st_mode)
            or candidate.is_symlink()
            or bool(attributes & 0x400)
            or candidate != resolved
            or not _trusted_path_chain(resolved)
            or any(_is_contained(root, resolved) for root in resolved_forbidden)
        ):
            continue
        return str(resolved)
    return None


def _trusted_path_chain(path: Path) -> bool:
    if not path.is_absolute():
        return False
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        try:
            metadata = os.lstat(current)
        except OSError:
            return False
        attributes = getattr(metadata, "st_file_attributes", 0)
        if stat_module.S_ISLNK(metadata.st_mode) or bool(attributes & 0x400):
            return False
    return True


def _is_contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _clone_arguments(
    executable: str, source: SourceReference, depth: int, target: Path
) -> list[str]:
    return [
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
        str(depth),
        "--no-tags",
        "--single-branch",
        "--no-recurse-submodules",
        source.canonical_identity,
        str(target),
    ]


def _safe_clone_failure(error: BaseException) -> str:
    if isinstance(error, subprocess.TimeoutExpired):
        return "Git clone timed out"
    if isinstance(error, subprocess.CalledProcessError):
        return f"Git clone failed (status {error.returncode})"[:_DIAGNOSTIC_LIMIT]
    return f"Git clone failed ({type(error).__name__})"[:_DIAGNOSTIC_LIMIT]


@contextmanager
def acquire_source(
    source: SourceReference,
    config: EffectiveConfig,
    *,
    git_executable: str | None = None,
    runner: GitRunner | None = None,
) -> Iterator[AcquiredRepository]:
    """Yield a read-only local root or a bounded private temporary clone."""
    if source.kind is SourceKind.LOCAL:
        if source.local_path is None:
            raise AcquisitionError("Local source path is unavailable")
        yield AcquiredRepository(source.local_path, source, False)
        return

    executable = _trusted_git_executable(
        git_executable,
        forbidden_roots=(Path.cwd(),),
    )
    if not executable:
        raise AcquisitionError("Trusted Git executable is unavailable")
    run = runner or subprocess.run
    try:
        with tempfile.TemporaryDirectory(prefix="repoinsight-") as temporary:
            temporary_root = Path(temporary)
            target = temporary_root / "repository"
            argv = _clone_arguments(
                executable,
                source,
                config.git.remote_history_depth,
                target,
            )
            try:
                completed = run(
                    argv,
                    cwd=temporary_root,
                    env=_git_environment(executable),
                    shell=False,
                    timeout=config.git.clone_timeout_seconds,
                    capture_output=True,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    check=False,
                )
                if getattr(completed, "returncode", 1) != 0:
                    raise subprocess.CalledProcessError(
                        completed.returncode,
                        argv,
                        output=getattr(completed, "stdout", ""),
                        stderr=getattr(completed, "stderr", ""),
                    )
                if not target.is_dir():
                    raise OSError("Git clone did not create repository directory")
            except (OSError, subprocess.SubprocessError) as error:
                raise AcquisitionError(_safe_clone_failure(error)) from None
            yield AcquiredRepository(target, source, True)
    except AcquisitionError:
        raise
    except BaseException:
        # TemporaryDirectory cleanup runs before preserving control-flow exceptions.
        raise


__all__ = [
    "AcquiredRepository",
    "GitRunner",
    "SourceReference",
    "acquire_source",
    "parse_source",
]
