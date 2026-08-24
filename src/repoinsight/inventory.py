"""Bounded repository inventory."""

from __future__ import annotations

import codecs
import heapq
import io
import itertools
import os
import stat as stat_module
import time
import tokenize
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from pathspec import GitIgnoreSpec
from pathspec.patterns.gitignore.base import GitIgnorePatternError

from .models import (
    Completeness,
    EffectiveConfig,
    Limitation,
    RepositoryInventory,
    SkippedInput,
    WarningRecord,
)
from .paths import normalize_relative_path

_SAFETY_DIRECTORY_NAMES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".venv",
        "venv",
        "env",
        ".tox",
        ".nox",
        ".pytest_cache",
        ".mypy_cache",
        ".ruff_cache",
        "__pycache__",
        "build",
        "dist",
        "site-packages",
        "node_modules",
        "vendor",
        "vendors",
        "third_party",
        "third-party",
        "generated",
    }
)
_DEPENDENCY_NAMES = frozenset(
    {
        "requirements.txt",
        "requirements-dev.txt",
        "constraints.txt",
        "poetry.lock",
        "pdm.lock",
        "uv.lock",
        "pipfile",
        "pipfile.lock",
        "pyproject.toml",
        "setup.cfg",
        "setup.py",
    }
)
_PACKAGING_NAMES = frozenset(
    {"pyproject.toml", "setup.cfg", "setup.py", "tox.ini", "noxfile.py", "manifest.in"}
)
_MAX_DIRECTORY_ENTRIES = 50_000
_WINDOWS_PLATFORM = os.name == "nt"


class FileRole(StrEnum):
    PYTHON_SOURCE = "python_source"
    PYTHON_TEST = "python_test"
    README = "readme"
    DOCUMENTATION = "documentation"
    CONTRIBUTION_GUIDE = "contribution_guide"
    CHANGELOG = "changelog"
    EXAMPLE = "example"
    DEPENDENCY = "dependency"
    PACKAGING = "packaging"
    CI = "ci"
    DOCKERFILE = "dockerfile"
    DOCKER_IGNORE = "docker_ignore"
    LICENSE = "license"
    IGNORE = "ignore"
    ISSUE_TEMPLATE = "issue_template"
    PULL_REQUEST_TEMPLATE = "pull_request_template"
    CODE_OF_CONDUCT = "code_of_conduct"
    SECURITY_POLICY = "security_policy"
    OTHER_TEXT = "other_text"


@dataclass(frozen=True)
class FileRecord:
    path: str
    size_bytes: int
    roles: frozenset[FileRole]
    text: str
    encoding: str
    line_count: int


@dataclass(frozen=True)
class InventoryResult:
    root: Path
    files: tuple[FileRecord, ...]
    summary: RepositoryInventory
    skipped_inputs: tuple[SkippedInput, ...]
    warnings: tuple[WarningRecord, ...]
    limitations: tuple[Limitation, ...]
    completeness: Completeness


@dataclass(frozen=True)
class _DirectorySnapshot:
    path: Path
    safe_path: str
    metadata: os.stat_result
    ancestors: tuple[tuple[Path, os.stat_result], ...]


@dataclass(frozen=True)
class _Candidate:
    safe_path: str
    path: Path
    metadata: os.stat_result
    ancestors: tuple[tuple[Path, os.stat_result], ...]


@dataclass(frozen=True)
class _OpenedDescriptor:
    descriptor: int
    atomic_beneath: bool


