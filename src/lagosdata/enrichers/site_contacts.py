"""Crawl each business's own website for contacts (SPEC §3.5) - replaces Apify scrapeContacts.

Homepage plus up to 3 of /contact, /contact-us, /about, /order, /delivery. Extracts
emails, social handles, extra phones, WhatsApp links and delivery signals.

Rules: robots.txt respected per host; 10s timeout; 2MB cap; concurrency across hosts,
serial within a host; every response cached by URL so a re-run costs nothing; GET only,
never a form, never off-domain. Social-media "websites" are read from the URL itself,
never fetched.
"""
from __future__ import annotations

import hashlib
import json
import re
import threading
import urllib.robotparser
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from urllib.parse import unquote, urljoin, urlparse

import requests

from .. import __version__
from ..normalise import clean_phone

PATHS = ['/contact', '/contact-us', '/about', '/order', '/delivery']
MAX_BYTES = 2 * 1024 * 1024
TIMEOUT = 10

EMAIL_RE = re.compile(r'[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}')
BAD_EMAIL = re.compile(r'(noreply|no-reply|donotreply|example\.(com|org)|sentry|wixpress|@\d+x\.|'
                       r'\.(png|jpe?g|gif|svg|webp|css|js)$|yourdomain|domain\.com|email\.com|user@)', re.I)
SOCIAL = {
    'instagram': re.compile(r'instagram\.com/([A-Za-z0-9_.]{2,30})', re.I),
    'facebook': re.compile(r'facebook\.com/(?!sharer|share|dialog|plugins|tr\b)([A-Za-z0-9.\-]{2,80}'
                           r'|profile\.php\?id=\d+)', re.I),
    'twitter': re.compile(r'(?:twitter|x)\.com/(?!intent|share|home)([A-Za-z0-9_]{1,15})\b', re.I),
    'linkedin': re.compile(r'linkedin\.com/(company|in)/([A-Za-z0-9\-_%]{2,100})', re.I),
    'tiktok': re.compile(r'tiktok\.com/@([A-Za-z0-9_.]{2,30})', re.I),
}
SOCIAL_SKIP = {'p', 'reel', 'reels', 'explore', 'accounts', 'stories', 'tv', 'about', 'legal', 'privacy',
               'help', 'login', 'signup', 'home', 'pages', 'groups', 'events', 'watch', 'search'}
WA_RE = re.compile(r'(?:wa\.me/|api\.whatsapp\.com/send/?\?phone=|whatsapp\.com/send\?phone=)\+?(\d{10,15})', re.I)
TEL_RE = re.compile(r'href=["\']tel:([^"\']+)', re.I)
PHONE_TEXT_RE = re.compile(r'(?:\+?234|0)[\s\-]?[789]\d{2}[\s\-]?\d{3}[\s\-]?\d{4}')
DELIVERY_RE = re.compile(r'\b(deliver(?:y|ies)?|dispatch|bulk order|corporate order|catering|wholesale|'
                         r'we deliver|free delivery)\b', re.I)
ORDER_ONLINE_RE = re.compile(r'\b(order online|order now|place an order|add to cart|checkout)\b', re.I)
SOCIAL_HOSTS = ('instagram.com', 'facebook.com', 'fb.com', 'twitter.com', 'x.com', 'tiktok.com',
                'linkedin.com', 'wa.me', 'whatsapp.com', 'google.com', 'goo.gl', 'g.page')


def canonical(kind: str, m: re.Match) -> str:
    if kind == 'instagram': return f'https://www.instagram.com/{m.group(1).rstrip(".")}'
    if kind == 'facebook': return f'https://www.facebook.com/{m.group(1)}'
    if kind == 'twitter': return f'https://x.com/{m.group(1)}'
    if kind == 'linkedin': return f'https://www.linkedin.com/{m.group(1)}/{m.group(2)}'
    return f'https://www.tiktok.com/@{m.group(1)}'


