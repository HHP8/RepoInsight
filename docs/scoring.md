# Scoring contract 1.0

Each category starts at 100. Enabled findings subtract the catalog deduction until the rule's category cap is reached. Findings remain in the report when a cap leaves zero additional applied impact, so the trace preserves evidence without double-counting it.

Default weights are:

| Category | Weight |
|---|---:|
| Maintainability | 25 |
| Testing | 25 |
| Documentation | 15 |
| Security hygiene | 15 |
| Repository hygiene | 10 |
| Maintenance | 10 |

Unavailable categories have no score and their weight is removed from the denominator. Partial categories retain a score with an explicit partial marker. This prevents missing evidence from appearing as a perfect zero-deduction measurement.

The overall score is calculated with `Decimal`, clamped to 0 through 100, and rounded once to one decimal using round-half-up. Rating boundaries use the unrounded overall value:

- Excellent: 90 or higher
- Strong: 80 through less than 90
- Healthy: 70 through less than 80
- Needs improvement: 50 through less than 70
- High maintenance risk: below 50

`--fail-under N` returns exit code 10 only when the unrounded score is below `N`. Equality passes. JSON category traces list the baseline, completeness, configured weight, per-rule raw deduction, applied deduction, and cap.
