# Offline static analysis walkthrough

From a development checkout, analyze the supplied problematic fixture:

```console
repoinsight analyze tests/fixtures/repos/problematic --output demo-report --format all
repoinsight explain RI-SEC-003
```

Open `demo-report/repoinsight-report.html` locally. Review category scores,
completeness, and each finding's evidence and limitations. The tool discovers
static patterns without installing fixture dependencies or executing its code.
Missing Git history is shown as unavailable; it does not stop file analysis.

Run the same workflow against `tests/fixtures/repos/healthy` and inspect the
difference in evidence. Neither report proves that the fixture's tests pass.
Repository tests must be run separately in an environment you trust.

To require a deterministic health threshold in your own CI:

```console
repoinsight analyze . --output reports --fail-under 80
```

Code 10 means the score is below the threshold. See the [CLI reference](../cli.md)
and [AI walkthrough](ai-guidance.md) for optional explanations of a saved report.
