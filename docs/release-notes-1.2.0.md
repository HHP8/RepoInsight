# RepoInsight 1.2.0 — 2026-10-20

Offline saved-report comparison is added in 1.2.0. Version 1.1.0 has no comparison
command. The experimental AI behavior and its existing limitations are unchanged.
GitHub release assets provide the wheel, source archive and checksums.
PyPI publication is separate and is not included.

Compare two saved reports without scanning repositories or using AI:

```console
repoinsight compare before.json after.json
repoinsight compare before.json after.json --format json --output comparison.json
```

The comparison preserves exact input byte hashes, uses bounded shared static
schema/model loading (16 MiB per input), and supports tool 1.0.0/1.1.0/1.2.0 reports.
Findings match by rule, analyzer and exact normalized location; duplicate evidence
is a multiset, with ambiguity disclosed. Renames and line shifts can look like
removals/additions. Matched severity, confidence, impact and suppression changes
are explicit. Suppression is not a fix. Missing findings under incomplete coverage
or incompatible metadata are no longer observed with uncertainty, not proven fixed.

Terminal and deterministic JSON outputs show observed score/category deltas,
finding counts, coverage and warning/skip changes. Different source/configuration/
tool/analyzer evidence qualifies interpretation. Even complete static comparisons
do not prove a security fix. Output rejects input paths and symlink/hardlink aliases.

Package/runtime/new-report metadata becomes 1.2.0. Static schema/scoring and
comparison contracts stay 1.0; rule IDs, scoring, analyzer 1.0.0 metadata and
experimental AI prompt/request/response behavior stay unchanged. The updated
static/comparison metadata enums accept the three listed tool versions. Older
strict validators may reject 1.2.0 metadata and need updated schemas; there is no
unlimited future-version acceptance. Offline enrichment preview supports newly
produced reports without an API key or provider request.

No bounded source context, static-rule tuning, retry/model/budget/consent changes
or new paid evaluation is included. Historical 1.1.0 AI caveats and evidence remain
applicable and immutable. See the [comparison guide](comparison.md),
[examples](examples/report-comparison.md) and [release checklist](release.md).

Implementation platform validation passed all 12 OS/Python cells and quality on
[candidate CI](https://github.com/HHP8/RepoInsight/actions/runs/37995687225) and
[main CI](https://github.com/HHP8/RepoInsight/actions/runs/37998558157) for `25ae05f`: 588 passed and one optional benchmark skip per cell.
Windows named link passes were inferred from quiet logs using matching source and
collection order. These runs precede the final release-document changes; final
commit CI, signing, tag build and uploaded-asset checks are recorded separately
in the release checkpoint. No live AI generation or new usefulness rating was
performed for this release.
