"""Recorded directory pages: a selector break must fail here, not silently empty a run."""
from pathlib import Path

import pytest

from lagosdata.sources.base import Search
from lagosdata.sources.directories import (DirectoriesSource, ParserBroken, finelib_category_links, finelib_slugs,
                                           parse_businesslist, parse_finelib)

FIX = Path(__file__).parent / 'fixtures'
AREA = 'https://www.finelib.com/cities/lagos/areas-and-suburbs/anthony-village'


def test_finelib_listing_page():
    rows = parse_finelib((FIX / 'finelib-2026-10-06.html').read_text(), AREA + '/health-services')
    assert len(rows) == 8, 'finelib selector break - check FL_* in directories.py'
    r = next(x for x in rows if x['name'] == 'Biologix Support Services')
    assert 'Anthony Village' in r['addr'] and r['phone'].startswith('0805') and r['listing_id'] == '103205'
    assert r['category'] == 'health services'


def test_finelib_area_page_category_tree():
    links = finelib_category_links((FIX / 'finelib-area-2026-10-06.html').read_text(), AREA)
    assert len(links) >= 10 and all(u.startswith(AREA + '/') for u in links)


def test_finelib_slugs():
    assert finelib_slugs('Anthony / Anthony Village', []) == ['anthony', 'anthony-village']


def test_businesslist_pages():
    p1 = parse_businesslist((FIX / 'businesslist-2026-10-06.html').read_text(), 'p1')
    p2 = parse_businesslist((FIX / 'businesslist-p2-2026-10-06.html').read_text(), 'p2')
    assert len(p1) == 20 and len(p2) == 20, 'businesslist selector break - check BL_* in directories.py'
    assert sum(1 for r in p2 if r['lat']) >= 15 and all(r['name'] for r in p2)


def test_zero_parse_on_a_listing_page_raises(magazine_run):
    src = DirectoriesSource(magazine_run, fetch=lambda u: '<div class="company"><div class="company_header">'
                                                          '<h4>markup changed</h4></div></div>')
    with pytest.raises(ParserBroken):
        src.search(Search('businesslist', 'lagos page 2'))


def test_finelib_crawl_and_mapping(magazine_run):
    pages = {AREA.replace('anthony-village', 'anthony'): None,
             AREA: (FIX / 'finelib-area-2026-10-06.html').read_text()}
    listing = (FIX / 'finelib-2026-10-06.html').read_text()
    src = DirectoriesSource(magazine_run, fetch=lambda u: pages.get(u, listing if u.startswith(AREA) else None))
    rows = src.search(Search('finelib', 'Anthony / Anthony Village'))
    assert len(rows) == 8                          # same listings on every category page: deduped by listing id
    b = src.to_business(rows[1])
    assert b.source.startswith('Finelib (') and b.phone == '+2348053072221' and b.phones_all.count(';') == 2
    assert b.lat == '' and b.verification == ''    # no coordinates: geo falls back to the area named in the address


def test_businesslist_tagline_and_directory_classification(magazine_run):
    from lagosdata.classify import classify
    p2 = parse_businesslist((FIX / 'businesslist-p2-2026-10-06.html').read_text(), 'p2')
    assert sum(1 for r in p2 if r['desc']) >= 10
    from lagosdata.stages.classify import classify as classify_stage
    src = DirectoriesSource(magazine_run)
    rows = [{**r, '_site': 'businesslist', '_fetched': '2026-10-06'} for r in p2]
    bs = [src.to_business(r) for r in rows]
    for b in bs:
        b.area = 'Outside catchment'
    magazine_run.write_stage('geo', bs)
    classify_stage(magazine_run)
    out = magazine_run.read_stage('classify')
    with_label_only = sum(1 for b in bs if classify(b.label, b.name)[1] != 'Unclassified (needs review)')
    assert sum(1 for b in out if b.sub != 'Unclassified (needs review)') > with_label_only


def test_recrawled_listing_supersedes_old_raw_row(magazine_run):
    from lagosdata.stages.geo import geo
    magazine_run.append_raw('directories', [
        {'name': 'Old Name Ltd', 'listing_id': '9', '_site': 'businesslist', '_fetched': '2026-10-06', 'addr': 'Yaba'},
        {'name': 'New Name Ltd', 'listing_id': '9', '_site': 'businesslist', '_fetched': '2026-10-06', 'addr': 'Yaba',
         'desc': 'Phone repairs'}])
    geo(magazine_run)
    names = [b.name for b in magazine_run.read_stage('geo')]
    assert names == ['New Name Ltd']
