"""--import-csv: hand-collected records through the same normalise/classify/dedupe path (SPEC §3.6).

Josh walks these areas and will have businesses no scraper finds. Column names
are matched loosely (case/spacing-insensitive, common synonyms). Each file is
one "search" keyed by name + content hash, so re-importing an unchanged file is
a no-op and an edited file is imported afresh.
"""
from __future__ import annotations

import csv
import hashlib
from datetime import date
from pathlib import Path

from ..normalise import clean_phone, street_of
from ..record import Business
from .base import Search, Source

SYNONYMS = {
    'name': ['name', 'business name', 'business', 'company'],
    'phone': ['phone', 'phone number', 'telephone', 'tel', 'mobile', 'contact', 'phones'],
    'addr': ['address', 'full address', 'addr', 'location'],
    'label': ['category', 'type', 'label', 'business type', 'source category'],
    'website': ['website', 'web', 'url', 'site'],
    'email': ['email', 'e-mail', 'mail'],
    'whatsapp': ['whatsapp', 'wa'],
    'instagram': ['instagram', 'ig'],
    'facebook': ['facebook', 'fb'],
    'lat': ['lat', 'latitude'],
    'lng': ['lng', 'lon', 'long', 'longitude'],
    'notes': ['notes', 'note', 'comments', 'sales notes'],
    'sales_status': ['sales status', 'status'],
}


def _norm(h: str) -> str:
    return ' '.join((h or '').lower().replace('_', ' ').split())


def _float(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return ''


class CsvImportSource(Source):
    name = 'manual_csv'

    def files(self) -> list[Path]:
        return [Path(p) for p in self.run.options.get('import_csv') or []]

    def plan(self) -> list[Search]:
        out = []
        for p in self.files():
            digest = hashlib.sha1(p.read_bytes()).hexdigest()[:10]
            out.append(Search(term=f'csv:{p.name}:{digest}', area=str(p)))
        return out

    def search(self, s: Search) -> list[dict]:
        p = Path(s.area)
        with open(p, newline='', encoding='utf-8-sig') as fh:
            rows = list(csv.DictReader(fh))
        today = date.today().isoformat()
        return [{**r, '_file': p.name, '_fetched': today} for r in rows]

    def to_business(self, raw: dict) -> Business | None:
        cols = {_norm(k): v for k, v in raw.items() if not k.startswith('_')}

        def get(field):
            for syn in SYNONYMS[field]:
                if (cols.get(syn) or '').strip():
                    return cols[syn].strip()
            return ''
        name = get('name')
        if not name:
            return None
        phones = [clean_phone(x) for x in get('phone').replace('/', ';').replace(',', ';').split(';')]
        phones = list(dict.fromkeys(p for p in phones if p))
        src = f'Manual CSV ({raw.get("_file", "import")})'
        return Business(
            name=name, addr=get('addr'), street=street_of(get('addr')), label=get('label'),
            phone=phones[0] if phones else '', phones_all='; '.join(phones),
            whatsapp=clean_phone(get('whatsapp')), website=get('website'), email=get('email'),
            instagram=get('instagram'), facebook=get('facebook'),
            lat=_float(get('lat')), lng=_float(get('lng')), notes=get('notes'),
            sales_status=get('sales_status') or 'Not Contacted',
            source=src, sources_all=[src], added=raw.get('_fetched') or date.today().isoformat())
