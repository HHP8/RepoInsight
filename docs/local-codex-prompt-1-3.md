# Local Codex handoff for prompt 1.3

Paste the following prompt into local Codex with the 2026-10-04 source handoff ZIP.
Live testing requires separate approval of the bounded pilot below. The handoff
itself does not authorize provider charges.

```text
Continue RepoInsight from the attached RepoInsight-handoff-2026-10-04.zip.

Read UPGRADE_PROGRESS.md first. Locate the actual checkout, compare it with the
snapshot, back up changed files, and integrate the supplied prompt-1.3 changes
while preserving unrelated local edits and applicable workspace AGENTS.md rules.
Verify HANDOFF_MANIFEST.json hashes before applying files. Do not reconstruct
changes from report prose or repeat the completed Astra rating.

The owner accepted the single Astra review: 19/20 saved mixed-prompt cases useful.
Prompt 1.3 now requests at most two explanations, two distinct actions, and two
limitations. Its 180-word narrative/section limits are enforced locally; older
prompt responses retain their original replay contracts. Case 03 previously used
927 of 1500 output tokens on reasoning and returned incomplete JSON. This is a
mitigation, not yet evidence of improved live reliability.

First verify that the installed source reports PROMPT_VERSION == "1.3". Run the
appropriate offline quality/tests and Windows checks on the final source, saving
logs. Linux Python 3.11–3.14 already passed here; do not rerun paid evaluation
calls to reproduce these offline results. Do not run fixture programs.

The prepared pilot corpus is:
.artifacts/followup-validation-2026-10-04/ai-evaluation-prompt-1-3
Use its exact saved reports and previews; do not regenerate it in place. Verify
manifest hashes and inspect the five pilot previews before any transmission.

Unless the owner separately approves this exact pilot, stop after offline checks
and report readiness. Do not treat the earlier approval of implementation as
approval of paid API testing.

Approved pilot scope, if explicitly authorized: cases 03, 06, 07, 12, 19, in that
order. All LIVE provider generations and retries must use only gpt-6-luna. Never
fallback, probe another model, or use another provider. Keys come only from the
process OPENAI_API_KEY; do not ask for or print a literal key. Only minimized saved
evidence may be sent: no raw source, repository prose, paths, or identities.

Execute cases one at a time, using the development helper:
python -m tools.ai_evaluation send --directory .artifacts/followup-validation-2026-10-04/ai-evaluation-prompt-1-3 --model gpt-6-luna --cases 3
Then use --cases 6, 7, 12, 19 separately only if each prior case succeeded.
Read attempt.json exit_code/state and AI sidecar status after EACH command; the
helper's process success alone does not establish enrichment success.
Stop on any failure, incomplete/overlong answer, uncertain attempt, refusal, or
account/model/API compatibility rejection. Preserve the failure and its usage.
Do not rerun a recorded attempt, raise budgets, repair via another generation,
change reasoning options, or perform more calls without further approval.

Limits stay at 8000 conservative input estimate, 1500 output tokens, 30 seconds,
and the adapter's existing single transient retry. Five initial requests plus
at most one transient retry each means a maximum of ten provider requests.
No truncation or compactness-validation failure triggers a retry.

For successes, inspect the complete advice for grounded citations, useful test
cases, concrete docstrings, distinct actions, skipped-input diagnostics, and
unsupported verification claims. Report observations rather than claiming a
new Astra or human sign-off. Confirm static report hashes remain unchanged and
retain sanitized envelopes, actual request counts, prompt provenance and usage.

Do not send the other 15 cases or run a variability subset automatically. This
pilot cannot establish the full final-prompt release gate. Save UPGRADE_PROGRESS.md
with changes, checks, request counts, failures, and the exact next step, then
return a sanitized handoff ZIP. Exclude credentials/.env files, authorization
headers, Git metadata, virtual environments, interpreter downloads and caches.
Do not commit, push, tag, bump versions, or publish automatically.
```

The five selected cases test incomplete output, explicit test cases, duplicate
CI advice, docstring usefulness, and skipped-input follow-through. A successful
pilot supports proceeding to the remaining 15 cases in the same corpus, then a
separately prepared variability subset after an explicit budget decision.

The pilot's worst-case envelope caps are 80,000 conservatively estimated input
tokens and 15,000 output tokens across ten attempts. Output includes reasoning.
Actual token usage may be smaller; these are limits, not a currency price quote.
