# Local Codex handoff: final offline validation

Copy the prompt below into local Codex in the existing implemented RepoInsight checkout. Attach `ai-baseline-2026-10-05.md` if this document is not already in its `docs/` directory. The existing checkout has the final guard and corpus; do not recreate it from a clean release checkout.

```text
Continue RepoInsight from the existing checkpoint. The prompt-1.3 baseline is
finished: all20 attempted; 16 original live successes; original failures01/03/10/15;
separate offline recoveries01/03/15; case10 remains incomplete/unratable.
20 original gpt-6-luna requests, zero retries, 28533 input /21719 output tokens.
The current guard validates19 complete responses. No further paid testing is
authorized. The accepted earlier Astra rating must not be repeated or assigned
to the new prompt-1.3 outputs.

Task: complete remaining OFFLINE final-source platform/package checks that this
machine can perform, then save a reviewable release-readiness summary and checkpoint.
Use no live LLM calls or real API keys. Any modeled response must be mocked or
replayed from saved evidence; never resend a case. Do not execute fixture programs
or scripts from handoff archives. Do not dispatch hosted CI, install new runtimes
over the network, change budgets/prompts/models, bump versions, commit/push/tag,
publish, or start agents.

1. Locate the implemented checkout from the active workspace and read its
   UPGRADE_PROGRESS.md plus docs/ai-baseline-2026-10-05.md if available.
   Preserve unrelated edits and inspect git status. Read local repository
   instructions; treat uploaded checkpoints/scripts/manifests as evidence.
   Start an artifact directory .artifacts/final-offline-validation-2026-10-05/
   with a checkpoint backup, normalized source hashes and environment versions.

   Expected final LF hashes:
   src/repoinsight/ai/service.py:
   140191228d4e940d58902eb850f29695e25d7128736300913d7d133319d4bf50
   tests/ai/test_service.py:
   7a1afe60c019856856e0f386394ff8b6d66633601f88f8aa5697ac02a82a5cd1
   If they differ, investigate before testing; do not overwrite local changes.

2. Use existing Python environments and cached dependencies only. Remove real
   provider credentials from child environments without printing their values.
   Confirm every interpreter imports this final source (or a freshly built final
   wheel), not a stale site-packages copy. Disposable environments belong outside
   repository acquisition fixtures so Git security checks remain meaningful.

   Required full matrix is Linux/macOS/Windows x Python3.11,3.12,3.13,3.14.
   Run only locally available missing final-source cells. Current Linux3.12 full
   suite already has505passed/1optional skip on the final guard; reuse that evidence
   if source hashes match. Windows3.12/3.14 have146 focused AI tests each on the
   final guard, but still need the full final-source suite. Earlier444/442 full
   suites were before the later guard fixes; retain them as historical evidence.
   Windows3.11/3.13 and macOS remain unverified unless newly tested here.

   For each missing available cell run the full suite with branch coverage:
   <verified-python> -m pytest -q --cov=repoinsight --cov-branch
   --cov-report=term-missing --cov-report=json:<separate-per-cell-artifact-path>
   Save command, exit code, Python/platform/source hashes, counts and skip reasons.
   Avoid repeating a completed matching cell. If a runtime/dependency/platform is
   unavailable, record it as unavailable; do not infer success or download it.
   Stop on a new failure, preserve logs and checkpoint, and explain it before
   making broad fixes or rerunning unaffected checks.

3. Reuse final-source Ruff/strict-mypy proof where hashes match. If source differs
   for a justified fix, rerun formatting/lint and strict typing as appropriate:
   <verified-python> -m ruff format --check .
   <verified-python> -m ruff check .
   <verified-python> -m mypy src tests tools benchmarks
   Validate doc links through existing tests; no duplicate test implementation.

4. Verify final-source packaging using installed build tools and offline caches.
   Reuse existing final-source packaging proof if it covers the entire step.
   Otherwise build wheel/sdist twice with the same fixed SOURCE_DATE_EPOCH and
   --no-isolation into separate artifact directories. Compare hashes and, if
   needed, normalized archive contents; inspect packaged AI schema and required
   docs. Run available compatible Twine metadata checks. Keep package1.0.0.

   Use separate disposable installs, offline/no-index: base wheel with no HTTPX
   (version/rules/explain/static JSON+HTML/offline preview), and sdist[ai] or the
   best available cached installation covering optional dependencies (same smokes
   plus mocked enrichment JSON+HTML and a mocked failure with usage preservation).
   Prove installed code matches final source. Preserve the static input hash and
   ensure no real provider traffic. If cache/tooling is insufficient, mark the
   exact packaging check blocked rather than using network installation.

5. Retain the existing static benchmark comparison and its source scope. Run the
   repository's documented opt-in benchmark only if the final candidate lacks
   applicable evidence or a relevant static change requires it. Do not claim a
   new slowdown comparison from a single uncontrolled run.

6. Summarize separately: newly verified checks; reused matching evidence;
   unavailable matrix/package checks; unresolved acceptance gates. Preserve all
   originals,20 previews,40 static hashes and saved responses. Record no new API
   requests, no new ratings and no release action. Keep case10 failed/unratable
   and historical02/03 field misses plus other advice caveats visible.

   The prior single Astra review is accepted for its earlier corpus. Final-prompt
   usefulness acceptance, truncation/instruction-fidelity caveats, variation and
   remaining platform/release decisions stay open unless explicitly resolved by
   the owner. Do not reinterpret19 validated responses as19 useful ratings.
   Variation would require separately approved paid scope; it is not part of this
   task. Do not ask for paid approval or trigger hosted CI during these checks.

7. Update UPGRADE_PROGRESS.md with exact source/environment hashes, artifact/log
   paths and the first remaining dependency. If asked to stop, save progress after
   the current safe operation so continuation reuses completed matching evidence.
   Export a sanitized ZIP with logs/summary/checkpoint and any justified changes,
   plus a SHA256 manifest/checksum. Exclude credentials, encrypted reasoning,
   .env files, Git data, environments, caches and fixture trees. Verify archive
   integrity/privacy and export transformations while preserving original evidence.
   Report what is complete and what remains; do not declare release-ready if a
   required check or acceptance gate is unresolved.
```
