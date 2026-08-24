# Release process

RepoInsight uses semantic version tags shaped `v1.0.0`. The package, runtime constant, schema version, score contract, changelog, docs, and tag must agree.

## Maintainer checklist

1. Start from a clean commit and update `CHANGELOG.md`.
2. Run formatting, lint, strict typing, the complete test suite with branch coverage, and the opt-in benchmark.
3. Generate representative JSON and HTML reports and validate JSON against the packaged schema.
4. Build wheel and sdist twice from clean archives and compare normalized contents.
5. Run Twine 7 metadata checks, which support the artifact's Core Metadata 2.5 contract.
6. Install wheel and sdist into separate disposable environments and run `version`, `rules`, `explain`, and local analysis smokes.
7. Run the optional public GitHub acquisition smoke when network access is available and verify clone cleanup.
8. Create and push the signed or protected `vX.Y.Z` tag.
9. Approve the protected GitHub `pypi` environment. The release workflow uses PyPI trusted publishing through GitHub OIDC and stores no API token.
10. Verify the published package, checksums, generated provenance, and installation instructions.

The workflow refuses non-version tags, builds once, checks metadata, uploads artifacts, and publishes only from the protected release job. Publishing is not performed by tests or pull requests.
