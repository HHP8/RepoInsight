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

## `repoinsight enrich REPORT` (development checkout)

Explain an existing v1 JSON report without reading or executing current repository
source. This command is implemented for the next release and is not available in
the published 1.0.0 package. Require exactly one consent mode and an explicit model.

| Option | Meaning |
|---|---|
| `--preview` | Print the exact OpenAI JSON request without sending it; no key or AI extra needed |
| `--send` | Explicitly authorize transmission to the fixed OpenAI HTTPS endpoint |
| `--model MODEL_ID` | Required in both modes; choose a Responses API model with Structured Outputs |
| `--output PATH` | Separate AI output directory; default `repoinsight-ai` |
| `--max-findings 0..20` | Maximum findings selected; default 20 |
| `--max-input-tokens 1..32000` | Conservative input estimate limit; default 8000 |
| `--max-output-tokens 1..4000` | Provider output limit; default 1500, including reasoning tokens where applicable |
| `--timeout 1..120` | Transport timeout and checked request deadline; default 30 seconds across at most two attempts |

The input report is capped at 16 MiB and validated against the existing schema.
Input estimates conservatively count one token per UTF-8 byte of the entire request
plus overhead. They are deliberately larger than typical tokenizer counts. Lower
priority findings and then metrics are dropped until the request fits; omission
counts are shown. A budget too small for the fixed envelope fails with code 20.
Output text and the full provider response are bounded and validated.

```console
repoinsight enrich reports/repoinsight-report.json --preview --model MODEL_ID
repoinsight enrich reports/repoinsight-report.json --send --model MODEL_ID --output ai-reports
```

Preview's standard output is machine-readable JSON; estimates go to standard error.
With identical report bytes and options, preview shows the same request body that
send uses. Changing the file/options changes the request. Authorization headers
are never printed. Send reads only `OPENAI_API_KEY` from the process environment;
literal-key flags, TOML AI settings, endpoint overrides, and automatic source uploads
are unsupported. Install the AI extra from this checkout before sending.

Outputs are `repoinsight-ai.json` and `repoinsight-ai.html`, each bound to the exact
base report hash. The original report is never overwritten. AI status, usage when
available, omitted evidence, timestamps, revision, and limitations are recorded.
No current-source verification is performed. A sanitized failed-status record is
written when possible for provider or guidance-validation failures; invalid usage
does not send a request. Output failure takes code 23. AI output is advisory and
does not affect `analyze --fail-under`.

## Exit codes

| Code | Meaning |
|---:|---|
| 0 | Success |
| 10 | Score below `--fail-under` |
| 20 | Invalid usage or configuration |
| 21 | Acquisition failure |
| 22 | Analysis failure |
| 23 | Report validation or write failure |
| 24 | AI provider/enrichment failure |
| 130 | Interrupted |

Diagnostics are concise, non-color-dependent, and redacted. Analyzer failures normally produce a partial report rather than exit code 22.
