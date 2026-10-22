# AI guidance walkthrough

AI guidance was introduced in 1.1.0 and is included in the published 1.2.0 package.
Use the [README installation instructions](../../README.md#install) for Python
3.11+ and a virtual environment; no source checkout or older release is needed.
See the [feature overview](../../README.md#experimental-ai-guidance).

Run these examples from the folder containing `.venv`. On Windows PowerShell,
replace `python` with `.\.venv\Scripts\python.exe` and `repoinsight` with
`.\.venv\Scripts\repoinsight.exe`. On macOS/Linux, activate that environment or use
`.venv/bin/python` and `.venv/bin/repoinsight` explicitly.

## Offline analysis and preview

The base installation supports both commands below. It requires no API key or
optional HTTPX dependency:

```console
python -m pip install --upgrade repoinsight
repoinsight analyze "PATH_TO_PROJECT" --output demo-report --format all
```

Replace `PATH_TO_PROJECT` with your own project directory. Analysis inspects it
as data without executing its code or making an AI request. A local directory
works offline; a remote GitHub URL instead needs Git and network access.

`MODEL_ID` is a placeholder, not a default model. Choose an OpenAI Responses API
model supporting Structured Outputs that your account can access before sending.
Preview requires the identifier but checks only its syntax, not model support or
account access; no model is selected or queried automatically.

```console
repoinsight enrich demo-report/repoinsight-report.json --preview --model MODEL_ID
```

Preview prints valid JSON to standard output and estimates to standard error.
Inspect `input` inside that JSON: it contains rule descriptions, opaque evidence
IDs, numeric evidence, and completeness counts. It excludes source, paths,
repository identity, and arbitrary prose. Preview needs no credential and sends
nothing. It does not generate AI guidance JSON/HTML. To save the outbound request
on macOS/Linux:

```sh
repoinsight enrich demo-report/repoinsight-report.json --preview --model MODEL_ID > preview.json
```

On Windows PowerShell, use the installed executable and explicit UTF-8 encoding:

```powershell
.\.venv\Scripts\repoinsight.exe enrich demo-report/repoinsight-report.json --preview --model MODEL_ID | Set-Content -Encoding utf8 preview.json
```

Inspect the preview locally before any transmission; even minimized evidence can
be confidential. Do not commit it. Changing the saved report, model or budget
options changes the request; keep them the same when comparing preview with send.

## Optional live send

**This section is optional and can incur charges. Stop after preview for an
offline walkthrough.** Guidance is experimental and may fail after spending tokens.
It does not modify source, execute tests or change static scores.

Install the optional live transport in the same environment:

```console
python -m pip install --upgrade "repoinsight[ai]"
```

Supply `OPENAI_API_KEY` through a secret manager or interactive input in the same
shell that will run send. RepoInsight does not load `.env` files. Never paste the
key into a command, source, application settings or reports. These interactive
examples keep the entered value out of command history and do not print it.

Windows PowerShell:

```powershell
$repoInsightKey = Read-Host 'OpenAI API key' -AsSecureString
$repoInsightBstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($repoInsightKey)
try { $env:OPENAI_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($repoInsightBstr) }
finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($repoInsightBstr)
    $repoInsightKey.Dispose()
    Remove-Variable repoInsightKey, repoInsightBstr
}
```

Bash on macOS/Linux:

```bash
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
printf '\n'
export OPENAI_API_KEY
```

Authentication sends the key to OpenAI in the authorization header over
certificate-verified HTTPS; it is not bundled in the application or request JSON.
See [credential and provider-retention boundaries](../security.md#experimental-ai-enrichment).

Only when you choose to make a live request, replace `MODEL_ID` with your accessible
compatible model and explicitly send the selected evidence:

```console
repoinsight enrich demo-report/repoinsight-report.json --send --model MODEL_ID --output demo-report/ai
```

Send writes `demo-report/ai/repoinsight-ai.json` and
`demo-report/ai/repoinsight-ai.html`; without `--output`, the directory is
`repoinsight-ai/`. Open the HTML report locally. Guidance contains a summary, evidence-linked
explanations, and up to two actions with rough effort and verification steps.
Paths are resolved locally from the base report. AI guidance is unverified;
review it before changing code. The original JSON/HTML and scores are unchanged.

Lower the evidence limit or raise the budget explicitly when needed:

```console
repoinsight enrich demo-report/repoinsight-report.json --preview --model MODEL_ID --max-findings 5
```

After use, remove the process-environment key with `Remove-Item Env:OPENAI_API_KEY`
in PowerShell or `unset OPENAI_API_KEY` in Bash. This is not a guarantee against a
compromised host or external debugging/logging tools.

## Budgets, retries and troubleshooting

The defaults are 20 selected findings, 8000 estimated input tokens, 1500 output
tokens and a 30-second transport deadline. Estimates are
conservative byte-based counts, not prices. Larger limits and a retry can incur
charges. Incomplete/refused responses and unknown citations return code 24 and
write a failed-status report when possible. Missing credentials or the optional
dependency return code 20. Invalid options/model identifier syntax also use code 20;
provider model/access rejection uses code 24. Check model availability in your own
account; preview cannot establish it. Output failures return code 23. See the
[CLI option ranges](../cli.md#repoinsight-enrich-report-experimental).

At most one retry is made for transient transport/rate-limit/server failures,
within the checked deadline. Authentication failures are not retried. Budget,
timeout and last-response usage figures are not exact total-price caps, especially
if an earlier attempt consumed tokens. Keep original reports and failed sidecars;
inspect status and recorded usage before deciding whether to make another paid
request. A retry is another potentially billable request.

### Recorded prompt and evaluation limits

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
is a mitigation. Under final prompt 1.3, case 10 exhausted the same cap in both
its original and variation attempts (1325 and 1189 reasoning tokens respectively).
Completion at this budget is not guaranteed; partial JSON is not reconstructed.

## Source-checkout-only examples

Developers can use [source setup](../../README.md#development-from-a-source-checkout),
including upgrading pip before `--group dev`. Optional transport from that checkout
can be installed with `python -m pip install -e ".[ai]"`. The following fixture and
test paths are for a RepoInsight source checkout, not a user project or base wheel:

```console
repoinsight analyze tests/fixtures/repos/problematic --output fixture-report --format all
python -m pytest -q tests/ai
```

These tests use synthetic provider responses and no credentials; they are not a
live-quality evaluation. Installing the published package needs neither fixture
nor development tools.

For privacy and provider-retention details, read [security](../security.md).
For practical follow-through, see [before/after improvements](improve-a-repository.md).
