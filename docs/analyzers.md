# Analyzer extension guide

Version 1 ships six statically registered analyzers: maintainability, testing, documentation, security hygiene, repository hygiene, and maintenance history.

To add an analyzer in a future compatible release:

1. Define stable rule metadata in `analyzers/catalog.py`.
2. Implement the `Analyzer` protocol from `analyzers/base.py`.
3. Declare a stable analyzer ID, version, category, owned rule IDs, and required capabilities.
4. Read only from `RepositoryContext`. Never open arbitrary paths, import repository modules, invoke interpreters, or execute repository tools.
5. Emit typed `Metric`, `Finding`, and disclosure records with explicit completeness.
6. Register the instance explicitly in `analyzers/registry.py`.
7. Add boundary and absence-evidence tests. A skipped or unavailable input must not be treated as a measured zero.

Normalization is a trust boundary. It revalidates paths and text, applies redaction and deterministic ordering, and rejects duplicate metric IDs. Renderers must consume `AnalysisReport`, not analyzer-specific objects.

Runtime third-party analyzer loading is intentionally unsupported in version 1. This avoids executing code discovered inside an untrusted repository and keeps the public CLI and report contract stable.