def build_inventory(
    root: Path,
    config: EffectiveConfig,
    *,
    monotonic: Callable[[], float] = time.monotonic,
) -> InventoryResult:
    """Build a deterministic, bounded inventory without following link-like entries."""
    resolved_root = root.resolve(strict=True)
    start = monotonic()
    skipped: list[SkippedInput] = []
    warnings: list[WarningRecord] = []
    limitations: list[Limitation] = []
    candidates: list[_Candidate] = []
    timed_out = False
    root_unreadable = False
    discovery_limited = False
    ignore_specs: dict[str, GitIgnoreSpec] = {}
    configured_excludes = GitIgnoreSpec.from_lines(config.analysis.exclude)

    def expired() -> bool:
        return monotonic() - start >= config.analysis.timeout_seconds

    try:
        root_metadata = os.lstat(resolved_root)
    except OSError:
        root_metadata = None
        root_unreadable = True
        limitations.append(
            Limitation(
                code="root-unreadable",
                message="Repository root became unreadable during inventory",
            )
        )
    work: list[tuple[str, int, _DirectorySnapshot | _Candidate]] = (
        [
            (
                "",
                0,
                _DirectorySnapshot(
                    path=resolved_root,
                    safe_path="",
                    metadata=root_metadata,
                    ancestors=((resolved_root, root_metadata),),
                ),
            )
        ]
        if root_metadata is not None
        else []
    )
    while work:
        if expired():
            timed_out = True
            for _, _, pending_item in sorted(work, key=lambda item: item[0]):
                if pending_item.safe_path:
                    skipped.append(
                        SkippedInput(
                            path=pending_item.safe_path,
                            reason="inventory time limit reached",
                        )
                    )
            break
        _, _, item = heapq.heappop(work)
        if isinstance(item, _Candidate):
            if len(candidates) >= config.analysis.max_files:
                discovery_limited = True
                skipped.append(SkippedInput(path=item.safe_path, reason="file-count limit reached"))
                for _, _, remaining_item in sorted(work, key=lambda pending: pending[0]):
                    if remaining_item.safe_path:
                        skipped.append(
                            SkippedInput(
                                path=remaining_item.safe_path,
                                reason="file-count limit reached",
                            )
                        )
                break
            candidates.append(item)
            continue

        directory_snapshot = item
        directory = directory_snapshot.path
        if not _directory_is_stable(
            resolved_root,
            directory,
            directory_snapshot.metadata,
        ):
            if directory == resolved_root:
                root_unreadable = True
                limitations.append(
                    Limitation(
                        code="root-unreadable",
                        message="Repository root changed before inventory",
                    )
                )
            else:
                skipped.append(
                    SkippedInput(
                        path=directory_snapshot.safe_path,
                        reason="directory changed before enumeration",
                    )
                )
            continue
        try:
            with os.scandir(directory) as stream:
                bounded = list(itertools.islice(stream, _MAX_DIRECTORY_ENTRIES + 1))
        except OSError:
            if directory == resolved_root:
                root_unreadable = True
                limitations.append(
                    Limitation(
                        code="root-unreadable",
                        message="Repository root became unreadable during inventory",
                    )
                )
            else:
                skipped.append(
                    SkippedInput(
                        path=directory_snapshot.safe_path,
                        reason="directory is unreadable",
                    )
                )
            continue
        if not _directory_is_stable(
            resolved_root,
            directory,
            directory_snapshot.metadata,
        ):
            skipped.append(
                SkippedInput(
                    path=directory_snapshot.safe_path,
                    reason="directory changed during enumeration",
                )
            )
            continue
        if len(bounded) > _MAX_DIRECTORY_ENTRIES:
            display = directory_snapshot.safe_path or "repository root"
            if directory_snapshot.safe_path:
                skipped.append(
                    SkippedInput(
                        path=directory_snapshot.safe_path,
                        reason="directory-entry limit reached",
                    )
                )
            limitations.append(
                Limitation(
                    code="directory-entry-limit",
                    message=(
                        "Directory was not analyzed because its entry limit was exceeded: "
                        f"{display}"
                    ),
                )
            )
            continue
        entries = sorted(bounded, key=lambda entry: entry.name)
        metadata_by_name: dict[str, os.stat_result] = {}
        ignore_entry = next((entry for entry in entries if entry.name == ".gitignore"), None)
        if ignore_entry is not None:
            ignore_path = Path(ignore_entry.path)
            try:
                ignore_metadata = os.lstat(ignore_path)
            except OSError:
                ignore_metadata = None
            if ignore_metadata is not None:
                metadata_by_name[ignore_entry.name] = ignore_metadata
                _load_directory_ignore(
                    resolved_root,
                    directory_snapshot.safe_path,
                    ignore_path,
                    ignore_metadata,
                    config.analysis.max_file_bytes,
                    ignore_specs,
                    warnings,
                    limitations,
                )
        for entry in entries:
            candidate = Path(entry.path)
            safe_path = _safe_child_path(directory_snapshot.safe_path, entry.name)
            try:
                metadata = metadata_by_name.get(entry.name) or os.lstat(candidate)
            except OSError:
                skipped.append(SkippedInput(path=safe_path, reason="entry metadata is unreadable"))
                continue
            if _is_reparse_or_linklike(candidate, metadata):
                skipped.append(
                    SkippedInput(path=safe_path, reason="link-like entry is not followed")
                )
                continue
            if stat_module.S_ISDIR(metadata.st_mode):
                if candidate.name.casefold() in _SAFETY_DIRECTORY_NAMES:
                    skipped.append(SkippedInput(path=safe_path, reason="safety-excluded directory"))
                    limitations.append(
                        Limitation(
                            code="safety-excluded",
                            message=f"Safety-excluded directory was not inspected: {safe_path}",
                        )
                    )
                    continue
                if _is_ignored(
                    f"{safe_path}/",
                    ignore_specs,
                    configured_excludes,
                    config.analysis.respect_gitignore,
                ):
                    skipped.append(SkippedInput(path=safe_path, reason="excluded by ignore policy"))
                    continue
                child = _DirectorySnapshot(
                    path=candidate,
                    safe_path=safe_path,
                    metadata=metadata,
                    ancestors=(*directory_snapshot.ancestors, (candidate, metadata)),
                )
                heapq.heappush(work, (f"{safe_path}/", 0, child))
            elif stat_module.S_ISREG(metadata.st_mode):
                if _is_ignored(
                    safe_path,
                    ignore_specs,
                    configured_excludes,
                    config.analysis.respect_gitignore,
                ):
                    skipped.append(SkippedInput(path=safe_path, reason="excluded by ignore policy"))
                    continue
                file_candidate = _Candidate(
                    safe_path=safe_path,
                    path=candidate,
                    metadata=metadata,
                    ancestors=directory_snapshot.ancestors,
                )
                heapq.heappush(work, (safe_path, 1, file_candidate))
            else:
                skipped.append(
                    SkippedInput(path=safe_path, reason="non-regular entry is not analyzed")
                )

    if timed_out:
        limitations.append(
            Limitation(code="inventory-timeout", message="Repository inventory time limit reached")
        )

    if discovery_limited:
        limitations.append(
            Limitation(
                code="file-discovery-limit",
                message="Repository discovery stopped at the configured file limit",
            )
        )

    candidates.sort(key=lambda item: item.safe_path)
    records: list[FileRecord] = []
    source_bytes = 0

    for index, candidate_record in enumerate(candidates):
        safe_path = candidate_record.safe_path
        candidate = candidate_record.path
        metadata = candidate_record.metadata
        if expired():
            timed_out = True
            for remaining_candidate in candidates[index:]:
                skipped.append(
                    SkippedInput(
                        path=remaining_candidate.safe_path,
                        reason="inventory time limit reached",
                    )
                )
            if not any(item.code == "inventory-timeout" for item in limitations):
                limitations.append(
                    Limitation(
                        code="inventory-timeout",
                        message="Repository inventory time limit reached",
                    )
                )
            break
        if metadata.st_size > config.analysis.max_file_bytes:
            skipped.append(
                SkippedInput(
                    path=safe_path,
                    reason=f"file exceeds {config.analysis.max_file_bytes}-byte limit",
                )
            )
            continue
        if len(records) >= config.analysis.max_files:
            skipped.append(SkippedInput(path=safe_path, reason="file-count limit reached"))
            continue
        if source_bytes + metadata.st_size > config.analysis.max_source_bytes:
            skipped.append(SkippedInput(path=safe_path, reason="source-byte limit reached"))
            continue
        if not _directory_chain_is_stable(resolved_root, candidate_record.ancestors):
            skipped.append(SkippedInput(path=safe_path, reason="ancestor changed before read"))
            continue
        try:
            raw = _bounded_descriptor_read(
                candidate,
                metadata,
                config.analysis.max_file_bytes,
                root=resolved_root,
            )
        except _UnsafeRead as error:
            skipped.append(SkippedInput(path=safe_path, reason=error.reason))
            warnings.append(
                WarningRecord(code="input-read-failed", message=f"Unable to analyze {safe_path}")
            )
            continue
        if not _directory_chain_is_stable(resolved_root, candidate_record.ancestors):
            skipped.append(SkippedInput(path=safe_path, reason="ancestor changed during read"))
            continue
        if b"\x00" in raw:
            skipped.append(SkippedInput(path=safe_path, reason="binary content is not analyzed"))
            continue
        try:
            text, encoding = _decode(candidate, raw)
        except (LookupError, SyntaxError, UnicodeDecodeError):
            skipped.append(
                SkippedInput(path=safe_path, reason="unsupported or invalid text encoding")
            )
            warnings.append(
                WarningRecord(
                    code="input-decoding-failed",
                    message=f"Unable to decode eligible text file: {safe_path}",
                )
            )
            continue
        if _has_generated_marker(text):
            skipped.append(SkippedInput(path=safe_path, reason="recognized generated file"))
            limitations.append(
                Limitation(
                    code="generated-excluded",
                    message=f"Recognized generated file was not analyzed: {safe_path}",
                )
            )
            continue
        roles = _classify(safe_path)
        records.append(
            FileRecord(
                path=safe_path,
                size_bytes=len(raw),
                roles=roles,
                text=text,
                encoding=encoding,
                line_count=len(text.splitlines()),
            )
        )
        source_bytes += len(raw)

    records.sort(key=lambda item: item.path)
    skipped.sort(key=lambda item: (item.path, item.reason))
    python_records = [
        item
        for item in records
        if FileRole.PYTHON_SOURCE in item.roles or FileRole.PYTHON_TEST in item.roles
    ]
    summary = RepositoryInventory(
        total_files=len(records),
        python_files=len(python_records),
        test_files=sum(FileRole.PYTHON_TEST in item.roles for item in records),
        total_bytes=sum(item.size_bytes for item in records),
        source_bytes=source_bytes,
        python_lines=sum(item.line_count for item in python_records),
    )
    if root_unreadable:
        completeness = Completeness.UNAVAILABLE
    elif skipped or limitations or timed_out:
        completeness = Completeness.PARTIAL
    else:
        completeness = Completeness.AVAILABLE
    return InventoryResult(
        root=resolved_root,
        files=tuple(records),
        summary=summary,
        skipped_inputs=tuple(skipped),
        warnings=tuple(warnings),
        limitations=tuple(limitations),
        completeness=completeness,
    )


