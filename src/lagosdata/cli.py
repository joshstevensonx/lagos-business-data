"""lagosdata command line (SPEC §2.1)."""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

import yaml

from .config import load_config
from .pipeline import STAGES, run_stages
from .run import Run


def _collect_opts(p, resume=False):
    p.add_argument('--osm-via-browser', action='store_true', help='run the Overpass query from a Playwright page')
    p.add_argument('--dedupe-report', action='store_true', help='write every merge decision to dedupe_report.csv')
    p.add_argument('--max-searches', type=int, help='ceiling on Google Maps searches this invocation')
    p.add_argument('--max-runtime', type=int, help='wall-clock ceiling for Google Maps, minutes')
    if not resume:
        p.add_argument('--import-csv', action='append', default=[], metavar='FILE',
                       help='merge a hand-collected CSV through the same pipeline (repeatable)')
        p.add_argument('--top-ups', action='store_true',
                       help='add targeted searches for areas below their gmaps_browser.top_ups floor')


def _common(p):
    p.add_argument('--out', help='output base directory (default: output.dir from config)')
    p.add_argument('--quiet', action='store_true', help='do not echo log events to stderr')


def _options(run, args):
    run.options['dedupe_report'] = getattr(args, 'dedupe_report', False)
    run.options['max_searches'] = getattr(args, 'max_searches', None)
    run.options['max_runtime'] = getattr(args, 'max_runtime', None)
    run.options['top_ups'] = getattr(args, 'top_ups', False)
    csvs = getattr(args, 'import_csv', None) or []
    for c in csvs:
        if not Path(c).is_file():
            raise SystemExit(f'--import-csv: no such file {c}')
    run.options['import_csv'] = [str(Path(c).resolve()) for c in csvs]
    if getattr(args, 'osm_via_browser', False):
        run.options.setdefault('source_kwargs', {})['osm'] = {'via_browser': True}


def derive_centroids_cmd(args) -> int:
    from .areas import derive_centroids
    cfg, areas, path = load_config(args.config)
    run = Run.open(args.run_id, out_dir=args.out, echo=False)
    try:
        recs = run.read_stage('geo')
    finally:
        run.close()
    res = derive_centroids(recs, cfg.areas, areas.areas, google_only=not args.any_source)
    print(f'{"area":32} {"n":>5}  {"lat":>9} {"lng":>9}  note')
    areas_path = path.parent / cfg.areas_file
    doc = yaml.safe_load(areas_path.read_text()) or {'areas': {}}
    changed = 0
    for name, r in res.items():
        if not r['n']:
            print(f'{name:32} {0:>5}  {"":>9} {"":>9}  no address names this area - unchanged')
            continue
        note = 'LOW CONFIDENCE (<15) - needs human review' if r['low_confidence'] else ''
        print(f'{name:32} {r["n"]:>5}  {r["lat"]:>9} {r["lng"]:>9}  {note}')
        entry = doc['areas'].setdefault(name, {})
        entry.update({'lat': r['lat'], 'lng': r['lng'],
                      'radius_km': entry.get('radius_km') or args.default_radius,
                      'derived_from': f'{r["n"]} records, run {args.run_id}, {date.today().isoformat()}',
                      'low_confidence': r['low_confidence']})
        changed += 1
    if args.write and changed:
        header = ('# Shared area registry. Centroids are DERIVED, never guessed (SPEC §4.1): the median\n'
                  '# position of businesses whose address explicitly names the area. Rewritten by\n'
                  '# `lagosdata derive-centroids --write`.\n')
        areas_path.write_text(header + yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=200))
        print(f'wrote {changed} centroids to {areas_path}')
    elif changed:
        print('dry run - add --write to update', areas_path)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='lagosdata', description='Free-source Lagos business data collector')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('run', help='run the pipeline (default: every stage, verify last)')
    p.add_argument('--config', required=True)
    p.add_argument('--run-id')
    p.add_argument('--stages', help=f'comma-separated subset of {",".join(STAGES)}')
    p.add_argument('--force-term', action='append', default=[], help='redo searches for this term')
    p.add_argument('--force-area', action='append', default=[], help='redo searches for this area')
    _collect_opts(p)
    _common(p)

    p = sub.add_parser('discover', help='run discovery only, optionally for one area/term')
    p.add_argument('--config', required=True)
    p.add_argument('--run-id')
    p.add_argument('--area', help='only searches whose area/viewport label contains this text')
    p.add_argument('--term')
    _collect_opts(p)
    _common(p)

    p = sub.add_parser('derive-centroids', help='median position of records whose address names each area')
    p.add_argument('--config', required=True)
    p.add_argument('--run-id', required=True, help='a run whose geo stage has been built')
    p.add_argument('--out', default='out')
    p.add_argument('--write', action='store_true', help='update the areas file (default: print only)')
    p.add_argument('--any-source', action='store_true', help='also use non-Google records with coordinates')
    p.add_argument('--default-radius', type=float, default=1.3)

    for name, hlp in (('resume', 'continue an interrupted run from its saved config'),
                      ('report', 'rebuild the workbook only'),
                      ('verify', 'recount and check a built workbook')):
        p = sub.add_parser(name, help=hlp)
        p.add_argument('--run-id', required=True)
        p.add_argument('--out', default='out')
        p.add_argument('--quiet', action='store_true')
        if name == 'resume':
            _collect_opts(p, resume=True)

    args = ap.parse_args(argv)
    if args.cmd == 'derive-centroids':
        return derive_centroids_cmd(args)

    if args.cmd in ('run', 'discover'):
        cfg, areas, path = load_config(args.config)
        run = Run.create(cfg, areas, path, run_id=args.run_id, out_dir=args.out, echo=not args.quiet)
    else:
        run = Run.open(args.run_id, out_dir=args.out, echo=not args.quiet)
    _options(run, args)
    run.stop.install()
    print(f'run {run.id} -> {run.dir}')
    try:
        if args.cmd == 'run':
            if args.force_term or args.force_area:
                n = run.state.force(args.force_term, args.force_area)
                run.log.event('force', f'reset {n} searches to pending')
            stages = args.stages.split(',') if args.stages else None
            ok = run_stages(run, stages)
        elif args.cmd == 'discover':
            ok = run_stages(run, ['discover'], only_area=args.area, only_term=args.term)
        elif args.cmd == 'resume':
            ok = run_stages(run, None)
        elif args.cmd == 'report':
            ok = run_stages(run, ['report'])
        else:
            ok = run_stages(run, ['verify'])
    finally:
        run.close()
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
