"""Nigerian business directories (SPEC §3.4) - free HTML, lower trust than Google.

Each site has its own small parser with its selectors declared at the top of its
block, because these sites change markup. Each parser has a recorded fixture test;
a page that should hold listings but parses to zero raises (a silent zero is the
worst failure mode here).

Conduct: robots.txt checked before every fetch (disallowed paths are skipped and
logged, never worked around); one shared session; <= 1 request/second per domain;
descriptive User-Agent with a contact email.

Status Oct 2026: finelib (area -> category tree) and businesslist (all-Lagos list,
with coordinates) are built. cybo answers automated requests with 403 and vconnect
timed out; ngex has no area pages - those three are logged as skipped.
"""
from __future__ import annotations

import re
import time
import urllib.robotparser
from datetime import date
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

from .. import __version__
from ..normalise import clean_phone, street_of
from ..record import Business
from .base import Search, Source, SourceUnavailable


class ParserBroken(Exception):
    """A page that should contain listings parsed to nothing - fix the selector block."""


class Polite:
    def __init__(self, contact: str, rate: float, log):
        self.s = requests.Session()
        self.s.headers['User-Agent'] = f'lagosdata/{__version__} (small local business directory; {contact or "no contact"})'
        self.min_gap = 1.0 / rate
        self.last: dict[str, float] = {}
        self.robots: dict[str, urllib.robotparser.RobotFileParser] = {}
        self.log = log
        self.skipped: list[str] = []

    def _wait(self, host):
        gap = time.monotonic() - self.last.get(host, 0)
        if gap < self.min_gap:
            time.sleep(self.min_gap - gap)
        self.last[host] = time.monotonic()

    def allowed(self, url) -> bool:
        p = urlparse(url)
        base = f'{p.scheme}://{p.netloc}'
        if base not in self.robots:
            rp = urllib.robotparser.RobotFileParser()
            self._wait(p.netloc)
            try:
                r = self.s.get(base + '/robots.txt', timeout=15)
                rp.parse(r.text.splitlines() if r.status_code == 200 else [])
            except requests.RequestException:
                rp.parse([])
            self.robots[base] = rp
        ok = self.robots[base].can_fetch(self.s.headers['User-Agent'], url)
        if not ok:
            self.skipped.append(url)
            self.log.event('robots_skip', f'robots.txt disallows {url}', url=url)
        return ok

    def get(self, url) -> str | None:
        if not self.allowed(url):
            return None
        self._wait(urlparse(url).netloc)
        try:
            r = self.s.get(url, timeout=20)
        except requests.RequestException as e:
            raise SourceUnavailable(f'{url}: {type(e).__name__}') from e
        self.log.event('http', '', method='GET', url=url, status=r.status_code)
        if r.status_code == 404:
            return None
        if r.status_code in (403, 429):
            raise SourceUnavailable(f'{url}: HTTP {r.status_code} (refusing automated access - not worked around)')
        r.raise_for_status()
        return r.text


# ============================================================== finelib ====
FINELIB = 'https://www.finelib.com'
FL_AREA_URL = FINELIB + '/cities/lagos/areas-and-suburbs/{slug}'
FL_CATEGORY_LINKS = 'div.category-list a[href]'
FL_LISTING = 'div.box-682.bg-none'
FL_NAME = 'div.box-headings a[href*="/listing/"]'
FL_ADDR = 'div.cmpny-lstng-1:has(img[src*="bldng"])'
FL_PHONE = 'div.cmpny-lstng-1:has(img[src*="phone"])'
FL_DESC = 'div.listing-desc'


def finelib_slugs(area: str, aliases: list[str]) -> list[str]:
    names = [p.strip() for p in area.split('/')] + list(aliases)
    return list(dict.fromkeys(re.sub(r'[^a-z0-9]+', '-', n.lower()).strip('-') for n in names if n))


