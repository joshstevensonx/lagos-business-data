"""Google Places API (New) - OPTIONAL, free monthly allowance only, OFF by default (SPEC §3.1).

Billing must be enabled on the GCP project even to use the free tier, so this is
Josh's decision, never a default. Safeguards:
  * the field mask decides the SKU, so each SKU's mask is explicit and asserted
    (never '*', which would bill every call at the top tier)
  * a local usage counter (~/.lagosdata/places_usage.json, by YYYY-MM and SKU)
    refuses any call beyond monthly_ceiling_pct of the free allowance
  * the key comes from GOOGLE_PLACES_API_KEY (env or a gitignored .env) only;
    it is never read from config, never logged
Used only to fill phone / website / rating / review count on the highest-value
records (most reviews first), not for discovery.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from pathlib import Path

import requests

FREE_PER_MONTH = {'essentials': 10_000, 'pro': 5_000, 'enterprise': 1_000}   # confirmed Oct 2026; volatile
FIELD_MASKS = {
    'essentials': 'id,formattedAddress,location',
    'pro': 'id,formattedAddress,location,displayName,types',
    'enterprise': 'id,formattedAddress,location,nationalPhoneNumber,internationalPhoneNumber,websiteUri,'
                  'rating,userRatingCount',
}
for _sku, _mask in FIELD_MASKS.items():
    assert '*' not in _mask, 'a wildcard field mask bills every call at the top SKU'
ENDPOINT = 'https://places.googleapis.com/v1/places/{pid}'
# Kept in the repo (committed) by default, NOT in ~ - cloud containers and new sessions start with
# a fresh home directory, and a lost count is how the free tier gets overspent.
USAGE_FILE = Path(os.environ.get('LAGOSDATA_HOME', '.lagosdata')) / 'places_usage.json'


def api_key() -> str:
    key = os.environ.get('GOOGLE_PLACES_API_KEY', '')
    if not key and Path('.env').exists():
        for line in Path('.env').read_text().splitlines():
            if line.strip().startswith('GOOGLE_PLACES_API_KEY='):
                key = line.split('=', 1)[1].strip().strip('"\'')
    return key


class Budget:
    def __init__(self, ceiling_pct: int, path: Path = USAGE_FILE):
        self.path = path
        self.pct = ceiling_pct
        self.month = date.today().strftime('%Y-%m')
        self.data = json.loads(path.read_text()) if path.exists() else {}

    def used(self, sku) -> int:
        return self.data.get(self.month, {}).get(sku, 0)

    def ceiling(self, sku) -> int:
        return FREE_PER_MONTH[sku] * self.pct // 100

    def remaining(self, sku) -> int:
        return max(0, self.ceiling(sku) - self.used(sku))

    def take(self, sku) -> bool:
        if self.remaining(sku) <= 0:
            return False
        self.data.setdefault(self.month, {})[sku] = self.used(sku) + 1
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self.data, indent=1))     # persisted before the call is made
        return True


def places_id(maps_url: str) -> str:
    m = re.search(r'!19s(ChIJ[\w\-]+)', maps_url or '')
    return m.group(1) if m else ''


def candidates(run, recs, top_n):
    from ..record import OUTSIDE, UNASSIGNED
    # free calls go where they change the most: in-catchment records missing a phone or
    # website first, then by review count (the highest-value businesses)
    cand = [b for b in recs if places_id(b.maps) and b.area not in (OUTSIDE, UNASSIGNED)]
    cand.sort(key=lambda b: (bool(b.phone) and bool(b.website),
                             -(b.reviews if isinstance(b.reviews, int) else -1)))
    return cand[:top_n]


def load_cache(path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                d = json.loads(line)
                out[d['key']] = d['data']
    return out


def apply(b, d: dict, used_phones: set):
    """Fold one Places response into a record. Like the other enrichers, a phone never becomes a
    record's primary number if another record already uses it (e.g. a chain's hotline)."""
    from ..normalise import clean_phone
    phone = clean_phone(d.get('internationalPhoneNumber') or d.get('nationalPhoneNumber') or '')
    if phone:
        if not b.phone and phone not in used_phones:
            b.phone = phone
            used_phones.add(phone)
        b.phones_all = '; '.join(dict.fromkeys([p for p in [b.phone] + b.phones_all.split('; ') + [phone] if p]))
    if d.get('websiteUri') and not b.website:
        b.website = d['websiteUri']
    if d.get('userRatingCount') is not None:
        b.reviews = int(d['userRatingCount'])
    if d.get('rating') is not None and b.rating == '':
        b.rating = float(d['rating'])
    if not any('Places API' in s for s in b.sources_all):
        b.sources_all.append(f'Google Places API ({date.today().strftime("%b %Y")})')


def enrich(run, recs, http=requests, budget: Budget | None = None):
    """Responses are cached in cache/places_api.jsonl, so rebuilding the derived stages never
    spends a call twice."""
    cfg = run.cfg.sources.places_api
    if not cfg.enabled:
        return recs
    cache_path = run.dir / 'cache' / 'places_api.jsonl'
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = load_cache(cache_path)
    targets = [b for b in candidates(run, recs, cfg.top_n) if places_id(b.maps) not in cache]
    key = api_key() if targets else ''
    if targets and not key:
        run.log.event('skip', 'places_api enabled but GOOGLE_PLACES_API_KEY is not set (env or .env) - '
                      f'{len(targets)} uncached records not enriched')
        targets = []
    sku = 'enterprise' if 'enterprise' in cfg.skus else cfg.skus[-1]
    mask = FIELD_MASKS[sku]
    called = 0
    if targets:
        budget = budget or Budget(cfg.monthly_ceiling_pct)
        with open(cache_path, 'a', encoding='utf-8') as fh:
            for b in targets:
                if not budget.take(sku):
                    run.log.event('budget', f'places_api: {sku} ceiling ({budget.ceiling(sku)}/month = '
                                  f'{cfg.monthly_ceiling_pct}% of free) reached - stopping')
                    break
                r = http.get(ENDPOINT.format(pid=places_id(b.maps)), timeout=15,
                             headers={'X-Goog-Api-Key': key, 'X-Goog-FieldMask': mask})
                run.log.event('places_api', '', sku=sku, status=r.status_code, remaining=budget.remaining(sku))
                if r.status_code != 200:
                    continue
                d = {k: v for k, v in r.json().items() if k in ('internationalPhoneNumber', 'nationalPhoneNumber',
                                                              'websiteUri', 'userRatingCount', 'rating')}
                cache[places_id(b.maps)] = d
                fh.write(json.dumps({'key': places_id(b.maps), 'name': b.name, 'data': d}, ensure_ascii=False) + '\n')
                called += 1
    used = {b.phone for b in recs if b.phone}
    applied = 0
    for b in recs:
        d = cache.get(places_id(b.maps))
        if d is not None:
            apply(b, d, used)
            applied += 1
    run.log.event('stage', f'places_api: {applied} records enriched ({called} new calls this run)')
    return recs
