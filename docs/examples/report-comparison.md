# Before/after saved-report examples

Synthetic examples of the local uncommitted implementation; no new runtime,
release or live-AI proof. See the [comparison contract](../comparison.md).

## Complete compatible static evidence

Assume matching source/configuration/contracts, complete successful categories/
analyzers, no skips/warnings and matching observed analyzer versions.

| Evidence | Before | After | Result |
|---|---|---|---|
| Overall score | 75 | 80 | Observed +5; no runtime improvement proof |
| Same rule/analyzer at `src/app.py:3` | medium, impact 5 | high, impact 9 | `changed`: severity, score impact |
| Same rule/analyzer at `old.py:1` | present | absent | `resolved` static evidence |
| Same rule/analyzer at `new.py:1` | absent | present | `new`; no rename inference |
| A separate matched occurrence | unsuppressed | suppressed with reason | `changed`, not a fix |

```console
repoinsight compare complete-before.json complete-after.json
repoinsight compare complete-before.json complete-after.json --format json --output complete-diff.json
```

The first three finding rows yield changed=1, resolved=1 and new=1. Range/line
changes also appear as separate removals/additions. Duplicate/locationless
matching retains counts with ambiguity flags, not fabricated identities.

## Partial after coverage

| Evidence | Before | After | Result |
|---|---|---|---|
| Overall score | 75 | 85 | Observed +10; interpretation limited |
| Completeness | available | partial | Partial-coverage warning |
| Findings | one present | absent | `no_longer_observed=1`, `resolved=0`, uncertain |
| Skipped inputs | 0 | 1 | Delta +1, diagnostic added count 1 |

```console
repoinsight compare complete-before.json partial-after.json --format json
```

A higher number cannot establish improvement: the finding may be outside
available evidence. Different configuration/source identity/analyzer versions also
require qualification; absent version evidence stays unknown. Diagnostic changes
are detected even if totals remain equal.

Comparing a partial report with itself produces zero new/removed/changed findings
and zero score deltas, while retaining partial coverage and compatibility warnings.
It does not establish full coverage.
