from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator

from repoinsight.ai.payload import load_report as legacy_loader
from repoinsight.cli import main
from repoinsight.comparison import compare_reports
from repoinsight.errors import InvalidUsageError, ReportError
from repoinsight.models import Category, Location
from repoinsight.reporting.comparison import (
    comparison_schema,
    generate_comparison_schema,
    render_comparison,
    serialize_comparison,
    write_comparison,
)
from repoinsight.saved_reports import MAX_REPORT_BYTES, load_report

from .conftest import ReportFactory, finding


def mutate(path: Path, change: Any) -> None:
    data = json.loads(path.read_bytes())
    change(data)
    path.write_text(json.dumps(data), encoding="utf-8")


def test_shared_loader_preserves_legacy_behavior_and_input_bytes(
    report_factory: ReportFactory,
) -> None:
    path = report_factory(findings=(finding(),))
    raw = path.read_bytes()
    assert load_report(path) == legacy_loader(path)
    assert load_report(path)[1] == hashlib.sha256(raw).hexdigest()
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "mutation",
    [
        lambda d: d.update(schema_version="2.0"),
        lambda d: d["tool"].update(version="9.0.0"),
        lambda d: d["tool"].update(schema_version="2.0"),
        lambda d: d["tool"].update(score_contract_version="2.0"),
        lambda d: d.update(completeness="invalid"),
        lambda d: d["scorecard"]["categories"].append(d["scorecard"]["categories"][0]),
        lambda d: d["scorecard"].update(overall_score=float("inf")),
        lambda d: d["scorecard"].update(overall_score=float("nan")),
        lambda d: d["metrics"].extend(
            [
                {
                    "id": "duplicate",
                    "analyzer_id": "testing",
                    "category": "testing",
                    "value": 1,
                    "unit": None,
                    "provenance": "synthetic",
                    "completeness": "available",
                }
            ]
            * 2
        ),
        lambda d: d["metrics"].append(
            {
                "id": "nonfinite",
                "analyzer_id": "testing",
                "category": "testing",
                "value": float("nan"),
                "unit": None,
                "provenance": "synthetic",
                "completeness": "available",
            }
        ),
        lambda d: d["findings"][0]["location"].update(path="src/../escape.py"),
        lambda d: d["findings"][0].update(score_impact="5"),
    ],
)
def test_invalid_inputs_are_safe_and_immutable(
    report_factory: ReportFactory, mutation: Any
) -> None:
    path = report_factory(findings=(finding(),))
    mutate(path, mutation)
    raw = path.read_bytes()
    with pytest.raises(InvalidUsageError) as error:
        compare_reports(path, path)
    assert "synthetic" not in str(error.value)
    assert path.read_bytes() == raw


@pytest.mark.parametrize(
    "raw", [b"{untrusted private invalid JSON}", b"\xff", b"null", b"[]", b"[" * 1200 + b"]" * 1200]
)
def test_malformed_inputs_do_not_echo_prose(tmp_path: Path, raw: bytes) -> None:
    path = tmp_path / "bad.json"
    path.write_bytes(raw)
    with pytest.raises(InvalidUsageError, match=r"valid saved|report schema"):
        compare_reports(path, path)
    assert path.read_bytes() == raw


def test_input_limit_is_real_and_boundary_inclusive(report_factory: ReportFactory) -> None:
    path = report_factory()
    raw = path.read_bytes()
    path.write_bytes(raw + b" " * (MAX_REPORT_BYTES - len(raw)))
    assert load_report(path)[1] == hashlib.sha256(path.read_bytes()).hexdigest()
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(InvalidUsageError, match="16 MiB"):
        compare_reports(path, path)