class _UnsafeRead(Exception):
    def __init__(self, reason: str) -> None:
        self.reason = reason


def _safe_child_path(parent: str, name: str) -> str:
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError("Entry name is not safe")
    return f"{parent}/{name}" if parent else name


def _directory_is_stable(
    root: Path,
    directory: Path,
    expected: os.stat_result,
) -> bool:
    try:
        current = os.lstat(directory)
        resolved = directory.resolve(strict=True)
    except OSError:
        return False
    attributes = getattr(current, "st_file_attributes", 0)
    return (
        _same_identity(expected, current)
        and stat_module.S_ISDIR(current.st_mode)
        and not stat_module.S_ISLNK(current.st_mode)
        and not bool(attributes & 0x400)
        and (directory == root or not os.path.ismount(directory))
        and _path_is_contained(root, resolved)
    )


def _directory_chain_is_stable(
    root: Path,
    ancestors: tuple[tuple[Path, os.stat_result], ...],
) -> bool:
    return all(_directory_is_stable(root, path, metadata) for path, metadata in ancestors)


def _path_is_contained(root: Path, candidate: Path) -> bool:
    try:
        candidate.relative_to(root)
    except ValueError:
        return False
    return True


def _load_directory_ignore(
    root: Path,
    directory_safe_path: str,
    path: Path,
    metadata: os.stat_result,
    maximum: int,
    specs: dict[str, GitIgnoreSpec],
    warnings: list[WarningRecord],
    limitations: list[Limitation],
) -> None:
    safe_path = _safe_child_path(directory_safe_path, ".gitignore")
    if (
        _is_reparse_or_linklike(path, metadata)
        or not stat_module.S_ISREG(metadata.st_mode)
        or metadata.st_size > maximum
    ):
        return
    try:
        raw = _bounded_descriptor_read(path, metadata, maximum, root=root)
        text = raw.decode("utf-8-sig", errors="strict")
        spec = GitIgnoreSpec.from_lines(text.splitlines())
    except (_UnsafeRead, UnicodeDecodeError, GitIgnorePatternError, TypeError, ValueError):
        warnings.append(
            WarningRecord(
                code="invalid-ignore-pattern",
                message=f"Unable to apply ignore rules from {safe_path}",
            )
        )
        limitations.append(
            Limitation(
                code="invalid-ignore-pattern",
                message=f"Invalid repository ignore rules were not applied: {safe_path}",
            )
        )
        return
    specs[directory_safe_path] = spec


