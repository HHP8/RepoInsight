# Experimental AI MVP acceptance — 2026-10-07

The owner accepted the current experimental AI MVP with its recorded limitations
and required that personal API keys not appear in published material or saved
application data. This document records experimental feature acceptance,
not permission to publish. The separately approved candidate and main pushes
completed at `602bfe1`; main CI passed. Additional paid testing, ratings,
tagging and release publication still require their own authorization.

The original 20-case corpus remains immutable: 20 requests, no retries, 19 complete
saved responses validated by final guards, case 10 incomplete, original live
failures and offline recoveries preserved separately. The three separate variation
trials used three gpt-6-luna requests with zero retries: 06/20 complete, 10 incomplete
again at the unchanged 1500-output-token cap including reasoning. The owner accepts
that incomplete paid responses can occur, historical per-field misses remain,
structured citation grouping and verification detail can be imperfect, and
minimized evidence limits application-specific advice. This does not guarantee
reliable completion or rate all final responses useful.

The accepted one-time Astra rating applies only to its earlier corpus. No new
rating or transfer of its scores was made. The merged implementation passed
[main CI](https://github.com/HHP8/RepoInsight/actions/runs/37540211948): all
12 cells each had 506 passed and one optional benchmark skip; quality passed.
Later release documentation changes need their appropriate checks.

Keys are supplied only through the local process environment. RepoInsight does
not bundle or persist them, accept key arguments or repository credential settings,
or include them in request content/reports. Explicit send necessarily uses the
key in the provider's HTTPS authorization header; process memory/provider
authentication are distinct from publishing or saving keys. Offline validation
uses synthetic credentials and requires no owner key. No real key was requested
or copied into release material. Secret-pattern scans are evidence about inspected
files, not a universal proof against every credential format or outside logging.

Version 1.1.0 includes this experimental MVP. Current schema and score identifiers
remain 1.0; the static schema's tool-version metadata constraint is expanded only
to retain old reports while truthfully identifying newly generated 1.1 reports.
No scoring fields or AI fields are added to the static report. Acceptance of
these feature limitations does not authorize new commits, pushes, tags, CI
dispatches, GitHub Release or PyPI publication.
