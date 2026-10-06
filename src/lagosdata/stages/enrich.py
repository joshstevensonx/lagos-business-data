"""enrich: site_contacts (SPEC §3.5) and place_pages (§6.4).

Runs after dedupe so the enrichment budget (max_sites, max_place_visits) is spent
once per business, not once per duplicate. Neither enricher is built yet; until
they are, this stage passes records through and says so in run.log.
"""
from __future__ import annotations

ENRICHERS = {}   # name -> callable(run, records) -> records; filled in as they are built


def enrich(run) -> dict:
    recs = run.read_stage('dedupe')
    pending = []
    if run.cfg.sources.site_contacts.enabled:
        pending.append('site_contacts')
    if run.cfg.enrich.place_pages.enabled:
        pending.append('place_pages')
    ran = []
    for name in pending:
        if name in ENRICHERS:
            recs = ENRICHERS[name](run, recs)
            ran.append(name)
        else:
            run.log.event('skip', f'{name}: enabled in config but not built yet - records pass through '
                          'unenriched', enricher=name)
    run.write_stage('enrich', recs)
    return {'records': len(recs), 'ran': ran, 'not_built': [n for n in pending if n not in ran]}
