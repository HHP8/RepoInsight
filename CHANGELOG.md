# Changelog

All notable changes to RepoInsight are documented here.

## 1.2.0 - 2026-10-20

- Added offline `compare BEFORE.json AFTER.json` with readable terminal output,
  deterministic JSON, optional atomic file output and exact input byte hashes.
- Match findings by rule, analyzer and exact normalized location, preserving
  duplicates as a multiset and disclosing repeated/locationless ambiguity.
  Renames and line shifts can appear as removals/additions; no fuzzy matching.
- Show matched attribute and suppression changes; suppression is not a fix.
  Missing findings under incomplete coverage or incompatible metadata are
  no longer observed, with uncertainty, rather than proven resolved.
- Show observed overall/category score deltas, coverage, warning/skip changes
  and source/configuration/tool/analyzer compatibility qualifications.
- Share bounded 16 MiB schema/model validation with offline enrichment, retaining
  its loader import compatibility, redaction and read-only input boundaries.
- New reports identify tool 1.2.0. Updated static and comparison metadata enums
  accept 1.0.0, 1.1.0 and 1.2.0; unsupported future versions still fail safely.
  Older strict validators need the updated schemas for 1.2.0 metadata.
- Retain static schema/scoring and comparison contracts at 1.0, analyzer versions
  at 1.0.0, rule IDs and experimental AI prompt/request/response behavior.
  No source-context mode, rule tuning or new live AI evaluation is included.

## 1.1.0 - 2026-10-07

- Added experimental opt-in AI guidance over minimized saved-report evidence,
  offline preview, explicit send consent and separate JSON/HTML sidecars.
- Added optional HTTPX transport, fixed certificate-verified provider endpoint,
  bounded request/response budgets, evidence validation and sanitized failure
  records preserving supplied usage and original static reports.
- Read API credentials only from the process environment; no bundled or saved
  keys, repository credential settings, key arguments or automatic AI calls.
  Explicit send uses the provider's HTTPS authorization header; keys are excluded
  from request content and redacted from application diagnostics and AI reports.
- Added examples, privacy/limit documentation and offline regression coverage.
- Retained static scoring, analyzer versions and schema/score contracts at 1.0.
  New reports identify tool version 1.1.0; updated v1 metadata validation accepts
  both 1.0.0 and 1.1.0 saved reports. Older strict schemas may reject the new tool
  version and should be updated with the package.
- AI guidance is advisory and variable. The original evaluation and a separate
  variation trial both left case 10 incomplete at 1500 output tokens, including
  reasoning. Failure can incur charges; no complete answer is guaranteed and
  incomplete guidance is rejected rather than reconstructed.

## 1.0.0 - 2026-08-24

- Added safe local-directory and bounded public-GitHub acquisition.
- Added deterministic inventory, Python AST index, six analyzer families, 52 metrics, and 41 stable rules.
- Added completeness-aware scoring with traceable caps and weights.
- Added Typer commands, stable exit codes, canonical schema-validated JSON, terminal summaries, and standalone offline HTML.
- Refined the offline HTML report with section navigation, prioritized collapsible findings, accessible filtering, and clearer completeness states.
- Added representative fixtures, opt-in 100,000-line benchmark, cross-platform CI, governance, and trusted-publishing release assets.
- Validated the complete test, formatting, lint, and strict typing gates; reproducible wheel/sdist builds; Twine metadata checks; isolated installs; and bounded public-GitHub acquisition.

Version 1.0 intentionally performs static analysis only and does not execute repository code.
