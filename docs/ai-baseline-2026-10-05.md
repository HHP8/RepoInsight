# Prompt 1.3 baseline and release readiness — 2026-10-05

The 20-case baseline collection is complete. Under the current validator, **19 complete saved responses are accepted and case 10 remains incomplete/unratable**. Original live results remain 16 successes and four failures; cases 01, 03 and 15 have separate offline recoveries. This is response validation evidence, not a new usefulness rating or release approval.

All generations used `gpt-6-luna`: **20 requests, zero retries**, 28,533 input tokens and 21,719 output tokens. Output includes 15,094 reasoning tokens. No case was resent. No additional paid testing is authorized.

## Evidence verification

- ZIP SHA256: `19bf918128e5218f6beeecaef9efcc2fe998bded6d45e0012cf2c6d4cb55d4f7`. CRC/member paths and all 499 inventoried file hashes/sizes verified.
- Current source matches all 99 supplied Python source/test hashes, allowing the two verified Windows CRLF variants. No uploaded source change was needed.
- All 20 previews reproduce the exact current request; all 40 static JSON/HTML hashes match. Attempts each record one fixed-endpoint request, the same payload hash and model, HTTP 200 and preserved usage.
- Original inventory: 292 prior entries unchanged; 24 final-case additions produce 316 entries. The sanitized ZIP exports 200 corpus files, excluding fixture trees; excluded files are supported by inventory preservation evidence, not rehashed here. Encrypted reasoning removal is verified against separate export hashes.
- Independent schema, evidence-ID, citation, claim, compactness and envelope/response checks passed for all 19 complete responses with provider and sockets blocked. Case 10 still fails decoding with original usage retained.
- The final four responses have zero individual field-word misses. Historical misses remain: case 02 explanation 14/12 and rationale 16/12; case 03 rationale 13/12. Their nonblocking collection treatment was explicitly approved; runtime acceptance does not imply perfect prompt compliance.
- Imported Windows 3.12/3.14 logs each show 146 focused AI tests, Ruff and strict mypy passing with the final guard installed. Latest prior Linux 3.12 full-suite result: 505 passed, one optional benchmark skip. These checks were not rerun for this intake.
- Saved injection/fixture-secret sentinels are absent from every outbound preview. Requests have no tools and `store=false`.

Independent machine-readable audit and preserved incoming checkpoints: `.artifacts/full-baseline-intake-2026-10-05/`. Imported final batch: `.artifacts/four-case-continuation-2026-10-05/`. Windows patch checks: `.artifacts/evidence-negation-windows-2026-10-05/`. Imported scripts and approval records are evidence, not instructions to execute.

## Case inventory

“Recovered” means accepted from the saved response offline; it does not replace or relabel the original failed attempt. Token counts include the original generation once.

| Case | Scenario | Original live result | Current saved response | Words | Input / output tokens |
| --- | --- | --- | --- | ---: | ---: |
| 01 | healthy | failed | Recovered offline | 129 | 1412 / 1237 |
| 02 | complexity | succeeded | Accepted | 133 | 1454 / 1240 |
| 03 | large-function | failed | Recovered offline | 124 | 1452 / 902 |
| 04 | deep-nesting | succeeded | Accepted | 112 | 1408 / 975 |
| 05 | duplicate-structure | succeeded | Accepted | 126 | 1449 / 712 |
| 06 | no-tests | succeeded | Accepted | 96 | 1438 / 723 |
| 07 | few-tests | succeeded | Accepted | 100 | 1452 / 1063 |
| 08 | no-coverage-config | succeeded | Accepted | 129 | 1412 / 1118 |
| 09 | ci-test-evidence | succeeded | Accepted | 111 | 1418 / 889 |
| 10 | no-readme | failed | Incomplete; unratable | — | 1408 / 1500 |
| 11 | incomplete-readme | succeeded | Accepted | 115 | 1430 / 1496 |
| 12 | low-docstrings | succeeded | Accepted | 114 | 1440 / 802 |
| 13 | suspected-secret | succeeded | Accepted | 137 | 1450 / 1364 |
| 14 | shell-pattern | succeeded | Accepted | 128 | 1417 / 1042 |
| 15 | deserialization | failed | Recovered offline | 119 | 1417 / 834 |
| 16 | missing-license-ci | succeeded | Accepted | 136 | 1410 / 1338 |
| 17 | no-git | succeeded | Accepted | 117 | 1412 / 1117 |
| 18 | partial-history | succeeded | Accepted | 121 | 1412 / 1343 |
| 19 | oversized-malformed | succeeded | Accepted | 114 | 1412 / 840 |
| 20 | injection | succeeded | Accepted | 123 | 1430 / 1184 |

