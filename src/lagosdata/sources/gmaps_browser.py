"""Google Maps via Playwright (SPEC §3.3) - a browser reading public listing pages.

Mechanics learned the hard way, all implemented here:
  (a) never read before the feed renders: poll for >=3 result anchors (22s max),
      then scroll the feed until the count is stable for 2 checks (27s cap).
      Reading straight after navigation once returned 1 pharmacy where 118 existed.
  (b) concurrency via independent BrowserContexts (default 3, cap 6), recycled
      every N searches, random 2-6s delay per worker, randomised viewport.
  (c) wide-viewport sweeps: one zoom-14 search spans several areas; records are
      assigned to areas afterwards from their own coordinates (geo stage).
  (d) conduct: back off hard on rate-limit signals, never solve a CAPTCHA - abort
      the source, keep what was collected, say so plainly. No proxies, no UA farm.

JS is used only for the render/scroll loop and to read raw card pieces; all
parsing is Python (parse_card), so it is testable against recorded pages.

Observed Oct 2026: the search feed shows the star rating but NOT the review
count. Review counts now come only from place pages (enrich step).
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import time
from datetime import date
from urllib.parse import quote

from ..normalise import clean_phone, street_of
from ..record import Business
from ..tree import ALL_TERMS
from .base import Search, Source, SourceAborted

RENDER_JS = """async ([waitMs, capMs, pollMs, pauseMs, minAnchors]) => {
  const t0 = Date.now();
  const cnt = () => document.querySelectorAll('a.hfpxzc').length;
  // 1. wait for the feed to render at all
  while (Date.now() - t0 < waitMs && cnt() < minAnchors) {
    await new Promise(s => setTimeout(s, pollMs));
  }
  // 2. scroll until the result count stops growing
  let prev = cnt(), stale = 0;
  while (Date.now() - t0 < capMs) {
    const feed = document.querySelector('div[role="feed"]');
    if (feed) feed.scrollTop = feed.scrollHeight;
    await new Promise(s => setTimeout(s, pauseMs));
    const cur = cnt();
    if (cur === prev) { if (++stale >= 2) break; } else { stale = 0; prev = cur; }
  }
  return cnt();
}"""

# raw pieces only - no positional interpretation here
EXTRACT_JS = """() => [...document.querySelectorAll('a.hfpxzc')].map(a => {
  const card = a.closest('div[jsaction]') || a.parentElement;
  const leaves = card ? [...card.querySelectorAll('*')].filter(e => !e.children.length)
                         .map(e => e.textContent.trim()) : [];
  const st = card && card.querySelector('span[role="img"][aria-label]');
  const web = card && (card.querySelector('a[data-value="Website"]') ||
                       card.querySelector('a[aria-label^="Visit"][href^="http"]'));
  return {aria: a.getAttribute('aria-label') || '', href: a.getAttribute('href') || '',
          stars: st ? st.getAttribute('aria-label') : '', leaves,
          website: web ? (web.getAttribute('href') || '') : ''};
})"""

SINGLE_JS = """() => ({aria: (document.querySelector('h1') || {}).textContent || '',
                       href: location.href, stars: '', leaves: [], website: ''})"""

CAPTCHA_JS = """() => location.pathname.startsWith('/sorry') ||
                       !!document.querySelector('iframe[src*="recaptcha"], #captcha-form, form[action*="sorry"]')"""
CONSENT_JS = """() => location.hostname.startsWith('consent.') ||
                       !!document.querySelector('form[action*="consent.google"]')"""

# The Maps feed stops at 120 results (observed Oct 2026: every busy term returned exactly 120).
# A search that hits the cap has been truncated, so it is split into 4 quadrant searches one
# zoom level closer, recursively, up to MAX_SPLIT_ZOOM.
FEED_CAP = 120
MAX_SPLIT_ZOOM = 17
REF_VIEWPORT = (1366, 768)


def split_viewport(lat: float, lng: float, zoom: int) -> list[tuple[float, float, int]]:
    """Centres of the 4 quadrants of a viewport, at zoom + 1 (each child shows one quadrant)."""
    import math
    deg_per_px = 360 / (256 * 2 ** zoom)
    dlng = REF_VIEWPORT[0] * deg_per_px / 4
    dlat = REF_VIEWPORT[1] * deg_per_px * math.cos(math.radians(lat)) / 4
    return [(round(lat + sy * dlat, 4), round(lng + sx * dlng, 4), zoom + 1) for sy in (1, -1) for sx in (-1, 1)]


def viewport_of(area_label: str):
    m = re.search(r'(-?\d+\.\d+),(-?\d+\.\d+),(\d+)z', area_label)
    return (float(m.group(1)), float(m.group(2)), int(m.group(3))) if m else None


def child_searches(s: Search) -> list[Search]:
    v = viewport_of(s.area)
    if not v or v[2] >= MAX_SPLIT_ZOOM:
        return []
    prefix = s.area.split(' ')[0] if s.area.startswith('sweep') else s.area.split(' @')[0]
    return [Search(term=s.term, area=f'{prefix} {la:.4f},{lo:.4f},{z}z' if prefix == 'sweep'
                   else f'{prefix} @{la:.4f},{lo:.4f},{z}z') for la, lo, z in split_viewport(*v)]


VIEWPORTS = [(1366, 768), (1440, 900), (1536, 864), (1280, 800), (1600, 900)]

STATUS_RE = re.compile(r'^(?:·\s*)?(open|closed|opens|closes|temporarily closed|permanently closed|open 24 hours)\b',
                       re.I)
PHONE_RE = re.compile(r'^\+?\d[\d\s\-()]{7,}$')
RATING_RE = re.compile(r'^\d(?:\.\d)?$')
REVIEWS_RE = re.compile(r'^\(([\d,]+)\)$')
STARS_RE = re.compile(r'([\d.]+)\s*stars?(?:\s*([\d,]+)\s*review)?', re.I)
NO_REVIEWS_RE = re.compile(r'^no reviews$', re.I)
ICON_RE = re.compile(r'^[\ue000-\uf8ff\s]+$')          # Material icon glyphs (private-use code points)
SKIP_LEAVES = {'·', '', 'Website', 'Directions', 'Order online', 'Reserve a table', 'Menu', 'Book online',
               'Delivery', 'Takeout', 'Dine-in', 'Sponsored'}


class CaptchaDetected(Exception):
    pass


class RateLimitSignal(Exception):
    pass


def parse_card(raw: dict) -> dict:
    """Raw card pieces -> fields. Every field defaults to ''."""
    out = {'name': (raw.get('aria') or '').strip(), 'label': '', 'addr': '', 'phone': '', 'rating': '',
           'reviews': '', 'lat': '', 'lng': '', 'place_id': '', 'website': '', 'maps': raw.get('href') or ''}
    href = out['maps']
    m = re.search(r'!3d(-?\d+\.\d+)!4d(-?\d+\.\d+)', href)
    if m:
        out['lat'], out['lng'] = float(m.group(1)), float(m.group(2))
    m = re.search(r'!1s(0x[0-9a-f]+:0x[0-9a-f]+)', href)
    if m:
        out['place_id'] = m.group(1)
    m = STARS_RE.search(raw.get('stars') or '')
    if m:
        out['rating'] = float(m.group(1))
        if m.group(2):
            out['reviews'] = int(m.group(2).replace(',', ''))
    web = raw.get('website') or ''
    if web.startswith('http') and 'google.' not in web.split('/')[2]:
        out['website'] = web
    rest = []
    for t in raw.get('leaves') or []:
        t = t.strip()
        if t in SKIP_LEAVES or t == out['name'] or NO_REVIEWS_RE.match(t) or ICON_RE.match(t):
            continue
        if RATING_RE.match(t):
            continue
        rm = REVIEWS_RE.match(t)
        if rm:
            if out['reviews'] == '':
                out['reviews'] = int(rm.group(1).replace(',', ''))
            continue
        if PHONE_RE.match(t):
            if not out['phone']:
                out['phone'] = t
            continue
        if STATUS_RE.match(t) or t.startswith('·'):
            continue
        rest.append(t)
    if rest:
        out['label'] = rest[0]
    if len(rest) > 1:
        out['addr'] = rest[1]
    # reference sweep filter: a "label" that is really a rating, or a price as an address
    if re.match(r'^[\d.]+\(', out['label']) or out['addr'].startswith('₦'):
        out['label'], out['addr'] = '', ''
    return out


class GmapsBrowserSource(Source):
    name = 'gmaps_browser'

    def __init__(self, run, url_for=None, timing: dict | None = None, executable_path: str | None = None):
        super().__init__(run)
        self.cfg = run.cfg.sources.gmaps_browser
        self.url_for = url_for or self._maps_url
        t = {'wait_ms': 22000, 'cap_ms': 27000, 'poll_ms': 500, 'pause_ms': 1300, 'min_anchors': 3,
             'delay': tuple(self.cfg.delay_seconds), 'backoff_base': 60.0, 'recycle_every': 25,
             'nav_timeout_ms': 45000}
        t.update(timing or {})
        self.t = t
        self.executable_path = executable_path or os.environ.get('LAGOSDATA_CHROMIUM') or None
        self.max_searches = run.options.get('max_searches') or self.cfg.max_searches
        self.max_runtime_s = 60 * (run.options.get('max_runtime') or self.cfg.max_runtime_minutes)
        self.best: dict[str, int] = {}         # term -> most results seen for it
        for s in run.state.searches():
            if s['source'] == self.name and s['status'] == 'done' and s['raw_count']:
                self.best[s['term']] = max(self.best.get(s['term'], 0), s['raw_count'])

    # ---------------------------------------------------------------- plan
    def terms(self) -> list[str]:
        tx = self.run.cfg.taxonomy
        return list(tx.terms) if tx.mode == 'subset' else list(tx.terms or ALL_TERMS)

    def plan(self) -> list[Search]:
        sweeps = [(sw.center[0], sw.center[1], sw.zoom) for sw in self.cfg.sweeps]
        if not sweeps:
            from ..areas import centre
            for a in self.run.cfg.areas:
                ad = self.run.areas.areas.get(a)
                c = centre(ad) if ad else None
                if c:
                    sweeps.append((c[0], c[1], self.cfg.zoom))
        if not sweeps:
            self.run.log.event('skip', 'gmaps_browser: no sweeps configured and no area has a centroid',
                               source=self.name)
        out = [Search(term=t, area=f'sweep {lat:.4f},{lng:.4f},{z}z') for t in self.terms() for lat, lng, z in sweeps]
        out += self.top_up_plan()
        return out + self.saturation_plan()

    def saturation_plan(self) -> list[Search]:
        """Children of every completed search that hit the feed cap - rebuilt from state, so a
        resumed run still splits searches that saturated before it was interrupted."""
        saturated = [Search(r['term'], r['area']) for r in self.run.state.searches()
                     if r['source'] == self.name and r['status'] == 'done' and (r['raw_count'] or 0) >= FEED_CAP]
        out, seen = [], set()
        while saturated:
            s = saturated.pop()
            for c in child_searches(s):
                if (c.term, c.area) in seen:
                    continue
                seen.add((c.term, c.area))
                out.append(c)
                if self.run.state.is_done(self.name, c.term, c.area):
                    row = next((r for r in self.run.state.searches() if r['source'] == self.name
                                and r['term'] == c.term and r['area'] == c.area), None)
                    if row and (row['raw_count'] or 0) >= FEED_CAP:
                        saturated.append(c)
        return out

    def top_up_plan(self) -> list[Search]:
        """Targeted zoom-15 searches for areas whose post-geo count is below its configured floor."""
        if not self.run.options.get('top_ups') or not self.cfg.top_ups:
            return []
        from ..areas import centre
        try:
            recs = self.run.read_stage('geo')
        except FileNotFoundError:
            self.run.log.event('skip', 'top-ups need a geo stage first; run the sweep and geo, then --top-ups')
            return []
        counts = {}
        for r in recs:
            counts[r.area] = counts.get(r.area, 0) + 1
        out = []
        for area, floor in self.cfg.top_ups.items():
            ad = self.run.areas.areas.get(area)
            c = centre(ad) if ad else None
            if c and counts.get(area, 0) < floor:
                self.run.log.event('plan', f'top-up {area}: {counts.get(area, 0)} < floor {floor}')
                out += [Search(term=t, area=f'topup {area} @{c[0]:.4f},{c[1]:.4f},15z') for t in self.terms()]
        return out

    @staticmethod
    def _maps_url(s: Search) -> str:
        lat, lng, z = viewport_of(s.area)
        return f'https://www.google.com/maps/search/{quote(s.term)}/@{lat:.4f},{lng:.4f},{z}z?hl=en'

    # -------------------------------------------------------------- search
    def search(self, s: Search) -> list[dict]:
        """One search, synchronously (used by tests and single-term discover)."""
        box = {}

        class _Rec:
            def started(self, s): pass
            def done(self, s, rows): box['rows'] = rows
            def failed(self, s, err, status='error'): box['err'] = err
            def released(self, s): pass
        self.search_many([s], _Rec(), split=False)
        if 'err' in box:
            raise RuntimeError(box['err'])
        return box.get('rows', [])

    def search_many(self, todo: list[Search], rec, split: bool = True):
        self.split = split
        self.run.log.event('notice', 'Google Maps source enabled: it reads public listing pages at low volume. '
                           'Keep concurrency and max_searches modest; CAPTCHAs are never solved - the source '
                           'stops instead.', source=self.name)
        asyncio.run(self._run(todo, rec))

    async def _run(self, todo, rec):
        try:
            from playwright.async_api import async_playwright
        except ImportError as e:
            raise SourceAborted('Playwright not installed: pip install "lagosdata[browser]"') from e
        queue: asyncio.Queue = asyncio.Queue()
        for s in todo:
            queue.put_nowait(s)
        self.abort_reason = ''
        self.started_n = 0
        self.t0 = time.monotonic()
        async with async_playwright() as p:
            kw = {'headless': True}
            if self.executable_path:
                kw['executable_path'] = self.executable_path
            browser = await p.chromium.launch(**kw)
            try:
                n = min(self.cfg.concurrency, len(todo))
                await asyncio.gather(*(self._worker(i, browser, queue, rec) for i in range(n)))
            finally:
                await browser.close()
        if self.abort_reason:
            raise SourceAborted(self.abort_reason)

    def _ceiling_hit(self) -> str:
        if self.run.stop.requested:
            return 'clean shutdown requested'
        if self.started_n >= self.max_searches:
            return f'max_searches={self.max_searches} reached'
        if time.monotonic() - self.t0 > self.max_runtime_s:
            return f'max_runtime={self.max_runtime_s // 60} min reached'
        return ''

    async def _new_context(self, browser):
        w, h = random.choice(VIEWPORTS)
        ua = None
        try:
            v = browser.version            # a real, current UA for this exact browser build - one, fixed
            ua = (f'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) '
                  f'Chrome/{v} Safari/537.36')
        except Exception:  # noqa: BLE001
            pass
        ctx = await browser.new_context(viewport={'width': w, 'height': h}, locale='en-GB', user_agent=ua)
        return ctx, await ctx.new_page()

    async def _worker(self, wid, browser, queue, rec):
        ctx = page = None
        done_here = fails = 0
        try:
            while not self.abort_reason:
                why = self._ceiling_hit()
                if why:
                    if not queue.empty():
                        self.run.log.event('stop', f'worker {wid}: {why}; remaining searches stay pending')
                    return
                try:
                    s = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                self.started_n += 1          # claim the slot before any await, so workers can't overshoot
                rec.started(s)
                if ctx is None or done_here % self.t['recycle_every'] == 0:
                    if ctx is not None:
                        await ctx.close()
                    ctx, page = await self._new_context(browser)
                try:
                    rows = await self._one(page, s)
                except CaptchaDetected as e:
                    self.abort_reason = (f'CAPTCHA shown on "{s.term}" @ {s.area} ({e}). The Google Maps source '
                                         'has stopped for this run; everything collected so far is kept. Do not '
                                         'retry immediately - wait (hours, not minutes), then re-run with lower '
                                         'concurrency and max_searches.')
                    rec.released(s)
                    return
                except RateLimitSignal as e:
                    fails += 1
                    rec.released(s)
                    if fails >= 3:
                        self.run.log.event('worker_stopped', f'worker {wid}: 3 consecutive rate-limit signals '
                                           f'(last: {e}); worker stopped, its searches stay pending', source=self.name)
                        return
                    wait = self.t['backoff_base'] * 2 ** (fails - 1)
                    self.run.log.event('backoff', f'worker {wid}: {e}; backing off {wait:.0f}s', source=self.name)
                    queue.put_nowait(s)
                    await ctx.close()
                    ctx = None
                    await asyncio.sleep(wait)
                    continue
                except Exception as e:  # noqa: BLE001 - one bad search never aborts the sweep
                    rec.failed(s, f'{type(e).__name__}: {str(e)[:300]}')
                    await ctx.close()
                    ctx = None
                    continue
                fails = 0
                done_here += 1
                rec.done(s, rows)
                if self.split and len(rows) >= FEED_CAP:
                    kids = [c for c in child_searches(s) if not self.run.state.is_done(self.name, c.term, c.area)]
                    if kids:
                        self.run.log.event('split', f'"{s.term}" @ {s.area} hit the {FEED_CAP}-result feed cap; '
                                           f'adding {len(kids)} zoomed-in quadrant searches', source=self.name)
                    for c in kids:
                        queue.put_nowait(c)
                await asyncio.sleep(random.uniform(*self.t['delay']))
        finally:
            if ctx is not None:
                await ctx.close()

    async def _one(self, page, s: Search) -> list[dict]:
        await page.goto(self.url_for(s), timeout=self.t['nav_timeout_ms'], wait_until='domcontentloaded')
        if await page.evaluate(CAPTCHA_JS):
            raise CaptchaDetected(page.url[:100])
        if await page.evaluate(CONSENT_JS):
            raise RateLimitSignal('consent wall')
        n = await page.evaluate(RENDER_JS, [self.t['wait_ms'], self.t['cap_ms'], self.t['poll_ms'],
                                            self.t['pause_ms'], self.t['min_anchors']])
        if await page.evaluate(CAPTCHA_JS):
            raise CaptchaDetected(page.url[:100])
        if n:
            rows = await page.evaluate(EXTRACT_JS)
        elif '/maps/place/' in page.url:
            rows = [await page.evaluate(SINGLE_JS)]      # an exact match opens the place page directly
        else:
            rows = []
        prev = self.best.get(s.term, 0)
        if not rows and prev > 0:
            raise RateLimitSignal(f'empty feed for "{s.term}", which returned {prev} elsewhere')
        if prev > 10 and len(rows) < 4:
            self.run.log.event('suspect_render', f'"{s.term}" @ {s.area}: {len(rows)} results where it returned '
                               f'{prev} before - check the render wait (SPEC §11)', source=self.name)
        self.best[s.term] = max(prev, len(rows))
        fetched = date.today().isoformat()
        kind = 'top-up' if s.area.startswith('topup') else 'sweep'
        for r in rows:
            r['_fetched'] = fetched
            r['_kind'] = kind
        return rows

    # ------------------------------------------------------------- mapping
    def to_business(self, raw: dict) -> Business | None:
        f = parse_card(raw)
        if not f['name']:
            return None
        fetched = raw.get('_fetched') or date.today().isoformat()
        src = f'Google Maps ({raw.get("_kind", "sweep")}, {date.fromisoformat(fetched).strftime("%b %Y")})'
        phone = clean_phone(f['phone'])
        return Business(
            name=f['name'], place_id=f['place_id'], lat=f['lat'], lng=f['lng'], addr=f['addr'],
            street=street_of(f['addr']), label=f['label'], phone=phone, phones_all=phone,
            website=f['website'], rating=f['rating'], reviews=f['reviews'], maps=f['maps'],
            source=src, sources_all=[src], added=fetched)
