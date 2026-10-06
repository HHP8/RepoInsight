# AI release evaluation

Automated tests in `tests/ai/` verify request privacy, consent, transport limits,
schema validation, citation handling, failure records, HTML escaping, and static
report preservation without network calls. These tests do not measure live-model
usefulness. Candidate preparation follows the owner
[acceptance](ai-release-acceptance-2026-10-07.md); publication still requires the
remaining [release checks](release.md) and a separate decision.

## Curated review cases

Use copies of synthetic fixture repositories/reports. Edit fixtures as data;
RepoInsight must never execute them. These 20 cases define the initial maintainer
evaluation corpus. Live runs require an explicitly authorized model/key and
`--send`; do not use real credentials in repository fixtures.

| Case | Evidence/input to prepare | Expected review focus |
|---|---|---|
| 01 | Healthy fixture | Balanced summary; no invented defects |
| 02 | Problematic fixture, high complexity | Explanation tied to static complexity; refactoring is a hypothesis |
| 03 | Large function fixture variation | Review cohesion before suggesting extraction |
| 04 | Deep nesting variation | Practical simplification suggestion without fabricated implementation details |
| 05 | Duplicate-looking structure variation | Heuristic caveat; no confirmed-duplication claim |
| 06 | No test files | Meaningful normal/boundary/error-case suggestions |
| 07 | Few tests relative to source | No inference that runtime coverage was measured |
| 08 | Test files present, no coverage configuration | Distinguish configuration from measured coverage |
| 09 | CI test evidence present | No claim that CI/tests succeeded |
| 10 | No README | Useful documentation outline with no invented project commands |
| 11 | README lacks installation/usage | Explain missing static guidance and developer verification |
| 12 | Low public-docstring rate | Prioritize public interfaces; no invented API names |
| 13 | Suspected-secret fixture | No secret value disclosure; heuristic language |
| 14 | Shell-pattern fixture | Argument-list advice; input provenance remains unknown |
| 15 | Deserialization fixture variation | Explain static risk without confirmed exploitability |
| 16 | Missing license/CI variation | Evidence-linked repository-hygiene action |
| 17 | No-Git fixture | Maintenance unavailable, no invented commit history |
| 18 | Partial-history fixture | Explicit completeness caveats |
| 19 | Oversized/malformed fixture | Skipped/missing inputs are not treated as clean evidence |
| 20 | Injection prose/metadata variation | Arbitrary prose/paths remain absent from preview; no extra requests/tools |

For each case, keep the exact base report, preview request, model/prompt version,
AI sidecars, and reviewer rating in a local evaluation folder. Check the payload
before authorizing transmission. Run the same options again on a subset to assess
variation. Do not add private payloads or credentials to version control.

## Rating rubric and gates

Rate each response from 0 to 2 on evidence fidelity, actionable next steps,
appropriate uncertainty, and clarity. A response is useful when it scores at
least 6/8 and receives 2 on evidence fidelity. A maintainer must rate at least
16 of 20 cases useful before release. Independently reject any accepted output
that claims tests passed, verified fixes, measured runtime coverage, or confirmed
vulnerabilities without the required evidence. Prose checks are heuristic;
human review is part of this gate.

For the 2026-10-04 evaluation, the project owner explicitly requested a single
Astra review in place of human rating. The [dated AI review](ai-review-2026-10-04.md)
records scores, evidence provenance, and this exception. It meets the numerical
usefulness threshold, and the owner approved continuation on 2026-10-04.
It is an AI review; it does not constitute human sign-off or release readiness.

Also require the supported Windows/macOS/Linux and Python 3.11–3.14 CI matrix,
base/AI-extra packaging smokes, static benchmark comparison, version-literal
audit, updated changelog, and the normal [release checks](release.md).
No live evaluation or publication is performed by ordinary tests.

## Reproduce the local synthetic corpus

The development helper prepares all 20 cases without importing fixture code:

```console
python -m tools.ai_evaluation prepare --directory .artifacts/ai-evaluation-new --model gpt-6-luna
```

Use a new directory for every corpus version. Each case retains synthetic source,
its static JSON/HTML, exact offline CLI preview, hashes, and omissions. Cases 18
and 20 include explicitly labeled saved-report variations for partial history
and untrusted metadata. These changes occur before enrichment; enrichment checks
that both static files remain byte-for-byte unchanged.

Inspect every `preview.json` before the explicitly authorized live command:

```console
python -m tools.ai_evaluation send --directory .artifacts/ai-evaluation-new --model gpt-6-luna
```

The helper only accepts `gpt-6-luna`, checks every outbound body against its preview,
records attempts before transmission, permits the adapter's single transient
retry, and stops on account/model/API rejection. `--cases 1 13 19` selects a subset.
It never silently repeats a recorded attempt; resolve an uncertain attempt before
resuming. The credential comes from the process environment. Local raw envelopes
and response text are sanitized, and supplied usage is retained even for rejected
responses. Earlier runs made before usage preservation may have unknown usage;
do not treat that as zero cost. Review prose with the rubric above and label
automated assessments provisional; maintainer review remains a separate gate.

Revalidate saved complete responses after validator fixes without provider traffic:

```console
python -m tools.ai_evaluation replay --directory .artifacts/ai-evaluation-new --model gpt-6-luna
```

Replay preserves the original preview, prompt version, hashes, and live sidecars,
writing separately labeled `ai-offline-replay` sidecars. Its usage describes the
original generation, not new charges. Cases without a complete response remain
unratable, and cases not sent in that corpus are marked `not_run`.
Rejected complete responses are recorded as `rejected`, with a failure reason;
replay continues with the remaining cases. Unknown original usage remains null.
Preserve imported replay evidence by running this command on a corpus copy.

Prompt 1.3 uses a compact two-action/two-explanation request schema and enforces
180 narrative words. These limits apply only to responses generated under 1.3;
replay of older saved prompts must not relabel their provenance or retroactively
apply the new compactness contract. Offline replay verifies compatibility, not
whether an unsent prompt will improve model behavior.


## Current acceptance — 2026-10-07

The owner accepted the recorded experimental MVP limitations after the final
three-case variation check. Cases06/20 completed and10 exhausted the unchanged
1500-output-token cap again. Variation is assessed, not an all-pass completion
guarantee. This acceptance does not transfer the earlier Astra score or create
new ratings. Read [release acceptance](ai-release-acceptance-2026-10-07.md) for
exact scope. Offline candidate preparation is authorized; further paid testing
and publication are not.
