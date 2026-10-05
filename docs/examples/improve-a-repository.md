# Before/after improvement walkthrough

Use a repository you can safely edit. Record its current static report:

```console
repoinsight analyze PATH_TO_PROJECT --output before
repoinsight enrich before/repoinsight-report.json --preview --model MODEL_ID
```

Sending is optional and follows the [AI walkthrough](ai-guidance.md). Whether
using deterministic remediation or AI guidance, choose one concrete change:

| Finding/evidence | Example developer action | Check |
|---|---|---|
| `RI-SEC-003`, shell execution pattern | Review whether a shell is needed; consider argument arrays for trusted command names | Review quoting and input handling, then test behavior separately |
| `RI-MAINT-001`, high complexity | Identify cohesive branches and consider helper extraction | Add branch/error cases, run project tests, then rescan complexity |
| Missing installation/usage documentation | Add commands verified against the project environment | Ask a reader to follow the instructions, then rescan documentation evidence |
| Sparse test evidence | Add meaningful normal, boundary, and failure-case tests | Run them separately; do not equate file ratios with runtime coverage |

After reviewing and implementing the change yourself:

```console
repoinsight analyze PATH_TO_PROJECT --output after
```

Inspect `before/repoinsight-report.html` and `after/repoinsight-report.html` for
the specific finding and category. Check skipped inputs and completeness as
well as scores. An absent finding may reflect exclusions or missing evidence
rather than a fix. Use the same configuration and score contract for comparisons.
The automatic `compare` command remains a later roadmap item.

No AI action changes files or runs tests. Keep original reports and inspect the
base hash/timestamp when reviewing older AI guidance.
