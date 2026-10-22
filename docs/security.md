# Security and privacy

## Version 1 threat model

Repository contents are untrusted and are never imported or executed. RepoInsight protects against ordinary path traversal, external symlink following, secret disclosure in outputs and diagnostics, unsafe HTML rendering, and temporary-directory leaks.

The scanner uses contained normalized report paths, refuses unsupported sources, bounds remote Git acquisition, disables interactive Git behavior and hooks for its clone command, uses a safe file inventory, parses Python with `ast`, revalidates analyzer output, redacts secret-like values, autoescapes repository text in HTML, validates JSON against a checked-in schema, and atomically replaces output files. Temporary remote clones are owned by a context manager and removed on success and failure.

RepoInsight does not execute tests, package metadata, build backends, Git hooks, project scripts, configuration Python, imported modules, or suspected commands found in source. Findings describe static evidence only.

## Out of scope

Version 1 does not attempt to defend against:

- a concurrent privileged local attacker mutating directories during a scan;
- a compromised operating system;
- a malicious or replaced system Git installation;
- a hostile executable `PATH`;
- an adversarial filesystem driver.

These cases require operating-system-level trust and isolation outside the product's approved scope. Run RepoInsight in an appropriately isolated environment when the host or toolchain is not trusted.

## Reporting a vulnerability

Follow [SECURITY.md](../SECURITY.md). Do not include real credentials, private repository contents, or exploit data in a public issue.

## Experimental AI enrichment

The experimental `enrich` command adds an explicit transmission mode for saved
static reports. `analyze` remains static and does not call AI (remote
GitHub acquisition still needs Git and network access). Only
`enrich --send` transmits data; a saved key or repository TOML cannot enable it.
`enrich --preview --model MODEL_ID` prints the complete request without a key or
network access or the optional HTTPX dependency. AI guidance was introduced in
1.1.0 and is included in published 1.2.0; the historical 1.0.0 package has no
enrichment. Only live send requires the AI extra, an accessible compatible model
and `OPENAI_API_KEY`. See the [walkthrough](examples/ai-guidance.md).

The outbound projection contains trusted built-in rule descriptions, rule IDs,
severity/confidence, numeric scores, selected numeric/boolean aggregate metrics,
and completeness/omission counts. It omits raw code, free-form repository text,
paths, URLs, revisions, timestamps, author identities, and commit messages.
Opaque evidence IDs map to file locations only in local AI reports. Selected
metrics and findings can still reveal characteristics of a private project.

The credential comes exclusively from `OPENAI_API_KEY` and is used only in the
authorization header when the user explicitly selects send mode. The key exists
in process memory during authentication and is sent to the API provider over
certificate-verified HTTPS. It is not bundled in the application, written to app
settings or a credential file, cached, or included in reports or request content.
RepoInsight does not load .env files. Static analysis and preview need no key and
make no AI request. This does not promise protection from a compromised OS or
third-party debugging/HTTP logging enabled outside RepoInsight.

RepoInsight rejects keys in request content, redacts the
exact active key from diagnostics and responses, and applies existing heuristic
redaction. Neither technique guarantees removal of every confidential value.
Do not commit keys or preview payloads containing confidential evidence.

The provider uses certificate-verified HTTPS to `api.openai.com/v1/responses`,
with redirects, environment proxies, and custom endpoints disabled. Requests
set `store: false`; this is not a guarantee of zero provider retention. Account
and provider data policies still apply. There is no request cache or telemetry.

The model receives no tools, executable context, source files, or retrieval
capabilities. Responses have size/field limits, must cite supplied evidence IDs,
and cannot add score fields. Direct file/line/URL citations are rejected. Model
prose is escaped into a self-contained HTML report with no active scripts or
external resources. Suggestions require developer review; no automatic edits
or test execution occur. Prompt instructions and heuristic prose checks cannot
prove that every natural-language claim is accurate.

Provider failures leave the static report intact. Each sidecar is written
atomically; the JSON/HTML pair is not a multi-file transaction. Request retries
are bounded to one for transient failures, and authentication errors are not
retried. Token limits do not guarantee an exact monetary cap.
