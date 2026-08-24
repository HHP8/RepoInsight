# CLI reference

## `repoinsight analyze SOURCE`

Analyze a local directory or public GitHub HTTPS URL.

| Option | Meaning |
|---|---|
| `--output PATH` | Output directory |
| `--format json|html|all` | Selected report formats |
| `--fail-under 0..100` | CI score threshold |
| `--config PATH` | Explicit TOML configuration |
| `--exclude PATTERN` | Repeatable Git-style exclusion |
| `--max-file-bytes N` | Per-file read limit |
| `--max-files N` | Inventory count limit |
| `--max-source-bytes N` | Total source-byte limit |
| `--timeout SECONDS` | Overall analysis deadline |
| `--enable-rule ID` | Repeatable rule enable override |
| `--disable-rule ID` | Repeatable rule disable override |

Examples:

```console
repoinsight analyze . --output reports --format all
repoinsight analyze . --config team.toml --exclude generated/
repoinsight analyze https://github.com/pypa/sampleproject --fail-under 75
```

## `repoinsight rules`

List every stable rule with category, severity, default deduction, cap, default state, and title.

## `repoinsight explain RULE_ID`

Show evidence, scoring, limitations, and remediation for one rule.

```console
repoinsight explain RI-SEC-001
```

## `repoinsight version`

Print the package and public JSON Schema versions.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 10 | Score below `--fail-under` |
| 20 | Invalid usage or configuration |
| 21 | Acquisition failure |
| 22 | Analysis failure |
| 23 | Report validation or write failure |
| 130 | Interrupted |

Diagnostics are concise, non-color-dependent, and redacted. Analyzer failures normally produce a partial report rather than exit code 22.
