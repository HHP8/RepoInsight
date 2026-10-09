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

## Optional AI enrichment

The next-release implementation in `ai/` is a separate saved-report pipeline:

1. `enrich` requires an explicit preview/send mode and model.
2. A bounded loader validates the unchanged v1 schema and hashes exact input bytes.
3. An allowlist projection selects trusted rule descriptions and numeric evidence, maps locations to opaque IDs, and enforces request budgets.
4. Preview serializes that exact request offline; send alone reads the environment credential and calls the fixed OpenAI Responses endpoint.
5. Structured-output validation rejects unknown references, fields, unsupported citations, and representative unsupported verification claims.
6. An independent AI model/schema records provenance and advisory guidance. Escaped JSON/HTML sidecars are written without altering the static report.

Provider interfaces and clocks are injectable for tests. HTTPX is imported only in
send mode. The ordinary installation, analyzer registry, static score contract,
and static JSON schema remain unchanged. Missing credentials/dependencies are
usage failures; provider/guidance failures have exit code 24 and record sanitized
failure status when possible.

## Local saved-report comparison

Included in the local uncommitted 1.2.0 candidate, unreleased. `saved_reports.py`
owns shared bounded validation and exact-byte hashes; enrichment's loader import
remains compatible. `comparison.py` compares immutable saved models without
acquisition, analyzer execution or AI transport, using exact multiset keys.
`comparison_models.py` and its packaged schema own independent contract 1.0.
The comparison renderer rejects input aliases and reuses atomic writing.
Static/AI and comparison contracts, rules and scoring remain unchanged. Package
and runtime versions are 1.2.0 in this local candidate. Static ToolMetadata and
comparison InputSummary accept tool 1.0.0, 1.1.0 and 1.2.0; both checked schemas
are regenerated from their own model generators. Unknown future versions fail.
AI payload/sidecar behavior is unchanged; the shared loader supplies the expanded
saved-report compatibility to offline enrichment. Older strict validators require
updated schemas for the new tool metadata.
See [comparison](comparison.md) for matching and unknown version evidence.
