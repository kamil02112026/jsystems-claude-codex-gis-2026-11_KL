"""Command line interface (ADR-000 §6, D13)."""

from __future__ import annotations

import sys

from mapqa.cli.main import main


def entry_point() -> None:
    sys.exit(main(sys.argv[1:]))


__all__ = ["main", "entry_point"]
