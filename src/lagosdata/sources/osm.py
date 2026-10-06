"""OpenStreetMap via the Overpass API (SPEC §3.2).

Free and unlimited, but thin in these Lagos areas (the Maryland bbox held 38
POIs): treat it as a cross-verification layer and a source of phone / website /
opening_hours tags, not as the census.

Overpass was unreachable through the HTTPS proxy during the manual runs but
worked when fetch()-ed from a browser page, so there are two transports:
`requests` (default) and a Playwright page (`--osm-via-browser`). Either failing
is logged and never aborts a run.

Data © OpenStreetMap contributors, ODbL.
"""
from __future__ import annotations

from datetime import date

import requests

from .. import __version__
from ..areas import bbox_for
from ..normalise import clean_phone
from ..record import Business
from .base import Search, Source, SourceUnavailable

ENDPOINTS = ['https://overpass-api.de/api/interpreter',
             'https://overpass.kumi.systems/api/interpreter']

# what to ask for, per pipeline
SELECTORS = {
    'magazine': [
        'node["shop"]', 'way["shop"]',
        'node["amenity"~"restaurant|cafe|fast_food|pharmacy|bank|school|place_of_worship"]',
        'node["office"]', 'node["healthcare"]',
    ],
    'delivery': [
        'node["amenity"~"^(restaurant|cafe|fast_food|food_court|pharmacy)$"]',
        'way["amenity"~"^(restaurant|cafe|fast_food|food_court|pharmacy)$"]',
        'node["shop"~"^(supermarket|convenience|bakery|greengrocer|chemist|deli|general|beverages|butcher)$"]',
        'way["shop"~"^(supermarket|convenience|bakery|greengrocer|chemist|deli|general)$"]',
        'node["healthcare"="pharmacy"]',
    ],
}
LABEL_KEYS = ('shop', 'amenity', 'healthcare', 'office', 'craft', 'tourism', 'leisure')


def build_query(bbox, pipeline: str, timeout: int = 60) -> str:
    s, w, n, e = bbox
    box = f'({s},{w},{n},{e})'
    body = '\n'.join(f'  {sel}{box};' for sel in SELECTORS[pipeline])
    return f'[out:json][timeout:{timeout}];\n(\n{body}\n);\nout center tags;'


def label_of(tags: dict) -> str:
    for k in LABEL_KEYS:
        v = tags.get(k)
        if v:
            v = v.split(';')[0].strip()
            return k if v == 'yes' else v.replace('_', ' ')
    return ''


