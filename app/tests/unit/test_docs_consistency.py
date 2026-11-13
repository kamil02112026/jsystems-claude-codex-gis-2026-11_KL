"""Guards against stale statements coming back into PRD, ADR, plans and AGENTS.md."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
DOCS = [ROOT / "docs" / "PRD.md", ROOT / "AGENTS.md"]
ADRS = sorted((ROOT / "docs" / "ADR").glob("*.md"))
PLANS = sorted((ROOT / "docs" / "plans").glob("*.md"))
ALL_DOCS = DOCS + ADRS + PLANS

TEST_ID = re.compile(r"\b([A-Z]{2,4})-(\d{2})(?:\.\.(\d{2}))?\b")
# Plan-internal identifiers and external names that look like test IDs.
IGNORED_PREFIXES = {"GP", "G", "M", "U", "T", "A"}
STALE_IMAGE_LIMITS = re.compile(r"256–1568|256 / krótszy bok|do 256 px")


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _expand_ids(text: str) -> set[str]:
    ids: set[str] = set()
    for prefix, start, end in TEST_ID.findall(text):
        if prefix in IGNORED_PREFIXES:
            continue
        for n in range(int(start), int(end or start) + 1):
            ids.add(f"{prefix}-{n:02d}")
    return ids


def test_no_stale_image_limits() -> None:
    hits = [p.name for p in ALL_DOCS if STALE_IMAGE_LIMITS.search(_read(p))]
    assert not hits, f"stale 256 px image limits in: {hits}"


def test_typer_only_as_superseded() -> None:
    offenders = []
    for path in ALL_DOCS:
        in_d13 = False
        for number, line in enumerate(_read(path).splitlines(), start=1):
            if line.startswith("### "):
                in_d13 = line.startswith("### D13")
            if "Typer" in line and "Superseded" not in line and not in_d13:
                offenders.append(f"{path.name}:{number}")
    assert not offenders, f"Typer mentioned outside Superseded/D13: {offenders}"


def test_plan_test_ids_exist_in_specs() -> None:
    known: set[str] = set()
    for path in [ROOT / "docs" / "PRD.md", *ADRS]:
        known |= _expand_ids(_read(path))
    missing: set[str] = set()
    for path in PLANS:
        missing |= _expand_ids(_read(path)) - known
    assert not missing, f"test IDs used in plans but absent from PRD/ADR: {sorted(missing)}"
