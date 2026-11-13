"""CRS-safe metric and bearing helpers (ADR-002 §3.1)."""

from __future__ import annotations

import math


def distance_sql(a_col: str, b_col: str) -> str:
    """Build metric distance SQL only for columns projected to EPSG:2180."""
    if not a_col.endswith("_2180") or not b_col.endswith("_2180"):
        raise ValueError("distance columns must use the _2180 suffix")
    return f"ST_Distance({a_col}, {b_col})"


def to_2180_sql(expr: str) -> str:
    """Transform an EPSG:4326 geometry expression to metric EPSG:2180."""
    return f"ST_Transform({expr}, 'EPSG:4326', 'EPSG:2180', always_xy := true)"


def initial_bearing(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Return spherical initial bearing clockwise from true north in [0, 360)."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_lon = math.radians(lon2 - lon1)
    y = math.sin(delta_lon) * math.cos(phi2)
    x = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(delta_lon)
    return math.degrees(math.atan2(y, x)) % 360.0


def point_distance_m(con, lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Transform two lon/lat points in DuckDB, then measure distance in meters."""
    first = to_2180_sql(f"ST_Point({float(lon1)!r}, {float(lat1)!r})")
    second = to_2180_sql(f"ST_Point({float(lon2)!r}, {float(lat2)!r})")
    # The computed expressions aren't columns; apply the same guarded helper contract
    # by naming their projected results in a SELECT scope.
    query = (
        f"SELECT {distance_sql('a.geom_2180', 'b.geom_2180')} FROM "
        f"(SELECT {first} AS geom_2180) a CROSS JOIN (SELECT {second} AS geom_2180) b"
    )
    return float(con.execute(query).fetchone()[0])
