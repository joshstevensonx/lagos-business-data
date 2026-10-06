import json

from lagosdata.areas import derive_centroids
from lagosdata.config import AreaDef
from lagosdata.pipeline import run_stages
from lagosdata.record import Business


def test_import_csv_goes_through_the_pipeline(magazine_run, tmp_path):
    f = tmp_path / 'walk.csv'
    f.write_text('Business Name,Phone,Address,Category,Notes\n'
                 'Mama Fixture Provisions,0803 555 1212,"3 Fixture St, Anthony Village",Provision store,met owner\n'
                 'Test Fixture Supermarket Anthony,08031234567,,Supermarket,\n'
                 ',,no name row,,\n')
    magazine_run.options['import_csv'] = [str(f)]
    run_stages(magazine_run, ['discover', 'geo', 'classify', 'dedupe', 'enrich', 'score'])
    by = {r['name']: r for r in json.loads(magazine_run.master_path.read_text())}
    mama = by['Mama Fixture Provisions']
    assert mama['area'] == 'Anthony / Anthony Village'          # no coordinates: address-name fallback
    assert mama['phone'] == '+2348035551212' and mama['notes'] == 'met owner'
    assert mama['verification'] == 'Directory listing only'
    # same phone as an OSM record: merged and marked cross-verified
    assert by['Test Fixture Supermarket Anthony']['source'] == 'Multiple sources (cross-verified)'
    # re-running is a no-op for an unchanged file
    n = len(magazine_run.read_raw('manual_csv'))
    run_stages(magazine_run, ['discover'])
    assert len(magazine_run.read_raw('manual_csv')) == n == 3


def test_derive_centroids_uses_median_and_flags_low_n():
    g = 'Google Maps (sweep, Oct 2026)'
    recs = [Business(name=f'b{i}', lat=6.50 + i * 0.001, lng=3.40, addr='x, Yaba, Lagos', source=g) for i in range(20)]
    recs.append(Business(name='outlier', lat=9.0, lng=7.0, addr='Yaba', source=g))          # median ignores it
    recs.append(Business(name='osm', lat=1.0, lng=1.0, addr='Yaba', source='OpenStreetMap (Oct 2026)'))
    recs += [Business(name=f's{i}', lat=6.49, lng=3.35, addr='Surulere', source=g) for i in range(3)]
    res = derive_centroids(recs, ['Yaba', 'Surulere', 'Ikoyi'], {'Yaba': AreaDef(), 'Surulere': AreaDef()})
    assert res['Yaba']['n'] == 21 and abs(res['Yaba']['lat'] - 6.510) < 0.0011 and res['Yaba']['lng'] == 3.40
    assert not res['Yaba']['low_confidence']
    assert res['Surulere']['n'] == 3 and res['Surulere']['low_confidence']
    assert res['Ikoyi']['n'] == 0
