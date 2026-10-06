"""discover: execute every planned search not already done; append raw rows immediately."""
from __future__ import annotations

from ..sources import IMPLEMENTED, ORDER
from ..sources.base import SourceAborted, SourceUnavailable


def enabled_sources(run) -> list[str]:
    cfg = run.cfg.sources
    names = [n for n in ORDER if getattr(cfg, n).enabled]
    if run.options.get('import_csv'):
        names.append('manual_csv')
    return names


def make_source(run, name: str):
    kw = run.options.get('source_kwargs', {}).get(name, {})
    return IMPLEMENTED[name](run, **kw)


class Recorder:
    """The single place search outcomes reach state.sqlite and raw/*.jsonl. Batch
    sources call it from their (single-threaded asyncio) loop as each search lands,
    so a crash loses at most the in-flight searches."""

    def __init__(self, run, source: str, summary: dict):
        self.run, self.source, self.summary = run, source, summary

    def started(self, s):
        self.run.state.start(self.source, s.term, s.area)

    def done(self, s, rows: list[dict]):
        for r in rows:
            r['_search'] = {'source': self.source, 'term': s.term, 'area': s.area}
        self.run.append_raw(self.source, rows)
        self.run.state.finish(self.source, s.term, s.area, len(rows))
        self.run.log.event('search', f'{self.source} "{s.term}" @ {s.area}: {len(rows)} raw',
                           source=self.source, term=s.term, area=s.area, raw_count=len(rows))
        self.summary['searched'] += 1
        self.summary['raw_rows'] += len(rows)

    def failed(self, s, err: str, status: str = 'error'):
        self.run.state.fail(self.source, s.term, s.area, err, status=status)
        self.run.log.event('search_error', f'{self.source} "{s.term}" @ {s.area}: {err}',
                           source=self.source, term=s.term, area=s.area)
        self.summary['failed'] += 1

    def released(self, s):
        """An in-flight search abandoned by a stop/abort: it never completed, so it stays pending."""
        self.run.state.fail(self.source, s.term, s.area, 'interrupted before completion', status='pending')


def discover(run, only_area: str | None = None, only_term: str | None = None) -> dict:
    summary = {'searched': 0, 'skipped_done': 0, 'failed': 0, 'raw_rows': 0, 'sources_not_built': [],
               'aborted': []}
    for name in enabled_sources(run):
        if name not in IMPLEMENTED:
            summary['sources_not_built'].append(name)
            run.log.event('skip', f'{name}: enabled in config but not built yet - skipped', source=name)
            continue
        src = make_source(run, name)
        todo = []
        for s in src.plan():
            if only_area and only_area not in s.area:
                continue
            if only_term and only_term != s.term:
                continue
            if run.state.is_done(name, s.term, s.area):
                summary['skipped_done'] += 1
                continue
            todo.append(s)
        if not todo:
            continue
        rec = Recorder(run, name, summary)
        if hasattr(src, 'search_many'):
            try:
                src.search_many(todo, rec)
            except SourceAborted as e:
                summary['aborted'].append(name)
                run.log.event('source_aborted', f'{name} ABORTED: {e}', source=name)
            continue
        for s in todo:
            if run.stop.requested:
                run.log.event('stop', 'clean shutdown requested; stopping before the next search')
                return summary
            rec.started(s)
            try:
                rows = src.search(s)
            except SourceUnavailable as e:
                rec.failed(s, str(e))
                run.log.event('source_unavailable', f'{name} unreachable, continuing without it: {e}',
                              source=name)
                break
            except Exception as e:  # noqa: BLE001 - one bad search never aborts a run
                rec.failed(s, f'{type(e).__name__}: {e}')
                continue
            rec.done(s, rows)
    return summary