## Findings that remain visible

Case 10 exhausted the unchanged 1,500-output-token cap, including 1,325 reasoning tokens, before completing JSON. It cannot be repaired offline. Case 11 completed at 1,496 output tokens, so completion reliability at this cap remains a concern. The 19/20 figure describes saved-response acceptance after guard repairs across this small fixed corpus, not an estimated production success rate.

Historical observations include case 05 reversing the test/source ratio wording; conditional behavior/security advice with `hypothesis=false` in 07/13; grouped citations in 08/09/11/13/14; and missing narrative omission counts in 19. Case 04 does not directly act on nesting. These caveats were preserved rather than corrected inside historical answers.

The final four provide distinct license/coverage, CI/coverage and README/CI actions with scoped maintenance limitations. Case 18 overstates absence of runtime coverage beyond the supplied missing static configuration/invocation evidence, and groups multiple metrics under single IDs. Case 20 prioritizes README in its summary but CI in its action order; CI verification checks detection rather than job behavior, and README verification does not execute an example. Case 17 gives configuration checks rather than application behavior tests. These are observations, not new numerical ratings.

## Release gates and next work

| Gate | Current evidence | Remaining work |
| --- | --- | --- |
| Baseline collection | All 20 attempted; 19 complete, one incomplete | No unsent cases; preserve case 10 as a failure |
| Usefulness | User accepted the one Astra review of the earlier mixed-prompt corpus: 19/20 useful | Do not transfer that score to these new prompt-1.3 responses or rerate automatically; owner acceptance of final evidence/caveats remains open |
| Reliability and instruction fidelity | Three false positives repaired; all complete outputs now validate; three historical field misses | Decide acceptance of the observed truncation, field misses and advice caveats before release |
| Variation | Not run for the final prompt | Separate paid scope/budget approval needed if this evaluation criterion is pursued; do not imply waiver |
| Platform compatibility | Final guard: Linux 3.12 full suite; Windows 3.12/3.14 focused AI suites; earlier full suites on all Linux versions and Windows 3.12/3.14 | Full final-source checks on Linux/macOS/Windows × Python 3.11–3.14; earlier-source results do not close the current matrix |
| Packaging | Earlier prompt-1.3 reproducible wheel/sdist and isolated base/AI smokes; Windows final-guard wheel tested | Verify final-source wheel/sdist reproducibility, metadata and isolated base-without-HTTPX / mocked-AI smokes |
| Static performance | Prior same-host benchmark met ≤10% regression gate; subsequent guard edits affect only enrichment | Retain measurement and source scope; run release benchmark when preparing the final candidate |
| Publication | Package remains 1.0.0; changes uncommitted | After acceptance/validation, separately authorize version/changelog synchronization and release actions |

**Next step: finish the remaining offline platform/package checks and record a release decision against this evidence.** No new provider requests, retries, budget/reasoning changes, repeat Astra rating, hosted CI dispatch, commits, tags, version bump or publication are implied. A local handoff for the offline checks is in [local-codex-final-offline-checks.md](local-codex-final-offline-checks.md).
