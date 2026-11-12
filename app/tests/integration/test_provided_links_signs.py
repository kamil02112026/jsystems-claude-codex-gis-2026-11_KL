"""T10/T11 on real course data: provided links and signs profile (ADR-002 §3.3–§3.4, MAT-08, HDG-02; PRD F2.3, §7)."""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import pytest

from mapqa.config.schema import FilesSource
from mapqa.matching.provided import map_provided_links
from mapqa.profile.profile import build_profile
from mapqa.sources.files import FilesAdapter


@pytest.fixture(scope="module")
def bundle(data_dir: Path):
    return FilesAdapter("files", FilesSource(type="files", path=str(data_dir))).load_signs(bbox=None)


def test_mat08_every_photo_keeps_a_link_and_flags(bundle) -> None:
    links = map_provided_links(bundle)
    assert len(links) == 119
    assert {lk.link_source for lk in links.values()} == {"provided"}
    counts = Counter(f for lk in links.values() for f in lk.flags if f != "missing_heading")
    assert counts == {"ambiguous_candidates": 35, "poor_heading_alignment": 9, "service_way": 6, "outside_standard_25m": 4}


def test_hdg02_missing_heading_only_for_null(bundle) -> None:
    links = map_provided_links(bundle)
    null_heading = {s.photo_id for s in bundle.signs if s.heading is None}
    flagged = {pid for pid, lk in links.items() if "missing_heading" in lk.flags}
    assert flagged == null_heading


def test_profile_signs(bundle) -> None:
    prof = build_profile(bundle, bbox_text=None)
    assert prof.counts["signs"] == {"total": 119, "in_bbox": 119}
    assert prof.rejected_by_reason == {}
    m = prof.maxspeed
    assert m.denominator == 119
    # 97 rows have a number (119 - 22 empty); + PL:* defaults for rows without a number
    assert m.with_number == 97
    assert m.numerator >= m.with_number
    assert m.implicit_without_number == m.numerator - m.with_number
    assert "obciążon" in prof.sample_note
