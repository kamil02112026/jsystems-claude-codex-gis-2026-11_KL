"""Plain-data view model for report.md (ADR-004 §3.6). Filled by the pipeline, rendered by Jinja2."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from mapqa.contract.models import Confirmation, RejectedRecord, RunLimits, SourceDescriptor
from mapqa.evaluation.baseline import OsmDiscrepancies
from mapqa.evaluation.metrics import EvaluationReport, Metric

SAMPLE_BIAS_NOTE = (
    "Obciążenie próbki: dostarczone zdjęcia Mapillary dobrano przez znaki, a 95% dróg połączonych ze zdjęciami "
    "ma `maxspeed` (wobec 16,3% w całym OSM). Wyników nie uogólniamy na całe miasto; status `osm_missing` "
    "jest w próbce rzadki."
)


@dataclass
class ModelLevel:
    level: int
    model: str
    effort: str | None = None


@dataclass
class DatasetCount:
    dataset: str
    total: int
    in_bbox: int


@dataclass
class Completeness:
    attribute: str
    numerator: int
    denominator: int
    implicit_count: int = 0  # maxspeed: PL:* types counted in numerator


@dataclass
class FunnelRow:
    attribute: str
    total: int
    resolved_l1: int
    escalated: int
    resolved_l2: int
    handed_to_human: int
    abstain: int = 0
    model_unavailable: int = 0
    budget_exceeded: int = 0
    image_out_of_bounds: int = 0
    skipped_no_model: int = 0


@dataclass
class CircuitInfo:
    error_code: str
    skipped_questions: int  # questions with status circuit_open


@dataclass
class CostSummary:
    total_usd: Decimal = Decimal(0)
    per_level_usd: dict[str, Decimal] = field(default_factory=dict)  # "1", "2", ...
    per_query_usd: Decimal | None = None
    per_candidate_usd: Decimal | None = None
    cache_hits: int = 0
    estimated: bool = False
    queries_used: int = 0
    images_used: int = 0
    budget_exceeded_count: int = 0
    circuit: CircuitInfo | None = None


@dataclass
class Attribution:
    photo_id: str
    author: str
    license: str
    source_url: str


@dataclass
class ReportViewModel:
    run_id: str
    tool_version: str = ""
    # 1. run parameters
    bbox_text: str = "brak filtra"
    attributes: list[str] = field(default_factory=list)
    dataset: str = ""
    source: SourceDescriptor | None = None
    model_reading: bool = False
    confirmation: Confirmation | None = None
    cost_manifest: dict[str, Any] | None = None
    models: list[ModelLevel] = field(default_factory=list)
    thresholds: dict[str, float] = field(default_factory=dict)
    uncalibrated_warnings: list[str] = field(default_factory=list)
    limits: RunLimits = field(default_factory=RunLimits)
    # 2. profile
    dataset_counts: list[DatasetCount] = field(default_factory=list)
    completeness: list[Completeness] = field(default_factory=list)
    rejected: list[RejectedRecord] = field(default_factory=list)
    profile_warnings: list[str] = field(default_factory=list)
    link_agreement: tuple[int, int] | None = None  # own osm_way_id == photo_road_links.csv (F3.5, MAT-07)
    link_flags: dict[str, int] = field(default_factory=dict)  # photo→road flags, marked not hidden (F3.3)
    sample_bias_note: str = SAMPLE_BIAS_NOTE
    # 3. cascade funnel
    funnel: list[FunnelRow] = field(default_factory=list)
    # 4. candidates: attribute -> priority -> count; reason -> count of not_comparable
    candidates_by_priority: dict[str, dict[str, int]] = field(default_factory=dict)
    not_comparable_reasons: dict[str, int] = field(default_factory=dict)
    # 5. queue rendering helpers: photo_id -> relative thumb path (None = unavailable)
    thumbs: dict[str, str | None] = field(default_factory=dict)
    # 6. sign vs OSM discrepancies
    osm_discrepancies: OsmDiscrepancies | None = None
    discrepancy_distribution: dict[str, int] = field(default_factory=dict)  # label -> count
    # 7. evaluation (baseline_mapillary is shown also without model reading)
    evaluation: EvaluationReport | None = None
    baseline_mapillary: Metric | None = None
    # 8. cost
    cost: CostSummary = field(default_factory=CostSummary)
    # 9. attribution of shown photos
    attributions: list[Attribution] = field(default_factory=list)
    # input_modified (exit code 4)
    input_modified: bool = False
    input_modified_paths: list[str] = field(default_factory=list)
