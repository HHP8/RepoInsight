"""Support ``python -m repoinsight`` through the installed CLI adapter."""

from importlib import import_module
from typing import Protocol, cast


class _Main(Protocol):
    def __call__(self) -> object: ...


def main() -> object:
    """Load the CLI lazily so the foundation package has no import side effects."""
    cli = import_module("repoinsight.cli")
    return cast(_Main, cli.main)()


if __name__ == "__main__":
    raise SystemExit(main())
