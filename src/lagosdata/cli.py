"""lagosdata command line (SPEC §2.1)."""
from __future__ import annotations

import argparse
import sys

from .config import load_config
from .pipeline import STAGES, run_stages
from .run import Run


def _common(p):
    p.add_argument('--out', help='output base directory (default: output.dir from config)')
    p.add_argument('--quiet', action='store_true', help='do not echo log events to stderr')


def _options(run, args):
    run.options['dedupe_report'] = getattr(args, 'dedupe_report', False)
    if getattr(args, 'osm_via_browser', False):
        run.options.setdefault('source_kwargs', {})['osm'] = {'via_browser': True}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog='lagosdata', description='Free-source Lagos business data collector')
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('run', help='run the pipeline (default: every stage, verify last)')
    p.add_argument('--config', required=True)
    p.add_argument('--run-id')
    p.add_argument('--stages', help=f'comma-separated subset of {",".join(STAGES)}')
    p.add_argument('--force-term', action='append', default=[], help='redo searches for this term')
    p.add_argument('--force-area', action='append', default=[], help='redo searches for this area')
    p.add_argument('--osm-via-browser', action='store_true', help='run the Overpass query from a Playwright page')
    p.add_argument('--dedupe-report', action='store_true', help='write every merge decision to dedupe_report.csv')
    _common(p)

    p = sub.add_parser('discover', help='run discovery only, optionally for one area/term')
    p.add_argument('--config', required=True)
    p.add_argument('--run-id')
    p.add_argument('--area')
    p.add_argument('--term')
    p.add_argument('--osm-via-browser', action='store_true')
    _common(p)

    for name, hlp in (('resume', 'continue an interrupted run from its saved config'),
                      ('report', 'rebuild the workbook only'),
                      ('verify', 'recount and check a built workbook')):
        p = sub.add_parser(name, help=hlp)
        p.add_argument('--run-id', required=True)
        p.add_argument('--out', default='out')
        p.add_argument('--quiet', action='store_true')
        if name == 'resume':
            p.add_argument('--dedupe-report', action='store_true')
            p.add_argument('--osm-via-browser', action='store_true')

    args = ap.parse_args(argv)

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
