# RepoInsight Design Specification

**Status:** Implemented version 1 design
**Date:** 2026-08-23  
**Target:** Version 1.0  

## 1. Purpose

RepoInsight is a cross-platform Python command-line application that analyzes the health of Python repositories. It accepts public GitHub repository URLs and local repository directories, performs deterministic static analysis without executing repository code, and generates both machine-readable JSON and a polished standalone HTML report.

The project is intended to demonstrate strong Python and software-engineering ability: modular architecture, safe handling of untrusted input, static analysis, Git integration, transparent scoring, stable interfaces, testing, packaging, CI, and documentation. Data analysis supports the engineering core through metrics and scoring; generative AI is explicitly excluded from version 1.

## 2. Product Scope

### 2.1 Included in version 1

- Public GitHub repository URLs.
- Local repository directories, with or without Git metadata.
- Deep Python-specific static analysis using Python's abstract syntax tree.
- Language-agnostic inspection of repository documentation, configuration, packaging, CI, licensing, and structure.
- Lightweight Git-history metrics with graceful fallback when history is missing or partial.
- Deterministic category scores and a weighted overall score.
- Offline security-hygiene checks.
- A cross-platform CLI.
- Versioned JSON output and a self-contained offline HTML report.
- Optional project configuration through `.repoinsight.toml`.
- CI-friendly thresholds and distinct process exit codes.

### 2.2 Explicitly excluded from version 1

- Private GitHub authentication.
- JavaScript, TypeScript, or other language-specific analyzers.
- Generative AI or LLM-based review.
- Online dependency-vulnerability lookup.
- A hosted service, web server, dashboard, user accounts, or database.
- Installing repository dependencies.
- Importing or executing analyzed project modules.
- Running the analyzed repository's tests or measuring runtime coverage.
- Claiming that security-hygiene analysis proves a repository is secure.

## 3. Architectural Approach

RepoInsight will use a hybrid modular analysis engine. The acquisition, inventory, analysis interfaces, normalized result models, scoring, CLI, and reports are native project components. External tools may be integrated through narrow adapters only when they provide clear value and emit machine-readable results. The application must remain useful when optional adapters are unavailable.

The CLI is a thin orchestration layer and contains no rule or scoring logic. Independent analyzers operate on a shared, read-only repository context and return normalized metrics and findings. Report renderers consume a stable analysis-result model rather than analyzer-specific output.

### 3.1 Core components

1. **Source acquisition** validates public GitHub URLs or local paths. Remote repositories are cloned into an isolated temporary directory; local repositories are never modified.
2. **Repository inventory** discovers Python source, tests, documentation, configuration, dependency metadata, CI workflows, containers, licensing, ignore rules, and Git metadata.
3. **Python parsing** produces safe AST-based representations without importing or executing analyzed code.
4. **Analysis engine** selects and runs eligible independent analyzers.
5. **Normalization** validates, orders, and deduplicates metrics and findings.
6. **Scoring engine** converts normalized evidence into category scores and a weighted overall score.
7. **Report layer** serializes a versioned JSON contract and renders a standalone HTML report from the same data.
8. **Configuration layer** merges built-in defaults, project configuration, and CLI overrides.

### 3.2 Extensibility requirement

Analyzer interfaces must make it possible to add another language, an online vulnerability adapter, or a browser dashboard without changing existing CLI commands, normalized findings, scoring contracts, or JSON consumers. Each analyzer declares its identity, version, required repository capabilities, emitted metrics or rule IDs, and execution entry point.

## 4. User Experience

The working distribution and command name is `repoinsight`.

### 4.1 Primary command

```bash
repoinsight analyze <source>
```

Examples:

```bash
repoinsight analyze https://github.com/owner/project
repoinsight analyze C:\Projects\my-project
repoinsight analyze . --output reports
repoinsight analyze . --format json
repoinsight analyze . --fail-under 70
```

### 4.2 Supporting commands

```bash
repoinsight rules
repoinsight explain <rule-id>
repoinsight version
```

- `rules` lists every available rule, category, default severity, score effect, and whether it is enabled.
- `explain` provides the rationale, evidence definition, limitations, and remediation guidance for one stable rule ID.
- `version` displays the application version and JSON schema version.

### 4.3 Configuration

Configuration precedence is:

```text
CLI arguments > .repoinsight.toml > built-in defaults
```

Configuration supports exclusions, file and repository limits, rule enablement, documented rule thresholds, category weights, output options, and CI score thresholds. Unknown or invalid configuration keys fail with actionable messages instead of being ignored.

## 5. Analysis Workflow

1. Parse CLI arguments and locate `.repoinsight.toml`.
2. Validate the source as a supported GitHub URL or local directory.
3. Acquire the source. Clone remote repositories into a temporary directory using a bounded history strategy; validate local paths without mutation.
4. Resolve repository boundaries and applicable ignore rules.
5. Build an inventory while enforcing file-count, file-size, and total-source-size limits.
6. Classify files and parse eligible Python files with the standard AST.
7. Run eligible analyzers independently against a shared read-only context.
8. Validate and normalize analyzer metrics and findings.
9. Deduplicate equivalent findings through stable rule and location identities.
10. Calculate category and overall scores.
11. Validate the complete result against the internal report model and JSON schema.
12. Write the requested JSON and HTML outputs atomically.
13. Print a concise terminal summary and return the appropriate exit code.
14. Remove temporary cloned data through guaranteed cleanup logic, including failure paths.

