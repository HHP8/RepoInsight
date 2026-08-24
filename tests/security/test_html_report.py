from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from repoinsight.application import AnalyzeService
from repoinsight.models import AnalysisReport, AnalysisRequest
from repoinsight.reporting.html_report import render_html


def _hostile_report(tmp_path: Path) -> tuple[AnalysisReport, str]:
    root = tmp_path / "repository"
    root.mkdir()
    (root / "app.py").write_text("value = 1\n", encoding="utf-8")
    report = (
        AnalyzeService(
            now=lambda: datetime(2026, 8, 24, 12, 0, tzinfo=UTC),
            monotonic=lambda: 1.0,
        )
        .analyze(
            AnalysisRequest(
                source=str(root),
                output_directory=tmp_path / "unused",
                formats=(),
                cli_overrides={},
            )
        )
        .report
    )
    payload = '<img src=x onerror="alert(1)"></script>&entities'
    return report.model_copy(
        update={"source": report.source.model_copy(update={"identity": payload})}
    ), payload


def test_html_is_self_contained_semantic_responsive_and_printable(tmp_path: Path) -> None:
    report, _ = _hostile_report(tmp_path)

    html = render_html(report)

    assert html.startswith("<!doctype html>")
    assert '<meta name="viewport"' in html
    assert "<main" in html and "<h1" in html
    assert '<label for="severity-filter">' in html
    assert '<label for="category-filter">' in html
    assert "Analysis metrics" in html
    assert "Git activity" in html
    assert "Skipped inputs" in html
    assert "Warnings" in html
    assert "@media (max-width: 720px)" in html
    assert "@media print" in html
    assert "hidden = !matches" in html
    assert 'tabindex="0" role="region"' in html


def test_html_has_report_navigation_and_accessible_progressive_disclosure(
    tmp_path: Path,
) -> None:
    report, _ = _hostile_report(tmp_path)

    html = render_html(report)

    for section_id in (
        "summary",
        "inventory",
        "metrics",
        "findings",
        "git-activity",
        "skipped-files",
        "limitations",
    ):
        assert f'href="#{section_id}"' in html
        assert f'id="{section_id}"' in html
    assert '<nav class="report-nav" aria-label="Report sections">' in html
    assert '<details class="finding"' in html
    assert 'id="expand-findings"' in html
    assert 'id="collapse-findings"' in html
    assert 'id="filtered-empty"' in html
    assert 'class="skip-link"' in html
    assert ":focus-visible" in html
    assert "prefers-reduced-motion" in html


def test_html_explains_completeness_and_category_availability(tmp_path: Path) -> None:
    report, _ = _hostile_report(tmp_path)

    html = render_html(report)

    assert "Scores use available evidence" in html
    assert "Unavailable category weights are excluded" in html
    assert 'class="status-mark status-' in html
    assert 'aria-label="Completeness:' in html
    assert "Category scoring explanation" in html


def test_html_presents_highest_impact_findings_first_without_mutating_report(
    tmp_path: Path,
) -> None:
    report, _ = _hostile_report(tmp_path)
    original = report.findings[0]
    low = original.model_copy(
        update={"rule_id": "RI-SEC-998", "title": "Low impact presentation", "score_impact": 1.0}
    )
    high = original.model_copy(
        update={"rule_id": "RI-SEC-999", "title": "High impact presentation", "score_impact": 9.0}
    )
    reordered = report.model_copy(update={"findings": (low, high)})

    html = render_html(reordered)

    assert reordered.findings == (low, high)
    assert render_html(reordered) == html
    assert html.index("High impact presentation") < html.index("Low impact presentation")


def test_html_filter_controls_include_visible_state_actions(tmp_path: Path) -> None:
    report, _ = _hostile_report(tmp_path)

    html = render_html(report)

    assert 'id="reset-filters"' in html
    assert "Reset filters" in html
    assert "finding.open = true" in html
    assert "finding.open = false" in html
    assert "filteredEmpty.hidden = visible !== 0" in html


def test_html_escapes_hostile_repository_text_and_has_no_network_surface(tmp_path: Path) -> None:
    report, payload = _hostile_report(tmp_path)

    html = render_html(report)

    assert payload not in html
    assert "&lt;img src=x onerror=&#34;alert(1)&#34;&gt;&lt;/script&gt;&amp;entities" in html
    assert html.count("</script>") == 1
    assert "http://" not in html and "https://" not in html
    assert "fetch(" not in html
    assert "XMLHttpRequest" not in html
    assert "WebSocket" not in html
    assert ".innerHTML" not in html
