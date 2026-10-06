"""Structured JSONL run log (out/<run-id>/run.log) plus a short console echo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .state import now


class RunLog:
    def __init__(self, path: str | Path, echo: bool = True):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fh = open(self.path, 'a', encoding='utf-8')
        self.echo = echo

    def event(self, kind: str, msg: str = '', **data):
        rec = {'ts': now(), 'kind': kind, 'msg': msg, **data}
        self.fh.write(json.dumps(rec, ensure_ascii=False, default=str) + '\n')
        self.fh.flush()
        if self.echo and msg:
            print(f'[{kind}] {msg}', file=sys.stderr)

    def close(self):
        self.fh.close()
