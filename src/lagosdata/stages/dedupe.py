"""dedupe: key-cascade merge, non-business POI filter, magazine priority."""
from __future__ import annotations

import csv

from ..merge import assign_priority, dedupe as dedupe_records, drop_pois, sort_key
from ..record import count_channels


def dedupe(run) -> dict:
    recs = run.read_stage('classify')
    n_in = len(recs)
    kept, decisions = dedupe_records(recs)
    kept, dropped = drop_pois(kept)
    for d in dropped:
        run.log.event('poi_drop', f'dropped non-business POI "{d["name"]}": {d["reason"]}', **d)
    for r in kept:
        r.contact_channels = count_channels(r)
        if run.cfg.pipeline == 'magazine':
            assign_priority(r, run.cfg.core_areas)
    kept.sort(key=sort_key)
    if run.options.get('dedupe_report'):
        path = run.dir / 'dedupe_report.csv'
        cols = ['action', 'key', 'key_value', 'kept_name', 'kept_source', 'merged_name', 'merged_source',
                'kept_addr', 'merged_addr', 'reason', 'name', 'source']
        with open(path, 'w', newline='', encoding='utf-8') as fh:
            w = csv.DictWriter(fh, fieldnames=cols, extrasaction='ignore')
            w.writeheader()
            w.writerows(decisions)
        run.log.event('stage', f'dedupe report written: {path}')
    merges = sum(1 for d in decisions if d['action'] == 'merged')
    conflicts = sum(len(r.conflicts) for r in kept)
    run.write_stage('dedupe', kept)
    run.log.event('stage', f'dedupe: {n_in} in, {merges} merged, {len(dropped)} non-business POIs dropped, '
                  f'{len(kept)} kept, {conflicts} field conflicts recorded')
    return {'in': n_in, 'merged': merges, 'poi_dropped': len(dropped), 'kept': len(kept), 'conflicts': conflicts}
