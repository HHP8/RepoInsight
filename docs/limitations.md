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
