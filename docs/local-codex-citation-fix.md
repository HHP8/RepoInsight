# Local Codex: recover case 03 and resume the remaining pilot

Use this prompt with `RepoInsight-citation-fix-2026-10-04.zip` in the existing
checkout that produced the case-03 pilot results. The attachment permits offline
integration and recovery; paid continuation requires explicit owner approval.

```text
Continue RepoInsight from the saved prompt-1.3 pilot checkpoint. Integrate the
attached citation-fix patch; do not recreate the corpus or resend case 03.

Locate the checkout that contains the original case-03 attempt and all twenty
prepared previews. Read its checkpoint and applicable local AGENTS.md. Verify
PATCH_MANIFEST.json file hashes and compare the two source/test files with their
listed base hashes (normalize CRLF to LF for comparison). Back up changed files.
Apply citation-fix.patch or merge the supplied source/test changes if unrelated
edits exist. Do not overwrite unrelated changes. Merge the supplied checkpoint's
new pilot/recovery information into the local checkpoint; preserve local history.

The change exempts only the complete prose term source/runtime, like existing
test/source and issue/PR terms. Tighter boundaries keep actual paths rejected.
Prompt version stays 1.3. Request content, model settings, budgets and static
analysis do not change. This is a local validation fix, not another model attempt.

Run offline tests/format/lint/types on the installed patched source using the
existing Windows interpreters. Linux checks already passed: 461 passed/1 skipped,
102 focused AI tests, Ruff and strict mypy. Save Windows results; do not claim
the earlier Windows logs tested this patch. Do not run fixture programs.

Original corpus:
.artifacts/followup-validation-2026-10-04/ai-evaluation-prompt-1-3

Verify its manifest report/preview hashes. Confirm case 03 still records exactly
one gpt-6-luna request, zero retries, the original failed AI sidecars and saved
complete sanitized response. Its usage is 1452 input / 902 output; preserve this
as original generation usage, not replay charges. Cases 06/07/12/19 must have no
recorded attempt. Never delete a recorded attempt to bypass the send guard.

Copy the corpus to a new offline-replay directory; do not replay in the original.
Call tools.ai_evaluation.replay on that copy with OpenAIProvider.generate patched
to raise if called. This uses ReplayProvider and a synthetic environment key;
do not load credentials or contact the network. Compare all original files before
and after. Case 03 must produce status succeeded, prompt 1.3, original usage, and
124 narrative words. Keep the original failed sidecar and attempt unchanged.
Imported recovery evidence is for comparison; reproduce using the patched local
source and save a separate local recovery summary.

If the owner has not explicitly approved resuming the four remaining paid cases,
stop here, save UPGRADE_PROGRESS.md, and report offline readiness. Uploading this
patch or previous approval of implementation is not paid-continuation approval.

Only if explicitly approved to resume: use gpt-6-luna for every generation and
retry, with no fallback. Use the process OPENAI_API_KEY without printing it.
Send only minimized evidence from exact original previews, with no source,
repository prose, identities or paths. Keep 8000 conservative input estimate,
1500 output tokens including reasoning, 30 seconds and one existing transient
retry. Four initial requests, at most eight including transient retries; no
automatic increase, reasoning change or repair generation. Including the already
completed case-03 request, this continuation is at most nine total pilot requests.

Run ONE command at a time from the checkout:
python -m tools.ai_evaluation send --directory .artifacts/followup-validation-2026-10-04/ai-evaluation-prompt-1-3 --model gpt-6-luna --cases 6

Inspect attempt.json state/exit_code and AI sidecar status before proceeding.
Helper exit code 0 does not prove enrichment success. If case 06 succeeds, use
the same command with --cases 7, then 12, then 19, each separately after checking
the previous case. Never resend case 03 or any existing/uncertain attempt.

Stop on any failure, incomplete/overlong response, refusal, compatibility error
or uncertain attempt. Preserve usage and diagnostics. No further call or fix
followed by automatic generation is authorized after a failure. Do not send
the other fifteen cases or a variability subset.

Inspect successful advice for useful concrete tests/docstrings, distinct actions,
skipped-input follow-through and unsupported verification claims. These are
observations, not another Astra rating. Confirm static hashes are unchanged.
Save checkpoint, exact request/retry counts, usage and remaining cases. Return
a sanitized ZIP with evidence and logs; exclude keys, .env files, authorization
headers, encrypted reasoning, Git metadata, environments and caches. Do not
commit, push, tag, bump versions or publish automatically.
```

The saved answer passing validation establishes offline recovery of case 03.
Four unsent pilot cases, the full final-prompt evaluation and remaining platform
checks are still needed before release preparation.
