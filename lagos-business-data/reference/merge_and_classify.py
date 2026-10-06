# -*- coding: utf-8 -*-
"""Merge the v2 master (930 records, 2 catchments) with the new 7-area sweep
(4,446 records), classify everything into the 30-group / 436-subcategory tree,
dedupe, and emit master_v3.json."""
import json, re, math, unicodedata, collections, sys
sys.path.insert(0, '.')
from classify import classify

TODAY = "2026-09-21"

AREA_NAMES = {'A':'Anthony / Anthony Village','M':'Maryland / Mende','I':'Ilupeju',
              'G':'Gbagada','O':'Obanikoro','P':'Palmgrove','J':'Ojota'}
CENTROIDS = {'Anthony / Anthony Village':(6.55982,3.36915),'Maryland / Mende':(6.57229,3.36717),
             'Ilupeju':(6.54548,3.35989),'Gbagada':(6.55144,3.38653),'Obanikoro':(6.54773,3.36824),
             'Palmgrove':(6.53952,3.36767),'Ojota':(6.58282,3.38447)}
CORE = ('Anthony / Anthony Village','Maryland / Mende')

# ---------------------------------------------------------------- helpers ---
def norm_name(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode().lower()
    s = re.sub(r'\b(ltd|limited|nig|nigeria|plc|enterprises|enterprise|ventures|venture|'
               r'company|co|and|the|services|service|int\'l|international|global)\b', ' ', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return re.sub(r'\s+', ' ', s)

def norm_addr(s):
    s = unicodedata.normalize('NFKD', s or '').encode('ascii','ignore').decode().lower()
    s = re.sub(r'\b(street|st|road|rd|avenue|ave|close|cl|crescent|cres|drive|dr|lane|ln|'
               r'way|estate|est|shop|suite|plot|block|flat|no)\b', ' ', s)
    s = re.sub(r'[^a-z0-9]+', ' ', s).strip()
    return re.sub(r'\s+', ' ', s)

def clean_phone(p):
    if not p: return ''
    raw = str(p)
    for m in re.finditer(r'(?:\+?234|0)[\s\-]?([789]\d{2}[\s\-]?\d{3}[\s\-]?\d{4})', raw):
        d = re.sub(r'\D','', m.group(1))
        if len(d) == 10: return '+234' + d
    d = re.sub(r'\D','', raw)
    if d.startswith('0') and len(d) >= 11 and d[1] in '789':
        return '+234' + d[1:11]
    if d.startswith('234'):
        rest = d[3:]
        if rest[:1] in ('7','8','9') and len(rest) >= 10:      # mobile
            return '+234' + rest[:10]
        if rest[:1] == '1' and 8 <= len(rest) <= 9:            # Lagos landline
            return '+234' + rest
    if d.startswith('01') and 9 <= len(d) <= 10:
        return '+234' + d[1:]
    return ''

def street_of(addr):
    a = (addr or '').split(',')[0].strip()
    a = re.sub(r'^(shop|suite|plot|block|flat|no\.?)\s*[\w/]*\s*,?\s*', '', a, flags=re.I)
    return a[:60]

def nearest_area(la, lo):
    best, bd = None, 1e9
    for k,(cla,clo) in CENTROIDS.items():
        d = math.hypot((la-cla)*110.57, (lo-clo)*110.32*math.cos(math.radians(cla)))
        if d < bd: bd, best = d, k
    return best, bd

records = []

# ------------------------------------------------- 1. existing v2 master ----
for r in json.load(open('master_records.json')):
    la = r['lat'] if r['lat'] else None
    lo = r['lng'] if r['lng'] else None
    area = r['area']
    if la and lo:
        a2, d = nearest_area(la, lo)
        if d <= 1.6: area = a2
    records.append(dict(
        name=r['name'], area=area, street=r['street'], label=r['legacy_cat'],
        addr=r['addr'], phone=clean_phone(r['phone']), website=r['website'], maps=r['maps'],
        rating=r['rating'], reviews=r['reviews'], lat=la or '', lng=lo or '',
        source=r['source'], added=r.get('added') or '2026-09-16',
        sales=r.get('sales') or 'Not Contacted', notes=r.get('notes') or '',
        legacy18=r['cat']))

# ------------------------------------------------- 2. new 7-area sweep ------
for n, lab, addr, ph, rt, rc, la, lo, ac in json.load(open('sweep_rows.json')):
    if re.match(r'^[\d.]+\(', lab or '') or (addr or '').startswith('₦'):
        lab, addr = '', ''
    records.append(dict(
        name=n.strip(), area=AREA_NAMES[ac], street=street_of(addr), label=lab,
        addr=addr, phone=clean_phone(ph), website='', maps='',
        rating=rt or '', reviews=rc or '', lat=float(la), lng=float(lo),
        source='Google Maps (area sweep, Sep 2026)', added=TODAY,
        sales='Not Contacted', notes='', legacy18=''))

print('raw records:', len(records))

# ------------------------------------------------- 3. classify -------------
for r in records:
    g, s = classify(r['label'], r['name'])
    r['group'], r['sub'] = g, s
    if not r['street']: r['street'] = street_of(r['addr'])

# ------------------------------------------------- 4. dedupe ---------------
by_key, order = {}, []
for r in records:
    nn = norm_name(r['name'])
    if not nn: continue
    keys = []
    if r['phone']: keys.append(('p', r['phone']))
    keys.append(('na', nn + '|' + norm_addr(r['addr'])[:40]))
    keys.append(('n', nn))
    hit = next((by_key[k] for k in keys if k in by_key), None)
    if hit is None:
        order.append(r)
        for k in keys: by_key[k] = r
    else:
        for f in ('phone','website','maps','rating','reviews','lat','lng','addr','street','label','legacy18'):
            if not hit[f] and r[f]: hit[f] = r[f]
        if hit['source'] != r['source'] and 'multi' not in hit['source']:
            hit['source'] = 'Multiple sources (cross-verified)'
        for k in keys: by_key.setdefault(k, hit)

# drop map POIs that are not businesses (bus stops, bare street names)
NOT_A_BUSINESS = re.compile(r'\b(bus ?stop|busstop|bus-stop|roundabout|flyover|under ?bridge)\b', re.I)
def is_poi(r):
    n = (r['name'] or '').strip()
    if NOT_A_BUSINESS.search(n) and not r['label']: return True
    if not r['label'] and re.search(r'\b(street|crescent|close|avenue|road)\s*$', n, re.I): return True
    return False
dropped_poi = [r for r in order if is_poi(r)]
order = [r for r in order if not is_poi(r)]
print('dropped non-business map POIs:', len(dropped_poi))
print('after dedupe:', len(order))

# ------------------------------------------------- 5. scoring --------------
for r in order:
    try: rc = int(r['reviews']) if str(r['reviews']).strip() not in ('','None') else 0
    except Exception: rc = 0
    has_phone = bool(r['phone'])
    core = r['area'] in CORE
    if has_phone and core and (rc >= 10 or r['website']):
        r['priority'], r['package'] = 'A - High commercial relevance', 'Premium'
    elif has_phone and (core or rc >= 25):
        r['priority'], r['package'] = 'B - Potential advertiser', 'Standard'
    elif has_phone:
        r['priority'], r['package'] = 'C - Ring area, contactable', 'Listing'
    else:
        r['priority'], r['package'] = 'D - Listing only (no contact yet)', 'Listing'
    r['contactable'] = 'Yes' if has_phone else 'No'
    r['verification'] = 'Google-verified' if r['lat'] else 'Directory listing only'
    r['zone'] = 'Core catchment' if core else 'Ring area'

order.sort(key=lambda r: (0 if r['area'] in CORE else 1, r['area'], r['group'], r['sub'], r['name'].lower()))

print(collections.Counter(r['area'] for r in order))
print(collections.Counter(r['group'] for r in order).most_common())
print('subcategories used:', len(set((r['group'],r['sub']) for r in order)))
print('with phone:', sum(1 for r in order if r['phone']))
print('priority:', collections.Counter(r['priority'][:1] for r in order))
json.dump(order, open('master_v3.json','w'))
