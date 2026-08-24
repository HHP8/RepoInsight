"""Safe Python AST index."""

from __future__ import annotations

import ast
from dataclasses import dataclass

from .inventory import FileRecord, FileRole, InventoryResult
from .models import Completeness, Location, SkippedInput, WarningRecord


@dataclass(frozen=True)
class ParsedPythonFile:
    file: FileRecord
    tree: ast.Module
    source_lines: tuple[str, ...]


@dataclass(frozen=True)
class PythonIndex:
    files: tuple[ParsedPythonFile, ...]
    warnings: tuple[WarningRecord, ...]
    skipped_inputs: tuple[SkippedInput, ...]
    completeness: Completeness


def build_python_index(inventory: InventoryResult) -> PythonIndex:
    """Parse inventory-held Python text into immutable AST records."""
    parsed: list[ParsedPythonFile] = []
    warnings = list(inventory.warnings)
    skipped = list(inventory.skipped_inputs)
    python_records = [
        item
        for item in inventory.files
        if FileRole.PYTHON_SOURCE in item.roles or FileRole.PYTHON_TEST in item.roles
    ]
    syntax_failures = 0
    for file in sorted(python_records, key=lambda item: item.path):
        try:
            tree = ast.parse(file.text, filename=file.path, type_comments=True)
        except (SyntaxError, ValueError, TypeError, MemoryError) as error:
            syntax_failures += 1
            line = error.lineno if isinstance(error, SyntaxError) and error.lineno else 1
            column = (
                max(error.offset - 1, 0)
                if isinstance(error, SyntaxError) and error.offset is not None
                else None
            )
            warnings.append(
                WarningRecord(
                    code="python-syntax-error",
                    message=f"Python syntax error in {file.path} at line {line}",
                    location=Location(path=file.path, start_line=line, start_column=column),
                )
            )
            skipped.append(SkippedInput(path=file.path, reason="Python syntax error"))
            continue
        parsed.append(
            ParsedPythonFile(
                file=file,
                tree=tree,
                source_lines=tuple(file.text.splitlines(keepends=True)),
            )
        )

    completeness: Completeness
    if inventory.completeness in {Completeness.UNAVAILABLE, Completeness.SKIPPED}:
        completeness = inventory.completeness
    elif python_records and not parsed:
        completeness = Completeness.UNAVAILABLE
    elif syntax_failures or inventory.completeness is Completeness.PARTIAL:
        completeness = Completeness.PARTIAL
    elif not python_records:
        completeness = Completeness.UNAVAILABLE
    else:
        completeness = Completeness.AVAILABLE
    return PythonIndex(
        files=tuple(parsed),
        warnings=tuple(warnings),
        skipped_inputs=tuple(sorted(skipped, key=lambda item: (item.path, item.reason))),
        completeness=completeness,
    )


__all__ = ["ParsedPythonFile", "PythonIndex", "build_python_index"]