class OsmSource(Source):
    name = 'osm'

    def __init__(self, run, via_browser: bool | None = None, transport=None):
        super().__init__(run)
        self.cfg = run.cfg.sources.osm
        self.via_browser = self.cfg.via_browser if via_browser is None else via_browser
        self._transport = transport          # injectable for tests: fn(query) -> dict

    def bbox(self):
        if self.cfg.bbox:
            return tuple(self.cfg.bbox)
        return bbox_for(self.run.cfg.areas, self.run.areas.areas, self.cfg.bbox_pad_km)

    def plan(self) -> list[Search]:
        bb = self.bbox()
        if not bb:
            self.run.log.event('skip', 'OSM: no configured area has geometry and no osm.bbox override; '
                               'run derive-centroids first', source=self.name)
            return []
        return [Search(term=f'osm:{self.run.cfg.pipeline}', area='bbox ' + ','.join(map(str, bb)))]

    # ------------------------------------------------------------ transport
    def _user_agent(self) -> str:
        contact = self.run.cfg.sources.directories.contact_email
        return f'lagosdata/{__version__} (small local business directory; {contact or "no contact set"})'

    def _via_requests(self, query: str) -> dict:
        errors = []
        for url in ENDPOINTS:
            try:
                self.run.log.event('http', '', source=self.name, method='POST', url=url)
                resp = requests.post(url, data={'data': query}, timeout=self.cfg.timeout_seconds,
                                     headers={'User-Agent': self._user_agent()})
                resp.raise_for_status()
                return resp.json()
            except Exception as e:  # noqa: BLE001 - every failure mode means "try the next endpoint"
                errors.append(f'{url}: {type(e).__name__}: {e}')
        raise SourceUnavailable('; '.join(errors))

    def _via_browser(self, query: str) -> dict:
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise SourceUnavailable('--osm-via-browser needs Playwright: pip install "lagosdata[browser]"') from e
        errors = []
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            try:
                page = browser.new_page(user_agent=self._user_agent())
                for url in ENDPOINTS:
                    try:
                        self.run.log.event('browser', '', source=self.name, method='fetch', url=url)
                        page.goto(url.rsplit('/api/', 1)[0] + '/', timeout=30000)
                        return page.evaluate(
                            """async ([url, q]) => {
                                 const r = await fetch(url, {method: 'POST',
                                     headers: {'Content-Type': 'application/x-www-form-urlencoded'},
                                     body: 'data=' + encodeURIComponent(q)});
                                 if (!r.ok) throw new Error('HTTP ' + r.status);
                                 return await r.json();
                               }""", [url, query])
                    except Exception as e:  # noqa: BLE001
                        errors.append(f'{url}: {type(e).__name__}: {e}')
            finally:
                browser.close()
        raise SourceUnavailable('; '.join(errors))

    # --------------------------------------------------------------- search
    def search(self, s: Search) -> list[dict]:
        bb = tuple(float(x) for x in s.area.removeprefix('bbox ').split(','))
        query = build_query(bb, self.run.cfg.pipeline, timeout=min(self.cfg.timeout_seconds, 180))
        if self._transport:
            data = self._transport(query)
        elif self.via_browser:
            data = self._via_browser(query)
        else:
            data = self._via_requests(query)
        fetched = date.today().isoformat()
        rows = []
        for el in data.get('elements', []):
            rows.append({**el, '_fetched': fetched})
        return rows

    # ------------------------------------------------------------- mapping
    def to_business(self, raw: dict) -> Business | None:
        tags = raw.get('tags') or {}
        name = (tags.get('name') or tags.get('name:en') or tags.get('brand') or '').strip()
        if not name:
            return None
        lat = raw.get('lat', (raw.get('center') or {}).get('lat', ''))
        lng = raw.get('lon', (raw.get('center') or {}).get('lon', ''))
        phones_raw = []
        for k in ('phone', 'contact:phone', 'contact:mobile', 'mobile'):
            if tags.get(k):
                phones_raw += [p for p in tags[k].split(';') if p.strip()]
        phones = list(dict.fromkeys(p for p in (clean_phone(x) for x in phones_raw) if p))
        addr_parts = [' '.join(x for x in (tags.get('addr:housenumber'), tags.get('addr:street')) if x),
                      tags.get('addr:suburb') or tags.get('addr:district'),
                      tags.get('addr:city'), tags.get('addr:state')]
        addr = ', '.join(p for p in addr_parts if p)
        fetched = raw.get('_fetched') or date.today().isoformat()
        src = f'OpenStreetMap ({date.fromisoformat(fetched).strftime("%b %Y")})'
        wa = clean_phone(tags.get('contact:whatsapp', ''))
        return Business(
            name=name,
            lat=float(lat) if lat != '' else '',
            lng=float(lng) if lng != '' else '',
            addr=addr,
            street=tags.get('addr:street', ''),
            label=label_of(tags),
            phone=phones[0] if phones else '',
            phones_all='; '.join(phones),
            whatsapp=wa,
            website=tags.get('website') or tags.get('contact:website') or tags.get('url') or '',
            email=tags.get('email') or tags.get('contact:email') or '',
            instagram=tags.get('contact:instagram', ''),
            facebook=tags.get('contact:facebook', ''),
            twitter=tags.get('contact:twitter', ''),
            maps=f'https://www.openstreetmap.org/{raw.get("type", "node")}/{raw.get("id", "")}',
            source=src,
            sources_all=[src],
            added=fetched,
            notes=(f'Opening hours (OSM): {tags["opening_hours"]}' if tags.get('opening_hours') else ''),
        )