def parse_finelib(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for box in soup.select(FL_LISTING):
        a = box.select_one(FL_NAME)
        if not a:
            continue
        addr = box.select_one(FL_ADDR)
        phone = box.select_one(FL_PHONE)
        desc = box.select_one(FL_DESC)
        m = re.search(r'/listing/[^/]+/(\d+)', a['href'])
        out.append({'name': a.get_text(strip=True), 'listing_id': m.group(1) if m else '',
                    'url': urljoin(FINELIB, a['href']),
                    'addr': addr.get_text(' ', strip=True) if addr else '',
                    'phone': phone.get_text(' ', strip=True) if phone else '',
                    'desc': desc.get_text(' ', strip=True) if desc else '',
                    'category': ' > '.join(p.replace('-', ' ') for p in
                                           urlparse(page_url).path.split('/')[5:]),
                    'page': page_url})
    return out


def finelib_category_links(html: str, area_url: str) -> list[str]:
    soup = BeautifulSoup(html, 'html.parser')
    path = urlparse(area_url).path.rstrip('/')
    return [urljoin(FINELIB, a['href']) for a in soup.select(FL_CATEGORY_LINKS)
            if a['href'].rstrip('/').startswith(path + '/')]


# ========================================================= businesslist ====
BL = 'https://www.businesslist.com.ng'
BL_PAGE_URL = BL + '/location/lagos/{page}'
BL_COMPANY = 'div.company'
BL_NAME = 'div.company_header h3 a'
BL_ADDR = 'div.company_header div.address'
BL_PHONE = 'div.cont div.s:has(i.fa-phone) span'
BL_MARKER = 'div.mapmarker'
BL_REVIEWS = 'div.company_reviews'
BL_TAGLINE = 'div.company_header div.tagline'


def parse_businesslist(html: str, page_url: str) -> list[dict]:
    soup = BeautifulSoup(html, 'html.parser')
    out = []
    for c in soup.select(BL_COMPANY):
        a = c.select_one(BL_NAME)
        if not a:
            continue
        mk = c.select_one(BL_MARKER)
        ph = c.select_one(BL_PHONE)
        addr = c.select_one(BL_ADDR)
        tag = c.select_one(BL_TAGLINE)
        out.append({'name': a.get_text(strip=True), 'listing_id': c.get('data-cmpid', ''),
                    'url': urljoin(BL, a['href']),
                    'addr': addr.get_text(' ', strip=True) if addr else '',
                    'phone': ph.get_text(' ', strip=True) if ph else '',
                    'lat': mk.get('data-ltd', '') if mk else '', 'lng': mk.get('data-lng', '') if mk else '',
                    'desc': tag.get_text(' ', strip=True) if tag else '',
                    'sponsored': bool(c.find('i', string='Sponsored')), 'page': page_url})
    return out


# ================================================================ source ====
BUILT = {'finelib', 'businesslist'}


class DirectoriesSource(Source):
    name = 'directories'

    def __init__(self, run, fetch=None):
        super().__init__(run)
        self.cfg = run.cfg.sources.directories
        self.http = Polite(self.cfg.contact_email, self.cfg.rate_per_second, run.log)
        self.fetch = fetch or self.http.get                      # injectable for tests

    def plan(self) -> list[Search]:
        out = []
        for site in self.cfg.sites:
            if site not in BUILT:
                self.run.log.event('skip', f'directories/{site}: not built (cybo 403s automated requests, '
                                   'vconnect timed out, ngex has no area pages)', source=self.name)
                continue
            if site == 'finelib':
                out += [Search(term='finelib', area=a) for a in self.run.cfg.areas]
            elif site == 'businesslist':
                out += [Search(term='businesslist', area=f'lagos page {i}')
                        for i in range(1, self.cfg.businesslist_pages + 1)]
        return out

    def search(self, s: Search) -> list[dict]:
        rows = self._finelib(s.area) if s.term == 'finelib' else self._businesslist(s.area)
        fetched = date.today().isoformat()
        for r in rows:
            r['_site'] = s.term
            r['_fetched'] = fetched
            r['_area_hint'] = s.area if s.term == 'finelib' else ''
        return rows

    def _finelib(self, area: str) -> list[dict]:
        ad = self.run.areas.areas.get(area)
        for slug in finelib_slugs(area, ad.aliases if ad else []):
            url = FL_AREA_URL.format(slug=slug)
            html = self.fetch(url)
            if not html:
                continue
            cats = finelib_category_links(html, url)
            if not cats:
                continue
            rows, seen, queue = [], set(), list(cats)
            while queue:
                cu = queue.pop(0)
                if cu in seen:
                    continue
                seen.add(cu)
                page = self.fetch(cu)
                if not page:
                    continue
                queue += [u for u in finelib_category_links(page, cu) if u not in seen]
                rows += parse_finelib(page, cu)
            uniq = {r['listing_id'] or r['name']: r for r in rows}
            self.run.log.event('directory', f'finelib {area} ({slug}): {len(seen)} category pages, '
                               f'{len(uniq)} listings')
            return list(uniq.values())
        self.run.log.event('directory', f'finelib: no area page for {area}')
        return []

    def _businesslist(self, label: str) -> list[dict]:
        page = int(label.rsplit(' ', 1)[1])
        url = BL + '/location/lagos' if page == 1 else BL_PAGE_URL.format(page=page)
        html = self.fetch(url)
        if not html:
            return []
        rows = parse_businesslist(html, url)
        if not rows and 'company_header' in html:
            raise ParserBroken(f'businesslist {url}: listings present but 0 parsed - check BL_* selectors')
        return [r for r in rows if not r['sponsored'] or page == 1]

    def to_business(self, raw: dict) -> Business | None:
        name = (raw.get('name') or '').strip()
        if not name:
            return None
        site = raw.get('_site', 'directory')
        fetched = raw.get('_fetched') or date.today().isoformat()
        label_site = {'finelib': 'Finelib', 'businesslist': 'BusinessList.com.ng'}.get(site, site)
        src = f'{label_site} ({date.fromisoformat(fetched).strftime("%b %Y")})'
        phones = [clean_phone(p) for p in re.split(r'[,/;]| or ', raw.get('phone') or '')]
        phones = list(dict.fromkeys(p for p in phones if p))
        cat = raw.get('category', '')
        label = cat.split(' > ')[-1] if cat else ''

        def f(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return ''
        addr = raw.get('addr', '')
        return Business(name=name, addr=addr, street=street_of(addr), label=label,
                        phone=phones[0] if phones else '', phones_all='; '.join(phones),
                        lat=f(raw.get('lat')), lng=f(raw.get('lng')), maps=raw.get('url', ''),
                        notes=(raw.get('desc') or '')[:300], source=src, sources_all=[src], added=fetched)
