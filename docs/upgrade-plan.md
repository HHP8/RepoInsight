# RepoInsight upgrade plan

**Status:** AI MVP implemented in the development checkout; release evaluation pending. Sections below preserve the original proposal and estimates; see implementation status immediately below.  
**Date:** 2026-10-02  
**Baseline:** RepoInsight 1.0.0  
**Recommended next release:** 1.1, optional AI guidance over existing static evidence.

## Implementation status

Implemented: offline request preview, explicit send mode, minimized evidence with
opaque identifiers, environment credentials, bounded fixed-endpoint OpenAI
Responses transport, structured guidance validation, independent AI schema,
separate escaped JSON/HTML reports, failure records, tests, and worked examples.
Static v1 reports and scoring remain unchanged. Both modes require `--model MODEL_ID`
so preview shows the same request body as send. Package version remains 1.0.0
during development; the published 1.0.0 release does not include enrichment.

The 2026-10-03 source handoff includes prompt 1.2 and saved GPT-6 luna evaluation
evidence. Offline replay verifies 19 successful selected responses out of 20 cases;
case 03 remains truncated, and the selection mixes prompt versions 1.1 and 1.2.
On 2026-10-04, the owner explicitly requested a single Astra rating in place of
human review. The [AI review](ai-review-2026-10-04.md) rated 19/20 cases useful;
the owner approved continuation on 2026-10-04. This is an AI evaluation,
not human sign-off or confirmation that all release gates have passed.

Pending release gates include final-prompt consistency/variation evaluation,
cross-platform CI, and release/version synchronization. Prompt 1.3 now requests
and validates compact guidance, with offline checks passing; live
reliability has not yet been established. Report comparison, bounded
source context, rule-precision changes, and other later extensions remain planned.
See [AI workflow examples](examples/ai-guidance.md). Local resume details are in
`UPGRADE_PROGRESS.md` at the repository root.
The [evaluation guide](ai-evaluation.md) defines 20 curated review cases and the
maintainer rubric. A portable offline review packet and blank human rating sheet
are recorded in the checkpoint. Saved paid calls must not be repeated; future
live testing is restricted to `gpt-6-luna` without fallback.

## 1. Basis in the original project

This plan extends the [original design specification](../repoinsight-design.md), especially sections 3 (architecture), 6 (findings), 7 (scoring), 8–9 (safety and privacy), 12 (reports), and 16 (post-1.0 extensions). The current [architecture](architecture.md), [configuration](configuration.md), [analyzer guide](analyzers.md), [security model](security.md), and [limitations](limitations.md) supply the implementation constraints.

The current project already has six analyzers, 41 stable rules, and 52 metrics, as recorded in the [1.0 changelog](../CHANGELOG.md). It uses Python ASTs, transparent deterministic scoring, bounded Git acquisition, strict Pydantic models, schema-validated JSON, and offline HTML. The next release should make that evidence easier to understand and act on.

The original design excludes generative AI and external transmission from version 1, but explicitly proposes optional AI explanations after 1.0. This roadmap introduces a separately enabled network feature. Before releasing it, revise the product's privacy statements to describe that exception precisely. Repository code must still never be imported or executed.

## 2. Upgrade goals and priorities

| Priority | Improvement | User benefit | Target |
|---|---|---|---|
| P0 | Optional AI summary and explanations | Understand findings, limitations, and practical next steps | 1.1 |
| P0 | API key handling and payload preview | Control credentials and exactly what leaves the machine | 1.1 |
| P0 | Evidence-linked action plan | Receive a small, actionable improvement backlog | 1.1 |
| P0 | Worked examples and evaluation fixtures | Learn the workflow and verify that guidance is useful | 1.1 |
| P1 | Comparison of saved reports | See new findings, resolved findings, and score changes | 1.2 |
| P1 | Optional bounded source context | Get more specific refactoring and test suggestions | 1.2 |
| P1 | More precise static rules | Reduce avoidable noise in existing results | 1.2 |
| P2 | Online vulnerability lookup, other languages, CI annotations | Broaden the analysis after the first upgrades are validated | Later |

Keep the next release focused on one provider and report-based guidance. Hosted dashboards, private GitHub access, runtime test execution, automatic code edits, and additional providers are separate projects.

