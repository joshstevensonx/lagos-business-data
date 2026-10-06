"""enrich: site_contacts (SPEC §3.5) and place_pages (§6.4).

Runs after dedupe so the enrichment budget (max_sites, max_place_visits) is spent
once per business, not once per duplicate. Results are merged into the records;
the site crawl is cached by URL and place pages are only revisited for records
not yet marked 'Full', so re-running enrich is cheap.
"""
from __future__ import annotations

from ..enrichers import place_pages, places_api, site_contacts

ENRICHERS = {'place_pages': place_pages.enrich, 'site_contacts': site_contacts.enrich,
             'places_api': places_api.enrich}


def enrich(run) -> dict:
    recs = run.read_stage('dedupe')
    pending = []
    if run.cfg.sources.site_contacts.enabled:
        pending.append('site_contacts')
    if run.cfg.enrich.place_pages.enabled:
        pending.append('place_pages')
    if run.cfg.sources.places_api.enabled:
        pending.append('places_api')
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
