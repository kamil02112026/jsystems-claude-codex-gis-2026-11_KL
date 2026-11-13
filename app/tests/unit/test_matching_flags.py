"""ADR-002 §3.3 road-tag flags — one shared copy for own and provided links."""

import pytest

from mapqa.matching import provided, spatial
from mapqa.matching.flags import grade_separated_tags, service_or_restricted_tags


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"bridge": "yes"}, True),
        ({"tunnel": "building_passage"}, True),
        ({"bridge": "no", "tunnel": None}, False),
        ({"layer": "1"}, True),
        ({"layer": "-1"}, True),
        ({"layer": "0"}, False),
        ({"layer": "-1;0"}, False),  # non-numeric layer: no flag, no crash
        ({}, False),
    ],
)
def test_grade_separated_tags(tags, expected):
    assert grade_separated_tags(tags) is expected


@pytest.mark.parametrize(
    ("tags", "expected"),
    [
        ({"highway": "service"}, True),
        ({"highway": "residential", "access": "private"}, True),
        ({"motor_vehicle": "destination"}, True),
        ({"access": "yes", "motor_vehicle": "permissive"}, False),
        ({"highway": "track"}, False),
    ],
)
def test_service_or_restricted_tags(tags, expected):
    assert service_or_restricted_tags(tags) is expected


def test_single_copy_used_by_both_matchers():
    assert provided.grade_separated_tags is spatial.grade_separated_tags is grade_separated_tags
    assert provided.service_or_restricted_tags is spatial.service_or_restricted_tags is service_or_restricted_tags