def test_category_delta_missing_category_and_null_scores(report_factory: ReportFactory) -> None:
    before = report_factory()
    after = report_factory()

    def change(d: Any) -> None:
        d["scorecard"]["categories"][0]["score"] = 85
        d["scorecard"]["categories"][1].update(score=None, completeness="unavailable")
        d["scorecard"]["categories"].pop()
        d["scorecard"].update(overall_score=90, rating="Strong")

    mutate(after, change)
    result = compare_reports(before, after)
    assert result.overall.delta == -10
    categories = {x.category: x for x in result.categories}
    assert categories[Category.MAINTAINABILITY].delta == -15
    assert categories[Category.TESTING].after is None and categories[Category.TESTING].delta is None
    assert categories[Category.MAINTENANCE].after_completeness is None
    assert "category-set" in result.compatibility.differences
    assert not result.compatibility.scores_interpretable


@pytest.mark.parametrize(
    "mutation,flag",
    [
        (lambda d: d.update(configuration_fingerprint="1" * 64), "configuration-fingerprint"),
        (lambda d: d["source"].update(identity="another source"), "source-identity"),
        (lambda d: d["tool"].update(version="1.0.0"), "tool"),
        (lambda d: d["findings"][0].update(analyzer_version="2.0.0"), "analyzer-versions"),
        (lambda d: d["scorecard"]["categories"][0].update(weight=9), "scorecard-settings"),
        (lambda d: d["scorecard"].update(rounding="different rounding"), "scorecard-settings"),
    ],
)
def test_compatibility_differences_qualify_scores(
    report_factory: ReportFactory,
    mutation: Any,
    flag: str,
) -> None:
    before = report_factory(findings=(finding(),))
    after = report_factory(findings=(finding(),))
    mutate(after, mutation)
    result = compare_reports(before, after)
    assert flag in result.compatibility.differences
    assert not result.compatibility.scores_interpretable
    assert "regression" not in render_comparison(result).split("Limit:")[0]


def test_version_unknown_is_not_invented(report_factory: ReportFactory) -> None:
    path = report_factory()
    result = compare_reports(path, path)
    assert result.compatibility.analyzer_versions[0].before == ()
    assert "analyzer-version-evidence-incomplete" in result.warnings
    assert not result.compatibility.scores_interpretable


def test_complete_known_versions_permit_interpretation(report_factory: ReportFactory) -> None:
    path = report_factory(findings=(finding(),))
    result = compare_reports(path, path)
    assert result.compatibility.scores_interpretable
    Draft202012Validator(comparison_schema()).validate(json.loads(serialize_comparison(result)))
    assert comparison_schema() == generate_comparison_schema()
    Draft202012Validator.check_schema(comparison_schema())


def test_category_and_analyzer_coverage_limit_removal(report_factory: ReportFactory) -> None:
    before = report_factory(findings=(finding(),))
    after = report_factory()
    mutate(after, lambda d: d["scorecard"]["categories"][0].update(completeness="partial"))
    assert compare_reports(before, after).counts.no_longer_observed == 1
    after = report_factory()
    mutate(
        after, lambda d: d["analyzer_status"][0].update(state="failed", completeness="unavailable")
    )
    assert compare_reports(before, after).counts.no_longer_observed == 1
    after = report_factory()
    mutate(after, lambda d: d.update(analyzer_status=[]))
    assert compare_reports(before, after).counts.no_longer_observed == 1


def test_config_change_blocks_resolution(report_factory: ReportFactory) -> None:
    before = report_factory(findings=(finding(),))
    after = report_factory(configuration_fingerprint="f" * 64)
    result = compare_reports(before, after)
    assert result.counts.resolved == 0 and result.counts.no_longer_observed == 1


@pytest.mark.parametrize(
    "field,new",
    [
        ("title", "New title"),
        ("explanation", "New explanation"),
        ("evidence", "New evidence"),
        ("remediation", "New remediation"),
        ("limitations", ["New limitation"]),
        ("cap_applied", True),
        ("analyzer_version", "1.1.0"),
        ("category", "testing"),
    ],
)
def test_all_meaningful_attributes_are_detected(
    report_factory: ReportFactory, field: str, new: object
) -> None:
    result = compare_reports(
        report_factory(findings=(finding(),)), report_factory(findings=(finding(**{field: new}),))
    )
    assert result.counts.changed == 1
    assert field in result.findings[0].changed_attributes