## 3. Recommended AI design

### Evidence first, guidance second

Keep `AnalyzeService` in `src/repoinsight/application.py` responsible for the current static report. Add a separate enrichment service that reads a validated saved report. The AI layer consumes an explicitly selected, redacted projection of that report and produces advisory text.

The first release should offer:

- A short repository-health summary with completeness caveats.
- Explanations of selected existing findings in plain language.
- Up to five prioritized actions, with rationale, rough effort, and a way to verify each change.
- Test and documentation suggestions anchored to available static evidence.

AI cannot change rule IDs, measured metrics, severities, confidence, category scores, overall scores, or `--fail-under` behavior. It cannot claim tests passed, measured runtime coverage, confirmed exploitability, or verified fixes. Suggestions beyond existing evidence must be labeled hypotheses requiring review.

Initially, send rule descriptions, sanitized findings, category scores, selected aggregate metrics, and completeness disclosures. Omit raw source, repository URLs, absolute paths, Git author identities, commit messages, and unnecessary metadata. Map locations to opaque evidence identifiers by default; display actual locations locally after validating references. Even this minimized payload can disclose information about a project, so show it before transmission when requested.

### API key and network boundary

- Use one explicitly registered OpenAI provider adapter for the MVP, behind a typed provider interface. Verify its current API and structured-output support during implementation; do not hard-code a model that may become unavailable.
- Read the credential from `OPENAI_API_KEY` in the process environment. Do not accept literal keys in CLI arguments or repository TOML, persist them, include them in fingerprints, or log HTTP authorization headers.
- Having an environment key must not enable AI automatically. Only the explicit `enrich --send` command permits transmission. A repository's `.repoinsight.toml` cannot grant consent, select a destination, or choose a credential environment variable.
- Keep provider, model, and network settings in explicit user command options for the MVP. Use the provider's fixed HTTPS endpoint with certificate verification; reject endpoint overrides and cross-origin redirects. Custom/local endpoints need a separate credential and network design later.
- Redact before transmission and again before output. Supplement heuristic redaction with exact removal of the active credential from diagnostics and responses. State that redaction cannot guarantee removal of every confidential value.
- Treat repository-derived text and model output as untrusted. Supply fixed instructions, separate evidence as data, and expose no tools, shell execution, retrieval, arbitrary URLs, or automatic edits to the model.
- Require structured output, validate its size and fields, and reject unknown evidence identifiers or fabricated file/line citations. Escape accepted text in HTML; render as plain text initially.

### Limits and failure behavior

Start with a maximum of 20 selected findings, 8,000 estimated input tokens, 1,500 output tokens, a 30-second request timeout, and at most one bounded retry for transient failures. Treat these as proposed defaults to tune with evaluation. Exceeding the input budget requires deterministic selection and a visible omission count; never silently upload more data. Authentication failures must not be retried.

Display token estimates before sending and actual usage when supplied by the provider. Only show currency estimates when a dated price source is available. A token limit is not an exact monetary cap; disclose uncertain accounting and possible retry charges.

Provider outages, invalid output, missing credentials, and budget exhaustion must leave the original report intact. For the new enrichment command, use existing invalid-usage code 20 for invalid options or missing credentials, report-output code 23 for output failures, and a new documented code 24 for enrichment failures. Existing `analyze` exit codes stay unchanged. Return success only when the requested enrichment was produced; store a sanitized failed-status record when possible.

## 4. Compatibility and implementation map

The current `AnalysisReport` and v1 JSON Schema reject unknown fields. Adding an `ai` field would break the existing contract. Write a separate `repoinsight-ai.json` with its own schema and a separate standalone `repoinsight-ai.html`; leave the original report files unchanged.

The AI document should include schema version, status, provider/model, prompt version, input payload hash, base report hash, base revision when present, generation time, usage, omitted evidence count, limitations, summary, and evidence-linked actions. Compute the base report hash from the exact input file bytes to bind guidance to that particular report. Cache identity should use the canonical redacted payload, provider/model, prompt version, and generation settings; disable caching by default and provide deletion controls if added later.

AI output is variable even at low temperature. Preserve the original deterministic scoring guarantee and expose AI provenance separately. A new scored rule or changed scoring policy needs documented contract/version treatment independently of the AI feature.

