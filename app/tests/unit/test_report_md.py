"""RPT-01, RPT-02, RPT-04, TAC-004-01, TAC-004-03, TAC-11 (ADR-004 §3.5-3.6)."""

from __future__ import annotations

import re
from decimal import Decimal
from pathlib import Path

from PIL import Image

from mapqa.candidates.queue import QueueItem
from mapqa.contract.models import RejectedRecord, SourceDescriptor
from mapqa.report.thumbs import make_thumbnail
from mapqa.report.viewmodel import (
    Attribution,
    CircuitInfo,
    Completeness,
    CostSummary,
    DatasetCount,
    FunnelRow,
    ModelLevel,
    ReportViewModel,
)
from mapqa.report.writer import write_run

HEADINGS = [
    "Parametry uruchomienia",
    "Profil danych",
    "Lejek kaskady",
    "Podsumowanie kandydatów",
    "Kolejka ręcznej weryfikacji",
    "Rozbieżności znak ↔ OSM",
    "Ewaluacja",
    "Koszt",
    "Licencje i atrybucja",
]


def make_item(n: int = 1, **kw: str) -> QueueItem:
    base = dict.fromkeys(QueueItem.__dataclass_fields__, "")
    base.update(
        item_id=f"id{n:014d}",
        typ="kandydat_rozbieżności",
        atrybut="maxspeed",
        priorytet="wysoki",
        powod="OSM `maxspeed=50`, odczyt 30 | Flagi: `service_way`.",
        photo_id=f"p{n}",
        photo_author="Zażółć <Gęślą> | Jaźń",
        photo_license="CC BY-SA 4.0",
        photo_source_url="https://www.mapillary.com/app/?pKey=1",
        osm_way_id="123",
        osm_normalized="50",
        l1_model="m1",
        l1_answer="30",
        l1_probability="0.55",
        l2_model="m2",
        l2_answer="30",
        l2_probability="0.97",
        resolved_by="2",
        final_status="resolved",
    )
    base.update(kw)
    return QueueItem(**base)


def make_vm(**kw: object) -> ReportViewModel:
    vm = ReportViewModel(
        run_id="20261112T100000Z-abc123",
        bbox_text="brak filtra",
        attributes=["maxspeed"],
        dataset="course",
        source=SourceDescriptor(name="local", type="parquet", access="local"),
        dataset_counts=[DatasetCount("osm", 100, 90)],
        completeness=[Completeness("maxspeed", 95, 100, implicit_count=5)],
        rejected=[RejectedRecord(dataset="osm", record_id="1", reason="invalid_value")],
        funnel=[FunnelRow("maxspeed", 10, 6, 4, 3, 1)],
        candidates_by_priority={"maxspeed": {"wysoki": 1}},
        cost=CostSummary(total_usd=Decimal("0.0123")),
    )
    for k, v in kw.items():
        setattr(vm, k, v)
    return vm


def render(tmp_path: Path, vm: ReportViewModel, queue: list[QueueItem] | None = None) -> str:
    write_run(tmp_path, vm, queue if queue is not None else [], {"run_id": vm.run_id}, None)
    return (tmp_path / "report.md").read_text(encoding="utf-8")


def make_image(path: Path) -> Path:
    Image.new("RGB", (800, 400), (200, 10, 10)).save(path)
    return path


def test_sections_in_adr_order(tmp_path: Path) -> None:
    text = render(tmp_path, make_vm(), [make_item()])
    assert re.findall(r"^## \d+\. (.+)$", text, flags=re.M) == HEADINGS


def test_no_model_text_and_zero_candidates(tmp_path: Path) -> None:
    text = render(tmp_path, make_vm(model_reading=False))
    assert "Odczyt modelem nie był uruchomiony" in text
    assert "Brak kandydatów" in text


def test_model_run_has_no_no_model_text(tmp_path: Path) -> None:
    vm = make_vm(model_reading=True, confirmation="flag_yes", models=[ModelLevel(1, "m1", "low")])
    assert "Odczyt modelem nie był uruchomiony" not in render(tmp_path, vm, [make_item()])


