"""`mapqa run` / `mapqa eval`: F2 → F7 for the signs and photos datasets (ADR-000 §6, D11, D12; ADR-003 §3.5; ADR-004 §3.5)."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from mapqa import __version__
from mapqa.budget.budget import Budget
from mapqa.budget.cost_log import CostLog
from mapqa.cache.sqlite_cache import AnswerCache, CacheKey
from mapqa.candidates.queue import QueueItem, build_queue
from mapqa.candidates.rules import CandidateInput, build_candidates
from mapqa.cascade.cascade import Cascade
from mapqa.cascade.ports import ModelPort, PortResult
from mapqa.config import LoadedConfig, load
from mapqa.contract.bundle import Bbox, SignsBundle
from mapqa.contract.errors import ConfirmationRequired, InputModified, ValidationError
from mapqa.datasets import DatasetView, photos_bbox, photos_view, signs_view
from mapqa.contract.hashing import sha256_file
from mapqa.contract.models import AttributeValue, CascadeResult, Confirmation, RunLimits
from mapqa.evaluation import calibrate, calibration_pairs, evaluation_input_files, photo_split, run_evaluation
from mapqa.models.image_prep import ImageOutOfBounds, PreparedImage, prepare_image
from mapqa.questions.catalog import SPEED_LIMIT_VALUE
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
from mapqa.sources.registry import build_adapter

QUESTION = SPEED_LIMIT_VALUE
ATTRIBUTE = "speed_limit"


def build_port(loaded: LoadedConfig) -> ModelPort:
    """Real OpenRouter client (T20). Built only after confirmation, never in no-model mode (TAC-13)."""
    from mapqa.models.openrouter import OpenRouterPort  # noqa: PLC0415 - created lazily on purpose

    return OpenRouterPort.from_env(loaded.config)


def _stdin_is_tty() -> bool:
    """True only for an interactive console. On Windows the NUL device reports isatty() == True,
    so we additionally require a real console handle (GetConsoleMode succeeds)."""
    if sys.stdin is None or not sys.stdin.isatty():
        return False
    if os.name != "nt":
        return True
    import ctypes  # noqa: PLC0415
    import msvcrt  # noqa: PLC0415

    try:
        handle = msvcrt.get_osfhandle(sys.stdin.fileno())
    except (OSError, ValueError):
        return False
    mode = ctypes.c_uint32()
    return bool(ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)))


def _sha256(path: Path) -> str | None:
    return sha256_file(path) if path.is_file() else None


def _hash_all(paths: list[Path]) -> dict[str, str | None]:
    """sha256 of every input file plus a listing hash of each input directory, so a file added to or
    removed from an input directory during the run is detected too (ADR-000 §6, review #5)."""
    out: dict[str, str | None] = {str(p): _sha256(p) for p in paths}
    for d in sorted({p.parent for p in paths}):
        names = sorted(x.name for x in d.iterdir() if x.is_file()) if d.is_dir() else []
        out[f"{d}{os.sep}*"] = hashlib.sha256("\n".join(names).encode("utf-8")).hexdigest()
    return out


# ---- configuration with CLI overrides ---------------------------------------------------------
def _apply_overrides(loaded: LoadedConfig, args: argparse.Namespace) -> None:
    c = loaded.config
    lim = c.limits.model_copy()
    if args.max_queries is not None:
        lim.max_queries = args.max_queries
    if args.max_images is not None:
        lim.max_images = args.max_images
    if getattr(args, "cache_only", False):
        lim.max_images = 0  # guard: no new image may be read, so no request can be sent
    if args.max_usd is not None:
        lim.max_usd = Decimal(args.max_usd)
    c.limits = RunLimits.model_validate(lim.model_dump())
    if args.level1_model:
        c.models.level1 = args.level1_model
    if args.level2_model:
        c.models.level2 = args.level2_model
    if args.level2_effort:
        c.models.level2_effort = args.level2_effort
    for level, value, model in ((1, args.threshold_l1, c.models.level1), (2, args.threshold_l2, c.models.level2)):
        if value is not None:
            c.thresholds.setdefault(f"level{level}", {}).setdefault(model, {})[ATTRIBUTE] = value


def _run_id(params: dict[str, Any], now: datetime) -> str:
    digest = hashlib.sha256(json.dumps(params, sort_keys=True, default=str).encode()).hexdigest()[:6]
    return now.strftime("%Y%m%dT%H%M%SZ") + "-" + digest


def _parse_grid(text: str) -> list[float]:
    """'0.50:0.99:0.01' → [0.50, 0.51, ..., 0.99] (ADR-000 §6 eval calibrate --grid)."""
    try:
        start, stop, step = (Decimal(x) for x in text.split(":"))
    except (ValueError, ArithmeticError):
        raise ValidationError("--grid musi mieć postać start:stop:krok, np. 0.50:0.99:0.01", code="invalid_grid") from None
    if step <= 0 or start > stop or start < 0 or stop > 1:
        raise ValidationError("--grid: 0 ≤ start ≤ stop ≤ 1 i krok > 0", code="invalid_grid")
    values, v = [], start
    while v <= stop:
        values.append(float(v))
        v += step
    return values


def _unique_out_dir(base: Path, run_id: str) -> tuple[Path, str]:
    """Never share a run directory between two runs started in the same second (review finding)."""
    candidate, n = run_id, 1
    while (base / candidate).exists():
        n += 1
        candidate = f"{run_id}-{n}"
    return base / candidate, candidate


@dataclass
class _ModelPhase:
    results: dict[str, CascadeResult]
    confirmation: Confirmation | None
    manifest: dict[str, Any] | None
    budget: Budget | None
    warnings: list[str]
    uncalibrated: list[str]
    cache_hits_l1: int


def _manifest(loaded: LoadedConfig, uncached_images: int) -> dict[str, Any]:
    """What the run may spend, stated before any request (D11). Upper bounds use the reserves (ADR-003 §3.6)."""
    c = loaded.config
    planned = min(uncached_images, c.limits.max_images)
    reserve = c.limits.reserve_usd
    max_cost = min(planned * (reserve["level1"] + reserve["level2"]), c.limits.max_usd)
    return {
        "images_without_cache": uncached_images,
        "planned_new_images": planned,
        "max_requests": min(planned * 2, c.limits.max_queries),
        "max_cost_usd": str(max_cost),
        "questions_per_image": 1,
        "models": {"level1": c.models.level1, "level2": f"{c.models.level2} (reasoning {c.models.level2_effort})"},
        "max_queries": c.limits.max_queries,
        "max_images": c.limits.max_images,
        "max_usd": str(c.limits.max_usd),
    }


def _confirm(manifest: dict[str, Any], args: argparse.Namespace) -> Confirmation:
    if args.yes:
        # never silent: the manifest is printed on stderr also when --yes skips the question
        sys.stderr.write("Płatny odczyt modelem (potwierdzony flagą --yes):\n" + json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
        sys.stderr.flush()
        return "flag_yes"
    if not _stdin_is_tty():
        raise ConfirmationRequired(
            "Odczyt modelem wymaga potwierdzenia, a wejście nie jest terminalem.",
            hint="Dodaj --yes albo uruchom bez --model.",
        )
    stream = sys.stderr if getattr(args, "output", "text") == "json" else sys.stdout
    stream.write("Płatny odczyt modelem:\n" + json.dumps(manifest, ensure_ascii=False, indent=2) + "\nKontynuować? [y/N] ")
    stream.flush()
    try:
        answer = input().strip().lower()  # no prompt argument: input() would write it to stdout
    except EOFError:  # stdin closed: no confirmation was given (D11)
        raise ConfirmationRequired(
            "Odczyt modelem wymaga potwierdzenia, a wejście zostało zamknięte.",
            hint="Dodaj --yes albo uruchom bez --model.",
        ) from None
    return "interactive" if answer in ("y", "t", "tak", "yes") else "declined"


def _model_phase(
    loaded: LoadedConfig, args: argparse.Namespace, bundle: SignsBundle, photo_ids: list[str], run_id: str, out_dir: Path
) -> _ModelPhase:
    c = loaded.config
    signs = {s.photo_id: s for s in bundle.signs}
    data_root = Path(loaded.source.path)  # type: ignore[union-attr]
    data_root = data_root if data_root.is_absolute() else Path.cwd() / data_root
    cache_path = Path(c.cache_dir)
    cache_path = (cache_path if cache_path.is_absolute() else Path.cwd() / cache_path) / "llm_cache.sqlite"
    cache = AnswerCache(cache_path)
    port: Any = None
    try:
        usable = [pid for pid in photo_ids if signs[pid].image_status == "ok"]
        uncached = [pid for pid in usable if _needs_request(cache, c, signs[pid].crop_sha256)]
        manifest = _manifest(loaded, len(uncached))
        cache_only = getattr(args, "cache_only", False) or not uncached
        confirmation: Confirmation = "cache_only" if cache_only else _confirm(manifest, args)
        if confirmation == "declined":
            skipped = {pid: CascadeResult(photo_sha256=signs[pid].crop_sha256, question_id=QUESTION.question_id, final_status="skipped_no_model") for pid in photo_ids}
            return _ModelPhase(skipped, "declined", manifest, None, ["model_reading_declined"], [], 0)

        port = _CacheOnlyPort() if cache_only else build_port(loaded)
        budget = Budget(c.limits)
        out_dir.mkdir(parents=True, exist_ok=True)
        cascade = Cascade(port, cache, budget, CostLog(out_dir / "costs.jsonl"), c, run_id)
        results: dict[str, CascadeResult] = {}
        hits = 0
        for pid in photo_ids:  # stable order (photo_id) → deterministic image limit (ADR-003 §3.6)
            sign = signs[pid]
            if sign.image_status != "ok":
                results[pid] = CascadeResult(photo_sha256=sign.crop_sha256, question_id=QUESTION.question_id, final_status="image_out_of_bounds", resolved_by="human")
                continue
            image: PreparedImage | ImageOutOfBounds
            try:
                image = prepare_image(data_root / sign.crop_path)
            except ImageOutOfBounds as exc:
                image = exc
            res = cascade.resolve(image_sha256=sign.crop_sha256, image=image, question=QUESTION, attribute=ATTRIBUTE)
            hits += sum(1 for a in res.attempts if a.level == 1 and a.cache_hit)
            results[pid] = res
        warnings = []
        exceeded = sum(1 for r in results.values() if r.final_status == "budget_exceeded")
        if exceeded:
            warnings.append(f"budget_exceeded: {exceeded} pytań")
        if budget.circuit_open:
            skipped = sum(1 for r in results.values() for a in r.attempts if a.error_class == "circuit_open")
            warnings.append(f"circuit_open: {budget.circuit_error_class}, {skipped} pytań")
        return _ModelPhase(results, confirmation, manifest, budget, warnings, cascade.uncalibrated_warnings(), hits)
    finally:
        if port is not None and hasattr(port, "close"):
            port.close()  # one HTTP client per run, closed also on failure (ADR-003 §3.3, review finding)
        cache.close()


def _needs_request(cache: AnswerCache, c: Any, sha: str) -> bool:
    """True when the cascade would send at least one request for this image (review #2, D11).

    L1 miss → request. L1 hit that is not confident at the L1 threshold escalates, so an L2 miss → request.
    """
    l1 = cache.get(CacheKey(1, sha, QUESTION.question_id, c.models.level1, "", QUESTION.prompt_version))
    if l1 is None:
        return True
    if l1.status_for(c.threshold(level=1, model=c.models.level1, attribute=ATTRIBUTE)) == "confident":
        return False
    l2 = cache.get(CacheKey(2, sha, QUESTION.question_id, c.models.level2, c.models.level2_effort, QUESTION.prompt_version))
    return l2 is None


class _CacheOnlyPort:
    """Used only when `_needs_request` found nothing to send. If it is ever reached, it fails safe:
    no network, `model_unavailable` (opens the breaker, visible as a warning) instead of a silent answer."""

    def ask(self, **_: Any) -> PortResult:
        return PortResult(answer=None, probability=None, parse_status="model_unavailable", error_class="cache_only_unexpected")


def _funnel(results: dict[str, CascadeResult]) -> FunnelRow:
    status = Counter(r.final_status for r in results.values())
    by = Counter(r.resolved_by for r in results.values() if r.final_status == "resolved")
    escalated = sum(1 for r in results.values() if any(a.level == 2 for a in r.attempts))
    human = sum(1 for r in results.values() if r.resolved_by == "human")
    return FunnelRow(
        attribute=ATTRIBUTE,
        total=len(results),
        resolved_l1=by.get("1", 0),
        escalated=escalated,
        resolved_l2=by.get("2", 0),
        handed_to_human=human,
        abstain=status.get("abstain", 0),
        model_unavailable=status.get("model_unavailable", 0),
        budget_exceeded=status.get("budget_exceeded", 0),
        image_out_of_bounds=status.get("image_out_of_bounds", 0),
        skipped_no_model=status.get("skipped_no_model", 0),
    )


def _completeness(profile: Any) -> list[Completeness]:
    rows = [Completeness("maxspeed", profile.maxspeed.numerator, profile.maxspeed.denominator, profile.maxspeed.implicit_without_number)]
    for name in ("surface", "lit"):
        value = getattr(profile, name)
        if value is not None:
            rows.append(Completeness(name, value.numerator, value.denominator))
    return rows


def _write_outputs(out_dir: Path, vm: ReportViewModel, queue: list[QueueItem], run_json: dict, evaluation_json: dict | None) -> dict[str, str]:
    return write_run(out_dir, vm, queue, run_json, evaluation_json)


# ---- entry point used by the CLI ----------------------------------------------------------------
def run_command(args: argparse.Namespace, *, bbox: Bbox | None, attributes: list[str], eval_mode: str | None) -> tuple[dict[str, Any], list[str], int]:
    loaded = load(source=args.source, config_path=args.config, env=os.environ, cwd=Path.cwd())
    _apply_overrides(loaded, args)
    c = loaded.config
    model_reading = eval_mode is not None or ((args.model or args.cache_only or c.model_reading) and not args.no_model)

    if args.dataset == "photos" and model_reading:
        raise ValidationError(
            "Odczyt modelem zestawu photos nie jest jeszcze dostępny (pytania o oświetlenie: plan v1 T46–T47)",
            code="model_not_available_for_dataset",
            hint="Uruchom --dataset photos z --no-model albo użyj --dataset signs",
        )
    if args.dataset == "photos" and loaded.source.type != "files":
        raise ValidationError(
            "Własne dopasowanie zestawu photos wymaga źródła files (Databricks: plan v1 T38–T41)",
            code="dataset_not_available",
            hint="Użyj --source files",
        )
    adapter = build_adapter(loaded.source_name, loaded.source, Path.cwd())
    descriptor = adapter.describe()
    started = datetime.now(UTC)
    labels_root = Path(c.labels_path)
    labels_root = labels_root if labels_root.is_absolute() else Path.cwd() / labels_root
    data_root = Path(loaded.source.path)  # type: ignore[union-attr]
    data_root = data_root if data_root.is_absolute() else Path.cwd() / data_root
    bundle: SignsBundle | None = None
    if args.dataset == "photos":
        area = photos_bbox(bbox)
        view: DatasetView = photos_view(adapter.load_photos(area), data_root, bbox, adapter.check(area))
    else:
        bundle = adapter.load_signs(bbox)
        view = signs_view(bundle, bbox)
    input_paths = [Path(p) for p in view.files_read] + evaluation_input_files(labels_root, args.dataset)
    hashes_before = _hash_all(input_paths)

    params = {
        "bbox": bbox.as_text() if bbox else None,
        "attributes": attributes,
        "source": loaded.source_name,
        "dataset": args.dataset,
        "model_reading": model_reading,
        "models": c.models.model_dump(),
        "limits": c.limits.model_dump(mode="json"),
        "split": args.split,
        "eval": eval_mode,
    }
    if eval_mode == "calibrate" and args.split != "calibration":
        raise ValidationError(
            "Kalibracja progów działa wyłącznie na części calibration (ADR-004 §3.9)", code="invalid_split", hint="Użyj --split calibration"
        )
    grid = _parse_grid(args.grid) if eval_mode == "calibrate" else None
    reports_dir = Path(c.reports_dir)
    out_dir, run_id = _unique_out_dir(reports_dir if reports_dir.is_absolute() else Path.cwd() / reports_dir, _run_id(params, started))

    split = photo_split(labels_root, args.dataset) if args.split != "all" else {}
    photo_ids = [pid for pid in view.photo_ids if args.split == "all" or split.get(pid) == args.split]
    links, osm_values, meta = view.links, view.osm_values, view.meta

    warnings: list[str] = list(view.warnings)
    phase: _ModelPhase | None = None
    if model_reading and bundle is not None:
        phase = _model_phase(loaded, args, bundle, photo_ids, run_id, out_dir)
        results = phase.results
        warnings += phase.warnings
    else:
        results = {pid: CascadeResult(photo_sha256=meta[pid].sha256, question_id=QUESTION.question_id, final_status="skipped_no_model") for pid in photo_ids}
    model_used = phase is not None and phase.confirmation != "declined"

    inputs = [
        CandidateInput(
            photo_id=pid,
            link=links[pid],
            osm=osm_values[pid],
            cascade=results[pid],
            photo_path=meta[pid].path,
            photo_captured_at=meta[pid].captured_at,
            photo_author=meta[pid].author,
            photo_license=meta[pid].license,
            photo_source_url=meta[pid].source_url,
        )
        for pid in photo_ids
    ]
    candidates = build_candidates(inputs)
    queue = build_queue(candidates, inputs)

    evaluation = run_evaluation(
        labels_root, results, split_name=None if args.split == "all" else args.split, with_model=model_used, photo_ids=set(photo_ids),
        dataset=args.dataset,
    )
    calibration: dict[str, Any] | None = None
    if eval_mode == "calibrate" and model_used:
        cal = calibrate(calibration_pairs(labels_root, results, level=1), target_accuracy=args.target_accuracy, grid=grid)
        calibration = cal.model_dump(mode="json") if hasattr(cal, "model_dump") else cal.__dict__

    # ---- report ---------------------------------------------------------------------------
    profile = view.profile
    out_dir.mkdir(parents=True, exist_ok=True)
    queue_photos = sorted({item.photo_id for item in queue})
    thumbs = {pid: make_thumbnail(data_root / meta[pid].path, out_dir, meta[pid].sha256) for pid in queue_photos if meta[pid].image_ok}
    budget = phase.budget if phase else None
    cost = CostSummary(
        total_usd=budget.cost_used_usd if budget else Decimal(0),
        cache_hits=phase.cache_hits_l1 if phase else 0,
        queries_used=budget.queries_used if budget else 0,
        images_used=budget.images_used if budget else 0,
        budget_exceeded_count=sum(1 for r in results.values() if r.final_status == "budget_exceeded"),
        circuit=CircuitInfo(error_code=budget.circuit_error_class or "", skipped_questions=sum(1 for r in results.values() for a in r.attempts if a.error_class == "circuit_open")) if budget and budget.circuit_open else None,
    )
    funnel = _funnel(results)
    vm = ReportViewModel(
        run_id=run_id,
        tool_version=__version__,
        bbox_text=bbox.as_text() if bbox else (photos_bbox(None).as_text() + " (domyślny bbox danych)" if args.dataset == "photos" else "brak filtra"),
        attributes=attributes,
        dataset=args.dataset,
        source=descriptor,
        model_reading=model_used,
        confirmation=phase.confirmation if phase else None,
        cost_manifest=phase.manifest if phase else None,
        models=[ModelLevel(1, c.models.level1), ModelLevel(2, c.models.level2, c.models.level2_effort)],
        thresholds={
            f"level1 {c.models.level1}": c.threshold(level=1, model=c.models.level1, attribute=ATTRIBUTE),
            f"level2 {c.models.level2}": c.threshold(level=2, model=c.models.level2, attribute=ATTRIBUTE),
        },
        uncalibrated_warnings=phase.uncalibrated if phase else [],
        limits=c.limits,
        dataset_counts=[DatasetCount(name, v["total"], v["in_bbox"]) for name, v in profile.counts.items()],
        completeness=_completeness(profile),
        rejected=view.rejected,
        link_agreement=(profile.agreement.numerator, profile.agreement.denominator) if profile.agreement else None,
        link_flags=dict(sorted(Counter(f for pid in photo_ids for f in links[pid].flags).items())),
        profile_warnings=profile.warnings,
        funnel=[funnel],
        candidates_by_priority={ATTRIBUTE: dict(sorted(Counter(cd.priority for cd in candidates).items()))},
        not_comparable_reasons=dict(sorted(Counter(v.note for v in osm_values.values() if v.status == "not_comparable").items())),
        thumbs=thumbs,
        osm_discrepancies=evaluation.discrepancies,
        evaluation=evaluation.report,
        baseline_mapillary=evaluation.baseline_mapillary,
        cost=cost,
        attributions=[Attribution(pid, meta[pid].author, meta[pid].license, meta[pid].source_url) for pid in queue_photos],
    )
    run_json: dict[str, Any] = {
        "run_id": run_id,
        "tool_version": __version__,
        "params": params,
        "confirmation": phase.confirmation if phase else None,
        "manifest": phase.manifest if phase else None,
        "source": {**descriptor.model_dump(mode="json"), "read_started_at": started.isoformat(timespec="seconds")},
        "funnel": funnel.__dict__,
        "candidates": len(candidates),
        "queue_items": len(queue),
        "warnings": warnings,
        "link_agreement": {"numerator": profile.agreement.numerator, "denominator": profile.agreement.denominator} if profile.agreement else None,
        "calibration": calibration,
    }
    evaluation_json = evaluation.report.model_dump(mode="json") if evaluation.report else None
    _write_outputs(out_dir, vm, queue, run_json, evaluation_json)
    if calibration is not None:
        (out_dir / "calibration.json").write_text(json.dumps(calibration, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    # ---- input manifest after the run (ADR-000 D12, exit code 4) -----------------------------
    hashes_after = _hash_all(input_paths)
    run_json["source"]["input_hashes"] = {p: {"before": hashes_before[p], "after": hashes_after[p]} for p in sorted(hashes_before)}
    run_json["source"]["read_finished_at"] = datetime.now(UTC).isoformat(timespec="seconds")
    changed = sorted(p for p in hashes_before if hashes_before[p] != hashes_after[p])
    if changed:
        vm.input_modified, vm.input_modified_paths = True, changed
        run_json["input_modified"] = changed
    write_run(out_dir, vm, queue, run_json, evaluation_json)
    if changed:
        raise InputModified("Dane wejściowe zmieniły się w trakcie uruchomienia — wyniki niewiarygodne: " + ", ".join(changed))

    result = {
        "run_id": run_id,
        "output_dir": str(out_dir),
        "files": sorted(p.name for p in out_dir.iterdir() if p.is_file()),
        "model_reading": model_used,
        "confirmation": phase.confirmation if phase else None,
        "manifest": phase.manifest if phase else None,
        "funnel": {**{k: v for k, v in funnel.__dict__.items() if k != "attribute"}, "cache_hits_l1": cost.cache_hits},
        "candidates": dict(Counter(cd.priority for cd in candidates)),
        "queue_items": len(queue),
        "cost_usd": str(cost.total_usd),
        "queries_used": cost.queries_used,
    }
    exit_code = 3 if (cost.budget_exceeded_count or cost.circuit) else 0
    return result, warnings, exit_code


def text_summary(result: dict[str, Any]) -> str:
    f = result["funnel"]
    lines = [
        f"Uruchomienie {result['run_id']} zakończone.",
        f"Wyniki: {result['output_dir']}",
        f"Odczyt modelem: {'tak' if result['model_reading'] else 'nie'}"
        + (f" (potwierdzenie: {result['confirmation']})" if result.get("confirmation") else ""),
        f"Zdjęcia: {f['total']}; rozstrzygnięte poziom 1: {f['resolved_l1']}, poziom 2: {f['resolved_l2']}, do człowieka: {f['handed_to_human']}, bez modelu: {f['skipped_no_model']}",
        f"Kandydaci: {result['candidates'] or 0}; pozycje kolejki: {result['queue_items']}",
        f"Koszt: {result['cost_usd']} USD, zapytania: {result['queries_used']}",
    ]
    return "\n".join(lines)
