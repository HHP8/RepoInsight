from __future__ import annotations

from collections.abc import Callable

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.catalog import RULE_CATALOG
from repoinsight.analyzers.security import ANALYZER
from repoinsight.models import AnalyzerResult, Completeness, Finding, Metric

ContextFactory = Callable[..., AnalysisContext]


def _findings(result: AnalyzerResult, rule_id: str) -> list[Finding]:
    return [finding for finding in result.findings if finding.rule_id == rule_id]


def _metrics(result: AnalyzerResult) -> dict[str, Metric]:
    return {metric.id: metric for metric in result.metrics}


def test_dynamic_execution_resolves_direct_module_and_from_alias_calls(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "dynamic.py": (
                    "import builtins as bi\n"
                    "from builtins import eval as dynamic\n"
                    "eval('1')\n"
                    "exec('value = 1')\n"
                    "bi.compile('1', '<text>', 'eval')\n"
                    "dynamic('2')\n"
                    "ast.literal_eval('1')\n"
                )
            }
        )
    )
    findings = _findings(result, "RI-SEC-002")

    assert [item.evidence for item in findings] == [
        "dynamic execution call: eval",
        "dynamic execution call: exec",
        "dynamic execution call: builtins.compile",
        "dynamic execution call: builtins.eval",
    ]
    assert _metrics(result)["security.dynamic_execution_calls"].value == 4


def test_shell_execution_flags_os_and_literal_subprocess_patterns_but_not_argument_arrays(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "shells.py": (
                    "import os\n"
                    "import subprocess as sp\n"
                    "os.system('id')\n"
                    "os.popen('id')\n"
                    "sp.run('echo hello')\n"
                    "sp.Popen(['echo', 'ok'], shell=True)\n"
                    "sp.run(['echo', 'safe'])\n"
                    "sp.run(['echo', 'safe'], shell=False)\n"
                )
            }
        )
    )

    assert [item.evidence for item in _findings(result, "RI-SEC-003")] == [
        "shell execution pattern: os.system",
        "shell execution pattern: os.popen",
        "literal string subprocess command: subprocess.run",
        "subprocess call with literal shell=True: subprocess.Popen",
    ]
    assert _metrics(result)["security.unsafe_subprocess_calls"].value == 4


def test_unsafe_deserialization_recognizes_safe_yaml_loader_negative_cases(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "deserialize.py": (
                    "import pickle\n"
                    "import marshal as binary\n"
                    "import yaml\n"
                    "pickle.loads(data)\n"
                    "binary.load(stream)\n"
                    "yaml.load(text)\n"
                    "yaml.load(text, Loader=yaml.SafeLoader)\n"
                    "yaml.load(text, yaml.CSafeLoader)\n"
                    "yaml.safe_load(text)\n"
                )
            }
        )
    )

    assert [item.evidence for item in _findings(result, "RI-SEC-004")] == [
        "unsafe deserialization call: pickle.loads",
        "unsafe deserialization call: marshal.load",
        "yaml.load without an explicit SafeLoader or CSafeLoader",
    ]
    assert _metrics(result)["security.unsafe_deserialization_calls"].value == 3


def test_risky_tempfile_rule_is_narrow_to_mktemp_and_predictable_tempdir_join_use(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "temporary.py": (
                    "import os\n"
                    "import tempfile as tf\n"
                    "from pathlib import Path\n"
                    "first = tf.mktemp()\n"
                    "predictable = os.path.join(tf.gettempdir(), 'fixed.txt')\n"
                    "open(predictable, 'w')\n"
                    "arbitrary = os.path.join('/var/tmp', 'fixed.txt')\n"
                    "open(arbitrary, 'w')\n"
                    "with tf.NamedTemporaryFile() as safe:\n"
                    "    safe.write(b'ok')\n"
                )
            }
        )
    )

    assert [item.evidence for item in _findings(result, "RI-SEC-005")] == [
        "risky temporary-file call: tempfile.mktemp",
        "predictable filename under tempfile.gettempdir used by open",
    ]
    assert _metrics(result)["security.risky_tempfile_patterns"].value == 2


def test_unpinned_dependencies_are_one_finding_per_runtime_manifest_with_compensation(
    context_factory: ContextFactory,
) -> None:
    unpinned = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "requirements.txt": "requests>=2\nflask==3.0.0\n",
                "requirements-dev.txt": "pytest>=9\n",
                "pyproject.toml": ("[project]\nname = 'demo'\ndependencies = ['httpx>=0.28']\n"),
                "setup.cfg": "[options]\ninstall_requires =\n    click==8.1.8\n",
            }
        )
    )
    assert [
        item.location.path if item.location else None for item in _findings(unpinned, "RI-SEC-006")
    ] == [
        "pyproject.toml",
        "requirements.txt",
    ]
    assert _metrics(unpinned)["security.unpinned_runtime_manifests"].value == 2

    lock_compensated = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "requirements.txt": "requests>=2\n",
                "uv.lock": "version = 1\n",
            }
        )
    )
    assert _findings(lock_compensated, "RI-SEC-006") == []
    assert _metrics(lock_compensated)["security.unpinned_runtime_manifests"].value == 0

    constraints_compensated = ANALYZER.analyze(
        context_factory(
            {
                "app.py": "value = 1\n",
                "requirements.txt": "requests>=2\n",
                "constraints.txt": "requests==2.32.5\n",
            }
        )
    )
    assert _findings(constraints_compensated, "RI-SEC-006") == []


