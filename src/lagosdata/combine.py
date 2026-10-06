"""Combine finished runs into one MASTER DATABASE (magazine census + delivery prospects).

Records are re-assigned against the union of both pipelines' areas (a business the
magazine's wide sweep saw in Yaba is 'Outside catchment' there but inside a delivery
area here), deduplicated across runs with the same key cascade, re-prioritised, and
tagged with the programme(s) they belong to. Delivery scores are carried through.
"""
from __future__ import annotations

from .areas import assign, zone_of
from .merge import assign_priority, dedupe, sort_key
from .record import OUTSIDE, UNASSIGNED, count_channels
from .run import Run

def combine(run: Run, source_runs: list[Run]) -> dict:
    recs = []
    for src in source_runs:
        recs += src.read_master()
    n_in = len(recs)
    for r in recs:
        r.area, _ = assign(r.lat, r.lng, r.addr, run.cfg.areas, run.areas.areas)
    # delivery-scored records first so their score survives a merge with a census record
    recs.sort(key=lambda r: 0 if r.score != '' else 1)
    kept, decisions = dedupe(recs)
    for r in kept:
        r.zone = zone_of(r.area, run.cfg.core_areas)
        assign_priority(r, run.cfg.core_areas)
        r.contact_channels = count_channels(r)
    kept.sort(key=sort_key)
    run.write_stage('combine', kept)
    run.write_master(kept)
    merged = sum(1 for d in decisions if d['action'] == 'merged')
    inside = sum(1 for r in kept if r.area not in (OUTSIDE, UNASSIGNED))
    run.log.event('stage', f'combine: {n_in} records from {len(source_runs)} runs, {merged} merged across runs, '
                  f'{len(kept)} kept, {inside} inside the 13 areas')
    run.update_manifest(combine={'from': [s.id for s in source_runs], 'in': n_in, 'merged': merged,
                                 'kept': len(kept), 'inside': inside})
    return {'in': n_in, 'merged': merged, 'kept': len(kept), 'inside': inside}