| Existing location | Planned work |
|---|---|
| `src/repoinsight/cli.py` | Add an `enrich` command, mutually exclusive preview/send modes, and explicit model/budget options |
| `src/repoinsight/application.py` | Retain static analysis orchestration; use its saved output as the enrichment input |
| `src/repoinsight/models.py` | Reuse static models without adding AI fields; place new strict models in proposed `ai/models.py` |
| `src/repoinsight/redaction.py` | Reuse and extend boundary redaction, including exact active-key removal |
| Proposed `src/repoinsight/ai/` | Implement payload selection, provider interface, OpenAI adapter, response validation, and service |
| `src/repoinsight/schema/` | Add an independently versioned AI schema; retain the existing v1 schema |
| `src/repoinsight/reporting/` | Add atomic sidecar writers and an escaped offline AI renderer |
| `src/repoinsight/exit_codes.py` | Add the enrichment-specific error code without renumbering existing codes |
| `pyproject.toml` | Add an optional `ai` dependency extra; ordinary installation remains sufficient for static analysis |
| `tests/unit`, `tests/security`, `tests/contract`, `tests/cli`, `tests/e2e` | Add mocked provider, privacy, schema, command, and combined-output coverage |
| `README.md`, `docs/cli.md`, `docs/security.md`, `docs/limitations.md`, original design | Document installation, opt-in transmission, contracts, limits, and the post-1.0 privacy exception |

The current source embeds version literals in `application.py` as well as exposing version metadata elsewhere. Audit those literals and synchronization tests when bumping the release; do not update only `pyproject.toml`.

## 5. Proposed user workflow

The static command below works today. All `enrich` commands and options are proposed. Set `OPENAI_API_KEY` through the shell or CI secret manager before using send mode; no real key is needed to develop or test this feature.

```console
# Current: produce deterministic evidence locally.
repoinsight analyze . --output reports --format all

# Proposed: inspect the exact redacted provider payload without network access.
repoinsight enrich reports/repoinsight-report.json --preview --model <supported-model>

# Proposed: explicitly send that evidence and generate separate AI reports.
repoinsight enrich reports/repoinsight-report.json --send --model <supported-model> --output ai-reports
```

Require exactly one of `--preview` or `--send`; calling the command without a mode shows an actionable usage error. Preview must use the same selection/redaction code as send and require no credential. Fail clearly if the optional dependency extra is missing.

Generating guidance from a saved report can describe an older revision. Show the report timestamp/revision and its hash in the AI HTML. Report-only mode must not read the current repository or suggest that it verified current source.

## 6. Concrete improvement examples

These illustrate expected output, not results of a new scan.

| Evidence | Expected improvement | Verification |
|---|---|---|
| `RI-MAINT-001` flags a branch-heavy function | Explain complexity and suggest reviewing input validation and branch responsibilities; detailed helper extraction requires later source context | Developer reviews behavior, adds branch cases, and reruns the static scan |
| `RI-SEC-003` reports a shell execution pattern | Explain why shell interpretation may be risky and give a generic argument-list alternative; disclose that input provenance is unknown | Developer reviews quoting/behavior and checks whether the pattern remains |
| Testing evidence shows few discovered tests or no coverage configuration | Suggest normal, boundary, and error-case tests for known public interfaces; explain that the ratio does not measure test quality | Developer runs the project's tests separately; RepoInsight reassesses static evidence |
| Documentation evidence lacks installation or usage guidance | Draft a short README outline with clearly marked command placeholders | Maintainer verifies commands in the project's own environment and updates the README |
| A later comparison shows a finding resolved but lower completeness | Explain the score change alongside newly skipped inputs | Compare only compatible score contracts/configurations and inspect missing evidence |

Add a proposed `docs/examples/` guide with an offline walkthrough, an AI preview/send walkthrough, and a before/after improvement walkthrough. Reuse the existing `healthy`, `problematic`, `suspected_secret`, and `partial_history` fixtures where possible. Use synthetic credentials and mocked responses; never publish real keys or private code. Preserve the secret and partial-history cases to show limitations, not just successful examples.

## 7. Delivery milestones

Estimates assume one developer familiar with the codebase. They are effort ranges, not calendar commitments; provider evaluation and security fixes may extend them.