def test_candidate_row_fields_and_escaping(tmp_path: Path) -> None:  # RPT-02
    rel = make_thumbnail(make_image(tmp_path / "src.png"), tmp_path, "a" * 64)
    vm = make_vm(
        model_reading=True,
        thumbs={"p1": rel},
        attributions=[Attribution("p1", "A", "CC BY-SA 4.0", "https://x.y/1")],
    )
    text = render(tmp_path, vm, [make_item()])
    assert f"thumbs/{'a' * 64}.jpg" in text
    assert "https://www.openstreetmap.org/way/123" in text
    assert "CC BY-SA 4.0" in text and "0,97" in text and "0,55" in text
    assert "Zażółć &lt;Gęślą&gt; \\| Jaźń" in text
    assert "<Gęślą>" not in text


def test_missing_thumbnail_text(tmp_path: Path) -> None:
    text = render(tmp_path, make_vm(thumbs={"p1": None}), [make_item()])
    assert "Miniatura niedostępna" in text
    assert "https://www.mapillary.com/app/?pKey=1" in text


def test_thumbnail_size_and_missing_source(tmp_path: Path) -> None:
    src = make_image(tmp_path / "s.png")
    rel = make_thumbnail(src, tmp_path / "run", "b" * 64)
    assert rel == f"thumbs/{'b' * 64}.jpg"
    with Image.open(tmp_path / "run" / rel) as im:
        assert im.format == "JPEG" and max(im.size) == 320
    assert make_thumbnail(tmp_path / "nope.png", tmp_path / "run", "c" * 64) is None
    (tmp_path / "bad.png").write_bytes(b"not an image")
    assert make_thumbnail(tmp_path / "bad.png", tmp_path / "run", "d" * 64) is None


def test_relative_thumb_links_exist_and_no_base64(tmp_path: Path) -> None:  # TAC-004-03
    rel = make_thumbnail(make_image(tmp_path / "s.png"), tmp_path, "e" * 64)
    text = render(tmp_path, make_vm(thumbs={"p1": rel}), [make_item()])
    links = re.findall(r"\((thumbs/[^)]+)\)", text)
    assert links and all((tmp_path / link).is_file() for link in links)
    assert "data:image" not in text


def test_input_modified_warning_header(tmp_path: Path) -> None:
    vm = make_vm(input_modified=True, input_modified_paths=["a.parquet"])
    text = render(tmp_path, vm)
    assert "Dane wejściowe zmieniły się w trakcie uruchomienia — wyniki niewiarygodne" in text
    assert "a.parquet" in text
    assert text.index("wyniki niewiarygodne") < text.index("## 1.")
    assert "wyniki niewiarygodne" not in render(tmp_path, make_vm())


def test_licenses_section(tmp_path: Path) -> None:  # RPT-04
    text = render(tmp_path, make_vm())
    assert "ODbL 1.0" in text and "CC BY-SA 4.0" in text
    assert "Kandydat nie oznacza błędu mapy; decyzję podejmuje człowiek." in text


def test_profile_sample_bias_and_completeness(tmp_path: Path) -> None:
    text = render(tmp_path, make_vm())
    assert "95% (95/100)" in text
    assert "Obciążenie próbki" in text
    assert "invalid_value" in text


def test_circuit_open_and_queue_limit(tmp_path: Path) -> None:
    vm = make_vm(model_reading=True, cost=CostSummary(total_usd=Decimal("1"), circuit=CircuitInfo("429", 7)))
    text = render(tmp_path, vm, [make_item(n) for n in range(1, 206)])
    assert "Odczyt przerwany: błąd API" in text and "429" in text
    assert text.count("openstreetmap.org/way/123") == 200
    assert "manual_queue.csv" in text


def test_deterministic(tmp_path: Path) -> None:  # TAC-004-01
    a, b = tmp_path / "a", tmp_path / "b"
    for d in (a, b):
        d.mkdir()
        write_run(d, make_vm(), [make_item()], {"run_id": "x", "b": 1, "a": 2}, None)
    for name in ("report.md", "manual_queue.csv", "run.json"):
        assert (a / name).read_bytes() == (b / name).read_bytes()
    run_json = (a / "run.json").read_text(encoding="utf-8")
    assert run_json.index('"a"') < run_json.index('"b"')
