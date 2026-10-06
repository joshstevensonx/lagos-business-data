"""discover: execute every planned search not already done; append raw rows immediately."""
from __future__ import annotations

from ..sources import IMPLEMENTED, ORDER
from ..sources.base import SourceUnavailable


def enabled_sources(run) -> list[str]:
    cfg = run.cfg.sources
    return [n for n in ORDER if getattr(cfg, n).enabled]


def make_source(run, name: str):
    kw = run.options.get('source_kwargs', {}).get(name, {})
    return IMPLEMENTED[name](run, **kw)


def discover(run, only_area: str | None = None, only_term: str | None = None) -> dict:
    summary = {'searched': 0, 'skipped_done': 0, 'failed': 0, 'raw_rows': 0, 'sources_not_built': []}
    if run.cfg.sources.gmaps_browser.enabled and 'gmaps_browser' in IMPLEMENTED:
        run.log.event('notice', 'Google Maps source enabled: it reads public listing pages. Keep volumes low '
                      '(rate_limit, concurrency, max_searches); it never solves CAPTCHAs.', source='gmaps_browser')
    for name in enabled_sources(run):
        if name not in IMPLEMENTED:
            summary['sources_not_built'].append(name)
            run.log.event('skip', f'{name}: enabled in config but not built yet - skipped', source=name)
            continue
        src = make_source(run, name)
        for s in src.plan():
            if run.stop.requested:
                run.log.event('stop', 'clean shutdown requested; stopping before the next search')
                return summary
            if only_area and only_area not in s.area:
                continue
            if only_term and only_term != s.term:
                continue
            if run.state.is_done(name, s.term, s.area):
                summary['skipped_done'] += 1
                continue
            run.state.start(name, s.term, s.area)
            try:
                rows = src.search(s)
            except SourceUnavailable as e:
                run.state.fail(name, s.term, s.area, str(e))
                run.log.event('source_unavailable', f'{name} unreachable, continuing without it: {e}',
                              source=name, term=s.term, area=s.area)
                summary['failed'] += 1
                break
            except Exception as e:  # noqa: BLE001 - one bad search never aborts a run
                run.state.fail(name, s.term, s.area, f'{type(e).__name__}: {e}')
                run.log.event('search_error', f'{name} "{s.term}" @ {s.area}: {type(e).__name__}: {e}',
                              source=name, term=s.term, area=s.area)
                summary['failed'] += 1
                continue
            for r in rows:
                r['_search'] = {'source': name, 'term': s.term, 'area': s.area}
            run.append_raw(name, rows)
            run.state.finish(name, s.term, s.area, len(rows))
            run.log.event('search', f'{name} "{s.term}" @ {s.area}: {len(rows)} raw',
                          source=name, term=s.term, area=s.area, raw_count=len(rows))
            summary['searched'] += 1
            summary['raw_rows'] += len(rows)
    return summary
