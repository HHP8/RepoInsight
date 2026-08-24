"""Security-hygiene analyzer."""

from __future__ import annotations

import ast
import configparser
import re
import tomllib
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import cast

from ..inventory import FileRecord, FileRole
from ..models import AnalyzerMetadata, AnalyzerResult, Category, Completeness, Location
from ..python_index import ParsedPythonFile
from ._shared import (
    is_rule_enabled,
    make_finding,
    make_limitation,
    make_location,
    make_metric,
    make_result,
    module_aliases,
    qualified_call_name,
    qualified_expr_name,
)
from .base import AnalysisContext, Applicability

_PRIVATE_KEY = re.compile(
    r"-----BEGIN(?: [A-Z0-9]+)? PRIVATE KEY-----.*?"
    r"-----END(?: [A-Z0-9]+)? PRIVATE KEY-----",
    re.DOTALL,
)
_GITHUB_TOKEN = re.compile(r"(?<![A-Za-z0-9])gh[pousr]_[A-Za-z0-9]{20,}(?![A-Za-z0-9])")
_OPENAI_TOKEN = re.compile(r"(?<![A-Za-z0-9])sk-(?:proj-)?[A-Za-z0-9_-]{16,}(?![A-Za-z0-9])")
_AWS_KEY = re.compile(r"(?<![A-Z0-9])AKIA[A-Z0-9]{16}(?![A-Z0-9])")
_NAMED_SECRET = re.compile(
    r"(?i)\b(?:api[_-]?key|access[_-]?key(?:_id)?|secret(?:[_-]?key)?|"
    r"password|passwd|token|authorization|github[_-]?token|openai[_-]?token|aws[_-]?key)"
    r"\b\s*[:=]\s*(?P<quote>[\"']?)(?P<value>[A-Za-z0-9_./+=:@-]{12,})(?P=quote)"
)
_PLACEHOLDER_WORDS = (
    "changeme",
    "change-me",
    "example",
    "placeholder",
    "your-",
    "your_",
    "dummy",
    "sample",
    "not-a-secret",
    "${",
    "{{",
)
_SUBPROCESS_APIS = frozenset(
    {
        "subprocess.run",
        "subprocess.Popen",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
    }
)
_DYNAMIC_CALLS = frozenset(
    {"eval", "exec", "compile", "builtins.eval", "builtins.exec", "builtins.compile"}
)
_UNSAFE_DESERIALIZATION = frozenset(
    {
        "pickle.load",
        "pickle.loads",
        "marshal.load",
        "marshal.loads",
        "shelve.load",
        "shelve.loads",
    }
)
_LOCK_NAMES = frozenset({"poetry.lock", "pdm.lock", "uv.lock", "pipfile.lock"})
_DEV_REQUIREMENTS = re.compile(r"requirements[-_.](?:dev|test|tests|docs|lint|build)", re.I)
_PACKAGE_NAME = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9_.-]*)")
_EXACT_PIN = re.compile(r"(?<![<>=!~])==(?!=)\s*[^\s;,]+")


@dataclass(frozen=True)
class _SecretMatch:
    file: FileRecord
    family: str
    start: int
    end: int


def _overlaps(start: int, end: int, spans: Iterable[tuple[int, int]]) -> bool:
    return any(
        start < existing_end and existing_start < end for existing_start, existing_end in spans
    )


def _named_value_is_secret(value: str) -> bool:
    folded = value.casefold()
    if len(value) < 16 or any(word in folded for word in _PLACEHOLDER_WORDS):
        return False
    return any(character.isalpha() for character in value) and any(
        character.isdigit() for character in value
    )


