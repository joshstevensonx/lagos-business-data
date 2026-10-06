# -*- coding: utf-8 -*-
"""Deduplication and magazine priority assignment.

The key cascade and fill-from-duplicate behaviour are ported from
reference/merge_and_classify.py. Order is load-bearing (SPEC §6.3):

    0. ('pid', place_id)       Google's own identity - beats everything
    1. ('p',  phone)
    2. ('na', norm_name + '|' + norm_addr[:40])
    3. ('n',  norm_name)        most likely to over-merge

Added for the multi-source tool: on conflicting non-empty values prefer the more
trusted source (Places API > Google Maps > OSM > directory > manual CSV) and
record the loser in `conflicts`. Every merge decision is returned so a
--dedupe-report can make over-merges auditable.
"""
from __future__ import annotations

from .areas import dist_km
from .normalise import norm_addr, norm_name, poi_reason
from .record import CORE_ZONE, Business, is_google, trust

FILL_FIELDS = ('phone', 'website', 'maps', 'rating', 'reviews', 'lat', 'lng', 'addr', 'street',
               'label', 'legacy18', 'place_id', 'whatsapp', 'email', 'instagram', 'facebook',
               'twitter', 'linkedin', 'tiktok')
# conflicts on these are noise rather than information
NO_CONFLICT = {'rating', 'reviews', 'maps', 'street', 'label', 'legacy18'}
MULTI = 'Multiple sources (cross-verified)'


def _keys(b: Business) -> list[tuple[str, str]]:
    nn = norm_name(b.name)
    keys = []
    if b.place_id: keys.append(('pid', b.place_id))
    if b.phone: keys.append(('p', b.phone))
    keys.append(('na', nn + '|' + norm_addr(b.addr)[:40]))
    keys.append(('n', nn))
    return keys


def _merge_into(hit: Business, r: Business):
    hit_src = hit.sources_all[0] if hit.sources_all else hit.source
    r_wins = trust(r.source) > trust(hit_src)
    if r_wins and r.lat not in ('', None) and hit.lat not in ('', None):
        moved = dist_km(float(r.lat), float(r.lng), float(hit.lat), float(hit.lng))
        if moved > 0.2:
            hit.conflicts.append({'field': 'lat,lng', 'kept': f'{r.lat},{r.lng}',
                                  'dropped': f'{hit.lat},{hit.lng}', 'dropped_source': hit_src})
        hit.lat, hit.lng = r.lat, r.lng
    for f in FILL_FIELDS:
        hv, rv = getattr(hit, f), getattr(r, f)
        if rv in ('', None):
            continue
        if hv in ('', None):
            setattr(hit, f, rv)
        elif f in ('lat', 'lng'):
            continue
        elif str(hv) != str(rv):
            if r_wins:
                setattr(hit, f, rv)
                loser, loser_src, kept = hv, hit_src, rv
            else:
                loser, loser_src, kept = rv, r.source, hv
            if f not in NO_CONFLICT:
                hit.conflicts.append({'field': f, 'kept': kept, 'dropped': loser, 'dropped_source': loser_src})
    if r_wins:
        # the more trusted record leads provenance (used for later conflict calls)
        hit.sources_all = [r.source] + [s for s in hit.sources_all if s != r.source]
    for s in r.sources_all or [r.source]:
        if s not in hit.sources_all:
            hit.sources_all.append(s)
    if len(set(hit.sources_all)) > 1:
        hit.source = MULTI
    phones = [p for p in (hit.phones_all.split('; ') + r.phones_all.split('; ') + [hit.phone, r.phone]) if p]
    hit.phones_all = '; '.join(dict.fromkeys(phones))
    for s in r.delivery_text_signals:
        if s not in hit.delivery_text_signals:
            hit.delivery_text_signals.append(s)
    for g, entries in (r.additional_info or {}).items():
        hit.additional_info.setdefault(g, entries)


def dedupe(records: list[Business]) -> tuple[list[Business], list[dict]]:
    """Return (kept records, merge decisions)."""
    by_key: dict = {}
    order: list[Business] = []
    decisions: list[dict] = []
    for r in records:
        if not r.sources_all:
            r.sources_all = [r.source]
        if not norm_name(r.name):
            decisions.append({'action': 'dropped', 'reason': 'empty normalised name', 'name': r.name,
                              'source': r.source})
            continue
        keys = _keys(r)
        hit_key = next((k for k in keys if k in by_key), None)
        if hit_key is None:
            order.append(r)
            for k in keys: by_key[k] = r
        else:
            hit = by_key[hit_key]
            decisions.append({'action': 'merged', 'key': hit_key[0], 'key_value': hit_key[1],
                              'kept_name': hit.name, 'kept_source': hit.source,
                              'merged_name': r.name, 'merged_source': r.source,
                              'kept_addr': hit.addr, 'merged_addr': r.addr})
            _merge_into(hit, r)
            for k in _keys(hit) + keys: by_key.setdefault(k, hit)
    return order, decisions


def drop_pois(records: list[Business]) -> tuple[list[Business], list[dict]]:
    kept, dropped = [], []
    for r in records:
        why = poi_reason({'name': r.name, 'label': r.label})
        if why:
            dropped.append({'name': r.name, 'label': r.label, 'source': r.source, 'reason': why})
        else:
            kept.append(r)
    return kept, dropped


def assign_priority(r: Business, core: list[str]):
    """Magazine prospect priority - reference/merge_and_classify.py step 5."""
    try: rc = int(r.reviews) if str(r.reviews).strip() not in ('', 'None') else 0
    except Exception: rc = 0
    has_phone = bool(r.phone)
    is_core = r.area in core
    if has_phone and is_core and (rc >= 10 or r.website):
        r.priority, r.package = 'A - High commercial relevance', 'Premium'
    elif has_phone and (is_core or rc >= 25):
        r.priority, r.package = 'B - Potential advertiser', 'Standard'
    elif has_phone:
        r.priority, r.package = 'C - Ring area, contactable', 'Listing'
    else:
        r.priority, r.package = 'D - Listing only (no contact yet)', 'Listing'
    r.contactable = 'Yes' if has_phone else 'No'
    # the reference marked anything with coordinates Google-verified, because Google was
    # the only coordinate source; OSM now also has coordinates, so check provenance
    if is_google(r):
        r.verification = 'Google-verified'
    elif r.lat not in ('', None):
        r.verification = 'Mapped location (OSM)'
    else:
        r.verification = 'Directory listing only'


def sort_key(r: Business):
    return (0 if r.zone == CORE_ZONE else 1, r.area, r.group, r.sub, r.name.lower())