def extract(html: str) -> dict:
    """Contacts and signals from one HTML page."""
    text = unescape(html)
    out = {'emails': [], 'phones': [], 'whatsapp': [], 'delivery': [], 'order_online': False}
    for kind in SOCIAL:
        out[kind] = []
    mailtos = re.findall(r'mailto:([^"\'?>\s]+)', text, re.I)
    for e in [unquote(x) for x in mailtos] + EMAIL_RE.findall(re.sub(r'<[^>]+>', ' ', text)):
        e = e.strip().strip('.').lower()
        if EMAIL_RE.fullmatch(e) and not BAD_EMAIL.search(e) and e not in out['emails']:
            out['emails'].append(e)
    for kind, rx in SOCIAL.items():
        for m in rx.finditer(text):
            handle = m.group(1).lower() if kind != 'linkedin' else m.group(2).lower()
            if handle.strip('.') in SOCIAL_SKIP:
                continue
            url = canonical(kind, m)
            if url not in out[kind]:
                out[kind].append(url)
    for m in WA_RE.finditer(text):
        p = clean_phone(m.group(1))
        if p and p not in out['whatsapp']:
            out['whatsapp'].append(p)
    for raw in TEL_RE.findall(text) + PHONE_TEXT_RE.findall(re.sub(r'<[^>]+>', ' ', text)):
        p = clean_phone(raw)
        if p and p not in out['phones']:
            out['phones'].append(p)
    visible = re.sub(r'<(script|style)\b.*?</\1>', ' ', text, flags=re.S | re.I)
    visible = re.sub(r'<[^>]+>', ' ', visible)
    for m in DELIVERY_RE.finditer(visible):
        w = m.group(1).lower()
        w = 'delivery' if w.startswith('deliver') else w
        if w not in out['delivery']:
            out['delivery'].append(w)
    out['order_online'] = bool(ORDER_ONLINE_RE.search(visible))
    return out


def from_social_url(url: str) -> dict:
    """A 'website' that is really a social profile: read the handle from the URL, never fetch it."""
    return extract(f'<a href="{url}"></a>')


class Fetcher:
    def __init__(self, cache_dir, contact: str, log):
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.log = log
        self.ua = f'lagosdata/{__version__} (small local business directory; {contact or "no contact set"})'
        self.robots: dict[str, urllib.robotparser.RobotFileParser | None] = {}
        self.lock = threading.Lock()
        self.robots_skips: list[str] = []

    def _cache(self, url):
        return self.cache_dir / (hashlib.sha1(url.encode()).hexdigest() + '.json')

    def _get(self, url) -> tuple[int, str, str]:
        c = self._cache(url)
        if c.exists():
            d = json.loads(c.read_text())
            return d['status'], d['text'], d.get('final', url)
        try:
            with requests.get(url, timeout=TIMEOUT, stream=True, allow_redirects=True,
                              headers={'User-Agent': self.ua, 'Accept': 'text/html,*/*'}) as r:
                ctype = r.headers.get('content-type', '')
                body = b''
                if 'html' in ctype or 'text' in ctype or not ctype:
                    for chunk in r.iter_content(65536):
                        body += chunk
                        if len(body) > MAX_BYTES:
                            break
                status, final = r.status_code, r.url
                text = body.decode(r.encoding or 'utf-8', errors='replace')
        except Exception as e:  # noqa: BLE001
            status, text, final = 0, f'{type(e).__name__}', url
        c.write_text(json.dumps({'status': status, 'text': text if status == 200 else '', 'final': final}))
        return status, (text if status == 200 else ''), final

    def allowed(self, url) -> bool:
        p = urlparse(url)
        base = f'{p.scheme}://{p.netloc}'
        if base not in self.robots:
            st, txt, _ = self._get(base + '/robots.txt')
            if st == 200:
                rp = urllib.robotparser.RobotFileParser()
                rp.parse(txt.splitlines())
                self.robots[base] = rp
            else:
                self.robots[base] = None          # no robots.txt (or unreachable): allowed
        rp = self.robots[base]
        ok = rp is None or rp.can_fetch(self.ua, url)
        if not ok:
            with self.lock:
                self.robots_skips.append(url)
            self.log.event('robots_skip', f'robots.txt disallows {url}', url=url)
        return ok

    def page(self, url) -> tuple[str, str]:
        if not self.allowed(url):
            return '', url
        st, text, final = self._get(url)
        self.log.event('http', '', method='GET', url=url, status=st)
        return text, final


