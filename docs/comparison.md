# Local saved-report comparison

Implemented locally and uncommitted after release 1.1.0; not a published 1.2
release. Comparison reads saved static reports only: no acquisition, analyzer
execution, target-code imports, configuration execution, AI or network calls.
The base installation needs neither HTTPX nor an API key.

```console
repoinsight compare before.json after.json
repoinsight compare before.json after.json --format json
repoinsight compare before.json after.json --format json --output comparison.json
```

`--format terminal|json` defaults to terminal. Without `--output`, the selected
representation goes to stdout. JSON stdout is one document and a newline, without
progress messages. `--output PATH` writes to a file with empty stdout. Exit codes:
0 for success regardless of score direction, 20 for invalid input/options, 23 for
output failures/aliases. No fail-on-regression policy, HTML or publication action.

## Inputs and output safety

Each input is bounded to 16 MiB, independently validated against the packaged
static schema and immutable models, then hashed from its exact original bytes.
Supported tool versions: 1.0.0 and 1.1.0; static schema/scoring contracts: 1.0.
Unsupported contracts, malformed JSON, duplicate metric/category IDs, non-finite
values, invalid locations and wrong types fail without echoing raw input/prose.
`saved_reports.load_report` is shared with enrichment; the existing
`ai.payload.load_report` import and bounded behavior are preserved.

Identical inputs are valid. Inputs stay read-only, including on failures. Before
creating output directories, preflight rejects either input and resolved
symlink/hardlink aliases. Preflight is repeated before atomic replacement through
the existing writer, with temporary-file cleanup. Concurrent privileged filesystem
mutation remains outside the v1 threat model. JSON escapes non-ASCII characters
for safe stdout; terminal output redacts and escapes controls/bidi characters.

## Matching, duplicates and suppression

The exact key is rule ID, analyzer ID and normalized location: relative POSIX path,
start/end line and start/end column, including absent range components. Paths are
case-sensitive on every OS. No fuzzy matching, rename or line-shift inference:
location changes can appear as removal/addition.

Repeated keys are multisets. Equal attribute snapshots consume counts first.
Remaining snapshots are sorted canonically and paired by count; leftovers become
additions/removals. Repeated-key and locationless records have `ambiguous:true`
and `uncertain:true`; pairings do not identify physical occurrences. There are
no invented unique finding IDs and no dropped duplicates.

| Status | Meaning |
|---|---|
| `new` | Only observed after; limited earlier coverage can explain it |
| `unchanged` | Matched redacted attributes equal; coverage can remain uncertain |
| `changed` | Matched attributes differ; fields and both snapshots are shown |
| `resolved` | Absent from compatible complete static coverage for the relevant analyzer/category |
| `no_longer_observed` | Missing under limited coverage or incompatible metadata; uncertain |

Direct attributes include category, analyzer version, severity, confidence, score
impact, suppression and cap application. Title, explanation, evidence, remediation,
limitations and suppression reason are compared by SHA256 of canonical redacted
values; arbitrary prose is not exported. Redaction can collapse distinct secrets,
so those differences cannot be detected. Suppression transitions are changes, not
fixes; suppressed occurrences remain counted. Ambiguous removals retain a count
classification with explicit uncertainty. Even `resolved` never proves a security
fix, correctness or improved runtime behavior.

## Scores and compatibility

Overall/category scores show observed `after - before` deltas. Missing/unavailable
scores yield null deltas; absent categories have null score/completeness on that
side. Skip/warning totals show before/after/delta; diagnostic multiset counts
detect different evidence even when totals stay equal, without exposing messages
or skipped paths.

Flags disclose source kind/identity, configuration fingerprint, tool metadata,
schema/scoring contracts, category membership, explicit scorecard weight/baseline/
rounding differences, analyzer membership and observed analyzer-version changes.
Unsupported contracts fail first. Revisions may naturally differ between scans
and are not themselves an incompatibility. Configuration settings absent from a
saved report cannot be inferred from its fingerprint.

Analyzer versions come only from findings. Empty version lists mean unknown;
mixed versions are flagged. No installed version is substituted.
`scores_interpretable` requires compatible metadata, complete reports/categories/
analyzers, no skips/warnings and one matching observed version per represented
analyzer. Otherwise deltas require context. Even when true, arithmetic does not
prove improvement/regression. Partial/incompatible inputs never yield an
unqualified regression claim.

## Independent output contract 1.0

Packaged schema:
[`repoinsight-comparison-v1.schema.json`](../src/repoinsight/schema/repoinsight-comparison-v1.schema.json).
Static and AI contracts are unchanged. Comparison has no timestamp, duration or
input filename; identical bytes produce deterministic output.

| Field | Meaning |
|---|---|
| `comparison_schema_version` | Literal `1.0`, independent of package/static/AI versions |
| `before`, `after` | Exact-byte hash, tool/schema/scoring versions, config fingerprint, coverage and totals |
| `compatibility` | Sorted difference codes, observed version lists and score interpretation flag |
| `overall`, `categories` | Before/after scores, deltas and coverage; categories sorted |
| `skipped_inputs`, `warning_count` | Before/after counts and signed deltas |
| `skipped_input_changes`, `warning_changes` | Added/removed/unchanged diagnostic multiset counts |
| `counts` | New/resolved/no-longer-observed/unchanged/changed occurrence totals |
| `findings` | Exact key, status/count, snapshots, changed fields, ambiguity and uncertainty |
| `warnings`, `limitations` | Compatibility/coverage codes and fixed interpretation limits |

Keys sort lexicographically by rule/analyzer/canonical location. Within a key,
exact matches come first, then changed pairs, removals and additions. Attribute
snapshots and changed fields are canonical; counts preserve duplicates. Content
hashes represent redacted attributes, not unique finding identities.

See [complete and partial examples](examples/report-comparison.md).
