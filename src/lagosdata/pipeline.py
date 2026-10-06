"""Stage orchestration (SPEC §2.1).

    discover -> geo -> classify -> dedupe -> enrich -> score -> report -> verify

Deliberate deviation from the spec's listed order (which puts dedupe after score):
dedupe runs before enrich and score so that (a) the enrichment budgets
(max_sites, max_place_visits) are spent once per business rather than once per
cross-source duplicate, and (b) score.py's chain detection, which counts how
often a name occurs in the dataset, is not fooled into calling a business a
chain because two sources both listed it.

Each stage reads the previous stage's artifact from disk, so any stage can be
re-run alone. Derived stages are cheap and deterministic and always re-run;
discover skips every search already marked done.
"""
from __future__ import annotations

import time

from .stages.classify import classify
from .stages.dedupe import dedupe
from .stages.discover import discover
from .stages.enrich import enrich
from .stages.geo import geo
from .stages.report import report
from .stages.scoring import score
from .stages.verify import format_summary, verify

STAGES = ['discover', 'geo', 'classify', 'dedupe', 'enrich', 'score', 'report', 'verify']
FUNCS = {'discover': discover, 'geo': geo, 'classify': classify, 'dedupe': dedupe,
         'enrich': enrich, 'score': score, 'report': report}


def run_stages(run, stages: list[str] | None = None, **discover_kw) -> bool:
    stages = stages or STAGES
    unknown = [s for s in stages if s not in STAGES]
    if unknown:
        raise ValueError(f'unknown stages {unknown}; choose from {STAGES}')
    ok = True
    for name in STAGES:
        if name not in stages:
            continue
        t0 = time.time()
        if name == 'verify':
            ok, checks = verify(run)
            for c in checks:
                print(f'  [{"PASS" if c.ok else "FAIL"}] {c.name}: {c.detail}')
            import json
            print(format_summary(json.loads((run.dir / 'verify_report.json').read_text())['summary']))
            result = {'ok': ok, 'failed': [c.name for c in checks if not c.ok]}
        else:
            result = FUNCS[name](run, **(discover_kw if name == 'discover' else {}))
        secs = round(time.time() - t0, 2)
        run.state.stage_done(name, str(result)[:500])
        run.update_manifest(**{name: result}, timings={name: secs})
        run.log.event('stage_done', f'{name} done in {secs}s', stage=name, result=result)
        if name == 'discover' and run.stop.requested:
            print('Stopped cleanly after discover; re-run the same command (or `lagosdata resume`) to continue.')
            return True
    return ok
