"""classify: 29-group / 436-subcategory tree plus the legacy 18-category column."""
from __future__ import annotations

import collections

from ..classify import classify as classify_one
from ..record import UNCLASSIFIED, source_kind
from ..taxonomy import normalise as legacy18


def classify(run, source_stage: str = 'geo') -> dict:
    recs = run.read_stage(source_stage)
    for r in recs:
        r.group, r.sub = classify_one(r.label, r.name)
        if (r.group, r.sub) == UNCLASSIFIED and not r.label and source_kind(r.source) == 'directory' and r.notes:
            # directory listings often carry no category, only a tagline/description
            r.group, r.sub = classify_one(r.notes[:160], r.name)
        if not r.legacy18:
            r.legacy18 = legacy18(r.label, r.name)
    run.write_stage('classify', recs)
    unc = [r for r in recs if (r.group, r.sub) == UNCLASSIFIED]
    top = collections.Counter(r.label for r in unc).most_common(20)
    run.log.event('stage', f'classify: {len(recs)} records, {len(unc)} unclassified', top_unclassified=top)
    return {'records': len(recs), 'unclassified': len(unc)}
