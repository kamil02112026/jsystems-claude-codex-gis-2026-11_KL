"""ADR-002 matching acceptance cases, with metric synthetic geometry near Kraków."""
from dataclasses import replace

import pytest
from pyproj import Transformer, Geod

from mapqa.contract.bundle import PhotoRecord
from mapqa.contract.db import connect, sql_path
from mapqa.matching.spatial import SpatialMatcher, _compare_candidates

FORWARD = Transformer.from_crs(4326, 2180, always_xy=True)
BACK = Transformer.from_crs(2180, 4326, always_xy=True)
X, Y = FORWARD.transform(19.94, 50.06)


def photo(x=0, y=0, heading=0.0, **kwargs):
    lon, lat = BACK.transform(X+x, Y+y)
    return PhotoRecord(photo_id='p', source='test', filename='', longitude=lon,
        latitude=lat, heading=heading, captured_at='', sequence='', author='',
        license='', license_url='', source_url='', sha256='', is_panorama=False,
        horizontal_accuracy_m=None, image_path=None, image_status='missing_file', **kwargs)


def wkt(points):
    coords = [BACK.transform(X+x, Y+y) for x,y in points]
    return 'LINESTRING (' + ','.join(f'{x} {y}' for x,y in coords) + ')'


@pytest.fixture
def scene(tmp_path):
    con = connect()
    con.execute('''CREATE TABLE roads (osm_id BIGINT, geometry GEOMETRY('EPSG:4326'),
        node_ids BIGINT[], highway VARCHAR, oneway VARCHAR, boundary_crossing BOOLEAN,
        bridge VARCHAR, tunnel VARCHAR, layer VARCHAR, access VARCHAR, motor_vehicle VARCHAR)''')
    con.execute('''CREATE TABLE segments (id VARCHAR, geometry GEOMETRY('EPSG:4326'),
        sources STRUCT(record_id VARCHAR)[], level_rules STRUCT(value INTEGER)[])''')

    def road(oid=1, points=((-100,0),(100,0)), nodes=(1,2), **tags):
        values = dict(highway='residential', oneway='no', boundary_crossing=False,
                      bridge='no', tunnel='no', layer='0', access=None, motor_vehicle=None)
        values.update(tags)
        con.execute('INSERT INTO roads VALUES (?, ST_GeomFromText(?), ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    [oid, wkt(points), list(nodes), *values.values()])

    def overture(sid='s', points=((-100,1),(100,1)), refs=(), levels=()):
        con.execute('INSERT INTO segments VALUES (?, ST_GeomFromText(?), ?, ?)',
                    [sid, wkt(points), [{'record_id': r} for r in refs], [{'value': v} for v in levels]])

    def matcher():
        # Build fixtures in memory, then exercise the actual GeoParquet reader.
        con.execute(f'COPY roads TO {sql_path(tmp_path / "osm_roads.parquet")} (FORMAT PARQUET)')
        con.execute(f'COPY segments TO {sql_path(tmp_path / "overture_segments.parquet")} (FORMAT PARQUET)')
        return SpatialMatcher(con, tmp_path)

    yield road, overture, matcher
    con.close()


@pytest.mark.parametrize('heading', [270, 90, 89, 271])
def test_mat01_bidirectional_and_geod_oracle(scene, heading):
    road, _, build = scene
    road(oneway='yes')
    result = build().match([photo(heading=heading)])['p']
    a,b = BACK.transform(X-5,Y), BACK.transform(X+5,Y)
    azimuth = Geod(ellps='WGS84').inv(*a,*b)[0] % 360
    directed = abs((heading-azimuth+180)%360-180)
    assert result.heading_diff_deg == pytest.approx(min(directed,180-directed), abs=.1)
    assert ('camera_against_way_direction' in result.flags) == (directed > 90)
    assert result.link_source == 'own'


@pytest.mark.parametrize('heading', [0.0, 360.0, None])
def test_hdg01_hdg02_tac04_null_is_not_north(scene, heading):
    road, _, build = scene
    road(points=((0,-100),(0,100)))
    p = photo(heading=heading)
    before = p.heading
    result = build().match([p])['p']
    assert p.heading == before
    assert ('missing_heading' in result.flags) == (heading is None)
    assert result.heading_diff_deg is None if heading is None else result.heading_diff_deg < 1


def test_mat02_id_tie_and_tac05_determinism(scene):
    road, _, build = scene
    for oid in [30,10,20]:
        road(oid)
    matcher = build()
    photos = [photo(heading=None), replace(photo(heading=90), photo_id='a')]
    first = matcher.match(photos)
    assert first == matcher.match(list(reversed(photos)))
    assert list(first) == ['a','p']
    assert first['p'].osm_way_id == 10
    assert first['p'].candidate_count == 3
    assert 'ambiguous_candidates' in first['p'].flags


def test_ranking_heading_penalty_and_ambiguity(scene):
    road, _, build = scene
    road(1, points=((-100,1),(100,1)))
    road(2, points=((5,-100),(5,100)))
    matcher = build()
    assert matcher.match([photo()])['p'].osm_way_id == 2  # 5 < 1 + ~90/9
    missing = matcher.match([photo(heading=None)])['p']
    assert missing.osm_way_id == 1  # same +5 penalty for both
    assert 'ambiguous_candidates' not in missing.flags
    for candidate in matcher._candidates(photo(heading=None)):
        assert candidate['rank'] == pytest.approx(candidate['distance_2180'] + 5)
        assert candidate['diff'] is None
    assert 'poor_heading_alignment' in matcher.match([photo(heading=90)])['p'].flags or matcher.match([photo(heading=90)])['p'].heading_diff_deg < 1


@pytest.mark.parametrize('offset,matched', [(24.999999,True),(25.1,False)])
def test_mat03_radius(scene, offset, matched):
    road, _, build = scene
    road(points=((-100,offset),(100,offset)))
    result = build().match([photo(heading=None)])['p']
    assert (result.osm_way_id is not None) == matched
    assert ('no_osm_within_25m' in result.flags) == (not matched)
    assert result.candidate_count == int(matched)
    if matched:
        assert result.distance_m == pytest.approx(offset, abs=.001)
    else:
        assert result.distance_m is None


@pytest.mark.parametrize('offset,expected', [(10,True),(15.1,False)])
def test_mat04_junction_uses_projection_and_shared_internal_node(scene, offset, expected):
    road, _, build = scene
    road(1, points=((-100,0),(offset,0),(100,0)), nodes=(1,99,2))
    road(2, points=((offset,0),(offset,100)), nodes=(99,3))
    road(3, points=((offset,0),(offset,-100)), nodes=(99,4))
    result = build().match([photo(y=-16,heading=90)])['p']
    assert result.osm_way_id == 1
    assert ('junction_nearby' in result.flags) == expected


@pytest.mark.parametrize('tags,expected', [
    ({'highway':'service'}, {'service_way','service_or_restricted'}),
    ({'highway':'track'}, {'service_way'}),
    ({'access':'private'}, {'service_or_restricted'}),
    ({'motor_vehicle':'destination'}, {'service_or_restricted'}),
    ({'bridge':'yes'}, {'grade_separated'}), ({'tunnel':'yes'}, {'grade_separated'}),
    ({'layer':'1'}, {'grade_separated'}), ({'layer':'0','bridge':'no'}, set()),
    ({'boundary_crossing':True}, {'boundary_crossing'}),
])
def test_mat05_mat09_tag_flags(scene, tags, expected):
    road, _, build = scene
    road(**tags)
    result = build().match([photo(heading=90)])['p']
    assert set(result.flags) == expected


@pytest.mark.parametrize('reference_distance,expected', [(20,'ref'),(26,'near')])
def test_mat06_overture_reference_before_nearest_and_radius(scene, reference_distance, expected):
    road, overture, build = scene
    road(123)
    overture('near', refs=('w1234@4',))  # substring must not match w123
    overture('ref', points=((-100,reference_distance),(100,reference_distance)), refs=('w123@4',))
    result = build().match([photo(heading=90)])['p']
    assert result.overture_id == expected
    assert ('overture_spatial_only' in result.flags) == (expected=='near')


def test_overture_levels_and_deterministic_tie(scene):
    road, overture, build = scene
    road()
    overture('z', refs=('w1@1',), levels=(1,))
    overture('a', refs=('w1@2',), levels=(1,))
    result = build().match([photo(heading=90)])['p']
    assert result.overture_id == 'a'
    assert 'grade_separated' in result.flags


def test_no_osm_still_matches_overture_and_keeps_photo_flags(scene):
    _, overture, build = scene
    overture()
    result = build().match([replace(photo(heading=None), is_panorama=True)])['p']
    assert result.overture_id == 's'
    assert set(result.flags) == {'no_osm_within_25m','missing_heading','panorama_heading_ambiguous','overture_spatial_only'}


def test_local_tangent_at_bend_not_endpoint_bearing(scene):
    road, _, build = scene
    road(points=((-100,0),(0,0),(0,100)), nodes=(1,2,3))
    result = build().match([photo(y=50)])['p']
    assert result.heading_diff_deg < 1
    assert 'poor_heading_alignment' not in result.flags


def test_poor_alignment_panorama_and_empty_input(scene):
    road, _, build = scene
    road(oneway='yes')
    matcher = build()
    result = matcher.match([replace(photo(heading=45), is_panorama=True)])['p']
    assert set(result.flags) == {'poor_heading_alignment','panorama_heading_ambiguous'}
    assert matcher.match([]) == {}


@pytest.mark.parametrize('delta,expected', [(0,-1),(0.5e-9,-1),(2e-9,1)])
def test_mat02_rank_tolerance_then_smaller_distance(delta, expected):
    nearer = {'rank': 7 + delta, 'distance_2180': 2, 'osm_id': 20}
    farther = {'rank': 7, 'distance_2180': 3, 'osm_id': 10}
    assert _compare_candidates(nearer, farther) == expected
    assert _compare_candidates(farther, nearer) == -expected


@pytest.mark.parametrize('gap,expected', [(1.999,True),(2.001,False)])
def test_ambiguity_margin_is_two_meters_of_rank(scene, gap, expected):
    road, _, build = scene
    road(1, points=((-100,1),(100,1)))
    road(2, points=((-100,1+gap),(100,1+gap)))
    result = build().match([photo(heading=None)])['p']
    assert result.osm_way_id == 1
    assert ('ambiguous_candidates' in result.flags) == expected


@pytest.mark.parametrize('y', [-101, 101])
def test_tangent_is_clipped_at_line_endpoints(scene, y):
    road, _, build = scene
    road(points=((0,-100),(0,100)))
    result = build().match([photo(y=y)])['p']
    assert result.osm_way_id == 1
    assert result.distance_m == pytest.approx(1, abs=.001)
    assert result.heading_diff_deg < 1


def test_mat03_exactly_25_meters_is_inclusive(scene):
    road, _, build = scene
    road()
    matcher = build()
    p = photo(heading=None)
    # Set the metric fixture directly: a 4326 round trip adds sub-nanometer noise.
    matcher.con.execute(f'''WITH point AS (
        SELECT ST_Transform(ST_Point(?, ?), 'EPSG:4326', 'EPSG:2180',
            always_xy := true) AS geom_2180)
        UPDATE {matcher.roads} SET geom_2180 = ST_MakeLine(
            ST_Point(ST_X(point.geom_2180)-100, ST_Y(point.geom_2180)+25),
            ST_Point(ST_X(point.geom_2180)+100, ST_Y(point.geom_2180)+25))
        FROM point''', [p.longitude, p.latitude])
    result = matcher.match([p])['p']
    assert result.osm_way_id == 1
    assert result.distance_m == 25



