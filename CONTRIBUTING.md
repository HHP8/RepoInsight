# Contributing

Thank you for improving RepoInsight. Open a focused issue before a large behavioral change so rule IDs, report contracts, and the version 1 threat model remain stable.

## Setup

```console
python -m venv .venv
python -m pip install -e . --group dev
python -m pytest -q
python -m ruff format --check .
python -m ruff check .
python -m mypy src tests tools benchmarks
```

Use tests first for behavior changes. Repository fixtures are untrusted data and must never be imported or executed. Keep findings evidence-based, deterministic, redacted, and explicit about completeness. Do not add runtime plugin discovery or expand the approved threat model without a design decision.

Pull requests should include the reason, narrow scope, tests, documentation impact, and exact validation commands. Update rule metadata and synchronized docs together. By participating, you agree to [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
