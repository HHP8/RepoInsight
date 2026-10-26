# RepoInsight

**RepoInsight 1.2.0** adds offline saved-report comparison with
`repoinsight compare before.json after.json`. Version 1.1.0 has no comparison
command. See the
[comparison guide](docs/comparison.md) and [before/after examples](docs/examples/report-comparison.md).

RepoInsight is a cross-platform Python CLI that produces deterministic repository-health reports without importing or executing repository code. It analyzes local directories and public GitHub repositories with bounded file discovery, Python AST inspection, sanitized Git metadata, transparent scoring, a versioned JSON contract, and a standalone offline HTML report.

![Illustrative RepoInsight standalone report preview](docs/assets/report-preview.svg)

## Install

RepoInsight requires **Python 3.11+**. Install from
[production PyPI](https://pypi.org/project/repoinsight/) in a virtual environment.
Installation and static analysis require no OpenAI API key.

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade repoinsight
.\.venv\Scripts\repoinsight.exe version
```

On macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade repoinsight
repoinsight version
```

For the commands below, Windows users should replace `python` with
`.\.venv\Scripts\python.exe` and `repoinsight` with `.\.venv\Scripts\repoinsight.exe`;
activation is not needed. On macOS/Linux, `.venv/bin/python` and
`.venv/bin/repoinsight` also work without activation.
Run the examples from this environment's folder; pass your project directory to
`analyze` rather than changing folders.

To install the exact 1.2.0 release instead:

```console
python -m pip install "repoinsight==1.2.0"
```

Alternatively, download the 1.2.0 wheel and `SHA256SUMS` from the
[GitHub release](https://github.com/HHP8/RepoInsight/releases/tag/v1.2.0), verify
the checksum, and install the downloaded wheel in the same environment:

```console
python -m pip install ./repoinsight-1.2.0-py3-none-any.whl
repoinsight version
```

See [Experimental AI guidance](#experimental-ai-guidance) for optional AI
dependencies, or [Development from a source checkout](#development-from-a-source-checkout)
for an editable developer installation.

## Quick start

```console
repoinsight analyze "PATH_TO_PROJECT" --output before --format all
```

Replace `PATH_TO_PROJECT` with your project directory. Review the findings, make
your chosen change yourself, and independently verify it with appropriate tests
or other checks. RepoInsight does not make or verify the change. Then:

```console
repoinsight analyze "PATH_TO_PROJECT" --output after --format all
repoinsight compare before/repoinsight-report.json after/repoinsight-report.json
```

Comparing saved reports is offline and makes no AI request. Check completeness
and compatibility warnings; a higher score or missing finding does not prove a
fix. See the [improvement walkthrough](docs/examples/improve-a-repository.md).

Other commands:

```console
repoinsight analyze "PATH_TO_PROJECT" --fail-under 80
repoinsight rules
repoinsight explain RI-SEC-001
```

`analyze` makes no AI request and prints a compact terminal summary. Report files
are `repoinsight-report.json` and `repoinsight-report.html`; the default directory
is `repoinsight-report/`. The HTML report works offline. Analyzing a public GitHub
URL additionally requires Git and network access; see the [CLI reference](docs/cli.md).

## Safety and privacy

Repository contents are untrusted input. RepoInsight never imports analyzed modules or runs repository scripts, build tools, tests, hooks, or configuration code. It blocks ordinary traversal and external symlink following, bounds discovery and Git acquisition, redacts secret-like text at trust boundaries, autoescapes report data, and removes temporary clones.

Version 1 does not defend against a concurrent privileged local attacker, a compromised operating system, a malicious system Git installation, a hostile executable `PATH`, or an adversarial filesystem driver. See [Security and privacy](docs/security.md) and [Known limitations](docs/limitations.md).

## Documentation

- [First health report: find a missing README (beginner tutorial and video)](docs/tutorials/first-health-report/README.md)
- [CLI reference](docs/cli.md)
- [Configuration](docs/configuration.md)
- [Rules](docs/rules.md)
- [Scoring](docs/scoring.md)
- [Architecture](docs/architecture.md)
- [Analyzer extension guide](docs/analyzers.md)
- [Security and privacy](docs/security.md)
- [Known limitations](docs/limitations.md)
- [Release process](docs/release.md)
- [Proposed upgrade plan: AI guidance and future improvements](docs/upgrade-plan.md)
- [AI enrichment examples](docs/examples/ai-guidance.md)
- [AI release evaluation](docs/ai-evaluation.md)
- [Codex Cloud development](docs/codex-cloud.md)
- [Support](SUPPORT.md)

## Development from a source checkout

Use an editable installation with the development dependency group. Upgrade pip
first so it supports `--group dev` (pip 25.1 or newer). On Windows PowerShell:

This source checkout identifies new reports as tool 1.2.0 and accepts saved
1.0.0, 1.1.0 and 1.2.0 reports. Static schema/scoring and comparison contracts
remain 1.0. Older strict validators may reject the new tool metadata and need
updated packaged schemas; unknown future tool versions remain unsupported.

```console
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -e . --group dev
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff format --check .
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy src tests tools benchmarks
```

On macOS or Linux:

```console
python3 -m venv .venv
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -e . --group dev
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m mypy src tests tools benchmarks
```

The standard test suite needs no network access. The 100,000-line benchmark and live public-repository smoke are opt-in. See [CONTRIBUTING.md](CONTRIBUTING.md).

<a id="experimental-ai-guidance-110"></a>

## Experimental AI guidance

AI guidance was introduced in 1.1.0 and is included in 1.2.0; installing an older
version is unnecessary. It is experimental, advisory, and may be wrong. It can
explain a saved report and suggest up to two evidence-linked actions, without
modifying source, running tests, or changing static scores.

**Offline preview:** the base installation is sufficient; no API key or optional
HTTPX dependency is needed. `MODEL_ID` is a placeholder for an OpenAI Responses
API model with Structured Outputs; preview does not check account access.

```console
repoinsight enrich before/repoinsight-report.json --preview --model MODEL_ID
```

**Optional live support:** install the extra in the same environment:

```console
python -m pip install --upgrade "repoinsight[ai]"
```

Only `enrich --send` sends selected evidence. It additionally requires
`OPENAI_API_KEY` in the process environment and an accessible compatible model.
The [AI walkthrough](docs/examples/ai-guidance.md#optional-live-send) separates the
paid send step from offline preview and explains setup and JSON/HTML output paths.
Live requests can incur charges and fail after spending tokens, including under
the default 1500-output-token cap; see [budgets and retries](docs/examples/ai-guidance.md#budgets-retries-and-troubleshooting).
Source, identities, paths and repository prose are omitted from the request;
selected static evidence can still be sensitive. Keep credentials out of commands,
source, settings and reports; authentication sends the key only to the provider
over verified HTTPS. See [privacy boundaries](docs/security.md#experimental-ai-enrichment).
Package/tool version 1.2.0 is independent of schema and score-contract versions 1.0.

## License

MIT. See [LICENSE](LICENSE).
