# Consolidated release readiness — 2026-10-06

**Six final-source platform/Python cells remain unverified. Packaging and all available full suites passed; release acceptance is still open.** The new Linux runs reduce the incoming Windows report’s nine missing cells to six. No production source change or API generation occurred.

## Current matrix

| Platform | Python | Full-suite evidence | Coverage / limitations |
| --- | --- | --- | --- |
| Linux | 3.11.16 | New: 505 passed, 1 skipped | Branch coverage saved; optional benchmark skip |
| Linux | 3.12.14 | Reused final-source: 505 passed, 1 skipped | Existing full-suite proof; no new coverage percentage claimed |
| Linux | 3.13.5 | New: 505 passed, 1 skipped | Branch coverage saved; optional benchmark skip |
| Linux | 3.14.7 | New: 505 passed, 1 skipped | Branch coverage saved; optional benchmark skip |
| macOS | 3.11 / 3.12 / 3.13 / 3.14 | Four cells unverified | No available macOS environment |
| Windows | 3.11 | Unverified | No available runtime |
| Windows | 3.12.14 | Imported: 503 passed, 3 skipped | Optional benchmark and two symlink-privilege skips |
| Windows | 3.13 | Unverified | No available runtime |
| Windows | 3.14.7 | Imported: 503 passed, 3 skipped | Optional benchmark and two symlink-privilege skips |

Linux full-suite logs and per-runtime coverage JSON are saved in `.artifacts/final-linux-matrix-2026-10-06/`. Each new run measured 88.58% combined coverage and 82.59% branch coverage. Windows logs/coverage are in `.artifacts/final-offline-validation-2026-10-05/` (actual run date 2026-10-06): 90.74% statement, 82.80% branch and 88.67% combined coverage. These measurements describe RepoInsight’s tests, not coverage of analyzed repositories.

All new Linux runs used existing cached environments copied outside the repository, imported the final source, and ran with provider credentials removed. No runtime/dependency download was needed. The 99 frozen Python hashes and all local corpus files match their pre-run snapshots. Matching Ruff/mypy evidence was reused. Windows source/package hashes also match the current implementation.

## Packaging and evidence intake

The incoming ZIP passed CRC/path/duplicate/exclusion checks and all 312 inventoried hash/size checks. SHA256: `728bf23f6e8eedc08f2a2317ca9d95d51e581ffa41341b6ce511165b78e10a8d`. The separately uploaded readiness report matches the archived report; its checkpoint adds only the final export verification note. Original checkpoints and logs are preserved as data under `.artifacts/final-offline-intake-2026-10-06/`; no uploaded scripts were executed.

Windows logs record byte-identical wheel and sdist pairs with a fixed epoch, successful strict Twine checks, 47 packaged-file checks and both schemas. Separate offline base-wheel and sdist[ai] installations passed pip check, static/preview smokes, and mocked success/failure sidecar checks with usage preservation. HTTPX is absent from the base install. Cached dependencies were reused with `--no-index/--no-deps`; cold dependency resolution remains untested.

The distributions themselves were excluded from the ZIP because the sdist contains fixture data. This intake verifies their recorded logs, hashes and member inventories; it does not independently rehash unavailable distribution bytes. Successful packaging proof is retained rather than repeating the builds. Version remains 1.0.0.

Prior static benchmark evidence remains applicable to the enrichment-only guard edits. The imported Windows comparison reported medians 14.914 seconds before and 13.312 seconds after; the earlier cloud comparison is a separate same-host measurement. These are retained measurements, not newly measured performance.

## Acceptance gates

- All 20 baseline cases were attempted using `gpt-6-luna`: 20 requests, zero retries, 28,533 input / 21,719 output tokens, including 15,094 reasoning tokens. No new paid requests or retries occurred.
- Original live results remain 16 successes and four failures. Cases 01/03/15 have separate offline recoveries; case 10 remains incomplete/unratable. Nineteen validated saved responses do not constitute nineteen useful ratings.
- The accepted single Astra review remains valid for its earlier corpus. No new rating was performed or inferred for prompt 1.3. Owner acceptance of final-prompt usefulness, truncation, field misses and other recorded advice caveats remains open.
- Variation remains an unresolved evaluation criterion. It requires a separately approved paid scope if pursued; no waiver or new budget is assumed.
- Six full-suite matrix cells and the two privilege-skipped tests on Windows 3.12/3.14 remain open. Linux symlink passes do not close Windows privilege checks.
- Version/changelog synchronization, commits/pushes, hosted CI and publication have not been authorized or performed.

## Exact next step

Run the six missing platform cells and the previously skipped Windows symlink tests on capable environments. Reuse all matching completed cells and packaging evidence. The [remaining-platform handoff](local-codex-remaining-platform-checks.md) gives the exact scope. Hosted runners may be the simplest way to obtain macOS and missing Windows versions, but publishing this uncommitted implementation and dispatching CI require separate approval. The existing CI workflow runs all 12 cells and has no six-cell selector.

After platform validation, resolve owner acceptance and the variation criterion before preparing a release. Preserve the existing [baseline and caveats](ai-baseline-2026-10-05.md); do not resend case 10 or repeat the earlier Astra review automatically.

## Local continuation verified — 2026-10-06

The Linux evidence packet passed all 17 inventoried size/hash checks, exact member coverage and CRC (18 members including manifest). Its 99 LF source hashes match this checkout. The previous Windows result ZIP and its 312 inventoried members, 47 package hashes and original 316-file corpus inventory were independently rechecked. Imported Linux evidence is retained under `.artifacts/linux-matrix-intake-2026-10-06/.artifacts/final-linux-matrix-2026-10-06/`; uploaded scripts were not executed. The supplied checkpoint remains intake data; local history was appended, not replaced. The local baseline doc differed from the supplied copy and was preserved.

Current Windows 3.12.14 and 3.14.7 imports each match all 47 final package files, prompt 1.3 and package 1.0.0. Credential-free symlink capability probes both failed with WinError 1314. No privilege settings changed; no targeted tests or completed full suites were rerun. Missing Windows 3.11/3.13 runtimes and all macOS cells remain unavailable locally. Six cells plus four symlink test/runtime results remain unresolved. No source change, fixture execution, download, new AI request/rating, or release action occurred. Linux packet metadata does not include a full OS/dependency inventory; the supplied runtime identifiers and logs are preserved without inventing those details.

Local logs, exact commands, dependency versions, snapshots, matrix status and CI review proposal are in `.artifacts/remaining-platform-validation-2026-10-06/`. The 45-file review diff targets local Git HEAD; three outer local edits require manual merge (README.md, .gitignore, ci.yml). Nothing was applied to those files. The proposed manual workflow covers six missing full-suite cells and two symlink-only jobs. Publishing a codex branch automatically triggers existing full 12-cell CI plus quality checks; the scoped proposal does not suppress that trigger. Owner approval of exact integration and hosted scope is required before publication/dispatch. Original AI failures and separate recoveries remain unchanged; final acceptance, variation and release decisions stay open.
