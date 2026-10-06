"""Google Maps source - against recorded and synthetic pages, never live."""
import json
from pathlib import Path

import pytest

from lagosdata.sources.base import Search, SourceAborted
from lagosdata.sources.gmaps_browser import GmapsBrowserSource, parse_card
from lagosdata.stages.discover import Recorder

from .conftest import requires_playwright

FIX = Path(__file__).parent / 'fixtures'
FAST = {'delay': (0, 0), 'pause_ms': 400, 'backoff_base': 0.01}


def src_for(run, page, **timing):
    return GmapsBrowserSource(run, url_for=lambda s: (FIX / page).as_uri(), timing={**FAST, **timing})


def test_parse_card_live_shape():
    raw = {'aria': 'Medplus Pharmacy Ogudu',
           'href': 'https://www.google.com/maps/place/x/data=!4m7!3m6!1s0x103b8d404baa79c5:0xfae86733a56b4a1b'
                   '!8m2!3d6.547964!4d3.4007149!16s',
           'stars': '4.3 stars', 'website': 'https://medplus.example/',
           'leaves': ['Medplus Pharmacy Ogudu', 'Medplus Pharmacy Ogudu', '4.3', 'Pharmacy', '·', '45A Ogudu Rd',
                      'Open 24 hours', '·', '+234 908 335 4474', '', 'Website', '', 'Directions']}
    f = parse_card(raw)
    assert (f['name'], f['label'], f['addr'], f['phone']) == ('Medplus Pharmacy Ogudu', 'Pharmacy', '45A Ogudu Rd',
                                                              '+234 908 335 4474')
    assert f['rating'] == 4.3 and f['reviews'] == ''           # the feed no longer shows review counts
    assert (f['lat'], f['lng']) == (6.547964, 3.4007149)
    assert f['place_id'] == '0x103b8d404baa79c5:0xfae86733a56b4a1b'
    assert f['website'] == 'https://medplus.example/'


def test_parse_card_old_shape_and_empty_address():
    f = parse_card({'aria': 'X', 'href': '', 'stars': '4.1 stars 1,234 Reviews',
                    'leaves': ['X', 'Pharmacy', '·', '', '·', '4, Diya street Ifako', 'Open', '· Closes 10 PM']})
    assert f['reviews'] == 1234 and f['label'] == 'Pharmacy' and f['addr'] == '4, Diya street Ifako'
    assert parse_card({'aria': 'Y', 'leaves': ['Y', '4.0(12)', '₦₦']})['label'] == ''   # reference sweep filter


def test_plan_uses_sweeps(magazine_run):
    src = GmapsBrowserSource(magazine_run)
    plan = src.plan()
    assert len(plan) == 321                                   # one wide viewport covers all seven areas
    assert src._maps_url(plan[0]) == 'https://www.google.com/maps/search/provision%20store/@6.5613,3.3721,14z?hl=en'


@requires_playwright
def test_recorded_feed_extracts_every_card(magazine_run):
    rows = src_for(magazine_run, 'gmaps-feed-pharmacy-2026-10-06.html').search(Search('pharmacy', 'sweep 1,1,14z'))
    assert len(rows) == 120, 'selector break: the recorded feed has 120 result cards'
    bs = [b for b in (GmapsBrowserSource(magazine_run).to_business(r) for r in rows) if b]
    assert len(bs) == 120
    assert all(b.place_id and b.lat and b.maps for b in bs)
    assert sum(1 for b in bs if b.label == 'Pharmacy') > 80
    assert sum(1 for b in bs if b.phone) > 60
    assert all(b.phone.startswith('+234') for b in bs if b.phone)
    assert sum(1 for b in bs if b.website) > 5


@requires_playwright
def test_render_wait_beats_a_naive_read(magazine_run):
    """The bug that returned 1 pharmacy where 118 existed: the feed renders late and grows on scroll."""
    rows = src_for(magazine_run, 'gmaps-lazy-synthetic.html').search(Search('pharmacy', 'sweep 1,1,14z'))
    assert len(rows) == 40
    naive = src_for(magazine_run, 'gmaps-lazy-synthetic.html', wait_ms=0, cap_ms=0)
    assert len(naive.search(Search('pharmacy2', 'sweep 1,1,14z'))) < 40


@requires_playwright
def test_captcha_aborts_the_source_and_leaves_search_pending(magazine_run):
    src = src_for(magazine_run, 'gmaps-captcha-synthetic.html')
    summary = {'searched': 0, 'failed': 0, 'raw_rows': 0}
    s = Search('pharmacy', 'sweep 1,1,14z')
    with pytest.raises(SourceAborted, match='CAPTCHA'):
        src.search_many([s], Recorder(magazine_run, 'gmaps_browser', summary))
    assert not magazine_run.state.is_done('gmaps_browser', s.term, s.area)
    assert summary['raw_rows'] == 0