Remote Git analysis is explicitly labeled partial when only bounded recent history is available. Local repositories use all locally available history. Missing Git metadata disables maintenance metrics without blocking file analysis.

## 6. Findings and Metrics Contract

Every finding contains:

- stable rule ID;
- analyzer identity and version;
- category;
- severity;
- concise title;
- plain-language explanation;
- repository-relative file and line range when applicable;
- redacted supporting evidence;
- remediation guidance;
- score impact;
- confidence level;
- applicable limitations or suppression reason.

Severities are `info`, `low`, `medium`, `high`, and `critical`. Confidence values are `low`, `medium`, and `high`. Heuristic results, including possible secrets and duplicated-looking structures, must be explicitly labeled and must not be described as confirmed vulnerabilities or duplication.

Metrics have stable identifiers, typed values, units where applicable, provenance, and completeness state. Report output must distinguish zero from unavailable or skipped data.

## 7. Analysis Categories and Scoring

| Category | Weight | Core evidence |
|---|---:|---|
| Maintainability | 25% | Complexity, large functions/classes/modules, nesting, duplicated-looking structures, dead-code indicators, TODO/FIXME markers, and import organization |
| Testing | 25% | Test discovery, source-to-test ratio, test organization, framework/configuration evidence, CI test execution, and coverage configuration |
| Documentation | 15% | README completeness, installation and usage guidance, docstrings, contribution guidance, changelog, and examples |
| Security hygiene | 15% | Possible secrets, dangerous calls, insecure subprocess patterns, unsafe deserialization, risky temporary-file handling, and dependency pinning |
| Repository hygiene | 10% | License, ignore rules, dependency metadata, packaging, CI, Docker configuration, and issue/PR templates |
| Maintenance | 10% | Repository age when available, recent activity, commit frequency, contributors, and stale-development signals |

The overall score is the weighted average of available category scores from 0 to 100. If a category cannot be evaluated, the report marks it unavailable and renormalizes the remaining weights; it must never silently treat missing evidence as a perfect or zero score.

Default ratings are:

- 90–100: Excellent
- 80–89: Strong
- 70–79: Healthy
- 50–69: Needs improvement
- Below 50: High maintenance risk

Each category starts from a documented baseline. Rules add or deduct bounded points according to documented severity and evidence. Category scores are clamped to 0–100. The report exposes category weights, rule impacts, caps, unavailable evidence, and rounding behavior. Identical repository content, Git input, configuration, and tool version must produce identical JSON apart from explicitly nondeterministic run metadata such as timestamp and elapsed duration.

## 8. Static-Analysis Safety Boundary

RepoInsight treats every analyzed repository as untrusted. It must not:

- install dependencies;
- run build scripts, project commands, hooks, plugins, tests, or repository executables;
- import analyzed modules;
- evaluate Python expressions;
- enable executable report content from the repository;
- send source code, metadata, or findings to an external service.

Testing quality is inferred only from repository structure, static files, recognized configuration, and CI definitions. The tool must never report that tests pass or claim measured runtime coverage unless a future, separately designed execution feature provides verified evidence.

## 9. Filesystem, Privacy, and Report Safety

- Never modify the analyzed repository.
- Never follow symlinks outside the resolved repository root.
- Exclude `.git`, virtual environments, caches, build products, generated files, and vendored directories by default.
- Respect applicable ignore rules while allowing explicit analyzer safety exclusions to take precedence.
- Normalize report paths as repository-relative paths and prevent path traversal.
- Redact suspected secret values in logs, terminal output, JSON, HTML, exceptions, and test snapshots.
- Use no external JavaScript, fonts, analytics, images, or CDNs in HTML.
- Escape all repository-derived text before HTML rendering.
- Clean up temporary clones on success, failure, and interruption where the platform permits.

## 10. Error Model and Exit Codes

The application distinguishes:

1. **Fatal operational errors:** invalid source, failed acquisition, inaccessible root, invalid configuration, or inability to write required output.
2. **Partial-analysis warnings:** invalid Python syntax, unreadable files, unsupported encodings, unavailable or partial Git history, file-limit exclusions, and isolated analyzer failures.
3. **Repository findings:** quality and security-hygiene evidence produced by rules.

An individual analyzer failure is isolated so other analyzers can finish. The report records that analyzer's failure and marks affected categories incomplete. Internal failures are never converted into repository findings and never silently ignored.

Exit codes are stable and documented. They distinguish successful analysis, score-threshold failure, invalid usage or configuration, acquisition failure, analysis failure, and report-output failure. A partial report may still be produced when safe and useful, and its completeness state must be obvious.

## 11. Resource Limits and Performance

Configurable safeguards include:

- maximum individual file size;
- maximum files inventoried or analyzed;
- maximum total source bytes;
- bounded Git history for remote repositories;
- clone timeout;
- total analysis timeout where cross-platform behavior can be implemented safely.

