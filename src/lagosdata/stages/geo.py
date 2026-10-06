"""geo: map raw rows to Business records and assign each an area from its coordinates."""
from __future__ import annotations

import collections

from ..areas import assign, zone_of
from ..normalise import street_of
from ..record import OUTSIDE, UNASSIGNED
from ..sources import IMPLEMENTED
from .discover import make_source


def geo(run) -> dict:
    cfg = run.cfg
    out, kept = [], collections.Counter()
    stats = collections.Counter()
    for name in IMPLEMENTED:
        rows = run.read_raw(name)
        if not rows:
            continue
        src = make_source(run, name)
        for raw in rows:
            b = src.to_business(raw)
            if b is None:
                stats['unmappable'] += 1
                continue
            b.area, d = assign(b.lat, b.lng, b.addr, cfg.areas, run.areas.areas)
            b.zone = zone_of(b.area, cfg.core_areas)
            if not b.street:
                b.street = street_of(b.addr)
            if not b.added:
                b.added = run.today
            stats[b.area] += 1
            if b.area not in (OUTSIDE, UNASSIGNED):
                s = raw.get('_search') or {}
                kept[(s.get('source', name), s.get('term', ''), s.get('area', ''))] += 1
            out.append(b)
    no_geom = [a for a in cfg.areas if not (a in run.areas.areas and run.areas.areas[a].has_geometry)]
    if no_geom:
        run.log.event('warn', f'areas without centroids (address-name matching only): {no_geom}; '
                      'run derive-centroids', areas=no_geom)
    run.state.set_kept(dict(kept))
    run.write_stage('geo', out)
    run.log.event('stage', f'geo: {len(out)} records, {stats["unmappable"]} unmappable raw rows dropped '
                  f'(no name), {stats[OUTSIDE]} outside catchment, {stats[UNASSIGNED]} unassigned')
    return {'records': len(out), **stats}
