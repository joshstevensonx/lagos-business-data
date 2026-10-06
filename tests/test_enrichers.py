from lagosdata.enrichers import place_pages as PP
from lagosdata.enrichers import site_contacts as SC
from lagosdata import score as S
from lagosdata.record import Business

HTML = '''<html><body>
<a href="mailto:orders@fixture-foods.example?subject=hi">Email</a> info@fixture-foods.example
noreply@fixture-foods.example logo@2x.png
<a href="https://www.instagram.com/fixturefoods/">IG</a> <a href="https://instagram.com/p/abc123">post</a>
<a href="https://www.facebook.com/FixtureFoodsNG">FB</a> <a href="https://www.facebook.com/sharer/sharer.php?u=x">share</a>
<a href="https://twitter.com/fixturefoods">X</a> <a href="https://www.tiktok.com/@fixturefoods">tt</a>
<a href="https://wa.me/2348031234567">WhatsApp us</a> <a href="tel:+234 805 987 6543">call</a>
<p>We deliver across Lagos. Catering for events and bulk order discounts. Order online now!</p>
<script>var x = "delivery in script must not count";</script>
</body></html>'''


def test_extract_contacts_and_signals():
    x = SC.extract(HTML)
    assert x['emails'] == ['orders@fixture-foods.example', 'info@fixture-foods.example']
    assert x['instagram'] == ['https://www.instagram.com/fixturefoods']
    assert x['facebook'] == ['https://www.facebook.com/FixtureFoodsNG']
    assert x['twitter'] == ['https://x.com/fixturefoods'] and x['tiktok'] == ['https://www.tiktok.com/@fixturefoods']
    assert x['whatsapp'] == ['+2348031234567']
    assert '+2348059876543' in x['phones']
    assert set(x['delivery']) >= {'we deliver', 'catering', 'bulk order'}
    assert x['order_online']


def test_social_website_is_read_not_fetched():
    x = SC.crawl_site(fetcher=None, website='https://instagram.com/teeignite_auto')
    assert x['instagram'] == ['https://www.instagram.com/teeignite_auto']


def test_apply_never_reuses_another_records_phone():
    b = Business(name='Branch 2')
    found = SC.extract(HTML)
    SC.apply(b, found, used_phones={'+2348059876543'})       # head-office number already on branch 1
    assert b.phone == '' and '+2348059876543' in b.phones_all
    assert b.whatsapp == '+2348031234567' and b.email.startswith('orders@')
    assert 'catering' in b.delivery_text_signals and 'online ordering' in b.delivery_text_signals
    total, c, _ = S.score(S.apify_view(b), {})
    assert c['Catering offered'] == 15 and c['Online ordering / menu'] == 7


def test_place_page_parse_and_nested_shape():
    info = {'h1': 'X', 'items': {
        'address': {'label': 'Address: 350, Maryland mall, 360 Ikorodu Rd, Anthony, Ikeja ', 'href': ''},
        'action:4': {'label': '', 'href': 'https://glovoapp.com/ng/en/x'},
        'phone:tel:+2348131867091': {'label': 'Phone', 'href': ''},
        'authority': {'label': 'Website', 'href': 'http://x.example/'}}}
    p = PP.parse_place(info, ['Offers delivery', 'Offers takeout', 'Serves dine-in', 'Has wheelchair access'])
    assert p['phone'] == '+2348131867091' and p['order_url'].startswith('https://glovoapp')
    assert p['attrs'] == {'Service options': {'Delivery': True, 'Takeout': True, 'Dine-in': True}}
    b = Business(name='X', addr='360 Ikorodu Rd', maps='https://www.google.com/maps/place/x')
    PP.apply(b, p, set())
    assert b.additional_info['Service options'] == [{'Delivery': True}, {'Takeout': True}, {'Dine-in': True}]
    assert b.score_basis == S.BASIS_FULL and 'Anthony' in b.addr
    total, c, _ = S.score(S.apify_view(b), {})
    assert c['Google Delivery flag'] == 25 and c['Takeout'] == 5 and c['Online ordering / menu'] == 7


def test_order_link_alone_is_not_the_google_delivery_flag():
    p = PP.parse_place({'items': {'action:4': {'href': 'https://chowdeck.example/x', 'label': ''}}}, [])
    b = Business(name='Y', maps='https://www.google.com/maps/place/y')
    PP.apply(b, p, set())
    total, c, _ = S.score(S.apify_view(b), {})
    assert c['Google Delivery flag'] == 0 and c['Online ordering / menu'] == 7


def test_place_page_results_persist_across_rebuilds(magazine_run, monkeypatch):
    magazine_run.cfg.enrich.place_pages.enabled = True
    maps = 'https://www.google.com/maps/place/x/data=!4m7!3m6!1s0x10:0xab!8m2!3d6.5!4d3.3'
    calls = []

    async def fake_visit(run, targets, exe, conc, delay):
        calls.append(len(targets))
        return {id(b): PP.parse_place({'items': {'action:4': {'href': 'https://glovo.example', 'label': ''}}}, [])
                for b in targets}
    monkeypatch.setattr(PP, '_visit_all', fake_visit)
    recs = PP.enrich(magazine_run, [Business(name='A', label='Restaurant', area='Yaba', maps=maps, reviews=50)])
    assert recs[0].score_basis == S.BASIS_FULL
    again = PP.enrich(magazine_run, [Business(name='A', label='Restaurant', area='Yaba', maps=maps, reviews=50)])
    assert again[0].score_basis == S.BASIS_FULL and calls == [1]                   # applied from cache, no visit
