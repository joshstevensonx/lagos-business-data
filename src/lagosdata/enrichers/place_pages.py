"""Second Playwright visit to a Google place page for delivery signals (SPEC §6.4).

Observed Oct 2026 (logged-out, Lagos): place pages show the full address, phone,
website and - where the business has one - an ordering action link
(data-item-id "action:4", e.g. Glovo / Chowdeck). The About tab's service-option
list (Delivery / Takeout / Catering) is read when present but was absent on the
pages checked; review counts are NOT on the place page (they come from the feed).

Emits additional_info in the NESTED shape score.py's _flag() reads, so that path
stays exercised. A visited record gets score_basis 'Full'; an ordering link scores
as online ordering, never as Google's own delivery flag.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from datetime import date

from ..normalise import clean_phone
from ..score import BASIS_FULL
from ..sources.gmaps_browser import CAPTCHA_JS, LAUNCH_ARGS, VIEWPORTS

PLACE_JS = """() => {
  const items = {};
  for (const e of document.querySelectorAll('[data-item-id]')) {
    items[e.getAttribute('data-item-id')] = {label: e.getAttribute('aria-label') || '', href: e.getAttribute('href') || ''};
  }
  return {h1: (document.querySelector('h1') || {}).textContent || '', items};
}"""
ABOUT_JS = """() => [...document.querySelectorAll('div[role="region"] li span[aria-label], div[role="region"] li[aria-label]')]
                    .map(e => e.getAttribute('aria-label'))"""

ATTRS = [  # (regex on About aria-label, group, key, value)
    (r'^(offers |has )?no-contact delivery', 'Service options', 'No-contact delivery', True),
    (r"^(no|doesn.t offer) delivery", 'Service options', 'Delivery', False),
    (r'^(offers )?delivery', 'Service options', 'Delivery', True),
    (r"^(no|doesn.t offer) takeout", 'Service options', 'Takeout', False),
    (r'^(offers )?takeout|^(offers )?takeaway', 'Service options', 'Takeout', True),
    (r'^(offers |serves )?dine-in', 'Service options', 'Dine-in', True),
    (r'^(offers )?catering', 'Dining options', 'Catering', True),
]


def parse_place(info: dict, about: list[str]) -> dict:
    items = info.get('items') or {}
    out = {'phone': '', 'website': '', 'addr': '', 'order_url': '', 'attrs': {}}
    for k, v in items.items():
        if k.startswith('phone:tel:'):
            out['phone'] = clean_phone(k.removeprefix('phone:tel:'))
        elif k == 'authority':
            out['website'] = v.get('href', '')
        elif k == 'address':
            out['addr'] = re.sub(r'^Address:\s*', '', v.get('label', '')).strip()
        elif k.startswith('action:4') and v.get('href'):
            out['order_url'] = v['href']
    for lab in about or []:
        lab = (lab or '').strip().lower()
        for rx, group, key, val in ATTRS:
            if re.search(rx, lab):
                out['attrs'].setdefault(group, {})[key] = val
                break
    return out


def apply(b, p: dict, used_phones: set):
    if p['phone'] and not b.phone and p['phone'] not in used_phones:
        b.phone = p['phone']
        used_phones.add(p['phone'])
    if p['phone']:
        b.phones_all = '; '.join(dict.fromkeys([x for x in [b.phone] + b.phones_all.split('; ') + [p['phone']] if x]))
    if p['website'] and not b.website:
        b.website = p['website']
    if p['addr'] and len(p['addr']) > len(b.addr or ''):
        b.addr = p['addr']                     # the full address names the area (derive-centroids)
    ai = dict(b.additional_info or {})
    for group, kv in p['attrs'].items():
        ai[group] = [{k: v} for k, v in kv.items()]
    meta = dict(ai.get('_meta') or {})
    meta['place_page_checked'] = date.today().isoformat()
    if p['order_url']:
        meta['order_online_url'] = p['order_url']
    ai['_meta'] = meta
    b.additional_info = ai
    b.score_basis = BASIS_FULL


async def _visit_all(run, targets, executable_path, conc, delay):
    from playwright.async_api import async_playwright
    queue: asyncio.Queue = asyncio.Queue()
    for b in targets:
        queue.put_nowait(b)
    results, state = {}, {'abort': '', 'fails': 0}
    t0 = time.monotonic()

    async def worker(browser):
        ctx = page = None
        n = 0
        try:
            while not state['abort'] and not run.stop.requested:
                try:
                    b = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                if ctx is None or n % 25 == 0:
                    if ctx:
                        await ctx.close()
                    w, h = random.choice(VIEWPORTS)
                    ctx = await browser.new_context(viewport={'width': w, 'height': h}, locale='en-GB')
                    await ctx.route('**/*', lambda r: r.abort() if r.request.resource_type in ('image', 'media', 'font')
                                    else r.continue_())
                    page = await ctx.new_page()
                n += 1
                url = b.maps + ('&' if '?' in b.maps else '?') + 'hl=en'
                try:
                    await page.goto(url, wait_until='domcontentloaded', timeout=45000)
                    if await page.evaluate(CAPTCHA_JS):
                        state['abort'] = f'CAPTCHA on place page for "{b.name}"; place-page enrichment stopped'
                        return
                    await page.wait_for_selector('h1', timeout=20000)
                    await page.wait_for_timeout(1200)
                    info = await page.evaluate(PLACE_JS)
                    about = []
                    tab = await page.query_selector('button[role="tab"][aria-label^="About"]')
                    if tab:
                        await tab.click()
                        await page.wait_for_timeout(1200)
                        about = await page.evaluate(ABOUT_JS)
                    results[id(b)] = parse_place(info, about)
                    run.log.event('place_page', '', name=b.name, url=b.maps[:120])
                except Exception as e:  # noqa: BLE001
                    run.log.event('place_page_error', f'{b.name}: {type(e).__name__}: {str(e)[:150]}')
                    await ctx.close()
                    ctx = None
                await asyncio.sleep(random.uniform(*delay))
        finally:
            if ctx:
                await ctx.close()

    async with async_playwright() as p:
        kw = {'headless': True, 'args': LAUNCH_ARGS}
        if executable_path:
            kw['executable_path'] = executable_path
        browser = await p.chromium.launch(**kw)
        try:
            await asyncio.gather(*(worker(browser) for _ in range(min(conc, len(targets)))))
        finally:
            await browser.close()
    run.log.event('stage', f'place_pages: visited {len(results)}/{len(targets)} in {time.monotonic() - t0:.0f}s'
                  + (f'; ABORTED: {state["abort"]}' if state['abort'] else ''))
    return results


def _key(b) -> str:
    m = re.search(r'!1s(0x[0-9a-f]+:0x[0-9a-f]+)', b.maps or '')
    return b.place_id or (m.group(1) if m else b.maps.split('?')[0])


def _load_cache(path) -> dict:
    out = {}
    if path.exists():
        for line in path.read_text(encoding='utf-8').splitlines():
            if line.strip():
                d = json.loads(line)
                out[d['key']] = d['parsed']
    return out


def enrich(run, recs):
    """Visit place pages not yet in the run's cache (derived stages are rebuilt from raw, so
    visit results persist in cache/place_pages.jsonl like raw data), then apply every cached
    result. A re-run revisits nothing."""
    cfg = run.cfg.enrich.place_pages
    g = run.cfg.sources.gmaps_browser
    cache_path = run.dir / 'cache' / 'place_pages.jsonl'
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache = _load_cache(cache_path)
    cand = [b for b in recs if b.maps.startswith('https://www.google.com/maps/place/') and _key(b) not in cache]
    # reviews_desc: review counts come from the feed (missing on some cards - those go last)
    cand.sort(key=lambda b: -(b.reviews if isinstance(b.reviews, int) else -1))
    budget = max(0, cfg.max_place_visits - len(cache))
    targets = cand[:budget]
    if targets:
        results = asyncio.run(_visit_all(run, targets, os.environ.get('LAGOSDATA_CHROMIUM'),
                                         run.options.get('place_concurrency') or g.concurrency,
                                         tuple(g.delay_seconds)))
        with open(cache_path, 'a', encoding='utf-8') as fh:
            for b in targets:
                if id(b) in results:
                    cache[_key(b)] = results[id(b)]
                    fh.write(json.dumps({'key': _key(b), 'name': b.name, 'parsed': results[id(b)]},
                                        ensure_ascii=False) + '\n')
    used = {b.phone for b in recs if b.phone}
    applied = 0
    for b in recs:
        p = cache.get(_key(b))
        if p is not None:
            apply(b, p, used)
            applied += 1
    run.log.event('stage', f'place_pages: {applied} records have a checked place page '
                  f'({len(targets)} visited this run, budget {cfg.max_place_visits})')
    return recs
