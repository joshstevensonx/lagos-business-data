from lagosdata.sources.base import SourceUnavailable
from lagosdata.sources.osm import OsmSource, build_query, label_of
from lagosdata.stages.discover import discover


def test_query_has_bbox_and_out_center():
    q = build_query((6.52, 3.33, 6.60, 3.41), 'magazine')
    assert '(6.52,3.33,6.6,3.41)' in q and 'out center tags;' in q and 'node["shop"]' in q


def test_label_of():
    assert label_of({'amenity': 'fast_food'}) == 'fast food'
    assert label_of({'office': 'yes'}) == 'office'
    assert label_of({}) == ''


def test_mapping(magazine_run, overpass_fixture):
    src = OsmSource(magazine_run, transport=lambda q: overpass_fixture)
    [plan] = src.plan()
    rows = src.search(plan)
    assert len(rows) == len(overpass_fixture['elements'])
    bs = [src.to_business(r) for r in rows]
    assert sum(b is None for b in bs) == 1                      # the nameless kiosk
    bs = [b for b in bs if b]
    by = {b.name: b for b in bs}
    assert by['Test Fixture Supermarket Anthony'].phone == '+2348031234567'
    assert by['Fixture Gift Shop'].phone == ''                  # 9-digit mobile rejected
    assert by['Fixture Shawarma Spot'].notes.startswith('Opening hours (OSM)')
    assert by['Test Fixture Supermarket Anthony Ltd'].lat       # way -> center coordinates
    assert all(b.source.startswith('OpenStreetMap (') for b in bs)
    assert by['Fixture Pharmacy One'].maps.startswith('https://www.openstreetmap.org/node/')


def test_unreachable_overpass_is_not_fatal(magazine_run):
    def boom(q):
        raise SourceUnavailable('CONNECT tunnel failed, response 403')
    magazine_run.options['source_kwargs'] = {'osm': {'transport': boom}}
    summary = discover(magazine_run)
    assert summary['failed'] == 1 and summary['raw_rows'] == 0
    assert magazine_run.state.searches()[0]['status'] == 'error'
    assert 'gmaps_browser' in summary['sources_not_built']