def test_poetry_runtime_constraints_treat_bare_versions_as_exact_and_caret_as_unpinned(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "pyproject.toml": (
                    "[tool.poetry]\nname = 'demo'\n"
                    "[tool.poetry.dependencies]\n"
                    "python = '^3.11'\n"
                    "flask = '3.0.0'\n"
                    "requests = '^2.32'\n"
                )
            }
        )
    )

    findings = _findings(result, "RI-SEC-006")
    assert len(findings) == 1
    assert findings[0].location is not None
    assert findings[0].location.path == "pyproject.toml"


def test_setup_py_and_pipfile_runtime_literals_are_parsed_without_execution(
    context_factory: ContextFactory,
) -> None:
    marker = "should_not_be_created"
    context = context_factory(
        {
            "setup.py": (
                "from setuptools import setup\n"
                "setup(name='demo', install_requires=['requests>=2'])\n"
                f"open('{marker}', 'w').write('bad')\n"
            ),
            "Pipfile": "[packages]\nhttpx = '*'\n[dev-packages]\npytest = '*'\n",
        }
    )
    result = ANALYZER.analyze(context)

    assert [
        item.location.path if item.location else None for item in _findings(result, "RI-SEC-006")
    ] == [
        "Pipfile",
        "setup.py",
    ]
    assert not (context.inventory.root / marker).exists()


def test_tls_verification_rule_requires_literal_false_or_cert_none(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "tls.py": (
                    "import requests as req\n"
                    "import httpx\n"
                    "import urllib3\n"
                    "req.get(url, verify=False)\n"
                    "httpx.Client(verify=False)\n"
                    "urllib3.PoolManager(cert_reqs='CERT_NONE')\n"
                    "req.get(url, verify=True)\n"
                    "httpx.get(url, verify=setting)\n"
                )
            }
        )
    )

    assert [item.evidence for item in _findings(result, "RI-SEC-007")] == [
        "TLS verification disabled in requests.get",
        "TLS verification disabled in httpx.Client",
        "urllib3 cert_reqs is literal CERT_NONE",
    ]
    assert _metrics(result)["security.tls_verification_disabled_calls"].value == 3


def test_tls_verification_tracks_simple_static_client_variables(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {
                "client.py": (
                    "import httpx\n"
                    "client = httpx.Client()\n"
                    "client.get(url, verify=False)\n"
                    "client.get(url, verify=True)\n"
                )
            }
        )
    )

    assert [item.evidence for item in _findings(result, "RI-SEC-007")] == [
        "TLS verification disabled in client.get"
    ]


def test_malformed_python_keeps_secret_scan_and_marks_ast_metrics_unavailable(
    context_factory: ContextFactory,
) -> None:
    token = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    result = ANALYZER.analyze(context_factory({"broken.py": f"token = '{token}'\ndef broken(\n"}))

    assert result.status.completeness is Completeness.PARTIAL
    assert len(_findings(result, "RI-SEC-001")) == 1
    assert token not in result.model_dump_json()
    dynamic = _metrics(result)["security.dynamic_execution_calls"]
    assert dynamic.value is None
    assert dynamic.completeness is Completeness.UNAVAILABLE
    secrets = _metrics(result)["security.possible_secret_count"]
    assert secrets.value == 1
    assert secrets.completeness is Completeness.AVAILABLE


def test_security_disabled_rule_keeps_metric_and_all_metrics_are_stable_partial(
    context_factory: ContextFactory,
) -> None:
    result = ANALYZER.analyze(
        context_factory(
            {"module.py": "eval('1')\n"},
            config_overrides={"rules": {"disabled": ["RI-SEC-002"]}},
            index_completeness=Completeness.PARTIAL,
        )
    )
    assert _findings(result, "RI-SEC-002") == []
    assert _metrics(result)["security.dynamic_execution_calls"].value == 1
    expected_ids = {
        "security.possible_secret_count",
        "security.dynamic_execution_calls",
        "security.unsafe_subprocess_calls",
        "security.unsafe_deserialization_calls",
        "security.risky_tempfile_patterns",
        "security.unpinned_runtime_manifests",
        "security.tls_verification_disabled_calls",
    }
    assert [metric.id for metric in result.metrics] == sorted(expected_ids)
    assert all(
        metric.analyzer_id == "security-hygiene" and metric.provenance for metric in result.metrics
    )
    assert _metrics(result)["security.possible_secret_count"].completeness is Completeness.AVAILABLE
    assert (
        _metrics(result)["security.unpinned_runtime_manifests"].completeness
        is Completeness.AVAILABLE
    )
    for metric_id in expected_ids - {
        "security.possible_secret_count",
        "security.unpinned_runtime_manifests",
    }:
        assert _metrics(result)[metric_id].completeness is Completeness.PARTIAL
    catalog = {rule.id: rule for rule in RULE_CATALOG}
    for finding in result.findings:
        rule = catalog[finding.rule_id]
        assert finding.title == rule.title
        assert finding.remediation == rule.remediation
        assert finding.limitations[0] == rule.limitations
