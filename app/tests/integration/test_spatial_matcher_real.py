"""Small seeded real-data smoke check; full agreement belongs to T36."""
import random

from mapqa.config.schema import FilesSource
from mapqa.contract.db import connect
from mapqa.matching.spatial import SpatialMatcher
from mapqa.sources.files import FilesAdapter


def test_twenty_real_photos_agreement(data_dir):
    bundle = FilesAdapter("files", FilesSource(type="files", path=str(data_dir))).load_photos(None)
    sample = random.Random(34).sample(sorted(bundle.photos, key=lambda p: p.photo_id), 20)
    provided = {link.photo_id: link.osm_way_id for link in bundle.links}
    con = connect()
    try:
        actual = SpatialMatcher(con, data_dir).match(sample)
    finally:
        con.close()
    agreed = sum(actual[p.photo_id].osm_way_id == provided[p.photo_id] for p in sample)
    print(f'Agreement: {agreed}/20 = {agreed/20:.0%}')
    assert len(actual) == 20
    assert agreed >= 18

