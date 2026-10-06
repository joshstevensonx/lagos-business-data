# -*- coding: utf-8 -*-
"""Delivery Potential scoring for Lagos restaurant / supermarket / pharmacy prospects.

Score is 0-100. It is a ranking aid, not a measurement: Google has no
"does large deliveries" field, so this combines the signals that do exist.
Every component is written to the workbook so the client can see the reasoning.
"""
import re, math, collections

CHAIN_HINTS = [
    'shoprite','spar','ebeano','justrite','market square','addide','hubmart','prince ebeano',
    'grocery bazaar','next cash','game','blenco','everyday','citydia','foodco','marketsquare',
    'medplus','healthplus','alpha pharmacy','juli pharmacy','nett pharmacy','emzor','h medix',
    'chicken republic','kfc','domino','cold stone','the place','mr bigg','tantalizers','sweet sensation',
    'burger king','krispy kreme','coldstone','genesis','ntachi osa','iya eba','food concepts',
    'shawarma','chowdeck','jumia','glovo',
]

def _flag(rec, path):
    """additionalInfo arrives as {"Service options":[{"Delivery":true},...]} - a dict of
    lists of single-key objects - so dot-notation lookups silently miss. Handle both."""
    if path in rec:                       # already-flattened form
        v = rec[path]
        return bool(v) if not isinstance(v, str) else v.strip().lower() not in ('', 'no', 'false')
    if path.startswith('additionalInfo.'):
        _, group, key = path.split('.', 2)
        ai = rec.get('additionalInfo') or {}
        for entry in (ai.get(group) or []):
            if isinstance(entry, dict) and key in entry:
                return bool(entry[key])
    return False

def category_of(rec):
    blob = ((rec.get('categoryName') or '') + ' ' + ' '.join(rec.get('categories') or []) + ' ' +
            (rec.get('title') or '')).lower()
    if re.search(r'pharmac|chemist|drug ?store', blob): return 'Pharmacy'
    if re.search(r'supermarket|grocer|provision|mini ?mart|hypermarket|convenience|food store|market', blob):
        return 'Supermarket / Grocery'
    if re.search(r'restaurant|fast food|buka|canteen|eatery|cafe|food|bakery|pizza|chicken|shawarma|grill|'
                 r'diner|bistro|kitchen|takeaway|caterer', blob):
        return 'Restaurant / Food'
    return 'Other'

def contact_channels(rec):
    ch = {}
    ph = rec.get('phoneUnformatted') or rec.get('phone') or ''
    extra = [p for p in (rec.get('phones') or []) if p]
    ch['phone'] = ph or (extra[0] if extra else '')
    ch['phones_all'] = '; '.join(dict.fromkeys([p for p in ([ph] + extra) if p]))
    ch['website'] = rec.get('website') or ''
    ch['email'] = '; '.join(rec.get('emails') or [])
    ch['instagram'] = '; '.join(rec.get('instagrams') or [])
    ch['facebook'] = '; '.join(rec.get('facebooks') or [])
    ch['linkedin'] = '; '.join(rec.get('linkedIns') or [])
    ch['twitter'] = '; '.join(rec.get('twitters') or [])
    ch['tiktok'] = '; '.join(rec.get('tiktoks') or [])
    ch['count'] = sum(1 for k in ('phone','website','email','instagram','facebook','linkedin')
                      if ch.get(k))
    return ch

def score(rec, name_counts):
    """Return (score 0-100, dict of component contributions)."""
    c = {}
    cat = category_of(rec)

    # --- explicit delivery signals from Google -----------------------------
    c['Google Delivery flag'] = 25 if _flag(rec, 'additionalInfo.Service options.Delivery') else 0
    c['No-contact delivery'] = 5 if _flag(rec, 'additionalInfo.Service options.No-contact delivery') else 0
    c['Takeout'] = 5 if _flag(rec, 'additionalInfo.Service options.Takeout') else 0
    c['Delivery hours published'] = 5 if rec.get('additionalOpeningHours.Delivery.hours') or \
                                        rec.get('additionalOpeningHours.Delivery.day') else 0
    # catering is the strongest proxy for genuinely large orders
    c['Catering offered'] = 15 if _flag(rec, 'additionalInfo.Dining options.Catering') else 0

    # --- volume proxy -------------------------------------------------------
    try: rc = int(rec.get('reviewsCount') or 0)
    except Exception: rc = 0
    c['Order-volume proxy (reviews)'] = min(25, round(math.log10(rc + 1) * 9, 1)) if rc else 0

    # --- commercial sophistication -----------------------------------------
    c['Has website'] = 8 if rec.get('website') else 0
    c['Online ordering / menu'] = 7 if (rec.get('googleFoodUrl') or rec.get('menu') or
                                        rec.get('servicesLink')) else 0

    # --- scale --------------------------------------------------------------
    nm = re.sub(r'[^a-z0-9]+', ' ', (rec.get('title') or '').lower()).strip()
    is_chain = any(h in nm for h in CHAIN_HINTS) or name_counts.get(nm, 0) > 1
    c['Chain / multi-branch'] = 10 if is_chain else 0

    c['Category weight'] = {'Supermarket / Grocery': 10, 'Restaurant / Food': 6, 'Pharmacy': 4}.get(cat, 0)

    try: ts = float(rec.get('totalScore') or 0)
    except Exception: ts = 0
    c['Rating 4.0+'] = 5 if ts >= 4.0 else 0

    total = min(100, round(sum(c.values()), 1))
    return total, c, cat

def band(s):
    if s >= 60: return 'Hot - approach first'
    if s >= 40: return 'Warm - worth a call'
    if s >= 25: return 'Cool - lower priority'
    return 'Cold - little evidence of delivery'

def build_name_counts(records):
    cnt = collections.Counter()
    for r in records:
        nm = re.sub(r'[^a-z0-9]+', ' ', (r.get('title') or '').lower()).strip()
        if nm: cnt[nm] += 1
    return cnt

COMPONENTS = ['Google Delivery flag','No-contact delivery','Takeout','Delivery hours published',
              'Catering offered','Order-volume proxy (reviews)','Has website','Online ordering / menu',
              'Chain / multi-branch','Category weight','Rating 4.0+']