def _safe_entry_path(root: Path, candidate: Path) -> str:
    parent = candidate.parent
    prefix = "" if parent == root else normalize_relative_path(root, parent)
    name = candidate.name
    if not name or name in {".", ".."} or "/" in name or "\\" in name:
        raise ValueError("Entry name is not safe")
    return f"{prefix}/{name}" if prefix else name


def _is_reparse_or_linklike(path: Path, metadata: os.stat_result) -> bool:
    attributes = getattr(metadata, "st_file_attributes", 0)
    return (
        stat_module.S_ISLNK(metadata.st_mode)
        or bool(attributes & 0x400)
        or (stat_module.S_ISREG(metadata.st_mode) and metadata.st_nlink > 1)
        or os.path.ismount(path)
    )


def _bounded_descriptor_read(
    path: Path,
    before: os.stat_result,
    maximum: int,
    *,
    root: Path | None = None,
) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        opened_descriptor = _open_descriptor(path, flags, root=root)
    except OSError:
        raise _UnsafeRead("file is unreadable") from None
    descriptor = opened_descriptor.descriptor
    try:
        opened = os.fstat(descriptor)
        if not stat_module.S_ISREG(opened.st_mode) or not _same_identity(before, opened):
            raise _UnsafeRead("file changed before bounded read")
        if root is not None and not _opened_handle_is_contained(
            descriptor,
            root,
            atomic_beneath=opened_descriptor.atomic_beneath,
        ):
            raise _UnsafeRead("opened file is outside repository")
        chunks: list[bytes] = []
        remaining = maximum + 1
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        after = os.fstat(descriptor)
        if not _same_identity(opened, after) or opened.st_size != after.st_size:
            raise _UnsafeRead("file changed during bounded read")
        raw = b"".join(chunks)
        if len(raw) > maximum:
            raise _UnsafeRead(f"file exceeds {maximum}-byte limit")
        return raw
    except OSError:
        raise _UnsafeRead("file is unreadable") from None
    finally:
        os.close(descriptor)


