"""Static architecture checks (ADR-000 TAC-12, TAC-15; ADR-004 TAC-004-07)."""

from __future__ import annotations

import ast
import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[2] / "src" / "mapqa"
CORE = ("matching", "normalize", "compare", "cascade", "candidates", "evaluation")
FORBIDDEN_IN_CORE = ("httpx", "mapqa.sources.databricks", "mapqa.cli")
FORBIDDEN_ANYWHERE = ("geopandas", "shapely", "pyproj", "pandas")


def _py_files() -> list[Path]:
    return sorted(SRC.rglob("*.py"))


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def _module_of(path: Path) -> str:
    return path.relative_to(SRC).parts[0]


def check_core_imports(files: list[Path]) -> list[str]:
    bad = []
    for f in files:
        if _module_of(f) in CORE:
            for name in _imports(f):
                if name.startswith(FORBIDDEN_IN_CORE):
                    bad.append(f"{f.relative_to(SRC)} imports {name}")
    return bad


def check_label_isolation(files: list[Path]) -> list[str]:
    bad = []
    for f in files:
        if _module_of(f) == "evaluation":
            continue
        text = f.read_text(encoding="utf-8")
        if any(n.startswith("mapqa.evaluation.labels") for n in _imports(f)):
            bad.append(f"{f.relative_to(SRC)} imports evaluation.labels")
        if re.search(r"reference_labels\.csv|labels\.csv", text):
            bad.append(f"{f.relative_to(SRC)} mentions a labels file")
    return bad


def check_no_dataframe_libs(files: list[Path]) -> list[str]:
    return [
        f"{f.relative_to(SRC)} imports {n}"
        for f in files
        for n in _imports(f)
        if n.split(".")[0] in FORBIDDEN_ANYWHERE
    ]


def check_metric_sql(files: list[Path]) -> list[str]:
    bad = []
    sql_texts = [(p, p.read_text(encoding="utf-8")) for p in SRC.rglob("*.sql")]
    sql_texts += [(p, p.read_text(encoding="utf-8")) for p in files]
    for path, text in sql_texts:
        for m in re.finditer(r"ST_(Distance|DWithin)\s*\(([^)]*)\)", text):
            args = m.group(2)
            # matching/crs.py is the single sanctioned SQL builder: it validates the _2180 suffix at runtime
            # (TAC-002-01 test), so f-string placeholders are allowed there and nowhere else
            if path.name == "crs.py" and re.fullmatch(r"\s*\{\w+\}\s*,\s*\{\w+\}\s*", args):
                continue
            if "_2180" not in args:
                bad.append(f"{path.name}: {m.group(0)}")
        for m in re.finditer(r"ST_Transform\s*\(([^;]*?)\)", text):
            if "4326" in m.group(1) and "always_xy" not in m.group(1):
                bad.append(f"{path.name}: ST_Transform without always_xy")
    return bad


def test_core_does_not_import_adapters_or_cli() -> None:  # TAC-12
    assert check_core_imports(_py_files()) == []


def test_only_evaluation_touches_labels() -> None:  # TAC-12, TAC-004-07
    assert check_label_isolation(_py_files()) == []


def test_no_dataframe_or_geo_libs_in_runtime() -> None:  # TAC-15
    assert check_no_dataframe_libs(_py_files()) == []


def test_metric_sql_uses_2180_and_always_xy() -> None:  # TAC-15
    assert check_metric_sql(_py_files()) == []


def test_checks_detect_violations(tmp_path: Path) -> None:
    """Controlled mutation: each check must flag a planted violation."""
    core = tmp_path / "cascade"
    core.mkdir()
    bad = core / "bad.py"
    bad.write_text("import httpx\nimport pandas\nX = 'signs/labels.csv'\nQ = 'ST_Distance(a.geom, b.geom)'\n", encoding="utf-8")
    global SRC
    original = SRC
    SRC = tmp_path
    try:
        files = [bad]
        assert check_core_imports(files)
        assert check_label_isolation(files)
        assert check_no_dataframe_libs(files)
        assert check_metric_sql(files)
    finally:
        SRC = original
