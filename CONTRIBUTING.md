# Contributing

Thank you for improving RepoInsight. Open a focused issue before a large behavioral change so rule IDs, report contracts, and the version 1 threat model remain stable.

## Setup

Follow the [platform setup](README.md#development-from-a-source-checkout) from
the checkout root. It creates `.venv`, upgrades pip to support `--group dev`
(pip 25.1+), and installs the editable package and development dependencies.
Then use that environment for the checks below: on Windows PowerShell, replace
`python` with `.\.venv\Scripts\python.exe`; on macOS/Linux, use
`.venv/bin/python`. Activation-policy changes and administrator access are not
needed.

```console
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests tools benchmarks
```

Use tests first for behavior changes. Repository fixtures are untrusted data and must never be imported or executed. Keep findings evidence-based, deterministic, redacted, and explicit about completeness. Do not add runtime plugin discovery or expand the approved threat model without a design decision.

Pull requests should include the reason, narrow scope, tests, documentation impact, and exact validation commands. Update rule metadata and synchronized docs together. By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