@requires_playwright
def test_empty_feed_on_a_term_that_worked_backs_off_then_stops_worker(magazine_run, tmp_path):
    empty = tmp_path / 'empty.html'
    empty.write_text('<html><body><div role="feed"></div></body></html>')
    src = GmapsBrowserSource(magazine_run, url_for=lambda s: empty.as_uri(),
                             timing={**FAST, 'wait_ms': 300, 'cap_ms': 600})
    src.best['pharmacy'] = 50                                 # it returned 50 in another viewport
    summary = {'searched': 0, 'failed': 0, 'raw_rows': 0}
    src.search_many([Search('pharmacy', 'sweep 1,1,14z')], Recorder(magazine_run, 'gmaps_browser', summary))
    log = [json.loads(line) for line in (magazine_run.dir / 'run.log').read_text().splitlines()]
    assert sum(1 for e in log if e['kind'] == 'backoff') == 2
    assert any(e['kind'] == 'worker_stopped' for e in log)
    assert not magazine_run.state.is_done('gmaps_browser', 'pharmacy', 'sweep 1,1,14z')


@requires_playwright
def test_max_searches_ceiling(magazine_run):
    magazine_run.options['max_searches'] = 1
    src = src_for(magazine_run, 'gmaps-lazy-synthetic.html')
    summary = {'searched': 0, 'failed': 0, 'raw_rows': 0}
    todo = [Search('a', 'sweep 1,1,14z'), Search('b', 'sweep 1,1,14z')]
    src.search_many(todo, Recorder(magazine_run, 'gmaps_browser', summary))
    assert summary['searched'] == 1


def test_split_viewport_quadrants():
    from lagosdata.sources.gmaps_browser import child_searches, split_viewport
    kids = split_viewport(6.566, 3.368, 15)
    assert len(kids) == 4 and all(z == 16 for _, _, z in kids)
    lats = sorted({k[0] for k in kids}); lngs = sorted({k[1] for k in kids})
    assert lats[0] < 6.566 < lats[1] and lngs[0] < 3.368 < lngs[1]
    assert child_searches(Search('x', 'sweep 6.5,3.3,17z')) == []         # recursion bottoms out


def test_saturated_searches_are_replanned_from_state(magazine_run):
    src = GmapsBrowserSource(magazine_run)
    st = magazine_run.state
    st.start('gmaps_browser', 'pharmacy', 'sweep 6.5600,3.3700,14z')
    st.finish('gmaps_browser', 'pharmacy', 'sweep 6.5600,3.3700,14z', 120)   # hit the feed cap
    st.start('gmaps_browser', 'church', 'sweep 6.5600,3.3700,14z')
    st.finish('gmaps_browser', 'church', 'sweep 6.5600,3.3700,14z', 37)      # complete, no split
    kids = src.saturation_plan()
    assert len(kids) == 4 and {k.term for k in kids} == {'pharmacy'} and all(k.area.endswith('15z') for k in kids)


@requires_playwright
def test_saturated_feed_enqueues_quadrants(magazine_run):
    magazine_run.options['max_searches'] = 3
    src = src_for(magazine_run, 'gmaps-feed-pharmacy-2026-10-06.html')
    summary = {'searched': 0, 'failed': 0, 'raw_rows': 0}
    src.search_many([Search('pharmacy', 'sweep 6.5600,3.3700,14z')], Recorder(magazine_run, 'gmaps_browser', summary))
    done = [r['area'] for r in magazine_run.state.searches() if r['status'] == 'done']
    assert len(done) == 3 and sum(a.endswith('15z') for a in done) == 2      # parent + 2 children within ceiling


def test_parse_card_no_reviews_and_icon_glyphs():
    f = parse_card({'aria': 'T-top beauty salon', 'href': '',
                    'leaves': ['T-top beauty salon', 'No reviews', 'Hair salon', '·', '59 Igbeyinadun St']})
    assert (f['label'], f['addr']) == ('Hair salon', '59 Igbeyinadun St')
    f = parse_card({'aria': 'J', 'leaves': ['J', '4.7', '(6)', 'Pharmacy', '·', '16 Ajayi Aina St', 'Open',
                                            '· Closes 9 PM', '·', '+234 904 999 4999', '']})
    assert f['reviews'] == 6 and f['addr'] == '16 Ajayi Aina St' and f['phone'] == '+234 904 999 4999'


def test_splits_skip_quadrants_outside_the_catchment():
    from lagosdata.sources.gmaps_browser import child_searches
    s = Search('x', 'sweep 6.5613,3.3721,15z')
    assert len(child_searches(s)) == 4
    ne_bbox = (6.570, 3.390, 6.580, 3.400)                   # only the north-east quadrant reaches it
    kids = child_searches(s, ne_bbox)
    assert [k.area for k in kids] == ['sweep 6.5695,3.3868,16z']