def test_no_location_and_repeated_evidence_do_not_gain_invented_identities(
    report_factory: ReportFactory,
) -> None:
    result = compare_reports(
        report_factory(findings=(finding(location=None), finding(location=None))),
        report_factory(findings=(finding(location=None),)),
    )
    assert result.counts.unchanged == 1 and result.counts.resolved == 1
    assert all(item.ambiguous and item.uncertain for item in result.findings)
    assert all("id" not in item.model_dump() for item in result.findings)


@pytest.mark.parametrize("alias", ["before", "after", "hardlink", "symlink", "input-symlink"])
def test_output_aliases_cannot_mutate_inputs(
    report_factory: ReportFactory,
    tmp_path: Path,
    alias: str,
) -> None:
    before = report_factory()
    after = report_factory()
    output = tmp_path / "output.json"
    originals = (before.read_bytes(), after.read_bytes())
    if alias == "before":
        output = before
    elif alias == "after":
        output = after
    elif alias == "hardlink":
        try:
            output.hardlink_to(before)
        except PermissionError:
            pytest.skip("Host does not permit hardlink creation")
    else:
        try:
            output.symlink_to(before)
        except OSError:
            pytest.skip("Host does not permit symlink creation")
        if alias == "input-symlink":
            before, output = output, before
    with pytest.raises(ReportError, match="must not replace"):
        write_comparison(output, b"comparison", (before, after))
    assert (before.read_bytes(), after.read_bytes()) == originals