| Milestone | Estimate | Deliverables | Completion gate |
|---|---|---|---|
| M1: contracts and privacy | 2–3 days | Payload projection, evidence identifiers, AI schema, consent modes, provider selection, version/privacy changes | Existing v1 reports still validate; preview sends nothing; repository configuration cannot enable transmission |
| M2: provider and service | 4–6 days | Optional dependency, environment credential reader, mocked adapter, structured-response validation, limits and failure status | Valid guidance references only supplied evidence; credential, timeout, malformed-response, and retry cases pass |
| M3: CLI, reports, examples | 3–4 days | `enrich`, separate JSON/HTML, usage disclosure, three walkthroughs | End-to-end mocked workflow works offline and preserves original reports and exit behavior |
| M4: evaluation and release | 3–5 days | Evaluation corpus, privacy/injection fixtures, docs, packaging, compatibility and performance checks | Release criteria below pass; any live evaluation uses explicitly authorized synthetic/public evidence |

Recommended 1.1 scope is M1–M4, approximately 12–18 developer days. Ship only after the gates pass. Build report comparison next, then bounded source context; do not make either a dependency for the AI MVP.

## 8. Evaluation and release criteria

Use at least 20 curated cases spanning all six categories, no-Git/partial history, malformed inputs, secrets, repository prompt injection, and sparse evidence. Standard tests use recorded synthetic responses and mocks, require no API key, and prohibit network calls. Live provider evaluation is a separate opt-in activity because it transmits data and incurs charges.

Release criteria:

1. Static commands, v1 schemas, scoring, and threshold exit codes retain their existing behavior; ordinary analysis makes no AI network request.
2. Preview requires no key and shows the complete outbound evidence. Repository-controlled configuration cannot authorize network access or redirect credentials.
3. Synthetic secrets and the active API key appear in none of the payloads, outputs, errors, or snapshots. Document residual redaction limits.
4. Every accepted citation resolves to supplied evidence. Reject unsupported paths, line ranges, unknown identifiers, and schema-invalid output.
5. Injection fixtures cannot trigger tool execution, extra requests, score changes, or unsafe HTML. Inspect accepted prose for misleading instruction-following during evaluation.
6. Provider failures and enrichment output failures leave the base report untouched and return documented results.
7. A maintainer rates at least 80% of evaluated responses useful and actionable under a written rubric; accepted evaluation outputs contain no unsupported claims that tests passed or vulnerabilities were confirmed. If this fails, narrow the prompts/features before release.
8. Existing cross-platform CI and package checks pass across Python 3.11–3.14. Test optional-extra installation and ordinary installation separately.
9. Rerun the reproducible static benchmark and compare against the existing baseline; investigate a median slowdown over 10%. Keep provider latency separate from static timing and from the original 30-second benchmark target.

## 9. Follow-on upgrades

**Report comparison (1.2):** Add proposed `repoinsight compare before.json after.json`. Validate both inputs, match findings by rule and location with disclosed rename/line-shift limits, distinguish new/resolved/unchanged evidence, and show score and completeness changes. Flag different configurations, tool/scoring contracts, and partial inputs; do not present incomparable scores as regression proof. Start with local terminal/JSON output; defer publishing PR comments.

**Bounded source context (1.2):** Add an independently enabled mode for selected finding snippets. Existing acquisition deletes temporary clones before returning, so later source access requires a deliberate change: construct a bounded redacted snapshot while acquisition is active, or separately reacquire the exact revision. For local sources, detect content changes. Apply inventory exclusions, path containment, byte/token caps, and explicit source-transmission consent. Show the exact payload and label suggestions unverified. Never send the whole repository automatically.

**Static precision (1.2):** Select noisy rules based on curated positive/negative fixtures and user reports. Candidate work includes better distinction between production/test shell patterns, recognized test layouts, and lock/constraint evidence. Publish measured false-positive improvements and resulting score changes; keep rule IDs stable where semantics remain compatible.

**Later extensions:** Online dependency vulnerability lookup should resolve supported dependency/lock formats without installation, disclose advisory freshness, and distinguish unavailable data from no known advisories. Language support should use the explicit analyzer protocol and registry. CI annotations should consume validated reports and require separate authorization for external writes. Each extension gets its own design, contract treatment, and failure model before implementation.