def _secret_matches(files: tuple[FileRecord, ...]) -> tuple[_SecretMatch, ...]:
    matches: list[_SecretMatch] = []
    high_patterns = (
        ("PEM private key", _PRIVATE_KEY),
        ("GitHub token", _GITHUB_TOKEN),
        ("OpenAI token", _OPENAI_TOKEN),
        ("AWS access key", _AWS_KEY),
    )
    for file in sorted(files, key=lambda item: item.path):
        accepted: list[tuple[int, int]] = []
        file_matches: list[_SecretMatch] = []
        high_candidates = sorted(
            (
                (match.start(), match.end(), family)
                for family, pattern in high_patterns
                for match in pattern.finditer(file.text)
            ),
            key=lambda item: (item[0], item[1], item[2]),
        )
        for start, end, family in high_candidates:
            if _overlaps(start, end, accepted):
                continue
            accepted.append((start, end))
            file_matches.append(_SecretMatch(file, family, start, end))
        for match in _NAMED_SECRET.finditer(file.text):
            start, end = match.span("value")
            if _overlaps(start, end, accepted) or not _named_value_is_secret(match.group("value")):
                continue
            accepted.append((start, end))
            file_matches.append(_SecretMatch(file, "named secret assignment", start, end))
        matches.extend(sorted(file_matches, key=lambda item: (item.start, item.end, item.family)))
    return tuple(matches)


def _secret_location(match: _SecretMatch) -> Location:
    line = match.file.text.count("\n", 0, match.start) + 1
    previous_newline = match.file.text.rfind("\n", 0, match.start)
    column = match.start if previous_newline < 0 else match.start - previous_newline - 1
    end_line = match.file.text.count("\n", 0, match.end) + 1
    return Location(
        path=match.file.path,
        start_line=line,
        end_line=end_line,
        start_column=column,
    )


def _calls(
    parsed_files: tuple[ParsedPythonFile, ...],
) -> tuple[tuple[ParsedPythonFile, ast.Call, str, Mapping[str, str]], ...]:
    records: list[tuple[ParsedPythonFile, ast.Call, str, Mapping[str, str]]] = []
    for parsed in parsed_files:
        aliases = module_aliases(parsed.tree)
        for call in ast.walk(parsed.tree):
            if not isinstance(call, ast.Call):
                continue
            qualified = qualified_call_name(call, aliases)
            if qualified is not None:
                records.append((parsed, call, qualified, aliases))
    return tuple(
        sorted(records, key=lambda item: (item[0].file.path, item[1].lineno, item[1].col_offset))
    )


def _keyword(call: ast.Call, name: str) -> ast.expr | None:
    return next((keyword.value for keyword in call.keywords if keyword.arg == name), None)


