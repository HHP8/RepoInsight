# Before/after improvement walkthrough

Use a project you can safely edit and the [installed virtual environment](../../README.md#install).
Run from the environment's folder, replacing `PATH_TO_PROJECT` with your project
directory. Use the README's explicit Windows executable paths, or activate the
environment on macOS/Linux. Record a static report without an AI request:

```console
repoinsight analyze "PATH_TO_PROJECT" --output before --format all
```

Optional offline AI-payload preview (no key or optional HTTPX dependency):

```console
repoinsight enrich before/repoinsight-report.json --preview --model MODEL_ID
```

`MODEL_ID` is a placeholder for an OpenAI Responses API model with Structured
Outputs; preview checks only identifier syntax. Sending is a separate, potentially
paid choice with dependencies, credentials and model access described in the
[AI walkthrough](ai-guidance.md#optional-live-send). Whether
using deterministic remediation or AI guidance, choose one concrete change:

| Finding/evidence | Example developer action | Check |
|---|---|---|
| `RI-SEC-003`, shell execution pattern | Review whether a shell is needed; consider argument arrays for trusted command names | Review quoting and input handling, then test behavior separately |
| `RI-MAINT-001`, high complexity | Identify cohesive branches and consider helper extraction | Add branch/error cases, run project tests, then rescan complexity |
| Missing installation/usage documentation | Add commands verified against the project environment | Ask a reader to follow the instructions, then rescan documentation evidence |
| Sparse test evidence | Add meaningful normal, boundary, and failure-case tests | Run them separately; do not equate file ratios with runtime coverage |

Make your chosen change yourself and independently verify it, for example by
reviewing the behavior and running relevant project tests. RepoInsight does not
perform that verification. Then generate a second static report and compare the
two saved JSON files with the implemented 1.2.0 command:

```console
repoinsight analyze "PATH_TO_PROJECT" --output after --format all
repoinsight compare before/repoinsight-report.json after/repoinsight-report.json
```

To save a machine-readable comparison instead:

```console
repoinsight compare before/repoinsight-report.json after/repoinsight-report.json --format json --output comparison.json
```

Inspect `before/repoinsight-report.html` and `after/repoinsight-report.html` for
the specific finding and category. Check skipped inputs and completeness as
well as scores. An absent finding may reflect exclusions or missing evidence
rather than a fix. Use the same configuration and score contract for comparisons.
Comparing saved reports is offline: it does not rescan source or request AI.
Analyzing a remote GitHub URL instead of a local path requires Git and network
access. A higher score does not prove a security fix or runtime improvement;
see the [comparison contract and limits](../comparison.md).

No AI action changes files or runs tests. Keep original reports and inspect the
base hash/timestamp when reviewing older AI guidance.
