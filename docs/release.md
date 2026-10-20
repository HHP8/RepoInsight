# Release process

RepoInsight uses semantic version tags shaped `v1.0.0`. The package, runtime constant, new-report tool version, changelog, docs and tag
must agree. Schema, score-contract and analyzer identifiers are versioned
independently. Version 1.2.0 retains static schema,
score and comparison contracts 1.0 and analyzer metadata 1.0.0. Its regenerated
static/comparison schemas accept tool metadata 1.0.0, 1.1.0 and 1.2.0 only.
Saved older reports remain readable; older strict validators may reject new tool
metadata until updated. Unknown future versions are unsupported. Do not globally
replace historical version literals or alter the experimental AI contracts.

## 1.2.0 validation and publication

Version 1.2.0 adds saved-report comparison, absent from 1.1.0. Implementation
[candidate CI](https://github.com/HHP8/RepoInsight/actions/runs/37995687225) and
[main CI](https://github.com/HHP8/RepoInsight/actions/runs/37998558157) for `25ae05f`
passed all 12 supported OS/Python cells (588 passed, one optional benchmark skip
each) and quality. Windows named link passes use disclosed quiet-log node-order
inference. Final release-document changes require matching final-commit CI and
artifact validation; historical CI does not establish those results.

See the [release notes](release-notes-1.2.0.md). Record the final commit, signed
or protected tag, automatic tag build and verified uploaded asset hashes in the
release checkpoint. Any commit/push, tag or release action needs explicit scope
approval. PyPI publication is separate. No provider call or new AI rating is
required. Preserve earlier release assets and original AI evidence.

Local checks use every available supported development interpreter, explicit
nonsecret child environments and synthetic fixtures. Run the ordinary suite with
branch coverage, schema/documentation checks, format/lint/mypy and the offline
opt-in benchmark required below. Record privilege skips without weakening host
policy. Build twice from fresh clean candidate snapshots with a fixed
SOURCE_DATE_EPOCH and compare normalized member paths/bytes (ignore archive header
timestamps; normalize text CRLF to LF). Record both archive hashes; byte equality
is additional evidence rather than a substitute for member verification.
Check strict Twine metadata and inventories before separate non-editable wheel
and sdist installs. Base wheel needs no HTTPX; sdist[ai] smoke uses only a mocked
provider. Produce a controlled 1.2.0 static report, validate installed schemas,
compare/preview offline and verify input preservation. Keep raw distributions and
private reports out of sanitized handoffs. Publication requires bounded approval
against the final diff; reuse completed checks only when their content matches.

Before staging or exporting any release candidate, check the explicit file
allowlist and built wheel/sdist members for accidentally included credentials,
.env files, API headers, checkpoints, evaluation responses or local evidence.
Use synthetic credentials for offline tests. Never set a real OPENAI_API_KEY in
CI release validation; no live AI smoke or credential upload is required.

## Maintainer checklist

1. Start from a clean commit and update `CHANGELOG.md`.
2. Run formatting, lint, strict typing, the complete test suite with branch coverage, and the opt-in benchmark.
3. Generate representative JSON and HTML reports and validate JSON against the packaged schema.
4. Build wheel and sdist twice from clean archives and compare normalized contents.
5. Run Twine 7 metadata checks, which support the artifact's Core Metadata 2.5 contract.
6. Install wheel and sdist into separate disposable environments and run `version`, `rules`, `explain`, and local analysis smokes.
7. Run the optional public GitHub acquisition smoke when network access is available and verify clone cleanup.
8. Create and push the signed or protected `vX.Y.Z` tag. The tag-triggered workflow validates the release and builds artifacts but cannot publish to PyPI.
9. Create the GitHub Release from the validated tag and attach the reviewed artifacts.
10. To publish to PyPI separately, manually dispatch the Release workflow against the existing `vX.Y.Z` tag.
11. Approve the protected GitHub `pypi` environment. The manual publication job uses PyPI trusted publishing through GitHub OIDC and stores no API token.
12. Verify the published package, checksums, generated provenance, and installation instructions.

Tag pushes validate, build, and retain distribution artifacts without entering the PyPI publication job. PyPI publishing is available only from an explicit manual workflow dispatch against an existing version tag, after the build succeeds and the protected `pypi` environment is approved. Publishing is not performed by tags, tests, or pull requests.
