"""Command line interface (ADR-000 §6, D13)."""

from __future__ import annotations

import sys

from mapqa.cli.main import main


def entry_point() -> None:
    # Windows pipes default to the ANSI code page (cp1250); --output json must always be UTF-8 (review #1)
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8")
    sys.exit(main(sys.argv[1:]))


__all__ = ["main", "entry_point"]
