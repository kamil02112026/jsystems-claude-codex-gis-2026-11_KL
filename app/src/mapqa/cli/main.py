"""argparse CLI: run, sources list/check, eval run/calibrate (ADR-000 §6, D13; PRD F8.9)."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from mapqa import __version__
from mapqa.config import load
from mapqa.contract.bundle import Bbox
from mapqa.contract.errors import MapQAError, ValidationError
from mapqa.contract.models import Envelope, ErrorInfo
from mapqa.sources.registry import build_adapter

ATTRIBUTES = ("speed_limit", "surface", "lit")
MVP_ATTRIBUTES = ("speed_limit",)


class _ArgError(Exception):
    pass


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:  # type: ignore[override]
        raise _ArgError(message)


def _common(p: argparse.ArgumentParser) -> None:
    p.add_argument("--config", help="ścieżka pliku konfiguracyjnego (domyślnie MAPQA_CONFIG albo ./mapqa.toml)")
    p.add_argument("--output", choices=("text", "json"), default="text", help="format wyniku (json: jeden dokument na stdout)")
    p.add_argument("--source", help="nazwa źródła danych (pierwszeństwo przed MAPQA_SOURCE i plikiem)")


def _run_options(p: argparse.ArgumentParser, *, default_split: str) -> None:
    p.add_argument("--bbox", help="minx,miny,maxx,maxy w WGS84 (dla --dataset signs domyślnie bez filtra)")
    p.add_argument("--attributes", default="speed_limit", help="lista atrybutów (MVP: speed_limit)")
    p.add_argument("--dataset", choices=("signs", "photos"), default="signs")
    p.add_argument("--model", action="store_true", help="włącza płatny odczyt modelem (wymaga potwierdzenia)")
    p.add_argument("--no-model", action="store_true", help="wymusza tryb bez modelu")
    p.add_argument("--yes", action="store_true", help="potwierdza manifest kosztu bez pytania")
    p.add_argument(
        "--cache-only",
        action="store_true",
        help="odczyt modelem wyłącznie z cache: 0 zapytań, bez klienta HTTP i bez potwierdzenia",
    )
    p.add_argument("--max-queries", type=int)
    p.add_argument("--max-images", type=int)
    p.add_argument("--max-usd", type=str)
    p.add_argument("--level1-model")
    p.add_argument("--level2-model")
    p.add_argument("--level2-effort")
    p.add_argument("--threshold-l1", type=float)
    p.add_argument("--threshold-l2", type=float)
    p.add_argument("--split", choices=("all", "calibration", "test"), default=default_split)


def build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="mapqa", description="Map Attribute QA Copilot: kandydaci do ręcznej weryfikacji atrybutów dróg.")
    parser.add_argument("--version", action="version", version=f"mapqa {__version__}")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="uruchomienie: profil, połączenia, porównanie, kandydaci, raport")
    _common(run)
    _run_options(run, default_split="all")

    sources = sub.add_parser("sources", help="źródła danych")
    ssub = sources.add_subparsers(dest="sources_command")
    for name, help_text in (("list", "lista skonfigurowanych źródeł"), ("check", "test połączenia i liczności tabel")):
        sp = ssub.add_parser(name, help=help_text)
        _common(sp)
        if name == "check":
            sp.add_argument("--bbox", help="minx,miny,maxx,maxy (domyślnie bbox danych)")

    ev = sub.add_parser("eval", help="ewaluacja kaskady na etykietach")
    esub = ev.add_subparsers(dest="eval_command")
    er = esub.add_parser("run", help="metryki na części test")
    _common(er)
    _run_options(er, default_split="test")
    ec = esub.add_parser("calibrate", help="propozycja progów na części calibration")
    _common(ec)
    _run_options(ec, default_split="calibration")
    ec.add_argument("--target-accuracy", type=float, default=0.90)
    ec.add_argument("--grid", default="0.50:0.99:0.01")
    return parser


# ---------------------------------------------------------------------------------------------
def _emit(output: str, envelope: Envelope, text: Callable[[dict[str, Any]], str] | None) -> int:
    if output == "json":
        sys.stdout.write(json.dumps(envelope.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")
    elif envelope.ok:
        if text is not None:
            sys.stdout.write(text(envelope.result or {}) + "\n")
        for w in envelope.warnings:
            sys.stderr.write(f"Ostrzeżenie: {w}\n")
    else:
        assert envelope.error is not None
        sys.stderr.write(f"Błąd ({envelope.error.code}): {envelope.error.message}\n")
        if envelope.error.hint:
            sys.stderr.write(f"Wskazówka: {envelope.error.hint}\n")
    return envelope.exit_code


def _error(command: str, exc: MapQAError) -> Envelope:
    return Envelope(ok=False, command=command, exit_code=exc.exit_code, error=ErrorInfo(code=exc.code, message=exc.message, hint=exc.hint))


def _loaded(args: argparse.Namespace):
    return load(source=getattr(args, "source", None), config_path=args.config, env=os.environ, cwd=Path.cwd())


def _cmd_sources_list(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    loaded = _loaded(args)
    rows = []
    for name, src in sorted(loaded.config.sources.items()):
        rows.append(
            {
                "name": name,
                "type": src.type,
                "access": getattr(src, "access", "local"),
                "is_default": name == loaded.source_name,
                "resolved_by": loaded.resolved_by if name == loaded.source_name else None,
            }
        )
    return {"sources": rows}, []


def _text_sources_list(result: dict[str, Any]) -> str:
    lines = ["Źródła danych:"]
    for s in result["sources"]:
        mark = " (domyślne, " + str(s["resolved_by"]) + ")" if s["is_default"] else ""
        lines.append(f"  {s['name']}: {s['type']}/{s['access']}{mark}")
    return "\n".join(lines)


def _cmd_sources_check(args: argparse.Namespace) -> tuple[dict[str, Any], list[str]]:
    bbox = Bbox.parse(args.bbox) if args.bbox else Bbox(19.80, 49.95, 20.15, 50.15)
    loaded = _loaded(args)
    adapter = build_adapter(loaded.source_name, loaded.source, Path.cwd())
    tables = adapter.check(bbox)
    reference = {"osm_roads": 99768, "overture_segments": 85405, "photos": 561, "photo_road_links": 561, "traffic_signs": 1730}
    warnings = [
        f"liczność {t} ({v['total']}) różni się od referencji plików kursu ({reference[t]})"
        for t, v in tables.items()
        if t in reference and v["total"] != reference[t]
    ]
    return {"name": loaded.source_name, "reachable": True, "bbox": bbox.as_text(), "tables": tables}, warnings


def _text_sources_check(result: dict[str, Any]) -> str:
    lines = [f"Źródło {result['name']}: dostępne (bbox {result['bbox']})"]
    for t, v in result["tables"].items():
        lines.append(f"  {t}: {v['total']} (w bbox: {v['in_bbox']})")
    return "\n".join(lines)


def validate_run_args(args: argparse.Namespace) -> tuple[Bbox | None, list[str]]:
    """Checks that must fail with code 1 before any data is read (PRD F1.1)."""
    bbox = Bbox.parse(args.bbox) if args.bbox else None
    attributes = [a.strip() for a in args.attributes.split(",") if a.strip()]
    unknown = [a for a in attributes if a not in ATTRIBUTES]
    if unknown or not attributes:
        raise ValidationError(f"Nieznany atrybut: {', '.join(unknown) or '(pusty)'}", code="invalid_attribute", hint="Dozwolone: " + ", ".join(ATTRIBUTES))
    not_mvp = [a for a in attributes if a not in MVP_ATTRIBUTES]
    if not_mvp:
        raise ValidationError(f"Atrybut niedostępny w MVP: {', '.join(not_mvp)}", code="invalid_attribute", hint="MVP obsługuje speed_limit (PRD §9)")
    if args.dataset != "signs":
        raise ValidationError("Zestaw photos będzie dostępny od przyrostu P1", code="dataset_not_available", hint="Użyj --dataset signs")
    if (args.model or args.cache_only) and args.no_model:
        raise ValidationError("Flagi --model/--cache-only i --no-model wykluczają się", code="invalid_flags")
    for name in ("max_queries", "max_images"):
        value = getattr(args, name)
        if value is not None and value < 0:
            raise ValidationError(f"--{name.replace('_', '-')} musi być liczbą ≥ 0", code="invalid_limits")
    if args.max_usd is not None:
        try:
            usd = Decimal(args.max_usd)
        except InvalidOperation:
            raise ValidationError("--max-usd musi być kwotą, np. 1.00", code="invalid_limits") from None
        if not usd.is_finite() or usd < 0:
            raise ValidationError("--max-usd musi być kwotą ≥ 0", code="invalid_limits")
    return bbox, attributes


def _cmd_run(args: argparse.Namespace) -> tuple[dict[str, Any], list[str], int]:
    bbox, attributes = validate_run_args(args)
    from mapqa.pipeline import run_command  # imported lazily: heavy modules only for run

    return run_command(args, bbox=bbox, attributes=attributes, eval_mode=None)


def _cmd_eval(args: argparse.Namespace) -> tuple[dict[str, Any], list[str], int]:
    bbox, attributes = validate_run_args(args)
    from mapqa.pipeline import run_command

    return run_command(args, bbox=bbox, attributes=attributes, eval_mode=args.eval_command)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    wants_json = "--output=json" in argv or any(a == "--output" and b == "json" for a, b in zip(argv, argv[1:]))
    try:
        args = parser.parse_args(argv)
    except SystemExit as exc:  # --help / --version
        return int(exc.code or 0)
    except _ArgError as exc:
        env = Envelope(ok=False, command=" ".join(argv[:2]), exit_code=1, error=ErrorInfo(code="invalid_arguments", message=str(exc)))
        return _emit("json" if wants_json else "text", env, None)

    if args.command is None:
        parser.print_help()
        return 0
    command = args.command
    handlers: dict[str, Any] = {}
    if command == "sources":
        if args.sources_command is None:
            sys.stdout.write("Użycie: mapqa sources {list,check}\n")
            return 1
        command = f"sources {args.sources_command}"
        handlers = {
            "sources list": (_cmd_sources_list, _text_sources_list),
            "sources check": (_cmd_sources_check, _text_sources_check),
        }
    elif command == "eval":
        if args.eval_command is None:
            sys.stdout.write("Użycie: mapqa eval {run,calibrate}\n")
            return 1
        command = f"eval {args.eval_command}"

    output = getattr(args, "output", "text")
    try:
        if command in handlers:
            fn, text = handlers[command]
            result, warnings = fn(args)
            env = Envelope(ok=True, command=command, exit_code=0, result=result, warnings=warnings)
            return _emit(output, env, text)
        if command == "run" or command.startswith("eval "):
            fn2 = _cmd_run if command == "run" else _cmd_eval
            result, warnings, code = fn2(args)
            from mapqa.pipeline import text_summary

            env = Envelope(ok=True, command=command, exit_code=code, result=result, warnings=warnings)
            return _emit(output, env, text_summary)
    except MapQAError as exc:
        return _emit(output, _error(command, exc), None)
    except Exception as exc:  # last resort: still one JSON envelope for agents (TAC-02), no secrets in type name
        env = Envelope(
            ok=False, command=command, exit_code=1, error=ErrorInfo(code="internal_error", message=f"Nieoczekiwany błąd: {type(exc).__name__}")
        )
        return _emit(output, env, None)
    return 1  # pragma: no cover
