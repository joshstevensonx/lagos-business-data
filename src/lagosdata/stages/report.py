"""report: build the pipeline's workbook from master.json."""
from __future__ import annotations

import json

from ..workbook import delivery, magazine


def report(run) -> dict:
    recs = run.read_master()
    info = {'today': run.today, 'run_id': run.id,
            'sources_not_built': (run.manifest().get('discover') or {}).get('sources_not_built', [])}
    if run.cfg.run_id_prefix == 'combined':
        info['title'] = f'LAGOS COMBINED MASTER DATABASE - MAGAZINE CENSUS + DELIVERY PROSPECTS ({run.id})'
        info['ring_label'] = ('Ring + delivery areas (5 magazine ring areas and 6 delivery areas: Lekki Ph1, '
                              'Lekki-Ajah, VI, Ikoyi, Yaba, Surulere)')
    builder = magazine if run.cfg.pipeline == 'magazine' else delivery
    wb, meta = builder.build(recs, run.cfg, run.state.searches(), info)
    wb.save(run.workbook_path)
    (run.dir / 'workbook_meta.json').write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    run.log.event('stage', f'report: wrote {run.workbook_path} ({len(recs)} rows)')
    return {'workbook': str(run.workbook_path), 'rows': len(recs)}
