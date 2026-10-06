"""score: delivery scoring via reference score.py (delivery pipeline only).

The magazine pipeline has no score; its master.json is the enriched record set.
"""
from __future__ import annotations

import collections

from .. import score as S


def score(run) -> dict:
    recs = run.read_stage('enrich')
    out = {'records': len(recs)}
    if run.cfg.delivery_scoring.enabled:
        name_counts = S.name_counts_for(recs)
        for b in recs:
            view = S.apify_view(b)
            total, comps, cat = S.score(view, name_counts)
            b.score, b.score_components, b.delivery_category = total, comps, cat
            b.band = S.band(total)
            # only an enricher that actually checked the place page may claim a full basis
            b.score_basis = S.BASIS_FULL if b.score_basis == S.BASIS_FULL else S.BASIS_FLOOR
        recs.sort(key=lambda r: (-r.score, r.area, r.name.lower()))
        out['bands'] = dict(collections.Counter(r.band for r in recs))
        out['basis'] = dict(collections.Counter(r.score_basis for r in recs))
        run.log.event('stage', f'score: {len(recs)} scored; bands {out["bands"]}; basis {out["basis"]}')
    run.write_master(recs)
    return out