def test_atomic_failure_preserves_existing_output_and_inputs(
    report_factory: ReportFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = report_factory()
    after = report_factory()
    originals = (before.read_bytes(), after.read_bytes())
    output = tmp_path / "result.txt"
    output.write_bytes(b"existing")

    def fail(*args: object) -> None:
        raise OSError("Synthetic failure")

    monkeypatch.setattr("repoinsight.reporting.writers.os.replace", fail)
    with pytest.raises(ReportError):
        write_comparison(output, b"replacement", (before, after))
    assert output.read_bytes() == b"existing"
    assert not list(tmp_path.glob("*.tmp"))
    assert (before.read_bytes(), after.read_bytes()) == originals


def test_cli_machine_and_terminal_and_output_errors(
    report_factory: ReportFactory,
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    path = report_factory(findings=(finding(),))
    args = ["compare", str(path), str(path)]
    assert main(args) == 0
    output = capsys.readouterr()
    assert "Overall score" in output.out and not output.err
    assert main([*args, "--format", "json"]) == 0
    output = capsys.readouterr()
    assert not output.err and json.loads(output.out)["counts"]["unchanged"] == 1
    assert output.out.count("\n") == 1
    assert main([*args, "--format", "json"]) == 0
    assert capsys.readouterr().out == output.out
    destination = tmp_path / "nested/result.json"
    assert main([*args, "--format", "json", "--output", str(destination)]) == 0
    assert capsys.readouterr().out == "" and json.loads(destination.read_bytes()) == json.loads(
        output.out
    )
    assert main([*args, "--output", str(path)]) == 23
    assert not capsys.readouterr().out
    assert main([*args, "--format", "html"]) == 20
    assert not capsys.readouterr().out
    bad_parent = tmp_path / "file"
    bad_parent.write_bytes(b"occupied")
    assert main([*args, "--output", str(bad_parent / "child")]) == 23
    assert not capsys.readouterr().out
    assert main(["compare", str(tmp_path / "missing"), str(path)]) == 20
    assert not capsys.readouterr().out


def test_terminal_and_json_escape_controls_and_redact_prose(report_factory: ReportFactory) -> None:
    token = "ghp_" + "A" * 36
    path = report_factory(
        findings=(
            finding(
                location=Location(path="src/\x1b[31m\u202efile.py", start_line=1),
                evidence=token,
                explanation="PRIVATE SENTINEL",
                analyzer_id="analyzer\x1b[31m\u009b",
            ),
        )
    )
    result = compare_reports(path, path)
    terminal = render_comparison(result)
    raw = serialize_comparison(result)
    assert "\x1b" not in terminal and "\u202e" not in terminal and "\u009b" not in terminal
    assert b"\x1b" not in raw and "\u202e".encode() not in raw and "\u009b".encode() not in raw
    assert token not in terminal and token.encode() not in raw
    assert "PRIVATE SENTINEL" not in terminal and b"PRIVATE SENTINEL" not in raw


def test_comparison_never_calls_acquisition_analyzers_or_provider(
    report_factory: ReportFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import socket

    from repoinsight.ai.provider import OpenAIProvider
    from repoinsight.application import AnalyzeService

    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("Forbidden execution or network")

    monkeypatch.setattr(AnalyzeService, "analyze", forbidden)
    monkeypatch.setattr(OpenAIProvider, "generate", forbidden)
    monkeypatch.setattr(socket, "create_connection", forbidden)
    monkeypatch.setattr(socket.socket, "connect", forbidden)
    path = report_factory()
    assert compare_reports(path, path).counts.new == 0


def test_skip_warning_multisets_change_even_when_counts_stay_equal(
    report_factory: ReportFactory,
) -> None:
    before = report_factory()
    after = report_factory()
    for path, name in ((before, "old"), (after, "new")):

        def change(d: Any, name: str = name) -> None:
            d["completeness"] = "partial"
            d["skipped_inputs"] = [{"path": name + ".py", "reason": "Synthetic skip"}]
            d["warnings"] = [{"code": "synthetic-" + name, "message": "Synthetic warning"}]

        mutate(path, change)
    result = compare_reports(before, after)
    assert result.skipped_inputs.delta == result.warning_count.delta == 0
    assert result.skipped_input_changes.added == result.skipped_input_changes.removed == 1
    assert result.warning_changes.added == result.warning_changes.removed == 1
    assert not result.compatibility.scores_interpretable


def test_samefile_alias_guard_is_checked_before_output_creation(
    report_factory: ReportFactory,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    before = report_factory()
    after = report_factory()
    output = tmp_path / "existing-alias"
    output.write_bytes(b"Synthetic hardlink simulation")
    original = Path.samefile

    def samefile(path: Path, other: Path) -> bool:
        return True if path == output and other == before else original(path, other)

    monkeypatch.setattr(Path, "samefile", samefile)
    with pytest.raises(ReportError, match="must not replace"):
        write_comparison(output, b"replacement", (before, after))
    assert output.read_bytes() == b"Synthetic hardlink simulation"


def test_duplicate_categories_do_not_make_coverage_order_dependent(
    report_factory: ReportFactory,
) -> None:
    before = report_factory(findings=(finding(), finding(category="testing")))
    permuted = report_factory(findings=(finding(category="testing"), finding()))
    after = report_factory()
    for path in (before, permuted, after):
        mutate(path, lambda d: d["scorecard"]["categories"][1].update(completeness="partial"))
    a, b = compare_reports(before, after), compare_reports(permuted, after)
    assert a.findings == b.findings
    assert a.counts.no_longer_observed == 2 and a.counts.resolved == 0


def test_missing_status_evidence_limits_scores_even_with_finding_versions(
    report_factory: ReportFactory,
) -> None:
    path = report_factory(findings=(finding(),))
    mutate(path, lambda d: d.update(analyzer_status=[]))
    result = compare_reports(path, path)
    assert not result.compatibility.scores_interpretable
    assert "analyzer-status-evidence-incomplete" in result.warnings


def test_terminal_shows_direct_attribute_before_after_values(report_factory: ReportFactory) -> None:
    before = report_factory(findings=(finding(),))
    after = report_factory(findings=(finding(severity="high", evidence="different"),))
    terminal = render_comparison(compare_reports(before, after))
    assert "severity medium -> high" in terminal and "evidence redacted content changed" in terminal
