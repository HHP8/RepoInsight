# AI guidance walkthrough

This workflow uses the development checkout; the published 1.0.0 package does
not contain `enrich`. Start by installing the optional transport and producing
a static report. Replace `MODEL_ID` below with an accessible Responses API model
that supports Structured Outputs. No model is selected automatically.

```console
python -m pip install -e '.[ai]'
repoinsight analyze tests/fixtures/repos/problematic --output demo-report
repoinsight enrich demo-report/repoinsight-report.json --preview --model MODEL_ID
```

Preview prints valid JSON to standard output and estimates to standard error.
Inspect `input` inside that JSON: it contains rule descriptions, opaque evidence
IDs, numeric evidence, and completeness counts. It excludes source, paths,
repository identity, and arbitrary prose. Preview needs no credential and sends
nothing. To save it on macOS/Linux:

```console
repoinsight enrich demo-report/repoinsight-report.json --preview --model MODEL_ID > preview.json
```

For send mode, supply `OPENAI_API_KEY` through your shell or CI secret manager.
On Bash, this prompt avoids putting the credential itself in shell history:

```bash
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
```

With the environment configured, explicitly send the selected evidence:

```console
repoinsight enrich demo-report/repoinsight-report.json --send --model MODEL_ID --output demo-report/ai
```

Open `demo-report/ai/repoinsight-ai.html`. Guidance contains a summary, evidence-linked
explanations, and up to two actions with rough effort and verification steps.
Paths are resolved locally from the base report. AI guidance is unverified;
review it before changing code. The original JSON/HTML and scores are unchanged.

Lower the evidence limit or raise the budget explicitly when needed:

```console
repoinsight enrich demo-report/repoinsight-report.json --preview --model MODEL_ID --max-findings 5
```

The default input estimate limit is 8000; the output limit is 1500. Estimates are
conservative byte-based counts, not prices. Larger limits and a retry can incur
charges. Incomplete/refused responses and unknown citations return code 24 and
write a failed-status report when possible. Missing credentials or the optional
dependency return code 20. Output failures return code 23.

Prompt version 1.3 bounds the response schema to two explanations, two distinct
prioritized actions, and one or two limitations. It requests shorter field text,
explicit normal/boundary/error test cases, useful public docstring contents, and
review of skipped-input diagnostics before other changes. Security and
maintainability matches take priority over generic CI or policy suggestions.
Its 180-word limit counts whitespace-separated words across summary, explanation
text, action titles/rationales/changes/verification, and limitations. Section or
word-limit violations return code 24 with a failed sidecar and retained usage;
they do not trigger another paid generation or silently cut off advice.
Historical prompt 1.0–1.2 responses retain their original validation contract
during offline replay.

Even compact guidance can exhaust the default output budget. The output limit
includes any model reasoning tokens. A truncated response is rejected; supplied
usage is retained in the failed sidecar, and truncation is not retried automatically.
In the saved case-03 response, 927 of 1500 output tokens were reasoning tokens;
the remaining 573 did not complete the JSON answer. The smaller prompt/schema
is a mitigation; live reliability with prompt 1.3 still needs validation.

Offline tests use synthetic provider responses and no credentials:

```console
python -m pytest -q tests/ai
```

For privacy and provider-retention details, read [security](../security.md).
For practical follow-through, see [before/after improvements](improve-a-repository.md).
