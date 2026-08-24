from __future__ import annotations

from collections.abc import Callable

from repoinsight.analyzers.base import AnalysisContext
from repoinsight.analyzers.security import ANALYZER

ContextFactory = Callable[..., AnalysisContext]


def test_possible_secret_findings_never_contain_raw_values_or_derived_raw_hashes(
    context_factory: ContextFactory,
) -> None:
    github = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    openai = "sk-" + "proj-" + "abcdefghijklmnopqrstuv"
    aws = "AKIA" + "ABCDEFGHIJKLMNOP"
    named = "Sup3rConservativeValue987654"
    pem_body = "MIIEvgIBADANBgkqhkiG9w0BAQEFAASCBKgw"
    source = (
        f"github_token = '{github}'\n"
        f"openai_token = '{openai}'\n"
        f"aws_key = '{aws}'\n"
        f"password = '{named}'\n"
        'placeholder = "changeme"\n'
        'short_secret = "tiny"\n'
        'pem = """-----BEGIN ' + "PRIVATE KEY-----\n"
        f"{pem_body}\n"
        "-----END " + 'PRIVATE KEY-----"""\n'
    )

    result = ANALYZER.analyze(context_factory({"secrets.py": source}))
    findings = [item for item in result.findings if item.rule_id == "RI-SEC-001"]
    serialized = result.model_dump_json()

    assert len(findings) == 5
    assert all("possible secret" in item.explanation.casefold() for item in findings)
    assert all("[REDACTED]" in item.evidence for item in findings)
    assert all("family:" in item.evidence and "value:" in item.evidence for item in findings)
    for raw in (github, openai, aws, named, pem_body):
        assert raw not in serialized
        assert raw not in "\n".join(item.evidence for item in findings)
    assert [item.location.start_line if item.location else None for item in findings] == [
        1,
        2,
        3,
        4,
        7,
    ]


def test_overlapping_named_assignment_and_token_emit_once_and_placeholders_stay_negative(
    context_factory: ContextFactory,
) -> None:
    token = "ghp_" + "ABCDEFGHIJKLMNOPQRSTUVWXYZ123456"
    result = ANALYZER.analyze(
        context_factory(
            {
                "config.py": (
                    f"api_key = '{token}'\n"
                    "password = 'your-password-here'\n"
                    "token = '${TOKEN}'\n"
                    "secret = 'example-value'\n"
                )
            }
        )
    )

    findings = [item for item in result.findings if item.rule_id == "RI-SEC-001"]
    assert len(findings) == 1
    assert findings[0].evidence == "family: GitHub token; value: [REDACTED]"