def crawl_site(fetcher: Fetcher, website: str) -> dict | None:
    """Homepage + up to 3 contact-ish paths on the same host. None if nothing could be read."""
    url = website if website.startswith('http') else 'http://' + website
    host = urlparse(url).netloc.lower()
    if any(host == h or host.endswith('.' + h) for h in SOCIAL_HOSTS):
        return from_social_url(url)
    home, final = fetcher.page(url)
    if not home:
        return None
    merged = extract(home)
    base = f'{urlparse(final).scheme}://{urlparse(final).netloc}'
    fetched = 0
    for path in PATHS:
        if fetched >= 3:
            break
        u = urljoin(base, path)
        if urlparse(u).netloc != urlparse(final).netloc:
            continue
        html, _ = fetcher.page(u)
        if not html:
            continue
        fetched += 1
        x = extract(html)
        if path in ('/order', '/delivery'):
            x['order_online'] = x['order_online'] or path == '/order'
        for k, v in x.items():
            if isinstance(v, list):
                merged[k] += [i for i in v if i not in merged[k]]
            elif v:
                merged[k] = v
    return merged


def apply(b, found: dict, used_phones: set):
    """Fold crawl results into a Business. Site phones never displace a listing phone, and never
    become a primary phone already used by another record (a chain's head-office number)."""
    def first(lst): return lst[0] if lst else ''
    if not b.email and found['emails']:
        b.email = '; '.join(found['emails'][:3])
    for k in ('instagram', 'facebook', 'twitter', 'linkedin', 'tiktok'):
        if not getattr(b, k) and found[k]:
            setattr(b, k, first(found[k]))
    if not b.whatsapp and found['whatsapp']:
        b.whatsapp = first(found['whatsapp'])
    phones = [p for p in (b.phones_all.split('; ') if b.phones_all else []) + found['phones'] if p]
    b.phones_all = '; '.join(dict.fromkeys(([b.phone] if b.phone else []) + phones))
    if not b.phone:
        for p in found['phones']:
            if p not in used_phones:
                b.phone = p
                used_phones.add(p)
                break
    for s in found['delivery']:
        if s not in b.delivery_text_signals:
            b.delivery_text_signals.append(s)
    if found['order_online'] and 'online ordering' not in b.delivery_text_signals:
        b.delivery_text_signals.append('online ordering')


def enrich(run, recs):
    cfg = run.cfg.sources.site_contacts
    from ..record import CORE_ZONE, count_channels
    targets = [b for b in recs if b.website]
    targets.sort(key=lambda b: (b.zone != CORE_ZONE, -(b.reviews if isinstance(b.reviews, int) else 0)))
    targets = targets[:cfg.max_sites]
    fetcher = Fetcher(run.dir / 'cache' / 'sites', run.cfg.sources.directories.contact_email, run.log)
    by_host: dict[str, list] = {}
    for b in targets:
        by_host.setdefault(urlparse(b.website if '//' in b.website else '//' + b.website).netloc.lower(),
                           []).append(b)
    results: dict[int, dict | None] = {}

    def do_host(items):                        # serial within a host
        for b in items:
            results[id(b)] = crawl_site(fetcher, b.website)
    with ThreadPoolExecutor(max_workers=cfg.concurrency) as ex:
        list(ex.map(do_host, by_host.values()))
    used = {b.phone for b in recs if b.phone}
    read = 0
    for b in targets:
        found = results.get(id(b))
        if found:
            read += 1
            apply(b, found, used)
            b.contact_channels = count_channels(b)
    run.log.event('stage', f'site_contacts: {len(targets)} websites, {read} readable, '
                  f'{len(fetcher.robots_skips)} pages skipped by robots.txt')
    run.update_manifest(robots_skips={'site_contacts': fetcher.robots_skips[:500]})
    return recs
