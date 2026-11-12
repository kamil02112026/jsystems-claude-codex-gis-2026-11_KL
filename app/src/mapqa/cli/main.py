"""argparse entry point. Subcommands are added by later tasks (T05)."""

from __future__ import annotations

import argparse

from mapqa import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mapqa",
        description="Map Attribute QA Copilot: kandydaci do ręcznej weryfikacji atrybutów dróg.",
    )
    parser.add_argument("--version", action="version", version=f"mapqa {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    try:
        parser.parse_args(argv)
    except SystemExit as exc:  # argparse exits on --help / errors
        return int(exc.code or 0)
    return 0
