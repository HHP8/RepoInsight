# Draft local release notes: RepoInsight 1.2.0

**Unreleased, local and uncommitted candidate.** Not approved for publication,
signed or validated across the candidate platform matrix. The published release
remains 1.1.0 and its package has no comparison command. These notes are local
preparation only; no GitHub draft or release has been created.

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

Local validation results and remaining platform/publication decisions will be
recorded in the ignored candidate checkpoint and sanitized review handoff. Earlier
main CI is baseline proof only; candidate platform CI needs separate approval.