def _open_descriptor(path: Path, flags: int, *, root: Path | None) -> _OpenedDescriptor:
    supports_relative_open = (
        root is not None
        and os.open in os.supports_dir_fd
        and bool(getattr(os, "O_DIRECTORY", 0))
        and bool(getattr(os, "O_NOFOLLOW", 0))
    )
    if not supports_relative_open or root is None:
        return _OpenedDescriptor(os.open(path, flags), False)
    try:
        relative = path.relative_to(root)
    except ValueError:
        raise OSError("path is outside repository") from None
    directory_flags = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptors: list[int] = []
    try:
        current = os.open(root, directory_flags)
        descriptors.append(current)
        for part in relative.parts[:-1]:
            current = os.open(part, directory_flags, dir_fd=current)
            descriptors.append(current)
        return _OpenedDescriptor(os.open(relative.name, flags, dir_fd=current), True)
    finally:
        for directory_descriptor in reversed(descriptors):
            os.close(directory_descriptor)


def _opened_handle_is_contained(
    descriptor: int,
    root: Path,
    *,
    atomic_beneath: bool,
) -> bool:
    final_path = _final_handle_path(descriptor)
    if not _WINDOWS_PLATFORM and atomic_beneath and final_path is None:
        return True
    if final_path is None:
        return False
    canonical_root = Path(os.path.abspath(root))
    canonical_final = Path(os.path.abspath(final_path))
    return _path_is_contained(canonical_root, canonical_final)


def _final_handle_path(descriptor: int) -> Path | None:
    if _WINDOWS_PLATFORM:
        import ctypes
        import importlib

        try:
            msvcrt = importlib.import_module("msvcrt")
            handle = msvcrt.get_osfhandle(descriptor)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            get_final_path = kernel32.GetFinalPathNameByHandleW
            buffer = ctypes.create_unicode_buffer(32_768)
            length = get_final_path(handle, buffer, len(buffer), 0)
        except (AttributeError, OSError, ValueError):
            return None
        if length <= 0 or length >= len(buffer):
            return None
        value = buffer.value
        if value.startswith("\\\\?\\UNC\\"):
            value = "\\\\" + value[8:]
        elif value.startswith("\\\\?\\"):
            value = value[4:]
        return Path(value)
    proc_path = Path(f"/proc/self/fd/{descriptor}")
    try:
        return proc_path.resolve(strict=True)
    except OSError:
        return None


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (
        left.st_dev,
        left.st_ino,
        stat_module.S_IFMT(left.st_mode),
    ) == (
        right.st_dev,
        right.st_ino,
        stat_module.S_IFMT(right.st_mode),
    )


