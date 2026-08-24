# Architecture

RepoInsight is a static-analysis pipeline with narrow typed boundaries:

1. The Typer CLI parses user intent and creates an immutable `AnalysisRequest`.
2. Configuration merges built-in defaults, one TOML file, then CLI overrides.
3. Acquisition validates a local root or makes a bounded temporary clone of a public GitHub repository.
4. Inventory walks contained regular files without following external links.
5. The Python index decodes source and parses ASTs without importing modules.
6. Six analyzers consume the read-only context through an explicit registry.
7. Normalization revalidates, redacts, deduplicates, caps, and deterministically sorts outputs.
8. Scoring produces category traces and a weighted overall result.
9. Report writers validate the public schema and atomically write canonical JSON and standalone HTML.

There is no runtime plugin discovery in version 1. Analyzer order and rule ownership are explicit. Repository content is data only and is never interpreted as Python configuration or imported code.

## Stable boundaries

- `Analyzer` describes metadata and an `analyze(context)` entry point.
- `RepositoryContext` exposes bounded inventory, AST, configuration, and sanitized Git evidence.
- `AnalyzerResult` contains typed metrics, findings, status, skipped inputs, warnings, and limitations.
- `AnalysisReport` is the renderer input and JSON contract source.
- `repoinsight-report-v1.schema.json` independently validates every successful report.

Output ordering is canonical. Runtime timestamps and elapsed durations are intentionally run-specific; injected clocks make them deterministic in tests.

## Failure behavior

Acquisition and report failures stop with stable exit codes. An individual analyzer failure is isolated, redacted, and disclosed as partial analysis. Missing Git metadata does not block file analysis. Temporary clone cleanup occurs when the acquisition context exits, before report writing.
