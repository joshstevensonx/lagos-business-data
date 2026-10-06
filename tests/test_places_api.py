import json

from lagosdata.enrichers import places_api as P
from lagosdata.record import Business

MAPS = 'https://www.google.com/maps/place/x/data=!4m7!3m6!1s0x1:0x2!8m2!3d6.5!4d3.3!16s%2Fg%2Fx!19sChIJIRCl-o2NOxARLIyWKs5YNO8?a=b'


def test_masks_are_explicit_and_sku_sized():
    assert all('*' not in m for m in P.FIELD_MASKS.values())
    assert 'nationalPhoneNumber' not in P.FIELD_MASKS['essentials']
    assert P.places_id(MAPS) == 'ChIJIRCl-o2NOxARLIyWKs5YNO8'


def test_budget_refuses_past_ceiling_and_persists(tmp_path):
    b = P.Budget(80, tmp_path / 'u.json')
    assert b.ceiling('enterprise') == 800
    b.data = {b.month: {'enterprise': 799}}
    assert b.take('enterprise') and not b.take('enterprise')
    assert json.loads((tmp_path / 'u.json').read_text())[b.month]['enterprise'] == 800
    assert P.Budget(80, tmp_path / 'u.json').remaining('enterprise') == 0


def test_off_by_default_and_no_key_means_no_calls(magazine_run, monkeypatch):
    class Boom:
        def get(*a, **k): raise AssertionError('no HTTP call allowed')
    recs = [Business(name='x', maps=MAPS)]
    assert P.enrich(magazine_run, recs, http=Boom()) == recs           # disabled in config
    magazine_run.cfg.sources.places_api.enabled = True
    monkeypatch.delenv('GOOGLE_PLACES_API_KEY', raising=False)
    monkeypatch.chdir(magazine_run.dir)
    assert P.enrich(magazine_run, recs, http=Boom()) == recs           # enabled but no key


def test_enrich_fills_fields_and_never_logs_key(magazine_run, monkeypatch, tmp_path):
    magazine_run.cfg.sources.places_api.enabled = True
    magazine_run.cfg.sources.places_api.skus = ['enterprise']
    monkeypatch.setenv('GOOGLE_PLACES_API_KEY', 'SECRET-KEY-123')
    seen = {}

    class Resp:
        status_code = 200
        def json(self): return {'internationalPhoneNumber': '+234 803 123 4567', 'userRatingCount': 412, 'rating': 4.4}

    class Http:
        def get(self, url, timeout, headers):
            seen.update(headers); return Resp()
    b = Business(name='x', maps=MAPS)
    P.enrich(magazine_run, [b], http=Http(), budget=P.Budget(80, tmp_path / 'u.json'))
    assert b.phone == '+2348031234567' and b.reviews == 412 and b.rating == 4.4
    assert seen['X-Goog-FieldMask'] == P.FIELD_MASKS['enterprise']
    assert 'SECRET-KEY-123' not in (magazine_run.dir / 'run.log').read_text()
