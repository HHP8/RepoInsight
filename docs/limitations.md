# Known limitations

- Python is the only language with AST-level analysis in version 1. Other files contribute bounded repository evidence only.
- Static structure cannot prove runtime correctness, code quality, exploitability, test effectiveness, documentation accuracy, or maintenance intent.
- Duplicate-looking code, unused private definitions, secret-like strings, dependency pins, and complexity are heuristics with documented false-positive and false-negative limits.
- Git maintenance metrics are unavailable outside a repository. Public GitHub acquisition intentionally uses bounded recent history and is marked partial.
- Ignore handling is rooted and intentionally does not implement every exotic Git worktree or adversarial filesystem race semantic.
- Unreadable, oversized, malformed, unsupported-encoding, excluded, or deadline-skipped inputs are disclosed and reduce completeness rather than being treated as clean evidence.
- Repository-local configuration for a remote source cannot retroactively weaken clone limits because it is read only after bounded acquisition.
- HTML uses inline CSS and JavaScript so one file works offline. A restrictive CSP blocks every other resource type; consumers that prohibit inline assets may need the JSON report.
- Version 1 does not defend against concurrent privileged mutation, a compromised OS, malicious system Git, hostile executable `PATH`, or adversarial filesystem drivers.

Nonessential edge cases that require operating-system-level defenses are documented rather than silently expanding the version 1 threat model.

## Experimental AI enrichment limitations

- AI guidance is experimental. The owner accepted the recorded MVP limitations;
  this is not a guarantee of usefulness or completion on every input.
- The default 1500-output-token cap includes reasoning. Saved case 10 exhausted
  this cap in both the original and variation attempts. Incomplete JSON is rejected
  with usage retained; truncation is not retried automatically and may incur charges.
- Individual requested field lengths are prompt instructions; runtime validation
  enforces the overall 180-word cap and compact sections. Historical field misses,
  grouped-evidence citations and verification-detail caveats remain recorded.
- Guidance describes a saved report, which may represent an older revision. It never checks current source or runs tests.
- AI output is variable, advisory, and may be wrong. It cannot change deterministic scores or confirm security, coverage, runtime behavior, or a fix.
- The evidence projection intentionally omits source snippets, arbitrary finding prose, identity, and paths. Detailed project-specific code edits are outside this release.
- Conservative byte-based token estimates can omit findings sooner than an exact tokenizer would. Omission counts are explicit; retry usage can exceed the last successful response's reported usage.
- Direct file/line/URL citations and a small set of unsupported verification claims are rejected heuristically. The checks may reject otherwise useful prose and do not catch every misleading statement; developer review remains necessary.
- A model supporting Responses and Structured Outputs must be explicitly selected. Access, supported features, provider latency, pricing, and retention policies depend on the account/provider.
- HTTP timeouts and deadline checks bound transport stages and streaming; they are not an operating-system hard deadline for every network/OS failure.
- An output failure can leave only one refreshed sidecar because writes are atomic per file. The base report stays unchanged; use recorded status/hash/timestamps to identify results.
