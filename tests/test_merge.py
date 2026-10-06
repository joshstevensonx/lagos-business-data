from lagosdata.merge import MULTI, assign_priority, dedupe, drop_pois
from lagosdata.record import Business


def B(**kw):
    kw.setdefault('source', 'Google Maps (sweep, Oct 2026)')
    return Business(**kw)


def test_phone_key_merges_and_fills_empty_fields():
    a = B(name='Fixture Foods', phone='+2348031234567', addr='1 A Road')
    b = B(name='Fixture Foods Kitchen', phone='+2348031234567', website='https://x.example',
          source='OpenStreetMap (Oct 2026)')
    kept, dec = dedupe([a, b])
    assert len(kept) == 1
    assert kept[0].website == 'https://x.example'
    assert kept[0].source == MULTI
    assert dec[0]['key'] == 'p'


def test_place_id_beats_everything():
    a = B(name='Alpha', place_id='0x1:0x2', phone='+2348031234567')
    b = B(name='Totally Different', place_id='0x1:0x2', phone='+2348059876543')
    kept, dec = dedupe([a, b])
    assert len(kept) == 1 and dec[0]['key'] == 'pid'


def test_name_address_then_name_only():
    a = B(name='Fixture Salon Ltd', addr='5 Fixture Road, Anthony')
    b = B(name='Fixture Salon', addr='5 Fixture Rd, Anthony')
    kept, dec = dedupe([a, b])
    assert len(kept) == 1 and dec[0]['key'] == 'na'
    c = B(name='Fixture Salon', addr='somewhere else entirely')
    kept, dec = dedupe([a, c])
    assert len(kept) == 1 and dec[0]['key'] == 'n'


def test_distinct_businesses_survive():
    kept, _ = dedupe([B(name='One'), B(name='Two'), B(name='Three')])
    assert len(kept) == 3


def test_conflict_prefers_trusted_source_and_records_loser():
    osm = B(name='Fixture Mart', phone='', website='https://old.example', source='OpenStreetMap (Oct 2026)')
    gm = B(name='Fixture Mart', website='https://new.example', source='Google Maps (sweep, Oct 2026)')
    kept, _ = dedupe([osm, gm])
    r = kept[0]
    assert r.website == 'https://new.example'
    assert r.conflicts == [{'field': 'website', 'kept': 'https://new.example', 'dropped': 'https://old.example',
                            'dropped_source': 'OpenStreetMap (Oct 2026)'}]
    # and the reverse order keeps the trusted value too
    osm2 = B(name='Fixture Mart', website='https://old.example', source='OpenStreetMap (Oct 2026)')
    gm2 = B(name='Fixture Mart', website='https://new.example', source='Google Maps (sweep, Oct 2026)')
    kept, _ = dedupe([gm2, osm2])
    assert kept[0].website == 'https://new.example' and kept[0].conflicts[0]['dropped'] == 'https://old.example'


def test_poi_drop_is_reported():
    kept, dropped = drop_pois([B(name='Anthony Bus Stop'), B(name='Bus Stop Pharmacy', label='Pharmacy')])
    assert [k.name for k in kept] == ['Bus Stop Pharmacy']
    assert dropped[0]['reason']


def test_priority_rules():
    core = ['Anthony / Anthony Village']
    a = B(name='x', phone='+2348031234567', area=core[0], reviews=12)
    assign_priority(a, core)
    assert a.priority.startswith('A') and a.package == 'Premium' and a.verification == 'Google-verified'
    b = B(name='y', phone='+2348031234567', area='Gbagada', reviews=30)
    assign_priority(b, core)
    assert b.priority.startswith('B')
    c = B(name='z', phone='+2348031234567', area='Gbagada')
    assign_priority(c, core)
    assert c.priority.startswith('C')
    d = B(name='w', area=core[0], lat=6.5, lng=3.3, source='OpenStreetMap (Oct 2026)')
    assign_priority(d, core)
    assert d.priority.startswith('D') and d.contactable == 'No'
    assert d.verification == 'Mapped location (OSM)'   # OSM coordinates are not Google verification


def test_different_place_ids_are_never_fused_by_name():
    a = B(name='Nett Pharmacy', place_id='0x1:0xa', addr='350/360 Ikorodu Rd')
    b = B(name='Nett Pharmacy', place_id='0x1:0xb', addr='Opic Plz, Mobolaji Bank Anthony Way')
    kept, dec = dedupe([a, b])
    assert len(kept) == 2 and dec == []
    # a record without a place id still merges by name into the first branch
    c = B(name='Nett Pharmacy', source='OpenStreetMap (Oct 2026)', phone='+2348031234567')
    kept, dec = dedupe([a, b, c])
    assert len(kept) == 2 and kept[0].phone == '+2348031234567'


def test_merge_inherits_classification_when_kept_record_is_unclassified():
    a = B(name='Fixture Hub', phone='+2348031234567', source='BusinessList.com.ng (Oct 2026)')
    a.group, a.sub = 'Other Local Services', 'Unclassified (needs review)'
    b = B(name='Fixture Hub', phone='+2348031234567')
    b.group, b.sub = 'Phones & Technology', 'Phone Shops'
    kept, _ = dedupe([a, b])
    assert (kept[0].group, kept[0].sub) == ('Phones & Technology', 'Phone Shops')
