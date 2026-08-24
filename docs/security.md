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