def _literal_false(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _literal_true(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and node.value is True


def _literal_string(node: ast.expr | None) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _yaml_loader_is_safe(call: ast.Call, aliases: Mapping[str, str]) -> bool:
    loader = _keyword(call, "Loader")
    if loader is None and len(call.args) >= 2:
        loader = call.args[1]
    if loader is None:
        return False
    name = qualified_expr_name(loader, aliases)
    return bool(name and name.rsplit(".", 1)[-1] in {"SafeLoader", "CSafeLoader"})


def _predictable_temp_join(node: ast.expr, aliases: Mapping[str, str]) -> bool:
    if not isinstance(node, ast.Call) or qualified_call_name(node, aliases) != "os.path.join":
        return False
    if len(node.args) < 2 or not isinstance(node.args[0], ast.Call):
        return False
    if qualified_call_name(node.args[0], aliases) != "tempfile.gettempdir":
        return False
    filename = node.args[1]
    return (
        isinstance(filename, ast.Constant)
        and isinstance(filename.value, str)
        and bool(filename.value)
        and "/" not in filename.value
        and "\\" not in filename.value
    )


def _predictable_temp_uses(
    parsed: ParsedPythonFile, aliases: Mapping[str, str]
) -> tuple[ast.Call, ...]:
    names: set[str] = set()
    for node in ast.walk(parsed.tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if isinstance(value, ast.expr) and _predictable_temp_join(value, aliases):
                names.update(target.id for target in targets if isinstance(target, ast.Name))
    uses: list[ast.Call] = []
    for call in ast.walk(parsed.tree):
        if not isinstance(call, ast.Call):
            continue
        qualified = qualified_call_name(call, aliases)
        if qualified not in {"open", "builtins.open", "os.open"} or not call.args:
            continue
        first = call.args[0]
        if (isinstance(first, ast.Name) and first.id in names) or _predictable_temp_join(
            first, aliases
        ):
            uses.append(call)
    return tuple(sorted(uses, key=lambda call: (call.lineno, call.col_offset)))


def _mapping(value: object) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping) or not all(isinstance(key, str) for key in value):
        return None
    return cast(Mapping[str, object], value)


def _nested_mapping(value: object, *keys: str) -> Mapping[str, object] | None:
    current = _mapping(value)
    for key in keys:
        if current is None:
            return None
        current = _mapping(current.get(key))
    return current


def _dependency_lines(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    return tuple(item.strip() for item in value if isinstance(item, str) and item.strip())


def _pyproject_dependencies(file: FileRecord) -> tuple[str, ...]:
    try:
        loaded = tomllib.loads(file.text)
    except tomllib.TOMLDecodeError:
        return ()
    dependencies: list[str] = []
    project = _nested_mapping(loaded, "project")
    if project is not None:
        dependencies.extend(_dependency_lines(project.get("dependencies")))
    poetry = _nested_mapping(loaded, "tool", "poetry", "dependencies")
    if poetry is not None:
        for name, raw in poetry.items():
            if name.casefold() == "python":
                continue
            constraint: object = raw
            if isinstance(raw, Mapping):
                constraint = raw.get("version")
            if isinstance(constraint, str):
                stripped = constraint.strip()
                if re.fullmatch(r"\d+(?:\.\d+)*(?:[A-Za-z0-9_.+-]*)?", stripped):
                    dependencies.append(f"{name}=={stripped}")
                else:
                    dependencies.append(f"{name}{stripped}")
    return tuple(dependencies)


def _ini_dependencies(file: FileRecord, section: str, option: str) -> tuple[str, ...]:
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    try:
        parser.read_string(file.text)
    except configparser.Error:
        return ()
    raw = parser.get(section, option, fallback="")
    return tuple(line.strip() for line in raw.splitlines() if line.strip())


def _pipfile_dependencies(file: FileRecord) -> tuple[str, ...]:
    try:
        loaded = tomllib.loads(file.text)
    except tomllib.TOMLDecodeError:
        return ()
    packages = _nested_mapping(loaded, "packages")
    if packages is None:
        return ()
    dependencies: list[str] = []
    for name, raw in packages.items():
        if isinstance(raw, str):
            dependencies.append(f"{name}{raw}" if raw != "*" else name)
        elif isinstance(raw, Mapping):
            version = raw.get("version")
            dependencies.append(f"{name}{version}" if isinstance(version, str) else name)
        else:
            dependencies.append(name)
    return tuple(dependencies)


def _setup_py_dependencies(parsed: ParsedPythonFile) -> tuple[str, ...]:
    aliases = module_aliases(parsed.tree)
    for node in ast.walk(parsed.tree):
        if not isinstance(node, ast.Call):
            continue
        name = qualified_call_name(node, aliases)
        if name not in {"setup", "setuptools.setup", "distutils.core.setup"}:
            continue
        value = _keyword(node, "install_requires")
        if not isinstance(value, (ast.List, ast.Tuple)):
            continue
        return tuple(
            element.value.strip()
            for element in value.elts
            if isinstance(element, ast.Constant)
            and isinstance(element.value, str)
            and element.value.strip()
        )
    return ()


def _runtime_manifests(
    context: AnalysisContext,
) -> tuple[tuple[FileRecord, tuple[str, ...]], ...]:
    parsed_by_path = {parsed.file.path.casefold(): parsed for parsed in context.python_index.files}
    manifests: list[tuple[FileRecord, tuple[str, ...]]] = []
    for file in context.inventory.files:
        name = file.path.casefold().rsplit("/", 1)[-1]
        dependencies: tuple[str, ...] = ()
        if name.startswith("requirements") and name.endswith((".txt", ".in")):
            if _DEV_REQUIREMENTS.search(name):
                continue
            dependencies = tuple(
                line.strip()
                for line in file.text.splitlines()
                if line.strip() and not line.lstrip().startswith(("#", "-"))
            )
        elif name == "pyproject.toml":
            dependencies = _pyproject_dependencies(file)
        elif name == "pipfile":
            dependencies = _pipfile_dependencies(file)
        elif name == "setup.cfg":
            dependencies = _ini_dependencies(file, "options", "install_requires")
        elif name == "setup.py" and file.path.casefold() in parsed_by_path:
            dependencies = _setup_py_dependencies(parsed_by_path[file.path.casefold()])
        if dependencies:
            manifests.append((file, dependencies))
    return tuple(sorted(manifests, key=lambda item: item[0].path))


def _dependency_name(requirement: str) -> str | None:
    match = _PACKAGE_NAME.match(requirement)
    return match.group(1).casefold().replace("_", "-") if match is not None else None


def _is_exact_pin(requirement: str) -> bool:
    return _EXACT_PIN.search(requirement) is not None


def _constraint_pins(files: tuple[FileRecord, ...]) -> set[str]:
    pins: set[str] = set()
    for file in files:
        if file.path.casefold().rsplit("/", 1)[-1] != "constraints.txt":
            continue
        for line in file.text.splitlines():
            if _is_exact_pin(line) and (name := _dependency_name(line)) is not None:
                pins.add(name)
    return pins


def _unpinned_manifests(context: AnalysisContext) -> tuple[FileRecord, ...]:
    files = context.inventory.files
    if any(file.path.casefold().rsplit("/", 1)[-1] in _LOCK_NAMES for file in files):
        return ()
    constraints = _constraint_pins(files)
    unpinned: list[FileRecord] = []
    for file, dependencies in _runtime_manifests(context):
        missing = [
            requirement
            for requirement in dependencies
            if not _is_exact_pin(requirement) and _dependency_name(requirement) not in constraints
        ]
        if missing:
            unpinned.append(file)
    return tuple(unpinned)


def _client_variables(parsed: ParsedPythonFile, aliases: Mapping[str, str]) -> set[str]:
    clients: set[str] = set()
    for node in ast.walk(parsed.tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)) or not isinstance(
            node.value, ast.Call
        ):
            continue
        constructor = qualified_call_name(node.value, aliases)
        if constructor not in {"requests.Session", "httpx.Client", "httpx.AsyncClient"}:
            continue
        targets = node.targets if isinstance(node, ast.Assign) else [node.target]
        clients.update(target.id for target in targets if isinstance(target, ast.Name))
    return clients


class SecurityAnalyzer:
    metadata = AnalyzerMetadata(
        id="security-hygiene",
        version="1.0.0",
        category=Category.SECURITY_HYGIENE,
        rule_ids=tuple(f"RI-SEC-{index:03}" for index in range(1, 8)),
        capabilities=("inventory", "python-ast", "static-manifest-text", "redaction"),
    )

    def applies(self, context: AnalysisContext) -> Applicability:
        has_python = any(
            FileRole.PYTHON_SOURCE in file.roles or FileRole.PYTHON_TEST in file.roles
            for file in context.inventory.files
        )
        has_manifest = any(FileRole.DEPENDENCY in file.roles for file in context.inventory.files)
        if not has_python and not has_manifest:
            return Applicability(
                False,
                Completeness.UNAVAILABLE,
                ("No retained Python or dependency-manifest evidence is available",),
            )
        if context.inventory.completeness in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }:
            return Applicability(
                True,
                Completeness.UNAVAILABLE,
                ("Relevant repository inventory evidence is unavailable",),
            )
        if context.inventory.completeness is Completeness.PARTIAL or (
            has_python
            and context.python_index.completeness
            in {Completeness.PARTIAL, Completeness.UNAVAILABLE, Completeness.SKIPPED}
        ):
            return Applicability(
                True,
                Completeness.PARTIAL,
                ("Relevant inventory or Python AST evidence is incomplete",),
            )
        return Applicability(True, Completeness.AVAILABLE)

    def analyze(self, context: AnalysisContext) -> AnalyzerResult:
        applicability = self.applies(context)
        inventory_available = context.inventory.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        parsed_files = context.python_index.files
        ast_available = bool(parsed_files) and context.python_index.completeness not in {
            Completeness.UNAVAILABLE,
            Completeness.SKIPPED,
        }
        calls = _calls(parsed_files) if ast_available else ()
        secret_matches = _secret_matches(context.inventory.files) if inventory_available else ()
        unpinned_manifests = _unpinned_manifests(context) if inventory_available else ()

        dynamic = [record for record in calls if record[2] in _DYNAMIC_CALLS]
        shell_patterns: list[tuple[ParsedPythonFile, ast.Call, str]] = []
        unsafe_deserialization: list[tuple[ParsedPythonFile, ast.Call, str]] = []
        risky_temp: list[tuple[ParsedPythonFile, ast.Call, str]] = []
        tls_disabled: list[tuple[ParsedPythonFile, ast.Call, str]] = []
        predictable_seen: set[tuple[str, int, int]] = set()
        clients_by_path = {
            parsed.file.path: _client_variables(parsed, module_aliases(parsed.tree))
            for parsed in parsed_files
        }
        for parsed, call, qualified, aliases in calls:
            if qualified in {"os.system", "os.popen"}:
                shell_patterns.append((parsed, call, f"shell execution pattern: {qualified}"))
            elif qualified in _SUBPROCESS_APIS:
                if _literal_true(_keyword(call, "shell")):
                    shell_patterns.append(
                        (parsed, call, f"subprocess call with literal shell=True: {qualified}")
                    )
                else:
                    command = call.args[0] if call.args else _keyword(call, "args")
                    if _literal_string(command):
                        shell_patterns.append(
                            (parsed, call, f"literal string subprocess command: {qualified}")
                        )

            if qualified in _UNSAFE_DESERIALIZATION:
                unsafe_deserialization.append(
                    (parsed, call, f"unsafe deserialization call: {qualified}")
                )
            elif qualified == "yaml.load" and not _yaml_loader_is_safe(call, aliases):
                unsafe_deserialization.append(
                    (parsed, call, "yaml.load without an explicit SafeLoader or CSafeLoader")
                )

            if qualified == "tempfile.mktemp":
                risky_temp.append((parsed, call, "risky temporary-file call: tempfile.mktemp"))

            verify_false = _literal_false(_keyword(call, "verify"))
            is_http_client = qualified.startswith(("requests.", "httpx.")) or (
                "." in qualified
                and qualified.split(".", 1)[0] in clients_by_path.get(parsed.file.path, set())
            )
            if verify_false and is_http_client:
                tls_disabled.append((parsed, call, f"TLS verification disabled in {qualified}"))
            cert_reqs = _keyword(call, "cert_reqs")
            if (
                qualified.startswith("urllib3.")
                and isinstance(cert_reqs, ast.Constant)
                and cert_reqs.value == "CERT_NONE"
            ):
                tls_disabled.append((parsed, call, "urllib3 cert_reqs is literal CERT_NONE"))

        for parsed in parsed_files:
            aliases = module_aliases(parsed.tree)
            for call in _predictable_temp_uses(parsed, aliases):
                identity = (parsed.file.path, call.lineno, call.col_offset)
                if identity in predictable_seen:
                    continue
                predictable_seen.add(identity)
                risky_temp.append(
                    (
                        parsed,
                        call,
                        "predictable filename under tempfile.gettempdir used by open",
                    )
                )
        for records in (shell_patterns, unsafe_deserialization, risky_temp, tls_disabled):
            records.sort(key=lambda item: (item[0].file.path, item[1].lineno, item[1].col_offset))

        findings = []
        if inventory_available and is_rule_enabled(context.config, "RI-SEC-001"):
            for match in secret_matches:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-SEC-001",
                        location=_secret_location(match),
                        evidence=f"family: {match.family}; value: [REDACTED]",
                        explanation_detail="This is a possible secret, not a verified credential.",
                    )
                )
        if ast_available and is_rule_enabled(context.config, "RI-SEC-002"):
            for parsed, call, qualified, _ in dynamic:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-SEC-002",
                        location=make_location(parsed, call),
                        evidence=f"dynamic execution call: {qualified}",
                    )
                )
        for rule_id, records in (
            ("RI-SEC-003", shell_patterns),
            ("RI-SEC-004", unsafe_deserialization),
            ("RI-SEC-005", risky_temp),
            ("RI-SEC-007", tls_disabled),
        ):
            if ast_available and is_rule_enabled(context.config, rule_id):
                for parsed, call, evidence in records:
                    findings.append(
                        make_finding(
                            self.metadata,
                            rule_id,
                            location=make_location(parsed, call),
                            evidence=evidence,
                        )
                    )
        if inventory_available and is_rule_enabled(context.config, "RI-SEC-006"):
            for file in unpinned_manifests:
                findings.append(
                    make_finding(
                        self.metadata,
                        "RI-SEC-006",
                        location=Location(path=file.path, start_line=1),
                        evidence=f"runtime manifest has unpinned declarations: {file.path}",
                    )
                )

        inventory_completeness = context.inventory.completeness
        inventory_limitations = (
            ("Relevant repository inventory evidence is incomplete",)
            if inventory_completeness is Completeness.PARTIAL
            else ()
        )
        if ast_available:
            ast_completeness = context.python_index.completeness
            ast_limitations = (
                ("Python AST evidence is incomplete",)
                if ast_completeness is Completeness.PARTIAL
                else ()
            )
        else:
            ast_completeness = Completeness.UNAVAILABLE
            ast_limitations = ("No parsed Python AST evidence is available",)
        metrics = [
            make_metric(
                self.metadata,
                "security.possible_secret_count",
                len(secret_matches) if inventory_available else None,
                unit="count",
                provenance="High-specificity patterns over retained repository text",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
            make_metric(
                self.metadata,
                "security.unpinned_runtime_manifests",
                len(unpinned_manifests) if inventory_available else None,
                unit="count",
                provenance="Static runtime dependency declarations and compensating lock evidence",
                completeness=inventory_completeness,
                limitations=inventory_limitations,
            ),
        ]
        ast_metric_values = {
            "security.dynamic_execution_calls": len(dynamic),
            "security.unsafe_subprocess_calls": len(shell_patterns),
            "security.unsafe_deserialization_calls": len(unsafe_deserialization),
            "security.risky_tempfile_patterns": len(risky_temp),
            "security.tls_verification_disabled_calls": len(tls_disabled),
        }
        metrics.extend(
            make_metric(
                self.metadata,
                metric_id,
                value if ast_available else None,
                unit="count",
                provenance="Resolved calls in retained Python AST evidence",
                completeness=ast_completeness,
                limitations=ast_limitations,
            )
            for metric_id, value in ast_metric_values.items()
        )
        limitations = tuple(
            make_limitation(self.metadata, "security-evidence", message)
            for message in applicability.limitations
        )
        return make_result(
            self.metadata,
            applicability.completeness,
            metrics=metrics,
            findings=findings,
            limitations=limitations,
        )


ANALYZER = SecurityAnalyzer()

__all__ = ["ANALYZER", "SecurityAnalyzer"]
