"""Area geometry and geo-assignment (SPEC §4).

Never trust Google's geocoding of informal Lagos area names: records are assigned
from their own coordinates. Areas are discs (centroid + radius), corridors (a strip
along a segment, e.g. Lekki-Epe to Ajah) or polygons.
"""
from __future__ import annotations

import math
import re

from .config import AreaDef
from .record import CORE_ZONE, OUTSIDE, RING_ZONE, UNASSIGNED

KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LNG_EQ = 110.32


def dist_km(lat1, lng1, lat2, lng2) -> float:
    # local flat-earth approximation is fine at this scale
    return math.hypot((lat1 - lat2) * KM_PER_DEG_LAT,
                      (lng1 - lng2) * KM_PER_DEG_LNG_EQ * math.cos(math.radians(lat2)))


def _to_xy(lat, lng, lat0):
    return lng * KM_PER_DEG_LNG_EQ * math.cos(math.radians(lat0)), lat * KM_PER_DEG_LAT


def _seg_dist_km(lat, lng, a, b) -> float:
    lat0 = (a[0] + b[0]) / 2
    px, py = _to_xy(lat, lng, lat0)
    ax, ay = _to_xy(a[0], a[1], lat0)
    bx, by = _to_xy(b[0], b[1], lat0)
    dx, dy = bx - ax, by - ay
    L2 = dx * dx + dy * dy
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / L2))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def _in_polygon(lat, lng, poly) -> bool:
    inside = False
    j = len(poly) - 1
    for i in range(len(poly)):
        yi, xi = poly[i]
        yj, xj = poly[j]
        if (yi > lat) != (yj > lat) and lng < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def centre(a: AreaDef) -> tuple[float, float] | None:
    if a.lat is not None:
        return a.lat, a.lng
    if a.corridor:
        f, t = a.corridor.from_, a.corridor.to
        return (f[0] + t[0]) / 2, (f[1] + t[1]) / 2
    if a.polygon:
        return (sum(p[0] for p in a.polygon) / len(a.polygon),
                sum(p[1] for p in a.polygon) / len(a.polygon))
    return None


def distance_and_inside(lat, lng, a: AreaDef) -> tuple[float, bool] | None:
    """(distance used to rank areas, whether the point lies within the area)."""
    if a.radius_km is not None and a.lat is not None:
        d = dist_km(lat, lng, a.lat, a.lng)
        return d, d <= a.radius_km
    if a.corridor:
        d = _seg_dist_km(lat, lng, a.corridor.from_, a.corridor.to)
        return d, d <= a.corridor.width_km / 2
    if a.polygon:
        c = centre(a)
        inside = _in_polygon(lat, lng, a.polygon)
        return (0.0 if inside else dist_km(lat, lng, *c)), inside
    return None


def nearest_area(lat, lng, areas: dict[str, AreaDef]) -> tuple[str | None, float, bool]:
    """Nearest area by its reference distance, and whether the point is inside it (SPEC §4.2)."""
    best, bd, inside = None, 1e9, False
    for name, a in areas.items():
        r = distance_and_inside(lat, lng, a)
        if r is None:
            continue
        d, ins = r
        if d < bd:
            best, bd, inside = name, d, ins
    return best, bd, inside


def _aliases(name: str, a: AreaDef | None) -> list[str]:
    parts = [p.strip() for p in name.split('/') if p.strip()]
    al = parts + list(a.aliases if a else [])
    return sorted(set(al), key=len, reverse=True)


def area_from_address(addr: str, names: list[str], registry: dict[str, AreaDef]) -> str | None:
    """Fallback for records with no coordinates: the area name written in the address."""
    text = addr or ''
    for name in names:
        for al in _aliases(name, registry.get(name)):
            if re.search(r'\b' + re.escape(al) + r'\b', text, re.I):
                return name
    return None


def assign(lat, lng, addr: str, names: list[str], registry: dict[str, AreaDef]) -> tuple[str, float | None]:
    """Return (area, distance_km or None). Area is one of `names`, OUTSIDE or UNASSIGNED."""
    geo = {n: registry[n] for n in names if n in registry and registry[n].has_geometry}
    if lat not in ('', None) and lng not in ('', None) and geo:
        best, d, inside = nearest_area(float(lat), float(lng), geo)
        if best and inside:
            return best, d
        # coordinates put it outside every geometry; an area without geometry can
        # still claim it by name
        by_name = area_from_address(addr, [n for n in names if n not in geo], registry)
        return (by_name or OUTSIDE), d
    # no coordinates, or no configured area has geometry to test them against
    return area_from_address(addr, names, registry) or UNASSIGNED, None


def zone_of(area: str, core: list[str]) -> str:
    if area in (OUTSIDE, UNASSIGNED):
        return area
    return CORE_ZONE if area in core else RING_ZONE


def bbox_for(names: list[str], registry: dict[str, AreaDef], pad_km: float):
    """(south, west, north, east) covering every configured area with geometry, padded."""
    pts = []
    for n in names:
        a = registry.get(n)
        if not a or not a.has_geometry:
            continue
        if a.lat is not None:
            r = a.radius_km
            pts += [(a.lat - r / KM_PER_DEG_LAT, a.lng), (a.lat + r / KM_PER_DEG_LAT, a.lng),
                    (a.lat, a.lng - r / (KM_PER_DEG_LNG_EQ * math.cos(math.radians(a.lat)))),
                    (a.lat, a.lng + r / (KM_PER_DEG_LNG_EQ * math.cos(math.radians(a.lat))))]
        elif a.corridor:
            pts += [tuple(a.corridor.from_), tuple(a.corridor.to)]
        elif a.polygon:
            pts += [tuple(p) for p in a.polygon]
    if not pts:
        return None
    s, n = min(p[0] for p in pts), max(p[0] for p in pts)
    w, e = min(p[1] for p in pts), max(p[1] for p in pts)
    dlat = pad_km / KM_PER_DEG_LAT
    dlng = pad_km / (KM_PER_DEG_LNG_EQ * math.cos(math.radians((s + n) / 2)))
    return round(s - dlat, 5), round(w - dlng, 5), round(n + dlat, 5), round(e + dlng, 5)


def derive_centroids(records, names: list[str], registry: dict[str, AreaDef], min_n: int = 15,
                     google_only: bool = True) -> dict[str, dict]:
    """SPEC §4.1: for each area, the MEDIAN lat/lng of records whose address explicitly
    names it. Median, not mean - robust to the outliers that scattered "Maryland, Ikeja"
    across Ilupeju, Oshodi and Gbagada. Areas with corridor/polygon geometry are skipped
    (their shape is drawn, not derived)."""
    import statistics
    from .record import source_kind
    out = {}
    for name in names:
        a = registry.get(name)
        if a and (a.corridor or a.polygon):
            continue
        pts = []
        for r in records:
            if r.lat in ('', None) or r.lng in ('', None):
                continue
            if google_only and not any(source_kind(s) in ('gmaps', 'places_api') for s in (r.sources_all or [r.source])):
                continue
            if any(re.search(r'\b' + re.escape(al) + r'\b', r.addr or '', re.I) for al in _aliases(name, a)):
                pts.append((float(r.lat), float(r.lng)))
        if not pts:
            out[name] = {'n': 0}
            continue
        out[name] = {'n': len(pts), 'lat': round(statistics.median(p[0] for p in pts), 5),
                     'lng': round(statistics.median(p[1] for p in pts), 5),
                     'low_confidence': len(pts) < min_n}
    return out