Skipped or truncated inputs are disclosed with reasons. Results are sorted deterministically. Concurrency, if used, must be bounded and must not change output ordering.

The version 1 performance target is to analyze approximately 100,000 lines of Python in under 30 seconds on a typical modern laptop, excluding network cloning. This is a benchmark target, not a guaranteed service limit. A reproducible benchmark fixture and documented hardware/runtime context must accompany any published performance claim.

## 12. Reports

### 12.1 Terminal summary

The terminal displays source identity, overall rating, category scores, finding counts by severity, the highest-impact findings, output paths, skipped or incomplete analysis, and the process result. It remains concise and readable without color; color is an optional enhancement only when supported.

### 12.2 JSON report

JSON is a versioned public contract. It includes tool/schema versions, source metadata, configuration fingerprint, completeness information, repository inventory, metrics, findings, scores, Git summary, skipped inputs, analyzer status, timing, and limitations. A checked-in JSON Schema validates fixtures and every generated report before successful completion.

### 12.3 HTML report

HTML is generated from the same validated result model and contains no server dependency. It includes:

- overall and category scores;
- scoring explanation;
- repository inventory;
- severity and category filters;
- findings with file and line evidence;
- largest and most complex code units;
- testing and documentation indicators;
- security-hygiene warnings;
- recent Git activity;
- limitations, skipped files, and partial-analysis disclosures.

The report must be usable offline, keyboard-accessible for its primary interactions, responsive at common desktop and mobile widths, printable, and safe against injection from repository-controlled text.

## 13. Testing Strategy

- **Unit tests:** positive, negative, and edge-case fixtures for every rule.
- **Scoring tests:** weights, caps, severity impacts, disabled rules, unavailable categories, and deterministic rounding.
- **Parser tests:** valid Python, syntax errors, unusual supported encodings, generated content, and oversized files.
- **Security tests:** secret redaction, symlink containment, unsafe-pattern rules, HTML escaping, path normalization, and representative false-positive suppressions.
- **Git tests:** temporary repositories with controlled branches, contributors, dates, and histories.
- **CLI tests:** commands, options, configuration precedence, output formats, console behavior, and exit codes.
- **Contract tests:** JSON Schema validation and stable structural snapshots.
- **End-to-end tests:** local fixture repositories that verify terminal, JSON, and HTML outputs together.
- **Acquisition tests:** local Git remotes or mocks for normal tests; a small optional live GitHub test outside the required suite.
- **Performance tests:** a reproducibly generated large repository benchmark tracked separately from routine unit tests.

CI runs formatting, linting, static type checking, unit/integration tests, and coverage on Windows, macOS, and Linux across the supported Python range. Core acquisition, scoring, redaction, path-safety, normalization, and reporting code receives the strictest coverage expectations. Network access is not required for the standard test suite.

## 14. Distribution and Documentation

- Package metadata and dependencies are managed through `pyproject.toml`.
- The `repoinsight` console command is installed through a standard Python entry point.
- End users can install the released package with `pipx`.
- Releases are built from clean checkouts and include source and wheel distributions.
- Documentation includes installation, quick start, CLI reference, configuration reference, rule catalog, scoring methodology, architecture, security model, limitations, contribution guidance, examples, and report screenshots.
- The repository includes an appropriate license, changelog, code of conduct, contributing guide, security policy, issue templates, pull-request template, CI workflows, and release workflow.

## 15. Version 1 Acceptance Criteria

Version 1 is complete only when all of the following are true:

1. Public GitHub URLs and local directories work end to end.
2. Remote repositories are isolated and cleaned up; local repositories remain unchanged.
3. Malformed, unreadable, or oversized files cannot crash a complete scan.
4. Repository code is never imported, installed, or executed.
5. Every reported score is traceable to documented metrics and rule impacts.
6. Missing evidence is represented explicitly and scored according to the documented unavailable-category policy.
7. JSON output validates against its versioned schema and is deterministic under identical inputs.
8. HTML renders correctly offline and safely escapes repository-derived content.
9. Suspected secret values never appear in any output or diagnostic path.
10. Git-unavailable and partial-history modes are clearly disclosed.
11. `--fail-under` returns a distinct nonzero exit code when the score is below the requested threshold.
12. CI passes on Windows, macOS, and Linux across the supported Python range.
13. Installation through `pipx` works from a built package.
14. User and contributor documentation covers every public command, configuration key, scoring rule, limitation, and extension interface.
15. A tagged release can be produced reproducibly from a clean checkout.

## 16. Planned Post-1.0 Extensions

These are future possibilities, not version 1 requirements:

- JavaScript and TypeScript analyzers through the analyzer interface.
- Optional online dependency-vulnerability lookup.
- Private GitHub access with an explicit credential and threat model.
- A browser dashboard consuming the versioned JSON contract.
- Historical comparisons between report files.
- CI annotations and pull-request comments.
- Optional AI-generated explanations layered over deterministic findings.

Each extension requires its own design review and must preserve the static-analysis safety guarantees unless an explicitly separate execution mode is designed and approved.
