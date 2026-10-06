"""A run's on-disk layout and shared context (SPEC §1.3).

out/<run-id>/
  raw/<source>.jsonl     every record as discovered, untouched, append-only
  stages/<stage>.json    each derived stage's output
  master.json            merged, classified, scored record set (workbook input)
  state.sqlite           resumable search state
  run.log                structured JSONL log
  manifest.json          config snapshot, counts, timings, versions
"""
from __future__ import annotations

import json
import platform
import signal
from datetime import date
from pathlib import Path

import yaml

from . import __version__
from .config import AreaRegistry, Config, load_areas
from .record import Business
from .runlog import RunLog
from .state import State, now


class Stop:
    """Ctrl-C is a clean shutdown: finish the in-flight search, flush, exit 0."""

    def __init__(self):
        self.requested = False

    def install(self):
        def handler(signum, frame):
            if self.requested:
                raise KeyboardInterrupt
            self.requested = True
            print('\nStopping after the current search (Ctrl-C again to abort now)...')
        signal.signal(signal.SIGINT, handler)


class Run:
    def __init__(self, cfg: Config, areas: AreaRegistry, run_dir: Path, config_path: Path | None = None,
                 echo: bool = True):
        self.cfg = cfg
        self.areas = areas
        self.dir = Path(run_dir)
        self.id = self.dir.name
        self.config_path = config_path
        for d in (self.dir, self.raw_dir, self.stage_dir):
            d.mkdir(parents=True, exist_ok=True)
        self.state = State(self.dir / 'state.sqlite')
        self.log = RunLog(self.dir / 'run.log', echo=echo)
        self.stop = Stop()
        self.today = date.today().isoformat()
        self.options: dict = {}

    # ---------------------------------------------------------------- paths
    @property
    def raw_dir(self) -> Path: return self.dir / 'raw'
    @property
    def stage_dir(self) -> Path: return self.dir / 'stages'
    @property
    def master_path(self) -> Path: return self.dir / 'master.json'
    @property
    def workbook_path(self) -> Path: return self.dir / self.cfg.output.workbook
    @property
    def manifest_path(self) -> Path: return self.dir / 'manifest.json'

    # ------------------------------------------------------------- open/close
    @classmethod
    def create(cls, cfg: Config, areas: AreaRegistry, config_path: Path, run_id: str | None = None,
               out_dir: str | None = None, echo: bool = True) -> 'Run':
        rid = run_id or f'{date.today().isoformat()}-{cfg.run_id_prefix}'
        base = Path(out_dir or cfg.output.dir)
        run = cls(cfg, areas, base / rid, config_path, echo=echo)
        snap = run.dir / 'config.snapshot.yaml'
        if True:  # the latest config used is what resume/report should see
            snap.write_text(yaml.safe_dump(cfg.model_dump(mode='json', by_alias=True), sort_keys=False))
            (run.dir / 'areas.snapshot.yaml').write_text(
                yaml.safe_dump(areas.model_dump(mode='json', by_alias=True, exclude_none=True), sort_keys=False))
        return run

    @classmethod
    def open(cls, run_id: str, out_dir: str = 'out', echo: bool = True) -> 'Run':
        d = Path(out_dir) / run_id
        if not (d / 'config.snapshot.yaml').exists():
            raise FileNotFoundError(f'no run at {d} (missing config.snapshot.yaml)')
        cfg = Config.model_validate(yaml.safe_load((d / 'config.snapshot.yaml').read_text()))
        areas = load_areas(d / 'areas.snapshot.yaml')
        return cls(cfg, areas, d, echo=echo)

    def close(self):
        self.log.close()
        self.state.close()

    # ------------------------------------------------------------ artifacts
    def raw_path(self, source: str) -> Path:
        return self.raw_dir / f'{source}.jsonl'

    def append_raw(self, source: str, rows: list[dict]):
        with open(self.raw_path(source), 'a', encoding='utf-8') as fh:
            for r in rows:
                fh.write(json.dumps(r, ensure_ascii=False) + '\n')

    def read_raw(self, source: str) -> list[dict]:
        p = self.raw_path(source)
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text(encoding='utf-8').splitlines() if line.strip()]

    def write_stage(self, name: str, records: list[Business]):
        (self.stage_dir / f'{name}.json').write_text(
            json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=1))

    def read_stage(self, name: str) -> list[Business]:
        p = self.stage_dir / f'{name}.json'
        if not p.exists():
            raise FileNotFoundError(f'stage "{name}" has no output yet ({p}); run it first')
        return [Business.from_dict(d) for d in json.loads(p.read_text())]

    def write_master(self, records: list[Business]):
        self.master_path.write_text(json.dumps([r.to_dict() for r in records], ensure_ascii=False, indent=1))

    def read_master(self) -> list[Business]:
        return [Business.from_dict(d) for d in json.loads(self.master_path.read_text())]

    # -------------------------------------------------------------- manifest
    def manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text())
        return {}

    def update_manifest(self, **kw):
        m = self.manifest()
        m.setdefault('run_id', self.id)
        m.setdefault('created_at', now())
        m['updated_at'] = now()
        m['pipeline'] = self.cfg.pipeline
        m['versions'] = {'lagosdata': __version__, 'python': platform.python_version()}
        for k, v in kw.items():
            if isinstance(v, dict) and isinstance(m.get(k), dict):
                m[k].update(v)
            else:
                m[k] = v
        self.manifest_path.write_text(json.dumps(m, indent=2, ensure_ascii=False, default=str))
