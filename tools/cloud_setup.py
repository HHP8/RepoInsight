"""Prepare a source checkout for local or Codex Cloud development."""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*command: str) -> None:
    """Run a development command from the project root, stopping on failure."""
    print(f"Running: {' '.join(command)}", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="also run the standard checks")
    arguments = parser.parse_args()

    # This bootstrap can run before the package's minimum Python version is enforced.
    if sys.version_info < (3, 11):  # noqa: UP036
        parser.error("RepoInsight development requires Python 3.11 or newer")
    if shutil.which("git") is None:
        parser.error("Git must be installed and available on PATH")

    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")
    if not environment.exists():
        venv.EnvBuilder(with_pip=True).create(environment)
    if not python.is_file():
        parser.error(".venv is incompatible or incomplete; use a fresh checkout for this platform")

    executable = str(python)
    run(executable, "-m", "pip", "install", "--upgrade", "pip")
    run(executable, "-m", "pip", "install", "-e", ".", "--group", "dev")
    run(executable, "-m", "pip", "check")
    run(executable, "-m", "repoinsight", "version")
    if arguments.check:
        run(executable, "-m", "ruff", "format", "--check", ".")
        run(executable, "-m", "ruff", "check", ".")
        run(executable, "-m", "mypy", "src", "tests", "tools", "benchmarks")
        run(executable, "-m", "pytest", "-q")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