def _decode(path: Path, raw: bytes) -> tuple[str, str]:
    if path.suffix.casefold() == ".py":
        encoding, _ = tokenize.detect_encoding(io.BytesIO(raw).readline)
        return raw.decode(encoding, errors="strict"), encoding.casefold()
    encoding = "utf-8-sig" if raw.startswith(codecs.BOM_UTF8) else "utf-8"
    return raw.decode(encoding, errors="strict"), encoding


def _is_ignored(
    safe_path: str,
    specs: dict[str, GitIgnoreSpec],
    configured: GitIgnoreSpec,
    respect_gitignore: bool,
) -> bool:
    parts = safe_path.split("/")
    for end in range(1, len(parts)):
        directory = "/".join(parts[:end]) + "/"
        if respect_gitignore and _gitignore_decision(directory, specs):
            return True
        if configured.match_file(directory):
            return True
    ignored = _gitignore_decision(safe_path, specs) if respect_gitignore else False
    return ignored or configured.match_file(safe_path)


def _gitignore_decision(safe_path: str, specs: dict[str, GitIgnoreSpec]) -> bool:
    ignored = False
    parts = safe_path.rstrip("/").split("/")[:-1]
    bases = [""] + ["/".join(parts[:index]) for index in range(1, len(parts) + 1)]
    for base in bases:
        spec = specs.get(base)
        if spec is None:
            continue
        relative = safe_path if not base else safe_path[len(base) + 1 :]
        decision = spec.check_file(relative).include
        if decision is not None:
            ignored = decision
    return ignored


def _has_generated_marker(text: str) -> bool:
    for line in text.splitlines()[:5]:
        lowered = line.strip().casefold()
        if ("do not edit" in lowered and "generated" in lowered) or lowered.startswith(
            ("# @generated", "// @generated", "// code generated by")
        ):
            return True
    return False


def _classify(path: str) -> frozenset[FileRole]:
    pure = path.casefold()
    name = pure.rsplit("/", 1)[-1]
    parts = pure.split("/")
    roles: set[FileRole] = set()
    if name.endswith(".py"):
        if (
            "tests" in parts
            or "test" in parts
            or name.startswith("test_")
            or name.endswith("_test.py")
        ):
            roles.add(FileRole.PYTHON_TEST)
        else:
            roles.add(FileRole.PYTHON_SOURCE)
    if len(parts) == 1 and name.startswith("readme"):
        roles.add(FileRole.README)
    if "docs" in parts or (name.endswith((".md", ".rst")) and len(parts) > 1):
        roles.add(FileRole.DOCUMENTATION)
    if name.startswith("contributing"):
        roles.add(FileRole.CONTRIBUTION_GUIDE)
    if name.startswith(("changelog", "changes", "release-notes", "release_notes")):
        roles.add(FileRole.CHANGELOG)
    if "examples" in parts or "example" in parts:
        roles.add(FileRole.EXAMPLE)
    if name in _DEPENDENCY_NAMES or name.startswith("requirements"):
        roles.add(FileRole.DEPENDENCY)
    if name in _PACKAGING_NAMES:
        roles.add(FileRole.PACKAGING)
    if (".github" in parts and "workflows" in parts) or name in {".travis.yml", "appveyor.yml"}:
        roles.add(FileRole.CI)
    if name == "dockerfile" or name.startswith("dockerfile."):
        roles.add(FileRole.DOCKERFILE)
    if name == ".dockerignore":
        roles.add(FileRole.DOCKER_IGNORE)
    if name.startswith(("license", "licence", "copying")):
        roles.add(FileRole.LICENSE)
    if name in {".gitignore", ".dockerignore", ".ignore"}:
        roles.add(FileRole.IGNORE)
    if "issue_template" in parts:
        roles.add(FileRole.ISSUE_TEMPLATE)
    if "pull_request_template" in pure:
        roles.add(FileRole.PULL_REQUEST_TEMPLATE)
    if name.startswith("code_of_conduct") or name.startswith("code-of-conduct"):
        roles.add(FileRole.CODE_OF_CONDUCT)
    if name.startswith("security"):
        roles.add(FileRole.SECURITY_POLICY)
    if not roles:
        roles.add(FileRole.OTHER_TEXT)
    return frozenset(roles)


__all__ = ["FileRecord", "FileRole", "InventoryResult", "build_inventory"]
