# -*- coding: utf-8 -*-
"""Phone / name / address cleaners and the non-business POI filter.

Ported verbatim from reference/merge_and_classify.py. clean_phone() went through
three corrections (SPEC §6.1) - do not rewrite it; run tests/test_phone.py.
"""
import re
import unicodedata


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

# drop map POIs that are not businesses (bus stops, bare street names)
NOT_A_BUSINESS = re.compile(r'\b(bus ?stop|busstop|bus-stop|roundabout|flyover|under ?bridge)\b', re.I)
def is_poi(r):
    n = (r['name'] or '').strip()
    if NOT_A_BUSINESS.search(n) and not r['label']: return True
    if not r['label'] and re.search(r'\b(street|crescent|close|avenue|road)\s*$', n, re.I): return True
    return False

def poi_reason(r):
    """Why is_poi() would drop this record, for run.log. '' if it is kept."""
    n = (r['name'] or '').strip()
    if NOT_A_BUSINESS.search(n) and not r['label']: return 'transport landmark, no category label'
    if not r['label'] and re.search(r'\b(street|crescent|close|avenue|road)\s*$', n, re.I):
        return 'bare street name, no category label'
    return ''
