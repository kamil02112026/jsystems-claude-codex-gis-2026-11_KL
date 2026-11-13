from __future__ import annotations

import random

import pytest
from pyproj import Geod, Transformer

from mapqa.contract.db import connect
from mapqa.matching.crs import distance_sql, initial_bearing, point_distance_m


def test_crs_01_point_distance_is_measured_in_epsg_2180() -> None:
    to_2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
    x, y = to_2180.transform(19.94, 50.06)
    lon1, lat1 = to_wgs84.transform(x, y)
    lon2, lat2 = to_wgs84.transform(x + 100, y)

    con = connect()
    try:
        assert point_distance_m(con, lon1, lat1, lon2, lat2) == pytest.approx(100, abs=0.01)
    finally:
        con.close()


def test_crs_02_swapped_lon_lat_is_detectably_wrong() -> None:
    to_2180 = Transformer.from_crs("EPSG:4326", "EPSG:2180", always_xy=True)
    to_wgs84 = Transformer.from_crs("EPSG:2180", "EPSG:4326", always_xy=True)
    x, y = to_2180.transform(19.94, 50.06)
    lon1, lat1 = to_wgs84.transform(x, y)
    lon2, lat2 = to_wgs84.transform(x + 100, y)

    con = connect()
    try:
        correct = point_distance_m(con, lon1, lat1, lon2, lat2)
        swapped = point_distance_m(con, lat1, lon1, lat2, lon2)
    finally:
        con.close()
    assert correct == pytest.approx(100, abs=0.01)
    assert abs(swapped - correct) > 1


def test_tac_002_06_initial_bearing_matches_wgs84_geod() -> None:
    rng = random.Random(3302)
    geod = Geod(ellps="WGS84")
    for _ in range(20):
        lon1 = rng.uniform(19.80, 20.15)
        lat1 = rng.uniform(49.95, 50.15)
        azimuth, _, _ = geod.fwd(lon1, lat1, rng.uniform(0, 360), 10)
        lon2, lat2, _ = geod.fwd(lon1, lat1, azimuth, 10)
        expected, _, _ = geod.inv(lon1, lat1, lon2, lat2)
        actual = initial_bearing(lon1, lat1, lon2, lat2)
        assert abs((actual - expected + 180) % 360 - 180) <= 0.1


def test_tac_002_01_distance_sql_rejects_non_metric_column() -> None:
    with pytest.raises(ValueError):
        distance_sql("geom", "x_2180")
